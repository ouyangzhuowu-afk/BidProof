"""The seven-bucket line-edit table is a label of the current 1302 edits."""

from __future__ import annotations

import json
from pathlib import Path

from work.eval.line_edit_buckets import BUCKET_ORDER, classify_line_edits

ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "outputs" / "ocr-benchmark" / "line-edit-seven-buckets.json"


def test_seven_buckets_partition_the_1302_edits():
    report = classify_line_edits()
    assert report["pages"] == 54
    assert report["line_edits"] == 1302
    assert report["line_denom"] == 29835
    assert report["remainder"] == 0
    assert report["bucket_sum"] == 1302
    assert sum(report["buckets"][name] for name in BUCKET_ORDER) == 1302
    assert report["product_pass"] is False
    assert report["t005_modified"] is False
    assert report["gate"] == "GATE_FAIL"
    assert report["status"] == "pending_audit"
    page_edits = 0
    for row in report["page_rows"]:
        column_sum = sum(row[name] for name in BUCKET_ORDER)
        assert column_sum == row["edits"]
        page_edits += row["edits"]
    assert page_edits == 1302


def test_fragment_and_letterhead_pages_stay_exclusive():
    report = classify_line_edits()
    by_key = {(row["filename"], row["page"]): row for row in report["page_rows"]}
    assert by_key[("pub-gx-minzu-ultrasound-2026.pdf", 6)]["fragment"] == 20
    assert by_key[("pub-gx-tianlin-yuegui-devices-2026.pdf", 8)]["fragment"] == 8
    assert by_key[("source2-nanjing.pdf", 32)]["fragment"] == 4
    assert sum(row["fragment"] for row in report["page_rows"]) == 32
    zbtb4 = by_key[("source4-zbtb.pdf", 4)]
    assert zbtb4["header_letterhead"] == 76
    assert zbtb4["not_in_text_layer"] == 8
    letterhead_subs = sum(
        item["chars"]
        for item in report["evidence"]
        if item["kind"] == "paired_letterhead_substitution"
    )
    assert letterhead_subs == 15


def test_checked_in_report_matches_the_classifier():
    assert REPORT_JSON.is_file()
    saved = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    live = classify_line_edits()
    assert saved["buckets"] == live["buckets"]
    assert saved["bucket_sum"] == 1302
    assert saved["remainder"] == 0
    assert saved["line_denom"] == 29835
    assert saved["pages"] == 54
    assert saved["product_pass"] is False
    assert saved["underlying"]["line_cer_gate"] == "GATE_FAIL"
    assert saved["underlying"]["gate"] == "GATE_FAIL"
    assert saved["underlying"]["product_pass"] is False
