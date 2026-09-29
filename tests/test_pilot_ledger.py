import csv
from pathlib import Path

import pytest

from work.pilot_ledger import (
    REQUIRED_FIELDS,
    append_row,
    summarize_file,
    validate_ledger,
)

ROOT = Path(__file__).parents[1]


def test_pending_consultation_row_is_not_business_validation():
    ledger = ROOT / "outputs" / "pilot-ledger.csv"
    with ledger.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REQUIRED_FIELDS
        rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    assert row["task_id"] == "CONSULT-SMD-CG-202549"
    assert row["enterprise_name"] == "unknown-enterprise"
    assert row["human_confirmation"] == "pending"
    assert row["payment_signal"] == ""
    assert row["payment_note"] == ""
    assert row["output_run_id"] == ""
    assert "不是企业投标" in row["evidence_boundary"]
    assert "无企业反馈" in row["evidence_boundary"]
    assert "不解除 T-005" in row["evidence_boundary"]
    assert validate_ledger(rows) == {"rows": 1, "confirmed_tasks": 0, "payment_signals": 0}


def test_unconfirmed_task_cannot_count_as_business_validation():
    rows = [{field: "" for field in REQUIRED_FIELDS}
            | {"task_id": "DEMO-001", "human_confirmation": "pending"}]
    assert validate_ledger(rows) == {"rows": 1, "confirmed_tasks": 0, "payment_signals": 0}


def test_append_row_preserves_contract_and_returns_fast_summary(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
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
    }

    summary = append_row(ledger, row)

    assert summary == {"rows": 1, "confirmed_tasks": 0, "payment_signals": 0}
    assert summarize_file(ledger) == summary
    assert ledger.read_text(encoding="utf-8").splitlines()[0].split(",") == REQUIRED_FIELDS


def test_append_row_rejects_missing_task_identity(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    row = {field: "" for field in REQUIRED_FIELDS}

    with pytest.raises(ValueError, match="task_id"):
        append_row(ledger, row)


def test_append_row_rejects_missing_received_at(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    row = {field: "" for field in REQUIRED_FIELDS} | {"task_id": "REAL-001"}

    with pytest.raises(ValueError, match="received_at"):
        append_row(ledger, row)


def test_append_row_rejects_invalid_received_at(tmp_path):
    ledger = tmp_path / "pilot-ledger.csv"
    row = {field: "" for field in REQUIRED_FIELDS} | {
        "task_id": "REAL-001",
        "received_at": "not-a-datetime",
    }

    with pytest.raises(ValueError, match="ISO 8601"):
        append_row(ledger, row)
