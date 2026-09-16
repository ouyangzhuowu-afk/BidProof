"""S-A-01: fail-closed page JSONL annotation schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.page_annotation import (
    CURRENT_SCHEMA_VERSION,
    PAGE_TYPES,
    AnnotationError,
    load_annotations,
    validate_jsonl_text,
    validate_record,
)


ROOT = Path(__file__).resolve().parents[1]
SANDBOX_PAGES = ROOT / "work" / "eval" / "fixtures" / "sandbox_pages.jsonl"


def _v1(**overrides):
    record = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "doc_id": "sandbox-public-001",
        "page": 1,
        "page_type": "body",
        "text_gt": "招标编号 SANDBOX-A01",
        "fields": [{"name": "project_code", "value": "SANDBOX-A01"}],
        "table_html": None,
        "has_seal": False,
        "has_hw": False,
    }
    record.update(overrides)
    return record


def test_current_schema_accepts_a_complete_v1_page():
    result = validate_record(_v1())
    assert result.ok is True
    assert result.normalized["schema_version"] == "1.0"
    assert result.normalized["page_type"] == "body"


def test_weak_v0_1_label_stays_compatible_without_optional_fields():
    weak = {
        "schema_version": "0.1",
        "doc_id": "legacy-weak-001",
        "page": 2,
        "text_gt": "封面标题",
    }
    result = validate_record(weak)
    assert result.ok is True
    assert result.normalized["schema_version"] == "0.1"
    assert result.normalized["page_type"] == "body"
    assert result.normalized["fields"] == []
    assert result.normalized["table_html"] is None
    assert result.normalized["has_seal"] is False
    assert result.normalized["has_hw"] is False


def test_missing_schema_version_is_treated_as_weak_compatible_label():
    result = validate_record({"doc_id": "legacy-no-ver", "page": 1, "text_gt": "正文"})
    assert result.ok is True
    assert result.normalized["schema_version"] == "0.1"


@pytest.mark.parametrize(
    "illegal",
    [
        {"doc_id": "", "page": 1, "text_gt": "x", "schema_version": "1.0"},
        _v1(page=0),
        _v1(page=-1),
        _v1(page="1"),
        _v1(page_type="invoice"),
        _v1(text_gt=123),
        _v1(fields="project_code"),
        _v1(fields=[{"name": "project_code"}]),
        _v1(fields=[{"value": "SANDBOX-A01"}]),
        _v1(table_html=0),
        _v1(has_seal="no"),
        _v1(has_hw=1),
        _v1(schema_version="9.0"),
        ["not", "an", "object"],
        "plain string",
    ],
)
def test_illegal_samples_are_rejected_fail_closed(illegal):
    result = validate_record(illegal) if isinstance(illegal, dict) else validate_record(illegal)
    assert result.ok is False
    assert result.issues


def test_jsonl_rejects_duplicate_doc_page_and_bad_json():
    good = json.dumps(_v1(), ensure_ascii=False)
    dup = json.dumps(_v1(text_gt="duplicate page"), ensure_ascii=False)
    result = validate_jsonl_text("\n".join([good, "not-json", dup, ""]))
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "invalid_json" in codes
    assert "duplicate_page" in codes


def test_load_annotations_raises_on_illegal_file(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(_v1(page_type="not-a-type"), ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="fail-closed"):
        load_annotations(path)


def test_sandbox_fixture_is_valid_public_jsonl():
    records = load_annotations(SANDBOX_PAGES)
    assert records
    assert {row["schema_version"] for row in records} <= {"0.1", "1.0"}
    assert {row["page_type"] for row in records} <= PAGE_TYPES
    assert all(row["doc_id"].startswith("sandbox-") for row in records)


def test_page_types_match_documented_enum():
    assert PAGE_TYPES == {"cover", "toc", "body", "table", "seal"}
