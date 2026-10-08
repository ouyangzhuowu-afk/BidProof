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
from pathlib import Path, PurePosixPath
from typing import Any

from work.eval.sandbox_gates import (
    REQUIRED_COHORTS,
    aggregate_cohort_gates,
    aggregate_engineering_gates,
    is_measured_number,
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
PROVENANCE_KEYS = ("cohort", "source", "metric_source", "hypothesis_source")
_POINTER_REJECTED = object()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _metric_from_report(report: dict[str, Any] | None, key: str) -> Any:
    """Return a measured metric, or None. Never coerce null / NaN / missing to 0.0."""
    if report is None or key not in report:
        return None
    value = report[key]
    if not is_measured_number(value):
        return None
    return value


def _metric_status(report: dict[str, Any] | None, key: str) -> str:
    """Null, NaN, and a missing key are not evaluated."""
    if report is None or key not in report or not is_measured_number(report[key]):
        return "NOT_EVALUATED"
    return "EVALUATED"


def _provenance_labels(report: dict[str, Any] | None) -> list[str]:
    if report is None:
        return []
    labels: list[str] = []
    for key in PROVENANCE_KEYS:
        value = report.get(key)
        if value:
            labels.append(str(value))
    return labels


def _provenance_matches_cohort(report: dict[str, Any] | None, cohort: str) -> bool:
    """A present report must name this cohort. A copied foreign bundle does not match."""
    if report is None:
        return True
    labels = _provenance_labels(report)
    if not labels:
        return False
    return all(label == cohort for label in labels)


def _contained_child(root: Path, target: str) -> Path | None:
    """Resolve CURRENT only to a directory strictly inside ``root``.

    Rejects ``..``, and any absolute or relative path that resolves outside
    the cohort directory (including symlink escapes).
    """
    text = target.strip().lstrip("\ufeff")
    if not text or any(ch in text for ch in "\n\r\x00"):
        return None
    normalized = text.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if ".." in pure.parts:
        return None
    root_resolved = root.resolve()
    if pure.is_absolute():
        candidate = Path(normalized).resolve()
    else:
        candidate = (root_resolved / pure).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    if candidate == root_resolved or not candidate.is_dir():
        return None
    return candidate


def _cohort_dir(base: Path, cohort: str, version: str | None = None) -> Path | object:
    root = base / COHORT_DIRNAME / cohort
    if version:
        contained = _contained_child(root, version)
        return contained if contained is not None else _POINTER_REJECTED
    pointer = root / CURRENT_POINTER
    if pointer.is_file():
        # A CURRENT file is authoritative. Do not fall back to another directory.
        contained = _contained_child(root, pointer.read_text(encoding="utf-8"))
        return contained if contained is not None else _POINTER_REJECTED
    current = root / "current"
    if current.is_dir():
        contained = _contained_child(root, "current")
        if contained is not None:
            return contained
    return root


def _load_cohort_manifest(cohort_path: Path) -> dict[str, Any]:
    manifest = _read_json(cohort_path / MANIFEST_NAME) or {}
    return manifest if isinstance(manifest, dict) else {}


def _rejected_pointer_snapshot(cohort: str) -> dict[str, Any]:
    """CURRENT pointed outside this cohort. Do not read the foreign directory."""
    aggregate = aggregate_engineering_gates(
        line_cer=None,
        key_field_f1=None,
        teds=None,
        line_cer_status="NOT_EVALUATED",
        key_field_f1_status="NOT_EVALUATED",
        teds_status="NOT_EVALUATED",
    )
    aggregate["failures"] = [*aggregate["failures"], "current_pointer_outside_cohort"]
    aggregate["engineering_gate"] = "GATE_FAIL"
    aggregate["cohort"] = cohort
    aggregate["product_pass"] = False
    aggregate["forced_requirement_status"] = "NEEDS_REVIEW"
    return aggregate


def _cohort_snapshot(
    base: Path,
    cohort: str,
    *,
    version: str | None = None,
) -> dict[str, Any] | None:
    cohort_path = _cohort_dir(base, cohort, version=version)
    if cohort_path is _POINTER_REJECTED:
        return _rejected_pointer_snapshot(cohort)
    if not isinstance(cohort_path, Path) or not cohort_path.is_dir():
        return None

    line_report = _read_json(cohort_path / METRIC_FILES["line_cer"])
    teds_report = _read_json(cohort_path / METRIC_FILES["teds"])
    key_report = _read_json(cohort_path / METRIC_FILES["key_field_f1"])
    if line_report is None and teds_report is None and key_report is None:
        return None

    line_status = _metric_status(line_report, "line_cer")
    teds_status = _metric_status(teds_report, "teds")
    key_status = _metric_status(key_report, "key_field_f1")

    sources = {
        "line_cer": _provenance_labels(line_report),
        "teds": _provenance_labels(teds_report),
        "key_field_f1": _provenance_labels(key_report),
    }
    # Provenance must name this cohort directory. A copied expanded bundle that
    # still says "expanded" fails inside "old", even when its own files agree.
    inconsistent = any(
        not _provenance_matches_cohort(report, cohort)
        for report in (line_report, teds_report, key_report)
    )

    aggregate = aggregate_engineering_gates(
        line_cer=_metric_from_report(line_report, "line_cer"),
        key_field_f1=_metric_from_report(key_report, "key_field_f1"),
        teds=_metric_from_report(teds_report, "teds"),
        line_cer_status=line_status,
        key_field_f1_status=key_status,
        teds_status=teds_status,
        source=None if inconsistent else cohort,
        expected_source=cohort,
    )
    manifest = _load_cohort_manifest(cohort_path)
    manifest_cohort = manifest.get("cohort")
    if manifest_cohort is not None and str(manifest_cohort) != cohort:
        if "inconsistent_source" not in aggregate["failures"]:
            aggregate["failures"] = [*aggregate["failures"], "inconsistent_source"]
        aggregate["engineering_gate"] = "GATE_FAIL"
        aggregate["source"] = str(manifest_cohort)
        aggregate["expected_source"] = cohort
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
        line_cer_status=_metric_status(line_report, "line_cer"),
        key_field_f1_status=_metric_status(key_report, "key_field_f1"),
        teds_status=_metric_status(teds_report, "teds"),
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
