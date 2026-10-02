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
    assert report["invalid"] == []
    assert report["engineering_gate"] == "GATE_PASS"
    assert report["product_pass"] is False
    assert report["business_pass"] is False


def test_nan_and_out_of_range_are_failures():
    bad = aggregate_engineering_gates(line_cer=float("nan"), key_field_f1=0.99, teds=0.95)
    assert bad["engineering_gate"] == "GATE_FAIL"
    assert "invalid_line_cer" in bad["failures"]

    over = aggregate_engineering_gates(line_cer=0.01, key_field_f1=1.5, teds=0.95)
    assert over["engineering_gate"] == "GATE_FAIL"
    assert "invalid_key_field_f1" in over["failures"]

    # CER > 1 is allowed as a number but fails the ≤2% threshold (no false 1.0 cap).
    high = aggregate_engineering_gates(line_cer=1.5, key_field_f1=0.99, teds=0.95)
    assert high["line_cer"] == 1.5
    assert "line_cer" in high["failures"]
    assert "invalid_line_cer" not in high["failures"]


def test_inconsistent_source_fails_closed():
    report = aggregate_engineering_gates(
        line_cer=0.01,
        key_field_f1=0.99,
        teds=0.95,
        source="expanded",
        expected_source="old",
    )
    assert report["engineering_gate"] == "GATE_FAIL"
    assert "inconsistent_source" in report["failures"]
    assert report["product_pass"] is False
