"""S-A-09: rate-limited public government tender PDF collector.

Engineering fixtures only. Never writes `outputs/pilot-ledger.csv` or
`outputs/icp-outreach.csv`. Failed/dead URLs are recorded in the manifest
but do not count as completed documents.

Usage:
  uv run python -m work.eval.collect_public_tenders
  uv run python -m work.eval.collect_public_tenders --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import fitz

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES = ROOT / "work" / "eval" / "public_tender_candidates.json"
DEFAULT_MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"
DEFAULT_PDFS_DIR = ROOT / "work" / "public-eval" / "pdfs"
DEFAULT_REPORT_DIR = ROOT / "outputs" / "ocr-benchmark"
FORBIDDEN_OUTPUT_TOKENS = ("pilot-ledger", "icp-outreach")
DEFAULT_DELAY_SECONDS = 2.0
MAX_BYTES = 20 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (compatible; BidProof-public-eval-collector/S-A-09; "
    "+https://github.com/ouyangzhuowu-afk/BidProof) "
    "rate-limited engineering fixtures"
)
LICENSE_NOTE = (
    "公开政府采购/公共资源交易平台公开发布的招标采购文件，"
    "仅作为内部工程能力回归的公开 DATA 备份；不用于对外产品承诺，不替代官方分发授权。"
)
FetchFn = Callable[[str], tuple[int, bytes, str]]
SleepFn = Callable[[float], None]


class ForbiddenOutputError(ValueError):
    """Raised when a write target looks like a business ledger."""


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def assert_safe_output_path(path: Path) -> Path:
    text = str(path).replace("\\", "/").lower()
    if any(token in text for token in FORBIDDEN_OUTPUT_TOKENS):
        raise ForbiddenOutputError(
            f"refusing path that looks like a business ledger: {path}"
        )
    return path


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def is_pdf(payload: bytes) -> bool:
    return payload.lstrip().startswith(b"%PDF-")


def pdf_page_count(payload: bytes) -> int | None:
    try:
        doc = fitz.open(stream=payload, filetype="pdf")
        count = int(doc.page_count)
        doc.close()
        return count
    except Exception:
        return None


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = load_json(path)
    manifest.setdefault("schema_version", "1.0")
    manifest.setdefault("documents", [])
    manifest.setdefault("fetch_failures", [])
    manifest.setdefault("excluded", [])
    return manifest


def load_candidates(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    rows = data.get("candidates", [])
    if not isinstance(rows, list):
        raise ValueError(f"candidates must be a list: {path}")
    return [row for row in rows if isinstance(row, dict)]


def completed_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    done: list[dict[str, Any]] = []
    for row in manifest.get("documents") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").lower() in {"failed", "dead"}:
            continue
        url = str(row.get("source_url") or row.get("file_url") or "").strip()
        sha = str(row.get("sha256") or "").strip()
        if url and sha:
            done.append(row)
    return done


def failed_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("fetch_failures") or []
    return [row for row in rows if isinstance(row, dict)]


def summarize(
    manifest: dict[str, Any],
    newly_added: int = 0,
    newly_failed: int = 0,
) -> dict[str, Any]:
    return {
        "completed_documents": len(completed_documents(manifest)),
        "failed_urls": len(failed_records(manifest)),
        "newly_added": int(newly_added),
        "newly_failed": int(newly_failed),
        "this_leaf_completed": len(
            [row for row in completed_documents(manifest) if row.get("leaf_id") == "S-A-09"]
        ),
        "this_leaf_failed": len(
            [row for row in failed_records(manifest) if row.get("leaf_id") == "S-A-09"]
        ),
        "product_pass": False,
        "business_pass": False,
        "t005": False,
        "leaf_id": "S-A-09",
    }


def _row_urls(row: dict[str, Any]) -> set[str]:
    urls = set()
    for key in ("source_url", "file_url"):
        value = str(row.get(key) or "").strip()
        if value:
            urls.add(value)
    return urls


def _already_completed_url(manifest: dict[str, Any], url: str) -> bool:
    target = (url or "").strip()
    if not target:
        return False
    return any(target in _row_urls(row) for row in completed_documents(manifest))


def _already_failed_url(manifest: dict[str, Any], url: str) -> bool:
    target = (url or "").strip()
    if not target:
        return False
    return any(target in _row_urls(row) for row in failed_records(manifest))


def _document_path(row: dict[str, Any], pdfs_dir: Path) -> Path:
    if row.get("path"):
        return ROOT / str(row["path"])
    filename = str(row.get("filename") or "").strip()
    return pdfs_dir / filename


def validate_manifest(manifest: dict[str, Any], pdfs_dir: Path) -> list[str]:
    issues: list[str] = []
    seen_sha: set[str] = set()
    for row in completed_documents(manifest):
        doc_id = str(row.get("document_id") or row.get("filename") or "<unknown>")
        url = str(row.get("source_url") or "").strip()
        if not url.startswith("http"):
            issues.append(f"{doc_id}: completed row missing http source_url")
        sha = str(row.get("sha256") or "").strip()
        if len(sha) != 64:
            issues.append(f"{doc_id}: completed row missing sha256")
        elif sha in seen_sha:
            issues.append(f"{doc_id}: duplicate sha256")
        else:
            seen_sha.add(sha)
        path = _document_path(row, pdfs_dir)
        if not path.is_file():
            issues.append(f"{doc_id}: missing PDF {path}")
        elif sha and sha256_hex(path.read_bytes()) != sha:
            issues.append(f"{doc_id}: sha256 mismatch for {path}")
    for index, row in enumerate(failed_records(manifest)):
        if not str(row.get("source_url") or "").strip():
            issues.append(f"fetch_failures[{index}] missing source_url")
        if row.get("counts_as_completed") is not False:
            issues.append(f"fetch_failures[{index}] must set counts_as_completed=false")
        if row.get("sha256"):
            issues.append(f"fetch_failures[{index}] must not carry sha256")
    return issues


def default_fetch(url: str) -> tuple[int, bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("Content-Type") or "")
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_BYTES:
                return status, b"", f"too-large:{length}"
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    return status, b"", "too-large-stream"
                chunks.append(chunk)
            return status, b"".join(chunks), content_type
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read(4096)
        except Exception:
            body = b""
        return int(exc.code), body, str(exc)
    except Exception as exc:
        return 0, b"", str(exc)


def _safe_filename(candidate_id: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in candidate_id).strip("-")
    return f"{slug or 'public-tender'}.pdf"


def _failure_error(status: int, payload: bytes, content_type: str) -> str:
    if status == 0 and content_type:
        return f"network:{content_type}"
    if status != 200:
        return f"HTTP {status}"
    if content_type.startswith("too-large"):
        return content_type
    if not is_pdf(payload):
        return "not_pdf"
    if pdf_page_count(payload) is None:
        return "pdf_unreadable"
    return "unknown"


def _upsert_failure(manifest: dict[str, Any], record: dict[str, Any]) -> None:
    failures = list(failed_records(manifest))
    url = str(record.get("source_url") or "")
    updated = False
    for index, existing in enumerate(failures):
        if str(existing.get("source_url") or "") == url:
            failures[index] = record
            updated = True
            break
    if not updated:
        failures.append(record)
    manifest["fetch_failures"] = failures


def _drop_failure(manifest: dict[str, Any], url: str) -> None:
    manifest["fetch_failures"] = [
        row for row in failed_records(manifest) if str(row.get("source_url") or "") != url
    ]


def run_collection(
    candidates: list[dict[str, Any]],
    manifest_path: Path,
    pdfs_dir: Path,
    fetch: FetchFn | None = None,
    sleeper: SleepFn | None = None,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    now: str | None = None,
    retry_failures: bool = False,
) -> dict[str, Any]:
    fetch_fn = fetch if fetch is not None else default_fetch
    sleep_fn = sleeper if sleeper is not None else time.sleep
    stamp = now or utc_now()
    assert_safe_output_path(manifest_path)
    assert_safe_output_path(pdfs_dir)
    manifest = load_manifest(manifest_path)
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    newly_added = 0
    newly_failed = 0
    remote_attempts = 0

    for candidate in candidates:
        url = str(candidate.get("file_url") or candidate.get("source_url") or "").strip()
        if not url:
            continue
        if _already_completed_url(manifest, url):
            continue
        if not retry_failures and _already_failed_url(manifest, url):
            continue
        if remote_attempts and delay_seconds > 0:
            sleep_fn(delay_seconds)
        remote_attempts += 1
        status, payload, content_type = fetch_fn(url)
        candidate_id = str(candidate.get("candidate_id") or f"pub-{remote_attempts:03d}")
        pages = pdf_page_count(payload) if status == 200 and is_pdf(payload) else None
        if status != 200 or not is_pdf(payload) or pages is None:
            _upsert_failure(
                manifest,
                {
                    "candidate_id": candidate_id,
                    "title": candidate.get("title"),
                    "publisher": candidate.get("publisher"),
                    "source_url": str(candidate.get("source_url") or url),
                    "file_url": url,
                    "error": _failure_error(status, payload, content_type),
                    "http_status": status,
                    "content_type": content_type,
                    "failed_at": stamp,
                    "counts_as_completed": False,
                    "leaf_id": "S-A-09",
                },
            )
            newly_failed += 1
            continue
        filename = _safe_filename(candidate_id)
        dest = pdfs_dir / filename
        dest.write_bytes(payload)
        rel_path = _display_path(dest)
        document = {
            "document_id": candidate_id,
            "filename": filename,
            "title": candidate.get("title") or candidate_id,
            "publisher": candidate.get("publisher") or "",
            "source_type": candidate.get("source_type") or "public_government_tender",
            "domain": candidate.get("domain") or "hospital_meddevice",
            "source_url": str(candidate.get("source_url") or url),
            "file_url": url,
            "pages": pages,
            "sha256": sha256_hex(payload),
            "bytes": len(payload),
            "fetched_at": stamp,
            "license_or_usage_note": LICENSE_NOTE,
            "reuse_of_repo_fixture": False,
            "internal_test_allowed": True,
            "enterprise_confidential": False,
            "notes": "S-A-09 public government tender fetch; engineering fixture only. Not T-005.",
            "path": rel_path,
            "status": "fetched",
            "leaf_id": "S-A-09",
        }
        documents = [row for row in (manifest.get("documents") or []) if isinstance(row, dict)]
        documents.append(document)
        manifest["documents"] = documents
        _drop_failure(manifest, url)
        newly_added += 1

    counts = summarize(manifest, newly_added=newly_added, newly_failed=newly_failed)
    leaves = [str(item) for item in (manifest.get("campaign_leaves") or [])]
    if "S-A-09" not in leaves:
        leaves.append("S-A-09")
    manifest["campaign_leaves"] = leaves
    manifest["s_a_09"] = {
        "leaf_id": "S-A-09",
        "purpose": "Public government tender corpus expansion (engineering fixtures only).",
        "not_t005": True,
        "product_pass": False,
        "failed_urls_do_not_count_as_completed": True,
        "rate_limit_seconds": delay_seconds,
        "last_run_at": stamp,
        "counts": counts,
    }
    manifest["counts"] = counts
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return counts | {"manifest": _display_path(manifest_path), "pdfs_dir": _display_path(pdfs_dir)}


def write_fetch_report(report: dict[str, Any], report_dir: Path) -> Path:
    assert_safe_output_path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / "public-tender-fetch-report.md"
    json_path = report_dir / "public-tender-fetch-report.json"
    markdown = "\n".join(
        [
            "# S-A-09 public tender fetch report",
            "",
            "Engineering fixtures only. This is **not a product PASS** and is not T-005 / business acceptance.",
            "Failed/dead URLs recorded in the manifest do **not** count as completed documents.",
            "OCR/scan PASS gates were not relaxed (line CER remains ≤ 2%).",
            "",
            "| Metric | Count |",
            "|---|---:|",
            f"| newly added | {report.get('this_leaf_completed', report.get('newly_added', 0))} |",
            f"| newly failed | {report.get('this_leaf_failed', report.get('newly_failed', 0))} |",
            f"| completed documents (corpus total) | {report.get('completed_documents', 0)} |",
            f"| failed URLs (corpus total, not counted) | {report.get('failed_urls', 0)} |",
            "",
            "## Reproduce",
            "",
            "```bash",
            "uv run python -m work.eval.collect_public_tenders --delay 2",
            "uv run python -m work.eval.collect_public_tenders --check",
            "# Known fetch_failures are skipped unless you pass --retry-failures",
            "```",
            "",
            "See `work/public-eval/FETCH.md`.",
            "",
        ]
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch public government tender PDFs into the eval corpus (S-A-09)."
    )
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pdfs-dir", type=Path, default=DEFAULT_PDFS_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--limit", type=int, default=0, help="Optional candidate cap (0 = all).")
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="Re-attempt URLs already listed in fetch_failures (default: skip them).",
    )
    parser.add_argument("--check", action="store_true", help="Validate the canonical manifest only.")
    args = parser.parse_args(argv)

    try:
        if args.check:
            manifest = load_manifest(args.manifest)
            issues = validate_manifest(manifest, args.pdfs_dir)
            if issues:
                print("FAIL")
                for issue in issues:
                    print(f"- {issue}")
                return 1
            summary = summarize(manifest)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        candidates = load_candidates(args.candidates)
        if args.limit and args.limit > 0:
            candidates = candidates[: args.limit]
        report = run_collection(
            candidates=candidates,
            manifest_path=args.manifest,
            pdfs_dir=args.pdfs_dir,
            delay_seconds=args.delay,
            retry_failures=args.retry_failures,
        )
        write_fetch_report(report, args.report_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except ForbiddenOutputError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
