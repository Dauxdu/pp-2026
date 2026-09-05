/**
 * @file audit.hpp
 * @brief Предметная логика перебора паролей, общая для всех бэкендов.
 */

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

/**
 * @struct AuditConfig
 * @brief Параметры аудита, сгенерированные скриптом scripts/generate_data.py.
 */
struct AuditConfig
{
    std::string salt;                   ///< Соль для хэширования
    std::string charset;                ///< Алфавит используемых символов
    std::string hash_type;              ///< Тип хэш-функции
    int password_length = 0;            ///< Длина генерируемых паролей
    int iterations = 1;                 ///< Количество итераций хэширования
    std::uint64_t range_begin = 0;      ///< Начальный индекс диапазона перебора
    std::uint64_t range_end = 0;        ///< Конечный индекс диапазона перебора (не включая)
    int size_code = -1;                 ///< Код размера задачи для отчетности
    std::filesystem::path targets_file; ///< Путь к файлу с искомыми хэшами

    /**
     * @brief Загружает конфигурацию аудита из JSON-файла.
     * @param path Путь к конфигурационному файлу config.json.
     * @return Заполненный объект конфигурации AuditConfig.
     * @throws std::runtime_error Если файл не найден или параметры некорректны.
     */
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
        config.targets_file = targets_path.is_relative() ? path.parent_path() / targets_path : targets_path;

        if (config.charset.size() < 2 || config.password_length < 1 || config.range_end <= config.range_begin)
        {
            throw std::runtime_error("некорректные параметры конфигурации");
        }

        return config;
    }

    /**
     * @brief Возвращает общее количество кандидатов в диапазоне.
     * @return Количество комбинаций для проверки.
     */
    std::uint64_t candidate_count() const { return range_end - range_begin; }
};

/**
 * @struct TargetIndex
 * @brief Индекс целевых хэшей, загруженных из файла targets.jsonl.
 *
 * Содержит идентификаторы и хэши. Искомые пароли определяются в процессе аудита.
 */
struct TargetIndex
{
private:
    std::unordered_map<std::string, int> id_by_hash_; ///< Хэш-карта соответствия хэша и ID цели

public:
    /**
     * @brief Загружает список искомых хэшей из файла.
     * @param path Путь к файлу targets.jsonl.
     * @return Проиндексированный объект TargetIndex.
     * @throws std::runtime_error Если файл не может быть открыт.
     */
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

    /**
     * @brief Поиск идентификатора цели по её хэшу.
     * @param hash Строка хэша для проверки.
     * @return Указатель на ID цели, если хэш найден, иначе nullptr.
     */
    const int *
    find(const std::string &hash) const
    {
        const auto it = id_by_hash_.find(hash);
        return it == id_by_hash_.end() ? nullptr : &it->second;
    }
};

/**
 * @class CandidateCounter
 * @brief Счётчик кандидатов, представляющий индекс в виде строки пароля.
 */
class CandidateCounter
{
private:
    const std::string &charset_;       ///< Алфавит символов
    std::vector<std::uint8_t> digits_; ///< Позиционные индексы символов текущего пароля

public:
    /**
     * @brief Конструктор счётчика кандидатов.
     * @param charset Ссылка на строку-алфавит.
     * @param length Длина генерируемого пароля.
     * @param start_index Начальный числовой индекс для генерации.
     */
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

    /**
     * @brief Генерирует текущую строку пароля на основе внутреннего состояния разрядов.
     * @return Строка пароля.
     */
    std::string password() const
    {
        std::string out(digits_.size(), '\0');
        for (std::size_t i = 0; i < digits_.size(); ++i)
        {
            out[i] = charset_[digits_[i]];
        }
        return out;
    }

    /**
     * @brief Инкрементирует состояние счётчика для перехода к следующему кандидату.
     */
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

/**
 * @struct Match
 * @brief Структура, описывающая успешно найденное совпадение.
 */
struct Match
{
    int id = 0;           ///< Идентификатор цели
    std::string password; ///< Подобранный пароль
    std::string hash;     ///< Соответствующий хэш пароля
};

/**
 * @struct AuditResult
 * @brief Результат выполнения аудита конкретным бэкендом.
 *
 * Данные структуры считываются внешними скриптами верификации и построения графиков.
 */
struct AuditResult
{
    std::string backend;                  ///< Идентификатор бэкенда ("seq", "openmp", "mpi", "cuda")
    int size_code = -1;                   ///< Код размера задачи
    std::string config_file;              ///< Путь к файлу конфигурации
    std::string hash_type;                ///< Тип хэша
    int iterations = 1;                   ///< Число итераций хэширования
    std::uint64_t range_begin = 0;        ///< Начало проверенного поддиапазона
    std::uint64_t range_end = 0;          ///< Конец проверенного поддиапазона
    std::uint64_t candidates_checked = 0; ///< Фактическое число проверенных кандидатов
    double time_seconds = 0.0;            ///< Время выполнения в секундах
    int num_threads = 1;                  ///< Число потоков, использованных бэкендом
    std::vector<Match> matches;           ///< Список найденных совпадений

    /**
     * @brief Вычисляет производительность (скорость перебора).
     * @return Количество проверяемых кандидатов в секунду.
     */
    double throughput_per_second() const
    {
        return time_seconds > 0.0 ? static_cast<double>(candidates_checked) / time_seconds : 0.0;
    }

    /**
     * @brief Сохраняет результаты аудита в файл в формате JSON.
     * @param path Путь для сохранения результирующего JSON-файла.
     * @throws std::runtime_error Если не удается открыть файл на запись.
     */
    void write(const std::filesystem::path &path) const
    {
        nlohmann::json out;
        out["program"] = backend;
        out["size_code"] = size_code;
        out["config_file"] = config_file;
        out["hash_type"] = hash_type;
        out["iterations"] = iterations;
        out["range_begin"] = range_begin;
        out["range_end"] = range_end;
        out["candidates_checked"] = candidates_checked;
        out["time_seconds"] = time_seconds;
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

/**
 * @class Stopwatch
 * @brief Секундомер для измерения интервалов времени работы бэкендов.
 */
class Stopwatch
{
private:
    std::chrono::steady_clock::time_point start_;

public:
    /**
     * @brief Фиксирует точку начала отсчета времени.
     */
    void start() { start_ = std::chrono::steady_clock::now(); }

    /**
     * @brief Возвращает время, прошедшее с момента вызова start().
     * @return Время в секундах.
     */
    double elapsed_seconds() const
    {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - start_).count();
    }
};