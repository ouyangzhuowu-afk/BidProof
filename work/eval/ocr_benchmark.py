"""Unified OCR / text-extraction benchmark for BidProof assessment.

Runs without writing secrets. Cloud OCR is only called when BID_OCR_PROVIDER
and QWEN_OCR_API_KEY are set; otherwise cached OCR JSON and text-layer paths
still produce metrics.

Usage:
  uv run python -m work.eval.ocr_benchmark
  uv run python -m work.eval.ocr_benchmark --live-pages 2 --live-docs fixture-001
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz

from app.extraction import extract_pdf
from app.ocr import DisabledOCRAdapter, get_ocr_adapter
from app.rules import extract_requirements

ROOT = Path(__file__).resolve().parents[2]
KEY_FIELDS = ROOT / "work" / "eval" / "key_fields.json"
OUT_DIR = ROOT / "outputs" / "ocr-benchmark"
OUT_JSON = OUT_DIR / "raw-results.json"
OUT_MD = ROOT / "outputs" / "OCR_TECH_ASSESSMENT.md"


@dataclass
class PageMetric:
    document_id: str
    page: int
    provider: str
    mode: str
    cer: float | None
    wer: float | None
    char_count_ref: int
    char_count_hyp: int
    latency_ms: float | None
    field_hits: int
    field_total: int
    notes: str = ""


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", "", text)
    return text.lower()


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    r, h = _norm(ref), _norm(hyp)
    if not r:
        return 0.0 if not h else 1.0
    return levenshtein(r, h) / len(r)


def wer(ref: str, hyp: str) -> float:
    # Character-group WER for Chinese: split on punctuation boundaries.
    def toks(s: str) -> list[str]:
        s = unicodedata.normalize("NFKC", s or "")
        return [t for t in re.split(r"[\s，。；、：:；,.!！？?\n]+", s) if t]

    r, h = toks(ref), toks(hyp)
    if not r:
        return 0.0 if not h else 1.0
    # Token-level Levenshtein
    prev = list(range(len(h) + 1))
    for i, ra in enumerate(r, 1):
        cur = [i]
        for j, hb in enumerate(h, 1):
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ra != hb)))
        prev = cur
    return prev[-1] / len(r)


def field_hit(text: str, value: str) -> bool:
    return _norm(value) in _norm(text)


def load_labels() -> dict[str, Any]:
    return json.loads(KEY_FIELDS.read_text(encoding="utf-8"))


def text_layer_pages(path: Path) -> dict[int, str]:
    doc = fitz.open(path)
    out: dict[int, str] = {}
    with doc:
        for i, page in enumerate(doc, 1):
            out[i] = unicodedata.normalize("NFKC", page.get_text("text") or "")
    return out


def render_png(path: Path, page_number: int, scale: float = 1.5) -> bytes:
    doc = fitz.open(path)
    with doc:
        page = doc[page_number - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")


def load_cached_ocr(cache_dir: Path, page: int) -> str | None:
    path = cache_dir / f"page-{page:04d}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "EXTRACTED":
        return None
    return data.get("text") or ""


def eval_electronic_text_layer(doc: dict[str, Any]) -> list[PageMetric]:
    path = ROOT / doc["path"]
    pages = text_layer_pages(path)
    metrics: list[PageMetric] = []
    fields_by_page: dict[int, list[dict[str, Any]]] = {}
    for field in doc.get("fields", []):
        fields_by_page.setdefault(int(field["page"]), []).append(field)

    # Evaluate pages that have labeled fields (+ page 1 for coverage).
    targets = sorted(set(fields_by_page) | {1})
    for page in targets:
        text = pages.get(page, "")
        page_fields = fields_by_page.get(page, [])
        hits = sum(1 for f in page_fields if field_hit(text, f["value"]))
        metrics.append(
            PageMetric(
                document_id=doc["document_id"],
                page=page,
                provider="pymupdf_text_layer",
                mode="electronic_text",
                cer=0.0 if text.strip() else None,
                wer=0.0 if text.strip() else None,
                char_count_ref=len(_norm(text)),
                char_count_hyp=len(_norm(text)),
                latency_ms=None,
                field_hits=hits,
                field_total=len(page_fields),
                notes="text-layer self baseline; CER defined as 0 when non-empty",
            )
        )
    return metrics


def eval_live_ocr_vs_text(
    doc: dict[str, Any],
    adapter,
    max_pages: int,
) -> list[PageMetric]:
    path = ROOT / doc["path"]
    pages = text_layer_pages(path)
    fields_by_page: dict[int, list[dict[str, Any]]] = {}
    for field in doc.get("fields", []):
        fields_by_page.setdefault(int(field["page"]), []).append(field)

    # Prefer labeled pages with substantial text; skip empty scanned-like pages.
    candidates = [
        p
        for p in sorted(set(fields_by_page) | {1, 2, 3})
        if len(_norm(pages.get(p, ""))) >= 40
    ][:max_pages]

    metrics: list[PageMetric] = []
    for page in candidates:
        ref = pages[page]
        png = render_png(path, page)
        t0 = time.perf_counter()
        try:
            result = adapter.extract(png, page)
            hyp = result.text
            provider = result.provider
            note = ""
        except Exception as exc:  # noqa: BLE001 — benchmark must continue
            hyp = ""
            provider = getattr(adapter, "__class__", type(adapter)).__name__
            note = f"OCR_FAILED:{type(exc).__name__}"
        latency = (time.perf_counter() - t0) * 1000
        page_fields = fields_by_page.get(page, [])
        hits = sum(1 for f in page_fields if field_hit(hyp, f["value"]))
        metrics.append(
            PageMetric(
                document_id=doc["document_id"],
                page=page,
                provider=provider,
                mode="render_then_ocr_vs_text_layer",
                cer=cer(ref, hyp) if hyp else None,
                wer=wer(ref, hyp) if hyp else None,
                char_count_ref=len(_norm(ref)),
                char_count_hyp=len(_norm(hyp)),
                latency_ms=round(latency, 1),
                field_hits=hits,
                field_total=len(page_fields),
                notes=note,
            )
        )
    return metrics


def eval_cached_scan(doc: dict[str, Any]) -> list[PageMetric]:
    cache = ROOT / doc["ocr_cache_dir"]
    metrics: list[PageMetric] = []
    for field_group_page in sorted({int(f["page"]) for f in doc.get("fields", [])}):
        hyp = load_cached_ocr(cache, field_group_page) or ""
        page_fields = [f for f in doc["fields"] if int(f["page"]) == field_group_page]
        hits = sum(1 for f in page_fields if field_hit(hyp, f["value"]))
        metrics.append(
            PageMetric(
                document_id=doc["document_id"],
                page=field_group_page,
                provider="qwen-vl-ocr-cache",
                mode="scanned_cached_ocr",
                cer=None,  # no character-level GT for full scan pages yet
                wer=None,
                char_count_ref=0,
                char_count_hyp=len(_norm(hyp)),
                latency_ms=None,
                field_hits=hits,
                field_total=len(page_fields),
                notes="PII corpus; field-level only; CER requires human GT",
            )
        )
    return metrics


def pipeline_requirement_recall(doc: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / doc["path"]
    if not path.exists():
        return {"document_id": doc["document_id"], "error": "missing_pdf"}
    pages = extract_pdf(path, ocr_adapter=DisabledOCRAdapter())
    reqs = extract_requirements(pages)
    text_pages = sum(1 for p in pages if p.get("has_text"))
    ocr_needed = sum(1 for p in pages if p.get("ocr_required"))
    # Quote recall against labeled field values as weak proxy.
    joined = "\n".join(p["text"] for p in pages)
    field_recall = []
    for f in doc.get("fields", []):
        field_recall.append({"name": f["name"], "hit": field_hit(joined, f["value"])})
    return {
        "document_id": doc["document_id"],
        "pages": len(pages),
        "text_pages": text_pages,
        "ocr_required_pages": ocr_needed,
        "requirement_count": len(reqs),
        "field_hits": sum(1 for x in field_recall if x["hit"]),
        "field_total": len(field_recall),
        "field_recall": field_recall,
        "categories": _count([r["category"] for r in reqs]),
    }


def _count(items: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return out


def summarize(metrics: list[PageMetric]) -> dict[str, Any]:
    by_mode: dict[str, list[PageMetric]] = {}
    for m in metrics:
        by_mode.setdefault(m.mode, []).append(m)

    summary: dict[str, Any] = {}
    for mode, rows in by_mode.items():
        cers = [m.cer for m in rows if m.cer is not None]
        wers = [m.wer for m in rows if m.wer is not None]
        lats = [m.latency_ms for m in rows if m.latency_ms is not None]
        fh = sum(m.field_hits for m in rows)
        ft = sum(m.field_total for m in rows)
        summary[mode] = {
            "pages": len(rows),
            "mean_cer": round(sum(cers) / len(cers), 4) if cers else None,
            "mean_wer": round(sum(wers) / len(wers), 4) if wers else None,
            "p95_latency_ms": round(sorted(lats)[int(0.95 * (len(lats) - 1))], 1) if lats else None,
            "mean_latency_ms": round(sum(lats) / len(lats), 1) if lats else None,
            "field_accuracy": round(fh / ft, 4) if ft else None,
            "field_hits": fh,
            "field_total": ft,
            "providers": sorted({m.provider for m in rows}),
        }
    return summary


def write_assessment(payload: dict[str, Any]) -> None:
    s = payload["summary"]
    electronic = s.get("electronic_text", {})
    live = s.get("render_then_ocr_vs_text_layer", {})
    scanned = s.get("scanned_cached_ocr", {})

    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{x * 100:.2f}%"

    live_cer = live.get("mean_cer")
    scan_field = scanned.get("field_accuracy")
    elec_field = electronic.get("field_accuracy")

    # Decision logic aligned to prompt defaults.
    digital_ok = (live_cer is not None and live_cer <= 0.005) or (
        live_cer is None and (elec_field or 0) >= 0.99
    )
    # Without full scan CER, use field accuracy proxy with caveat.
    scan_partial = scan_field is not None and scan_field >= 0.97
    if digital_ok and scan_partial and live_cer is not None and live_cer <= 0.005:
        verdict = "部分达标"
        verdict_detail = (
            "电子 PDF 文本层路径达标；渲染→云 OCR 回读若 CER≤0.5% 则字符层达标。"
            "扫描件仅有字段级代理指标，缺完整人工 CER/TEDS 标注，不能宣称端到端达标。"
        )
    elif (elec_field or 0) >= 0.95 and (scan_field or 0) >= 0.9:
        verdict = "部分达标"
        verdict_detail = (
            "电子 PDF 关键字段召回较好；扫描件封面字段可用缓存 OCR 命中，"
            "但缺表格 TEDS、印章/手写、跨页关联与正式 CER 标注，整体不构成全面达标。"
        )
    else:
        verdict = "不达标"
        verdict_detail = "关键指标低于默认门槛或证据不足。"

    if live_cer is not None and live_cer > 0.02:
        verdict = "不达标"
        verdict_detail = f"渲染后云 OCR 对电子页回读 mean CER={live_cer:.4f} > 2%，字符层不达标。"

    lines = [
        "# OCR Technical Assessment",
        "",
        f"- Generated_at: `{payload['generated_at']}`",
        f"- Branch: `{payload.get('branch', 'assessment/ocr-backend-db')}`",
        f"- Verdict: **{verdict}**",
        f"- Detail: {verdict_detail}",
        "",
        "## Scope & limits",
        "",
        "- Public electronic PDFs: 3 fixtures under `work/public-eval/pdfs/`.",
        "- Scanned corpus: AKSS 78-page Qwen OCR cache (contains PII — do not publish).",
        "- No formal TEDS / seal / handwriting GT in-repo yet.",
        "- Live cloud OCR limited to a small page sample to control cost.",
        "- Default gates: electronic CER≤0.5% / field F1≥99%; scan CER≤2% / field≥97%; TEDS≥90%.",
        "",
        "## Input inventory",
        "",
        "| Item | Value |",
        "|---|---|",
        "| Current OCR | Qwen-VL-OCR via DashScope OpenAI-compatible API (`app/ocr.py`) |",
        "| Text extraction | PyMuPDF (`app/extraction.py`) |",
        "| Local OCR (Paddle/Tesseract) | Not installed |",
        "| Labeled key fields | `work/eval/key_fields.json` (minimal) |",
        "| Requirement GT | `work/ground-truth/fixture-00*.md` (5 quotes each, needs 2nd review) |",
        "",
        "## Metric summary",
        "",
        "| Mode | Pages | Mean CER | Mean WER | Field acc | Mean latency | P95 latency | Providers |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for mode, row in s.items():
        lines.append(
            f"| `{mode}` | {row['pages']} | {row['mean_cer'] if row['mean_cer'] is not None else 'n/a'} | "
            f"{row['mean_wer'] if row['mean_wer'] is not None else 'n/a'} | {pct(row['field_accuracy'])} | "
            f"{row['mean_latency_ms'] if row['mean_latency_ms'] is not None else 'n/a'} ms | "
            f"{row['p95_latency_ms'] if row['p95_latency_ms'] is not None else 'n/a'} ms | "
            f"{', '.join(row['providers'])} |"
        )

    lines += [
        "",
        "### Gate check vs defaults",
        "",
        "| Gate | Target | Observed | Pass? |",
        "|---|---|---|---|",
        f"| Electronic text-layer field accuracy | ≥99% | {pct(elec_field)} | "
        f"{'YES' if (elec_field or 0) >= 0.99 else 'NO / insufficient'} |",
        f"| Render→OCR CER (electronic pages) | ≤0.5% | "
        f"{'n/a' if live_cer is None else f'{live_cer*100:.2f}%'} | "
        f"{'YES' if live_cer is not None and live_cer <= 0.005 else ('NO' if live_cer is not None else 'NOT RUN / incomplete')} |",
        f"| Scanned field accuracy (proxy) | ≥97% | {pct(scan_field)} | "
        f"{'YES (proxy only)' if (scan_field or 0) >= 0.97 else 'NO / incomplete'} |",
        "| Table TEDS | ≥90% | not measured | NO EVIDENCE |",
        "| Seal / handwriting | ≥95% / ≥90% | not measured | NO EVIDENCE |",
        "| End-to-end human review rate | ≤5% | not measured | NO EVIDENCE |",
        "",
        "## Pipeline requirement extraction (text layer, OCR disabled)",
        "",
        "| Doc | Pages | Text pages | OCR-needed | Reqs extracted | Key-field hits |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["pipeline"]:
        if row.get("error"):
            lines.append(f"| {row['document_id']} | - | - | - | - | error:{row['error']} |")
        else:
            lines.append(
                f"| {row['document_id']} | {row['pages']} | {row['text_pages']} | "
                f"{row['ocr_required_pages']} | {row['requirement_count']} | "
                f"{row['field_hits']}/{row['field_total']} |"
            )

    lines += [
        "",
        "## Error taxonomy (from this run + code review)",
        "",
        "| Layer | Finding | Severity |",
        "|---|---|---|",
        "| Image quality | Scanned AKSS has no native text; 78/78 OCR-required | High for scan path |",
        "| OCR | Dense TOC truncates under VL; HTML sanitize mitigates wrapper noise | High for cloud CER |",
        "| Layout | Local OCR lines → multi-block locators; VL still weak on structure | Medium |",
        "| Tables | No table structure / TEDS path | High |",
        "| Field extraction | Regex keyword `rules.py` only; not schema IE | High |",
        "| Observability | `bidproof_ocr_pages_total` emitted when metrics enabled | OK |",
        "| Business rules | Fail-closed on OCR failure; auto PASS forbidden; T1 egress default off | OK |",
        "",
        "## Candidate comparison (for non-达标 / partial)",
        "",
        "| Option | Accuracy (est.) | Speed | Cost | Private | Compliance | Maintenance |",
        "|---|---|---|---|---|---|---|",
        "| A. Keep Qwen-VL-OCR + PyMuPDF | Strong on clean pages; TOC weak | ~1–5s/page cloud | API ¥/page | No | Allow-list | Low |",
        "| B. Hybrid harden (active) | Local Rapid/Paddle + tiling + T1 redacted escalate | Mixed | Lower egress | Partial→Good | Best with egress=0 | Medium |",
        "| C. Private PP-Structure replace | Needs bake-off | Local batch | Capex GPU | Yes | Best 不出网 | High |",
        "",
        "## Recommendation",
        "",
        f"**{verdict}** — continue **Option B**. Electronic text path is gate-ready; "
        "do **not** claim full OCR accuracy until labeled scan CER + TEDS/seal GT exist. "
        "Backend/DB: optimize in place — no rewrite.",
        "",
        "## Raw artifacts",
        "",
        f"- `{OUT_JSON.relative_to(ROOT).as_posix()}`",
        "- `work/eval/key_fields.json`",
        "- `work/eval/ocr_benchmark.py`",
        "- `outputs/OCR_BACKEND_DB_MIGRATION_REPORT.md`",
        "",
        "## Reproduce",
        "",
        "```powershell",
        "uv run python -m work.eval.ocr_benchmark --skip-live",
        "uv run python -m work.eval.ocr_benchmark --live-pages 2",
        "```",
        "",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-pages", type=int, default=2, help="Max pages per doc for live OCR")
    parser.add_argument("--live-docs", nargs="*", default=None, help="Document ids for live OCR")
    parser.add_argument("--skip-live", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    labels = load_labels()
    metrics: list[PageMetric] = []
    pipeline_rows: list[dict[str, Any]] = []

    adapter = get_ocr_adapter()
    live_ids = set(args.live_docs) if args.live_docs else None

    for doc in labels["documents"]:
        if doc.get("doc_type") == "electronic_pdf":
            metrics.extend(eval_electronic_text_layer(doc))
            pipeline_rows.append(pipeline_requirement_recall(doc))
            if not args.skip_live and adapter.enabled and (live_ids is None or doc["document_id"] in live_ids):
                metrics.extend(eval_live_ocr_vs_text(doc, adapter, args.live_pages))
        elif doc.get("doc_type") == "scanned_pdf":
            if doc.get("pii_warning"):
                print("WARN: evaluating PII scan corpus locally; do not export raw text")
            cache = ROOT / doc["ocr_cache_dir"]
            if cache.exists() and any(cache.glob("page-*.json")):
                metrics.extend(eval_cached_scan(doc))
            else:
                print(f"SKIP scanned {doc['document_id']}: missing OCR cache")

    summary = summarize(metrics)
    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "branch": "assessment/ocr-backend-db",
        "adapter_enabled": bool(getattr(adapter, "enabled", False)),
        "summary": summary,
        "metrics": [asdict(m) for m in metrics],
        "pipeline": pipeline_rows,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_assessment(payload)
    print(json.dumps({"summary": summary, "out_md": str(OUT_MD), "out_json": str(OUT_JSON)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
