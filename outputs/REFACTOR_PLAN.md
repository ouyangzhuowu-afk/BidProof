# Refactor Plan (OCR / Backend / DB)

## Decision

**Recommend Option B — Hybrid harden (conservative + targeted OCR fixes).**  
Do **not** replace OCR vendor or migrate database schema in bulk until labeled bake-off completes.

| Option | Accuracy | Cost | Latency | Compliance | Effort | Risk | Rollback |
|---|---|---|---|---|---|---|---|
| **A. Conservative** — keep Qwen; fix sanitize/confidence/metrics; grow labels | Improves post-process; TOC still weak | Same API ¥ | Same | Egress remains | 1–2 wk | Low | Revert commits |
| **B. Hybrid (recommended)** — A + page tiling for dense pages + optional local PaddleOCR fallback when cloud disabled | Better scan coverage; offline degrade | Lower cloud if local catches simple pages | Local slower | Better for 不出网 | 3–6 wk | Medium | Feature-flag adapters |
| **C. Full replace** — PP-Structure / other private stack + `run_pages` table + IE rewrite | Unknown until bake-off | Capex GPU | Batch-friendly | Best private | 2–4 mo | High | Parallel adapter + shadow traffic |

## Phased delivery

### Phase 0 — done on this branch
- Assessment docs + benchmark harness
- P0: gitignore OCR caches; sanitize HTML OCR; low-confidence flag

### Phase 1 — in progress (medical-device / hospital ICP)

Customer: 医疗器械公司 → 医院招标（见 `outputs/CUSTOMER_MEDDEVICE_HOSPITAL.md`）。

1. Expand public+synthetic labeled set to ≥50 docs (`OCR_EVAL_DATASET.md`) — **next**: collect redacted **scanned** hospital packs (DOCX text path already smoke-tested).
2. `PaddleOCRAdapter` / `RapidOCRAdapter` + `hybrid` — **done**.
3. Page tiling for truncated / low-confidence pages — **done** (skip when line boxes + conf≥0.5).
4. Qwen retry/backoff — **done**.
5. Hybrid / T1 blocks raw egress unless allow-listed — **done** (`BIDPROOF_OCR_EGRESS_ALLOWED`, redacted escalate).
6. Domain rules: 器械证照 / 授权两票制 / 三甲业绩 — **done**.
7. OCR multi-block localization + Prometheus OCR page metrics — **done**.

### Phase 1.5 — accuracy gate (blocking “OCR 达标” claim)

- Local RapidOCR CER on labeled scans (target ≤2%).
- Optional T1 redacted-cloud CER on hard pages only.
- Do not claim full OCR达标 until gates pass + TEDS/seal evidence.
### Phase 2 — after bake-off numbers
- Choose keep Qwen / hybrid / private.
- Only then design `run_pages` migration with up/down.

### Phase 3 — IE & tables
- Table structure extraction + TEDS metric.
- Field schema IE separate from keyword `rules.py`.
- Business validators (金额大小写, dates).

## API compatibility

- Keep existing job/run JSON shapes.
- Additive fields only: `ocr_confidence`, `low_text_confidence` (already present).
- If breaking: version `/api/v2` or compatibility presenter — **do not force frontend rewrite**.

## Stop-the-line rules

- No PASS without page+quote evidence (unchanged).
- No cloud OCR if customer forbids egress.
- No pilot-ledger writes from eval.
