#!/usr/bin/env python3
"""Прогоняет бекенд, верифицирует результат и дописывает его в results.jsonl."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_results import load_jsonl, verify  # noqa: E402


def clamp_cores(requested: int, available: int) -> int:
    """Ограничивает запрошенное число ядер доступным."""
    if requested > available:
        print(
            f"ВНИМАНИЕ: запрошено {requested} ядер, доступно {available} — "
            f"привязка обрезана до {available} (в results.jsonl останется "
            f"запрошенное значение cores={requested})",
            file=sys.stderr,
        )
        return available

    return requested


def available_cores() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        # fallback для систем без sched_getaffinity
        return os.cpu_count() or 1


def run_once(
    binary: Path,
    config_path: Path,
    threads: int | None,
    cores: int | None,
    taskset: str | None,
) -> dict:
    """Запускает бинарник и читает его JSON-результат."""
    fd, tmp_name = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    tmp = Path(tmp_name)

    cmd: list[str] = []

    if cores is not None and taskset:
        eff = clamp_cores(cores, available_cores())
        cmd += [taskset, "-c", f"0-{eff - 1}"]

    cmd += [str(binary), "--config", str(config_path), "--output", str(tmp)]

    if threads is not None:
        cmd += ["--threads", str(threads)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            raise RuntimeError(
                f"бинарник завершился с кодом {proc.returncode}: {proc.stderr.strip()}"
            )

        if proc.stdout.strip():
            print(proc.stdout.strip())

        try:
            return json.loads(tmp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"бинарник записал невалидный JSON: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)


def append_result(results_file: Path, data: dict, cores: int | None) -> None:
    data.setdefault("cores", cores if cores is not None else 1)

    with results_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Прогон бекенда по сетке размер x потоки x ядра с верификацией"
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--results-file", type=Path, required=True)
    parser.add_argument("--sizes", nargs="+", type=int, required=True)
    parser.add_argument(
        "--threads",
        nargs="*",
        type=int,
        default=None,
        help="Список чисел потоков. Запускается последовательное выполнение без --threads.",
    )
    parser.add_argument(
        "--cores",
        nargs="*",
        type=int,
        default=None,
        help="Список чисел ядер. Запускаеттся без привязки к ядрам.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.binary.exists():
        raise SystemExit(f"Бинарник не найден: {args.binary}")

    args.results_file.parent.mkdir(parents=True, exist_ok=True)
    args.results_file.touch(exist_ok=True)

    taskset = shutil.which("taskset")
    threads_grid: list[int | None] = args.threads if args.threads else [None]
    cores_grid: list[int | None] = args.cores if args.cores else [None]

    total = ok = 0

    for size in args.sizes:
        size_dir = args.data_dir / f"size_{size}"
        config_path = size_dir / "config.json"
        expected_path = size_dir / "expected.jsonl"

        if not config_path.exists():
            print(
                f"ПРОПУСК size={size}: нет {config_path}",
                file=sys.stderr,
            )
            continue

        config = json.loads(config_path.read_text(encoding="utf-8"))
        expected = {item["id"]: item for item in load_jsonl(expected_path)}

        for cores in cores_grid:
            for threads in threads_grid:
                label = (
                    f"size={size}"
                    + (f" threads={threads}" if threads is not None else "")
                    + (f" cores={cores}" if cores is not None else "")
                )

                total += 1

                try:
                    data = run_once(args.binary, config_path, threads, cores, taskset)
                except RuntimeError as exc:
                    print(f"ОШИБКА [{label}]: {exc}", file=sys.stderr)
                    continue

                report = verify(config, expected, data)

                if not report.ok:
                    print(f"[{label}] VERIFICATION FAILED:", file=sys.stderr)
                    for error in report.errors:
                        print(f"  - {error}", file=sys.stderr)
                    continue

                append_result(args.results_file, data, cores)
                ok += 1
                print(f"[{label}] VERIFICATION OK")

    print(f"Готово: {ok}/{total} прогонов записаны в {args.results_file}")

    if total == 0:
        raise SystemExit(
            "Ни одного прогона не выполнено — проверьте --sizes и --data-dir"
        )

    if ok < total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
