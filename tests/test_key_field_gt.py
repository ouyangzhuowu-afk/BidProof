"""S-A-04: key-field ground-truth seed expansion (public/synthetic only).

Fail-closed: missing GT is INSUFFICIENT, never a fabricated F1 or product PASS.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from work.eval.page_annotation import PAGE_TYPES, load_annotations, validate_record
from work.eval.key_field_gt import (
    FORBIDDEN_OUTPUT_TOKENS,
    KEY_FIELD_NAMES,
    MIN_LABELED_FIELDS,
    MIN_PUBLIC_DOCS,
    ForbiddenOutputError,
    KeyFieldGtError,
    evaluate_coverage,
    load_key_field_names,
    main as key_field_gt_main,
    validate_seed,
    write_report,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "work" / "eval" / "page_annotation.schema.json"
NAMES_JSON = ROOT / "work" / "eval" / "key_field_names.json"
SEED_JSONL = ROOT / "work" / "eval" / "fixtures" / "key_field_gt.jsonl"
CANONICAL_MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"
CANONICAL_PDFS = ROOT / "work" / "public-eval" / "pdfs"
PILOT_LEDGER = ROOT / "outputs" / "pilot-ledger.csv"
ICP_LEDGER = ROOT / "outputs" / "icp-outreach.csv"
SANDBOX_PAGES = ROOT / "work" / "eval" / "fixtures" / "sandbox_pages.jsonl"


def _v1_page(**overrides):
    record = {
        "schema_version": "1.0",
        "doc_id": "fixture-001",
        "page": 1,
        "page_type": "body",
        "text_gt": "项目名称:公开招标演示 项目编号:PUB-001 预算:10 万元",
        "fields": [{"name": "project_name", "value": "公开招标演示"}],
        "table_html": None,
        "has_seal": False,
        "has_hw": False,
        "origin": "public",
        "source_url": "https://gov.example/pub.pdf",
        "sha256": "a" * 64,
    }
    record.update(overrides)
    return record


def _manifest_row(document_id: str, **extra):
    row = {
        "document_id": document_id,
        "source_url": extra.pop("source_url", f"https://gov.example/{document_id}.pdf"),
        "sha256": extra.pop("sha256", "a" * 64),
        "filename": extra.pop("filename", f"{document_id}.pdf"),
        "path": extra.pop("path", f"work/public-eval/pdfs/{document_id}.pdf"),
        "status": extra.pop("status", "fetched"),
    }
    row.update(extra)
    return row


def _seed_text(records: list[dict]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n"


def test_frozen_key_field_enum_is_documented_and_stable():
    names = load_key_field_names(NAMES_JSON)
    assert names == KEY_FIELD_NAMES
    assert "project_name" in names
    assert "budget" in names
    assert "deadline" in names
    assert "bid_bond" in names
    # Legacy aliases must not re-enter the F1 vocabulary.
    for drifted in ("bond", "bond_required", "bond_section", "no_bond", "table_title"):
        assert drifted not in names
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["$defs"]["key_field_name"]["enum"] == sorted(names)


def test_s_a_01_still_allows_non_key_field_names_on_page_schema():
    result = validate_record(
        {
            "schema_version": "1.0",
            "doc_id": "sandbox-public-002",
            "page": 1,
            "page_type": "table",
            "text_gt": "报价明细",
            "fields": [{"name": "table_title", "value": "报价明细"}],
            "table_html": None,
            "has_seal": False,
            "has_hw": False,
        }
    )
    assert result.ok is True
    records = load_annotations(SANDBOX_PAGES)
    assert any(
        field.get("name") == "table_title"
        for row in records
        for field in row.get("fields") or []
    )


def test_unknown_key_field_name_is_rejected_fail_closed():
    text = _seed_text(
        [
            _v1_page(fields=[{"name": "bond_required", "value": "不收取投标保证金"}]),
        ]
    )
    result = validate_seed(text, manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    assert any(issue.code == "unknown_key_field_name" for issue in result.issues)


def test_public_rows_require_manifest_source_url_and_matching_sha256():
    good = _v1_page()
    missing_url = _v1_page(page=2, source_url="", text_gt="预算:10 万元", fields=[{"name": "budget", "value": "10 万元"}])
    result = validate_seed(
        _seed_text([good, missing_url]),
        manifest={"documents": [_manifest_row("fixture-001")]},
    )
    assert result.ok is False
    assert any(issue.code in {"missing_source_url", "manifest_mismatch"} for issue in result.issues)


def test_synthetic_rows_must_be_labeled_synthetic_and_not_counted_as_public():
    unlabeled = _v1_page(
        doc_id="synthetic-keyfield-001",
        origin="public",
        source_url="https://example.invalid/synth.pdf",
        text_gt="项目名称:SYNTH-演示",
        fields=[{"name": "project_name", "value": "SYNTH-演示"}],
    )
    result = validate_seed(_seed_text([unlabeled]), manifest={"documents": []})
    assert result.ok is False

    labeled = _v1_page(
        doc_id="synthetic-keyfield-001",
        origin="synthetic",
        source_url=None,
        sha256=None,
        text_gt="项目名称:SYNTH-演示 预算:1 万元",
        fields=[
            {"name": "project_name", "value": "SYNTH-演示"},
            {"name": "budget", "value": "1 万元"},
        ],
    )
    labeled.pop("source_url")
    labeled.pop("sha256")
    result = validate_seed(_seed_text([labeled]), manifest={"documents": []})
    assert result.ok is True
    coverage = evaluate_coverage(result.records)
    assert coverage["public_documents"] == 0
    assert coverage["synthetic_documents"] == 1
    assert coverage["coverage_status"] == "INSUFFICIENT"
    assert coverage["product_pass"] is False
    assert coverage["f1_status"] == "NOT_EVALUATED"


def test_coverage_below_thresholds_is_insufficient_not_a_high_score(tmp_path):
    records = []
    for index in range(2):
        doc_id = f"fixture-00{index+1}"
        records.append(
            _v1_page(
                doc_id=doc_id,
                source_url=f"https://gov.example/{doc_id}.pdf",
                sha256="b" * 64 if index else "a" * 64,
                text_gt="项目名称:公开项目 预算:10 万元",
                fields=[
                    {"name": "project_name", "value": "公开项目"},
                    {"name": "budget", "value": "10 万元"},
                ],
            )
        )
    manifest = {
        "documents": [
            _manifest_row("fixture-001"),
            _manifest_row("fixture-002", sha256="b" * 64, source_url="https://gov.example/fixture-002.pdf"),
        ]
    }
    result = validate_seed(_seed_text(records), manifest=manifest)
    assert result.ok is True
    coverage = evaluate_coverage(result.records)
    assert coverage["public_documents"] == 2
    assert coverage["labeled_key_fields"] == 4
    assert coverage["coverage_status"] == "INSUFFICIENT"
    assert coverage["product_pass"] is False
    assert coverage["business_pass"] is False
    assert coverage["f1"] is None
    assert coverage["f1_status"] == "NOT_EVALUATED"
    reasons = " ".join(coverage["insufficient_reasons"])
    assert "public_documents" in reasons
    assert "labeled_key_fields" in reasons
    assert "PASS" not in reasons
    report = write_report(coverage, result, out_dir=tmp_path)
    markdown = report["markdown"]
    assert "INSUFFICIENT" in markdown
    assert "product PASS" not in markdown.lower() or "not a product" in markdown.lower()
    assert "F1" in markdown
    assert "NOT_EVALUATED" in markdown or "not evaluated" in markdown.lower()


def test_write_report_refuses_ledger_paths(tmp_path):
    result = validate_seed(_seed_text([_v1_page()]), manifest={"documents": [_manifest_row("fixture-001")]})
    coverage = evaluate_coverage(result.records)
    with pytest.raises(ForbiddenOutputError):
        write_report(coverage, result, out_dir=tmp_path / "pilot-ledger")
    assert any(token in "pilot-ledger" for token in FORBIDDEN_OUTPUT_TOKENS)


def test_field_value_must_appear_in_text_gt_fail_closed():
    text = _seed_text(
        [
            _v1_page(
                text_gt="项目名称:真实标题",
                fields=[{"name": "project_name", "value": "不存在于原文的值"}],
            )
        ]
    )
    result = validate_seed(text, manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    assert any(issue.code == "value_not_in_text_gt" for issue in result.issues)


def test_personal_identifier_values_are_rejected():
    text = _seed_text(
        [
            _v1_page(
                text_gt="联系电话 13800138000",
                fields=[{"name": "purchaser", "value": "13800138000"}],
            )
        ]
    )
    result = validate_seed(text, manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "pii_value" in codes or "pii_in_text_gt" in codes


def test_phone_in_text_gt_is_rejected_even_if_fields_are_clean():
    text = _seed_text(
        [
            _v1_page(
                text_gt="项目名称:公开招标演示 咨询电话 0771-3381253",
                fields=[{"name": "project_name", "value": "公开招标演示"}],
            )
        ]
    )
    result = validate_seed(text, manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    assert any(issue.code == "pii_in_text_gt" for issue in result.issues)


def test_committed_seed_meets_min_public_docs_and_fields():
    assert MIN_PUBLIC_DOCS == 5
    assert MIN_LABELED_FIELDS == 30
    assert SEED_JSONL.is_file()
    payload = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    result = validate_seed(
        SEED_JSONL.read_text(encoding="utf-8"),
        manifest=payload,
        pdfs_dir=CANONICAL_PDFS,
    )
    assert result.ok is True, [issue.message for issue in result.issues]
    coverage = evaluate_coverage(result.records)
    assert coverage["public_documents"] >= MIN_PUBLIC_DOCS
    assert coverage["labeled_key_fields"] >= MIN_LABELED_FIELDS
    assert coverage["coverage_status"] == "SUFFICIENT_SEED"
    assert coverage["product_pass"] is False
    assert coverage["business_pass"] is False
    assert coverage["f1"] is None
    assert coverage["f1_status"] == "NOT_EVALUATED"
    assert {row["page_type"] for row in result.records} <= PAGE_TYPES
    for row in result.records:
        for field in row["fields"]:
            assert field["name"] in KEY_FIELD_NAMES


def test_committed_public_docs_match_canonical_manifest_sha256():
    payload = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    by_id = {row["document_id"]: row for row in payload.get("documents", [])}
    result = validate_seed(
        SEED_JSONL.read_text(encoding="utf-8"),
        manifest=payload,
        pdfs_dir=CANONICAL_PDFS,
    )
    assert result.ok is True
    public_ids = sorted({row["doc_id"] for row in result.records if row["origin"] == "public"})
    assert len(public_ids) >= 5
    for doc_id in public_ids:
        manifest_row = by_id[doc_id]
        path = ROOT / manifest_row["path"]
        assert path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == manifest_row["sha256"]
        labeled = next(row for row in result.records if row["doc_id"] == doc_id)
        assert labeled["source_url"] == manifest_row["source_url"]
        assert labeled["sha256"] == manifest_row["sha256"]


def test_cli_does_not_touch_pilot_or_icp_ledgers(tmp_path):
    out_dir = tmp_path / "ocr-benchmark"
    pilot_before = PILOT_LEDGER.read_text(encoding="utf-8")
    icp_before = ICP_LEDGER.read_text(encoding="utf-8")
    code = key_field_gt_main(["--jsonl", str(SEED_JSONL), "--out-dir", str(out_dir)])
    assert code == 0
    assert PILOT_LEDGER.read_text(encoding="utf-8") == pilot_before
    assert ICP_LEDGER.read_text(encoding="utf-8") == icp_before
    md = (out_dir / "key-field-gt-report.md").read_text(encoding="utf-8")
    data = json.loads((out_dir / "key-field-gt-report.json").read_text(encoding="utf-8"))
    assert "SUFFICIENT_SEED" in md
    assert data["product_pass"] is False
    assert data["f1_status"] == "NOT_EVALUATED"
    assert "T-005" in md
    assert not list(tmp_path.rglob("*pilot-ledger*"))
    assert not list(tmp_path.rglob("*icp-outreach*"))


def test_empty_or_missing_seed_is_fail_closed(tmp_path):
    result = validate_seed("\n", manifest={"documents": []})
    assert result.ok is False
    assert any(issue.code == "empty_seed" for issue in result.issues)
    missing = tmp_path / "absent.jsonl"
    with pytest.raises(KeyFieldGtError, match="fail-closed"):
        from work.eval.key_field_gt import load_seed

        load_seed(missing, manifest={"documents": []})
