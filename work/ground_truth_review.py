"""Build a reviewable ledger from the real-upload candidate manifest.

This script performs only local checks. It never changes candidate labels to
PASS and never treats a keyword hit as human ground truth.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "fixtures" / "real-upload" / "ground-truth-candidates.json"
OUTPUT = ROOT / "outputs" / "ground-truth-review-ledger.json"
REPORT = ROOT / "outputs" / "ground-truth-review.md"

FIRST_PASS_REJECTIONS = {
    ("REAL-001", "DEADLINE"): "评分业绩时间范围，不是投标/递交关键截止时间，类别误报。",
    ("REAL-003", "SCORING"): "仅说明通用评标方法，未包含具体评分因素或分值，类别误报。",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_ledger() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries: list[dict] = []
    for fixture in manifest:
        source = ROOT / fixture["source_path"]
        source_exists = source.is_file()
        hash_matches = source_exists and _sha256(source) == fixture["sha256"]
        for index, candidate in enumerate(fixture.get("candidates", []), start=1):
            rejection_reason = FIRST_PASS_REJECTIONS.get((fixture["fixture_id"], candidate["category"]))
            entries.append(
                {
                    "review_id": f"{fixture['fixture_id']}-{index:02d}",
                    "fixture_id": fixture["fixture_id"],
                    "source_path": fixture["source_path"],
                    "source_sha256": fixture["sha256"],
                    "source_exists": source_exists,
                    "source_hash_matches": hash_matches,
                    "category": candidate["category"],
                    "severity": candidate["severity"],
                    "page": candidate["page"],
                    "quote": candidate["quote"],
                    "polarity": candidate["polarity"],
                    "machine_status": "LOCALLY_TRACEABLE" if source_exists and hash_matches else "BLOCKED",
                    "first_pass_status": "REJECTED" if rejection_reason else "CONFIRMED",
                    "human_status": "PENDING_INDEPENDENT_REVIEW",
                    "reviewer": "codex_first_pass",
                    "review_note": rejection_reason or "原文包含具体要求且类别与页码一致；等待独立复核。",
                    "reviewed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "真实上传招标 PDF 的候选要求人工复核台账",
        "decision_rule": "机器可验证来源血缘，不可替代人工确认；未确认项不得参与 PASS 统计。",
        "entries": entries,
    }


def metric_eligible_entries(ledger: dict) -> list[dict]:
    """Return only independently confirmed, traceable, non-rejected labels."""
    return [
        entry
        for entry in ledger.get("entries", [])
        if entry.get("machine_status") == "LOCALLY_TRACEABLE"
        and entry.get("source_hash_matches") is True
        and entry.get("first_pass_status") == "CONFIRMED"
        and entry.get("human_status") == "INDEPENDENTLY_CONFIRMED"
    ]


def apply_independent_reviews(ledger: dict, decisions: list[dict]) -> dict:
    """Apply independently authored decisions without mutating the input ledger."""
    updated = copy.deepcopy(ledger)
    entries = {entry.get("review_id"): entry for entry in updated.get("entries", [])}
    seen: set[str] = set()
    for decision in decisions:
        review_id = str(decision.get("review_id", "")).strip()
        reviewer = str(decision.get("reviewer", "")).strip()
        verdict = str(decision.get("decision", "")).strip().upper()
        note = str(decision.get("note", "")).strip()
        if review_id not in entries:
            raise ValueError(f"unknown review_id: {review_id}")
        if review_id in seen:
            raise ValueError(f"duplicate review_id: {review_id}")
        if not reviewer or reviewer == entries[review_id].get("reviewer"):
            raise ValueError("independent reviewer must be different from first-pass reviewer")
        if verdict not in {"CONFIRM", "REJECT"}:
            raise ValueError(f"invalid independent review decision: {verdict}")
        if not note:
            raise ValueError("independent review note is required")
        seen.add(review_id)

    for decision in decisions:
        entry = entries[decision["review_id"]]
        verdict = decision["decision"].upper()
        agrees = (entry["first_pass_status"] == "CONFIRMED" and verdict == "CONFIRM") or (
            entry["first_pass_status"] == "REJECTED" and verdict == "REJECT"
        )
        if agrees:
            entry["human_status"] = "INDEPENDENTLY_CONFIRMED" if verdict == "CONFIRM" else "INDEPENDENTLY_REJECTED"
        else:
            entry["human_status"] = "NEEDS_ADJUDICATION"
        entry["independent_reviewer"] = decision["reviewer"].strip()
        entry["independent_review_note"] = decision["note"].strip()
        entry["independent_reviewed_at"] = datetime.now(timezone.utc).isoformat()
    return updated


def main() -> None:
    ledger = build_ledger()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    counts: dict[str, int] = {}
    for entry in ledger["entries"]:
        counts[entry["machine_status"]] = counts.get(entry["machine_status"], 0) + 1
    first_pass: dict[str, int] = {}
    for entry in ledger["entries"]:
        first_pass[entry["first_pass_status"]] = first_pass.get(entry["first_pass_status"], 0) + 1
    report_lines = [
        "# 真实上传样本 Ground Truth 第一轮审核",
        "",
        f"- 总候选：{len(ledger['entries'])}",
        f"- 第一轮确认：{first_pass.get('CONFIRMED', 0)}",
        f"- 第一轮驳回：{first_pass.get('REJECTED', 0)}",
        f"- 正式可计量样本：{len(metric_eligible_entries(ledger))}",
        "- 最终状态：全部仍为 `PENDING_INDEPENDENT_REVIEW`，未计入正式召回率。",
        "",
        "## 驳回项",
        "",
    ]
    for entry in ledger["entries"]:
        if entry["first_pass_status"] == "REJECTED":
            report_lines.append(
                f"- `{entry['review_id']}` {entry['category']} 第 {entry['page']} 页：{entry['review_note']}"
            )
    report_lines += [
        "",
        "## 门禁",
        "",
        "第一轮确认只能证明候选经过逐条原文审查，不构成独立双人 ground truth。独立复核前不得宣称达到 97% 召回率或 2% 漏报率门槛。",
    ]
    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(json.dumps({"entries": len(ledger["entries"]), "machine_status": counts, "first_pass": first_pass, "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
