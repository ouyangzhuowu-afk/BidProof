import json
from pathlib import Path

import pytest

from work.apply_independent_reviews import submit_reviews


ROOT = Path(__file__).parents[1]


def _complete_decisions() -> list[dict]:
    ledger = json.loads((ROOT / "outputs" / "ground-truth-review-ledger.json").read_text(encoding="utf-8"))
    return [
        {
            "review_id": entry["review_id"],
            "reviewer": "independent_reviewer_20260825",
            "decision": "CONFIRM" if entry["first_pass_status"] == "CONFIRMED" else "REJECT",
            "note": "已重新核对原始文件 SHA-256、页码、类别和 quote。",
        }
        for entry in ledger["entries"]
    ]


def test_submit_reviews_rejects_partial_submission(tmp_path):
    decisions_path = tmp_path / "partial.json"
    decisions_path.write_text(json.dumps(_complete_decisions()[:1], ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="complete submission required"):
        submit_reviews(decisions_path, tmp_path / "reviewed.json", tmp_path / "report.md")

    assert not (tmp_path / "reviewed.json").exists()


def test_submit_reviews_writes_new_ledger_without_overwriting_source(tmp_path):
    source_path = ROOT / "outputs" / "ground-truth-review-ledger.json"
    source_before = source_path.read_bytes()
    decisions_path = tmp_path / "complete.json"
    decisions_path.write_text(json.dumps(_complete_decisions(), ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "reviewed.json"
    report_path = tmp_path / "report.md"

    summary = submit_reviews(decisions_path, output_path, report_path)
    reviewed = json.loads(output_path.read_text(encoding="utf-8"))

    assert summary == {"reviewed": 33, "eligible": 31, "rejected": 2, "needs_adjudication": 0}
    assert sum(entry["human_status"] == "INDEPENDENTLY_CONFIRMED" for entry in reviewed["entries"]) == 31
    assert sum(entry["human_status"] == "INDEPENDENTLY_REJECTED" for entry in reviewed["entries"]) == 2
    assert source_path.read_bytes() == source_before
    assert "正式可计量样本：31" in report_path.read_text(encoding="utf-8")
