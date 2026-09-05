#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


def load_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


@dataclass
class VerificationReport:
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors

    def print(self) -> None:
        if self.ok:
            print("VERIFICATION OK")
            return
        print("VERIFICATION FAILED")
        for error in self.errors:
            print(f"- {error}")


def check_candidate_count(config: dict, result: dict) -> list[str]:
    expected = config["range_end"] - config["range_begin"]
    actual = result.get("candidates_checked")
    if actual != expected:
        return [f"candidates_checked mismatch: expected {expected}, got {actual}"]
    return []


def check_matches(expected: dict[int, dict], result: dict) -> list[str]:
    matches = result.get("matches", [])
    found = {m["id"]: m for m in matches}
    errors = []

    if len(found) != len(matches):
        errors.append("duplicate ids in result matches")
    if len(found) != len(expected):
        errors.append(
            f"matches count mismatch: expected {len(expected)}, got {len(found)}"
        )

    for target_id, target in expected.items():
        match = found.get(target_id)
        if match is None:
            errors.append(f"id {target_id} not found")
            continue
        if match.get("password") != target["password"]:
            errors.append(f"id {target_id}: password mismatch")
        if match.get("hash") != target["hash"]:
            errors.append(f"id {target_id}: hash mismatch")

    unexpected_ids = found.keys() - expected.keys()
    errors.extend(f"unexpected id {fid}" for fid in sorted(unexpected_ids))
    return errors


def verify(config: dict, expected: dict[int, dict], result: dict) -> VerificationReport:
    errors = check_candidate_count(config, result) + check_matches(expected, result)
    return VerificationReport(errors)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify audit results")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    expected = {item["id"]: item for item in load_jsonl(args.expected)}
    result = json.loads(args.result.read_text(encoding="utf-8"))

    report = verify(config, expected, result)
    report.print()
    if not report.ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
