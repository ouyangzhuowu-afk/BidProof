"""S-A-03: key-field F1 harness gates at 97% and never claims product PASS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.key_field_f1 import (
    ForbiddenOutputError,
    evaluate_key_field_f1,
    main as f1_main,
    score_key_field_f1,
    write_report,
)
from work.eval.page_annotation import load_annotations
from work.eval.sandbox_gates import KEY_FIELD_F1_MIN


ROOT = Path(__file__).resolve().parents[1]
GT = ROOT / "work" / "eval" / "fixtures" / "key_field_gt.jsonl"
HYP = ROOT / "work" / "eval" / "fixtures" / "key_field_hypotheses.jsonl"


def test_f1_gate_constant_is_ninety_seven_percent():
    assert KEY_FIELD_F1_MIN == 0.97


def test_perfect_predictions_are_gate_pass_but_not_product_pass():
    gt = [{"doc_id": "d", "page": 1, "fields": [{"name": "budget", "value": "10万元"}]}]
    hyp = [{"doc_id": "d", "page": 1, "fields_hyp": [{"name": "budget", "value": "10 万元"}]}]
    report = evaluate_key_field_f1(gt, hyp)
    assert report["key_field_f1"] == 1.0
    assert report["gate"] == "GATE_PASS"
    assert report["product_pass"] is False
    assert report["forced_requirement_status"] == "NEEDS_REVIEW"


def test_wrong_value_counts_against_f1():
    scored = score_key_field_f1(
        {("d", "budget"): "10万元"},
        {("d", "budget"): "99万元"},
    )
    assert scored["tp"] == 0
    assert scored["fn"] == 1
    assert scored["fp"] == 1
    assert scored["key_field_f1"] == 0.0


def test_sandbox_fixture_run_is_gate_fail():
    gt = load_annotations(GT)
    hyp = [json.loads(line) for line in HYP.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = evaluate_key_field_f1(gt, hyp)
    assert report["gt_count"] == 78
    assert report["key_field_f1"] < KEY_FIELD_F1_MIN
    assert report["gate"] == "GATE_FAIL"
    assert report["product_pass"] is False
    assert report["business_pass"] is False


def test_write_report_refuses_ledger_paths(tmp_path):
    report = evaluate_key_field_f1(
        [{"doc_id": "d", "page": 1, "fields": [{"name": "budget", "value": "1"}]}],
        [{"doc_id": "d", "page": 1, "fields_hyp": [{"name": "budget", "value": "1"}]}],
    )
    with pytest.raises(ForbiddenOutputError):
        write_report(report, tmp_path / "pilot-ledger.csv")


def test_cli_sandbox_exit_code_is_gate_fail(tmp_path):
    code = f1_main(["--out-dir", str(tmp_path / "ocr-benchmark")])
    assert code == 2
    payload = json.loads((tmp_path / "ocr-benchmark" / "key-field-f1-report.json").read_text(encoding="utf-8"))
    assert payload["gate"] == "GATE_FAIL"
    assert payload["product_pass"] is False
