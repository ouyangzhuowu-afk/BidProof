"""Validation contract for real-task pilot evidence; empty is a valid initial state.

Writes require real enterprise material provenance + human feedback fields.
Demo / synthetic / public-tender-only / confirmation-string-only rows are rejected.
Formal ledger in outputs/ must stay empty until Joe supplies real enterprise input.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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
    # Hard-check provenance + human feedback (Item 7)
    "enterprise_source",
    "enterprise_material_sha256",
    "enterprise_task_ref",
    "human_feedback_text",
    "human_feedback_author",
    "human_feedback_at",
]

ALLOWED_ENTERPRISE_SOURCES = frozenset(
    {
        "enterprise_response",
        "enterprise_upload",
        "enterprise_email",
        "enterprise_portal",
    }
)

_FORBIDDEN_TOKEN = re.compile(
    r"(?i)\b(demo|synthetic|fixture|sample|test[-_]?task|public[-_]?tender[-_]?only|mock)\b"
)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def validate_ledger(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    rows = list(rows)
    confirmed = sum(row.get("human_confirmation", "").strip().lower() == "confirmed" for row in rows)
    payment_signals = sum(bool(row.get("payment_signal", "").strip()) for row in rows)
    return {"rows": len(rows), "confirmed_tasks": confirmed, "payment_signals": payment_signals}


def _field(row: dict[str, str], name: str) -> str:
    return str(row.get(name, "") or "").strip()


def _reject_forbidden_tokens(row: dict[str, str]) -> None:
    for name in (
        "task_id",
        "enterprise_name",
        "evidence_boundary",
        "enterprise_source",
        "enterprise_task_ref",
        "tender_filename",
        "human_feedback_text",
    ):
        value = _field(row, name)
        if value and _FORBIDDEN_TOKEN.search(value):
            raise ValueError(
                f"{name} rejects demo/synthetic/public-tender-only tokens (got {value!r})"
            )


def validate_row_for_append(row: dict[str, str]) -> None:
    """Hard checks before any write. Does not mutate formal ledger by itself."""
    if not _field(row, "task_id"):
        raise ValueError("task_id is required for a pilot record")
    require_iso_datetime(_field(row, "received_at"), "received_at")

    source = _field(row, "enterprise_source").lower()
    if not source:
        raise ValueError("enterprise_source is required (real enterprise material provenance)")
    if source in {"public_tender_only", "public-tender-only", "public"}:
        raise ValueError("enterprise_source rejects public-tender-only material")
    if source not in ALLOWED_ENTERPRISE_SOURCES:
        raise ValueError(
            "enterprise_source must be one of: " + ", ".join(sorted(ALLOWED_ENTERPRISE_SOURCES))
        )

    material_hash = _field(row, "enterprise_material_sha256")
    if not material_hash or not _SHA256_RE.match(material_hash):
        raise ValueError("enterprise_material_sha256 must be a 64-char hex digest of real material")

    task_ref = _field(row, "enterprise_task_ref")
    if not task_ref:
        raise ValueError("enterprise_task_ref is required (links the real enterprise task)")

    feedback = _field(row, "human_feedback_text")
    author = _field(row, "human_feedback_author")
    feedback_at = _field(row, "human_feedback_at")
    confirmation = _field(row, "human_confirmation").lower()

    # confirmed-string-only is forbidden: confirmation alone never validates a row.
    if confirmation == "confirmed":
        if not feedback or len(feedback) < 8:
            raise ValueError(
                "human_feedback_text is required when human_confirmation=confirmed "
                "(confirmed-string-only is rejected)"
            )
        if not author:
            raise ValueError("human_feedback_author is required when human_confirmation=confirmed")
        require_iso_datetime(feedback_at, "human_feedback_at")
    elif feedback or author or feedback_at:
        # If feedback fields are present (even for pending), require a coherent set.
        if not feedback or len(feedback) < 8:
            raise ValueError("human_feedback_text must be substantive when feedback fields are set")
        if not author:
            raise ValueError("human_feedback_author is required when feedback fields are set")
        require_iso_datetime(feedback_at, "human_feedback_at")

    if not _field(row, "enterprise_name"):
        raise ValueError("enterprise_name is required for a real enterprise pilot row")
    if not _field(row, "tender_filename"):
        raise ValueError("tender_filename is required for a real enterprise pilot row")
    if not _field(row, "evidence_boundary"):
        raise ValueError("evidence_boundary is required")

    _reject_forbidden_tokens(row)


def append_row(path: Path, row: dict[str, str]) -> dict[str, int]:
    """Append one real pilot row and return the current business summary."""
    validate_row_for_append(row)
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
                "此台账只接受真实企业输入、真实人工确认、失败原因和付款意愿记录。"
                "必须填写 enterprise_source / enterprise_material_sha256 / enterprise_task_ref，"
                "以及 human_feedback_text / human_feedback_author / human_feedback_at。"
                "历史演示任务、自动化测试、公开招标-only、合成样本和仅写 confirmed 字符串不计入业务任务数。",
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
        try:
            print(json.dumps(append_row(args.ledger, row), ensure_ascii=False))
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        render_review(args.ledger, args.report)
        return
    print(json.dumps(summarize_file(args.ledger), ensure_ascii=False))


if __name__ == "__main__":
    main()
