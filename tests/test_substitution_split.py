"""The 395 substitution characters split into two exclusive pieces."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from work.eval.substitution_split import (
    PIECE_SAME_LINE,
    PIECE_WRONG_LINE,
    classify_substitution_split,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "outputs" / "ocr-benchmark" / "substitution-split-395.json"
SEVEN_JSON = ROOT / "outputs" / "ocr-benchmark" / "line-edit-seven-buckets.json"


@pytest.fixture(scope="module")
def report():
    return classify_substitution_split()


def test_pieces_partition_the_395_substitutions(report):
    assert report["pages"] == 54
    assert report["line_denom"] == 29835
    assert report["line_edits"] == 1302
    assert report["pieces"][PIECE_WRONG_LINE] == 208
    assert report["pieces"][PIECE_SAME_LINE] == 187
    assert report["matches_audit_check"] is True
    assert report["audit_check"] == {PIECE_WRONG_LINE: 208, PIECE_SAME_LINE: 187}
    assert report["comparison"] == "raw_text_before_norm"
    assert report["whitespace_or_case_pairs"] == 7
    assert report["whitespace_or_case_chars"] == 116
    assert sum(item["chars"] for item in report["whitespace_or_case_flips"]) == 116
    assert all(item["gt_raw"] != item["ocr_raw"] for item in report["whitespace_or_case_flips"])
    assert report["piece_sum"] == 395
    assert report["remainder"] == 0
    assert report["substitution_characters"] == 395
    assert report["letterhead_substitutions_excluded"] == 15
    assert report["duplicate_guard_kept_in_piece_2"] == 0
    assert report["page_substitution_matches_seven_buckets"] is True
    assert report["product_pass"] is False
    assert report["business_pass"] is False
    assert report["t005_modified"] is False
    assert report["gate"] == "GATE_FAIL"
    assert report["line_cer_gate"] == "GATE_FAIL"
    assert report["status"] == "pending_audit"
    assert report["live_buckets"] == {
        "not_in_text_layer": 47,
        "header_letterhead": 286,
        "whole_line_miss": 151,
        "paired_line_gap": 363,
        "substitution": 395,
        "extra_insertion": 28,
        "fragment": 32,
    }
    assert sum(report["live_buckets"].values()) == 1302
    keys = []
    for pair in report["pairs"]:
        assert pair["piece"] in {PIECE_WRONG_LINE, PIECE_SAME_LINE}
        assert pair["chars"] > 0
        keys.append((pair["filename"], pair["page"], pair["gt_index"], pair["ocr_index"]))
    assert len(keys) == len(set(keys))
    assert sum(pair["chars"] for pair in report["pairs"]) == 395
    assert sum(row["wrong_line_pairing"] + row["same_line_misread"] for row in report["page_rows"]) == 395


def test_space_and_case_pairs_stay_out_of_piece_1(report):
    notice = next(
        pair
        for pair in report["pairs"]
        if pair["filename"] == "source4-zbtb.pdf"
        and pair["page"] == 5
        and "采购公告" in pair["gt_raw"]
        and "评分法" in pair["ocr_raw"]
    )
    assert notice["piece"] == PIECE_SAME_LINE
    assert notice["chars"] == 17
    assert notice["norm_would_be_piece_1"] is True
    assert "100分" in notice["ocr_raw"]
    assert "100 分" not in notice["ocr_raw"]
    scoring = next(
        pair
        for pair in report["pairs"]
        if pair["filename"] == "source4-zbtb.pdf"
        and pair["page"] == 5
        and "综合评分法" in pair["gt_raw"]
        and "询问" in pair["ocr_raw"]
    )
    assert scoring["piece"] == PIECE_SAME_LINE
    assert scoring["chars"] == 18
    assert "100 分" in scoring["gt_raw"]
    assert scoring["gt_raw"].endswith(" ")
    assert scoring["gt_raw"] != notice["ocr_raw"]
    flip_keys = {(item["filename"], item["page"], item["chars"], item["gt_raw"]) for item in report["whitespace_or_case_flips"]}
    assert ("source4-zbtb.pdf", 5, 17, notice["gt_raw"]) in flip_keys
    assert ("source4-zbtb.pdf", 5, 18, scoring["gt_raw"]) in flip_keys
    assert all(
        pair["piece"] == PIECE_SAME_LINE
        for pair in report["pairs"]
        if (pair["filename"], pair["page"], pair["chars"], pair["gt_raw"]) in flip_keys
    )
    garbled = next(
        pair
        for pair in report["pairs"]
        if pair["filename"] == "source4-zbtb.pdf" and pair["page"] == 5 and "点击左侧菜单" in pair["gt_raw"]
    )
    assert garbled["piece"] == PIECE_SAME_LINE
    assert garbled["chars"] == 17
    assert garbled["norm_would_be_piece_1"] is False
    page = next(row for row in report["page_rows"] if row["filename"] == "source4-zbtb.pdf" and row["page"] == 5)
    assert page["substitution"] == 105
    assert page["wrong_line_pairing"] + page["same_line_misread"] == 105
    bid_open = next(
        pair
        for pair in report["pairs"]
        if pair["filename"] == "pub-gx-youjiang-ultrasound.pdf"
        and pair["page"] == 5
        and pair["gt_raw"].startswith("开标时间")
        and pair["ocr_raw"].startswith("开标地点")
    )
    assert bid_open["piece"] == PIECE_WRONG_LINE
    assert bid_open["chars"] == 17


def test_checked_in_report_matches_the_classifier(report):
    assert REPORT_JSON.is_file()
    saved = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert saved["pieces"] == report["pieces"]
    assert saved["piece_sum"] == 395
    assert saved["remainder"] == 0
    assert saved["pages"] == 54
    assert saved["line_edits"] == 1302
    assert saved["line_denom"] == 29835
    assert saved["product_pass"] is False
    assert saved["status"] == "pending_audit"
    assert saved["page_substitution_matches_seven_buckets"] is True
    assert saved["live_buckets"]["substitution"] == 395
    saved_pairs = [
        (pair["filename"], pair["page"], pair["gt_index"], pair["chars"], pair["piece"], pair["reason"])
        for pair in saved["pairs"]
    ]
    live_pairs = [
        (pair["filename"], pair["page"], pair["gt_index"], pair["chars"], pair["piece"], pair["reason"])
        for pair in report["pairs"]
    ]
    assert saved_pairs == live_pairs
    seven = json.loads(SEVEN_JSON.read_text(encoding="utf-8"))
    assert seven["buckets"]["substitution"] == 395
    assert seven["line_edits"] == 1302
    assert seven["line_denom"] == 29835
    assert seven["product_pass"] is False
