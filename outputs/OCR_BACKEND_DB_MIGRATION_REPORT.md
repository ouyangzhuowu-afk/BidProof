# OCR / Backend / DB Migration Report

- Branch: `assessment/ocr-backend-db`
- Date: 2026-09-16 (refresh)
- Frontend: **unchanged** (Opus5 design preserved)

## 1. Eval results & OCR verdict

See `outputs/OCR_TECH_ASSESSMENT.md`.

| Claim | Verdict |
|---|---|
| Electronic text / DOCX extraction for bidding fields | **达标** (public fixtures 14/14; hospital redacted DOCX → 105 reqs) |
| Cloud OCR character accuracy (Qwen live sample) | **不达标** (mean CER 23.77%; TOC) |
| Local RapidOCR / T1 escalate accuracy vs labeled scans | **Not yet measured** (engineering path ready; egress default off) |
| Full product “OCR 精准度全面达标” | **不可宣称** until ≥50 labeled docs + TEDS/seals |

## 2. Backend & DB

| Layer | Verdict | Detail |
|---|---|---|
| Backend | **Optimize, do not rewrite** | P0/P1 OCR reliability items largely done; IE/tables remain |
| Database | **Keep schema; no greenfield** | `claim_next` OK; defer `run_pages` until volume evidence |

Docs: `BACKEND_ASSESSMENT.md`, `DATABASE_ASSESSMENT.md`.

## 3. Changes in this batch

| File | Change |
|---|---|
| `app/extraction.py` | Multi-line OCR blocks + PDF-point bbox; tiling skip when lines+conf≥0.5; T1 escalate hook |
| `app/observability.py` | `record_ocr_page` + `bidproof_ocr_pages_total` |
| `tests/test_ocr.py` | Localized OCR blocks + metrics assertion |
| Prior on branch | sanitize, Rapid/Paddle/Hybrid, T1 privacy, domain rules, tiling, egress gate |

## 4. Verification

```text
uv run --group dev pytest -q tests/test_ocr.py tests/test_ocr_privacy_t1.py tests/test_extraction.py
# 24 passed, 1 skipped (plus claim/metrics subset green)

uv run python -m work.eval.ocr_benchmark --skip-live
# electronic_text field_accuracy=1.0

# Hospital redacted DOCX (local, no egress):
# pages=990, chars=29640, reqs=105
```

## 5. Residual risk

- Cloud CER gate still fails on dense TOC without live re-measure after tiling.
- No TEDS / seal / handwriting metrics.
- Hospital sample is born-digital DOCX — does not prove scan OCR.
- `run_pages` migration not started (correctly deferred).

## 6. Rollback

- Revert commits on `app/ocr.py`, `app/ocr_privacy.py`, `app/extraction.py`, `app/observability.py`, `app/rules.py`, tests.
- Assessment markdown / `work/eval` additive.
- No DB migration applied.

## 7. Next steps (evidence-gated)

1. Collect 10–20 **redacted scanned** hospital PDFs; run local RapidOCR CER bake-off.
2. If customer allows egress: enable T1 redacted escalate on hard pages only; re-measure CER.
3. Only after volume pain: design `run_pages` Alembic migration.
4. Do **not** swap primary OCR vendor or rewrite FastAPI/DB without bake-off numbers.
