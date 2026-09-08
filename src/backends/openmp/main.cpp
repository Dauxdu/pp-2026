#include "../../core/audit.hpp"
#include "../../core/sha256.hpp"

#include <omp.h>

#include <algorithm>
#include <iostream>
#include <optional>
#include <string>
#include <vector>

// Аргументы командной строки.
struct CliArgs
{
    std::string config_path;
    std::string output_path = "result.json";
    std::optional<int> threads;
};

CliArgs parse_args(int argc, char **argv)
{
    CliArgs args;
    for (int i = 1; i < argc; ++i)
    {
        const std::string arg = argv[i];
        if (arg == "--config" && i + 1 < argc)
        {
            args.config_path = argv[++i];
        }
        else if (arg == "--output" && i + 1 < argc)
        {
            args.output_path = argv[++i];
        }
        else if (arg == "--threads" && i + 1 < argc)
        {
            args.threads = std::stoi(argv[++i]);
        }
    }

    if (args.config_path.empty())
    {
        throw std::runtime_error(std::string("использование: ") + argv[0] + " --config <config.json> [--output <result.json>] [--threads <N>]");
    }

    return args;
}

// Перебор выделенного куска диапазона. Используется локальный вектор для исключения гонок данных.
std::vector<Match> scan_chunk(const AuditConfig &config, const TargetIndex &targets, const RangeChunk &chunk)
{
    std::vector<Match> local_matches;
    if (chunk.begin >= chunk.end)
    {
        return local_matches;
    }

    CandidateCounter counter(config.charset, config.password_length, chunk.begin);
    for (std::uint64_t index = chunk.begin; index < chunk.end; ++index)
    {
        const std::string password = counter.password();
        const std::string hash = hash_password(config.salt, password, config.iterations);

        if (const int *id = targets.find(hash))
        {
            local_matches.push_back({*id, password, hash});
        }
        counter.advance();
    }
    return local_matches;
}

AuditResult run_audit(const AuditConfig &config, const TargetIndex &targets, int requested_threads)
{
    AuditResult result;
    result.backend = "openmp";
    result.size_code = config.size_code;
    result.hash_type = config.hash_type;
    result.iterations = config.iterations;
    result.range_begin = config.range_begin;
    result.range_end = config.range_end;

    // Фиксируем число потоков, запрещая OpenMP менять его динамически
    omp_set_dynamic(0);
    omp_set_num_threads(requested_threads);
    const int actual_threads = omp_get_max_threads();

    const std::vector<RangeChunk> chunks = split_range(config.range_begin, config.range_end, actual_threads);
    std::vector<std::vector<Match>> per_thread_matches(chunks.size());

    Stopwatch stopwatch;
    stopwatch.start();

    // Каждый поток обрабатывает свой кусок и пишет в изолированный массив
#pragma omp parallel num_threads(actual_threads)

    {
        const int tid = omp_get_thread_num();
        per_thread_matches[static_cast<std::size_t>(tid)] = scan_chunk(config, targets, chunks[static_cast<std::size_t>(tid)]);
    }

    result.time_seconds = stopwatch.elapsed_seconds();
    result.num_threads = actual_threads;
    result.candidates_checked = config.candidate_count();

    for (auto &local : per_thread_matches)
    {
        result.matches.insert(result.matches.end(), local.begin(), local.end());
    }
    std::sort(result.matches.begin(), result.matches.end(),
              [](const Match &a, const Match &b)
              { return a.id < b.id; });

    return result;
}

int main(int argc, char **argv)
{
    try
    {
        const CliArgs args = parse_args(argc, argv);
        const AuditConfig config = AuditConfig::load(args.config_path);
        const TargetIndex targets = TargetIndex::load(config.targets_file);

        const int requested_threads = args.threads.value_or(omp_get_max_threads());
        AuditResult result = run_audit(config, targets, requested_threads);
        result.write(args.output_path);

        std::cout << "checked=" << result.candidates_checked
                  << " threads=" << result.num_threads
                  << " time=" << result.time_seconds << " s"
                  << " matches=" << result.matches.size() << "\n";
    }
    catch (const std::exception &e)
    {
        std::cerr << "Ошибка: " << e.what() << "\n";
        return 1;
    }

    return 0;
}
