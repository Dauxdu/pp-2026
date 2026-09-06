#!/usr/bin/env python3
"""Собирает файлы результатов result_*.json в один CSV-файл и строит графики времени/производительности."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, fields
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

_BG_FIGURE = "#0d1117"
_BG_AXES = "#161b22"
_GRID = "#30363d"
_TEXT = "#c9d1d9"
_TITLE = "#e6edf3"
_COLOR_BLUE = "#3d7ef2"
_COLOR_ORANGE = "#e0592b"

plt.rcParams.update(
    {
        "figure.facecolor": _BG_FIGURE,
        "axes.facecolor": _BG_AXES,
        "axes.edgecolor": _GRID,
        "axes.labelcolor": _TEXT,
        "axes.titlecolor": _TITLE,
        "axes.titleweight": "bold",
        "text.color": _TEXT,
        "xtick.color": _TEXT,
        "ytick.color": _TEXT,
        "grid.color": _GRID,
        "grid.alpha": 0.7,
        "grid.linewidth": 0.6,
        "font.size": 11,
        "axes.titlesize": 13,
        "savefig.facecolor": _BG_FIGURE,
    }
)


@dataclass(frozen=True)
class RunResult:
    """Одна строка CSV: единичное измерение для конкретного бэкенда и размера задачи."""

    size_code: int
    candidates: int
    iterations: int
    time_seconds: float
    throughput_per_second: float

    @classmethod
    def from_file(cls, path: Path) -> "RunResult":
        data = json.loads(path.read_text(encoding="utf-8"))
        size_code = data.get("size_code")
        if size_code is None:
            # Если в JSON нет size_code, извлекаем его из имени файла (например, size_4.json)
            size_code = int(path.stem.split("_")[1])
        return cls(
            size_code=size_code,
            candidates=data["candidates_checked"],
            iterations=data["iterations"],
            time_seconds=data["time_seconds"],
            throughput_per_second=data["throughput_per_second"],
        )


def load_results(results_dir: Path) -> list[RunResult]:
    # Ищем файлы, соответствующие шаблону size_*.json
    results = [
        RunResult.from_file(path) for path in sorted(results_dir.glob("size_*.json"))
    ]
    if not results:
        raise SystemExit(
            f"Файлы типа size_*.json не найдены в директории {results_dir}"
        )
    return sorted(results, key=lambda r: r.size_code)


def write_csv(results: list[RunResult], path: Path) -> None:
    fieldnames = [f.name for f in fields(RunResult)]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(vars(r) for r in results)
    print(f"Сохранено: {path}")


def _format_millions(value: float, _pos: int | None = None) -> str:
    """Компактная подпись деления оси"""
    return f"{value:g}"


def save_line_plot(
    x: list[float],
    y: list[float],
    *,
    xlabel: str,
    ylabel: str,
    title: str,
    color: str,
    path: Path,
    y_log: bool = False,
) -> None:
    """Общая функция для построения линейных графиков времени и производительности"""

    fig, ax = plt.subplots(figsize=(8, 5))

    ax.plot(
        x,
        y,
        marker="o",
        markersize=6,
        linewidth=2,
        color=color,
        markerfacecolor=color,
        markeredgecolor=_BG_AXES,
        markeredgewidth=1,
    )

    ax.set_xscale("log")
    ax.set_xticks(x)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_format_millions))
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

    if y_log:
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_format_millions))
        ax.grid(True, which="major", axis="y")
        ax.grid(True, which="minor", axis="y", alpha=0.3)
    else:
        ax.grid(True, which="major", axis="y")

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)
    print(f"Сохранено: {path}")


def plot_results(results: list[RunResult], figures_dir: Path) -> None:
    candidates_millions = [r.candidates / 1e6 for r in results]

    # График зависимости времени выполнения от размера задачи
    save_line_plot(
        candidates_millions,
        [r.time_seconds for r in results],
        xlabel="Количество кандидатов, млн",
        ylabel="Время, сек",
        title="Время последовательного выполнения vs Размер задачи",
        color=_COLOR_BLUE,
        path=figures_dir / "time_by_size.png",
    )

    save_line_plot(
        candidates_millions,
        [r.time_seconds for r in results],
        xlabel="Количество кандидатов, млн",
        ylabel="Время, сек (лог. шкала)",
        title="Время последовательного выполнения vs Размер задачи",
        color=_COLOR_BLUE,
        path=figures_dir / "time_by_size_log.png",
        y_log=True,
    )

    # График зависимости производительности от размера задачи
    save_line_plot(
        candidates_millions,
        [r.throughput_per_second / 1e6 for r in results],
        xlabel="Количество кандидатов, млн",
        ylabel="Производительность, млн канд/сек",
        title="Последовательная производительность vs Размер задачи",
        color=_COLOR_ORANGE,
        path=figures_dir / "throughput_by_size.png",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сбор результатов лабораторной работы и построение графиков"
    )
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--figures-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = load_results(args.results_dir)

    # Создаем директории, если они еще не существуют, и записываем данные
    args.results_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, args.results_dir / "results.csv")

    args.figures_dir.mkdir(parents=True, exist_ok=True)
    plot_results(results, args.figures_dir)


if __name__ == "__main__":
    main()
