"""S-A-06: reproducible TEDS harness + ≥90% engineering gate.

Default command:

  uv run python -m work.eval.teds_harness

Writes `outputs/ocr-benchmark/teds-report.{md,json}` only.
Never writes pilot/ICP ledgers. Never claims product or business PASS.
Mean TEDS gate is ≥ 0.9; otherwise GATE_FAIL.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from work.eval.page_annotation import load_annotations
from work.eval.sandbox_gates import TEDS_MIN, aggregate_engineering_gates
from work.eval.teds_gt import has_teds_gt
from work.eval.teds_score import teds

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATIONS = ROOT / "work" / "eval" / "fixtures" / "teds_gt.jsonl"
DEFAULT_HYPOTHESES = ROOT / "work" / "eval" / "fixtures" / "teds_hypotheses.jsonl"
DEFAULT_OUT_DIR = ROOT / "outputs" / "ocr-benchmark"
FORBIDDEN_OUTPUT_TOKENS = ("pilot-ledger", "icp-outreach")


class ForbiddenOutputError(ValueError):
    """Raised when a write target looks like a business ledger."""


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _hyp_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("doc_id", "")).strip(), int(row.get("page", 0) or 0)


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _assert_safe_output(path: Path) -> None:
    text = path.resolve().as_posix().lower()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        if token in text:
            raise ForbiddenOutputError(
                f"refusing ledger path {path}; TEDS reports cannot write pilot/ICP ledgers"
            )


def _render_markdown(report: dict[str, Any]) -> str:
    gate = report["gate"]
    lines = [
        "# TEDS engineering report (sandbox)",
        "",
        "- Claim scope: **engineering gate only**. This is **not** a product PASS "
        "and **not** a T-005 / business / enterprise acceptance.",
        f"- TEDS gate (S-A-06): **≥ {_pct(TEDS_MIN)}** (`{TEDS_MIN}`)",
        f"- Observed mean `teds`: **{_pct(report['teds'])}** → **{gate}**",
        f"- Pages scored: **{report['pages_scored']}** / GT pages with `<table>`: "
        f"**{report['teds_gt_pages']}**",
        "- Hard OR with line CER / key-field F1 still forces product `NEEDS_REVIEW` "
        "while any gate fails or stays unevaluated (see `sandbox_gates`).",
        "- Data: public / synthetic sandbox table labels only",
        "",
        "| Metric | Value | Role |",
        "|---|---|---|",
        f"| `teds` | {_pct(report['teds'])} | gate metric (micro-mean) |",
        f"| `teds_min` | {report['teds_min']} (≥ 90%) | S-A-06 threshold |",
        f"| `gate` | {gate} | engineering only |",
        f"| `product_pass` | {str(report['product_pass']).lower()} | never claimed by this harness |",
        f"| `business_pass` | {str(report['business_pass']).lower()} | never claimed by this harness |",
        f"| `forced_requirement_status` | {report['forced_requirement_status']} | product path while gates open |",
        "",
        "## Pages",
        "",
        "| doc_id | page | teds |",
        "|---|---:|---:|",
    ]
    for row in report["pages"]:
        lines.append(f"| {row['doc_id']} | {row['page']} | {_pct(row['teds'])} |")
    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv run python -m work.eval.teds_gt",
        "uv run python -m work.eval.teds_harness",
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


def evaluate_teds(
    gt_records: list[dict[str, Any]],
    hyp_records: list[dict[str, Any]],
    *,
    annotations: str = "",
    hypotheses: str = "",
) -> dict[str, Any]:
    hyp_by_key = {_hyp_key(row): row for row in hyp_records}
    pages: list[dict[str, Any]] = []
    scores: list[float] = []
    gt_with_table = [row for row in gt_records if has_teds_gt(row)]
    for gt in gt_with_table:
        doc_id = str(gt["doc_id"])
        page = int(gt["page"])
        hyp = hyp_by_key.get((doc_id, page), {})
        hyp_html = hyp.get("table_html_hyp", hyp.get("table_html"))
        score = teds(str(hyp_html) if hyp_html is not None else "", str(gt.get("table_html") or ""))
        scores.append(score)
        pages.append({"doc_id": doc_id, "page": page, "teds": score})

    mean_teds = (sum(scores) / len(scores)) if scores else 0.0
    gate = "GATE_PASS" if scores and mean_teds >= TEDS_MIN else "GATE_FAIL"
    aggregate = aggregate_engineering_gates(teds=mean_teds if scores else None, teds_status="EVALUATED" if scores else "INSUFFICIENT")
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "claim_scope": "engineering_gate_only",
        "teds": mean_teds,
        "teds_min": TEDS_MIN,
        "gate": gate,
        "product_pass": False,
        "business_pass": False,
        "forced_requirement_status": "NEEDS_REVIEW",
        "teds_gt_pages": len(gt_with_table),
        "pages_scored": len(scores),
        "pages": pages,
        "annotations": annotations,
        "hypotheses": hypotheses,
        "aggregate_engineering_gates": aggregate,
    }
    report["markdown"] = _render_markdown(report)
    return report


def write_report(report: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out = Path(out_dir)
    _assert_safe_output(out)
    if out.suffix:
        raise ForbiddenOutputError(f"out-dir must be a directory, not a file: {out}")
    out.mkdir(parents=True, exist_ok=True)
    markdown_path = out / "teds-report.md"
    json_path = out / "teds-report.json"
    _assert_safe_output(markdown_path)
    _assert_safe_output(json_path)
    payload = {key: value for key, value in report.items() if key != "markdown"}
    markdown_path.write_text(report["markdown"], encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"markdown": markdown_path, "json": json_path}


def load_hypotheses(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("each hypothesis line must be a JSON object")
        rows.append(parsed)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S-A-06 TEDS harness (engineering gate only)")
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--hypotheses", type=Path, default=DEFAULT_HYPOTHESES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    try:
        gt = load_annotations(args.annotations)
        hyp = load_hypotheses(args.hypotheses)
        report = evaluate_teds(
            gt,
            hyp,
            annotations=_display_path(args.annotations),
            hypotheses=_display_path(args.hypotheses),
        )
        paths = write_report(report, args.out_dir)
    except ForbiddenOutputError as exc:
        print(json.dumps({"error": str(exc), "gate": "GATE_FAIL"}, ensure_ascii=False))
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "gate": "GATE_FAIL"}, ensure_ascii=False))
        return 1

    summary = {
        "ok": True,
        "gate": report["gate"],
        "teds": report["teds"],
        "teds_min": TEDS_MIN,
        "product_pass": False,
        "business_pass": False,
        "forced_requirement_status": "NEEDS_REVIEW",
        "markdown": _display_path(paths["markdown"]),
        "json": _display_path(paths["json"]),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if report["gate"] == "GATE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
