"""S-A-03: key-field F1 harness + ≥97% engineering gate.

Default command:

  uv run python -m work.eval.key_field_f1

Writes ``outputs/ocr-benchmark/key-field-f1-report.{md,json}`` only.
Never writes pilot/ICP ledgers. Never claims product or business PASS.
Micro-averaged F1 over ``(doc_id, name)`` with NFKC value match; gate ≥ 0.97.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from work.eval.key_field_gt import KEY_FIELD_NAMES, load_key_field_names
from work.eval.page_annotation import load_annotations
from work.eval.sandbox_gates import KEY_FIELD_F1_MIN, aggregate_engineering_gates

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATIONS = ROOT / "work" / "eval" / "fixtures" / "key_field_gt.jsonl"
DEFAULT_HYPOTHESES = ROOT / "work" / "eval" / "fixtures" / "key_field_hypotheses.jsonl"
DEFAULT_OUT_DIR = ROOT / "outputs" / "ocr-benchmark"
FORBIDDEN_OUTPUT_TOKENS = ("pilot-ledger", "icp-outreach")


class ForbiddenOutputError(ValueError):
    """Raised when a write target looks like a business ledger."""


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", "", text).lower()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _assert_safe_output(path: Path) -> None:
    text = path.resolve().as_posix().lower()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        if token in text:
            raise ForbiddenOutputError(
                f"refusing ledger path {path}; key-field F1 reports cannot write pilot/ICP ledgers"
            )


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def extract_gt_fields(
    records: list[dict[str, Any]],
    *,
    names: frozenset[str] | None = None,
) -> dict[tuple[str, str], str]:
    """Map (doc_id, name) -> normalized value. Last write wins if duplicates agree."""
    allowed = names if names is not None else KEY_FIELD_NAMES
    out: dict[tuple[str, str], str] = {}
    for row in records:
        doc_id = str(row.get("doc_id") or "").strip()
        for item in row.get("fields") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            value = item.get("value")
            if name not in allowed or not isinstance(value, str) or not value.strip():
                continue
            out[(doc_id, name)] = str(value)
    return out


def extract_hyp_fields(
    records: list[dict[str, Any]],
    *,
    names: frozenset[str] | None = None,
) -> dict[tuple[str, str], str]:
    allowed = names if names is not None else KEY_FIELD_NAMES
    out: dict[tuple[str, str], str] = {}
    for row in records:
        doc_id = str(row.get("doc_id") or "").strip()
        raw_fields = row.get("fields_hyp", row.get("fields"))
        if not isinstance(raw_fields, list):
            continue
        for item in raw_fields:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            value = item.get("value")
            if name not in allowed or not isinstance(value, str) or not value.strip():
                continue
            out[(doc_id, name)] = str(value)
    return out


def score_key_field_f1(
    gt_fields: dict[tuple[str, str], str],
    hyp_fields: dict[tuple[str, str], str],
) -> dict[str, Any]:
    tp = 0
    matched_gt: set[tuple[str, str]] = set()
    matched_hyp: set[tuple[str, str]] = set()
    details: list[dict[str, Any]] = []

    for key, gt_value in sorted(gt_fields.items()):
        hyp_value = hyp_fields.get(key)
        if hyp_value is not None and _norm(hyp_value) == _norm(gt_value):
            tp += 1
            matched_gt.add(key)
            matched_hyp.add(key)
            details.append({"doc_id": key[0], "name": key[1], "result": "tp"})
        else:
            details.append(
                {
                    "doc_id": key[0],
                    "name": key[1],
                    "result": "fn",
                    "gt_value": gt_value,
                    "hyp_value": hyp_value,
                }
            )

    fp_keys = [key for key in hyp_fields if key not in matched_hyp]
    for key in sorted(fp_keys):
        details.append(
            {
                "doc_id": key[0],
                "name": key[1],
                "result": "fp",
                "hyp_value": hyp_fields[key],
            }
        )

    fp = len(fp_keys)
    fn = len(gt_fields) - tp
    precision = (tp / (tp + fp)) if (tp + fp) else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "key_field_f1": f1,
        "gt_count": len(gt_fields),
        "hyp_count": len(hyp_fields),
        "details": details,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    gate = report["gate"]
    lines = [
        "# Key-field F1 engineering report (sandbox)",
        "",
        "- Claim scope: **engineering gate only**. This is **not** a product PASS "
        "and **not** a T-005 / business / enterprise acceptance.",
        f"- Key-field F1 gate (S-A-03): **≥ {_pct(KEY_FIELD_F1_MIN)}** (`{KEY_FIELD_F1_MIN}`)",
        f"- Observed micro `key_field_f1`: **{_pct(report['key_field_f1'])}** → **{gate}**",
        f"- TP / FP / FN: **{report['tp']} / {report['fp']} / {report['fn']}**",
        "- Matching: exact NFKC-normalized value equality on frozen `(doc_id, name)` keys.",
        "- Hard OR with line CER / TEDS still forces product `NEEDS_REVIEW` while any gate "
        "fails or stays unevaluated.",
        "",
        "| Metric | Value | Role |",
        "|---|---|---|",
        f"| `precision` | {_pct(report['precision'])} | diagnostic |",
        f"| `recall` | {_pct(report['recall'])} | diagnostic |",
        f"| `key_field_f1` | {_pct(report['key_field_f1'])} | gate metric |",
        f"| `key_field_f1_min` | {report['key_field_f1_min']} (≥ 97%) | S-A-03 threshold |",
        f"| `gate` | {gate} | engineering only |",
        f"| `product_pass` | {str(report['product_pass']).lower()} | never claimed |",
        f"| `business_pass` | {str(report['business_pass']).lower()} | never claimed |",
        f"| `forced_requirement_status` | {report['forced_requirement_status']} | product path |",
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv run python -m work.eval.key_field_gt",
        "uv run python -m work.eval.key_field_f1",
        "```",
        "",
        "Writes only under `--out-dir` (default `outputs/ocr-benchmark/`). "
        "Refuses `pilot-ledger` / `icp-outreach` paths.",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Annotations: `{report['annotations']}`",
        f"- Hypotheses: `{report['hypotheses']}`",
        "",
    ]
    return "\n".join(lines)


def evaluate_key_field_f1(
    gt_records: list[dict[str, Any]],
    hyp_records: list[dict[str, Any]],
    *,
    annotations: str = "",
    hypotheses: str = "",
    names: frozenset[str] | None = None,
) -> dict[str, Any]:
    allowed = names if names is not None else load_key_field_names()
    gt_fields = extract_gt_fields(gt_records, names=allowed)
    hyp_fields = extract_hyp_fields(hyp_records, names=allowed)
    scored = score_key_field_f1(gt_fields, hyp_fields)
    f1 = float(scored["key_field_f1"])
    gate = "GATE_PASS" if gt_fields and f1 >= KEY_FIELD_F1_MIN else "GATE_FAIL"
    aggregate = aggregate_engineering_gates(
        key_field_f1=f1 if gt_fields else None,
        key_field_f1_status="EVALUATED" if gt_fields else "INSUFFICIENT",
    )
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "claim_scope": "engineering_gate_only",
        "key_field_f1": f1,
        "key_field_f1_min": KEY_FIELD_F1_MIN,
        "precision": scored["precision"],
        "recall": scored["recall"],
        "tp": scored["tp"],
        "fp": scored["fp"],
        "fn": scored["fn"],
        "gt_count": scored["gt_count"],
        "hyp_count": scored["hyp_count"],
        "gate": gate,
        "product_pass": False,
        "business_pass": False,
        "forced_requirement_status": "NEEDS_REVIEW",
        "annotations": annotations,
        "hypotheses": hypotheses,
        "aggregate_engineering_gates": aggregate,
        "details": scored["details"],
    }
    report["markdown"] = _render_markdown(report)
    return report


def write_report(report: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out = Path(out_dir)
    _assert_safe_output(out)
    if out.suffix:
        raise ForbiddenOutputError(f"out-dir must be a directory, not a file: {out}")
    out.mkdir(parents=True, exist_ok=True)
    markdown_path = out / "key-field-f1-report.md"
    json_path = out / "key-field-f1-report.json"
    _assert_safe_output(markdown_path)
    _assert_safe_output(json_path)
    payload = {key: value for key, value in report.items() if key != "markdown"}
    # Keep details in JSON but trim markdown size already handled.
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
    parser = argparse.ArgumentParser(description="S-A-03 key-field F1 harness (engineering gate only)")
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--hypotheses", type=Path, default=DEFAULT_HYPOTHESES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    try:
        gt = load_annotations(args.annotations)
        hyp = load_hypotheses(args.hypotheses)
        report = evaluate_key_field_f1(
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
        "key_field_f1": report["key_field_f1"],
        "key_field_f1_min": KEY_FIELD_F1_MIN,
        "tp": report["tp"],
        "fp": report["fp"],
        "fn": report["fn"],
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
