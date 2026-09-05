#include "../audit.hpp"
#include "../sha256.hpp"

#include <algorithm>
#include <iostream>
#include <string>

namespace
{
    struct CliArgs
    {
        std::string config_path;
        std::string output_path = "result.json";
    };

    CliArgs parse_args(int argc, char **argv)
    {
        CliArgs args;
        for (int i = 1; i < argc; ++i)
        {
            const std::string arg = argv[i];
            if (arg == "--config" && i + 1 < argc)
                args.config_path = argv[++i];
            else if (arg == "--output" && i + 1 < argc)
                args.output_path = argv[++i];
        }
        if (args.config_path.empty())
            throw std::runtime_error(
                std::string("usage: ") + argv[0] + " --config <config.json> [--output <result.json>]");
        return args;
    }

    AuditResult run_audit(const AuditConfig &config, const TargetIndex &targets)
    {
        AuditResult result;
        result.backend = "seq";
        result.size_code = config.size_code;
        result.hash_type = config.hash_type;
        result.iterations = config.iterations;
        result.range_begin = config.range_begin;
        result.range_end = config.range_end;

        CandidateCounter counter(config.charset, config.password_length, config.range_begin);
        Stopwatch stopwatch;
        stopwatch.start();

        for (std::uint64_t index = config.range_begin; index < config.range_end; ++index)
        {
            const std::string password = counter.password();
            const std::string hash = hash_password(config.salt, password, config.iterations);

            if (const int *id = targets.find(hash))
                result.matches.push_back({*id, password, hash});

            counter.advance();
        }

        result.time_seconds = stopwatch.elapsed_seconds();
        result.candidates_checked = config.candidate_count();
        std::sort(result.matches.begin(), result.matches.end(),
                  [](const Match &a, const Match &b)
                  { return a.id < b.id; });
        return result;
    }

} // namespace

int main(int argc, char **argv)
{
    try
    {
        const CliArgs args = parse_args(argc, argv);
        const AuditConfig config = AuditConfig::load(args.config_path);
        const TargetIndex targets = TargetIndex::load(config.targets_file);

        AuditResult result = run_audit(config, targets);
        result.config_file = args.config_path;
        result.write(args.output_path);

        std::cout << "checked=" << result.candidates_checked
                  << " time=" << result.time_seconds << " s"
                  << " matches=" << result.matches.size() << "\n";
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}