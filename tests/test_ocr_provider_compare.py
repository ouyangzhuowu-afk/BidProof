"""Provider compare: zero egress sends without keys; APPROVED_NOT_RUN."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.cohort_manifest import write_cohort_manifest
from work.eval.provider_compare import (
    DOCUMENTED_APPROVAL_ID,
    OUT_DIR,
    attempt_cloud_predict,
    build_compare_report,
    classify_run_status,
    page_failure_record,
    write_reports,
)


@pytest.fixture()
def frozen_manifest(tmp_path):
    path = tmp_path / "cohort.json"
    write_cohort_manifest(path)
    return json.loads(path.read_text(encoding="utf-8"))


def test_classify_approved_not_run_without_keys(monkeypatch):
    monkeypatch.delenv("BIDPROOF_OCR_EGRESS_ALLOWED", raising=False)
    monkeypatch.delenv("BIDPROOF_OCR_EGRESS_APPROVAL", raising=False)
    monkeypatch.delenv("QWEN_OCR_API_KEY", raising=False)
    assert (
        classify_run_status(policy_allowed=False, api_key_present=False, approval_present=False)
        == "APPROVED_NOT_RUN"
    )


def test_cloud_predict_zero_sends_without_keys(frozen_manifest, monkeypatch):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0")
    monkeypatch.delenv("BIDPROOF_OCR_EGRESS_APPROVAL", raising=False)
    monkeypatch.delenv("QWEN_OCR_API_KEY", raising=False)
    sends = {"n": 0}

    def send_fn(**kwargs):
        sends["n"] += 1
        return {"text_hyp": "should-not-run", "lines_hyp": ["should-not-run"]}

    result = attempt_cloud_predict(cohort=frozen_manifest, send_fn=send_fn)
    assert result["status"] == "APPROVED_NOT_RUN"
    assert result["egress_sends"] == 0
    assert sends["n"] == 0
    assert len(result["page_failures"]) == frozen_manifest["page_count"]
    assert all(row["kept_in_denominator"] for row in result["page_failures"])


def test_page_failure_keeps_denominator():
    row = page_failure_record(
        doc_id="fixture-001",
        page=2,
        provider="qwen-vl-ocr",
        reason="not_sent:no_auth_api_key",
    )
    assert row["kept_in_denominator"] is True
    assert row["failure_reason"].startswith("not_sent:")


def test_compare_report_local_baseline_and_no_gate_claim(frozen_manifest, monkeypatch, tmp_path):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0")
    monkeypatch.delenv("QWEN_OCR_API_KEY", raising=False)
    report = build_compare_report(cohort=frozen_manifest, send_fn=None)
    assert report["run_status"] == "APPROVED_NOT_RUN"
    assert report["egress_sends_total"] == 0
    assert report["product_pass"] is False
    assert report["gate_claim"] == "NOT_CLAIMED"
    assert report["page_count"] == 54
    assert report["cer_denominator_chars"] == 29835
    assert report["local"]["line_cer"] == pytest.approx(0.04963968493380258)
    assert report["local"]["line_cer_gate"] == "GATE_FAIL"
    assert report["documented_approval_id"] == DOCUMENTED_APPROVAL_ID
    assert "QWEN_OCR_API_KEY" in " ".join(report["required_env_for_send"])
    write_reports(report)
    assert (OUT_DIR / "provider-compare-report.json").is_file()
    assert (OUT_DIR / "provider-compare-report.md").is_file()
    assert (OUT_DIR / "cloud" / "result.json").is_file()


def test_even_with_policy_on_missing_sender_does_not_send(frozen_manifest, monkeypatch):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_APPROVAL", DOCUMENTED_APPROVAL_ID)
    monkeypatch.setenv("QWEN_OCR_API_KEY", "test-key-not-real")
    result = attempt_cloud_predict(cohort=frozen_manifest, send_fn=None)
    assert result["egress_sends"] == 0
    assert result["status"] == "APPROVED_NOT_RUN"
    assert any("live_sender_not_wired" in row["failure_reason"] for row in result["page_failures"])


def test_injected_sender_records_page_failure_without_dropping(frozen_manifest, monkeypatch):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_APPROVAL", DOCUMENTED_APPROVAL_ID)
    monkeypatch.setenv("QWEN_OCR_API_KEY", "test-key-not-real")

    def boom(**kwargs):
        raise RuntimeError("simulated cloud failure")

    result = attempt_cloud_predict(cohort=frozen_manifest, send_fn=boom)
    assert result["status"] == "RUN"
    # Exceptions are caught per page; successful send counter stays 0.
    assert result["egress_sends"] == 0
    assert len(result["hypotheses"]) == frozen_manifest["page_count"]
    assert all(h.get("failure_reason", "").startswith("cloud_error:") for h in result["hypotheses"])
    assert all(row["kept_in_denominator"] for row in result["page_failures"])
