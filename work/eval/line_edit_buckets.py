"""Classify the current 1302 expanded-set line edits into seven buckets.

Evidence only. This module does not change recognition, the scoring formula,
thresholds, ground truth, render scale, or any OCR model. It reads the same
prepared lines the line-CER gate already scores.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from work.eval.collect_public_tenders import load_manifest
from work.eval.ocr_benchmark import _norm, levenshtein
from work.eval.public_expand import (
    CER_GT_PATH,
    CER_HYP_PATH,
    MANIFEST,
    OUT_DIR,
    _fold_dash,
    _read_jsonl,
    is_synthetic_row,
    prepare_expanded_cer,
)

BUCKET_ORDER = (
    "not_in_text_layer",
    "header_letterhead",
    "whole_line_miss",
    "paired_line_gap",
    "substitution",
    "extra_insertion",
    "fragment",
)

BUCKET_LABELS = {
    "not_in_text_layer": "1. Not in the text layer",
    "header_letterhead": "2. Header or letterhead",
    "whole_line_miss": "3. Whole-line miss",
    "paired_line_gap": "4. Missing span inside an already paired line",
    "substitution": "5. Wrong character (substitution)",
    "extra_insertion": "6. Extra characters the recognizer inserted",
    "fragment": "7. Fragment lines that never aligned",
}

EXCLUSIVE_RULE = (
    "Each of the 1302 edit characters is assigned by the first matching rule. "
    "A character that also fits a later description stays in the earlier bucket. "
    "1) Fragment: a still-separate text-layer piece of length 1–2 that contains a CJK "
    "character and tiles an unused OCR line from left to right, plus that OCR line; "
    "or an unmatched one-character date particle (年/月/日/时/分/点) and the unused OCR "
    "line that contains it. "
    "2) Header or letterhead: an inserted character of an OCR line that is a masthead, "
    "logo, English legal-name line, short agency fragment of that masthead, garbled "
    "logo token 帐iii, or a 第N章 running header; plus a substitution on a paired line "
    "whose whole OCR line is a masthead or logo and is not itself in the page text layer. "
    "A deletion of a body character stays a missing span even when the paired OCR line "
    "is a letterhead. "
    "3) Not in the text layer: a remaining insertion, either a whole unused OCR line or "
    "one consecutive insertion run inside a paired line, whose text is not a substring "
    "of the normalized page text layer. "
    "4) Whole-line miss: a remaining character of a ground-truth line the greedy matcher "
    "never paired, of any length. "
    "5) Missing span: a remaining deletion inside a line that was paired. "
    "6) Wrong character: a remaining substitution. "
    "7) Extra insertion: a remaining insertion whose text is a substring of the page text layer. "
    "Short deletions are not a bucket. An unmatched short line is rule 4 unless rule 1 "
    "took it. A short gap inside a paired line is rule 5."
)

_CHAPTER_RE = re.compile(r"^第[0-9一二三四五六七八九十百]+章")
_MASTHEAD_RE = re.compile(r"项目管理有限公司|招标有限公司|projectmanagement|co\.,lt")
_LOGO_TOKENS = frozenset({"cpil", "帐iii"})
_DATE_PARTICLES = frozenset("年月日时分点")
_REPORT_MD = OUT_DIR / "line-edit-seven-buckets.md"
_REPORT_JSON = OUT_DIR / "line-edit-seven-buckets.json"


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _align_ops(ref: str, hyp: str) -> list[tuple[str, str, str]]:
    """Substitution-preferring unit-cost alignment. Tie order: sub, delete, insert."""
    width = len(hyp)
    prev = list(range(width + 1))
    rows = [prev]
    for ref_index, ref_char in enumerate(ref, 1):
        cur = [ref_index]
        for hyp_index, hyp_char in enumerate(hyp, 1):
            cur.append(
                min(
                    prev[hyp_index - 1] + (ref_char != hyp_char),
                    prev[hyp_index] + 1,
                    cur[hyp_index - 1] + 1,
                )
            )
        rows.append(cur)
        prev = cur
    ops: list[tuple[str, str, str]] = []
    ref_index, hyp_index = len(ref), len(hyp)
    while ref_index or hyp_index:
        if (
            ref_index
            and hyp_index
            and rows[ref_index][hyp_index]
            == rows[ref_index - 1][hyp_index - 1] + (ref[ref_index - 1] != hyp[hyp_index - 1])
        ):
            ref_char = ref[ref_index - 1]
            hyp_char = hyp[hyp_index - 1]
            ops.append(("S" if ref_char != hyp_char else "M", ref_char, hyp_char))
            ref_index -= 1
            hyp_index -= 1
            continue
        if ref_index and rows[ref_index][hyp_index] == rows[ref_index - 1][hyp_index] + 1:
            ops.append(("D", ref[ref_index - 1], ""))
            ref_index -= 1
            continue
        ops.append(("I", "", hyp[hyp_index - 1]))
        hyp_index -= 1
    ops.reverse()
    return ops


def _greedy(refs: list[str], hyps: list[str]) -> tuple[list[int | None], list[int]]:
    used: set[int] = set()
    pairs: list[int | None] = []
    for ref in refs:
        best_index: int | None = None
        best_distance = len(ref)
        for index, hyp in enumerate(hyps):
            if index in used:
                continue
            distance = levenshtein(ref, hyp)
            if distance < best_distance:
                best_distance = distance
                best_index = index
        pairs.append(best_index)
        if best_index is not None:
            used.add(best_index)
    unused = [index for index in range(len(hyps)) if index not in used]
    return pairs, unused


def _is_masthead_or_logo(line: str, ocr_lines: list[str]) -> bool:
    if line in _LOGO_TOKENS or _MASTHEAD_RE.search(line):
        return True
    if (
        4 <= len(line) <= 12
        and _has_cjk(line)
        and any(line != other and line in other and _MASTHEAD_RE.search(other) for other in ocr_lines)
    ):
        return True
    if len(line) == 1 and line.isascii() and line.isalpha():
        return any(_MASTHEAD_RE.search(other) for other in ocr_lines)
    return False


def _is_header_or_letterhead(line: str, ocr_lines: list[str]) -> bool:
    return _is_masthead_or_logo(line, ocr_lines) or bool(_CHAPTER_RE.match(line))


def _in_text(span: str, text: str, folded_text: str) -> bool:
    if not span:
        return False
    return span in text or _fold_dash(span) in folded_text


def _fragment_indexes(
    refs: list[str], hyps: list[str], pairs: list[int | None], unused: list[int]
) -> tuple[set[int], set[int]]:
    """GT indexes and OCR indexes whose edit characters are unaligned fragments."""
    unmatched = [(index, refs[index]) for index, hyp_index in enumerate(pairs) if hyp_index is None]
    pieces = [
        (index, text)
        for index, text in unmatched
        if 1 <= len(text) <= 2 and _has_cjk(text)
    ]
    used_pieces: set[int] = set()
    frag_gt: set[int] = set()
    frag_ocr: set[int] = set()
    for hyp_index in unused:
        remain = hyps[hyp_index]
        chosen: list[int] = []
        while remain:
            candidates = [
                (index, text)
                for index, text in pieces
                if index not in used_pieces and index not in chosen and remain.startswith(text)
            ]
            if not candidates:
                break
            index, text = max(candidates, key=lambda item: len(item[1]))
            chosen.append(index)
            remain = remain[len(text) :]
        if remain == "" and chosen:
            used_pieces.update(chosen)
            frag_gt.update(chosen)
            frag_ocr.add(hyp_index)
    for index, text in unmatched:
        if index in frag_gt or text not in _DATE_PARTICLES:
            continue
        for hyp_index in unused:
            if hyp_index in frag_ocr:
                continue
            if text in hyps[hyp_index]:
                frag_gt.add(index)
                frag_ocr.add(hyp_index)
                break
    return frag_gt, frag_ocr


def _filename_by_doc() -> dict[str, str]:
    names: dict[str, str] = {}
    manifest = load_manifest(MANIFEST)
    for row in manifest.get("documents") or []:
        if not isinstance(row, dict):
            continue
        doc_id = str(row.get("document_id") or "")
        filename = str(row.get("filename") or "")
        if doc_id and filename:
            names[doc_id] = filename
    return names


def _prepared_pages() -> list[dict[str, Any]]:
    gt_rows = [
        row
        for row in _read_jsonl(CER_GT_PATH)
        if row.get("scored") is not False and not is_synthetic_row(row)
    ]
    originals = {
        (str(row["doc_id"]), int(row["page"])): _norm(str(row.get("text_gt") or ""))
        for row in gt_rows
    }
    prepared_gt, prepared_hyp = prepare_expanded_cer(gt_rows, _read_jsonl(CER_HYP_PATH))
    pages: list[dict[str, Any]] = []
    for gt, hyp in zip(prepared_gt, prepared_hyp):
        key = (str(gt["doc_id"]), int(gt["page"]))
        refs = [_norm(line) for line in str(gt.get("text_gt") or "").splitlines() if _norm(line)]
        raw_lines = hyp.get("lines_hyp")
        if isinstance(raw_lines, list):
            hyps = [_norm(str(line)) for line in raw_lines if _norm(str(line))]
        else:
            hyps = [_norm(line) for line in str(hyp.get("text_hyp") or "").splitlines() if _norm(line)]
        pages.append({"key": key, "refs": refs, "hyps": hyps, "text": originals[key]})
    return pages


def _add(
    page_counts: Counter[str],
    samples: list[dict[str, Any]],
    bucket: str,
    text: str,
    kind: str,
    *,
    chars: int | None = None,
) -> None:
    count = len(text) if chars is None else chars
    if not count:
        return
    page_counts[bucket] += count
    samples.append({"bucket": bucket, "kind": kind, "chars": count, "text": text[:80]})


def _flush_insertion(
    insertion: list[str],
    *,
    letterhead_pair: bool,
    text: str,
    folded: str,
    counts: Counter[str],
    samples: list[dict[str, Any]],
) -> None:
    if not insertion:
        return
    span = "".join(insertion)
    insertion.clear()
    if letterhead_pair:
        _add(counts, samples, "header_letterhead", span, "paired_letterhead_insertion")
    elif not _in_text(span, text, folded):
        _add(counts, samples, "not_in_text_layer", span, "paired_insertion")
    else:
        _add(counts, samples, "extra_insertion", span, "paired_insertion")


def classify_page(page: dict[str, Any]) -> tuple[Counter[str], list[dict[str, Any]], int]:
    refs: list[str] = page["refs"]
    hyps: list[str] = page["hyps"]
    text: str = page["text"]
    folded = _fold_dash(text)
    pairs, unused = _greedy(refs, hyps)
    frag_gt, frag_ocr = _fragment_indexes(refs, hyps, pairs, unused)
    counts: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    edits = 0
    for ref_index, hyp_index in enumerate(pairs):
        ref = refs[ref_index]
        if hyp_index is None:
            edits += len(ref)
            if ref_index in frag_gt:
                _add(counts, samples, "fragment", ref, "unmatched_gt_piece")
            else:
                _add(counts, samples, "whole_line_miss", ref, "unmatched_gt_line")
            continue
        hyp = hyps[hyp_index]
        ops = _align_ops(ref, hyp)
        letterhead_pair = _is_masthead_or_logo(hyp, hyps) and not _in_text(hyp, text, folded)
        insertion: list[str] = []
        for op, ref_char, hyp_char in ops:
            if op == "M":
                _flush_insertion(
                    insertion,
                    letterhead_pair=letterhead_pair,
                    text=text,
                    folded=folded,
                    counts=counts,
                    samples=samples,
                )
                continue
            edits += 1
            if op == "I":
                insertion.append(hyp_char)
                continue
            _flush_insertion(
                insertion,
                letterhead_pair=letterhead_pair,
                text=text,
                folded=folded,
                counts=counts,
                samples=samples,
            )
            if op == "S" and letterhead_pair:
                _add(
                    counts,
                    samples,
                    "header_letterhead",
                    ref_char + "/" + hyp_char,
                    "paired_letterhead_substitution",
                    chars=1,
                )
            elif op == "D":
                _add(counts, samples, "paired_line_gap", ref_char, "paired_deletion")
            else:
                _add(
                    counts,
                    samples,
                    "substitution",
                    ref_char + "/" + hyp_char,
                    "substitution",
                    chars=1,
                )
        _flush_insertion(
            insertion,
            letterhead_pair=letterhead_pair,
            text=text,
            folded=folded,
            counts=counts,
            samples=samples,
        )
    for hyp_index in unused:
        line = hyps[hyp_index]
        edits += len(line)
        if hyp_index in frag_ocr:
            _add(counts, samples, "fragment", line, "unused_fragment_line")
        elif _is_header_or_letterhead(line, hyps):
            _add(counts, samples, "header_letterhead", line, "unused_header_line")
        elif not _in_text(line, text, folded):
            _add(counts, samples, "not_in_text_layer", line, "unused_ocr_line")
        else:
            _add(counts, samples, "extra_insertion", line, "unused_ocr_line")
    return counts, samples, edits


def classify_line_edits() -> dict[str, Any]:
    filenames = _filename_by_doc()
    pages = _prepared_pages()
    totals: Counter[str] = Counter()
    page_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    edit_sum = 0
    denom = 0
    for page in pages:
        counts, samples, edits = classify_page(page)
        doc_id, page_no = page["key"]
        denom += sum(len(line) for line in page["refs"])
        edit_sum += edits
        for bucket in BUCKET_ORDER:
            totals[bucket] += counts[bucket]
        filename = filenames.get(doc_id, doc_id)
        if edits:
            page_rows.append(
                {
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": page_no,
                    "edits": edits,
                    **{bucket: counts[bucket] for bucket in BUCKET_ORDER},
                }
            )
        for sample in samples:
            if sample["bucket"] in {"header_letterhead", "fragment", "not_in_text_layer"}:
                evidence.append(
                    {
                        "doc_id": doc_id,
                        "filename": filename,
                        "page": page_no,
                        **sample,
                    }
                )
    bucket_sum = sum(totals[bucket] for bucket in BUCKET_ORDER)
    report = {
        "leaf_id": "S-A-OCR-PUBLIC-EXPAND",
        "status": "pending_audit",
        "claim_scope": "error_classification_only",
        "product_pass": False,
        "business_pass": False,
        "t005_modified": False,
        "gate": "GATE_FAIL",
        "line_cer_gate": "GATE_FAIL",
        "generated_at": datetime.now(UTC).astimezone().isoformat(),
        "pages": len(pages),
        "line_edits": edit_sum,
        "line_denom": denom,
        "line_cer": (edit_sum / denom) if denom else None,
        "buckets": {bucket: totals[bucket] for bucket in BUCKET_ORDER},
        "bucket_sum": bucket_sum,
        "remainder": edit_sum - bucket_sum,
        "exclusive_rule": EXCLUSIVE_RULE,
        "underlying": {
            "line_edits": 1302,
            "line_denom": 29835,
            "line_cer_display": "4.36%",
            "line_cer_gate": "GATE_FAIL",
            "key_field_f1_display": "97.17%",
            "teds_display": "95.80%",
            "gate": "GATE_FAIL",
            "product_pass": False,
            "note": "Unchanged measurements. This table does not pass a gate.",
        },
        "page_rows": sorted(page_rows, key=lambda row: (-row["edits"], row["filename"], row["page"])),
        "evidence": evidence,
    }
    return report


def _dominant(rows: list[dict[str, Any]], bucket: str, limit: int = 8) -> list[dict[str, Any]]:
    ranked = [row for row in rows if row.get(bucket)]
    ranked.sort(key=lambda row: (-row[bucket], row["filename"], row["page"]))
    return ranked[:limit]


def render_markdown(report: dict[str, Any]) -> str:
    buckets = report["buckets"]
    lines = [
        "# Line-edit seven-bucket classification (pending_audit)",
        "",
        "Evidence note only. Recognition, the scoring formula, the thresholds, the ground truth, render scale, `max_side_len`, and the OCR model are unchanged. OCR was not re-run. No character was deleted. No letterhead was masked. OCR text was not copied into the ground truth. `outputs/pilot-ledger.csv` and `outputs/icp-outreach.csv` were not touched. T-005 stays blocked.",
        "",
        "This table does not pass any gate. The underlying line CER stays **1302/29835 (4.36%) GATE_FAIL**. Key-field F1 stays **97.17%**. TEDS stays **95.80%**. Overall gate stays **GATE_FAIL**. `product_pass` stays false.",
        "",
        f"Scored pages: **{report['pages']}**. Denominator: **{report['line_denom']}**. Classified edits: **{report['line_edits']}**. Seven-bucket sum: **{report['bucket_sum']}**. Remainder: **{report['remainder']}**.",
        "",
        "## Exclusive rule",
        "",
        report["exclusive_rule"],
        "",
        "Earlier splits are hints, not targets. The counts below are this assignment. They are not forced back onto 337, 100, 242, 369, 50, or 32.",
        "",
        "## Bucket totals",
        "",
        "| # | Bucket | Characters |",
        "|---:|---|---:|",
    ]
    for index, bucket in enumerate(BUCKET_ORDER, 1):
        lines.append(f"| {index} | {BUCKET_LABELS[bucket]} | {buckets[bucket]} |")
    lines.append(f"| | Sum | {report['bucket_sum']} |")
    lines.append(f"| | Remainder against 1302 | {report['remainder']} |")
    lines += [
        "",
        f"{report['bucket_sum']} = "
        + " + ".join(str(buckets[bucket]) for bucket in BUCKET_ORDER)
        + f". Remainder {report['remainder']}. Denominator {report['line_denom']} across {report['pages']} pages.",
        "",
    ]
    for bucket in BUCKET_ORDER:
        lines += [
            f"## {BUCKET_LABELS[bucket]}",
            "",
            f"Total: **{buckets[bucket]}** characters.",
            "",
            "Pages that dominate this bucket:",
            "",
            "| source file | page | characters in this bucket |",
            "|---|---:|---:|",
        ]
        ranked = _dominant(report["page_rows"], bucket)
        if not ranked:
            lines.append("| — | — | 0 |")
        for row in ranked:
            lines.append(f"| {row['filename']} | {row['page']} | {row[bucket]} |")
        lines.append("")
    lines += [
        "## Page breakdown",
        "",
        "Every scored page with at least one edit. The seven columns sum to the page edit count, and the page edit counts sum to 1302.",
        "",
        "| source file | page | edits | not in text | header | whole line | paired gap | substitution | extra | fragment |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(report["page_rows"], key=lambda item: (-item["edits"], item["filename"], item["page"])):
        lines.append(
            "| {filename} | {page} | {edits} | {not_in_text_layer} | {header_letterhead} | "
            "{whole_line_miss} | {paired_line_gap} | {substitution} | {extra_insertion} | {fragment} |".format(
                **row
            )
        )
    lines += [
        "",
        "## Boundary examples",
        "",
        "On `source4-zbtb.pdf` page 4 the greedy matcher paired a body line with `北京数字支点国际项目管理有限公司`, which is not in that page's text layer. The 15 substitution edits on that pair are bucket 2. The deleted body characters on that same pair stay in bucket 4, because those characters are the body line, not the letterhead.",
        "",
        "`pub-gx-tianlin-yuegui-devices-2026.pdf` page 1 puts both the Chinese masthead `广西恒桥项目管理有限公司` (also present in the body, so this is a repeated header) and the English legal-name line into bucket 2. They are not left in bucket 1 or bucket 6.",
        "",
        "Running headers `第一章响应邀请` and `第四章采购需求` on `source2-nanjing.pdf` are bucket 2. The garbled logo token `帐iii` on the two 目录 pages is bucket 2. Garbage that is not a header stays in bucket 1, including the 24-character line on `source2-shaanxi.pdf` page 6 and `中,中,中,()` on `source4-zbtb.pdf` page 4.",
        "",
        "Bucket 7 is three pages only: `pub-gx-minzu-ultrasound-2026.pdf` page 6 (20), `pub-gx-tianlin-yuegui-devices-2026.pdf` page 8 (8), and `source2-nanjing.pdf` page 32 (4).",
        "",
        "The counts differ from the earlier hints where the definitions differ. Bucket 1 is 47 rather than about 337 because letterheads that used to sit inside the absent pile are bucket 2. Bucket 3 is 151 rather than about 100 because every unmatched ground-truth line is included, not only deletions of 6 or more characters. Bucket 4 is 363 rather than about 242 because short gaps inside paired lines are included. Bucket 5 is 395 rather than about 369. Bucket 6 is 28 rather than about 50 because repeated headers that are in the text layer were pulled into bucket 2. Bucket 7 is 32. None of these labels changes the 1302.",
        "",
        "## What went into header / letterhead and fragments",
        "",
        "Shown so the exclusive cut can be checked. A preview is the OCR or ground-truth span, truncated at 80 characters. Paired letterhead substitutions on one page are one row.",
        "",
        "| bucket | source file | page | chars | kind | preview |",
        "|---|---|---:|---:|---|---|",
    ]
    grouped: dict[tuple[str, str, int, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, int, str, str]] = []
    for item in report["evidence"]:
        if item["bucket"] not in {"header_letterhead", "fragment"}:
            continue
        # One row per span. Pair substitutions are one glyph each, so they share a row.
        text_key = "" if item["kind"] == "paired_letterhead_substitution" else str(item["text"])
        key = (
            str(item["bucket"]),
            str(item["filename"]),
            int(item["page"]),
            str(item["kind"]),
            text_key,
        )
        if key not in grouped:
            grouped[key] = {"chars": 0, "text": str(item["text"])}
            order.append(key)
        grouped[key]["chars"] += int(item["chars"])
    for key in order:
        bucket_name, filename, page_no, kind, _text_key = key
        preview = str(grouped[key]["text"]).replace("|", "/")
        if kind == "paired_letterhead_substitution":
            preview = f"{grouped[key]['chars']} substitutions; first {preview}"
        lines.append(
            f"| {bucket_name} | {filename} | {page_no} | {grouped[key]['chars']} | {kind} | {preview} |"
        )
    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv run python -m work.eval.line_edit_buckets",
        "```",
        "",
        "The command rewrites only `outputs/ocr-benchmark/line-edit-seven-buckets.md` and `.json`. It does not write a pilot or ICP ledger and it does not call OCR.",
        "",
        f"Generated at `{report['generated_at']}`. Status: `pending_audit`.",
        "",
    ]
    return "\n".join(lines)


def write_reports(report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = classify_line_edits() if report is None else report
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    _REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_reports()
    print(
        json.dumps(
            {
                "line_edits": report["line_edits"],
                "line_denom": report["line_denom"],
                "pages": report["pages"],
                "buckets": report["buckets"],
                "bucket_sum": report["bucket_sum"],
                "remainder": report["remainder"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["remainder"] == 0 and report["line_edits"] == 1302 else 1


if __name__ == "__main__":
    raise SystemExit(main())
