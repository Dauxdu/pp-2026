#!/usr/bin/env python3
"""Collect lab result files (size_*.json) into a CSV and render summary plots."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULT_FIELDS = (
    "size_code",
    "candidates",
    "iterations",
    "time_seconds",
    "throughput_per_second",
)


@dataclass(frozen=True)
class Args:
    results_dir: Path = Path("results")
    figures_dir: Path = Path("figures")


@dataclass(frozen=True)
class Result:
    size_code: int
    candidates: int
    iterations: int
    time_seconds: float
    throughput_per_second: float


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="Collect lab results and build plots")
    parser.add_argument("--results-dir", type=Path, default=Args.results_dir)
    parser.add_argument("--figures-dir", type=Path, default=Args.figures_dir)
    ns = parser.parse_args()
    return Args(results_dir=ns.results_dir, figures_dir=ns.figures_dir)


def load_results(results_dir: Path) -> list[Result]:
    """Read every size_*.json file into a Result, sorted by size_code."""
    results = []
    for path in sorted(results_dir.glob("size_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        size_code = data.get("size_code")
        if size_code is None:
            size_code = int(path.stem.split("_")[1])
        results.append(
            Result(
                size_code=size_code,
                candidates=data["candidates_checked"],
                iterations=data["iterations"],
                time_seconds=data["time_seconds"],
                throughput_per_second=data["throughput_per_second"],
            )
        )
    if not results:
        raise SystemExit(f"no size_*.json files found in {results_dir}")
    return sorted(results, key=lambda r: r.size_code)


def write_csv(results: list[Result], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(
            {field: getattr(r, field) for field in RESULT_FIELDS} for r in results
        )
    print(f"Saved: {path}")


def plot_metric(
    results: list[Result],
    *,
    y_values: list[float],
    y_label: str,
    title: str,
    color: str | None,
    output_path: Path,
) -> None:
    """Render one candidates-vs-metric line plot and save it as PNG."""
    candidates_millions = [r.candidates / 1e6 for r in results]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(candidates_millions, y_values, marker="o", linewidth=2, color=color)
    ax.set_xlabel("Number of candidates, millions")
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)
    print(f"Saved: {output_path}")


def main() -> None:
    args = parse_args()
    results = load_results(args.results_dir)

    args.results_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, args.results_dir / "results.csv")

    args.figures_dir.mkdir(parents=True, exist_ok=True)
    plot_metric(
        results,
        y_values=[r.time_seconds for r in results],
        y_label="Time, seconds",
        title="Lab 1: sequential execution time vs task size",
        color=None,
        output_path=args.figures_dir / "lab1_time_by_size.png",
    )
    plot_metric(
        results,
        y_values=[r.throughput_per_second / 1e6 for r in results],
        y_label="Throughput, millions candidates/sec",
        title="Lab 1: sequential throughput vs task size",
        color="green",
        output_path=args.figures_dir / "lab1_throughput_by_size.png",
    )


if __name__ == "__main__":
    main()
