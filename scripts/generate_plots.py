#!/usr/bin/env python3
"""Собирает результаты в CSV-файл и строит графики."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, fields
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import matplotlib.ticker as mticker
import numpy as np

_BG_FIGURE = "#0d1117"
_BG_AXES = "#161b22"
_GRID = "#30363d"
_TEXT = "#c9d1d9"
_TITLE = "#e6edf3"

_PALETTE = [
    "#3d7ef2",
    "#e0592b",
    "#3fb950",
    "#bc8cff",
    "#f85149",
    "#d29922",
    "#00d2c4",
    "#f778ba",
]

_HEATMAP_CMAP = "viridis"

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
        "legend.facecolor": _BG_AXES,
        "legend.edgecolor": _GRID,
        "legend.labelcolor": _TEXT,
    }
)

Series = tuple[str, list[float], list[float]]


@dataclass(frozen=True)
class RunResult:
    size_code: int
    candidates: int
    iterations: int
    time_seconds: float
    throughput_per_second: float
    threads: int
    cores: int

    @classmethod
    def from_dict(cls, data: dict) -> "RunResult":
        return cls(
            size_code=data["size_code"],
            candidates=data["candidates_checked"],
            iterations=data["iterations"],
            time_seconds=data["time_seconds"],
            throughput_per_second=data["throughput_per_second"],
            threads=data.get("threads", 1),
            cores=data.get("cores", 1),
        )


def load_results(results_file: Path) -> list[RunResult]:
    if not results_file.exists():
        raise SystemExit(f"Файл не найден: {results_file}")

    results = []
    with results_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(RunResult.from_dict(json.loads(line)))

    if not results:
        raise SystemExit(f"Файл {results_file} пуст")

    return sorted(results, key=lambda r: (r.size_code, r.cores, r.threads))


def write_csv(results: list[RunResult], path: Path) -> None:
    fieldnames = [f.name for f in fields(RunResult)]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(vars(r) for r in results)

    print(f"Сохранено: {path}")


def _format_millions(value: float, _pos: int | None = None) -> str:
    return f"{value:g}"


@dataclass(frozen=True)
class PlotSpec:
    filename: str
    title: str
    xlabel: str
    ylabel: str
    series: list[Series]
    x_log: bool = True
    y_log: bool = False


def render_plots(specs: list[PlotSpec], figures_dir: Path) -> None:
    for spec in specs:
        fig, ax = plt.subplots(figsize=(8, 5))
        all_x: list[float] = []

        for i, (label, x, y) in enumerate(spec.series):
            color = _PALETTE[i % len(_PALETTE)]
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
                label=label or None,
            )
            all_x.extend(x)

        if spec.x_log:
            ax.set_xscale("log")
            ax.set_xticks(sorted(set(all_x)))
            ax.xaxis.set_major_formatter(mticker.FuncFormatter(_format_millions))
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

        if spec.y_log:
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(_format_millions))
            ax.grid(True, which="major", axis="y")
            ax.grid(True, which="minor", axis="y", alpha=0.3)
        else:
            ax.grid(True, which="major", axis="y")

        ax.set_xlabel(spec.xlabel)
        ax.set_ylabel(spec.ylabel)
        ax.set_title(spec.title)
        ax.grid(True, which="major", axis="x")

        if len(spec.series) > 1:
            ax.legend()

        fig.tight_layout()
        path = figures_dir / spec.filename
        fig.savefig(path, dpi=300)
        plt.close(fig)
        print(f"Сохранено: {path}")


@dataclass(frozen=True)
class HeatmapSpec:
    filename: str
    title: str
    cores_axis: list[int]
    threads_axis: list[int]
    matrix: list[list[float | None]]
    value_fmt: str = "{:.2f}"
    colorbar_label: str = ""


def render_heatmap(spec: HeatmapSpec, figures_dir: Path) -> None:
    data = np.array(
        [[np.nan if v is None else v for v in row] for row in spec.matrix],
        dtype=float,
    )

    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    im = ax.imshow(data, cmap=_HEATMAP_CMAP, aspect="auto", origin="lower")

    ax.set_xticks(range(len(spec.threads_axis)))
    ax.set_xticklabels(spec.threads_axis)
    ax.set_yticks(range(len(spec.cores_axis)))
    ax.set_yticklabels(spec.cores_axis)
    ax.set_xlabel("Число потоков")
    ax.set_ylabel("Число ядер")
    ax.set_title(spec.title)

    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if np.isnan(data[i, j]):
                continue

            text = ax.text(
                j,
                i,
                spec.value_fmt.format(data[i, j]),
                ha="center",
                va="center",
                color="white",
                fontsize=10,
                fontweight="bold",
            )
            text.set_path_effects(
                [path_effects.withStroke(linewidth=2, foreground=_BG_AXES)]
            )

    cbar = fig.colorbar(im, ax=ax)
    cbar.ax.yaxis.set_tick_params(color=_TEXT)
    cbar.outline.set_edgecolor(_GRID)
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color=_TEXT)

    if spec.colorbar_label:
        cbar.set_label(spec.colorbar_label, color=_TEXT)

    fig.tight_layout()
    path = figures_dir / spec.filename
    fig.savefig(path, dpi=300)
    plt.close(fig)
    print(f"Сохранено: {path}")


def _group_by_size(
    results: list[RunResult],
) -> dict[int, dict[tuple[int, int], RunResult]]:
    by_size: dict[int, dict[tuple[int, int], RunResult]] = defaultdict(dict)
    for r in results:
        by_size[r.size_code][(r.cores, r.threads)] = r
    return by_size


def _speedup_matrix(
    grid: dict[tuple[int, int], RunResult],
    cores_axis: list[int],
    threads_axis: list[int],
) -> list[list[float | None]]:
    """S = T(1,1) / T(cores, threads), точки с неположительным временем пропускаются."""
    baseline = grid.get((1, 1))
    if baseline is None or baseline.time_seconds <= 0:
        return [[None] * len(threads_axis) for _ in cores_axis]

    matrix = []
    for c in cores_axis:
        row = []
        for t in threads_axis:
            r = grid.get((c, t))
            if r is None:
                row.append(None)
            elif r.time_seconds <= 0:
                print(
                    f"ВНИМАНИЕ: time_seconds<=0 для cores={c} threads={t} — точка пропущена",
                    file=sys.stderr,
                )
                row.append(None)
            else:
                row.append(baseline.time_seconds / r.time_seconds)
        matrix.append(row)

    return matrix


def plot_single_threaded(results: list[RunResult], figures_dir: Path) -> None:
    candidates_millions = [r.candidates / 1e6 for r in results]
    time_series = [("", candidates_millions, [r.time_seconds for r in results])]
    throughput_series = [
        ("", candidates_millions, [r.throughput_per_second / 1e6 for r in results])
    ]

    render_plots(
        [
            PlotSpec(
                "time_by_size.png",
                "Время последовательного выполнения vs Размер задачи",
                "Количество кандидатов, млн",
                "Время, сек",
                time_series,
            ),
            PlotSpec(
                "time_by_size_log.png",
                "Время последовательного выполнения vs Размер задачи",
                "Количество кандидатов, млн",
                "Время, сек (лог. шкала)",
                time_series,
                y_log=True,
            ),
            PlotSpec(
                "throughput_by_size.png",
                "Последовательная производительность vs Размер задачи",
                "Количество кандидатов, млн",
                "Производительность, млн канд/сек",
                throughput_series,
            ),
        ],
        figures_dir,
    )


def plot_grid(results: list[RunResult], figures_dir: Path) -> None:
    by_size = _group_by_size(results)
    cores_axis = sorted({r.cores for r in results})
    threads_axis = sorted({r.threads for r in results})

    primary_size = max(by_size)
    grid = by_size[primary_size]
    print(f"Графики сетки ядра×потоки строятся по размеру {primary_size}")

    speedup_matrix = _speedup_matrix(grid, cores_axis, threads_axis)

    # Эффективность считаем от физически доступных исполнителей: min(cores, threads).
    efficiency_matrix = [
        [
            None if s is None else s / max(1, min(c, t))
            for s, t in zip(row, threads_axis)
        ]
        for c, row in zip(cores_axis, speedup_matrix)
    ]

    render_heatmap(
        HeatmapSpec(
            "heatmap_speedup.png",
            f"Ускорение (S) ядер к потокам на размере {primary_size}",
            cores_axis,
            threads_axis,
            speedup_matrix,
            value_fmt="{:.2f}",
            colorbar_label="Ускорение (S)",
        ),
        figures_dir,
    )

    render_heatmap(
        HeatmapSpec(
            "heatmap_efficiency.png",
            f"Эффективность (E) ядер к потокам на размере {primary_size}",
            cores_axis,
            threads_axis,
            efficiency_matrix,
            value_fmt="{:.2f}",
            colorbar_label="Эффективность (E)",
        ),
        figures_dir,
    )

    time_series = []
    for c, row in zip(
        cores_axis,
        [
            [
                grid[(c, t)].time_seconds if (c, t) in grid else None
                for t in threads_axis
            ]
            for c in cores_axis
        ],
    ):
        xs = [t for t, v in zip(threads_axis, row) if v is not None]
        ys = [v for v in row if v is not None]
        time_series.append((f"{c} ядер(а)", xs, ys))

    speedup_series = []
    for c, row in zip(cores_axis, speedup_matrix):
        xs = [t for t, v in zip(threads_axis, row) if v is not None]
        ys = [v for v in row if v is not None]
        speedup_series.append((f"{c} ядер(а)", xs, ys))

    render_plots(
        [
            PlotSpec(
                "time_by_threads.png",
                f"Время выполнения vs Число потоков, размер {primary_size}",
                "Число потоков",
                "Время, сек",
                time_series,
                x_log=False,
                y_log=False,
            ),
            PlotSpec(
                "speedup_by_threads.png",
                f"Ускорение (S) vs Число потоков, размер {primary_size}",
                "Число потоков",
                "Ускорение (S)",
                speedup_series,
                x_log=False,
            ),
        ],
        figures_dir,
    )

    matched = sorted(set(cores_axis) & set(threads_axis))
    size_codes = sorted(by_size)
    diag_series = []

    for n in matched:
        xs, ys = [], []
        for s in size_codes:
            r = by_size[s].get((n, n))
            if r is not None:
                xs.append(r.candidates / 1e6)
                ys.append(r.time_seconds)

        if xs:
            diag_series.append((f"{n} ядер = {n} поток(ов)", xs, ys))

    if diag_series:
        render_plots(
            [
                PlotSpec(
                    "time_by_size_scaling.png",
                    "Время выполнения vs Размер задачи",
                    "Количество кандидатов, млн",
                    "Время, сек (лог. шкала)",
                    diag_series,
                    y_log=True,
                ),
            ],
            figures_dir,
        )
    else:
        print("Пропускаю time_by_size_scaling.png: нет точек с cores == threads")


def plot_results(results: list[RunResult], figures_dir: Path) -> None:
    if len({(r.cores, r.threads) for r in results}) <= 1:
        plot_single_threaded(results, figures_dir)
    else:
        plot_grid(results, figures_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сбор результатов лабораторной работы и построение графиков"
    )
    parser.add_argument("--results-file", type=Path, required=True)
    parser.add_argument("--figures-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = load_results(args.results_file)
    write_csv(results, args.results_file.with_suffix(".csv"))

    args.figures_dir.mkdir(parents=True, exist_ok=True)
    plot_results(results, args.figures_dir)


if __name__ == "__main__":
    main()
