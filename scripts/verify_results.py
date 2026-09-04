#!/usr/bin/env python3
"""Verify a computed audit result against the expected (ground-truth) dataset."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Args:
    config: Path
    expected: Path
    result: Path


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="Verify audit results")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    ns = parser.parse_args()
    return Args(config=ns.config, expected=ns.expected, result=ns.result)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def check_candidate_count(config: dict, result: dict) -> list[str]:
    expected_count = config["range_end"] - config["range_begin"]
    actual_count = result.get("candidates_checked")
    if actual_count != expected_count:
        return [
            f"candidates_checked mismatch: expected {expected_count}, got {actual_count}"
        ]
    return []


def check_matches(expected: dict[int, dict], result: dict) -> list[str]:
    """Compare found matches against the expected id -> {password, hash} records."""
    matches = result.get("matches", [])
    found = {m["id"]: m for m in matches}
    errors = []

    if len(found) != len(matches):
        errors.append("duplicate ids in result matches")
    if len(found) != len(expected):
        errors.append(
            f"matches count mismatch: expected {len(expected)}, got {len(found)}"
        )

    for target_id, exp in expected.items():
        match = found.get(target_id)
        if match is None:
            errors.append(f"id {target_id} not found")
            continue
        if match.get("password") != exp["password"]:
            errors.append(f"id {target_id}: password mismatch")
        if match.get("hash") != exp["hash"]:
            errors.append(f"id {target_id}: hash mismatch")

    unexpected_ids = found.keys() - expected.keys()
    errors.extend(f"unexpected id {fid}" for fid in sorted(unexpected_ids))
    return errors


def main() -> None:
    args = parse_args()
    config = load_json(args.config)
    expected = {item["id"]: item for item in load_jsonl(args.expected)}
    result = load_json(args.result)

    errors = check_candidate_count(config, result) + check_matches(expected, result)

    if errors:
        print("VERIFICATION FAILED")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("VERIFICATION OK")


if __name__ == "__main__":
    main()
