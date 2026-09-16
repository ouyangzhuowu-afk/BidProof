"""S-A-04: key-field ground-truth seed validator and coverage report.

Uses the S-A-01 page JSONL schema, then fail-closed checks for the frozen
key-field name enum, public-manifest provenance, and seed coverage.

Engineering / sandbox only. Never writes pilot or ICP ledgers.
Never computes or claims key-field F1. Missing GT is INSUFFICIENT.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from work.eval.page_annotation import ValidationIssue, validate_jsonl_text

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSONL = ROOT / "work" / "eval" / "fixtures" / "key_field_gt.jsonl"
DEFAULT_NAMES = ROOT / "work" / "eval" / "key_field_names.json"
DEFAULT_MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"
DEFAULT_PDFS_DIR = ROOT / "work" / "public-eval" / "pdfs"
DEFAULT_OUT_DIR = ROOT / "outputs" / "ocr-benchmark"
FORBIDDEN_OUTPUT_TOKENS = ("pilot-ledger", "icp-outreach")
MIN_PUBLIC_DOCS = 5
MIN_LABELED_FIELDS = 30
ORIGIN_PUBLIC = "public"
ORIGIN_SYNTHETIC = "synthetic"
ORIGINS = frozenset({ORIGIN_PUBLIC, ORIGIN_SYNTHETIC})
PHONE_RE = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8})(?!\d)")
NATIONAL_ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


class ForbiddenOutputError(ValueError):
    """Raised when a write target looks like a business ledger."""


class KeyFieldGtError(ValueError):
    """Raised when a key-field seed cannot be trusted (fail-closed)."""


@dataclass
class SeedValidation:
    ok: bool
    records: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)


def _issue(code: str, message: str, line_no: int = 0) -> ValidationIssue:
    return ValidationIssue(line_no=line_no, code=code, message=message)


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


def assert_safe_output_path(path: Path) -> Path:
    text = str(path).replace("\\", "/").lower()
    if any(token in text for token in FORBIDDEN_OUTPUT_TOKENS):
        raise ForbiddenOutputError(f"refusing path that looks like a business ledger: {path}")
    return path


def load_key_field_names(path: Path | None = None) -> frozenset[str]:
    payload = json.loads((path or DEFAULT_NAMES).read_text(encoding="utf-8"))
    names = payload.get("names") or []
    frozen = []
    for item in names:
        if isinstance(item, str) and item.strip():
            frozen.append(item.strip())
        elif isinstance(item, dict) and str(item.get("name", "")).strip():
            frozen.append(str(item["name"]).strip())
    return frozenset(frozen)


KEY_FIELD_NAMES = load_key_field_names()


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


def _looks_like_pii(value: str) -> bool:
    compact = re.sub(r"\s+", "", value or "")
    return bool(PHONE_RE.search(compact) or NATIONAL_ID_RE.search(compact))


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


def validate_seed(
    text: str,
    *,
    manifest: dict[str, Any],
    pdfs_dir: Path | None = None,
    names: frozenset[str] | None = None,
) -> SeedValidation:
    allowed = names if names is not None else KEY_FIELD_NAMES
    issues: list[ValidationIssue] = []
    if not str(text or "").strip():
        return SeedValidation(ok=False, issues=[_issue("empty_seed", "key-field GT seed is empty")])

    page_result = validate_jsonl_text(text)
    raw_rows, raw_issues = _parse_objects(text)
    issues.extend(raw_issues)
    if not page_result.ok:
        issues.extend(page_result.issues)

    completed = _completed_manifest_docs(manifest)
    records: list[dict[str, Any]] = []
    seen_values: dict[tuple[str, str], str] = {}
    raw_by_key = {(str(row.get("doc_id") or "").strip(), row.get("page")): (line_no, row) for line_no, row in raw_rows}

    if page_result.ok:
        for normalized in page_result.records:
            key = (normalized["doc_id"], normalized["page"])
            line_no, raw = raw_by_key.get(key, (0, {}))
            origin = str(raw.get("origin") or "").strip().lower()
            if origin not in ORIGINS:
                issues.append(
                    _issue(
                        "invalid_origin",
                        "origin must be 'public' or 'synthetic'",
                        line_no,
                    )
                )
                continue
            fields = list(normalized.get("fields") or [])
            if not fields:
                issues.append(_issue("empty_fields", "key-field GT pages must label at least one field", line_no))
                continue
            text_gt = str(normalized.get("text_gt") or "")
            clean_fields: list[dict[str, str]] = []
            page_ok = True
            for index, item in enumerate(fields):
                name = str(item.get("name") or "").strip()
                value = item.get("value")
                if name not in allowed:
                    issues.append(
                        _issue(
                            "unknown_key_field_name",
                            f"fields[{index}].name {name!r} is not in the frozen key-field enum",
                            line_no,
                        )
                    )
                    page_ok = False
                    continue
                if not isinstance(value, str) or not value.strip():
                    issues.append(_issue("invalid_fields", f"fields[{index}].value must be a non-empty string", line_no))
                    page_ok = False
                    continue
                if _looks_like_pii(value):
                    issues.append(_issue("pii_value", f"fields[{index}] looks like a phone or national id", line_no))
                    page_ok = False
                    continue
                if _looks_like_pii(text_gt):
                    issues.append(
                        _issue(
                            "pii_in_text_gt",
                            "text_gt contains a phone or national id; clip to the labeled span",
                            line_no,
                        )
                    )
                    page_ok = False
                    break
                if _norm(value) not in _norm(text_gt):
                    issues.append(
                        _issue(
                            "value_not_in_text_gt",
                            f"fields[{index}] value is not present in text_gt",
                            line_no,
                        )
                    )
                    page_ok = False
                    continue
                previous = seen_values.get((normalized["doc_id"], name))
                if previous is not None and _norm(previous) != _norm(value):
                    issues.append(
                        _issue(
                            "conflicting_key_field",
                            f"{normalized['doc_id']}:{name} has conflicting values",
                            line_no,
                        )
                    )
                    page_ok = False
                    continue
                seen_values[(normalized["doc_id"], name)] = value
                clean_fields.append({"name": name, "value": value})
            if not page_ok:
                continue

            record = {
                **normalized,
                "fields": clean_fields,
                "origin": origin,
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
        issues.append(_issue("empty_seed", "key-field GT seed has no labeled pages"))

    return SeedValidation(ok=not issues, records=records, issues=issues)


def evaluate_coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    public_ids = sorted({row["doc_id"] for row in records if row.get("origin") == ORIGIN_PUBLIC})
    synthetic_ids = sorted({row["doc_id"] for row in records if row.get("origin") == ORIGIN_SYNTHETIC})
    unique_fields = {(row["doc_id"], field["name"]) for row in records for field in row.get("fields") or []}
    instances = sum(len(row.get("fields") or []) for row in records)
    labeled_names = {name for _, name in unique_fields}
    unlabeled_enum = sorted(KEY_FIELD_NAMES - labeled_names)
    insufficient_reasons: list[str] = []
    if len(public_ids) < MIN_PUBLIC_DOCS:
        insufficient_reasons.append(
            f"public_documents={len(public_ids)} < {MIN_PUBLIC_DOCS} (missing GT, not a score)"
        )
    if len(unique_fields) < MIN_LABELED_FIELDS:
        insufficient_reasons.append(
            f"labeled_key_fields={len(unique_fields)} < {MIN_LABELED_FIELDS} (missing GT, not a score)"
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
                "fields": [],
            },
        )
        item["pages"] += 1
        for field in row.get("fields") or []:
            if field["name"] not in item["fields"]:
                item["fields"].append(field["name"])
    return {
        "leaf_id": "S-A-04",
        "claim_scope": "engineering seed only; F1 not evaluated; not a product or business PASS",
        "coverage_status": status,
        "min_public_documents": MIN_PUBLIC_DOCS,
        "min_labeled_key_fields": MIN_LABELED_FIELDS,
        "public_documents": len(public_ids),
        "synthetic_documents": len(synthetic_ids),
        "labeled_key_fields": len(unique_fields),
        "labeled_field_instances": instances,
        "public_document_ids": public_ids,
        "synthetic_document_ids": synthetic_ids,
        "unlabeled_enum_names": unlabeled_enum,
        "insufficient_reasons": insufficient_reasons,
        "documents": list(by_doc.values()),
        "product_pass": False,
        "business_pass": False,
        "t005": False,
        "f1": None,
        "f1_status": "NOT_EVALUATED",
        "f1_gate": 0.97,
        "line_cer_gate": 0.02,
        "teds_gate": 0.90,
    }


def _render_markdown(coverage: dict[str, Any], result: SeedValidation) -> str:
    reasons = coverage.get("insufficient_reasons") or ["none"]
    lines = [
        "# S-A-04 key-field GT seed report",
        "",
        "Engineering / sandbox labels only. This is **not a product PASS**, **not T-005**,",
        "and **does not evaluate key-field F1**. Missing GT is `INSUFFICIENT`, not a high score.",
        "",
        f"- Generated_at: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        f"- Coverage status: **{coverage['coverage_status']}**",
        f"- `product_pass`: `{str(coverage['product_pass']).lower()}`",
        f"- `business_pass`: `{str(coverage['business_pass']).lower()}`",
        f"- `f1_status`: `{coverage['f1_status']}` (gate F1≥97% remains unevaluated)",
        "",
        "## Counts",
        "",
        "| Metric | Count | Minimum |",
        "|---|---:|---:|",
        f"| public documents with key-field GT | {coverage['public_documents']} | {coverage['min_public_documents']} |",
        f"| unique labeled key fields `(doc_id, name)` | {coverage['labeled_key_fields']} | {coverage['min_labeled_key_fields']} |",
        f"| labeled field instances | {coverage['labeled_field_instances']} | — |",
        f"| synthetic documents | {coverage['synthetic_documents']} | — |",
        "",
        "## Limitations",
        "",
        "- Public rows must match `work/public-eval/manifest.json` `source_url` + `sha256`.",
        "- Synthetic rows are labeled `origin=synthetic` and `doc_id` prefix `synthetic-`.",
        "- S-A-03 F1 is **not** computed here; do not treat seed coverage as gate PASS.",
        "- TEDS / seal / handwriting GT are out of scope for this leaf.",
        "- No PII or enterprise pilot rows. T-005 ledgers were not written.",
        "",
        "Insufficient reasons:",
        "",
    ]
    for reason in reasons:
        lines.append(f"- `{reason}`")
    unlabeled = coverage.get("unlabeled_enum_names") or []
    lines += ["", "Frozen enum names with zero labels in this seed:", ""]
    if unlabeled:
        for name in unlabeled:
            lines.append(f"- `{name}`")
    else:
        lines.append("- none")
    lines += ["", "## Documents", "", "| doc_id | origin | fields | pages | sha256 |", "|---|---|---|---:|---|"]
    for row in coverage.get("documents") or []:
        sha = (row.get("sha256") or "—")[:12]
        if row.get("sha256"):
            sha = f"`{sha}…`"
        lines.append(
            f"| `{row['doc_id']}` | {row.get('origin')} | {len(row.get('fields') or [])} | "
            f"{row.get('pages')} | {sha} |"
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
        "uv run python -m work.eval.key_field_gt",
        "uv run python -m work.eval.page_annotation work/eval/fixtures/key_field_gt.jsonl",
        "uv run --group dev pytest -q tests/test_key_field_gt.py tests/test_page_annotation.py",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


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
        "f1": None,
        "f1_status": "NOT_EVALUATED",
    }
    out.mkdir(parents=True, exist_ok=True)
    md_path = assert_safe_output_path(out / "key-field-gt-report.md")
    json_path = assert_safe_output_path(out / "key-field-gt-report.json")
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"markdown": markdown, "payload": payload, "md_path": md_path, "json_path": json_path}


def load_seed(path: Path, *, manifest: dict[str, Any], pdfs_dir: Path | None = None) -> SeedValidation:
    if not path.is_file():
        raise KeyFieldGtError(f"fail-closed: key-field GT seed missing: {path}")
    result = validate_seed(path.read_text(encoding="utf-8"), manifest=manifest, pdfs_dir=pdfs_dir)
    if not result.ok:
        details = "; ".join(f"L{i.line_no}:{i.code}:{i.message}" for i in result.issues)
        raise KeyFieldGtError(f"fail-closed: illegal key-field GT in {path}: {details}")
    return result


def document_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    documents: dict[str, dict[str, Any]] = {}
    for row in records:
        item = documents.setdefault(
            row["doc_id"],
            {
                "document_id": row["doc_id"],
                "origin": row.get("origin"),
                "source_url": row.get("source_url"),
                "sha256": row.get("sha256"),
                "fields": [],
            },
        )
        for field in row.get("fields") or []:
            item["fields"].append({"name": field["name"], "page": row["page"], "value": field["value"]})
    return {
        "schema_version": "1.1",
        "leaf_id": "S-A-04",
        "purpose": "Document-level projection of S-A-04 key-field JSONL. Canonical seed is the JSONL.",
        "canonical_jsonl": "work/eval/fixtures/key_field_gt.jsonl",
        "product_pass": False,
        "f1_status": "NOT_EVALUATED",
        "documents": list(documents.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate S-A-04 key-field GT seed and emit an engineering coverage report."
    )
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pdfs-dir", type=Path, default=DEFAULT_PDFS_DIR)
    parser.add_argument("--names", type=Path, default=DEFAULT_NAMES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--check", action="store_true", help="Validate and write the report (default behavior).")
    args = parser.parse_args(argv)
    try:
        assert_safe_output_path(args.out_dir)
        manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.is_file() else {}
        names = load_key_field_names(args.names)
        result = validate_seed(
            args.jsonl.read_text(encoding="utf-8") if args.jsonl.is_file() else "",
            manifest=manifest,
            pdfs_dir=args.pdfs_dir,
            names=names,
        )
        coverage = evaluate_coverage(result.records)
        report = write_report(coverage, result, args.out_dir)
    except ForbiddenOutputError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "product_pass": False, "f1_status": "NOT_EVALUATED"}, ensure_ascii=False))
        return 1
    except Exception as exc:  # noqa: BLE001 — CLI must fail closed
        print(json.dumps({"ok": False, "error": str(exc), "product_pass": False, "f1_status": "NOT_EVALUATED"}, ensure_ascii=False))
        return 1

    payload = {
        "ok": result.ok,
        "coverage_status": coverage["coverage_status"],
        "public_documents": coverage["public_documents"],
        "labeled_key_fields": coverage["labeled_key_fields"],
        "product_pass": False,
        "business_pass": False,
        "f1_status": "NOT_EVALUATED",
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
