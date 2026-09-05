#!/usr/bin/env python3
"""Генерация синтетического датасета паролей и хэшей для образовательных целей."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Все параметры, необходимые для воспроизведения датасета."""

    out: Path = Path("data/size_200")
    range_begin: int = 0
    range_end: int = 20_000_000
    password_length: int = 8
    charset: str = "abcdefghijklmnopqrstuvwxyz0123456789"
    iterations: int = 1
    salt: str = "edu-salt-2026"
    targets: int = 16
    size_code: int | None = None
    seed: int = 42

    @property
    def password_space(self) -> int:
        """Общее пространство возможных паролей."""
        return len(self.charset) ** self.password_length

    def validate(self) -> None:
        """Проверка корректности параметров конфигурации."""
        if self.range_end <= self.range_begin:
            raise ValueError("range-end должен быть больше, чем range-begin")
        if not 0 < self.targets <= self.range_end - self.range_begin:
            raise ValueError("недопустимое количество искомых хэшей (targets)")
        if self.range_end > self.password_space:
            raise ValueError("range-end превышает общее пространство паролей")

    def as_json_dict(self) -> dict:
        """Поля конфигурации для сохранения, исключая значения None и путь вывода."""
        data = {k: v for k, v in asdict(self).items() if k != "out" and v is not None}
        return {
            "version": 1,
            "hash_type": "sha256",
            **data,
            "targets_file": "targets.jsonl",
        }


def index_to_password(index: int, length: int, charset: str) -> str:
    """Преобразование числового индекса в пароль через N-ичное кодирование по алфавиту."""
    base = len(charset)
    if not 0 <= index < base**length:
        raise ValueError(
            "индекс выходит за пределы допустимого диапазона для данной длины/алфавита"
        )

    chars: list[str] = []
    for _ in range(length):
        index, remainder = divmod(index, base)
        chars.append(charset[remainder])
    return "".join(reversed(chars))


def hash_password(password: str, salt: str, iterations: int) -> str:
    """Хэширование пароля с солью и итерациями с использованием SHA-256."""
    digest = hashlib.sha256((salt + password).encode("utf-8")).digest()
    for _ in range(iterations - 1):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()


@dataclass(frozen=True)
class Target:
    """Искомая цель: структура для хранения сгенерированного пароля и его хэша."""

    id: int
    index: int
    password: str
    password_hash: str


def build_targets(config: Config) -> list[Target]:
    """Выбор случайных индексов в диапазоне и их преобразование в записи паролей/хэшей."""
    rng = random.Random(config.seed)
    indices = sorted(
        rng.sample(range(config.range_begin, config.range_end), config.targets)
    )
    targets = []
    for target_id, index in enumerate(indices, start=1):
        password = index_to_password(index, config.password_length, config.charset)
        password_hash = hash_password(password, config.salt, config.iterations)
        targets.append(Target(target_id, index, password, password_hash))
    return targets


def write_dataset(config: Config, targets: list[Target]) -> None:
    """Запись файлов targets.jsonl, expected.jsonl и config.json в директорию config.out."""
    config.out.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        targets_file = stack.enter_context(
            (config.out / "targets.jsonl").open("w", encoding="utf-8")
        )
        expected_file = stack.enter_context(
            (config.out / "expected.jsonl").open("w", encoding="utf-8")
        )
        for t in targets:
            targets_file.write(json.dumps({"id": t.id, "hash": t.password_hash}) + "\n")
            expected_file.write(
                json.dumps(
                    {
                        "id": t.id,
                        "index": t.index,
                        "password": t.password,
                        "hash": t.password_hash,
                    }
                )
                + "\n"
            )

    config_path = config.out / "config.json"
    config_path.write_text(
        json.dumps(config.as_json_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def parse_args() -> Config:
    """Парсинг аргументов командной строки."""
    defaults = Config()
    parser = argparse.ArgumentParser(description="Генерация синтетического датасета")
    parser.add_argument("--out", type=Path, default=defaults.out)
    parser.add_argument("--range-begin", type=int, default=defaults.range_begin)
    parser.add_argument("--range-end", type=int, default=defaults.range_end)
    parser.add_argument("--password-length", type=int, default=defaults.password_length)
    parser.add_argument("--charset", type=str, default=defaults.charset)
    parser.add_argument("--iterations", type=int, default=defaults.iterations)
    parser.add_argument("--salt", type=str, default=defaults.salt)
    parser.add_argument("--targets", type=int, default=defaults.targets)
    parser.add_argument("--size-code", type=int, default=defaults.size_code)
    parser.add_argument("--seed", type=int, default=defaults.seed)
    args = parser.parse_args()

    return Config(
        out=args.out,
        range_begin=args.range_begin,
        range_end=args.range_end,
        password_length=args.password_length,
        charset=args.charset,
        iterations=args.iterations,
        salt=args.salt,
        targets=args.targets,
        size_code=args.size_code,
        seed=args.seed,
    )


def main() -> None:
    config = parse_args()
    try:
        config.validate()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    targets = build_targets(config)
    write_dataset(config, targets)

    candidate_count = config.range_end - config.range_begin
    print(
        f"Сгенерировано: {config.out} "
        f"(кандидатов={candidate_count}, искомых хэшей={config.targets})"
    )


if __name__ == "__main__":
    main()
