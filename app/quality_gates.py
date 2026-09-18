"""Product-facing OCR engineering gate snapshot (S-A-08 / S-A-06 wiring).

Reads committed sandbox reports under ``outputs/ocr-benchmark/`` when present.
Fail-closed: missing or failing CER/F1/TEDS keeps ``forced_requirement_status=NEEDS_REVIEW``.
Never claims product PASS. Does not write ledgers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from work.eval.sandbox_gates import aggregate_engineering_gates

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "outputs" / "ocr-benchmark"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def engineering_gate_snapshot(report_dir: Path | None = None) -> dict[str, Any]:
    base = Path(report_dir) if report_dir is not None else REPORT_DIR
    line_report = _read_json(base / "line-cer-report.json")
    teds_report = _read_json(base / "teds-report.json")
    key_report = _read_json(base / "key-field-f1-report.json")

    line_cer = None
    line_status = "NOT_EVALUATED"
    if line_report is not None and "line_cer" in line_report:
        line_cer = float(line_report["line_cer"])
        line_status = "EVALUATED"

    teds = None
    teds_status = "NOT_EVALUATED"
    if teds_report is not None and "teds" in teds_report:
        teds = float(teds_report["teds"])
        teds_status = "EVALUATED"

    key_f1 = None
    key_status = "NOT_EVALUATED"
    if key_report is not None and "key_field_f1" in key_report:
        key_f1 = float(key_report["key_field_f1"])
        key_status = "EVALUATED"

    aggregate = aggregate_engineering_gates(
        line_cer=line_cer,
        key_field_f1=key_f1,
        teds=teds,
        line_cer_status=line_status,
        key_field_f1_status=key_status,
        teds_status=teds_status,
    )
    aggregate["sources"] = {
        "line_cer_report": bool(line_report),
        "teds_report": bool(teds_report),
        "key_field_f1_report": bool(key_report),
    }
    return aggregate


def allow_machine_pass(report_dir: Path | None = None) -> bool:
    """Machine/auto PASS is forbidden while any engineering gate fails or is missing."""
    snapshot = engineering_gate_snapshot(report_dir)
    return snapshot["engineering_gate"] == "GATE_PASS" and not snapshot["unevaluated"] and not snapshot["failures"]
