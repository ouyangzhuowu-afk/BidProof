"""S-A-06: TEDS harness gates at 90% and never claims product PASS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.page_annotation import load_annotations
from work.eval.sandbox_gates import TEDS_MIN
from work.eval.teds_harness import (
    ForbiddenOutputError,
    evaluate_teds,
    main as teds_main,
    write_report,
)
from work.eval.teds_score import teds


ROOT = Path(__file__).resolve().parents[1]
TEDS_GT = ROOT / "work" / "eval" / "fixtures" / "teds_gt.jsonl"
TEDS_HYP = ROOT / "work" / "eval" / "fixtures" / "teds_hypotheses.jsonl"


def test_teds_identical_tables_score_one():
    html = "<table><tr><td>甲</td><td>乙</td></tr></table>"
    assert teds(html, html) == 1.0


def test_teds_empty_vs_table_is_zero():
    html = "<table><tr><td>甲</td></tr></table>"
    assert teds("", html) == 0.0
    assert teds(html, "") == 0.0


def test_teds_gate_constant_is_ninety_percent():
    assert TEDS_MIN == 0.9


def test_perfect_pages_are_gate_pass_but_not_product_pass():
    gt = [{"doc_id": "t", "page": 1, "table_html": "<table><tr><td>a</td><td>b</td></tr></table>"}]
    hyp = [{"doc_id": "t", "page": 1, "table_html_hyp": "<table><tr><td>a</td><td>b</td></tr></table>"}]
    report = evaluate_teds(gt, hyp)
    assert report["teds"] == 1.0
    assert report["gate"] == "GATE_PASS"
    assert report["product_pass"] is False
    assert report["business_pass"] is False
    assert report["forced_requirement_status"] == "NEEDS_REVIEW"


def test_low_teds_is_gate_fail_not_product_pass():
    gt = [{"doc_id": "t", "page": 1, "table_html": "<table><tr><td>abcdefghij</td></tr></table>"}]
    hyp = [{"doc_id": "t", "page": 1, "table_html_hyp": "<table><tr><td>zzzzzzzzzz</td></tr></table>"}]
    report = evaluate_teds(gt, hyp)
    assert report["teds"] < TEDS_MIN
    assert report["gate"] == "GATE_FAIL"
    assert report["product_pass"] is False
    assert "GATE_FAIL" in report["markdown"]


def test_sandbox_fixture_run_is_gate_fail():
    gt = load_annotations(TEDS_GT)
    hyp = [json.loads(line) for line in TEDS_HYP.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = evaluate_teds(gt, hyp)
    assert report["pages_scored"] == 16
    assert report["teds"] < TEDS_MIN
    assert report["gate"] == "GATE_FAIL"
    assert report["product_pass"] is False
    assert report["business_pass"] is False


def test_write_report_refuses_pilot_and_icp_ledger_paths(tmp_path):
    report = evaluate_teds(
        [{"doc_id": "t", "page": 1, "table_html": "<table><tr><td>a</td></tr></table>"}],
        [{"doc_id": "t", "page": 1, "table_html_hyp": "<table><tr><td>a</td></tr></table>"}],
    )
    with pytest.raises(ForbiddenOutputError):
        write_report(report, tmp_path / "pilot-ledger.csv")
    with pytest.raises(ForbiddenOutputError):
        write_report(report, tmp_path / "icp-outreach")


def test_cli_sandbox_exit_code_is_gate_fail(tmp_path):
    code = teds_main(["--out-dir", str(tmp_path / "ocr-benchmark")])
    assert code == 2
    payload = json.loads((tmp_path / "ocr-benchmark" / "teds-report.json").read_text(encoding="utf-8"))
    assert payload["gate"] == "GATE_FAIL"
    assert payload["product_pass"] is False
