"""Sandbox Campaign A engineering gates (S-A-02 / S-A-03 / S-A-06).

Hard OR: any evaluated gate that fails keeps the product path on NEEDS_REVIEW.
Never claims product or business PASS. Never writes pilot/ICP ledgers.
"""

from __future__ import annotations

from typing import Any

LINE_CER_MAX = 0.02
KEY_FIELD_F1_MIN = 0.97
TEDS_MIN = 0.9


def aggregate_engineering_gates(
    *,
    line_cer: float | None = None,
    key_field_f1: float | None = None,
    teds: float | None = None,
    line_cer_status: str | None = None,
    key_field_f1_status: str | None = None,
    teds_status: str | None = None,
) -> dict[str, Any]:
    """Combine OCR/structure gates. Unevaluated metrics are ignored, not treated as pass."""
    failures: list[str] = []
    unevaluated: list[str] = []

    if line_cer is not None:
        if line_cer > LINE_CER_MAX:
            failures.append("line_cer")
    elif line_cer_status in {None, "NOT_EVALUATED", "INSUFFICIENT"}:
        unevaluated.append("line_cer")

    if key_field_f1 is not None:
        if key_field_f1 < KEY_FIELD_F1_MIN:
            failures.append("key_field_f1")
    elif key_field_f1_status in {None, "NOT_EVALUATED", "INSUFFICIENT"}:
        unevaluated.append("key_field_f1")

    if teds is not None:
        if teds < TEDS_MIN:
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
        "line_cer": line_cer,
        "key_field_f1": key_field_f1,
        "teds": teds,
        "failures": failures,
        "unevaluated": unevaluated,
        "engineering_gate": engineering_gate,
        "product_pass": False,
        "business_pass": False,
        "forced_requirement_status": "NEEDS_REVIEW",
        "claim_scope": "engineering_gate_only",
        "note": "Hard OR of evaluated CER/F1/TEDS failures, plus fail-closed on unevaluated gates. Not T-005.",
    }
