"""S-A-OCR-PUBLIC-EXPAND: public OCR eval stays fail-closed and leakage-free."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.public_expand import (
    LEAF_ID,
    build_report_from_fixtures,
    fields_from_text,
    is_forbidden_source,
    is_synthetic_row,
    looks_like_pii,
    redact_text,
    score_bundle,
    table_supported_by_text_layer,
)
from work.eval.sandbox_gates import KEY_FIELD_F1_MIN, LINE_CER_MAX, TEDS_MIN

ROOT = Path(__file__).resolve().parents[1]


def test_thresholds_unchanged():
    assert LINE_CER_MAX == 0.02
    assert KEY_FIELD_F1_MIN == 0.97
    assert TEDS_MIN == 0.9


def test_redacts_phone_id_and_contact_names():
    raw = "联系人：张三\n电话 13812345678\n证件 110101199001011234\n采购人：右江民族医学院附属医院"
    cleaned = redact_text(raw)
    assert "13812345678" not in cleaned
    assert "110101199001011234" not in cleaned
    assert "张三" not in cleaned
    assert "右江民族医学院附属医院" in cleaned
    assert not looks_like_pii(cleaned)
    requirement = "法定代表人（或负责人）或授权代表身份证复印件 符合招标文件要求"
    kept = redact_text(requirement)
    assert "授权代表身份证复印件" in kept
    assert "符合招标文件要求" in kept
    assert "已隐去" not in kept
    table = (
        "<table><tr><td>法定代表人（或负责人）或授权代表身份证复印件</td>"
        "<td>联系人：张三 13812345678</td></tr></table>"
    )
    cleaned_table = redact_text(table)
    assert "<table>" in cleaned_table and "</table>" in cleaned_table
    assert "授权代表身份证复印件" in cleaned_table
    assert "张三" not in cleaned_table
    assert "13812345678" not in cleaned_table


def test_forbidden_sources_cover_training_corpus_fujian_and_case_studies():
    assert is_forbidden_source("work/training-corpus/tender-public/pdfs/a.pdf")
    assert is_forbidden_source("source2-fujian.pdf")
    assert is_forbidden_source("outputs/case-studies/demo.pdf")
    assert not is_forbidden_source("work/public-eval/pdfs/pub-gx-tianlin.pdf")


def test_synthetic_rows_are_detected():
    assert is_synthetic_row({"origin": "synthetic", "doc_id": "synthetic-teds-score"})
    assert is_synthetic_row({"doc_id": "sandbox-public-001"})
    assert not is_synthetic_row({"origin": "public", "doc_id": "fixture-001"})


def test_fields_come_from_text_not_from_a_guess():
    text = "项目编号：GXZC2026-G1-001969-GXJT\n项目名称：南溪山医院医疗设备采购\n预算金额：4630000.00 元"
    found = fields_from_text(text)
    assert found["project_code"] == "GXZC2026-G1-001969-GXJT"
    assert found["project_name"].startswith("南溪山医院")
    assert "4630000.00" in found["budget"]


def test_table_must_be_supported_by_the_text_layer():
    rows = [["序号", "名称"], ["1", "超声诊断系统"]]
    assert table_supported_by_text_layer(rows, "序号 名称\n1 超声诊断系统")
    assert not table_supported_by_text_layer(rows, "这是一段完全无关的正文")


def test_score_bundle_excludes_nothing_by_itself_and_stays_not_product_pass():
    cer_gt = [{"doc_id": "d", "page": 1, "text_gt": "采购预算100万元"}]
    cer_hyp = [{"doc_id": "d", "page": 1, "text_hyp": "采购预算100万元", "lines_hyp": ["采购预算100万元"]}]
    scored = score_bundle(cer_gt, cer_hyp, [], [], [], [])
    assert scored["line_cer"] == 0.0
    assert scored["line_cer_gate"] == "GATE_PASS"
    assert scored["teds_gate"] == "GATE_FAIL"
    assert scored["key_field_f1_gate"] == "GATE_FAIL"


def test_old_published_metrics_still_reproduce():
    from work.eval.page_annotation import load_annotations
    from work.eval.public_expand import (
        OLD_CER_GT,
        OLD_CER_HYP,
        OLD_KF_GT,
        OLD_KF_HYP,
        OLD_TEDS_GT,
        OLD_TEDS_HYP,
        _read_jsonl,
    )
    from work.eval.rapidocr_line_cer import load_hypotheses

    scored = score_bundle(
        load_annotations(OLD_CER_GT),
        load_hypotheses(OLD_CER_HYP),
        load_annotations(OLD_TEDS_GT),
        _read_jsonl(OLD_TEDS_HYP),
        load_annotations(OLD_KF_GT),
        _read_jsonl(OLD_KF_HYP),
    )
    assert scored["line_cer"] == pytest.approx(0.031746031746031744)
    assert scored["line_cer_gate"] == "GATE_FAIL"
    assert scored["key_field_f1"] == pytest.approx(0.76)
    assert scored["key_field_f1_gate"] == "GATE_FAIL"
    assert scored["teds"] == pytest.approx(0.8784546114752891, rel=1e-6)
    assert scored["teds_gate"] == "GATE_FAIL"
    assert scored["teds_pages_scored"] == 16


def test_expand_fixtures_do_not_use_training_corpus_or_synthetic_gt(tmp_path):
    pages = ROOT / "work" / "eval" / "fixtures" / "public_expand_pages.jsonl"
    if not pages.is_file():
        pytest.skip("expand fixtures are written by --build")
    for line in pages.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        assert row.get("origin") == "public"
        assert not is_synthetic_row(row)
        blob = json.dumps(row, ensure_ascii=False)
        assert "training-corpus" not in blob
        assert "source2-fujian" not in blob
        assert row.get("source_url")
        assert row.get("fetched_at")
        assert row.get("license_or_usage_note")
        assert row.get("gt_source") != "ocr"
        assert not looks_like_pii(row.get("text_gt") or "")
    teds = ROOT / "work" / "eval" / "fixtures" / "public_expand_teds_gt.jsonl"
    teds_rows = [json.loads(line) for line in teds.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert teds_rows
    for row in teds_rows:
        assert "<table" in str(row.get("table_html") or "").lower()
        assert not looks_like_pii(json.dumps(row, ensure_ascii=False))


def test_report_keeps_product_pass_false_and_separates_synthetic():
    report_path = ROOT / "outputs" / "ocr-benchmark" / "public-expand-report.json"
    if not report_path.is_file():
        pytest.skip("report is written by --build")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["leaf_id"] == LEAF_ID
    assert report["product_pass"] is False
    assert report["t005"] is False
    assert report["old_set"]["line_cer_gate"] == "GATE_FAIL"
    assert report["old_set"]["key_field_f1_gate"] == "GATE_FAIL"
    assert report["old_set"]["teds_gate"] == "GATE_FAIL"
    assert report["synthetic_appendix"]["line_cer_pages"] == 3
    rebuilt = build_report_from_fixtures()
    assert rebuilt["expanded"]["line_cer"] == pytest.approx(report["expanded"]["line_cer"])
    assert rebuilt["expanded"]["key_field_f1"] == pytest.approx(report["expanded"]["key_field_f1"])
    assert rebuilt["expanded"]["teds"] == pytest.approx(report["expanded"]["teds"])
    for row in report["sources"]:
        if row.get("scored"):
            assert row.get("source_url")
            assert row.get("fetched_at")
            assert row.get("license_or_usage_note")
