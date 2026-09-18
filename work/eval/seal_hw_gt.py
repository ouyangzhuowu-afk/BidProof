"""S-A-07: seal / handwriting page-type slot GT seed validator.

Fills S-A-01 ``page_type`` slots ``seal`` / ``handwriting`` plus ``has_seal`` /
``has_hw`` flags. Engineering / sandbox only — no pixel-level detection score,
no product PASS, no pilot/ICP ledger writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from work.eval.page_annotation import (
    PAGE_TYPES,
    ValidationIssue,
    validate_jsonl_text,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSONL = ROOT / "work" / "eval" / "fixtures" / "seal_hw_gt.jsonl"
DEFAULT_MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"
DEFAULT_PDFS_DIR = ROOT / "work" / "public-eval" / "pdfs"
DEFAULT_OUT_DIR = ROOT / "outputs" / "ocr-benchmark"
FORBIDDEN_OUTPUT_TOKENS = ("pilot-ledger", "icp-outreach")
MIN_SEAL_PAGES = 6
MIN_HW_PAGES = 3
MIN_PAGE_TYPE_SEAL = 3
MIN_PAGE_TYPE_HW = 2
MIN_PUBLIC_DOCS = 3
ORIGIN_PUBLIC = "public"
ORIGIN_SYNTHETIC = "synthetic"
ORIGINS = frozenset({ORIGIN_PUBLIC, ORIGIN_SYNTHETIC})
SLOTS = frozenset({"seal", "handwriting", "mixed"})


class ForbiddenOutputError(ValueError):
    """Raised when a write target looks like a business ledger."""


class SealHwGtError(ValueError):
    """Raised when a seal/hw seed cannot be trusted (fail-closed)."""


@dataclass
class SeedValidation:
    ok: bool
    records: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)


def _issue(code: str, message: str, line_no: int = 0) -> ValidationIssue:
    return ValidationIssue(line_no=line_no, code=code, message=message)


def assert_safe_output_path(path: Path) -> Path:
    text = str(path).replace("\\", "/").lower()
    if any(token in text for token in FORBIDDEN_OUTPUT_TOKENS):
        raise ForbiddenOutputError(f"refusing path that looks like a business ledger: {path}")
    return path


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def has_seal_slot(record: dict[str, Any] | None) -> bool:
    row = record or {}
    return bool(row.get("has_seal")) or str(row.get("page_type") or "") == "seal"


def has_hw_slot(record: dict[str, Any] | None) -> bool:
    row = record or {}
    return bool(row.get("has_hw")) or str(row.get("page_type") or "") == "handwriting"


def validate_seal_hw_seed(
    text: str,
    *,
    manifest: dict[str, Any] | None = None,
    pdfs_dir: Path | None = None,
) -> SeedValidation:
    base = validate_jsonl_text(text)
    issues = list(base.issues)
    if not base.ok:
        return SeedValidation(ok=False, records=[], issues=issues)

    raw_by_key: dict[tuple[str, int], tuple[int, dict[str, Any]]] = {}
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("doc_id") is not None and parsed.get("page") is not None:
            key = (str(parsed["doc_id"]).strip(), int(parsed["page"]))
            raw_by_key.setdefault(key, (line_no, parsed))

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    completed = _completed_manifest_docs(manifest or {})
    pdf_root = Path(pdfs_dir) if pdfs_dir is not None else DEFAULT_PDFS_DIR

    for normalized in base.records:
        doc_id = str(normalized.get("doc_id") or "").strip()
        page = int(normalized.get("page") or 0)
        key = (doc_id, page)
        line_no, raw = raw_by_key.get(key, (0, {}))
        if key in seen:
            issues.append(_issue("duplicate_page", f"duplicate (doc_id, page) {key}", line_no))
            continue
        seen.add(key)

        row = dict(normalized)
        for extra in ("origin", "slot", "source_url", "sha256", "document_path", "notes"):
            if extra in raw:
                row[extra] = raw[extra]

        page_type = str(row.get("page_type") or "")
        if page_type == "seal" and not row.get("has_seal"):
            issues.append(_issue("seal_slot_inconsistent", "page_type=seal requires has_seal=true", line_no))
        if page_type == "handwriting" and not row.get("has_hw"):
            issues.append(_issue("hw_slot_inconsistent", "page_type=handwriting requires has_hw=true", line_no))
        if not row.get("has_seal") and not row.get("has_hw"):
            issues.append(_issue("empty_slot", "S-A-07 pages must set has_seal and/or has_hw", line_no))

        origin = str(row.get("origin") or "").strip()
        if origin not in ORIGINS:
            issues.append(_issue("invalid_origin", "origin must be public or synthetic", line_no))
        slot = str(row.get("slot") or "").strip()
        if slot and slot not in SLOTS:
            issues.append(_issue("invalid_slot", "slot must be seal, handwriting, or mixed", line_no))

        if origin == ORIGIN_SYNTHETIC:
            if not doc_id.startswith("synthetic-"):
                issues.append(_issue("synthetic_doc_id", "synthetic rows require doc_id prefix synthetic-", line_no))
        elif origin == ORIGIN_PUBLIC:
            manifest_row = completed.get(doc_id)
            if manifest_row is None:
                issues.append(_issue("unknown_public_doc", f"doc_id {doc_id!r} missing from public manifest", line_no))
            else:
                source_url = str(row.get("source_url") or "").strip()
                sha256 = str(row.get("sha256") or "").strip().lower()
                if source_url != str(manifest_row.get("source_url") or "").strip():
                    issues.append(_issue("source_url_mismatch", f"{doc_id} source_url does not match manifest", line_no))
                if sha256 != str(manifest_row.get("sha256") or "").strip().lower():
                    issues.append(_issue("sha256_mismatch", f"{doc_id} sha256 does not match manifest", line_no))
                rel = str(row.get("document_path") or "").strip()
                path = ROOT / rel if rel else pdf_root / str(manifest_row.get("filename") or "")
                if not path.is_file():
                    alt = pdf_root / str(manifest_row.get("filename") or "")
                    path = alt if alt.is_file() else path
                if not path.is_file():
                    issues.append(_issue("missing_pdf", f"public PDF missing for {doc_id}: {path}", line_no))
                elif sha256 and _sha256_file(path) != sha256:
                    issues.append(_issue("pdf_sha_mismatch", f"on-disk sha256 mismatch for {doc_id}", line_no))

        records.append(row)

    ok = not issues and bool(records)
    return SeedValidation(ok=ok, records=records, issues=issues)


def coverage_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    seal_pages = [row for row in records if has_seal_slot(row)]
    hw_pages = [row for row in records if has_hw_slot(row)]
    page_type_seal = [row for row in records if row.get("page_type") == "seal"]
    page_type_hw = [row for row in records if row.get("page_type") == "handwriting"]
    public_docs = sorted({row["doc_id"] for row in records if row.get("origin") == ORIGIN_PUBLIC})
    synthetic_docs = sorted({row["doc_id"] for row in records if row.get("origin") == ORIGIN_SYNTHETIC})
    sufficient = (
        len(seal_pages) >= MIN_SEAL_PAGES
        and len(hw_pages) >= MIN_HW_PAGES
        and len(page_type_seal) >= MIN_PAGE_TYPE_SEAL
        and len(page_type_hw) >= MIN_PAGE_TYPE_HW
        and len(public_docs) >= MIN_PUBLIC_DOCS
    )
    return {
        "coverage_status": "SUFFICIENT_SEED" if sufficient else "INSUFFICIENT",
        "seal_pages": len(seal_pages),
        "hw_pages": len(hw_pages),
        "page_type_seal": len(page_type_seal),
        "page_type_handwriting": len(page_type_hw),
        "public_documents": len(public_docs),
        "synthetic_documents": len(synthetic_docs),
        "min_seal_pages": MIN_SEAL_PAGES,
        "min_hw_pages": MIN_HW_PAGES,
        "min_page_type_seal": MIN_PAGE_TYPE_SEAL,
        "min_page_type_handwriting": MIN_PAGE_TYPE_HW,
        "min_public_docs": MIN_PUBLIC_DOCS,
        "product_pass": False,
        "business_pass": False,
        "detection_status": "NOT_EVALUATED",
        "public_doc_ids": public_docs,
        "synthetic_doc_ids": synthetic_docs,
    }


def _render_markdown(coverage: dict[str, Any], *, source: str) -> str:
    return "\n".join(
        [
            "# S-A-07 seal / handwriting page-type slot GT seed report",
            "",
            "Engineering / sandbox labels only. This is **not a product PASS**, **not T-005**,",
            "and **does not evaluate seal/handwriting detection accuracy**. Missing GT is",
            "`INSUFFICIENT`, not a high score. Pixel-level GT is still a gap.",
            "",
            f"- Generated_at: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
            f"- Coverage status: **{coverage['coverage_status']}**",
            f"- `product_pass`: `{str(coverage['product_pass']).lower()}`",
            f"- `detection_status`: `{coverage['detection_status']}`",
            f"- Source: `{source}`",
            "",
            "| Metric | Count | Minimum |",
            "|---|---:|---:|",
            f"| Seal slots (`has_seal` or `page_type=seal`) | {coverage['seal_pages']} | {coverage['min_seal_pages']} |",
            f"| Handwriting slots (`has_hw` or `page_type=handwriting`) | {coverage['hw_pages']} | {coverage['min_hw_pages']} |",
            f"| `page_type=seal` | {coverage['page_type_seal']} | {coverage['min_page_type_seal']} |",
            f"| `page_type=handwriting` | {coverage['page_type_handwriting']} | {coverage['min_page_type_handwriting']} |",
            f"| Public documents | {coverage['public_documents']} | {coverage['min_public_docs']} |",
            f"| Synthetic documents | {coverage['synthetic_documents']} | — |",
            "",
            "## Reproduce",
            "",
            "```bash",
            "uv run python -m work.eval.seal_hw_gt",
            "uv run python -m work.eval.page_annotation work/eval/fixtures/seal_hw_gt.jsonl",
            "```",
            "",
            "`SUFFICIENT_SEED` is not seal/handwriting detection ≥95%/≥90% and is not a product PASS.",
            "",
        ]
    )


def write_reports(coverage: dict[str, Any], out_dir: Path, *, source: str) -> dict[str, Path]:
    out = assert_safe_output_path(Path(out_dir))
    if out.suffix:
        raise ForbiddenOutputError(f"out-dir must be a directory, not a file: {out}")
    out.mkdir(parents=True, exist_ok=True)
    markdown_path = assert_safe_output_path(out / "seal-hw-gt-report.md")
    json_path = assert_safe_output_path(out / "seal-hw-gt-report.json")
    payload = {
        **coverage,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": source,
        "claim_scope": "engineering_seed_only",
    }
    markdown_path.write_text(_render_markdown(coverage, source=source), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"markdown": markdown_path, "json": json_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S-A-07 seal/handwriting page-type slot GT seed")
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pdfs-dir", type=Path, default=DEFAULT_PDFS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    try:
        text = args.jsonl.read_text(encoding="utf-8")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validation = validate_seal_hw_seed(text, manifest=manifest, pdfs_dir=args.pdfs_dir)
        if not validation.ok:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "issues": [issue.__dict__ for issue in validation.issues],
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        coverage = coverage_report(validation.records)
        paths = write_reports(coverage, args.out_dir, source=_display_path(args.jsonl))
    except (OSError, ValueError, json.JSONDecodeError, ForbiddenOutputError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    summary = {
        "ok": True,
        "coverage_status": coverage["coverage_status"],
        "seal_pages": coverage["seal_pages"],
        "hw_pages": coverage["hw_pages"],
        "page_type_seal": coverage["page_type_seal"],
        "page_type_handwriting": coverage["page_type_handwriting"],
        "public_documents": coverage["public_documents"],
        "synthetic_documents": coverage["synthetic_documents"],
        "product_pass": False,
        "business_pass": False,
        "detection_status": "NOT_EVALUATED",
        "markdown": _display_path(paths["markdown"]),
        "json": _display_path(paths["json"]),
        "issues": [],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if coverage["coverage_status"] == "SUFFICIENT_SEED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
