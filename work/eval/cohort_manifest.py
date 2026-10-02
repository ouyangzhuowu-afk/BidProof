"""Freeze the public-expand OCR cohort for fair local vs cloud compare.

Locks page list, PDF/GT content hashes, CER character denominator (after TOC
segmentation), and scorer version. Pages are never dropped from the denominator
when a provider fails — failures are recorded with a reason instead.

Engineering only. Not a product PASS and not T-005.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from work.eval.page_annotation import load_annotations
from work.eval.public_expand import (
    CER_GT_PATH,
    CER_HYP_PATH,
    KF_GT_PATH,
    KF_HYP_PATH,
    TEDS_GT_PATH,
    TEDS_HYP_PATH,
    prepare_expanded_cer,
)
from work.eval.rapidocr_line_cer import _line_edits, load_hypotheses

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "work" / "eval" / "fixtures"
DEFAULT_MANIFEST_PATH = FIXTURE_DIR / "cloud_compare_cohort_manifest.json"
OUT_DIR = ROOT / "outputs" / "ocr-benchmark" / "cloud-compare"

# Locked identifiers for this compare cohort (expanded public set on mainline a99014f).
COHORT_ID = "public-expand-54"
SCORER_VERSION = "line-cer-v1+toc-segment"
EXPECTED_PAGE_COUNT = 54
EXPECTED_CER_DENOM = 29835
MAINLINE_BASELINE = "a99014f3f265"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_cer_denominator(gt_rows: list[dict[str, Any]], hyp_rows: list[dict[str, Any]]) -> int:
    """Sum of reference character lengths after the same TOC prep used in scoring."""
    prepared_gt, prepared_hyp = prepare_expanded_cer(gt_rows, hyp_rows)
    hyp_by = {(str(row.get("doc_id")), int(row.get("page") or 0)): row for row in prepared_hyp}
    total = 0
    for gt in prepared_gt:
        key = (str(gt.get("doc_id")), int(gt.get("page") or 0))
        hyp = hyp_by.get(key, {})
        _edits, denom = _line_edits(
            str(gt.get("text_gt") or ""),
            str(hyp.get("text_hyp") or ""),
            hyp.get("lines_hyp") if isinstance(hyp.get("lines_hyp"), list) else None,
        )
        total += int(denom)
    return total


def build_cohort_manifest(
    *,
    cer_gt_path: Path = CER_GT_PATH,
    cer_hyp_path: Path = CER_HYP_PATH,
    teds_gt_path: Path = TEDS_GT_PATH,
    teds_hyp_path: Path = TEDS_HYP_PATH,
    kf_gt_path: Path = KF_GT_PATH,
    kf_hyp_path: Path = KF_HYP_PATH,
) -> dict[str, Any]:
    # Raw JSONL keeps provenance hashes; load_annotations strips them.
    raw_gt = _read_jsonl(cer_gt_path)
    gt_rows = load_annotations(cer_gt_path)
    hyp_rows = load_hypotheses(cer_hyp_path)
    if len(gt_rows) != EXPECTED_PAGE_COUNT:
        raise ValueError(
            f"cohort page count {len(gt_rows)} != frozen {EXPECTED_PAGE_COUNT}; refusing to rewrite freeze"
        )
    denom = compute_cer_denominator(gt_rows, hyp_rows)
    if denom != EXPECTED_CER_DENOM:
        raise ValueError(
            f"CER denominator {denom} != frozen {EXPECTED_CER_DENOM}; scorer or GT changed"
        )

    raw_by = {(str(row.get("doc_id")), int(row.get("page") or 0)): row for row in raw_gt}
    pages: list[dict[str, Any]] = []
    docs: dict[str, dict[str, Any]] = {}
    for row in gt_rows:
        doc_id = str(row.get("doc_id") or "")
        page = int(row.get("page") or 0)
        text_gt = str(row.get("text_gt") or "")
        raw = raw_by.get((doc_id, page), {})
        pdf_sha = str(raw.get("sha256") or row.get("sha256") or "").lower()
        pages.append(
            {
                "doc_id": doc_id,
                "page": page,
                "page_type": row.get("page_type"),
                "pdf_sha256": pdf_sha,
                "gt_text_sha256": _sha256_text(text_gt),
                "gt_char_count_raw": len(text_gt),
                "document_path": raw.get("document_path") or row.get("document_path"),
                "source_url": raw.get("source_url") or row.get("source_url"),
                "origin": raw.get("origin") or row.get("origin"),
            }
        )
        if doc_id not in docs:
            docs[doc_id] = {
                "doc_id": doc_id,
                "pdf_sha256": pdf_sha,
                "document_path": raw.get("document_path") or row.get("document_path"),
                "source_url": raw.get("source_url") or row.get("source_url"),
                "fetched_at": raw.get("fetched_at"),
                "license_or_usage_note": raw.get("license_or_usage_note"),
                "pages": [],
            }
        docs[doc_id]["pages"].append(page)

    for doc in docs.values():
        doc["pages"] = sorted(set(int(p) for p in doc["pages"]))

    fixture_hashes = {
        "public_expand_pages.jsonl": _sha256_file(cer_gt_path),
        "public_expand_hypotheses.jsonl": _sha256_file(cer_hyp_path),
        "public_expand_teds_gt.jsonl": _sha256_file(teds_gt_path) if teds_gt_path.is_file() else "",
        "public_expand_teds_hypotheses.jsonl": _sha256_file(teds_hyp_path) if teds_hyp_path.is_file() else "",
        "public_expand_key_field_gt.jsonl": _sha256_file(kf_gt_path) if kf_gt_path.is_file() else "",
        "public_expand_key_field_hypotheses.jsonl": _sha256_file(kf_hyp_path) if kf_hyp_path.is_file() else "",
    }

    return {
        "schema_version": "1.0",
        "cohort_id": COHORT_ID,
        "mainline_baseline": MAINLINE_BASELINE,
        "scorer_version": SCORER_VERSION,
        "page_count": len(pages),
        "cer_denominator_chars": denom,
        "teds_note": (
            "TEDS hypotheses place OCR text into the PDF ruling-line / table-grid "
            "(pdf table lines assist). That is not a pure E2E OCR-only table tree score; "
            "document separately if an E2E-only path is tested."
        ),
        "product_pass": False,
        "business_pass": False,
        "t005": "unchanged",
        "claim_scope": "engineering_compare_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture_sha256": fixture_hashes,
        "documents": sorted(docs.values(), key=lambda row: str(row["doc_id"])),
        "pages": pages,
        "integrity": {
            "expected_page_count": EXPECTED_PAGE_COUNT,
            "expected_cer_denominator_chars": EXPECTED_CER_DENOM,
            "pages_never_dropped_from_denominator": True,
        },
    }


def load_cohort_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"cohort manifest missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("cohort manifest must be an object")
    return data


def verify_cohort_manifest(manifest: dict[str, Any] | None = None, *, path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    """Recompute freeze inputs and assert they still match the locked values."""
    current = build_cohort_manifest()
    frozen = manifest if manifest is not None else load_cohort_manifest(path)
    errors: list[str] = []
    if frozen.get("page_count") != current["page_count"]:
        errors.append(f"page_count {frozen.get('page_count')} != {current['page_count']}")
    if frozen.get("cer_denominator_chars") != current["cer_denominator_chars"]:
        errors.append(
            f"cer_denominator_chars {frozen.get('cer_denominator_chars')} != {current['cer_denominator_chars']}"
        )
    if frozen.get("scorer_version") != SCORER_VERSION:
        errors.append(f"scorer_version {frozen.get('scorer_version')} != {SCORER_VERSION}")
    frozen_pages = {(p["doc_id"], int(p["page"])) for p in frozen.get("pages") or []}
    current_pages = {(p["doc_id"], int(p["page"])) for p in current["pages"]}
    if frozen_pages != current_pages:
        errors.append("page set drifted from freeze")
    if frozen.get("fixture_sha256") != current["fixture_sha256"]:
        errors.append("fixture sha256 drifted from freeze")
    return {
        "ok": not errors,
        "errors": errors,
        "page_count": current["page_count"],
        "cer_denominator_chars": current["cer_denominator_chars"],
        "scorer_version": SCORER_VERSION,
    }


def write_cohort_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    payload = build_cohort_manifest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cohort-manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze / verify the cloud-compare OCR cohort.")
    parser.add_argument("--write", action="store_true", help="Write frozen cohort manifest.")
    parser.add_argument("--verify", action="store_true", help="Verify fixtures match the freeze.")
    parser.add_argument("--out", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)
    if args.write:
        payload = write_cohort_manifest(args.out)
        print(
            json.dumps(
                {
                    "cohort_id": payload["cohort_id"],
                    "page_count": payload["page_count"],
                    "cer_denominator_chars": payload["cer_denominator_chars"],
                    "scorer_version": payload["scorer_version"],
                    "path": str(args.out),
                    "product_pass": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.verify:
        result = verify_cohort_manifest(path=args.out)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
