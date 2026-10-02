"""Sandbox Campaign A engineering gates (S-A-02 / S-A-03 / S-A-06).

Hard OR: any evaluated gate that fails keeps the product path on NEEDS_REVIEW.
Never claims product or business PASS. Never writes pilot/ICP ledgers.

Metric validation is fail-closed:
- line CER must be a finite number >= 0 (no false upper-cap of 1.0)
- key-field F1 and TEDS must be finite and in [0, 1]
- NaN / Inf / non-numeric / out-of-range values count as failures
"""

from __future__ import annotations

import math
from typing import Any

LINE_CER_MAX = 0.02
KEY_FIELD_F1_MIN = 0.97
TEDS_MIN = 0.9

REQUIRED_COHORTS = ("old", "expanded")


def _as_finite_number(value: Any) -> float | None:
    """Return a finite float, or None when missing / non-numeric / NaN / Inf."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text in {"nan", "inf", "+inf", "-inf", "infinity", "-infinity", "null", "none", "n/a"}:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    if not math.isfinite(number):
        return None
    return number


def validate_line_cer(value: Any) -> tuple[float | None, str | None]:
    """CER: finite and >= 0. Values above 1.0 remain valid (no false upper-cap)."""
    number = _as_finite_number(value)
    if number is None:
        if value is None:
            return None, None
        return None, "invalid_line_cer"
    if number < 0:
        return None, "invalid_line_cer"
    return number, None


def validate_unit_interval(value: Any, *, name: str) -> tuple[float | None, str | None]:
    """F1 / TEDS: finite and in [0, 1]."""
    number = _as_finite_number(value)
    if number is None:
        if value is None:
            return None, None
        return None, f"invalid_{name}"
    if number < 0.0 or number > 1.0:
        return None, f"invalid_{name}"
    return number, None


def aggregate_engineering_gates(
    *,
    line_cer: float | None = None,
    key_field_f1: float | None = None,
    teds: float | None = None,
    line_cer_status: str | None = None,
    key_field_f1_status: str | None = None,
    teds_status: str | None = None,
    source: str | None = None,
    expected_source: str | None = None,
) -> dict[str, Any]:
    """Combine OCR/structure gates. Unevaluated metrics are ignored, not treated as pass."""
    failures: list[str] = []
    unevaluated: list[str] = []
    invalid: list[str] = []

    if expected_source is not None:
        observed = str(source or "").strip()
        if not observed or observed != expected_source:
            failures.append("inconsistent_source")

    cer_value, cer_error = validate_line_cer(line_cer)
    if cer_error:
        failures.append(cer_error)
        invalid.append("line_cer")
    elif cer_value is not None:
        if cer_value > LINE_CER_MAX:
            failures.append("line_cer")
    elif line_cer_status in {None, "NOT_EVALUATED", "INSUFFICIENT"}:
        unevaluated.append("line_cer")

    f1_value, f1_error = validate_unit_interval(key_field_f1, name="key_field_f1")
    if f1_error:
        failures.append(f1_error)
        invalid.append("key_field_f1")
    elif f1_value is not None:
        if f1_value < KEY_FIELD_F1_MIN:
            failures.append("key_field_f1")
    elif key_field_f1_status in {None, "NOT_EVALUATED", "INSUFFICIENT"}:
        unevaluated.append("key_field_f1")

    teds_value, teds_error = validate_unit_interval(teds, name="teds")
    if teds_error:
        failures.append(teds_error)
        invalid.append("teds")
    elif teds_value is not None:
        if teds_value < TEDS_MIN:
            failures.append("teds")
    elif teds_status in {None, "NOT_EVALUATED", "INSUFFICIENT"}:
        unevaluated.append("teds")

    engineering_gate = "GATE_PASS" if not failures and not unevaluated else "GATE_FAIL"
    # Fail-closed: missing evaluations also block product PASS claims.
    if unevaluated and not failures:
        engineering_gate = "GATE_FAIL"

    return {
        "line_cer_max": LINE_CER_MAX,
        "key_field_f1_min": KEY_FIELD_F1_MIN,
        "teds_min": TEDS_MIN,
        "line_cer": cer_value,
        "key_field_f1": f1_value,
        "teds": teds_value,
        "failures": failures,
        "unevaluated": unevaluated,
        "invalid": invalid,
        "source": source,
        "expected_source": expected_source,
        "engineering_gate": engineering_gate,
        "product_pass": False,
        "business_pass": False,
        "forced_requirement_status": "NEEDS_REVIEW",
        "claim_scope": "engineering_gate_only",
        "note": "Hard OR of evaluated CER/F1/TEDS failures, plus fail-closed on unevaluated/invalid gates. Not T-005.",
    }


def aggregate_cohort_gates(
    cohorts: dict[str, dict[str, Any] | None],
    *,
    required: tuple[str, ...] = REQUIRED_COHORTS,
) -> dict[str, Any]:
    """Hard-OR across required cohorts. Missing / failing / invalid cohort ⇒ overall FAIL.

    Does not average, pick the best, or use latest-only. Every required cohort must
    independently GATE_PASS for the OCR engineering gate to pass. product_pass stays false.
    """
    cohort_results: dict[str, Any] = {}
    failing_cohorts: list[str] = []
    missing_cohorts: list[str] = []

    for name in required:
        payload = cohorts.get(name)
        if payload is None:
            missing_cohorts.append(name)
            cohort_results[name] = {
                "engineering_gate": "GATE_FAIL",
                "failures": ["missing_cohort"],
                "unevaluated": ["line_cer", "key_field_f1", "teds"],
                "product_pass": False,
            }
            failing_cohorts.append(name)
            continue
        gate = str(payload.get("engineering_gate") or "GATE_FAIL")
        cohort_results[name] = payload
        if gate != "GATE_PASS" or payload.get("failures") or payload.get("unevaluated") or payload.get("invalid"):
            failing_cohorts.append(name)

    engineering_gate = "GATE_PASS" if not failing_cohorts and not missing_cohorts else "GATE_FAIL"
    return {
        "required_cohorts": list(required),
        "cohorts": cohort_results,
        "failing_cohorts": failing_cohorts,
        "missing_cohorts": missing_cohorts,
        "engineering_gate": engineering_gate,
        "product_pass": False,
        "business_pass": False,
        "forced_requirement_status": "NEEDS_REVIEW",
        "claim_scope": "engineering_gate_only",
        "note": (
            "Hard OR across required cohorts (old + expanded). "
            "Expanded PASS cannot override old FAIL/missing. Not T-005."
        ),
    }
