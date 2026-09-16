"""Local RapidOCR CER vs PDF text-layer (and optional JPEG synthetic-scan).

Default: egress off — never calls cloud. Optional T1 hard-page escalate only when
BIDPROOF_OCR_EGRESS_ALLOWED=1 and a cloud adapter is configured.

Usage:
  uv run --extra ocr python -m work.eval.rapidocr_cer
  uv run --extra ocr python -m work.eval.rapidocr_cer --pages-per-doc 3 --synthetic
"""

from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz

from app.ocr import RapidOCRAdapter, get_cloud_ocr_adapter
from app.ocr_privacy import classify_page_text, egress_allowed_for_cloud, egress_mode, redact_png_bytes
from work.eval.ocr_benchmark import cer, wer

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "work" / "training-corpus" / "tender-public" / "manifest.json"
OUT_JSON = ROOT / "outputs" / "ocr-benchmark" / "rapidocr-cer.json"
OUT_MD = ROOT / "outputs" / "ocr-benchmark" / "RAPIDOCR_CER_REPORT.md"
SYN_DIR = ROOT / "work" / "training-corpus" / "tender-public" / "synthetic-scans"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return "".join(text.split())


def _docs() -> list[dict[str, Any]]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [d for d in data.get("documents", []) if d.get("ok") and d.get("path")]


def _page_text(doc: fitz.Document, page_index: int) -> str:
    return unicodedata.normalize("NFKC", doc[page_index].get_text("text") or "")


def _render_png(page: fitz.Page, scale: float = 1.5) -> bytes:
    return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")


def _synthetic_jpeg(png_bytes: bytes, quality: int = 40) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    # Mild downsample to mimic scan/fax.
    w, h = img.size
    img = img.resize((max(1, w // 2), max(1, h // 2)), Image.Resampling.BILINEAR)
    img = img.resize((w, h), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _pick_pages(doc: fitz.Document, n: int) -> list[int]:
    """Prefer cover + a dense middle page + last page when available."""
    total = doc.page_count
    if total <= 0:
        return []
    if total <= n:
        return list(range(total))
    picks = {0, total // 2, total - 1}
    i = 1
    while len(picks) < n and i < total:
        picks.add(i)
        i += 1
    return sorted(picks)[:n]


def _hard_page(ref: str, hyp: str, page_cer: float) -> bool:
    if page_cer >= 0.08:
        return True
    if len(_norm(ref)) >= 800 and len(_norm(hyp)) < 0.5 * len(_norm(ref)):
        return True
    risk = classify_page_text(ref)
    return "license" in risk.page_types or "seal_like" in risk.page_types


def eval_doc(
    row: dict[str, Any],
    adapter: RapidOCRAdapter,
    *,
    pages_per_doc: int,
    synthetic: bool,
    try_t1: bool,
) -> list[dict[str, Any]]:
    path = ROOT / row["path"]
    doc = fitz.open(path)
    metrics: list[dict[str, Any]] = []
    try:
        for page_index in _pick_pages(doc, pages_per_doc):
            page = doc[page_index]
            ref = _page_text(doc, page_index)
            if len(_norm(ref)) < 20:
                continue
            png = _render_png(page)
            modes = [("rapidocr_clean_render", png)]
            if synthetic:
                jpeg = _synthetic_jpeg(png)
                syn_path = SYN_DIR / f"{row['document_id']}-p{page_index + 1:03d}.jpg"
                SYN_DIR.mkdir(parents=True, exist_ok=True)
                syn_path.write_bytes(jpeg)
                modes.append(("rapidocr_synthetic_scan", jpeg))

            for mode, image_bytes in modes:
                t0 = time.perf_counter()
                result = None
                try:
                    result = adapter.extract(image_bytes, page_index + 1)
                    hyp = result.text
                    provider = result.provider
                    conf = result.confidence
                    err = ""
                except Exception as exc:  # noqa: BLE001
                    hyp, provider, conf, err = "", "rapidocr", None, str(exc)
                latency = (time.perf_counter() - t0) * 1000
                page_cer = cer(ref, hyp) if hyp else 1.0
                page_wer = wer(ref, hyp) if hyp else 1.0
                hard = _hard_page(ref, hyp, page_cer)
                t1_meta: dict[str, Any] = {"attempted": False, "egress": "none"}
                if try_t1 and hard and mode == "rapidocr_clean_render" and result is not None:
                    t1_meta = _maybe_t1(page, page_index + 1, hyp, result.lines)
                    if t1_meta.get("cloud_text"):
                        cloud_hyp = t1_meta["cloud_text"]
                        t1_meta["cer_after"] = cer(ref, cloud_hyp)
                        t1_meta["wer_after"] = wer(ref, cloud_hyp)

                metrics.append(
                    {
                        "document_id": row["document_id"],
                        "page": page_index + 1,
                        "mode": mode,
                        "provider": provider,
                        "cer": page_cer,
                        "wer": page_wer,
                        "ref_chars": len(_norm(ref)),
                        "hyp_chars": len(_norm(hyp)),
                        "latency_ms": round(latency, 1),
                        "confidence": conf,
                        "hard_page": hard,
                        "error": err,
                        "t1": t1_meta,
                    }
                )
    finally:
        doc.close()
    return metrics


def _maybe_t1(page: fitz.Page, page_number: int, local_text: str, lines: tuple) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "attempted": True,
        "egress_mode": egress_mode(),
        "egress_allowed": egress_allowed_for_cloud(),
    }
    if not egress_allowed_for_cloud():
        meta["egress"] = "blocked_policy"
        meta["note"] = "BIDPROOF_OCR_EGRESS_ALLOWED!=1 — skip cloud"
        return meta
    cloud = get_cloud_ocr_adapter()
    if not cloud.enabled:
        meta["egress"] = "cloud_unavailable"
        return meta
    png = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
    redacted = redact_png_bytes(png, lines)
    meta["masked_lines"] = redacted.masked_line_count
    if not redacted.clean:
        meta["egress"] = "blocked_residual_pii"
        meta["residuals"] = redacted.residual_findings
        return meta
    try:
        cloud_result = cloud.extract(redacted.image_bytes, page_number)
    except Exception as exc:  # noqa: BLE001
        meta["egress"] = "cloud_failed"
        meta["error"] = str(exc)
        return meta
    meta["egress"] = "redacted_cloud"
    meta["cloud_provider"] = cloud_result.provider
    meta["cloud_text"] = cloud_result.text
    return meta


def summarize(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in sorted({m["mode"] for m in metrics}):
        rows = [m for m in metrics if m["mode"] == mode and not m.get("error")]
        if not rows:
            continue
        cers = [m["cer"] for m in rows]
        out[mode] = {
            "pages": len(rows),
            "mean_cer": statistics.mean(cers),
            "median_cer": statistics.median(cers),
            "p95_cer": sorted(cers)[max(0, int(len(cers) * 0.95) - 1)],
            "mean_wer": statistics.mean(m["wer"] for m in rows),
            "mean_latency_ms": statistics.mean(m["latency_ms"] for m in rows),
            "hard_pages": sum(1 for m in rows if m["hard_page"]),
            "gate_cer_le_2pct": statistics.mean(cers) <= 0.02,
        }
    return out


def write_report(payload: dict[str, Any]) -> None:
    lines = [
        "# RapidOCR CER Report",
        "",
        f"- Generated_at: `{payload['generated_at']}`",
        f"- Egress allowed: `{payload['egress_allowed']}` (mode={payload['egress_mode']})",
        f"- Docs evaluated: {payload['doc_count']}",
        "",
        "## Summary",
        "",
        "| Mode | Pages | Mean CER | Median CER | P95 CER | Mean WER | Mean latency | Gate ≤2% |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for mode, s in payload["summary"].items():
        lines.append(
            f"| `{mode}` | {s['pages']} | {s['mean_cer']:.4f} | {s['median_cer']:.4f} | "
            f"{s['p95_cer']:.4f} | {s['mean_wer']:.4f} | {s['mean_latency_ms']:.0f} ms | "
            f"{'YES' if s['gate_cer_le_2pct'] else 'NO'} |"
        )
    lines += [
        "",
        "## Method notes",
        "",
        "- Reference = native PDF text layer (electronic tenders).",
        "- Hypothesis = RapidOCR ONNX on rendered page (and optional JPEG Q40 synthetic scan).",
        "- T1 redacted cloud only runs when egress is explicitly allowed; otherwise hard pages stay local.",
        "",
        f"Raw: `{OUT_JSON.relative_to(ROOT).as_posix()}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages-per-doc", type=int, default=3)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--try-t1", action="store_true", help="Attempt T1 only if egress allowed")
    args = parser.parse_args()

    os.environ.setdefault("BID_OCR_PROVIDER", "rapid")
    adapter = RapidOCRAdapter()
    if not adapter.enabled:
        raise SystemExit("RapidOCR not available; run: uv sync --extra ocr")

    docs = _docs()
    metrics: list[dict[str, Any]] = []
    for row in docs:
        metrics.extend(
            eval_doc(
                row,
                adapter,
                pages_per_doc=args.pages_per_doc,
                synthetic=args.synthetic,
                try_t1=args.try_t1,
            )
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "egress_allowed": egress_allowed_for_cloud(),
        "egress_mode": egress_mode(),
        "doc_count": len(docs),
        "summary": summarize(metrics),
        "metrics": metrics,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(payload)
    print(json.dumps({"summary": payload["summary"], "out": str(OUT_JSON)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
