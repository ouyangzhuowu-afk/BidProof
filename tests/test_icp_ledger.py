import csv
from pathlib import Path

import pytest

from work.icp_ledger import REQUIRED_FIELDS, append_row, render_review, summarize_file, validate_ledger


ROOT = Path(__file__).parents[1]


def test_empty_icp_ledger_has_outreach_contract():
    ledger = ROOT / "outputs" / "icp-outreach.csv"
    with ledger.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REQUIRED_FIELDS
        rows = list(reader)
    assert rows == []
    assert validate_ledger(rows) == {"rows": 0, "touched_contacts": 0, "linked_pilot_tasks": 0}


def test_pending_response_does_not_count_as_touched(tmp_path):
    rows = [{field: "" for field in REQUIRED_FIELDS} | {"contact_id": "ICP-001", "response_status": "pending"}]
    assert validate_ledger(rows) == {"rows": 1, "touched_contacts": 0, "linked_pilot_tasks": 0}


def test_append_row_and_render_review(tmp_path):
    ledger = tmp_path / "icp-outreach.csv"
    report = tmp_path / "icp-outreach-review.md"
    row = {field: "" for field in REQUIRED_FIELDS} | {
        "contact_id": "ICP-001",
        "contacted_at": "2026-09-02T10:00:00+08:00",
        "company_name": "示例企业",
        "icp_segment": "IT服务",
        "channel": "熟人介绍",
        "response_status": "interested",
        "next_step": "安排演示",
    }
    summary = append_row(ledger, row)
    assert summary == {"rows": 1, "touched_contacts": 1, "linked_pilot_tasks": 0}
    render_review(ledger, report, target_contacts=30)
    text = report.read_text(encoding="utf-8")
    assert "1 / 30" in text
    assert "IN_PROGRESS" in text


def test_append_row_rejects_missing_contact_id(tmp_path):
    ledger = tmp_path / "icp-outreach.csv"
    row = {field: "" for field in REQUIRED_FIELDS}

    with pytest.raises(ValueError, match="contact_id"):
        append_row(ledger, row)


def test_append_row_rejects_invalid_next_step_due(tmp_path):
    ledger = tmp_path / "icp-outreach.csv"
    row = {field: "" for field in REQUIRED_FIELDS} | {
        "contact_id": "ICP-002",
        "contacted_at": "2026-09-02T10:00:00+08:00",
        "next_step_due": "09/09/2026",
    }

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        append_row(ledger, row)
