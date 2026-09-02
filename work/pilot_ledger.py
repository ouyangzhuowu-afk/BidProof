"""Validation contract for real-task pilot evidence; empty is a valid initial state."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

from work.ledger_dates import require_iso_datetime


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
    require_iso_datetime(str(row.get("received_at", "")), "received_at")
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


def render_review(ledger_path: Path, report_path: Path, *, target_tasks: int = 10) -> None:
    summary = summarize_file(ledger_path)
    remaining = max(target_tasks - summary["rows"], 0)
    business_status = "NOT_STARTED" if summary["rows"] == 0 else "IN_PROGRESS"
    if summary["confirmed_tasks"] >= target_tasks and summary["payment_signals"] >= 2:
        business_status = "TARGET_MET"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# 真实任务验收台账",
                "",
                "## 当前状态",
                "",
                f"- 当前记录：{summary['rows']} / {target_tasks} 条真实任务",
                f"- 已有人工确认任务：{summary['confirmed_tasks']} 条",
                f"- 已记录付款意愿信号：{summary['payment_signals']} 条",
                f"- 业务验收结论：`{business_status}`",
                "",
                "## 使用边界",
                "",
                "此台账只接受真实企业输入、真实人工确认、失败原因和付款意愿记录。历史演示任务、自动化测试和工程验收不计入业务任务数，也不填充为付款意愿。",
                "",
                "## 下一步",
                "",
                f"距离 10 个真实任务目标还差 {remaining} 条记录。",
                "收到首个真实企业任务后，复制 `work/pilot-row.template.json` 并填写字段，运行：",
                "`uv run python -m work.pilot_ledger --row-json work/pilot-row.json`",
                "刷新本报告：`uv run python -m work.pilot_ledger --render-review`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Append and summarize real Project-025 pilot tasks")
    parser.add_argument("--ledger", type=Path, default=Path("outputs/pilot-ledger.csv"))
    parser.add_argument("--report", type=Path, default=Path("outputs/pilot-review.md"))
    parser.add_argument("--row-json", type=Path, help="JSON file containing one real task row")
    parser.add_argument("--render-review", action="store_true", help="Regenerate the markdown review from the CSV")
    args = parser.parse_args()
    if args.render_review:
        render_review(args.ledger, args.report)
        print(json.dumps(summarize_file(args.ledger), ensure_ascii=False))
        return
    if args.row_json:
        try:
            row = json.loads(args.row_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid JSON in {args.row_json}: {exc}") from exc
        if not isinstance(row, dict):
            raise SystemExit(f"row JSON must be an object, got {type(row).__name__}")
        print(json.dumps(append_row(args.ledger, row), ensure_ascii=False))
        render_review(args.ledger, args.report)
        return
    print(json.dumps(summarize_file(args.ledger), ensure_ascii=False))


if __name__ == "__main__":
    main()
