"""S-A-02: line-CER harness keeps page CER separate and gates at 2%."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.ocr_benchmark import cer
from work.eval.page_annotation import load_annotations
from work.eval.rapidocr_line_cer import (
    LINE_CER_GATE,
    ForbiddenOutputError,
    evaluate_line_cer,
    main as line_cer_main,
    write_report,
)


ROOT = Path(__file__).resolve().parents[1]
SANDBOX_PAGES = ROOT / "work" / "eval" / "fixtures" / "sandbox_pages.jsonl"
SANDBOX_HYP = ROOT / "work" / "eval" / "fixtures" / "sandbox_hypotheses.jsonl"
PILOT_LEDGER = ROOT / "outputs" / "pilot-ledger.csv"
ICP_LEDGER = ROOT / "outputs" / "icp-outreach.csv"


def test_line_cer_gate_constant_is_two_percent():
    assert LINE_CER_GATE == 0.02


def test_page_cer_and_line_cer_are_not_mixed_on_block_move():
    gt = {"doc_id": "t", "page": 1, "text_gt": "AAAA\nBBBB\nCCCC"}
    hyp = {"doc_id": "t", "page": 1, "text_hyp": "CCCC\nAAAA\nBBBB", "lines_hyp": ["CCCC", "AAAA", "BBBB"]}
    report = evaluate_line_cer([gt], [hyp])
    page = report["page_cer"]
    line = report["line_cer"]
    assert page != line
    assert line == 0.0
    assert page == cer("AAAABBBBCCCC", "CCCCAAAABBBB")
    assert "cer" not in report
    assert report["gate"] == "GATE_PASS"
    assert report["product_pass"] is False
    assert report["business_pass"] is False


def test_line_cer_above_two_percent_is_gate_fail_not_product_pass():
    gt = {"doc_id": "t", "page": 1, "text_gt": "abcdefghij"}
    hyp = {"doc_id": "t", "page": 1, "text_hyp": "abcdxxxxij", "lines_hyp": ["abcdxxxxij"]}
    report = evaluate_line_cer([gt], [hyp])
    assert report["line_cer"] == 0.4
    assert report["page_cer"] == 0.4
    assert report["gate"] == "GATE_FAIL"
    assert report["line_cer_gate"] == 0.02
    assert report["product_pass"] is False
    assert "GATE_FAIL" in report["markdown"]
    assert "product PASS" not in report["markdown"].lower() or "not a product" in report["markdown"].lower()


def test_sandbox_fixture_run_is_gate_fail_and_separates_metrics():
    gt = load_annotations(SANDBOX_PAGES)
    hyp = [json.loads(line) for line in SANDBOX_HYP.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = evaluate_line_cer(gt, hyp)
    assert report["page_cer"] is not None
    assert report["line_cer"] is not None
    assert report["page_cer"] != report["line_cer"]
    assert report["line_cer"] > LINE_CER_GATE
    assert report["gate"] == "GATE_FAIL"
    assert report["teds_gt_pages"] == 0
    assert report["product_pass"] is False
    assert report["business_pass"] is False


def test_write_report_refuses_pilot_and_icp_ledger_paths(tmp_path):
    report = evaluate_line_cer(
        [{"doc_id": "t", "page": 1, "text_gt": "ab"}],
        [{"doc_id": "t", "page": 1, "text_hyp": "ab", "lines_hyp": ["ab"]}],
    )
    with pytest.raises(ForbiddenOutputError):
        write_report(report, tmp_path / "pilot-ledger.csv")
    with pytest.raises(ForbiddenOutputError):
        write_report(report, tmp_path / "outputs" / "icp-outreach.md")


def test_write_report_does_not_touch_ledgers(tmp_path):
    report = evaluate_line_cer(
        [{"doc_id": "t", "page": 1, "text_gt": "ab"}],
        [{"doc_id": "t", "page": 1, "text_hyp": "ax", "lines_hyp": ["ax"]}],
    )
    out_dir = tmp_path / "ocr-benchmark"
    pilot_before = PILOT_LEDGER.read_text(encoding="utf-8")
    icp_before = ICP_LEDGER.read_text(encoding="utf-8")
    paths = write_report(report, out_dir)
    assert paths["markdown"].read_text(encoding="utf-8").startswith("# ")
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["gate"] in {"GATE_FAIL", "GATE_PASS"}
    assert PILOT_LEDGER.read_text(encoding="utf-8") == pilot_before
    assert ICP_LEDGER.read_text(encoding="utf-8") == icp_before
    assert "pilot-ledger" not in str(paths["markdown"])
    assert "icp-outreach" not in str(paths["json"])


def test_cli_writes_separated_gate_report(tmp_path, capsys):
    out_dir = tmp_path / "ocr-benchmark"
    code = line_cer_main(
        [
            "--annotations",
            str(SANDBOX_PAGES),
            "--hypotheses",
            str(SANDBOX_HYP),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert code == 2  # GATE_FAIL exit, not a crash
    md = (out_dir / "line-cer-report.md").read_text(encoding="utf-8")
    assert "GATE_FAIL" in md
    assert "page CER" in md.lower() or "`page_cer`" in md
    assert "`line_cer`" in md or "line CER" in md
    assert "≤ 2%" in md or "<= 2%" in md or "0.02" in md
    assert not list(out_dir.glob("*pilot*"))
    assert not list(out_dir.glob("*icp*"))
    printed = capsys.readouterr().out
    assert "GATE_FAIL" in printed
