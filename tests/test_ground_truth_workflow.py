import json
from pathlib import Path

import pytest

from tests.conftest import requires_real_uploads
from work.ground_truth_review import apply_independent_reviews, build_ledger, metric_eligible_entries
from work.ocr_batch import run
from app.ocr import OCRResult


@requires_real_uploads
def test_ground_truth_ledger_keeps_machine_and_human_status_separate():
    ledger = build_ledger()

    assert ledger["entries"]
    assert all(entry["machine_status"] == "LOCALLY_TRACEABLE" for entry in ledger["entries"])
    assert sum(entry["first_pass_status"] == "CONFIRMED" for entry in ledger["entries"]) == 31
    assert sum(entry["first_pass_status"] == "REJECTED" for entry in ledger["entries"]) == 2
    assert all(entry["human_status"] == "PENDING_INDEPENDENT_REVIEW" for entry in ledger["entries"])


def test_rejected_candidates_are_excluded_from_metric_ground_truth():
    ledger = build_ledger()
    rejected = next(entry for entry in ledger["entries"] if entry["first_pass_status"] == "REJECTED")
    rejected["human_status"] = "INDEPENDENTLY_CONFIRMED"

    eligible = metric_eligible_entries(ledger)

    assert rejected["review_id"] not in {entry["review_id"] for entry in eligible}


@requires_real_uploads
def test_unreviewed_candidates_cannot_count_as_verified_ground_truth():
    ledger = build_ledger()
    confirmed = next(entry for entry in ledger["entries"] if entry["first_pass_status"] == "CONFIRMED")

    assert metric_eligible_entries(ledger) == []

    confirmed["human_status"] = "INDEPENDENTLY_CONFIRMED"
    assert [entry["review_id"] for entry in metric_eligible_entries(ledger)] == [confirmed["review_id"]]


def test_independent_review_requires_a_different_reviewer():
    ledger = build_ledger()
    review_id = ledger["entries"][0]["review_id"]

    with pytest.raises(ValueError, match="different from first-pass reviewer"):
        apply_independent_reviews(
            ledger,
            [{"review_id": review_id, "reviewer": "codex_first_pass", "decision": "CONFIRM", "note": "checked"}],
        )

    assert ledger["entries"][0]["human_status"] == "PENDING_INDEPENDENT_REVIEW"


def test_conflicting_independent_review_requires_adjudication():
    ledger = build_ledger()
    confirmed = next(entry for entry in ledger["entries"] if entry["first_pass_status"] == "CONFIRMED")

    updated = apply_independent_reviews(
        ledger,
        [{"review_id": confirmed["review_id"], "reviewer": "reviewer_2", "decision": "REJECT", "note": "类别不符"}],
    )
    reviewed = next(entry for entry in updated["entries"] if entry["review_id"] == confirmed["review_id"])

    assert reviewed["human_status"] == "NEEDS_ADJUDICATION"
    assert metric_eligible_entries(updated) == []


@requires_real_uploads
def test_ocr_batch_without_provider_writes_blocked_plan(tmp_path, monkeypatch):
    monkeypatch.delenv("BID_OCR_PROVIDER", raising=False)
    monkeypatch.delenv("QWEN_OCR_API_KEY", raising=False)
    source = Path(__file__).parents[1] / "work" / "uploads" / "8.20定稿-招标文件-塔里木河流域阿克苏河水利管理中心2027年信息化设计项目.pdf"

    summary = run(source, tmp_path)

    assert summary["adapter_enabled"] is False
    assert summary["blocked_reason"]
    assert json.loads((tmp_path / "batch-summary.json").read_text(encoding="utf-8"))["completed"] == []


def test_ocr_batch_retry_failed_reprocesses_only_failed_pages(tmp_path, monkeypatch):
    import fitz

    source = tmp_path / "scan.pdf"
    document = fitz.open()
    document.new_page()
    document.save(source)
    document.close()
    output_dir = tmp_path / "ocr"
    output_dir.mkdir()
    (output_dir / "page-0001.json").write_text(
        json.dumps({"page": 1, "status": "FAILED", "error": "OCR_UNAVAILABLE"}), encoding="utf-8"
    )

    class Adapter:
        enabled = True

        def extract(self, image_bytes, page_number):
            return OCRResult(text="重试成功", provider="qwen-vl-ocr")

    monkeypatch.setattr("work.ocr_batch.get_ocr_adapter", lambda: Adapter())
    summary = run(source, output_dir, retry_failed=True)

    assert summary["completed"] == [1]
    assert summary["skipped_existing"] == []
    assert json.loads((output_dir / "page-0001.json").read_text(encoding="utf-8"))["status"] == "EXTRACTED"
