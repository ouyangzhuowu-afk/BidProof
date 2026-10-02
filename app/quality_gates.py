"""Product-facing OCR engineering gate snapshot (S-A-08 / S-A-06 wiring).

Reads committed sandbox reports under ``outputs/ocr-benchmark/`` when present.
Fail-closed: every required cohort (old + expanded) must independently pass
CER/F1/TEDS. Missing or failing any required cohort keeps
``forced_requirement_status=NEEDS_REVIEW``. Never claims product PASS.
Does not write ledgers. Does not average / pick-best / latest-only across cohorts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from work.eval.sandbox_gates import (
    REQUIRED_COHORTS,
    aggregate_cohort_gates,
    aggregate_engineering_gates,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "outputs" / "ocr-benchmark"
COHORT_DIRNAME = "cohorts"
CURRENT_POINTER = "CURRENT"
MANIFEST_NAME = "cohort-manifest.json"
METRIC_FILES = {
    "line_cer": "line-cer-report.json",
    "teds": "teds-report.json",
    "key_field_f1": "key-field-f1-report.json",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _metric_from_report(report: dict[str, Any] | None, key: str) -> Any:
    if report is None:
        return None
    if key not in report:
        return None
    return report[key]


def _source_from_report(report: dict[str, Any] | None) -> str | None:
    if report is None:
        return None
    for key in ("cohort", "source", "metric_source", "hypothesis_source"):
        value = report.get(key)
        if value:
            return str(value)
    return None


def _cohort_dir(base: Path, cohort: str, version: str | None = None) -> Path:
    root = base / COHORT_DIRNAME / cohort
    if version:
        return root / version
    pointer = root / CURRENT_POINTER
    if pointer.is_file():
        target = pointer.read_text(encoding="utf-8").strip()
        if target:
            candidate = root / target
            if candidate.is_dir():
                return candidate
    # Fall back to a literal "current" directory if present.
    current = root / "current"
    if current.is_dir():
        return current
    return root


def _load_cohort_manifest(cohort_path: Path) -> dict[str, Any]:
    manifest = _read_json(cohort_path / MANIFEST_NAME) or {}
    return manifest if isinstance(manifest, dict) else {}


def _cohort_snapshot(
    base: Path,
    cohort: str,
    *,
    version: str | None = None,
) -> dict[str, Any] | None:
    cohort_path = _cohort_dir(base, cohort, version=version)
    if not cohort_path.is_dir():
        return None

    line_report = _read_json(cohort_path / METRIC_FILES["line_cer"])
    teds_report = _read_json(cohort_path / METRIC_FILES["teds"])
    key_report = _read_json(cohort_path / METRIC_FILES["key_field_f1"])
    if line_report is None and teds_report is None and key_report is None:
        return None

    line_status = "EVALUATED" if line_report is not None and "line_cer" in line_report else "NOT_EVALUATED"
    teds_status = "EVALUATED" if teds_report is not None and "teds" in teds_report else "NOT_EVALUATED"
    key_status = "EVALUATED" if key_report is not None and "key_field_f1" in key_report else "NOT_EVALUATED"

    sources = {
        "line_cer": _source_from_report(line_report),
        "teds": _source_from_report(teds_report),
        "key_field_f1": _source_from_report(key_report),
    }
    # Consistent sources: all present metric reports for a cohort must share one source label.
    present_sources = {name: value for name, value in sources.items() if value}
    expected_source = next(iter(present_sources.values()), cohort)
    inconsistent = any(value != expected_source for value in present_sources.values())

    aggregate = aggregate_engineering_gates(
        line_cer=_metric_from_report(line_report, "line_cer"),
        key_field_f1=_metric_from_report(key_report, "key_field_f1"),
        teds=_metric_from_report(teds_report, "teds"),
        line_cer_status=line_status,
        key_field_f1_status=key_status,
        teds_status=teds_status,
        source=None if inconsistent else expected_source,
        expected_source=expected_source,
    )
    manifest = _load_cohort_manifest(cohort_path)
    report_version = str(manifest.get("report_version") or cohort_path.name)
    report_hash = str(manifest.get("report_hash") or "")
    if not report_hash:
        report_hash = _hash_cohort_metrics(aggregate)
    aggregate["cohort"] = cohort
    aggregate["report_version"] = report_version
    aggregate["report_hash"] = report_hash
    aggregate["cohort_path"] = str(cohort_path.relative_to(base)) if base in cohort_path.parents or cohort_path == base else str(cohort_path)
    aggregate["sources"] = {
        "line_cer_report": bool(line_report),
        "teds_report": bool(teds_report),
        "key_field_f1_report": bool(key_report),
        "metric_sources": sources,
    }
    return aggregate


def _hash_cohort_metrics(aggregate: dict[str, Any]) -> str:
    payload = {
        "line_cer": aggregate.get("line_cer"),
        "key_field_f1": aggregate.get("key_field_f1"),
        "teds": aggregate.get("teds"),
        "engineering_gate": aggregate.get("engineering_gate"),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _legacy_flat_snapshot(base: Path) -> dict[str, Any]:
    """Legacy flat reports only count as a single unknown cohort → overall FAIL.

    Kept so accidental average/latest-only reading of the overwritten top-level
    files cannot mint an OCR GATE_PASS when cohorts are missing.
    """
    line_report = _read_json(base / METRIC_FILES["line_cer"])
    teds_report = _read_json(base / METRIC_FILES["teds"])
    key_report = _read_json(base / METRIC_FILES["key_field_f1"])
    aggregate = aggregate_engineering_gates(
        line_cer=_metric_from_report(line_report, "line_cer"),
        key_field_f1=_metric_from_report(key_report, "key_field_f1"),
        teds=_metric_from_report(teds_report, "teds"),
        line_cer_status="EVALUATED" if line_report is not None and "line_cer" in line_report else "NOT_EVALUATED",
        key_field_f1_status="EVALUATED" if key_report is not None and "key_field_f1" in key_report else "NOT_EVALUATED",
        teds_status="EVALUATED" if teds_report is not None and "teds" in teds_report else "NOT_EVALUATED",
        source="legacy_flat",
        expected_source="legacy_flat",
    )
    aggregate["cohort"] = "legacy_flat"
    aggregate["report_version"] = "legacy_flat"
    aggregate["report_hash"] = _hash_cohort_metrics(aggregate)
    aggregate["sources"] = {
        "line_cer_report": bool(line_report),
        "teds_report": bool(teds_report),
        "key_field_f1_report": bool(key_report),
    }
    return aggregate


def engineering_gate_snapshot(report_dir: Path | None = None) -> dict[str, Any]:
    base = Path(report_dir) if report_dir is not None else REPORT_DIR
    cohorts: dict[str, dict[str, Any] | None] = {}
    for name in REQUIRED_COHORTS:
        cohorts[name] = _cohort_snapshot(base, name)

    if any(cohorts.values()):
        combined = aggregate_cohort_gates(cohorts)
    else:
        # No cohort dirs: fail-closed. Legacy flat files alone cannot satisfy required cohorts.
        legacy = _legacy_flat_snapshot(base)
        combined = aggregate_cohort_gates({"old": None, "expanded": None, "legacy_flat": legacy})
        combined["legacy_flat"] = legacy

    versions = {
        name: (payload or {}).get("report_version")
        for name, payload in (combined.get("cohorts") or {}).items()
    }
    hashes = {
        name: (payload or {}).get("report_hash")
        for name, payload in (combined.get("cohorts") or {}).items()
    }
    combined["report_version"] = versions
    combined["report_hash"] = hashes
    combined["failures"] = list(combined.get("failing_cohorts") or [])
    combined["unevaluated"] = list(combined.get("missing_cohorts") or [])
    # Surface any per-cohort metric failures for callers that inspect the flat keys.
    metric_failures: list[str] = []
    for name, payload in (combined.get("cohorts") or {}).items():
        for item in payload.get("failures") or []:
            metric_failures.append(f"{name}:{item}")
    combined["metric_failures"] = metric_failures
    return combined


def allow_machine_pass(report_dir: Path | None = None) -> bool:
    """Engineering OCR gate only. Still false when any required cohort fails/missing.

    Callers must not treat this as product PASS: snapshot always has product_pass=false.
    """
    snapshot = engineering_gate_snapshot(report_dir)
    return (
        snapshot["engineering_gate"] == "GATE_PASS"
        and not snapshot.get("unevaluated")
        and not snapshot.get("failures")
        and not snapshot.get("missing_cohorts")
        and not snapshot.get("failing_cohorts")
    )
