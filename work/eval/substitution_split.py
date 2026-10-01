"""Split the current 395 substitution characters into two exclusive pieces.

Evidence only. This module does not change recognition, the scoring formula,
thresholds, ground truth, or the greedy line matcher. It labels substitutions
the seven-bucket table already counted.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from work.eval.line_edit_buckets import (
    BUCKET_ORDER,
    _align_ops,
    _filename_by_doc,
    _fold_dash,
    _greedy,
    _in_text,
    _is_masthead_or_logo,
    _prepared_pages,
    classify_line_edits,
)
from work.eval.public_expand import OUT_DIR

PIECE_WRONG_LINE = "wrong_line_pairing"
PIECE_SAME_LINE = "same_line_misread"
PIECE_ORDER = (PIECE_WRONG_LINE, PIECE_SAME_LINE)
PIECE_LABELS = {
    PIECE_WRONG_LINE: "1. Whole line paired to the wrong OCR line",
    PIECE_SAME_LINE: "2. True wrong characters inside a correctly paired line",
}

# Frozen measurements. This split does not recompute them.
UNDERLYING = {
    "pages": 54,
    "line_edits": 1302,
    "line_denom": 29835,
    "line_cer_display": "4.36%",
    "line_cer_gate": "GATE_FAIL",
    "key_field_f1_display": "97.17%",
    "teds_display": "95.80%",
    "gate": "GATE_FAIL",
    "product_pass": False,
    "buckets": {
        "not_in_text_layer": 47,
        "header_letterhead": 286,
        "whole_line_miss": 151,
        "paired_line_gap": 363,
        "substitution": 395,
        "extra_insertion": 28,
        "fragment": 32,
    },
}

EXCLUSIVE_RULE = (
    "Each of the 395 substitution characters keeps the greedy pair that already "
    "produced it. Pairs are not changed, and there is no distance cutoff. "
    "A character is piece 1 when its pair meets either structural test, and piece 2 "
    "when it meets neither. Test A: the OCR line the matcher chose is "
    "character-for-character equal to a different ground-truth line on the same page. "
    "Test B: this ground-truth line is character-for-character equal to a different "
    "OCR line on the same page, and that other OCR line is not paired to another "
    "ground-truth line with this same text. The same-text guard stops a repeated "
    "line's own misread from being called a wrong line when the other copy was read "
    "exactly. If both tests match, the character is piece 1 once. Equality uses the "
    "normalized line text the current scorer already uses."
)

_REPORT_MD = OUT_DIR / "substitution-split-395.md"
_REPORT_JSON = OUT_DIR / "substitution-split-395.json"


def _other_gt_index(hyp: str, ref_index: int, refs: list[str]) -> int | None:
    for index, other in enumerate(refs):
        if index != ref_index and other == hyp:
            return index
    return None


def _displaced_ocr_index(
    ref: str,
    hyp_index: int,
    refs: list[str],
    hyps: list[str],
    owner: dict[int, int],
) -> int | None:
    """Another OCR line that is this ground-truth text, and is not the matching copy of a duplicate line."""
    for index, other in enumerate(hyps):
        if index == hyp_index or other != ref:
            continue
        owner_gt = owner.get(index)
        if owner_gt is None or refs[owner_gt] != ref:
            return index
    return None


def _same_text_ocr_only(
    ref: str,
    hyp_index: int,
    refs: list[str],
    hyps: list[str],
    owner: dict[int, int],
) -> bool:
    """True when the only exact OCR copies of this line are paired to the same text."""
    saw_exact = False
    for index, other in enumerate(hyps):
        if index == hyp_index or other != ref:
            continue
        saw_exact = True
        owner_gt = owner.get(index)
        if owner_gt is None or refs[owner_gt] != ref:
            return False
    return saw_exact


def classify_substitution_split() -> dict[str, Any]:
    buckets = classify_line_edits()
    filenames = _filename_by_doc()
    pages = _prepared_pages()
    totals: Counter[str] = Counter()
    page_counts: dict[tuple[str, int], Counter[str]] = {}
    pairs: list[dict[str, Any]] = []
    kept = 0
    letterhead_substitutions = 0
    duplicate_guard_kept_in_piece_2 = 0
    denom = 0
    for page in pages:
        doc_id, page_no = page["key"]
        filename = filenames.get(doc_id, doc_id)
        refs: list[str] = page["refs"]
        hyps: list[str] = page["hyps"]
        text = page["text"]
        folded = _fold_dash(text)
        denom += sum(len(line) for line in refs)
        matched, _unused = _greedy(refs, hyps)
        owner = {hyp_index: ref_index for ref_index, hyp_index in enumerate(matched) if hyp_index is not None}
        for ref_index, hyp_index in enumerate(matched):
            if hyp_index is None:
                continue
            ref = refs[ref_index]
            hyp = hyps[hyp_index]
            ops = _align_ops(ref, hyp)
            sub_count = sum(1 for op, _ref_char, _hyp_char in ops if op == "S")
            if not sub_count:
                continue
            letterhead = _is_masthead_or_logo(hyp, hyps) and not _in_text(hyp, text, folded)
            if letterhead:
                letterhead_substitutions += sub_count
                continue
            other_gt = _other_gt_index(hyp, ref_index, refs)
            displaced = _displaced_ocr_index(ref, hyp_index, refs, hyps, owner)
            if other_gt is None and displaced is None and _same_text_ocr_only(ref, hyp_index, refs, hyps, owner):
                duplicate_guard_kept_in_piece_2 += sub_count
            if other_gt is not None and displaced is not None:
                reason = "both"
            elif other_gt is not None:
                reason = "ocr_equals_other_gt"
            elif displaced is not None:
                reason = "gt_equals_other_ocr"
            else:
                reason = "same_line"
            piece = PIECE_WRONG_LINE if reason != "same_line" else PIECE_SAME_LINE
            kept += sub_count
            totals[piece] += sub_count
            page_counts.setdefault((filename, page_no), Counter())[piece] += sub_count
            pairs.append(
                {
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": page_no,
                    "gt_index": ref_index,
                    "ocr_index": hyp_index,
                    "chars": sub_count,
                    "piece": piece,
                    "reason": reason,
                    "gt": ref,
                    "ocr": hyp,
                    "other_gt": None if other_gt is None else refs[other_gt],
                    "other_ocr": None if displaced is None else hyps[displaced],
                }
            )
    piece_sum = sum(totals[piece] for piece in PIECE_ORDER)
    live_buckets = {name: buckets["buckets"][name] for name in BUCKET_ORDER}
    seven_substitution = {
        (row["filename"], int(row["page"])): int(row["substitution"])
        for row in buckets["page_rows"]
        if row.get("substitution")
    }
    page_rows = []
    for (filename, page_no), counts in page_counts.items():
        page_rows.append(
            {
                "filename": filename,
                "page": page_no,
                "wrong_line_pairing": counts[PIECE_WRONG_LINE],
                "same_line_misread": counts[PIECE_SAME_LINE],
                "substitution": counts[PIECE_WRONG_LINE] + counts[PIECE_SAME_LINE],
            }
        )
    page_rows.sort(key=lambda row: (-row["substitution"], row["filename"], row["page"]))
    split_substitution = {(row["filename"], int(row["page"])): int(row["substitution"]) for row in page_rows}
    return {
        "leaf_id": "S-A-OCR-PUBLIC-EXPAND",
        "status": "pending_audit",
        "claim_scope": "substitution_split_only",
        "product_pass": False,
        "business_pass": False,
        "t005_modified": False,
        "gate": "GATE_FAIL",
        "line_cer_gate": "GATE_FAIL",
        "generated_at": datetime.now(UTC).astimezone().isoformat(),
        "pages": len(pages),
        "line_edits": buckets["line_edits"],
        "line_denom": denom,
        "pieces": {piece: totals[piece] for piece in PIECE_ORDER},
        "piece_sum": piece_sum,
        "substitution_characters": kept,
        "remainder": UNDERLYING["buckets"]["substitution"] - piece_sum,
        "letterhead_substitutions_excluded": letterhead_substitutions,
        "duplicate_guard_kept_in_piece_2": duplicate_guard_kept_in_piece_2,
        "exclusive_rule": EXCLUSIVE_RULE,
        "underlying": UNDERLYING,
        "live_buckets": live_buckets,
        "page_substitution_matches_seven_buckets": split_substitution == seven_substitution,
        "page_rows": page_rows,
        "pairs": pairs,
    }


def _preview(text: str, limit: int = 80) -> str:
    shown = text if len(text) <= limit else text[:limit] + "…"
    return shown.replace("|", "/")


def _dominant(rows: list[dict[str, Any]], piece: str) -> list[dict[str, Any]]:
    ranked = [row for row in rows if row.get(piece)]
    ranked.sort(key=lambda row: (-row[piece], row["filename"], row["page"]))
    return ranked


def _find_pair(report: dict[str, Any], filename: str, page: int, gt_part: str, ocr_part: str) -> dict[str, Any] | None:
    for pair in report["pairs"]:
        if pair["filename"] == filename and pair["page"] == page and gt_part in pair["gt"] and ocr_part in pair["ocr"]:
            return pair
    return None


def render_markdown(report: dict[str, Any]) -> str:
    pieces = report["pieces"]
    wrong = pieces[PIECE_WRONG_LINE]
    same = pieces[PIECE_SAME_LINE]
    buckets = report["underlying"]["buckets"]
    notice = _find_pair(report, "source4-zbtb.pdf", 5, "采购公告", "评分法")
    garbled = _find_pair(report, "source4-zbtb.pdf", 5, "点击左侧菜单", "【与】")
    bid_open = _find_pair(report, "pub-gx-youjiang-ultrasound.pdf", 5, "开标时间", "开标地点")
    lines = [
        "# Substitution split of the 395 wrong characters (pending_audit)",
        "",
        "Evidence note only. Recognition, the scoring formula, the thresholds, the ground truth, render scale, `max_side_len`, and the OCR model are unchanged. The greedy line matcher is unchanged. OCR was not re-run. No character was deleted. No letterhead was masked. OCR text was not copied into the ground truth. `outputs/pilot-ledger.csv` and `outputs/icp-outreach.csv` were not touched. T-005 stays blocked.",
        "",
        "This split does not pass any gate. The underlying line CER stays **1302/29835 (4.36%) GATE_FAIL**. Key-field F1 stays **97.17%**. TEDS stays **95.80%**. Overall gate stays **GATE_FAIL**. `product_pass` stays false.",
        "",
        f"Scored pages: **{report['pages']}**. Denominator: **{report['line_denom']}**. Line edits: **{report['line_edits']}**. Substitution characters labeled: **{report['substitution_characters']}**. Piece sum: **{report['piece_sum']}**. Remainder against 395: **{report['remainder']}**.",
        "",
        "## Exclusive rule",
        "",
        report["exclusive_rule"],
        "",
        "Piece 1 is a whole ground-truth line paired to the wrong OCR line. The substitutions on that pair are the character differences of the bad pairing. Piece 2 is every remaining substitution. On this set, piece 2 is mostly one wrong character inside a line that otherwise matches. One pair in piece 2 is a heavily damaged reading of its own line; it is described with the page 5 boundary below, and it was not forced into piece 1. A character is in one piece only. The same-text guard kept "
        f"**{report['duplicate_guard_kept_in_piece_2']}** characters in piece 2 on this set.",
        "",
        "Letterhead substitutions already counted in the header bucket are not part of the 395. This walk excluded "
        f"**{report['letterhead_substitutions_excluded']}** of them, the same 15 paired letterhead substitutions as the seven-bucket table.",
        "",
        "## Piece totals",
        "",
        "| Piece | Characters |",
        "|---|---:|",
        f"| {PIECE_LABELS[PIECE_WRONG_LINE]} | {wrong} |",
        f"| {PIECE_LABELS[PIECE_SAME_LINE]} | {same} |",
        f"| Sum | {report['piece_sum']} |",
        f"| Remainder against 395 | {report['remainder']} |",
        "",
        f"{wrong} + {same} = {report['piece_sum']}. Remainder against 395 is {report['remainder']}.",
        "",
        "The other six bucket totals are unchanged: not in the text layer "
        f"**{buckets['not_in_text_layer']}**, header or letterhead **{buckets['header_letterhead']}**, "
        f"whole-line miss **{buckets['whole_line_miss']}**, missing span inside a paired line **{buckets['paired_line_gap']}**, "
        f"extra inserted characters **{buckets['extra_insertion']}**, unaligned fragments **{buckets['fragment']}**. "
        "The substitution bucket stays **395**. The line-edit total stays **1302**. None of these labels passes a gate.",
        "",
        "## 1. Whole line paired to the wrong OCR line",
        "",
        f"Total: **{wrong}** characters.",
        "",
        "Pages in this piece, sorted by character count. The column sums to the piece total.",
        "",
        "| source file | page | characters in this piece |",
        "|---|---:|---:|",
    ]
    for row in _dominant(report["page_rows"], PIECE_WRONG_LINE):
        lines.append(f"| {row['filename']} | {row['page']} | {row[PIECE_WRONG_LINE]} |")
    lines += [
        "",
        "## 2. True wrong characters inside a correctly paired line",
        "",
        f"Total: **{same}** characters.",
        "",
        "Pages in this piece, sorted by character count. The column sums to the piece total.",
        "",
        "| source file | page | characters in this piece |",
        "|---|---:|---:|",
    ]
    for row in _dominant(report["page_rows"], PIECE_SAME_LINE):
        lines.append(f"| {row['filename']} | {row['page']} | {row[PIECE_SAME_LINE]} |")
    lines += [
        "",
        "## Audit example on source4-zbtb.pdf page 5",
        "",
    ]
    if notice is None:
        lines.append(
            "The procurement-notice line was not found paired to a scoring-method line in the current substitutions. Nothing was forced into piece 1 to match that example."
        )
    else:
        lines += [
            f"The procurement-notice ground-truth line is paired to the scoring-method OCR line. That pair has **{notice['chars']}** substitution characters, and the rule places them in **piece 1** because both structural tests match.",
            "",
            f"Ground truth: `{notice['gt']}`",
            "",
            f"OCR line the matcher chose: `{notice['ocr']}`",
            "",
            f"That OCR line is character-for-character another ground-truth line on the page: `{notice['other_gt']}`.",
            "",
            f"The procurement-notice text itself is also present as a different OCR line: `{notice['other_ocr']}`. The matcher had already paired that OCR line to an earlier ground-truth line, so both structural tests match.",
            "",
            "This is one step of a shift on the same page, not a glyph error inside one line. The page's 105 substitution characters are 88 in piece 1 and 17 in piece 2.",
            "",
            "The same shift continues. The scoring-method ground-truth line is then paired to `七、对本次招标提出询问,请按以下方式联系。`, which is the next unmatched ground-truth line. Those 18 substitution characters are also piece 1.",
        ]
    if bid_open is not None:
        lines += [
            "",
            f"On `pub-gx-youjiang-ultrasound.pdf` page 5, `{bid_open['gt']}` is paired to `{bid_open['ocr']}`. That pair has **{bid_open['chars']}** substitution characters in piece 1, because the OCR line is the other ground-truth line. This label does not join those lines. The matcher is unchanged.",
        ]
    lines += ["", "## Boundary that stayed in piece 2", ""]
    if garbled is None:
        lines.append("The garbled menu pair on source4-zbtb.pdf page 5 was not found.")
    else:
        lines += [
            f"On the same page, `{garbled['gt']}` is paired to `{garbled['ocr']}`.",
            "",
            f"That pair has **{garbled['chars']}** substitution characters. The OCR line is not equal to any other ground-truth line, and this ground-truth line is not equal to any other OCR line, so the rule leaves them in **piece 2**. They were not moved into piece 1 to enlarge the wrong-line total. The reading is heavily damaged. It is still the paired line's own OCR string, not the scoring-method line.",
            "",
            "The other piece-2 characters are short disagreements on lines that otherwise match, including em dash read as 一, 〔〕 read as parentheses, and o read as 0. Five of them are on pub-gx-youjiang-ultrasound.pdf page 6, where the hotline line matches except the redacted phone span in the text layer. Those five stay in piece 2 because neither structural test matches. They are not a third piece.",
        ]
    lines += [
        "",
        "## Every substitution pair",
        "",
        "One row per current greedy pair that contributes substitution characters. Letterhead pairs are omitted. The character column sums to 395. `other line` is the ground-truth or OCR line that made the structural test true.",
        "",
        "| piece | source file | page | chars | reason | ground truth | ocr line | other line |",
        "|---|---|---:|---:|---|---|---|---|",
    ]
    reason_label = {
        "ocr_equals_other_gt": "ocr equals another ground-truth line",
        "gt_equals_other_ocr": "ground truth equals another ocr line",
        "both": "both tests",
        "same_line": "same line",
    }
    for pair in report["pairs"]:
        other = pair["other_gt"] or pair["other_ocr"] or ""
        lines.append(
            "| {piece} | {filename} | {page} | {chars} | {reason} | {gt} | {ocr} | {other} |".format(
                piece="1" if pair["piece"] == PIECE_WRONG_LINE else "2",
                filename=pair["filename"],
                page=pair["page"],
                chars=pair["chars"],
                reason=reason_label[pair["reason"]],
                gt=_preview(pair["gt"]),
                ocr=_preview(pair["ocr"]),
                other=_preview(other),
            )
        )
    lines += [
        "",
        "## Page check against the substitution bucket",
        "",
        "For every page that has substitution characters, the two pieces sum to that page's substitution count from the seven-bucket table. Pages with no substitutions are omitted. Those page sums total 395.",
        "",
        "| source file | page | piece 1 | piece 2 | substitution |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["page_rows"]:
        lines.append(
            f"| {row['filename']} | {row['page']} | {row['wrong_line_pairing']} | {row['same_line_misread']} | {row['substitution']} |"
        )
    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv run python -m work.eval.substitution_split",
        "```",
        "",
        "The command rewrites only `outputs/ocr-benchmark/substitution-split-395.md` and `.json`. It does not write a pilot or ICP ledger, it does not call OCR, and it does not change the seven-bucket files.",
        "",
        f"Generated at `{report['generated_at']}`. Status: `pending_audit`.",
        "",
    ]
    return "\n".join(lines)


def write_reports(report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = classify_substitution_split() if report is None else report
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    _REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _ok(report: dict[str, Any]) -> bool:
    buckets = report["live_buckets"]
    return (
        report["remainder"] == 0
        and report["piece_sum"] == 395
        and report["substitution_characters"] == 395
        and report["line_edits"] == 1302
        and report["line_denom"] == 29835
        and report["pages"] == 54
        and         report["letterhead_substitutions_excluded"] == 15
        and report["page_substitution_matches_seven_buckets"] is True
        and buckets == report["underlying"]["buckets"]
        and sum(buckets.values()) == 1302
    )


def main() -> int:
    report = write_reports()
    print(
        json.dumps(
            {
                "pages": report["pages"],
                "line_edits": report["line_edits"],
                "line_denom": report["line_denom"],
                "pieces": report["pieces"],
                "piece_sum": report["piece_sum"],
                "remainder": report["remainder"],
                "letterhead_substitutions_excluded": report["letterhead_substitutions_excluded"],
                "duplicate_guard_kept_in_piece_2": report["duplicate_guard_kept_in_piece_2"],
                "live_buckets": report["live_buckets"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if _ok(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
