"""Sandbox hard-OR gate aggregator."""

from work.eval.sandbox_gates import (
    KEY_FIELD_F1_MIN,
    LINE_CER_MAX,
    TEDS_MIN,
    aggregate_engineering_gates,
)


def test_gate_thresholds_match_roadmap():
    assert LINE_CER_MAX == 0.02
    assert KEY_FIELD_F1_MIN == 0.97
    assert TEDS_MIN == 0.9


def test_any_failing_gate_forces_needs_review():
    report = aggregate_engineering_gates(line_cer=0.0, key_field_f1=1.0, teds=0.5)
    assert report["failures"] == ["teds"]
    assert report["engineering_gate"] == "GATE_FAIL"
    assert report["forced_requirement_status"] == "NEEDS_REVIEW"
    assert report["product_pass"] is False


def test_unevaluated_gates_are_fail_closed():
    report = aggregate_engineering_gates(teds=0.99)
    assert "line_cer" in report["unevaluated"]
    assert "key_field_f1" in report["unevaluated"]
    assert report["engineering_gate"] == "GATE_FAIL"
    assert report["forced_requirement_status"] == "NEEDS_REVIEW"


def test_all_passing_evaluated_gates_are_engineering_pass_only():
    report = aggregate_engineering_gates(line_cer=0.01, key_field_f1=0.99, teds=0.95)
    assert report["failures"] == []
    assert report["unevaluated"] == []
    assert report["engineering_gate"] == "GATE_PASS"
    assert report["product_pass"] is False
    assert report["business_pass"] is False
