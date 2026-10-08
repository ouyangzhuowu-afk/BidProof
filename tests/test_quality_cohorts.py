"""Old vs expanded cohort OCR gates must not mint a wrong PASS."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest

from app import quality_gates
from app.presenters import quality_for_run, scan_quality
from work.eval.sandbox_gates import (
    aggregate_cohort_gates,
    aggregate_engineering_gates,
    validate_line_cer,
    validate_unit_interval,
)


def _write_cohort(
    root: Path,
    cohort: str,
    *,
    line_cer: float,
    key_field_f1: float,
    teds: float,
    version: str = "v1",
    source: str | None = None,
) -> dict[str, str]:
    cohort_dir = root / "cohorts" / cohort / version
    cohort_dir.mkdir(parents=True, exist_ok=True)
    src = source or cohort
    metrics = {
        "line_cer": line_cer,
        "key_field_f1": key_field_f1,
        "teds": teds,
    }
    report_hash = "hash-" + cohort + "-" + version
    for stem, key in (
        ("line-cer-report", "line_cer"),
        ("key-field-f1-report", "key_field_f1"),
        ("teds-report", "teds"),
    ):
        (cohort_dir / f"{stem}.json").write_text(
            json.dumps(
                {
                    key: metrics[key],
                    "gate": "GATE_PASS",
                    "cohort": src,
                    "source": src,
                    "report_version": version,
                    "report_hash": report_hash,
                    "product_pass": False,
                }
            ),
            encoding="utf-8",
        )
    (cohort_dir / "cohort-manifest.json").write_text(
        json.dumps(
            {
                "cohort": cohort,
                "report_version": version,
                "report_hash": report_hash,
                "product_pass": False,
            }
        ),
        encoding="utf-8",
    )
    (root / "cohorts" / cohort / "CURRENT").write_text(version + "\n", encoding="utf-8")
    return {"report_version": version, "report_hash": report_hash}


def test_expanded_pass_old_fail_overall_fail(tmp_path: Path):
    _write_cohort(tmp_path, "old", line_cer=0.0317, key_field_f1=0.76, teds=0.8785)
    _write_cohort(tmp_path, "expanded", line_cer=0.01, key_field_f1=0.99, teds=0.96)
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["cohorts"]["expanded"]["engineering_gate"] == "GATE_PASS"
    assert snap["cohorts"]["old"]["engineering_gate"] == "GATE_FAIL"
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert "old" in snap["failing_cohorts"]
    assert snap["product_pass"] is False
    assert quality_gates.allow_machine_pass(tmp_path) is False


def test_missing_old_cohort_overall_fail(tmp_path: Path):
    _write_cohort(tmp_path, "expanded", line_cer=0.01, key_field_f1=0.99, teds=0.96)
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert "old" in snap["missing_cohorts"]
    assert snap["product_pass"] is False


def test_both_cohorts_pass_ocr_gate_but_product_pass_false(tmp_path: Path):
    old_meta = _write_cohort(tmp_path, "old", line_cer=0.01, key_field_f1=0.99, teds=0.96, version="old-v1")
    exp_meta = _write_cohort(
        tmp_path, "expanded", line_cer=0.01, key_field_f1=0.99, teds=0.96, version="exp-v1"
    )
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_PASS"
    assert snap["product_pass"] is False
    assert snap["forced_requirement_status"] == "NEEDS_REVIEW"
    assert snap["report_version"]["old"] == old_meta["report_version"]
    assert snap["report_version"]["expanded"] == exp_meta["report_version"]
    assert snap["report_hash"]["old"] == old_meta["report_hash"]
    assert snap["report_hash"]["expanded"] == exp_meta["report_hash"]
    # OCR engineering allow may be true, but product_pass stays false on the snapshot.
    assert quality_gates.allow_machine_pass(tmp_path) is True
    assert snap["product_pass"] is False


def test_nan_inf_invalid_metrics_fail():
    for bad in (math.nan, math.inf, -math.inf, "NaN", "inf", "not-a-number"):
        report = aggregate_engineering_gates(line_cer=bad, key_field_f1=0.99, teds=0.95)
        assert report["engineering_gate"] == "GATE_FAIL"
        assert "invalid_line_cer" in report["failures"]
        assert report["product_pass"] is False

    for bad in (math.nan, 1.5, -0.1, "unknown"):
        report = aggregate_engineering_gates(line_cer=0.01, key_field_f1=bad, teds=0.95)
        assert report["engineering_gate"] == "GATE_FAIL"
        assert any(item.startswith("invalid_key_field_f1") for item in report["failures"])

    # CER may exceed 1.0; that is a threshold fail, not an invalid-range reject.
    value, error = validate_line_cer(1.25)
    assert error is None
    assert value == pytest.approx(1.25)
    report = aggregate_engineering_gates(line_cer=1.25, key_field_f1=0.99, teds=0.95)
    assert report["engineering_gate"] == "GATE_FAIL"
    assert "line_cer" in report["failures"]
    assert "invalid_line_cer" not in report["failures"]

    value, error = validate_unit_interval(1.01, name="teds")
    assert value is None
    assert error == "invalid_teds"


def test_inconsistent_sources_fail(tmp_path: Path):
    version = "mixed"
    cohort_dir = tmp_path / "cohorts" / "old" / version
    cohort_dir.mkdir(parents=True)
    (cohort_dir / "line-cer-report.json").write_text(
        json.dumps({"line_cer": 0.01, "cohort": "old", "source": "old", "product_pass": False}),
        encoding="utf-8",
    )
    (cohort_dir / "key-field-f1-report.json").write_text(
        json.dumps({"key_field_f1": 0.99, "cohort": "expanded", "source": "expanded", "product_pass": False}),
        encoding="utf-8",
    )
    (cohort_dir / "teds-report.json").write_text(
        json.dumps({"teds": 0.95, "cohort": "old", "source": "old", "product_pass": False}),
        encoding="utf-8",
    )
    (cohort_dir / "cohort-manifest.json").write_text(
        json.dumps({"cohort": "old", "report_version": version, "report_hash": "x"}),
        encoding="utf-8",
    )
    (tmp_path / "cohorts" / "old" / "CURRENT").write_text(version + "\n", encoding="utf-8")
    _write_cohort(tmp_path, "expanded", line_cer=0.01, key_field_f1=0.99, teds=0.95)
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert "inconsistent_source" in snap["cohorts"]["old"]["failures"]


def test_legacy_flat_reports_alone_cannot_pass(tmp_path: Path):
    # Even perfect flat top-level reports are not enough without required cohort dirs.
    (tmp_path / "line-cer-report.json").write_text(json.dumps({"line_cer": 0.01}), encoding="utf-8")
    (tmp_path / "key-field-f1-report.json").write_text(json.dumps({"key_field_f1": 0.99}), encoding="utf-8")
    (tmp_path / "teds-report.json").write_text(json.dumps({"teds": 0.95}), encoding="utf-8")
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert "old" in snap["missing_cohorts"]
    assert "expanded" in snap["missing_cohorts"]
    assert snap["product_pass"] is False


def test_aggregate_cohort_gates_no_average_or_best():
    old = aggregate_engineering_gates(line_cer=0.05, key_field_f1=0.5, teds=0.5)
    expanded = aggregate_engineering_gates(line_cer=0.01, key_field_f1=0.99, teds=0.96)
    combined = aggregate_cohort_gates({"old": old, "expanded": expanded})
    assert combined["engineering_gate"] == "GATE_FAIL"
    assert combined["product_pass"] is False
    assert "old" in combined["failing_cohorts"]


def test_presenters_bind_report_version_and_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _write_cohort(tmp_path, "old", line_cer=0.0317, key_field_f1=0.76, teds=0.87, version="bind-old")
    _write_cohort(tmp_path, "expanded", line_cer=0.01, key_field_f1=0.99, teds=0.95, version="bind-exp")
    monkeypatch.setattr(quality_gates, "REPORT_DIR", tmp_path)
    quality = scan_quality(
        [{"page": 1, "has_text": True, "ocr_required": False, "ocr_status": "NOT_REQUIRED", "low_text_confidence": False}],
        [],
    )
    assert quality["ocr_report_version"]["old"] == "bind-old"
    assert quality["ocr_report_version"]["expanded"] == "bind-exp"
    assert quality["ocr_report_hash"]["old"]
    assert quality["ocr_report_hash"]["expanded"]
    assert quality["ocr_engineering_gates"]["product_pass"] is False

    run_quality = quality_for_run({"state": {}, "source_documents": [{"pages": 2}]})
    assert run_quality["ocr_report_version"]["old"] == "bind-old"
    assert run_quality["ocr_report_hash"]["expanded"]


def _write_metric_file(directory: Path, stem: str, key: str, value: object, cohort: str, version: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stem}.json").write_text(
        json.dumps(
            {
                key: value,
                "gate": "GATE_PASS",
                "cohort": cohort,
                "source": cohort,
                "report_version": version,
                "product_pass": False,
            },
            allow_nan=True,
        ),
        encoding="utf-8",
    )


def test_all_null_metrics_do_not_pass(tmp_path: Path):
    version = "all-null"
    for cohort in ("old", "expanded"):
        cohort_dir = tmp_path / "cohorts" / cohort / version
        _write_metric_file(cohort_dir, "line-cer-report", "line_cer", None, cohort, version)
        _write_metric_file(cohort_dir, "key-field-f1-report", "key_field_f1", None, cohort, version)
        _write_metric_file(cohort_dir, "teds-report", "teds", None, cohort, version)
        (cohort_dir / "cohort-manifest.json").write_text(
            json.dumps({"cohort": cohort, "report_version": version, "report_hash": "nulls", "product_pass": False}),
            encoding="utf-8",
        )
        (tmp_path / "cohorts" / cohort / "CURRENT").write_text(version + "\n", encoding="utf-8")
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert snap["product_pass"] is False
    assert snap["forced_requirement_status"] == "NEEDS_REVIEW"
    assert snap["cohorts"]["old"]["engineering_gate"] == "GATE_FAIL"
    assert snap["cohorts"]["expanded"]["engineering_gate"] == "GATE_FAIL"
    assert "line_cer" in snap["cohorts"]["old"]["unevaluated"]
    assert quality_gates.allow_machine_pass(tmp_path) is False


def test_nan_and_missing_metrics_do_not_pass(tmp_path: Path):
    old_dir = tmp_path / "cohorts" / "old" / "nan-v"
    _write_metric_file(old_dir, "line-cer-report", "line_cer", float("nan"), "old", "nan-v")
    _write_metric_file(old_dir, "key-field-f1-report", "key_field_f1", 0.99, "old", "nan-v")
    _write_metric_file(old_dir, "teds-report", "teds", 0.95, "old", "nan-v")
    (old_dir / "cohort-manifest.json").write_text(
        json.dumps({"cohort": "old", "report_version": "nan-v", "report_hash": "nan", "product_pass": False}),
        encoding="utf-8",
    )
    (tmp_path / "cohorts" / "old" / "CURRENT").write_text("nan-v\n", encoding="utf-8")

    exp_dir = tmp_path / "cohorts" / "expanded" / "miss-v"
    # File exists but the CER key is absent. Other metrics would pass on their own.
    (exp_dir).mkdir(parents=True)
    (exp_dir / "line-cer-report.json").write_text(
        json.dumps({"gate": "GATE_PASS", "cohort": "expanded", "source": "expanded", "product_pass": False}),
        encoding="utf-8",
    )
    _write_metric_file(exp_dir, "key-field-f1-report", "key_field_f1", 0.99, "expanded", "miss-v")
    _write_metric_file(exp_dir, "teds-report", "teds", 0.95, "expanded", "miss-v")
    (exp_dir / "cohort-manifest.json").write_text(
        json.dumps({"cohort": "expanded", "report_version": "miss-v", "report_hash": "miss", "product_pass": False}),
        encoding="utf-8",
    )
    (tmp_path / "cohorts" / "expanded" / "CURRENT").write_text("miss-v\n", encoding="utf-8")

    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert snap["cohorts"]["old"]["engineering_gate"] == "GATE_FAIL"
    assert snap["cohorts"]["expanded"]["engineering_gate"] == "GATE_FAIL"
    assert "line_cer" in snap["cohorts"]["old"]["unevaluated"]
    assert "line_cer" in snap["cohorts"]["expanded"]["unevaluated"]
    assert snap["cohorts"]["old"]["line_cer"] is None
    assert snap["cohorts"]["expanded"]["line_cer"] is None
    assert snap["product_pass"] is False
    assert quality_gates.allow_machine_pass(tmp_path) is False


def test_legacy_missing_cer_is_not_zero_and_does_not_pass(tmp_path: Path):
    # Legacy flat file: key present, value null. Must not be read as 0.0 (which would pass ≤ 2%).
    (tmp_path / "line-cer-report.json").write_text(
        json.dumps({"line_cer": None, "gate": "GATE_PASS", "product_pass": False}),
        encoding="utf-8",
    )
    (tmp_path / "key-field-f1-report.json").write_text(
        json.dumps({"key_field_f1": 0.99, "product_pass": False}),
        encoding="utf-8",
    )
    (tmp_path / "teds-report.json").write_text(
        json.dumps({"teds": 0.95, "product_pass": False}),
        encoding="utf-8",
    )
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    legacy = snap["legacy_flat"]
    assert legacy["line_cer"] is None
    assert legacy["line_cer"] != 0.0
    assert "line_cer" in legacy["unevaluated"]
    assert legacy["engineering_gate"] == "GATE_FAIL"
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert snap["product_pass"] is False
    assert legacy["forced_requirement_status"] == "NEEDS_REVIEW"


def test_current_pointer_outside_cohort_does_not_pass(tmp_path: Path):
    _write_cohort(tmp_path, "expanded", line_cer=0.01, key_field_f1=0.99, teds=0.96, version="exp-v1")
    _write_cohort(tmp_path, "old", line_cer=0.05, key_field_f1=0.5, teds=0.5, version="old-v1")
    # Point old's CURRENT at the passing expanded cohort. Must not be followed.
    (tmp_path / "cohorts" / "old" / "CURRENT").write_text("../expanded/exp-v1\n", encoding="utf-8")
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert snap["cohorts"]["old"]["engineering_gate"] == "GATE_FAIL"
    assert "current_pointer_outside_cohort" in snap["cohorts"]["old"]["failures"]
    assert snap["product_pass"] is False
    assert quality_gates.allow_machine_pass(tmp_path) is False

    # Absolute path that resolves in the other cohort is the same rejection.
    escaped = (tmp_path / "cohorts" / "expanded" / "exp-v1").resolve().as_posix()
    (tmp_path / "cohorts" / "old" / "CURRENT").write_text(escaped + "\n", encoding="utf-8")
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert "current_pointer_outside_cohort" in snap["cohorts"]["old"]["failures"]
    assert snap["product_pass"] is False


def test_copied_expanded_report_into_old_does_not_pass(tmp_path: Path):
    _write_cohort(tmp_path, "expanded", line_cer=0.01, key_field_f1=0.99, teds=0.96, version="exp-v1")
    source = tmp_path / "cohorts" / "expanded" / "exp-v1"
    dest = tmp_path / "cohorts" / "old" / "exp-v1"
    shutil.copytree(source, dest)
    (tmp_path / "cohorts" / "old" / "CURRENT").write_text("exp-v1\n", encoding="utf-8")
    snap = quality_gates.engineering_gate_snapshot(tmp_path)
    assert snap["engineering_gate"] == "GATE_FAIL"
    assert snap["cohorts"]["old"]["engineering_gate"] == "GATE_FAIL"
    assert "inconsistent_source" in snap["cohorts"]["old"]["failures"]
    assert snap["cohorts"]["expanded"]["engineering_gate"] == "GATE_PASS"
    assert snap["product_pass"] is False
    assert snap["forced_requirement_status"] == "NEEDS_REVIEW"
    assert quality_gates.allow_machine_pass(tmp_path) is False
