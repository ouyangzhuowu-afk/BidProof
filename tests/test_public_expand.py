"""S-A-OCR-PUBLIC-EXPAND: public OCR eval stays fail-closed and leakage-free."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.public_expand import (
    LEAF_ID,
    _repo_relative,
    _write_cohort_bundle,
    _write_cohort_metric_file,
    build_report_from_fixtures,
    classify_local_pdf_intake,
    fields_from_text,
    is_forbidden_source,
    is_synthetic_row,
    is_toc_page,
    load_joe_local_pdf_intake,
    looks_like_pii,
    ocr_lines_into_cell_grid,
    prepare_expanded_cer,
    redact_text,
    score_bundle,
    segment_toc_lines,
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


def test_toc_segmentation_keeps_the_page_and_drops_dot_leaders():
    text = "1\n目\n录\n第一章\n招标公告..............2\n第二章\n采购需求..............5"
    assert is_toc_page(text)
    assert not is_toc_page("采购人：右江民族医学院附属医院\n项目编号：ABC-1")
    segmented = segment_toc_lines([line for line in text.splitlines() if line.strip()])
    assert "目录" in segmented
    assert "第一章招标公告2" in segmented
    assert "第二章采购需求5" in segmented
    assert all("..." not in line for line in segmented)
    hyp = segment_toc_lines(["第一章招标公告", "2", "第二章采购需求", "5"])
    assert hyp == ["第一章招标公告2", "第二章采购需求5"]


def test_ruling_grid_joins_multiline_cells_and_splits_a_wide_header():
    grid = [[(0.0, 0.0, 10.0, 10.0), (10.0, 0.0, 20.0, 10.0)]]
    html = ocr_lines_into_cell_grid(
        [{"text": "数量单位", "bbox": (0.0, 0.0, 20.0, 10.0)}],
        grid,
        1.0,
    )
    assert "数量" in html and "单位" in html
    assert html.count("<th>") == 2
    body = [[(0.0, 0.0, 30.0, 40.0)]]
    joined = ocr_lines_into_cell_grid(
        [
            {"text": "手术动力", "bbox": (1.0, 2.0, 20.0, 12.0)},
            {"text": "装置", "bbox": (1.0, 16.0, 16.0, 28.0)},
        ],
        body,
        1.0,
    )
    assert "手术动力装置" in joined
    assert joined.count("<th>") == 1


def test_toc_prepare_does_not_drop_pages():
    gt = [
        {"doc_id": "a", "page": 1, "text_gt": "目\n录\n第一章\n招标公告..........2"},
        {"doc_id": "b", "page": 2, "text_gt": "采购人：医院\n预算金额：10万元"},
    ]
    hyp = [
        {"doc_id": "a", "page": 1, "lines_hyp": ["目录", "第一章招标公告", "2"], "text_hyp": "x"},
        {"doc_id": "b", "page": 2, "lines_hyp": ["采购人：医院", "预算金额：10万元"], "text_hyp": "y"},
    ]
    prepared_gt, prepared_hyp = prepare_expanded_cer(gt, hyp)
    assert [(row["doc_id"], row["page"]) for row in prepared_gt] == [("a", 1), ("b", 2)]
    assert len(prepared_hyp) == 2
    assert "...." not in prepared_gt[0]["text_gt"]
    assert prepared_gt[1]["text_gt"].startswith("采购人")


def test_unlisted_pdf_without_a_public_url_is_provenance_unverified():
    classified = classify_local_pdf_intake(
        [{"filename": "unknown-tender.pdf", "sha256": "ab" * 32}],
        {"documents": []},
        scored_pages={},
    )
    assert classified["counts"]["provenance_unverified"] == 1
    assert classified["counts"]["newly_added_scored"] == 0
    assert classified["provenance_unverified"][0]["counts_as_new_document"] is False


def test_joe_local_pdfs_match_existing_manifest_and_are_not_recounted():
    intake = load_joe_local_pdf_intake()
    assert intake["counts"] == {
        "duplicate": 12,
        "newly_added_scored": 0,
        "newly_added_not_scored": 0,
        "provenance_unverified": 0,
    }
    seen = set()
    for row in intake["duplicate"]:
        assert row["counts_as_new_document"] is False
        assert row["matched_by"]
        assert row["matched_document_id"]
        assert str(row["source_url"]).startswith("http")
        assert row["fetched_at"]
        assert row["license_or_usage_note"]
        seen.add(row["filename"])
    assert seen == {
        "pub-gx-daxin-ultrasound-anesthesia.pdf",
        "pub-gx-guiping-hospital-it.pdf",
        "pub-gx-luocheng-smart-hospital.pdf",
        "pub-gx-nanning-vascular-doppler.pdf",
        "pub-gx-niv-sleep-monitor.pdf",
        "pub-gx-qintang-flow-cytometer.pdf",
        "pub-gx-ventilator-monitors.pdf",
        "pub-gx-youjiang-ultrasound.pdf",
        "pub-gx-yulin-dermatology-his.pdf",
        "source2-nanjing.pdf",
        "source2-shaanxi.pdf",
        "source4-zbtb.pdf",
    }


def test_missing_cer_is_not_written_as_zero(tmp_path: Path):
    _write_cohort_metric_file(
        tmp_path,
        stem="line-cer-report",
        metric="line_cer",
        value=None,
        gate="GATE_PASS",
        cohort="old",
        report_version="missing-cer",
        report_hash="abc123456789",
        generated_at="2026-10-08T00:00:00+00:00",
    )
    text = (tmp_path / "line-cer-report.json").read_text(encoding="utf-8")
    body = json.loads(text)
    assert body["line_cer"] is None
    assert body["gate"] == "GATE_FAIL"
    assert body["product_pass"] is False
    assert body["forced_requirement_status"] == "NEEDS_REVIEW"
    assert '"line_cer": 0' not in text
    assert '"line_cer": 0.0' not in text

    _write_cohort_metric_file(
        tmp_path,
        stem="line-cer-nan",
        metric="line_cer",
        value=float("nan"),
        gate="GATE_PASS",
        cohort="old",
        report_version="missing-cer",
        report_hash="abc123456789",
        generated_at="2026-10-08T00:00:00+00:00",
    )
    nan_text = (tmp_path / "line-cer-nan.json").read_text(encoding="utf-8")
    nan_body = json.loads(nan_text)
    assert nan_body["line_cer"] is None
    assert nan_body["gate"] == "GATE_FAIL"
    assert '"line_cer": 0.0' not in nan_text

    # A real perfect score is still stored as 0.0 and can pass the CER gate.
    _write_cohort_metric_file(
        tmp_path,
        stem="line-cer-perfect",
        metric="line_cer",
        value=0.0,
        gate="GATE_PASS",
        cohort="old",
        report_version="missing-cer",
        report_hash="abc123456789",
        generated_at="2026-10-08T00:00:00+00:00",
    )
    perfect = json.loads((tmp_path / "line-cer-perfect.json").read_text(encoding="utf-8"))
    assert perfect["line_cer"] == 0.0
    assert perfect["gate"] == "GATE_PASS"
    assert perfect["product_pass"] is False


def test_cohort_paths_are_repo_relative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from work.eval import public_expand

    monkeypatch.setattr(public_expand, "ROOT", tmp_path)
    monkeypatch.setattr(public_expand, "COHORT_ROOT", tmp_path / "outputs" / "ocr-benchmark" / "cohorts")
    metrics = {
        "line_cer": 0.05,
        "line_cer_gate": "GATE_FAIL",
        "key_field_f1": 0.5,
        "key_field_f1_gate": "GATE_FAIL",
        "teds": 0.5,
        "teds_gate": "GATE_FAIL",
    }
    meta = _write_cohort_bundle(
        {"generated_at": "2026-10-08T00:00:00+00:00"},
        cohort="old",
        metrics=metrics,
        report_version="vtest",
    )
    assert meta["path"] == "outputs/ocr-benchmark/cohorts/old/vtest"
    assert not Path(meta["path"]).is_absolute()
    assert "/workspace" not in meta["path"]
    assert (tmp_path / meta["path"]).is_dir()
    assert _repo_relative(tmp_path / "outputs" / "ocr-benchmark" / "cohorts" / "old" / "vtest") == meta["path"]


def test_committed_public_expand_report_has_no_workspace_absolute_paths():
    report_path = ROOT / "outputs" / "ocr-benchmark" / "public-expand-report.json"
    text = report_path.read_text(encoding="utf-8")
    assert "/workspace" not in text
    report = json.loads(text)
    for cohort, path in report["cohort_paths"].items():
        assert not Path(path).is_absolute()
        assert ".." not in Path(path).parts
        assert (ROOT / path).is_dir(), cohort
    assert report["product_pass"] is False
    assert report["forced_requirement_status"] == "NEEDS_REVIEW"


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
    assert report["expanded"]["line_cer_pages"] == 54
    assert report["expanded"]["teds_pages_scored"] == 19
    assert report["old_set"]["line_cer"] == pytest.approx(0.031746031746031744)
    assert report["old_set"]["key_field_f1"] == pytest.approx(0.76)
    assert report["old_set"]["teds"] == pytest.approx(0.8784546114752891, rel=1e-6)
    rebuilt = build_report_from_fixtures()
    assert rebuilt["joe_local_pdf_intake"]["counts"]["duplicate"] == 12
    assert rebuilt["joe_local_pdf_intake"]["counts"]["newly_added_scored"] == 0
    assert rebuilt["expanded"]["line_cer"] == pytest.approx(report["expanded"]["line_cer"])
    assert rebuilt["expanded"]["key_field_f1"] == pytest.approx(report["expanded"]["key_field_f1"])
    assert rebuilt["expanded"]["teds"] == pytest.approx(report["expanded"]["teds"])
    for row in report["sources"]:
        if row.get("scored"):
            assert row.get("source_url")
            assert row.get("fetched_at")
            assert row.get("license_or_usage_note")
