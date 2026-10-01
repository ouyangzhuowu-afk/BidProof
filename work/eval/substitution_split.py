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
from work.eval.ocr_benchmark import _norm
from work.eval.public_expand import (
    CER_GT_PATH,
    CER_HYP_PATH,
    OUT_DIR,
    _read_jsonl,
    is_synthetic_row,
    is_toc_page,
    prepare_expanded_cer,
    redact_text,
    segment_toc_lines,
)

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
    "Piece 1 compares the original line text, before _norm. Spaces and case stay. "
    "A character is piece 1 when its pair meets either structural test on that original "
    "text, and piece 2 when it meets neither. Test A: the OCR line the matcher chose "
    "is equal to a different ground-truth line on the same page. Test B: this "
    "ground-truth line is equal to a different OCR line on the same page, and that "
    "other OCR line is not paired to another ground-truth line with this same original "
    "text. The same-text guard stops a repeated line's own misread from being called "
    "a wrong line when the other copy was read exactly. If both tests match, the "
    "character is piece 1 once. Equality after deleting whitespace or lowercasing is "
    "not a whole-line mismatch. _norm (NFKC, all whitespace removed, English "
    "lowercased) is not the comparison. Piece 2 is every remaining substitution character."
)

AUDIT_CHECK = {PIECE_WRONG_LINE: 208, PIECE_SAME_LINE: 187}

_REPORT_MD = OUT_DIR / "substitution-split-395.md"
_REPORT_JSON = OUT_DIR / "substitution-split-395.json"


def _show_spaces(text: str) -> str:
    """Make spaces visible. The stored characters are not rewritten."""
    return text.replace(" ", "␣").replace("\t", "→")


def _source_lines(gt_row: dict[str, Any], hyp_row: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Lines that enter scoring, before _norm strips spaces and case.

    TOC segmentation already folds those lines. Body lines keep the stored text.
    """
    text_gt = str(gt_row.get("text_gt") or "")
    raw_lines = hyp_row.get("lines_hyp")
    source = [str(item) for item in raw_lines] if isinstance(raw_lines, list) else None
    if is_toc_page(text_gt):
        gt_lines = segment_toc_lines([line for line in text_gt.splitlines() if _norm(line)])
        hyp_source = source if source is not None else str(hyp_row.get("text_hyp") or "").splitlines()
        hyp_lines = segment_toc_lines([redact_text(line) for line in hyp_source])
    elif source is not None:
        hyp_lines = [redact_text(line) for line in source if _norm(redact_text(line))]
        gt_lines = [line for line in text_gt.splitlines() if _norm(line)]
    else:
        hyp_lines = [line for line in str(hyp_row.get("text_hyp") or "").splitlines() if _norm(line)]
        gt_lines = [line for line in text_gt.splitlines() if _norm(line)]
    return gt_lines, hyp_lines


def _group_raw(raw_lines: list[str], joined_norms: list[str]) -> list[list[str]]:
    """Map each scoring line back to the original lines whose _norm concatenation it is."""
    norms = [_norm(line) for line in raw_lines]
    groups: list[list[str]] = []
    cursor = 0
    for joined in joined_norms:
        start = cursor
        acc = ""
        while cursor < len(norms) and len(acc) < len(joined):
            acc += norms[cursor]
            cursor += 1
        if acc != joined:
            raise ValueError("prepared line does not match the original lines before _norm")
        groups.append(raw_lines[start:cursor])
    if cursor != len(norms):
        raise ValueError("original lines were left over after mapping scoring lines")
    return groups


def _raw_scoring_lines() -> dict[tuple[str, int], tuple[list[str], list[str]]]:
    gt_rows = [
        row
        for row in _read_jsonl(CER_GT_PATH)
        if row.get("scored") is not False and not is_synthetic_row(row)
    ]
    hyp_rows = _read_jsonl(CER_HYP_PATH)
    hyp_by = {(str(row.get("doc_id")), int(row.get("page") or 0)): row for row in hyp_rows}
    prepared_gt, prepared_hyp = prepare_expanded_cer(gt_rows, hyp_rows)
    raw_by_page: dict[tuple[str, int], tuple[list[str], list[str]]] = {}
    for gt_row, prep_gt, prep_hyp in zip(gt_rows, prepared_gt, prepared_hyp):
        key = (str(gt_row.get("doc_id")), int(gt_row.get("page") or 0))
        joined = [_norm(line) for line in str(prep_gt.get("text_gt") or "").splitlines() if _norm(line)]
        gt_src, _hyp_src = _source_lines(gt_row, hyp_by[key])
        raw_refs = ["".join(group) for group in _group_raw(gt_src, joined)]
        raw_field = prep_hyp.get("lines_hyp")
        if isinstance(raw_field, list):
            raw_hyps = [str(line) for line in raw_field if _norm(str(line))]
        else:
            raw_hyps = [line for line in str(prep_hyp.get("text_hyp") or "").splitlines() if _norm(line)]
        if [_norm(line) for line in raw_refs] != joined:
            raise ValueError(f"raw ground-truth lines do not norm back to the scoring lines on {key}")
        raw_by_page[key] = (raw_refs, raw_hyps)
    return raw_by_page


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
    raw_by_page = _raw_scoring_lines()
    totals: Counter[str] = Counter()
    page_counts: dict[tuple[str, int], Counter[str]] = {}
    pairs: list[dict[str, Any]] = []
    flips: list[dict[str, Any]] = []
    kept = 0
    letterhead_substitutions = 0
    duplicate_guard_kept_in_piece_2 = 0
    denom = 0
    for page in pages:
        doc_id, page_no = page["key"]
        filename = filenames.get(doc_id, doc_id)
        refs: list[str] = page["refs"]
        hyps: list[str] = page["hyps"]
        raw_refs, raw_hyps = raw_by_page[page["key"]]
        if [_norm(line) for line in raw_refs] != refs or [_norm(line) for line in raw_hyps] != hyps:
            raise ValueError(f"raw lines do not match the scored lines on {filename} page {page_no}")
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
            raw_ref = raw_refs[ref_index]
            raw_hyp = raw_hyps[hyp_index]
            ops = _align_ops(ref, hyp)
            sub_count = sum(1 for op, _ref_char, _hyp_char in ops if op == "S")
            if not sub_count:
                continue
            letterhead = _is_masthead_or_logo(hyp, hyps) and not _in_text(hyp, text, folded)
            if letterhead:
                letterhead_substitutions += sub_count
                continue
            other_gt = _other_gt_index(raw_hyp, ref_index, raw_refs)
            displaced = _displaced_ocr_index(raw_ref, hyp_index, raw_refs, raw_hyps, owner)
            other_gt_norm = _other_gt_index(hyp, ref_index, refs)
            displaced_norm = _displaced_ocr_index(ref, hyp_index, refs, hyps, owner)
            if other_gt is None and displaced is None and _same_text_ocr_only(raw_ref, hyp_index, raw_refs, raw_hyps, owner):
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
            norm_piece_1 = other_gt_norm is not None or displaced_norm is not None
            kept += sub_count
            totals[piece] += sub_count
            page_counts.setdefault((filename, page_no), Counter())[piece] += sub_count
            pair = {
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
                "gt_raw": raw_ref,
                "ocr_raw": raw_hyp,
                "other_gt": None if other_gt is None else raw_refs[other_gt],
                "other_ocr": None if displaced is None else raw_hyps[displaced],
                "norm_would_be_piece_1": norm_piece_1,
            }
            pairs.append(pair)
            if norm_piece_1 and piece == PIECE_SAME_LINE:
                flips.append(
                    {
                        "filename": filename,
                        "page": page_no,
                        "chars": sub_count,
                        "gt_raw": raw_ref,
                        "ocr_raw": raw_hyp,
                        "gt_raw_visible": _show_spaces(raw_ref),
                        "ocr_raw_visible": _show_spaces(raw_hyp),
                        "norm_other_gt_raw": None if other_gt_norm is None else raw_refs[other_gt_norm],
                        "norm_other_ocr_raw": None if displaced_norm is None else raw_hyps[displaced_norm],
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
        "comparison": "raw_text_before_norm",
        "exclusive_rule": EXCLUSIVE_RULE,
        "audit_check": AUDIT_CHECK,
        "matches_audit_check": {piece: totals[piece] for piece in PIECE_ORDER} == AUDIT_CHECK,
        "whitespace_or_case_flips": flips,
        "whitespace_or_case_pairs": len(flips),
        "whitespace_or_case_chars": sum(item["chars"] for item in flips),
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
        "Piece 1 is a whole ground-truth line paired to the wrong OCR line, judged on the original line text. Piece 2 is every remaining substitution character. A character is in one piece only. The same-text guard kept "
        f"**{report['duplicate_guard_kept_in_piece_2']}** characters in piece 2 on this set.",
        "",
        f"Audit's raw-text check is **{report['audit_check'][PIECE_WRONG_LINE]}** whole-line mismatches and **{report['audit_check'][PIECE_SAME_LINE]}** true in-line misreads. This recount is **{wrong}** and **{same}**.",
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
        f"Next to audit's check: this recount is {wrong} and {same}; audit's check is {report['audit_check'][PIECE_WRONG_LINE]} and {report['audit_check'][PIECE_SAME_LINE]}.",
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
        "## Pairs that match only after spaces or case are folded",
        "",
        "These pairs are whole-line mismatches under `_norm` and are not whole-line mismatches on the original text. "
        f"There are **{report['whitespace_or_case_pairs']}** pairs and **{report['whitespace_or_case_chars']}** characters. "
        "They are listed here, outside piece 1. They sit in piece 2. `␣` is a space.",
        "",
    ]
    if not report["whitespace_or_case_flips"]:
        lines.append("No pair flips only because of spaces or case.")
    for index, flip in enumerate(report["whitespace_or_case_flips"], 1):
        lines += [
            f"### {index}. `{flip['filename']}` page {flip['page']} — {flip['chars']} characters",
            "",
            "Ground truth:",
            "",
            "```",
            flip["gt_raw_visible"],
            "```",
            "",
            "OCR:",
            "",
            "```",
            flip["ocr_raw_visible"],
            "```",
            "",
        ]
        if flip.get("norm_other_gt_raw"):
            lines += [
                "The normalized OCR line equals this other ground-truth line only after `_norm`. That other line's original text is:",
                "",
                "```",
                _show_spaces(flip["norm_other_gt_raw"]),
                "```",
                "",
            ]
        if flip.get("norm_other_ocr_raw"):
            lines += [
                "This ground-truth line equals this other OCR line only after `_norm`. That other line's original text is:",
                "",
                "```",
                _show_spaces(flip["norm_other_ocr_raw"]),
                "```",
                "",
            ]
    lines += [
        "",
        "## Audit example on source4-zbtb.pdf page 5",
        "",
    ]
    if notice is None:
        lines.append(
            "The procurement-notice line was not found paired to a scoring-method line in the current substitutions."
        )
    else:
        piece_name = "1" if notice["piece"] == PIECE_WRONG_LINE else "2"
        lines += [
            f"The procurement-notice ground-truth line is paired to the scoring-method OCR line. That pair has **{notice['chars']}** substitution characters. Raw-text equality places them in **piece {piece_name}**.",
            "",
            "Ground truth:",
            "",
            "```",
            _show_spaces(notice["gt_raw"]),
            "```",
            "",
            "OCR:",
            "",
            "```",
            _show_spaces(notice["ocr_raw"]),
            "```",
            "",
            "The ground-truth scoring line keeps a space before 分 and a trailing space (`总分100␣分。␣`). The scoring OCR line is `总分100分`. Those original strings are not equal, so this pair is not piece 1.",
        ]
    if bid_open is not None:
        piece_name = "1" if bid_open["piece"] == PIECE_WRONG_LINE else "2"
        lines += [
            "",
            f"On `pub-gx-youjiang-ultrasound.pdf` page 5, the 开标时间 line is paired to the 开标地点 line. That pair has **{bid_open['chars']}** substitution characters in piece {piece_name}. This label does not join those lines. The matcher is unchanged.",
        ]
    lines += ["", "## Boundary that stayed in piece 2", ""]
    if garbled is None:
        lines.append("The garbled menu pair on source4-zbtb.pdf page 5 was not found.")
    else:
        lines += [
            f"On the same page, `{garbled['gt']}` is paired to `{garbled['ocr']}`.",
            "",
            f"That pair has **{garbled['chars']}** substitution characters. The OCR line is not equal to any other ground-truth line, and this ground-truth line is not equal to any other OCR line, so the rule leaves them in **piece 2**. The reading is heavily damaged. It is the paired line's own OCR string, not the scoring-method line.",
            "",
            "Piece 2 also holds the pairs listed above that match another line only after spaces or case are folded. Those characters are not piece 1. The remaining piece-2 characters include short disagreements on lines that otherwise match, such as an em dash read as 一, 〔〕 read as parentheses, and o read as 0.",
        ]
    lines += [
        "",
        "## Every substitution pair",
        "",
        "One row per current greedy pair that contributes substitution characters. Letterhead pairs are omitted. The character column sums to 395. Strings are the original line text; `␣` is a space. `other line` is the original line that made a raw-text test true.",
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
                gt=_preview(_show_spaces(pair["gt_raw"])),
                ocr=_preview(_show_spaces(pair["ocr_raw"])),
                other=_preview(_show_spaces(other)),
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
        and report["letterhead_substitutions_excluded"] == 15
        and report["page_substitution_matches_seven_buckets"] is True
        and report["matches_audit_check"] is True
        and report["whitespace_or_case_pairs"] == 7
        and report["whitespace_or_case_chars"] == 116
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
                "matches_audit_check": report["matches_audit_check"],
                "whitespace_or_case_pairs": report["whitespace_or_case_pairs"],
                "whitespace_or_case_chars": report["whitespace_or_case_chars"],
                "live_buckets": report["live_buckets"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if _ok(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
