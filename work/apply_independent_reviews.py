"""Validate and apply a complete independent ground-truth review submission."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .ground_truth_review import _sha256, apply_independent_reviews, metric_eligible_entries


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "outputs" / "ground-truth-review-ledger.json"
DEFAULT_SUBMISSION = ROOT / "outputs" / "independent-review-submission.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "ground-truth-independent-reviewed.json"
DEFAULT_REPORT = ROOT / "outputs" / "ground-truth-independent-review.md"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _verify_sources(ledger: dict) -> None:
    checked: set[tuple[str, str]] = set()
    for entry in ledger.get("entries", []):
        key = (entry["source_path"], entry["source_sha256"])
        if key in checked:
            continue
        source = ROOT / entry["source_path"]
        if not source.is_file() or _sha256(source) != entry["source_sha256"]:
            raise ValueError(f"source hash verification failed: {entry['source_path']}")
        checked.add(key)


def submit_reviews(decisions_path: Path, output_path: Path, report_path: Path) -> dict[str, int]:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if not isinstance(decisions, list):
        raise ValueError("independent review submission must be a JSON array")

    pending_ids = {
        entry["review_id"]
        for entry in ledger.get("entries", [])
        if entry.get("human_status") == "PENDING_INDEPENDENT_REVIEW"
    }
    submitted_ids = [str(decision.get("review_id", "")).strip() for decision in decisions]
    if len(submitted_ids) != len(pending_ids) or set(submitted_ids) != pending_ids:
        missing = sorted(pending_ids - set(submitted_ids))
        extra = sorted(set(submitted_ids) - pending_ids)
        raise ValueError(f"complete submission required; missing={missing}, extra={extra}")

    _verify_sources(ledger)
    reviewed = apply_independent_reviews(ledger, decisions)
    reviewed["independent_review_applied_at"] = datetime.now(timezone.utc).isoformat()

    statuses = [entry.get("human_status") for entry in reviewed.get("entries", [])]
    summary = {
        "reviewed": len(decisions),
        "eligible": len(metric_eligible_entries(reviewed)),
        "rejected": statuses.count("INDEPENDENTLY_REJECTED"),
        "needs_adjudication": statuses.count("NEEDS_ADJUDICATION"),
    }
    report = "\n".join(
        [
            "# Ground Truth 独立复核结果",
            "",
            f"- 已复核：{summary['reviewed']}",
            f"- 正式可计量样本：{summary['eligible']}",
            f"- 独立驳回：{summary['rejected']}",
            f"- 待裁决冲突：{summary['needs_adjudication']}",
            "",
            "本结果只确认候选类别、严重性、页码和 quote；不证明企业满足要求，也不直接证明召回率或漏报率达标。",
            "",
        ]
    )
    _atomic_write(output_path, json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n")
    _atomic_write(report_path, report)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", nargs="?", type=Path, default=DEFAULT_SUBMISSION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    print(json.dumps(submit_reviews(args.submission, args.output, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
