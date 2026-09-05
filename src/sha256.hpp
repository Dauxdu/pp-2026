/**
 * @file sha256.hpp
 * @brief Минимальная реализация алгоритма SHA-256 без внешних зависимостей.
 */

#pragma once

#include <array>
#include <cstdint>
#include <cstring>
#include <string>
#include <tuple>

/**
 * @class Sha256
 * @brief Класс для вычисления криптографических хэшей по стандарту SHA-256.
 *
 * Поддерживает потоковую обработку данных через последовательные вызовы update().
 */
class Sha256
{
private:
    /**
     * @brief Константы раундов алгоритма SHA-256 (64 элемента).
     *
     * Первые 32 бита дробных частей кубических корней первых 64 простых чисел.
     */
    static constexpr std::array<std::uint32_t, 64> kRoundConstants = {
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

    /**
     * @brief Вспомогательная функция циклического сдвига 32-битного числа вправо.
     * @param x Исходное число.
     * @param n Количество бит для сдвига.
     * @return Результат циклического сдвига.
     */
    static std::uint32_t rotr(std::uint32_t x, std::uint32_t n)
    {
        return (x >> n) | (x << (32 - n));
    }

    /**
     * @brief Основная функция трансформации 64-байтного блока данных.
     *
     * Выполняет расширение сообщения до 64 слов и запускает основной цикл из 64 раундов SHA-256,
     * обновляя текущие значения регистров state_.
     */
    void transform()
    {
        std::uint32_t m[64];
        for (int i = 0, j = 0; i < 16; ++i, j += 4)
        {
            m[i] = (static_cast<std::uint32_t>(block_[j]) << 24) |
                   (static_cast<std::uint32_t>(block_[j + 1]) << 16) |
                   (static_cast<std::uint32_t>(block_[j + 2]) << 8) |
                   static_cast<std::uint32_t>(block_[j + 3]);
        }

        for (int i = 16; i < 64; ++i)
        {
            const std::uint32_t s0 = rotr(m[i - 15], 7) ^ rotr(m[i - 15], 18) ^ (m[i - 15] >> 3);
            const std::uint32_t s1 = rotr(m[i - 2], 17) ^ rotr(m[i - 2], 19) ^ (m[i - 2] >> 10);
            m[i] = m[i - 16] + s0 + m[i - 7] + s1;
        }

        auto [a, b, c, d, e, f, g, h] = std::tuple{state_[0], state_[1], state_[2], state_[3],
                                                   state_[4], state_[5], state_[6], state_[7]};

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

        state_[0] += a;
        state_[1] += b;
        state_[2] += c;
        state_[3] += d;
        state_[4] += e;
        state_[5] += f;
        state_[6] += g;
        state_[7] += h;
    }

public:
    /**
     * @brief Конструктор по умолчанию. Автоматически сбрасывает состояние.
     */
    Sha256() { reset(); }

    /**
     * @brief Сбрасывает внутреннее состояние хэшера для начала нового вычисления.
     */
    void reset()
    {
        data_len_ = 0;
        bit_len_ = 0;
        state_ = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                  0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    }

    /**
     * @brief Добавляет порцию данных для хэширования.
     * @param data Указатель на массив байт.
     * @param len Размер данных в байтах.
     */
    void update(const std::uint8_t *data, std::size_t len)
    {
        while (len > 0)
        {
            const std::size_t space = 64 - data_len_;
            const std::size_t n = len < space ? len : space;
            std::memcpy(block_ + data_len_, data, n);
            data_len_ += n;
            data += n;
            len -= n;
            if (data_len_ == 64)
            {
                transform();
                bit_len_ += 512;
                data_len_ = 0;
            }
        }
    }

    /**
     * @brief Завершает вычисление хэша, добавляя необходимое дополнение (padding).
     * @return Массив из 32 байт, содержащий итоговый дайджест SHA-256.
     */
    std::array<std::uint8_t, 32> finalize()
    {
        const std::uint64_t total_bits = bit_len_ + static_cast<std::uint64_t>(data_len_) * 8u;

        block_[data_len_++] = 0x80u;
        if (data_len_ > 56)
        {
            while (data_len_ < 64)
            {
                block_[data_len_++] = 0;
            }
            transform();
            data_len_ = 0;
        }

        while (data_len_ < 56)
        {
            block_[data_len_++] = 0;
        }

        for (int i = 0; i < 8; ++i)
        {
            block_[56 + i] = static_cast<std::uint8_t>(total_bits >> (56 - 8 * i));
        }
        transform();

        std::array<std::uint8_t, 32> digest{};
        for (int i = 0; i < 8; ++i)
        {
            for (int j = 0; j < 4; ++j)
            {
                digest[i * 4 + j] = static_cast<std::uint8_t>(state_[i] >> (24 - 8 * j));
            }
        }
        return digest;
    }

    /**
     * @brief Вспомогательный статический метод для хэширования единого блока данных.
     * @param data Указатель на массив байт.
     * @param len Размер данных в байтах.
     * @return Массив из 32 байт с результатом SHA-256.
     */
    static std::array<std::uint8_t, 32> hash(const std::uint8_t *data, std::size_t len)
    {
        Sha256 hasher;
        hasher.update(data, len);
        return hasher.finalize();
    }

    std::array<std::uint32_t, 8> state_{}; ///< Текущее состояние хэша (хэш-регистры A-H)
    std::uint8_t block_[64]{};             ///< Внутренний буфер для обработки 64-байтных блоков
    std::size_t data_len_ = 0;             ///< Количество байт, находящихся в буфере block_ прямо сейчас
    std::uint64_t bit_len_ = 0;            ///< Общая длина обработанного сообщения в битах (без учета текущего буфера)
};

/**
 * @brief Конвертирует сырой байтовый хэш в шестнадцатеричную строку (HEX).
 * @param digest Массив из 32 байт, полученный после finalize().
 * @return Строка из 64 символов в нижнем регистре.
 */
inline std::string to_hex(const std::array<std::uint8_t, 32> &digest)
{
    static constexpr char kHexDigits[] = "0123456789abcdef";
    std::string out(64, '0');
    for (int i = 0; i < 32; ++i)
    {
        out[2 * i] = kHexDigits[digest[i] >> 4];
        out[2 * i + 1] = kHexDigits[digest[i] & 0x0fu];
    }
    return out;
}

/**
 * @brief Вычисляет итеративный salted-хэш SHA-256 для пароля.
 *
 * Склеивает соль и пароль, после чего применяет SHA-256 заданное количество раз
 * в соответствии с требованиями к конфигурации датасета.
 *
 * @param salt Соль в виде строки.
 * @param password Исходный пароль для проверки.
 * @param iterations Количество циклов хэширования (минимум 1).
 * @return Итоговый хэш в виде HEX-строки из 64 символов.
 */
inline std::string hash_password(const std::string &salt, const std::string &password, int iterations)
{
    const std::string salted = salt + password;
    auto digest = Sha256::hash(reinterpret_cast<const std::uint8_t *>(salted.data()), salted.size());
    for (int i = 1; i < iterations; ++i)
    {
        digest = Sha256::hash(digest.data(), digest.size());
    }
    return to_hex(digest);
}
