"""Product OCR engineering gate snapshot wiring."""

from __future__ import annotations

import json
from pathlib import Path

from app import quality_gates
from app.presenters import quality_for_run, scan_quality


def _seed_failing_cohorts(tmp_path: Path) -> None:
    for cohort, metrics in (
        ("old", {"line_cer": 0.0317, "key_field_f1": 0.76, "teds": 0.87}),
        ("expanded", {"line_cer": 0.0496, "key_field_f1": 0.9717, "teds": 0.958}),
    ):
        version = "test"
        cohort_dir = tmp_path / "cohorts" / cohort / version
        cohort_dir.mkdir(parents=True)
        (cohort_dir / "line-cer-report.json").write_text(
            json.dumps({"line_cer": metrics["line_cer"], "cohort": cohort, "source": cohort}),
            encoding="utf-8",
        )
        (cohort_dir / "teds-report.json").write_text(
            json.dumps({"teds": metrics["teds"], "cohort": cohort, "source": cohort}),
            encoding="utf-8",
        )
        (cohort_dir / "key-field-f1-report.json").write_text(
            json.dumps({"key_field_f1": metrics["key_field_f1"], "cohort": cohort, "source": cohort}),
            encoding="utf-8",
        )
        (cohort_dir / "cohort-manifest.json").write_text(
            json.dumps({"cohort": cohort, "report_version": version, "report_hash": f"h-{cohort}"}),
            encoding="utf-8",
        )
        (tmp_path / "cohorts" / cohort / "CURRENT").write_text(version + "\n", encoding="utf-8")


def test_engineering_gate_snapshot_reads_reports(tmp_path: Path):
    _seed_failing_cohorts(tmp_path)
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert "old" in snap["failing_cohorts"]
    assert "expanded" in snap["failing_cohorts"]
    assert "line_cer" in snap["cohorts"]["old"]["failures"]
    assert "teds" in snap["cohorts"]["old"]["failures"]
    assert snap["forced_requirement_status"] == "NEEDS_REVIEW"
    assert quality_gates.allow_machine_pass(tmp_path) is False


def test_scan_quality_embeds_ocr_engineering_gates():
    quality = scan_quality(
        [{"page": 1, "has_text": True, "ocr_required": False, "ocr_status": "NOT_REQUIRED", "low_text_confidence": False}],
        [],
    )
    assert "ocr_engineering_gates" in quality
    assert quality["ocr_engineering_gates"]["forced_requirement_status"] == "NEEDS_REVIEW"
    assert "NEEDS_REVIEW" in quality["interpretation"]
    assert "ocr_report_version" in quality
    assert "ocr_report_hash" in quality


def test_quality_for_run_always_attaches_gates():
    quality = quality_for_run({"state": {}, "source_documents": [{"pages": 2}]})
    assert quality["ocr_engineering_gates"]["product_pass"] is False
    assert quality["ocr_engineering_gates"]["claim_scope"] == "engineering_gate_only"
    assert "ocr_report_version" in quality
    assert "ocr_report_hash" in quality
