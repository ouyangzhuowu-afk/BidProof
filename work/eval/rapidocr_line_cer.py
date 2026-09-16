"""S-A-02: reproducible page-CER vs line-CER harness (engineering gate only).

Default command (sandbox public/synthetic labels):

  uv run python -m work.eval.rapidocr_line_cer

Writes `outputs/ocr-benchmark/line-cer-report.{md,json}` only.
Never writes `outputs/pilot-ledger.csv` or `outputs/icp-outreach.csv`.
Never claims product or business PASS. Line CER gate is ≤2%; otherwise GATE_FAIL.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from work.eval.ocr_benchmark import _norm, levenshtein
from work.eval.page_annotation import load_annotations

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATIONS = ROOT / "work" / "eval" / "fixtures" / "sandbox_pages.jsonl"
DEFAULT_HYPOTHESES = ROOT / "work" / "eval" / "fixtures" / "sandbox_hypotheses.jsonl"
DEFAULT_OUT_DIR = ROOT / "outputs" / "ocr-benchmark"
LINE_CER_GATE = 0.02
FORBIDDEN_OUTPUT_TOKENS = ("pilot-ledger", "icp-outreach")


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


class ForbiddenOutputError(ValueError):
    """Raised when a write target looks like a business ledger."""


def split_normalized_lines(text: str) -> list[str]:
    return [_norm(line) for line in (text or "").splitlines() if _norm(line)]


def line_cer(ref_text: str, hyp_text: str, hyp_lines: list[str] | None = None) -> float:
    """Micro-averaged line CER via greedy one-to-one matching (order-independent).

    This is intentionally not the same as page CER: a block-moved page can have
    high page CER and zero line CER.
    """
    refs = split_normalized_lines(ref_text)
    if hyp_lines is not None:
        hyps = [_norm(line) for line in hyp_lines if _norm(str(line))]
    else:
        hyps = split_normalized_lines(hyp_text)
    if not refs:
        return 0.0 if not hyps else 1.0
    denom = sum(len(item) for item in refs)
    used: set[int] = set()
    edits = 0
    for ref in refs:
        best_j: int | None = None
        best_d = len(ref)
        for index, hyp in enumerate(hyps):
            if index in used:
                continue
            distance = levenshtein(ref, hyp)
            if distance < best_d:
                best_d = distance
                best_j = index
        edits += best_d
        if best_j is not None:
            used.add(best_j)
    for index, hyp in enumerate(hyps):
        if index not in used:
            edits += len(hyp)
    return edits / denom


def _page_edits(ref_text: str, hyp_text: str) -> tuple[int, int]:
    ref_n, hyp_n = _norm(ref_text), _norm(hyp_text)
    if not ref_n:
        return (0, 0) if not hyp_n else (1, 1)
    return levenshtein(ref_n, hyp_n), len(ref_n)


def _line_edits(ref_text: str, hyp_text: str, hyp_lines: list[str] | None) -> tuple[int, int]:
    refs = split_normalized_lines(ref_text)
    if hyp_lines is not None:
        hyps = [_norm(line) for line in hyp_lines if _norm(str(line))]
    else:
        hyps = split_normalized_lines(hyp_text)
    if not refs:
        return (0, 0) if not hyps else (1, 1)
    denom = sum(len(item) for item in refs)
    used: set[int] = set()
    edits = 0
    for ref in refs:
        best_j: int | None = None
        best_d = len(ref)
        for index, hyp in enumerate(hyps):
            if index in used:
                continue
            distance = levenshtein(ref, hyp)
            if distance < best_d:
                best_d = distance
                best_j = index
        edits += best_d
        if best_j is not None:
            used.add(best_j)
    for index, hyp in enumerate(hyps):
        if index not in used:
            edits += len(hyp)
    return edits, denom


def _hyp_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("doc_id", "")).strip(), int(row.get("page", 0) or 0)


def _teds_gt(record: dict[str, Any]) -> bool:
    html = record.get("table_html")
    return isinstance(html, str) and "<table" in html.lower()


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _render_markdown(report: dict[str, Any]) -> str:
    gate = report["gate"]
    lines = [
        "# Line-CER engineering report (sandbox)",
        "",
        "- Claim scope: **engineering gate only**. This is **not** a product PASS "
        "and **not** a T-005 / business / enterprise acceptance.",
        "- Line CER gate (S-A-02): **≤ 2%** (`0.02`)",
        f"- Observed `line_cer`: **{_pct(report['line_cer'])}** → **{gate}**",
        f"- Observed `page_cer`: **{_pct(report['page_cer'])}** "
        "(diagnostic only; never mixed into the line-CER gate)",
        f"- TEDS GT pages: **{report['teds_gt_pages']}** (no TEDS claim this run)",
        "- Later gates (not evaluated here): key-field F1 ≥ 97%; TEDS ≥ 90%",
        "- Data: public / synthetic / redacted sandbox labels only",
        "",
        "| Metric | Value | Role |",
        "|---|---|---|",
        f"| `page_cer` | {_pct(report['page_cer'])} | diagnostic, page-level |",
        f"| `line_cer` | {_pct(report['line_cer'])} | gate metric |",
        f"| `line_cer_gate` | {report['line_cer_gate']} (≤ 2%) | S-A-02 threshold |",
        f"| `gate` | {gate} | engineering only |",
        f"| `product_pass` | {str(report['product_pass']).lower()} | never claimed by this harness |",
        f"| `business_pass` | {str(report['business_pass']).lower()} | never claimed by this harness |",
        f"| `teds_gt_pages` | {report['teds_gt_pages']} | TEDS GT still 0 unless `<table>` labels exist |",
        "",
        "## Pages",
        "",
        "| doc_id | page | page_cer | line_cer |",
        "|---|---:|---:|---:|",
    ]
    for row in report["pages"]:
        lines.append(
            f"| {row['doc_id']} | {row['page']} | {_pct(row['page_cer'])} | {_pct(row['line_cer'])} |"
        )
    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv run python -m work.eval.page_annotation work/eval/fixtures/sandbox_pages.jsonl",
        "uv run python -m work.eval.rapidocr_line_cer",
        "```",
        "",
        "This command writes only under `--out-dir` (default `outputs/ocr-benchmark/`). "
        "It refuses paths containing `pilot-ledger` or `icp-outreach`.",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Annotations: `{report['annotations']}`",
        f"- Hypotheses: `{report['hypotheses']}`",
        "",
    ]
    return "\n".join(lines)


def evaluate_line_cer(
    gt_records: list[dict[str, Any]],
    hyp_records: list[dict[str, Any]],
    *,
    annotations: str = "",
    hypotheses: str = "",
) -> dict[str, Any]:
    hyp_by_key = {_hyp_key(row): row for row in hyp_records}
    pages: list[dict[str, Any]] = []
    page_edits = 0
    page_denom = 0
    line_edits = 0
    line_denom = 0
    for gt in gt_records:
        doc_id = str(gt["doc_id"])
        page = int(gt["page"])
        hyp = hyp_by_key.get((doc_id, page), {})
        hyp_text = str(hyp.get("text_hyp") or hyp.get("text") or "")
        raw_lines = hyp.get("lines_hyp", hyp.get("lines"))
        hyp_lines = [str(item) for item in raw_lines] if isinstance(raw_lines, list) else None
        p_edits, p_denom = _page_edits(gt["text_gt"], hyp_text)
        l_edits, l_denom = _line_edits(gt["text_gt"], hyp_text, hyp_lines)
        page_edits += p_edits
        page_denom += p_denom
        line_edits += l_edits
        line_denom += l_denom
        pages.append(
            {
                "doc_id": doc_id,
                "page": page,
                "page_cer": (p_edits / p_denom) if p_denom else 0.0,
                "line_cer": (l_edits / l_denom) if l_denom else 0.0,
            }
        )

    page_cer = (page_edits / page_denom) if page_denom else 1.0
    observed_line_cer = (line_edits / line_denom) if line_denom else 1.0
    gate = "GATE_PASS" if observed_line_cer <= LINE_CER_GATE else "GATE_FAIL"
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "claim_scope": "engineering_gate_only",
        "page_cer": page_cer,
        "line_cer": observed_line_cer,
        "line_cer_gate": LINE_CER_GATE,
        "gate": gate,
        "product_pass": False,
        "business_pass": False,
        "teds_gt_pages": sum(1 for row in gt_records if _teds_gt(row)),
        "pages": pages,
        "annotations": annotations,
        "hypotheses": hypotheses,
        "page_edits": page_edits,
        "page_denom": page_denom,
        "line_edits": line_edits,
        "line_denom": line_denom,
    }
    report["markdown"] = _render_markdown(report)
    return report


def _assert_safe_output(path: Path) -> None:
    text = path.resolve().as_posix().lower()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        if token in text:
            raise ForbiddenOutputError(
                f"refusing ledger path {path}; line-CER reports cannot write pilot/ICP ledgers"
            )


def write_report(report: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out = Path(out_dir)
    _assert_safe_output(out)
    if out.suffix:
        # A file path was supplied; still never treat it as a ledger, and do not write it.
        raise ForbiddenOutputError(f"out-dir must be a directory, not a file: {out}")
    out.mkdir(parents=True, exist_ok=True)
    markdown_path = out / "line-cer-report.md"
    json_path = out / "line-cer-report.json"
    _assert_safe_output(markdown_path)
    _assert_safe_output(json_path)
    markdown_path.write_text(report["markdown"], encoding="utf-8")
    payload = {key: value for key, value in report.items() if key != "markdown"}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"markdown": markdown_path, "json": json_path}


def load_hypotheses(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"hypothesis JSONL fail-closed at L{line_no}: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"hypothesis JSONL fail-closed at L{line_no}: not an object")
        if not str(parsed.get("doc_id", "")).strip() or not parsed.get("page"):
            raise ValueError(f"hypothesis JSONL fail-closed at L{line_no}: doc_id and page required")
        rows.append(parsed)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a page-CER vs line-CER report with a ≤2% engineering gate (S-A-02)."
    )
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--hypotheses", type=Path, default=DEFAULT_HYPOTHESES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    try:
        gt = load_annotations(args.annotations)
        hyp = load_hypotheses(args.hypotheses)
        report = evaluate_line_cer(
            gt,
            hyp,
            annotations=_display_path(args.annotations),
            hypotheses=_display_path(args.hypotheses),
        )
        paths = write_report(report, args.out_dir)
    except ForbiddenOutputError as exc:
        print(json.dumps({"error": str(exc), "gate": "GATE_FAIL"}, ensure_ascii=False))
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI must fail closed
        print(json.dumps({"error": str(exc), "gate": "GATE_FAIL"}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "gate": report["gate"],
                "page_cer": report["page_cer"],
                "line_cer": report["line_cer"],
                "line_cer_gate": LINE_CER_GATE,
                "product_pass": False,
                "business_pass": False,
                "markdown": str(paths["markdown"]),
                "json": str(paths["json"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if report["gate"] == "GATE_PASS":
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
