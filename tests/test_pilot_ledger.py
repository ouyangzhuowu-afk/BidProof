import csv
from pathlib import Path

from work.pilot_ledger import REQUIRED_FIELDS, append_row, summarize_file, validate_ledger


ROOT = Path(__file__).parents[1]


def test_empty_pilot_ledger_has_a_business_handoff_contract():
    ledger = ROOT / "outputs" / "pilot-ledger.csv"
    with ledger.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REQUIRED_FIELDS
        rows = list(reader)
    assert rows == []
    assert validate_ledger(rows) == {"rows": 0, "confirmed_tasks": 0, "payment_signals": 0}


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

    try:
        append_row(ledger, row)
    except ValueError as exc:
        assert "task_id" in str(exc)
    else:
        raise AssertionError("missing task_id should be rejected")
