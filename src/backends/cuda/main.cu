#include "../../core/audit.hpp"
#include "../../core/sha256.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

constexpr int kMaxPasswordLen = 32;
constexpr int kMaxMessageLen = 96;
constexpr int kDigestLen = 32;
constexpr int kMaxCharsetLen = 96;

#define CUDA_CHECK(call)                                                                         \
    do                                                                                           \
    {                                                                                            \
        cudaError_t _status = (call);                                                            \
        if (_status != cudaSuccess)                                                              \
        {                                                                                        \
            throw std::runtime_error(std::string("CUDA error: ") + cudaGetErrorString(_status) + \
                                     " (" #call ")");                                            \
        }                                                                                        \
    } while (0)

// --- Device-код: выполняется на GPU --------------------------------------

__constant__ std::uint32_t kRoundConstants[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
    0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
    0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
    0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
    0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
    0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u};

__device__ __forceinline__ std::uint32_t rotr(std::uint32_t x, std::uint32_t n)
{
    return (x >> n) | (x << (32 - n));
}

__device__ void sha256_transform(std::uint32_t state[8], const std::uint8_t block[64])
{
    std::uint32_t m[64];
    for (int i = 0, j = 0; i < 16; ++i, j += 4)
    {
        m[i] = (static_cast<std::uint32_t>(block[j]) << 24) | (static_cast<std::uint32_t>(block[j + 1]) << 16) |
               (static_cast<std::uint32_t>(block[j + 2]) << 8) | static_cast<std::uint32_t>(block[j + 3]);
    }

    for (int i = 16; i < 64; ++i)
    {
        const std::uint32_t s0 = rotr(m[i - 15], 7) ^ rotr(m[i - 15], 18) ^ (m[i - 15] >> 3);
        const std::uint32_t s1 = rotr(m[i - 2], 17) ^ rotr(m[i - 2], 19) ^ (m[i - 2] >> 10);
        m[i] = m[i - 16] + s0 + m[i - 7] + s1;
    }

    std::uint32_t a = state[0], b = state[1], c = state[2], d = state[3];
    std::uint32_t e = state[4], f = state[5], g = state[6], h = state[7];

    for (int i = 0; i < 64; ++i)
    {
        const std::uint32_t s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const std::uint32_t ch = (e & f) ^ (~e & g);
        const std::uint32_t t1 = h + s1 + ch + kRoundConstants[i] + m[i];
        const std::uint32_t s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const std::uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        const std::uint32_t t2 = s0 + maj;
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = c;
        c = b;
        b = a;
        a = t1 + t2;
    }

    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}

__device__ void sha256_hash(const std::uint8_t *msg, std::size_t len, std::uint8_t digest[kDigestLen])
{
    std::uint8_t buf[128] = {};
    for (std::size_t i = 0; i < len; ++i)
    {
        buf[i] = msg[i];
    }
    buf[len] = 0x80u;

    const std::size_t total_len = len + 1;
    const std::size_t num_blocks = (total_len > 56) ? 2 : 1;
    const std::size_t padded_len = num_blocks * 64;
    const std::uint64_t bit_len = static_cast<std::uint64_t>(len) * 8u;
    for (int i = 0; i < 8; ++i)
    {
        buf[padded_len - 8 + i] = static_cast<std::uint8_t>(bit_len >> (56 - 8 * i));
    }

    std::uint32_t state[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                              0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    for (std::size_t blk = 0; blk < num_blocks; ++blk)
    {
        sha256_transform(state, buf + blk * 64);
    }

    for (int i = 0; i < 8; ++i)
    {
        for (int j = 0; j < 4; ++j)
        {
            digest[i * 4 + j] = static_cast<std::uint8_t>(state[i] >> (24 - 8 * j));
        }
    }
}

__device__ void index_to_password(std::uint64_t index, const char *charset, int charset_size, int length,
                                  char *out)
{
    for (int pos = length - 1; pos >= 0; --pos)
    {
        out[pos] = charset[index % static_cast<unsigned>(charset_size)];
        index /= static_cast<unsigned>(charset_size);
    }
}

__global__ void audit_kernel(std::uint64_t range_begin, std::uint64_t range_end, const char *charset,
                             int charset_size, int password_length, const char *salt, int salt_length,
                             int iterations, const std::uint8_t *target_digests, const int *target_ids,
                             int num_targets, int *out_match_count, int *out_match_ids,
                             std::uint64_t *out_match_indices, int max_matches)
{
    const std::uint64_t stride = static_cast<std::uint64_t>(blockDim.x) * gridDim.x;
    std::uint64_t index = range_begin + static_cast<std::uint64_t>(blockIdx.x) * blockDim.x + threadIdx.x;

    for (; index < range_end; index += stride)
    {
        char password[kMaxPasswordLen];
        index_to_password(index, charset, charset_size, password_length, password);

        std::uint8_t message[kMaxMessageLen];
        for (int i = 0; i < salt_length; ++i)
        {
            message[i] = static_cast<std::uint8_t>(salt[i]);
        }

        for (int i = 0; i < password_length; ++i)
        {
            message[salt_length + i] = static_cast<std::uint8_t>(password[i]);
        }

        std::uint8_t digest[kDigestLen];
        sha256_hash(message, static_cast<std::size_t>(salt_length + password_length), digest);
        for (int it = 1; it < iterations; ++it)
        {
            sha256_hash(digest, kDigestLen, digest);
        }

        for (int t = 0; t < num_targets; ++t)
        {
            bool match = true;
            for (int b = 0; b < kDigestLen; ++b)
            {
                if (digest[b] != target_digests[t * kDigestLen + b])
                {
                    match = false;
                    break;
                }
            }

            if (match)
            {
                const int slot = atomicAdd(out_match_count, 1);
                if (slot < max_matches)
                {
                    out_match_ids[slot] = target_ids[t];
                    out_match_indices[slot] = index;
                }
            }
        }
    }
}

// --- Хост-код: обычный C++, выполняется на CPU ---------------------------

struct CliArgs
{
    std::string config_path;
    std::string output_path = "result.json";
    int block_size = 256;
    std::optional<int> grid_size;
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
        else if (arg == "--block-size" && i + 1 < argc)
        {
            args.block_size = std::stoi(argv[++i]);
        }
        else if (arg == "--grid-size" && i + 1 < argc)
        {
            args.grid_size = std::stoi(argv[++i]);
        }
    }
    if (args.config_path.empty())
    {
        throw std::runtime_error(std::string("usage: ") + argv[0] +
                                 " --config <config.json> [--output <result.json>]"
                                 " [--block-size <N>] [--grid-size <N>]");
    }

    return args;
}

void hex_to_bytes(const std::string &hex, std::uint8_t out[kDigestLen])
{
    for (int i = 0; i < kDigestLen; ++i)
    {
        out[i] = static_cast<std::uint8_t>(std::stoul(hex.substr(static_cast<std::size_t>(i) * 2, 2), nullptr, 16));
    }
}

int main(int argc, char **argv)
{
    try
    {
        const CliArgs args = parse_args(argc, argv);
        const AuditConfig config = AuditConfig::load(args.config_path);
        const TargetIndex targets = TargetIndex::load(config.targets_file);

        if (config.password_length > kMaxPasswordLen)
        {
            throw std::runtime_error("password_length превышает предел CUDA-бэкенда (kMaxPasswordLen)");
        }

        if (config.charset.size() > static_cast<std::size_t>(kMaxCharsetLen))
        {
            throw std::runtime_error("charset превышает предел CUDA-бэкенда (kMaxCharsetLen)");
        }

        if (config.salt.size() + config.password_length > static_cast<std::size_t>(kMaxMessageLen))
        {
            throw std::runtime_error("salt+password превышает предел CUDA-бэкенда (kMaxMessageLen)");
        }

        const auto &entries = targets.entries();
        const int num_targets = static_cast<int>(entries.size());
        std::vector<int> target_ids;
        std::vector<std::uint8_t> target_digests(static_cast<std::size_t>(num_targets) * kDigestLen);
        target_ids.reserve(static_cast<std::size_t>(num_targets));
        int idx = 0;
        for (const auto &[hash, id] : entries)
        {
            target_ids.push_back(id);
            hex_to_bytes(hash, target_digests.data() + static_cast<std::size_t>(idx) * kDigestLen);
            ++idx;
        }

        const int block_size = args.block_size;
        const std::uint64_t candidate_count = config.candidate_count();
        const int grid_size = args.grid_size.value_or(static_cast<int>(std::min<std::uint64_t>(
            (candidate_count + static_cast<std::uint64_t>(block_size) - 1) / static_cast<std::uint64_t>(block_size),
            65535)));
        const int max_matches = std::max(num_targets * 4, 64);

        char *d_charset = nullptr;
        char *d_salt = nullptr;
        std::uint8_t *d_target_digests = nullptr;
        int *d_target_ids = nullptr;
        int *d_match_count = nullptr;
        int *d_match_ids = nullptr;
        std::uint64_t *d_match_indices = nullptr;

        CUDA_CHECK(cudaMalloc(&d_charset, config.charset.size()));
        CUDA_CHECK(cudaMalloc(&d_salt, config.salt.size()));
        CUDA_CHECK(cudaMalloc(&d_target_digests, target_digests.size()));
        CUDA_CHECK(cudaMalloc(&d_target_ids, target_ids.size() * sizeof(int)));
        CUDA_CHECK(cudaMalloc(&d_match_count, sizeof(int)));
        CUDA_CHECK(cudaMalloc(&d_match_ids, static_cast<std::size_t>(max_matches) * sizeof(int)));
        CUDA_CHECK(cudaMalloc(&d_match_indices, static_cast<std::size_t>(max_matches) * sizeof(std::uint64_t)));

        CUDA_CHECK(cudaMemcpy(d_charset, config.charset.data(), config.charset.size(), cudaMemcpyHostToDevice));
        CUDA_CHECK(cudaMemcpy(d_salt, config.salt.data(), config.salt.size(), cudaMemcpyHostToDevice));
        CUDA_CHECK(cudaMemcpy(d_target_digests, target_digests.data(), target_digests.size(),
                              cudaMemcpyHostToDevice));
        CUDA_CHECK(cudaMemcpy(d_target_ids, target_ids.data(), target_ids.size() * sizeof(int),
                              cudaMemcpyHostToDevice));
        CUDA_CHECK(cudaMemset(d_match_count, 0, sizeof(int)));

        Stopwatch stopwatch;
        stopwatch.start();

        audit_kernel<<<grid_size, block_size>>>(
            config.range_begin, config.range_end, d_charset, static_cast<int>(config.charset.size()),
            config.password_length, d_salt, static_cast<int>(config.salt.size()), config.iterations,
            d_target_digests, d_target_ids, num_targets, d_match_count, d_match_ids, d_match_indices, max_matches);
        CUDA_CHECK(cudaGetLastError());
        CUDA_CHECK(cudaDeviceSynchronize());

        const double time_seconds = stopwatch.elapsed_seconds();

        int match_count = 0;
        CUDA_CHECK(cudaMemcpy(&match_count, d_match_count, sizeof(int), cudaMemcpyDeviceToHost));
        const int copied = std::min(match_count, max_matches);
        std::vector<int> match_ids(static_cast<std::size_t>(copied));
        std::vector<std::uint64_t> match_indices(static_cast<std::size_t>(copied));
        if (copied > 0)
        {
            CUDA_CHECK(cudaMemcpy(match_ids.data(), d_match_ids, match_ids.size() * sizeof(int), cudaMemcpyDeviceToHost));
            CUDA_CHECK(cudaMemcpy(match_indices.data(), d_match_indices, match_indices.size() * sizeof(std::uint64_t), cudaMemcpyDeviceToHost));
        }
        if (match_count > max_matches)
        {
            std::cerr << "ВНИМАНИЕ: найдено " << match_count << " совпадений, буфер вмещал только " << max_matches
                      << " — часть потеряна, увеличьте max_matches\n";
        }

        cudaFree(d_charset);
        cudaFree(d_salt);
        cudaFree(d_target_digests);
        cudaFree(d_target_ids);
        cudaFree(d_match_count);
        cudaFree(d_match_ids);
        cudaFree(d_match_indices);

        AuditResult result;
        result.backend = "cuda";
        result.size_code = config.size_code;
        result.hash_type = config.hash_type;
        result.iterations = config.iterations;
        result.range_begin = config.range_begin;
        result.range_end = config.range_end;
        result.candidates_checked = candidate_count;
        result.time_seconds = time_seconds;
        result.num_threads = block_size * grid_size; // всего GPU-потоков в сетке
        result.block_size = block_size;
        result.grid_size = grid_size;

        for (int i = 0; i < copied; ++i)
        {
            CandidateCounter counter(config.charset, config.password_length,
                                     match_indices[static_cast<std::size_t>(i)]);
            const std::string password = counter.password();
            const std::string hash = hash_password(config.salt, password, config.iterations);
            result.matches.push_back({match_ids[static_cast<std::size_t>(i)], password, hash});
        }
        std::sort(result.matches.begin(), result.matches.end(),
                  [](const Match &a, const Match &b)
                  { return a.id < b.id; });

        result.write(args.output_path);

        std::cout << "checked=" << result.candidates_checked << " grid=" << grid_size << "x" << block_size
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
