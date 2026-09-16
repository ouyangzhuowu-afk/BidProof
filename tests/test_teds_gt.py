"""S-A-05: TEDS table-structure ground-truth seeds (public/synthetic only).

Fail-closed: missing GT is INSUFFICIENT, never a fabricated TEDS score or product PASS.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from work.eval.page_annotation import PAGE_TYPES, load_annotations, validate_jsonl_path
from work.eval.teds_gt import (
    FORBIDDEN_OUTPUT_TOKENS,
    MIN_PUBLIC_DOCS,
    MIN_TEDS_PAGES,
    ForbiddenOutputError,
    TedsGtError,
    count_teds_gt_pages,
    evaluate_coverage,
    has_teds_gt,
    main as teds_gt_main,
    rows_to_table_html,
    validate_seed,
    write_report,
)


ROOT = Path(__file__).resolve().parents[1]
SEED_JSONL = ROOT / "work" / "eval" / "fixtures" / "teds_gt.jsonl"
CANONICAL_MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"
CANONICAL_PDFS = ROOT / "work" / "public-eval" / "pdfs"
PILOT_LEDGER = ROOT / "outputs" / "pilot-ledger.csv"
ICP_LEDGER = ROOT / "outputs" / "icp-outreach.csv"
SANDBOX_PAGES = ROOT / "work" / "eval" / "fixtures" / "sandbox_pages.jsonl"


def _table_html(rows=None):
    rows = rows or [["序号", "名称", "数量"], ["1", "超声主机", "1"]]
    return rows_to_table_html(rows)


def _v1_page(**overrides):
    table_html = _table_html()
    record = {
        "schema_version": "1.0",
        "doc_id": "fixture-001",
        "page": 1,
        "page_type": "table",
        "text_gt": "序号 名称 数量\n1 超声主机 1",
        "fields": [{"name": "table_title", "value": "配置清单"}],
        "table_html": table_html,
        "has_seal": False,
        "has_hw": False,
        "origin": "public",
        "source_url": "https://gov.example/pub.pdf",
        "sha256": "a" * 64,
        "table_span": "single_page",
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


def test_has_teds_gt_requires_table_markup():
    assert has_teds_gt({"table_html": "<table><tr><td>a</td></tr></table>"}) is True
    assert has_teds_gt({"table_html": "<TABLE><tr><th>a</th></tr></TABLE>"}) is True
    assert has_teds_gt({"table_html": None}) is False
    assert has_teds_gt({"table_html": ""}) is False
    assert has_teds_gt({"table_html": "<div>not a table</div>"}) is False
    assert count_teds_gt_pages([{"table_html": None}, {"table_html": "<table></table>"}]) == 1


def test_null_or_non_table_html_is_rejected_for_teds_seed():
    missing = _v1_page(table_html=None)
    result = validate_seed(_seed_text([missing]), manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    assert any(issue.code == "missing_table_html" for issue in result.issues)

    junk = _v1_page(table_html="<p>报价明细</p>")
    result = validate_seed(_seed_text([junk]), manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    assert any(issue.code == "invalid_table_html" for issue in result.issues)


def test_s_a_01_schema_still_allows_null_table_html_outside_teds_seed():
    records = load_annotations(SANDBOX_PAGES)
    assert any(row.get("table_html") is None for row in records)
    assert count_teds_gt_pages(records) == 0


def test_public_rows_require_manifest_source_url_and_matching_sha256():
    good = _v1_page()
    missing_url = _v1_page(page=2, source_url="")
    result = validate_seed(
        _seed_text([good, missing_url]),
        manifest={"documents": [_manifest_row("fixture-001")]},
    )
    assert result.ok is False
    assert any(issue.code in {"missing_source_url", "manifest_mismatch"} for issue in result.issues)


def test_synthetic_rows_must_be_labeled_synthetic_and_not_counted_as_public():
    unlabeled = _v1_page(
        doc_id="synthetic-teds-001",
        origin="public",
        source_url="https://example.invalid/synth.pdf",
        text_gt="【SYNTHETIC】序号 名称 数量 1 超声主机 1",
    )
    result = validate_seed(_seed_text([unlabeled]), manifest={"documents": []})
    assert result.ok is False

    labeled = _v1_page(
        doc_id="synthetic-teds-001",
        origin="synthetic",
        source_url=None,
        sha256=None,
        text_gt="【SYNTHETIC 合成样本,非真实招标】\n序号 名称 数量\n1 超声主机 1",
    )
    labeled.pop("source_url")
    labeled.pop("sha256")
    result = validate_seed(_seed_text([labeled]), manifest={"documents": []})
    assert result.ok is True
    coverage = evaluate_coverage(result.records)
    assert coverage["public_documents"] == 0
    assert coverage["synthetic_documents"] == 1
    assert coverage["teds_gt_pages"] == 1
    assert coverage["coverage_status"] == "INSUFFICIENT"
    assert coverage["product_pass"] is False
    assert coverage["teds_status"] == "NOT_EVALUATED"
    assert coverage["teds"] is None


def test_coverage_below_fifteen_pages_is_insufficient_not_a_high_score(tmp_path):
    records = []
    for index in range(2):
        doc_id = f"fixture-00{index + 1}"
        records.append(
            _v1_page(
                doc_id=doc_id,
                source_url=f"https://gov.example/{doc_id}.pdf",
                sha256="b" * 64 if index else "a" * 64,
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
    assert coverage["teds_gt_pages"] == 2
    assert coverage["teds_gt_pages"] < MIN_TEDS_PAGES
    assert coverage["coverage_status"] == "INSUFFICIENT"
    assert coverage["product_pass"] is False
    assert coverage["business_pass"] is False
    assert coverage["teds"] is None
    assert coverage["teds_status"] == "NOT_EVALUATED"
    reasons = " ".join(coverage["insufficient_reasons"])
    assert "teds_gt_pages" in reasons
    assert "PASS" not in reasons
    report = write_report(coverage, result, out_dir=tmp_path)
    markdown = report["markdown"]
    assert "INSUFFICIENT" in markdown
    assert "not a product" in markdown.lower()
    assert "NOT_EVALUATED" in markdown or "not evaluated" in markdown.lower()
    assert "TEDS ≥ 90%" in markdown or "TEDS>=90%" in markdown or "teds_gate" in markdown.lower()


def test_write_report_refuses_ledger_paths(tmp_path):
    result = validate_seed(_seed_text([_v1_page()]), manifest={"documents": [_manifest_row("fixture-001")]})
    coverage = evaluate_coverage(result.records)
    with pytest.raises(ForbiddenOutputError):
        write_report(coverage, result, out_dir=tmp_path / "pilot-ledger")
    assert any(token in "pilot-ledger" for token in FORBIDDEN_OUTPUT_TOKENS)


def test_cross_page_continuation_markers_are_rejected():
    text = _seed_text(
        [
            _v1_page(
                text_gt="续表 序号 名称 数量\n1 超声主机 1",
                table_html=_table_html(),
            )
        ]
    )
    result = validate_seed(text, manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    assert any(issue.code == "cross_page_table" for issue in result.issues)


def test_table_span_must_be_single_page_for_week1():
    text = _seed_text([_v1_page(table_span="cross_page")])
    result = validate_seed(text, manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    assert any(issue.code == "cross_page_table" for issue in result.issues)


def test_header_cells_must_appear_in_text_gt():
    text = _seed_text(
        [
            _v1_page(
                text_gt="完全不相关的正文",
                table_html=_table_html([["序号", "名称"], ["1", "超声主机"]]),
            )
        ]
    )
    result = validate_seed(text, manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    assert any(issue.code == "cell_not_in_text_gt" for issue in result.issues)


def test_personal_identifier_values_are_rejected():
    html = rows_to_table_html([["联系人", "电话"], ["张三", "13800138000"]])
    text = _seed_text(
        [
            _v1_page(
                text_gt="联系人 电话 张三 13800138000",
                table_html=html,
            )
        ]
    )
    result = validate_seed(text, manifest={"documents": [_manifest_row("fixture-001")]})
    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "pii_value" in codes or "pii_in_text_gt" in codes


def test_empty_or_missing_seed_is_fail_closed(tmp_path):
    result = validate_seed("\n", manifest={"documents": []})
    assert result.ok is False
    assert any(issue.code == "empty_seed" for issue in result.issues)
    missing = tmp_path / "absent.jsonl"
    with pytest.raises(TedsGtError, match="fail-closed"):
        from work.eval.teds_gt import load_seed

        load_seed(missing, manifest={"documents": []})


def test_committed_seed_meets_min_teds_pages_and_schema():
    assert MIN_TEDS_PAGES == 15
    assert MIN_PUBLIC_DOCS == 3
    assert SEED_JSONL.is_file()
    schema = validate_jsonl_path(SEED_JSONL)
    assert schema.ok is True, [issue.message for issue in schema.issues]
    payload = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    result = validate_seed(
        SEED_JSONL.read_text(encoding="utf-8"),
        manifest=payload,
        pdfs_dir=CANONICAL_PDFS,
    )
    assert result.ok is True, [issue.message for issue in result.issues]
    coverage = evaluate_coverage(result.records)
    assert coverage["teds_gt_pages"] >= MIN_TEDS_PAGES
    assert coverage["public_documents"] >= MIN_PUBLIC_DOCS
    assert coverage["coverage_status"] == "SUFFICIENT_SEED"
    assert coverage["product_pass"] is False
    assert coverage["business_pass"] is False
    assert coverage["teds"] is None
    assert coverage["teds_status"] == "NOT_EVALUATED"
    assert {row["page_type"] for row in result.records} <= PAGE_TYPES
    assert all(row["page_type"] == "table" for row in result.records)
    assert all(has_teds_gt(row) for row in result.records)
    assert all(row.get("table_span") == "single_page" for row in result.records)
    origins = {row["origin"] for row in result.records}
    assert "public" in origins
    assert "synthetic" in origins
    assert any(row["doc_id"].startswith("synthetic-") for row in result.records if row["origin"] == "synthetic")


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
    assert len(public_ids) >= MIN_PUBLIC_DOCS
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
    code = teds_gt_main(["--jsonl", str(SEED_JSONL), "--out-dir", str(out_dir)])
    assert code == 0
    assert PILOT_LEDGER.read_text(encoding="utf-8") == pilot_before
    assert ICP_LEDGER.read_text(encoding="utf-8") == icp_before
    md = (out_dir / "teds-gt-report.md").read_text(encoding="utf-8")
    data = json.loads((out_dir / "teds-gt-report.json").read_text(encoding="utf-8"))
    assert "SUFFICIENT_SEED" in md
    assert data["product_pass"] is False
    assert data["teds_status"] == "NOT_EVALUATED"
    assert data["teds"] is None
    assert data["teds_gt_pages"] >= MIN_TEDS_PAGES
    assert "T-005" in md
    assert not list(tmp_path.rglob("*pilot-ledger*"))
    assert not list(tmp_path.rglob("*icp-outreach*"))
