#include "../../core/audit.hpp"
#include "../../core/sha256.hpp"

#include <mpi.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

// Аргументы командной строки.
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
        {
            args.config_path = argv[++i];
        }
        else if (arg == "--output" && i + 1 < argc)
        {
            args.output_path = argv[++i];
        }
    }

    if (args.config_path.empty())
    {
        throw std::runtime_error(std::string("использование: ") + argv[0] + " --config <config.json> [--output <result.json>]");
    }

    return args;
}

// Перебор одного смежного куска диапазона, с локальным для процесса вектором совпадений.
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

std::size_t record_size(int password_length)
{
    return sizeof(std::int32_t) + static_cast<std::size_t>(password_length) + 64;
}

std::vector<char> pack_matches(const std::vector<Match> &matches, int password_length)
{
    const std::size_t size = record_size(password_length);
    std::vector<char> buf(matches.size() * size);
    std::size_t offset = 0;
    for (const auto &m : matches)
    {
        const std::int32_t id = m.id;
        std::memcpy(buf.data() + offset, &id, sizeof(id));
        offset += sizeof(id);
        std::memcpy(buf.data() + offset, m.password.data(), static_cast<std::size_t>(password_length));
        offset += static_cast<std::size_t>(password_length);
        std::memcpy(buf.data() + offset, m.hash.data(), 64);
        offset += 64;
    }

    return buf;
}

std::vector<Match> unpack_matches(const std::vector<char> &buf, int password_length)
{
    const std::size_t size = record_size(password_length);
    std::vector<Match> matches;
    if (size == 0)
    {
        return matches;
    }

    matches.reserve(buf.size() / size);
    for (std::size_t offset = 0; offset < buf.size(); offset += size)
    {
        Match m;
        std::int32_t id;
        std::memcpy(&id, buf.data() + offset, sizeof(id));
        m.id = id;
        m.password.assign(buf.data() + offset + sizeof(id), static_cast<std::size_t>(password_length));
        m.hash.assign(buf.data() + offset + sizeof(id) + static_cast<std::size_t>(password_length), 64);
        matches.push_back(std::move(m));
    }

    return matches;
}

int main(int argc, char **argv)
{
    MPI_Init(&argc, &argv);
    int rank = 0;
    int world_size = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &world_size);

    try
    {
        const CliArgs args = parse_args(argc, argv);
        const AuditConfig config = AuditConfig::load(args.config_path);
        const TargetIndex targets = TargetIndex::load(config.targets_file);

        const std::vector<RangeChunk> chunks = split_range(config.range_begin, config.range_end, world_size);
        const RangeChunk my_chunk = chunks[static_cast<std::size_t>(rank)];

        MPI_Barrier(MPI_COMM_WORLD);
        Stopwatch stopwatch;
        stopwatch.start();
        std::vector<Match> local_matches = scan_chunk(config, targets, my_chunk);
        const double local_time = stopwatch.elapsed_seconds();

        double max_time = 0.0;
        MPI_Reduce(&local_time, &max_time, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);

        if (rank == 0)
        {
            std::vector<Match> all_matches = std::move(local_matches);
            for (int src = 1; src < world_size; ++src)
            {
                int count = 0;
                MPI_Status status;
                MPI_Recv(&count, 1, MPI_INT, src, 0, MPI_COMM_WORLD, &status);
                if (count > 0)
                {
                    std::vector<char> buf(static_cast<std::size_t>(count) * record_size(config.password_length));
                    MPI_Recv(buf.data(), static_cast<int>(buf.size()), MPI_BYTE, src, 1, MPI_COMM_WORLD, &status);
                    std::vector<Match> received = unpack_matches(buf, config.password_length);
                    all_matches.insert(all_matches.end(), received.begin(), received.end());
                }
            }

            std::sort(all_matches.begin(), all_matches.end(),
                      [](const Match &a, const Match &b)
                      { return a.id < b.id; });

            AuditResult result;
            result.backend = "mpi";
            result.size_code = config.size_code;
            result.hash_type = config.hash_type;
            result.iterations = config.iterations;
            result.range_begin = config.range_begin;
            result.range_end = config.range_end;
            result.candidates_checked = config.candidate_count();
            result.time_seconds = max_time;
            result.num_threads = world_size; // MPI-процессы
            result.matches = std::move(all_matches);
            result.write(args.output_path);

            std::cout << "checked=" << result.candidates_checked
                      << " processes=" << world_size
                      << " time=" << result.time_seconds << " s"
                      << " matches=" << result.matches.size() << "\n";
        }
        else
        {
            const int count = static_cast<int>(local_matches.size());
            MPI_Send(&count, 1, MPI_INT, 0, 0, MPI_COMM_WORLD);
            if (count > 0)
            {
                const std::vector<char> buf = pack_matches(local_matches, config.password_length);
                MPI_Send(buf.data(), static_cast<int>(buf.size()), MPI_BYTE, 0, 1, MPI_COMM_WORLD);
            }
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "[rank " << rank << "] Ошибка: " << e.what() << "\n";
        MPI_Abort(MPI_COMM_WORLD, 1);
    }

    MPI_Finalize();
    return 0;
}
