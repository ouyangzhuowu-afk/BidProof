"""Validation contract for real-task pilot evidence; empty is a valid initial state."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable


REQUIRED_FIELDS = [
    "task_id",
    "received_at",
    "tender_filename",
    "enterprise_name",
    "input_scope",
    "output_run_id",
    "requirement_count",
    "unresolved_count",
    "human_confirmation",
    "failure_reason",
    "elapsed_minutes",
    "payment_signal",
    "payment_note",
    "evidence_boundary",
]


def validate_ledger(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    rows = list(rows)
    confirmed = sum(row.get("human_confirmation", "").strip().lower() == "confirmed" for row in rows)
    payment_signals = sum(bool(row.get("payment_signal", "").strip()) for row in rows)
    return {"rows": len(rows), "confirmed_tasks": confirmed, "payment_signals": payment_signals}


def append_row(path: Path, row: dict[str, str]) -> dict[str, int]:
    """Append one real pilot row and return the current business summary."""
    if not row.get("task_id", "").strip():
        raise ValueError("task_id is required for a pilot record")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_rows: list[dict[str, str]] = []
    fieldnames = REQUIRED_FIELDS
    if path.exists() and path.stat().st_size:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != REQUIRED_FIELDS:
                raise ValueError("pilot ledger header does not match the contract")
            existing_rows = list(reader)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerow({field: str(row.get(field, "")) for field in fieldnames})
    return validate_ledger([*existing_rows, row])


def summarize_file(path: Path) -> dict[str, int]:
    if not path.exists() or not path.stat().st_size:
        return {"rows": 0, "confirmed_tasks": 0, "payment_signals": 0}
    with path.open(encoding="utf-8", newline="") as handle:
        return validate_ledger(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Append and summarize real Project-025 pilot tasks")
    parser.add_argument("--ledger", type=Path, default=Path("outputs/pilot-ledger.csv"))
    parser.add_argument("--row-json", type=Path, help="JSON file containing one real task row")
    args = parser.parse_args()
    if args.row_json:
        row = json.loads(args.row_json.read_text(encoding="utf-8"))
        print(json.dumps(append_row(args.ledger, row), ensure_ascii=False))
    else:
        print(json.dumps(summarize_file(args.ledger), ensure_ascii=False))


if __name__ == "__main__":
    main()
