"""S-A-05: TEDS table-structure ground-truth seed validator and coverage report.

Uses the S-A-01 page JSONL schema, then fail-closed checks for table_html
markup, public-manifest provenance, single-page completeness, and seed coverage.

Engineering / sandbox only. Never writes pilot or ICP ledgers.
Never computes or claims a TEDS score. Missing GT is INSUFFICIENT.
Cross-page tables are out of scope for Week-1.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from work.eval.page_annotation import ValidationIssue, validate_jsonl_text

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSONL = ROOT / "work" / "eval" / "fixtures" / "teds_gt.jsonl"
DEFAULT_MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"
DEFAULT_PDFS_DIR = ROOT / "work" / "public-eval" / "pdfs"
DEFAULT_OUT_DIR = ROOT / "outputs" / "ocr-benchmark"
FORBIDDEN_OUTPUT_TOKENS = ("pilot-ledger", "icp-outreach")
MIN_TEDS_PAGES = 15
MIN_PUBLIC_DOCS = 3
ORIGIN_PUBLIC = "public"
ORIGIN_SYNTHETIC = "synthetic"
ORIGINS = frozenset({ORIGIN_PUBLIC, ORIGIN_SYNTHETIC})
TABLE_SPAN_SINGLE = "single_page"
PHONE_RE = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8})(?!\d)")
NATIONAL_ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
CROSS_PAGE_RE = re.compile(r"续上表|接下页|接下表|见表续|续表|接上页|见下页")


class ForbiddenOutputError(ValueError):
    """Raised when a write target looks like a business ledger."""


class TedsGtError(ValueError):
    """Raised when a TEDS seed cannot be trusted (fail-closed)."""


@dataclass
class SeedValidation:
    ok: bool
    records: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)


class _TableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.table_count = 0
        self.row_count = 0
        self.cells: list[str] = []
        self._buf: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == "table":
            self.table_count += 1
        elif lowered == "tr":
            self.row_count += 1
        elif lowered in {"td", "th"}:
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._buf is not None:
            self.cells.append("".join(self._buf))
            self._buf = None

    def handle_data(self, data: str) -> None:
        if self._buf is not None:
            self._buf.append(data)


def _issue(code: str, message: str, line_no: int = 0) -> ValidationIssue:
    return ValidationIssue(line_no=line_no, code=code, message=message)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", "", text).lower()


def assert_safe_output_path(path: Path) -> Path:
    text = str(path).replace("\\", "/").lower()
    if any(token in text for token in FORBIDDEN_OUTPUT_TOKENS):
        raise ForbiddenOutputError(f"refusing path that looks like a business ledger: {path}")
    return path


def rows_to_table_html(rows: list[list[str]], *, header: bool = True) -> str:
    """Serialize a rectangular row list to a single HTML table (TEDS GT)."""
    cleaned: list[list[str]] = []
    width = 0
    for row in rows:
        cells = ["" if cell is None else str(cell) for cell in row]
        width = max(width, len(cells))
        cleaned.append(cells)
    if width == 0:
        return "<table></table>"
    for row in cleaned:
        if len(row) < width:
            row.extend([""] * (width - len(row)))
    parts = ["<table>"]
    body = cleaned
    if header and cleaned:
        parts.append("<thead><tr>")
        parts.extend(f"<th>{html.escape(cell)}</th>" for cell in cleaned[0])
        parts.append("</tr></thead>")
        body = cleaned[1:]
    parts.append("<tbody>")
    for row in body:
        parts.append("<tr>")
        parts.extend(f"<td>{html.escape(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def has_teds_gt(record: dict[str, Any] | None) -> bool:
    html_text = (record or {}).get("table_html")
    return isinstance(html_text, str) and "<table" in html_text.lower()


def count_teds_gt_pages(records: list[dict[str, Any]] | None) -> int:
    return sum(1 for row in records or [] if has_teds_gt(row))


def parse_table_html(html_text: str) -> _TableHtmlParser:
    parser = _TableHtmlParser()
    parser.feed(html_text or "")
    parser.close()
    return parser


def _looks_like_pii(value: str) -> bool:
    compact = re.sub(r"\s+", "", value or "")
    return bool(PHONE_RE.search(compact) or NATIONAL_ID_RE.search(compact))


def _completed_manifest_docs(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in manifest.get("documents") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").lower() in {"failed", "excluded"}:
            continue
        doc_id = str(row.get("document_id") or "").strip()
        source_url = str(row.get("source_url") or "").strip()
        sha256 = str(row.get("sha256") or "").strip().lower()
        if not doc_id or not source_url or len(sha256) != 64:
            continue
        out[doc_id] = row
    return out


def _parse_objects(text: str) -> tuple[list[tuple[int, dict[str, Any]]], list[ValidationIssue]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    issues: list[ValidationIssue] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(_issue("invalid_json", f"line is not JSON: {exc.msg}", line_no))
            continue
        if not isinstance(parsed, dict):
            issues.append(_issue("not_object", "each JSONL line must be a JSON object", line_no))
            continue
        rows.append((line_no, parsed))
    return rows, issues


def _validate_table_html(html_text: Any, line_no: int) -> tuple[list[ValidationIssue], list[str]]:
    if html_text is None or (isinstance(html_text, str) and not html_text.strip()):
        return [_issue("missing_table_html", "TEDS GT pages require table_html with a <table>", line_no)], []
    if not isinstance(html_text, str):
        return [_issue("invalid_table_html", "table_html must be a string containing <table>", line_no)], []
    if "<table" not in html_text.lower():
        return [_issue("invalid_table_html", "table_html must contain a <table> element", line_no)], []
    parser = parse_table_html(html_text)
    if parser.table_count < 1:
        return [_issue("invalid_table_html", "table_html must contain a <table> element", line_no)], []
    if parser.row_count < 1:
        return [_issue("invalid_table_html", "table_html must contain at least one <tr>", line_no)], []
    if len(parser.cells) < 2:
        return [_issue("invalid_table_html", "table_html must contain at least two cells", line_no)], []
    return [], parser.cells


def validate_seed(
    text: str,
    *,
    manifest: dict[str, Any],
    pdfs_dir: Path | None = None,
) -> SeedValidation:
    issues: list[ValidationIssue] = []
    if not str(text or "").strip():
        return SeedValidation(ok=False, issues=[_issue("empty_seed", "TEDS GT seed is empty")])

    page_result = validate_jsonl_text(text)
    raw_rows, raw_issues = _parse_objects(text)
    issues.extend(raw_issues)
    if not page_result.ok:
        issues.extend(page_result.issues)

    completed = _completed_manifest_docs(manifest)
    records: list[dict[str, Any]] = []
    raw_by_key = {(str(row.get("doc_id") or "").strip(), row.get("page")): (line_no, row) for line_no, row in raw_rows}

    if page_result.ok:
        for normalized in page_result.records:
            key = (normalized["doc_id"], normalized["page"])
            line_no, raw = raw_by_key.get(key, (0, {}))
            origin = str(raw.get("origin") or "").strip().lower()
            if origin not in ORIGINS:
                issues.append(_issue("invalid_origin", "origin must be 'public' or 'synthetic'", line_no))
                continue

            table_issues, cells = _validate_table_html(normalized.get("table_html"), line_no)
            if table_issues:
                issues.extend(table_issues)
                continue

            span = str(raw.get("table_span") or TABLE_SPAN_SINGLE).strip().lower()
            text_gt = str(normalized.get("text_gt") or "")
            html_text = str(normalized.get("table_html") or "")
            if span != TABLE_SPAN_SINGLE or CROSS_PAGE_RE.search(text_gt) or CROSS_PAGE_RE.search(html_text):
                issues.append(
                    _issue(
                        "cross_page_table",
                        "Week-1 TEDS GT only accepts single-page complete tables",
                        line_no,
                    )
                )
                continue

            page_ok = True
            if _looks_like_pii(text_gt) or any(_looks_like_pii(cell) for cell in cells):
                issues.append(
                    _issue(
                        "pii_in_text_gt" if _looks_like_pii(text_gt) else "pii_value",
                        "table GT contains a phone or national id; clip or redact",
                        line_no,
                    )
                )
                page_ok = False
            if page_ok:
                compact_gt = _norm(text_gt)
                for index, cell in enumerate(cells):
                    token = _norm(cell)
                    if not token:
                        continue
                    if token not in compact_gt:
                        issues.append(
                            _issue(
                                "cell_not_in_text_gt",
                                f"table cell[{index}] is not present in text_gt",
                                line_no,
                            )
                        )
                        page_ok = False
                        break
            if not page_ok:
                continue

            record = {
                **normalized,
                "origin": origin,
                "table_span": TABLE_SPAN_SINGLE,
            }
            if origin == ORIGIN_PUBLIC:
                source_url = str(raw.get("source_url") or "").strip()
                sha256 = str(raw.get("sha256") or "").strip().lower()
                manifest_row = completed.get(normalized["doc_id"])
                if not source_url:
                    issues.append(_issue("missing_source_url", "public rows require source_url", line_no))
                    continue
                if len(sha256) != 64:
                    issues.append(_issue("missing_sha256", "public rows require sha256", line_no))
                    continue
                if manifest_row is None:
                    issues.append(
                        _issue(
                            "manifest_mismatch",
                            f"public doc_id {normalized['doc_id']!r} is not a completed manifest document",
                            line_no,
                        )
                    )
                    continue
                expected_url = str(manifest_row.get("source_url") or "").strip()
                expected_sha = str(manifest_row.get("sha256") or "").strip().lower()
                if source_url != expected_url or sha256 != expected_sha:
                    issues.append(
                        _issue(
                            "manifest_mismatch",
                            "public source_url/sha256 do not match the canonical manifest",
                            line_no,
                        )
                    )
                    continue
                if pdfs_dir is not None:
                    rel = manifest_row.get("path") or f"{pdfs_dir}/{manifest_row.get('filename')}"
                    pdf_path = ROOT / rel if not Path(str(rel)).is_absolute() else Path(str(rel))
                    if not pdf_path.is_file():
                        alt = Path(pdfs_dir) / str(manifest_row.get("filename") or "")
                        pdf_path = alt if alt.is_file() else pdf_path
                    if not pdf_path.is_file():
                        issues.append(_issue("missing_pdf", f"public PDF missing: {pdf_path}", line_no))
                        continue
                    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
                    if digest != sha256:
                        issues.append(
                            _issue(
                                "file_sha256_mismatch",
                                f"local file sha256 {digest} != manifest {sha256}",
                                line_no,
                            )
                        )
                        continue
                record["source_url"] = source_url
                record["sha256"] = sha256
            else:
                if not str(normalized["doc_id"]).startswith("synthetic-"):
                    issues.append(
                        _issue(
                            "invalid_synthetic_id",
                            "synthetic doc_id must start with 'synthetic-'",
                            line_no,
                        )
                    )
                    continue
                if normalized["doc_id"] in completed:
                    issues.append(
                        _issue(
                            "synthetic_in_manifest",
                            "synthetic doc_id collides with a public manifest document",
                            line_no,
                        )
                    )
                    continue
            records.append(record)

    if page_result.ok and not records and not issues:
        issues.append(_issue("empty_seed", "TEDS GT seed has no labeled pages"))

    return SeedValidation(ok=not issues, records=records, issues=issues)


def evaluate_coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    public_ids = sorted({row["doc_id"] for row in records if row.get("origin") == ORIGIN_PUBLIC})
    synthetic_ids = sorted({row["doc_id"] for row in records if row.get("origin") == ORIGIN_SYNTHETIC})
    teds_pages = count_teds_gt_pages(records)
    insufficient_reasons: list[str] = []
    if teds_pages < MIN_TEDS_PAGES:
        insufficient_reasons.append(
            f"teds_gt_pages={teds_pages} < {MIN_TEDS_PAGES} (missing GT, not a score)"
        )
    if len(public_ids) < MIN_PUBLIC_DOCS:
        insufficient_reasons.append(
            f"public_documents={len(public_ids)} < {MIN_PUBLIC_DOCS} (missing GT, not a score)"
        )
    status = "INSUFFICIENT" if insufficient_reasons else "SUFFICIENT_SEED"
    by_doc: dict[str, dict[str, Any]] = {}
    for row in records:
        item = by_doc.setdefault(
            row["doc_id"],
            {
                "doc_id": row["doc_id"],
                "origin": row.get("origin"),
                "source_url": row.get("source_url"),
                "sha256": row.get("sha256"),
                "pages": 0,
                "titles": [],
            },
        )
        item["pages"] += 1
        for field in row.get("fields") or []:
            if field.get("name") == "table_title" and field.get("value"):
                item["titles"].append(field["value"])
    return {
        "leaf_id": "S-A-05",
        "claim_scope": "engineering seed only; TEDS not evaluated; not a product or business PASS",
        "coverage_status": status,
        "min_teds_pages": MIN_TEDS_PAGES,
        "min_public_documents": MIN_PUBLIC_DOCS,
        "teds_gt_pages": teds_pages,
        "public_documents": len(public_ids),
        "synthetic_documents": len(synthetic_ids),
        "public_document_ids": public_ids,
        "synthetic_document_ids": synthetic_ids,
        "insufficient_reasons": insufficient_reasons,
        "documents": list(by_doc.values()),
        "product_pass": False,
        "business_pass": False,
        "t005": False,
        "teds": None,
        "teds_status": "NOT_EVALUATED",
        "teds_gate": 0.90,
        "line_cer_gate": 0.02,
        "f1_gate": 0.97,
        "week1_scope": "single_page_complete_tables_only",
        "cross_page_tables": "out_of_scope",
    }


def _render_markdown(coverage: dict[str, Any], result: SeedValidation) -> str:
    reasons = coverage.get("insufficient_reasons") or ["none"]
    lines = [
        "# S-A-05 TEDS table-structure GT seed report",
        "",
        "Engineering / sandbox labels only. This is **not a product PASS**, **not T-005**,",
        "and **does not evaluate TEDS**. Missing GT is `INSUFFICIENT`, not a high score.",
        "The TEDS ≥ 90% product gate remains **NOT_EVALUATED**.",
        "",
        f"- Generated_at: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        f"- Coverage status: **{coverage['coverage_status']}**",
        f"- `product_pass`: `{str(coverage['product_pass']).lower()}`",
        f"- `business_pass`: `{str(coverage['business_pass']).lower()}`",
        f"- `teds_status`: `{coverage['teds_status']}` (gate TEDS≥90% remains unevaluated)",
        f"- `teds_gt_pages`: **{coverage['teds_gt_pages']}** (was 0 before this leaf)",
        "",
        "## Counts",
        "",
        "| Metric | Count | Minimum |",
        "|---|---:|---:|",
        f"| TEDS GT pages (`table_html` with `<table>`) | {coverage['teds_gt_pages']} | {coverage['min_teds_pages']} |",
        f"| public documents with table GT | {coverage['public_documents']} | {coverage['min_public_documents']} |",
        f"| synthetic documents | {coverage['synthetic_documents']} | — |",
        "",
        "## Limitations",
        "",
        "- Public rows must match `work/public-eval/manifest.json` `source_url` + `sha256`.",
        "- Synthetic rows are labeled `origin=synthetic` and `doc_id` prefix `synthetic-`.",
        "- Week-1 labels are **single-page complete tables only**; cross-page tables are out of scope.",
        "- S-A-06 TEDS similarity / ≥90% gate is **not** computed here.",
        "- Seal / handwriting GT (S-A-07) and key-field F1 (S-A-03) are out of scope.",
        "- No PII or enterprise pilot rows. T-005 ledgers were not written.",
        "",
        "Insufficient reasons:",
        "",
    ]
    for reason in reasons:
        lines.append(f"- `{reason}`")
    lines += ["", "## Documents", "", "| doc_id | origin | pages | titles | sha256 |", "|---|---|---:|---|---|"]
    for row in coverage.get("documents") or []:
        sha = (row.get("sha256") or "—")[:12]
        if row.get("sha256"):
            sha = f"`{sha}…`"
        titles = "; ".join(row.get("titles") or []) or "—"
        lines.append(
            f"| `{row['doc_id']}` | {row.get('origin')} | {row.get('pages')} | {titles} | {sha} |"
        )
    if not result.ok:
        lines += ["", "## Validation issues", ""]
        for issue in result.issues:
            lines.append(f"- L{issue.line_no} `{issue.code}`: {issue.message}")
    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "uv run python -m work.eval.teds_gt",
        "uv run python -m work.eval.page_annotation work/eval/fixtures/teds_gt.jsonl",
        "uv run --group dev pytest -q tests/test_teds_gt.py tests/test_page_annotation.py",
        "```",
        "",
        "Exit `0` = schema valid and seed minima met (`SUFFICIENT_SEED`).  ",
        "Exit `2` = schema valid but coverage `INSUFFICIENT`.  ",
        "Exit `1` = validation / IO error.",
        "",
        "`SUFFICIENT_SEED` is not TEDS ≥ 90% and is not a product/business PASS.",
        "",
    ]
    return "\n".join(lines)


def write_report(coverage: dict[str, Any], result: SeedValidation, out_dir: Path) -> dict[str, Any]:
    out = assert_safe_output_path(Path(out_dir))
    if out.suffix:
        raise ForbiddenOutputError(f"out-dir must be a directory, not a file: {out}")
    markdown = _render_markdown(coverage, result)
    payload = {
        **coverage,
        "ok": result.ok,
        "issues": [{"line": i.line_no, "code": i.code, "message": i.message} for i in result.issues],
        "schema_ok": result.ok,
        "claim_scope": coverage["claim_scope"],
        "product_pass": False,
        "business_pass": False,
        "teds": None,
        "teds_status": "NOT_EVALUATED",
    }
    out.mkdir(parents=True, exist_ok=True)
    md_path = assert_safe_output_path(out / "teds-gt-report.md")
    json_path = assert_safe_output_path(out / "teds-gt-report.json")
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"markdown": markdown, "payload": payload, "md_path": md_path, "json_path": json_path}


def load_seed(path: Path, *, manifest: dict[str, Any], pdfs_dir: Path | None = None) -> SeedValidation:
    if not path.is_file():
        raise TedsGtError(f"fail-closed: TEDS GT seed missing: {path}")
    result = validate_seed(path.read_text(encoding="utf-8"), manifest=manifest, pdfs_dir=pdfs_dir)
    if not result.ok:
        details = "; ".join(f"L{i.line_no}:{i.code}:{i.message}" for i in result.issues)
        raise TedsGtError(f"fail-closed: illegal TEDS GT in {path}: {details}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate S-A-05 TEDS table-structure GT seed and emit an engineering coverage report."
    )
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pdfs-dir", type=Path, default=DEFAULT_PDFS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--check", action="store_true", help="Validate and write the report (default behavior).")
    args = parser.parse_args(argv)
    try:
        assert_safe_output_path(args.out_dir)
        manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.is_file() else {}
        result = validate_seed(
            args.jsonl.read_text(encoding="utf-8") if args.jsonl.is_file() else "",
            manifest=manifest,
            pdfs_dir=args.pdfs_dir,
        )
        coverage = evaluate_coverage(result.records)
        report = write_report(coverage, result, args.out_dir)
    except ForbiddenOutputError as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "product_pass": False, "teds_status": "NOT_EVALUATED"},
                ensure_ascii=False,
            )
        )
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI must fail closed
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "product_pass": False, "teds_status": "NOT_EVALUATED"},
                ensure_ascii=False,
            )
        )
        return 1

    payload = {
        "ok": result.ok,
        "coverage_status": coverage["coverage_status"],
        "teds_gt_pages": coverage["teds_gt_pages"],
        "public_documents": coverage["public_documents"],
        "synthetic_documents": coverage["synthetic_documents"],
        "product_pass": False,
        "business_pass": False,
        "teds_status": "NOT_EVALUATED",
        "markdown": str(report["md_path"]),
        "json": str(report["json_path"]),
        "issues": [{"line": i.line_no, "code": i.code, "message": i.message} for i in result.issues],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not result.ok:
        return 1
    if coverage["coverage_status"] == "INSUFFICIENT":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
