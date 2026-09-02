"""45-day ICP outreach ledger — tracks contacts, not demo tasks."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path


REQUIRED_FIELDS = [
    "contact_id",
    "contacted_at",
    "company_name",
    "icp_segment",
    "channel",
    "contact_role",
    "response_status",
    "next_step",
    "next_step_due",
    "linked_pilot_task_id",
    "notes",
]


def validate_ledger(rows: list[dict[str, str]]) -> dict[str, int]:
    touched = sum(row.get("response_status", "").strip().lower() not in {"", "pending"} for row in rows)
    linked = sum(bool(row.get("linked_pilot_task_id", "").strip()) for row in rows)
    return {"rows": len(rows), "touched_contacts": touched, "linked_pilot_tasks": linked}


def append_row(path: Path, row: dict[str, str]) -> dict[str, int]:
    if not row.get("contact_id", "").strip():
        raise ValueError("contact_id is required for an ICP outreach record")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_rows: list[dict[str, str]] = []
    if path.exists() and path.stat().st_size:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != REQUIRED_FIELDS:
                raise ValueError("ICP ledger header does not match the contract")
            existing_rows = list(reader)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_FIELDS)
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerow({field: str(row.get(field, "")) for field in REQUIRED_FIELDS})
    return validate_ledger([*existing_rows, row])


def summarize_file(path: Path) -> dict[str, int]:
    if not path.exists() or not path.stat().st_size:
        return {"rows": 0, "touched_contacts": 0, "linked_pilot_tasks": 0}
    with path.open(encoding="utf-8", newline="") as handle:
        return validate_ledger(list(csv.DictReader(handle)))


def render_review(ledger_path: Path, report_path: Path, *, target_contacts: int = 30) -> None:
    summary = summarize_file(ledger_path)
    remaining = max(target_contacts - summary["rows"], 0)
    business_status = "NOT_STARTED" if summary["rows"] == 0 else "IN_PROGRESS"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# 45 天 ICP 触达台账",
                "",
                "## 当前状态",
                "",
                f"- 已记录触达：{summary['rows']} / {target_contacts}",
                f"- 已有反馈或跟进：{summary['touched_contacts']} 条",
                f"- 已关联真实 pilot 任务：{summary['linked_pilot_tasks']} 条",
                f"- 触达进度：`{business_status}`",
                "",
                "## 使用边界",
                "",
                "此台账只记录真实 ICP 触达与反馈，不将 demo、测试或内部演练计入 30 个 ICP 目标。",
                "产生真实 pilot 任务后，在 `linked_pilot_task_id` 填写对应 `task_id`，并与 `outputs/pilot-ledger.csv` 对齐。",
                "",
                "## 下一步",
                "",
                f"距离 45 天目标还差 {remaining} 个 ICP 触达记录。",
                "追加一行 UTF-8 JSON：`uv run python -m work.icp_ledger --row-json work/icp-row.json`。",
                "刷新本报告：`uv run python -m work.icp_ledger --render-review`。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Append and summarize 45-day ICP outreach records")
    parser.add_argument("--ledger", type=Path, default=Path("outputs/icp-outreach.csv"))
    parser.add_argument("--report", type=Path, default=Path("outputs/icp-outreach-review.md"))
    parser.add_argument("--row-json", type=Path, help="JSON file containing one ICP outreach row")
    parser.add_argument("--render-review", action="store_true", help="Regenerate the markdown review from the CSV")
    args = parser.parse_args()
    if args.render_review:
        render_review(args.ledger, args.report)
        print(json.dumps(summarize_file(args.ledger), ensure_ascii=False))
        return
    if args.row_json:
        row = json.loads(args.row_json.read_text(encoding="utf-8"))
        print(json.dumps(append_row(args.ledger, row), ensure_ascii=False))
        render_review(args.ledger, args.report)
        return
    print(json.dumps(summarize_file(args.ledger), ensure_ascii=False))


if __name__ == "__main__":
    main()
