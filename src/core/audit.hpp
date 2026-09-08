// audit.hpp
#pragma once
#include <nlohmann/json.hpp>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

// Параметры аудита из config.json.
struct AuditConfig
{
    std::string salt;
    std::string charset;
    std::string hash_type;
    int password_length = 0;
    int iterations = 1;
    std::uint64_t range_begin = 0;
    std::uint64_t range_end = 0;
    int size_code = -1;
    std::filesystem::path targets_file;

    static AuditConfig load(const std::filesystem::path &path)
    {
        std::ifstream stream(path);
        if (!stream)
        {
            throw std::runtime_error("не удалось открыть файл конфигурации: " + path.string());
        }

        const nlohmann::json j = nlohmann::json::parse(stream);
        AuditConfig config;

        config.salt = j.at("salt").get<std::string>();
        config.charset = j.at("charset").get<std::string>();
        config.hash_type = j.value("hash_type", std::string{"sha256"});
        config.password_length = j.at("password_length").get<int>();
        config.iterations = std::max(1, j.at("iterations").get<int>());
        config.range_begin = j.at("range_begin").get<std::uint64_t>();
        config.range_end = j.at("range_end").get<std::uint64_t>();
        config.size_code = j.value("size_code", -1);

        std::filesystem::path targets_path = j.at("targets_file").get<std::string>();
        // Относительный путь считаем от каталога конфигурации.
        config.targets_file = targets_path.is_relative() ? path.parent_path() / targets_path : targets_path;

        if (config.charset.size() < 2 || config.password_length < 1 || config.range_end <= config.range_begin)
        {
            throw std::runtime_error("некорректные параметры конфигурации");
        }

        return config;
    }

    std::uint64_t candidate_count() const { return range_end - range_begin; }
};

// Индекс искомых хэшей.
struct TargetIndex
{
private:
    std::unordered_map<std::string, int> id_by_hash_;

public:
    static TargetIndex load(const std::filesystem::path &path)
    {
        std::ifstream stream(path);
        if (!stream)
        {
            throw std::runtime_error("не удалось открыть файл с целевыми хэшами: " + path.string());
        }

        TargetIndex index;
        std::string line;
        while (std::getline(stream, line))
        {
            if (line.find_first_not_of(" \t\r\n") == std::string::npos)
            {
                continue;
            }

            const nlohmann::json t = nlohmann::json::parse(line);
            index.id_by_hash_[t.at("hash").get<std::string>()] = t.at("id").get<int>();
        }
        return index;
    }

    const int *find(const std::string &hash) const
    {
        const auto it = id_by_hash_.find(hash);
        return it == id_by_hash_.end() ? nullptr : &it->second;
    }
};

// Преобразует индекс в пароль по алфавиту.
class CandidateCounter
{
private:
    const std::string &charset_;
    std::vector<std::uint8_t> digits_;

public:
    CandidateCounter(const std::string &charset, int length, std::uint64_t start_index)
        : charset_(charset), digits_(static_cast<std::size_t>(length), 0)
    {
        std::uint64_t index = start_index;
        const std::size_t base = charset_.size();
        for (auto pos = static_cast<int>(digits_.size()) - 1; pos >= 0; --pos)
        {
            digits_[static_cast<std::size_t>(pos)] = static_cast<std::uint8_t>(index % base);
            index /= base;
        }
    }

    std::string password() const
    {
        std::string out(digits_.size(), '\0');
        for (std::size_t i = 0; i < digits_.size(); ++i)
        {
            out[i] = charset_[digits_[i]];
        }
        return out;
    }

    // Инкремент с переносом по алфавиту.
    void advance()
    {
        const std::size_t base = charset_.size();
        for (auto pos = static_cast<int>(digits_.size()) - 1; pos >= 0; --pos)
        {
            if (++digits_[static_cast<std::size_t>(pos)] < base)
            {
                return;
            }
            digits_[static_cast<std::size_t>(pos)] = 0;
        }
    }
};

struct Match
{
    int id = 0;
    std::string password;
    std::string hash;
};

// Смежный кусок диапазона [begin, end).
struct RangeChunk
{
    std::uint64_t begin = 0;
    std::uint64_t end = 0;
};

// Делит диапазон на части, остаток распределяется первым кускам.
inline std::vector<RangeChunk> split_range(std::uint64_t begin, std::uint64_t end, int parts)
{
    const std::uint64_t total = end - begin;
    const std::uint64_t base = total / static_cast<std::uint64_t>(parts);
    const std::uint64_t remainder = total % static_cast<std::uint64_t>(parts);

    std::vector<RangeChunk> chunks;
    chunks.reserve(static_cast<std::size_t>(parts));

    std::uint64_t cursor = begin;
    for (int i = 0; i < parts; ++i)
    {
        const std::uint64_t size = base + (static_cast<std::uint64_t>(i) < remainder ? 1 : 0);
        chunks.push_back({cursor, cursor + size});
        cursor += size;
    }
    return chunks;
}

// Результат аудита для верификации и графиков.
struct AuditResult
{
    std::string backend;
    int size_code = -1;
    std::string hash_type;
    int iterations = 1;
    std::uint64_t range_begin = 0;
    std::uint64_t range_end = 0;
    std::uint64_t candidates_checked = 0;
    double time_seconds = 0.0;
    int num_threads = 1;
    std::vector<Match> matches;

    double throughput_per_second() const
    {
        return time_seconds > 0.0 ? static_cast<double>(candidates_checked) / time_seconds : 0.0;
    }

    void write(const std::filesystem::path &path) const
    {
        nlohmann::json out;
        out["program"] = backend;
        out["size_code"] = size_code;
        out["hash_type"] = hash_type;
        out["iterations"] = iterations;
        out["range_begin"] = range_begin;
        out["range_end"] = range_end;
        out["candidates_checked"] = candidates_checked;
        out["time_seconds"] = time_seconds;
        out["threads"] = num_threads;
        out["throughput_per_second"] = throughput_per_second();
        out["matches"] = nlohmann::json::array();

        for (const auto &m : matches)
        {
            out["matches"].push_back({{"id", m.id}, {"password", m.password}, {"hash", m.hash}});
        }

        if (path.has_parent_path())
        {
            std::filesystem::create_directories(path.parent_path());
        }

        std::ofstream ofs(path);
        if (!ofs)
        {
            throw std::runtime_error("не удалось открыть файл для записи результатов: " + path.string());
        }
        ofs << out.dump(2) << "\n";
    }
};

class Stopwatch
{
private:
    std::chrono::steady_clock::time_point start_;

public:
    void start() { start_ = std::chrono::steady_clock::now(); }

    double elapsed_seconds() const
    {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
    }
};