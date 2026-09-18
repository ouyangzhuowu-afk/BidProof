"""S-A-07: seal/handwriting page-type slot GT seed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.page_annotation import PAGE_TYPES, load_annotations
from work.eval.seal_hw_gt import (
    coverage_report,
    has_hw_slot,
    has_seal_slot,
    main as seal_hw_main,
    validate_seal_hw_seed,
)


ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "work" / "eval" / "fixtures" / "seal_hw_gt.jsonl"
MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"


def test_page_type_slots_include_seal_and_handwriting():
    assert "seal" in PAGE_TYPES
    assert "handwriting" in PAGE_TYPES


def test_seed_fixture_is_sufficient():
    text = JSONL.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    validation = validate_seal_hw_seed(text, manifest=manifest)
    assert validation.ok
    assert validation.issues == []
    coverage = coverage_report(validation.records)
    assert coverage["coverage_status"] == "SUFFICIENT_SEED"
    assert coverage["seal_pages"] >= 6
    assert coverage["hw_pages"] >= 3
    assert coverage["page_type_seal"] >= 3
    assert coverage["page_type_handwriting"] >= 2
    assert coverage["product_pass"] is False
    assert coverage["detection_status"] == "NOT_EVALUATED"


def test_page_type_seal_requires_has_seal():
    bad = json.dumps(
        {
            "schema_version": "1.0",
            "doc_id": "synthetic-bad-seal",
            "page": 1,
            "page_type": "seal",
            "text_gt": "盖章",
            "fields": [],
            "table_html": None,
            "has_seal": False,
            "has_hw": True,
            "origin": "synthetic",
            "slot": "mixed",
        },
        ensure_ascii=False,
    )
    result = validate_seal_hw_seed(bad + "\n", manifest={"documents": []})
    assert not result.ok
    assert any(issue.code == "seal_slot_inconsistent" for issue in result.issues)


def test_slot_helpers():
    assert has_seal_slot({"has_seal": True, "page_type": "body"})
    assert has_seal_slot({"has_seal": False, "page_type": "seal"})
    assert has_hw_slot({"has_hw": True, "page_type": "body"})
    assert has_hw_slot({"has_hw": False, "page_type": "handwriting"})


def test_cli_sufficient_seed(tmp_path):
    code = seal_hw_main(["--out-dir", str(tmp_path / "ocr-benchmark")])
    assert code == 0
    payload = json.loads((tmp_path / "ocr-benchmark" / "seal-hw-gt-report.json").read_text(encoding="utf-8"))
    assert payload["coverage_status"] == "SUFFICIENT_SEED"
    assert payload["product_pass"] is False


def test_page_annotation_loads_seed():
    records = load_annotations(JSONL)
    assert len(records) == 13
    assert any(row["page_type"] == "handwriting" for row in records)
