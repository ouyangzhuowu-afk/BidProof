# OCR Technical Assessment

- Generated_at: `2026-09-16T01:05:00+08:00` (Option B + T1 harden refresh)
- Branch: `assessment/ocr-backend-db`
- Verdict: **部分达标（电子文本层） / 不达标（云 OCR 字符层 & 表格/印章全链路）**
- Product claim “招投标 OCR 精准度全面达标”: **不可宣称**

### Bottom line

| Path | Verdict |
|---|---|
| Born-digital PDF / DOCX via text extractors | **达标** for sampled key fields (14/14 public PDF) and hospital redacted DOCX pipeline (105 reqs extracted) |
| Render page → Qwen-VL-OCR → compare to text layer | **不达标** mean CER **23.77%** (prior live sample; TOC truncation dominates); clean body pages ~1.6–1.8% CER |
| Local RapidOCR / Hybrid / T1 redacted escalate | **Engineering ready**; accuracy bake-off vs labeled scans **not yet** (egress default off) |
| Tables / seals / handwriting / E2E review rate | **No evidence → cannot claim pass** |

## Scope & limits

- Public electronic PDFs: 12 fixtures under `work/public-eval/pdfs/`.
- Hospital ICP sample: desensitized cryostat consult DOCX (`work/eval/meddevice-redacted/`) — **text path**, not scan OCR.
- Scanned corpus: AKSS 78-page Qwen OCR cache (**PII — do not publish**).
- Live cloud OCR sample (prior): 4 pages, cost-controlled; this refresh ran offline (`adapter_enabled=false`).
- Default gates: electronic CER≤0.5% / field≥99%; scan CER≤2% / field≥97%; TEDS≥90%.

## Metric summary

| Mode | Pages | Mean CER | Mean WER | Field acc | Mean latency | P95 latency | Providers |
|---|---:|---:|---:|---:|---:|---:|---|
| `electronic_text` (2026-09-16 offline) | 9 | 0.0 | 0.0 | 100% | n/a | n/a | pymupdf_text_layer |
| `render_then_ocr_vs_text_layer` (prior live) | 4 | 0.2377 | 0.6028 | 83.3% | 2417 ms | 2564 ms | qwen-vl-ocr |
| `scanned_cached_ocr` (prior) | 1 | n/a | n/a | 100% | n/a | n/a | qwen-vl-ocr-cache |

### Stratified live OCR (prior 4 pages — still governing cloud CER gate)

| Doc | Page | Type | CER | Notes |
|---|---:|---|---:|---|
| fixture-001 | 2 | body | ~0.018 | Near gate after HTML sanitize |
| fixture-001 | 3 | body | ~0.000 | Pass |
| fixture-002 | 1 | cover | ~0.016 | Near gate |
| fixture-002 | 2 | **TOC** | ~0.917 | Truncation / structure loss |

### Hospital redacted sample (text path)

| Item | Value |
|---|---|
| File | `consult-cryostat-redacted.docx` |
| Pages/blocks | 990 line blocks |
| Chars | 29640 |
| Requirements extracted | 105 |
| Labels seen | 关键日期, 医疗器械资质, 医院业绩/售后, 废标/否决, 授权配送, 签章要求, 评分项, 资格条件 |

### Gate check

| Gate | Target | Observed | Pass? |
|---|---|---|---|
| Electronic text-layer field accuracy | ≥99% | 100% | YES |
| Render→OCR CER (all sampled pages) | ≤0.5% | 23.77% | NO |
| Render→OCR CER (excluding TOC) | ≤0.5% | ~1.1–1.8% | NO (close but over) |
| Scanned field accuracy (proxy) | ≥97% | 100% proxy only | YES proxy only |
| Table TEDS | ≥90% | not measured | NO EVIDENCE |
| Seal / handwriting | ≥95% / ≥90% | not measured | NO EVIDENCE |

## Pipeline requirement extraction (OCR disabled)

| Doc | Pages | Text pages | OCR-needed | Reqs | Key-field hits |
|---|---:|---:|---:|---:|---:|
| fixture-001 | 33 | 33 | 0 | 32 | 5/5 |
| fixture-002 | 67 | 67 | 0 | 85 | 5/5 |
| fixture-003 | 66 | 66 | 0 | 95 | 4/4 |

## Hardenings landed (Option B + T1)

| Item | Status |
|---|---|
| HTML/fence sanitize + low confidence | Done |
| Page tiling (low-conf / truncated VL pages only) | Done; skip when line boxes + conf≥0.5 |
| RapidOCR / Paddle / Hybrid adapters | Done |
| T1 redacted cloud escalate (`ocr_privacy`) | Done; default egress **off** |
| OCR → multi-line blocks + PDF-point bbox | Done |
| Prometheus `bidproof_ocr_pages_total` | Done |
| Domain rules (器械/授权/三甲) | Done |

## Error taxonomy

| Layer | Finding | Severity |
|---|---|---|
| OCR | Dense TOC → truncation under VL | **P0 residual for cloud CER** |
| Layout | Was one OCR page block | **Mitigated** via `ocr_line` blocks |
| Observability | No OCR page counter | **Mitigated** |
| Tables / seals | No structure / GT | High |
| Field IE | Regex `rules.py` only | High for IE F1 claims |

## Candidates

| Option | Status |
|---|---|
| A. Keep Qwen + PyMuPDF | Insufficient alone for CER gate |
| **B. Hybrid harden (active)** | In progress; engineering gates green |
| C. Private PP-Structure replace | Deferred until labeled bake-off |

## Reproduce

```powershell
uv run python -m work.eval.ocr_benchmark --skip-live
uv run python -m work.eval.ocr_benchmark --live-pages 2   # only if egress allowed + key set
uv run --group dev pytest -q tests/test_ocr.py tests/test_ocr_privacy_t1.py
```

Raw: `outputs/ocr-benchmark/raw-results.json`
