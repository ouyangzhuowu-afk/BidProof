"""Frozen OCR cohort integrity for cloud compare."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.cohort_manifest import (
    COHORT_ID,
    DEFAULT_MANIFEST_PATH,
    EXPECTED_CER_DENOM,
    EXPECTED_PAGE_COUNT,
    SCORER_VERSION,
    build_cohort_manifest,
    compute_cer_denominator,
    verify_cohort_manifest,
    write_cohort_manifest,
)
from work.eval.page_annotation import load_annotations
from work.eval.public_expand import CER_GT_PATH, CER_HYP_PATH
from work.eval.rapidocr_line_cer import load_hypotheses

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_page_count_and_denominator():
    gt = load_annotations(CER_GT_PATH)
    hyp = load_hypotheses(CER_HYP_PATH)
    assert len(gt) == EXPECTED_PAGE_COUNT
    assert compute_cer_denominator(gt, hyp) == EXPECTED_CER_DENOM


def test_build_manifest_matches_freeze_constants(tmp_path):
    payload = build_cohort_manifest()
    assert payload["cohort_id"] == COHORT_ID
    assert payload["page_count"] == EXPECTED_PAGE_COUNT
    assert payload["cer_denominator_chars"] == EXPECTED_CER_DENOM
    assert payload["scorer_version"] == SCORER_VERSION
    assert payload["product_pass"] is False
    assert len(payload["pages"]) == EXPECTED_PAGE_COUNT
    assert payload["integrity"]["pages_never_dropped_from_denominator"] is True
    for page in payload["pages"]:
        assert page["doc_id"]
        assert int(page["page"]) >= 1
        assert len(page["pdf_sha256"]) == 64
        assert len(page["gt_text_sha256"]) == 64
    assert all(len(doc["pdf_sha256"]) == 64 for doc in payload["documents"])


def test_write_and_verify_roundtrip(tmp_path):
    out = tmp_path / "cohort.json"
    write_cohort_manifest(out)
    assert out.is_file()
    result = verify_cohort_manifest(path=out)
    assert result["ok"] is True
    assert result["errors"] == []


def test_verify_detects_page_drift(tmp_path):
    payload = build_cohort_manifest()
    payload["pages"] = payload["pages"][:-1]
    payload["page_count"] = len(payload["pages"])
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_cohort_manifest(path=bad)
    assert result["ok"] is False
    assert any("page" in err for err in result["errors"])


def test_committed_manifest_if_present():
    if not DEFAULT_MANIFEST_PATH.is_file():
        pytest.skip("committed freeze not written yet")
    result = verify_cohort_manifest(path=DEFAULT_MANIFEST_PATH)
    assert result["ok"] is True
