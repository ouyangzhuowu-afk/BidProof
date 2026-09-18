"""Product OCR engineering gate snapshot wiring."""

from __future__ import annotations

import json
from pathlib import Path

from app import quality_gates
from app.presenters import quality_for_run, scan_quality


def test_engineering_gate_snapshot_reads_reports(tmp_path: Path):
    (tmp_path / "line-cer-report.json").write_text(
        json.dumps({"line_cer": 0.0317, "gate": "GATE_FAIL", "product_pass": False}),
        encoding="utf-8",
    )
    (tmp_path / "teds-report.json").write_text(
        json.dumps({"teds": 0.87, "gate": "GATE_FAIL", "product_pass": False}),
        encoding="utf-8",
    )
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert "line_cer" in snap["failures"]
    assert "teds" in snap["failures"]
    assert "key_field_f1" in snap["unevaluated"]
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


def test_quality_for_run_always_attaches_gates():
    quality = quality_for_run({"state": {}, "source_documents": [{"pages": 2}]})
    assert quality["ocr_engineering_gates"]["product_pass"] is False
    assert quality["ocr_engineering_gates"]["claim_scope"] == "engineering_gate_only"
