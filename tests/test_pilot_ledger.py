import csv
from pathlib import Path

import pytest

from work.pilot_ledger import (
    REQUIRED_FIELDS,
    append_row,
    summarize_file,
    validate_ledger,
    validate_row_for_append,
)

ROOT = Path(__file__).parents[1]
REAL_SHA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _valid_row(**overrides: str) -> dict[str, str]:
    row = {field: "" for field in REQUIRED_FIELDS} | {
        "task_id": "REAL-001",
        "received_at": "2026-08-26T18:00:00+08:00",
        "tender_filename": "招标文件.pdf",
        "enterprise_name": "首批试运行企业",
        "input_scope": "资格与废标风险扫描",
        "output_run_id": "run-real-001",
        "requirement_count": "12",
        "unresolved_count": "3",
        "human_confirmation": "pending",
        "evidence_boundary": "真实企业输入；待人工确认",
        "enterprise_source": "enterprise_response",
        "enterprise_material_sha256": REAL_SHA,
        "enterprise_task_ref": "ENT-TASK-001",
        "human_feedback_text": "",
        "human_feedback_author": "",
        "human_feedback_at": "",
    }
    row.update(overrides)
    return row


def test_empty_pilot_ledger_has_a_business_handoff_contract():
    ledger = ROOT / "outputs" / "pilot-ledger.csv"
    with ledger.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REQUIRED_FIELDS
        rows = list(reader)
    assert rows == []
    assert validate_ledger(rows) == {"rows": 0, "confirmed_tasks": 0, "payment_signals": 0}


def test_unconfirmed_task_cannot_count_as_business_validation():
    rows = [_valid_row(human_confirmation="pending")]
    assert validate_ledger(rows) == {"rows": 1, "confirmed_tasks": 0, "payment_signals": 0}


def test_append_row_preserves_contract_and_returns_fast_summary(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    summary = append_row(ledger, _valid_row())
    assert summary == {"rows": 1, "confirmed_tasks": 0, "payment_signals": 0}
    assert summarize_file(ledger) == summary
    assert ledger.read_text(encoding="utf-8").splitlines()[0].split(",") == REQUIRED_FIELDS


def test_append_row_rejects_missing_task_identity(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    with pytest.raises(ValueError, match="task_id"):
        append_row(ledger, _valid_row(task_id=""))


def test_append_row_rejects_missing_received_at(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    with pytest.raises(ValueError, match="received_at"):
        append_row(ledger, _valid_row(received_at=""))


def test_append_row_rejects_invalid_received_at(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    with pytest.raises(ValueError, match="ISO 8601"):
        append_row(ledger, _valid_row(received_at="not-a-datetime"))


def test_rejects_demo_and_synthetic_tokens(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    with pytest.raises(ValueError, match="demo|synthetic|public-tender"):
        append_row(ledger, _valid_row(task_id="DEMO-001"))
    with pytest.raises(ValueError, match="demo|synthetic|public-tender"):
        append_row(ledger, _valid_row(enterprise_name="synthetic corp"))


def test_rejects_public_tender_only_source(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    with pytest.raises(ValueError, match="public-tender-only|enterprise_source"):
        append_row(ledger, _valid_row(enterprise_source="public_tender_only"))


def test_rejects_confirmed_string_only_without_human_feedback(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    with pytest.raises(ValueError, match="human_feedback_text|confirmed-string-only"):
        append_row(ledger, _valid_row(human_confirmation="confirmed"))


def test_confirmed_requires_feedback_author_and_time(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    row = _valid_row(
        human_confirmation="confirmed",
        human_feedback_text="人工核对：资格材料齐全，页码引用有效",
        human_feedback_author="Joe",
        human_feedback_at="2026-09-02T12:00:00+08:00",
    )
    summary = append_row(ledger, row)
    assert summary == {"rows": 1, "confirmed_tasks": 1, "payment_signals": 0}


def test_rejects_missing_enterprise_material_hash():
    with pytest.raises(ValueError, match="enterprise_material_sha256"):
        validate_row_for_append(_valid_row(enterprise_material_sha256="short"))
