"""Resumable local OCR batch runner for scanned upload PDFs.

The runner is intentionally opt-in. Without BID_OCR_PROVIDER=qwen-vl-ocr and
QWEN_OCR_API_KEY it emits a plan and performs no network request.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import fitz

from app.ocr import OCRUnavailable, get_ocr_adapter


ROOT = Path(__file__).resolve().parents[1]


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def run(source: Path, output_dir: Path, limit: int | None = None, retry_failed: bool = False) -> dict:
    adapter = get_ocr_adapter()
    output_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(source)
    pages = [index + 1 for index, page in enumerate(document) if not (page.get_text("text") or "").strip()]
    if limit is not None:
        pages = pages[:limit]
    try:
        source_label = str(source.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        source_label = source.name
    summary = {
        "source": source_label,
        "pages_requiring_ocr": pages,
        "adapter_enabled": bool(adapter.enabled),
        "provider": "qwen-vl-ocr" if adapter.enabled else "disabled",
        "completed": [],
        "failed": [],
        "skipped_existing": [],
        "retried_failed": [],
    }
    if not adapter.enabled:
        summary["blocked_reason"] = "OCR provider is disabled or QWEN_OCR_API_KEY is absent"
        _atomic_write(output_dir / "batch-summary.json", summary)
        document.close()
        return summary
    for page_number in pages:
        result_path = output_dir / f"page-{page_number:04d}.json"
        if result_path.exists():
            try:
                existing = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
            if not (retry_failed and existing.get("status") == "FAILED"):
                summary["skipped_existing"].append(page_number)
                continue
            summary["retried_failed"].append(page_number)
        page = document[page_number - 1]
        try:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            result = adapter.extract(pixmap.tobytes("png"), page_number)
            _atomic_write(
                result_path,
                {"page": page_number, "status": "EXTRACTED", "provider": result.provider, "text": result.text},
            )
            summary["completed"].append(page_number)
        except OCRUnavailable:
            _atomic_write(result_path, {"page": page_number, "status": "FAILED", "error": "OCR_UNAVAILABLE"})
            summary["failed"].append(page_number)
    document.close()
    _atomic_write(output_dir / "batch-summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run resumable OCR for a scanned upload PDF")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None, help="Limit pages for a smoke run")
    parser.add_argument("--retry-failed", action="store_true", help="Retry pages whose prior result status is FAILED")
    args = parser.parse_args()
    summary = run(
        args.source.resolve(),
        (ROOT / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir.resolve(),
        args.limit,
        retry_failed=args.retry_failed,
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "pages_requiring_ocr"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
