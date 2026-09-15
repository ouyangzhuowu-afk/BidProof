# Backend Assessment

- Branch: `assessment/ocr-backend-db`
- Refreshed: `2026-09-16`
- Scope: FastAPI app, job runner, security, observability — **no frontend changes**

## Summary

Backend is past “script MVP”: workspace tenancy, durable jobs, idempotency, audit hash chain, rate limits, optional OIDC/LDAP. OCR-at-scale risks remain **egress latency/cost**, **inline render CPU**, and **JSON blob growth on `runs`** — none require a framework rewrite.

## P0 — fix now / low risk

| ID | Issue | Action |
|---|---|---|
| B-P0-1 | OCR HTML/truncate not sanitized | **Done** |
| B-P0-2 | OCR caches with PII could be committed | **Done** |
| B-P0-3 | OCR confidence unused | **Done** |

## P1 — sprint status

| ID | Issue | Status |
|---|---|---|
| B-P1-1 | Long pages truncated by VL OCR | **Done** tiling; skip when local lines + conf≥0.5 |
| B-P1-2 | OCR path drops block/bbox | **Done** `_blocks_from_ocr_result` → `ocr_line` locators |
| B-P1-3 | No retry/backoff in Qwen adapter | **Done** |
| B-P1-4 | Inline vs worker extract CPU | Document-only; prod stays on worker |
| B-P1-5 | No per-page OCR metrics | **Done** `bidproof_ocr_pages_total{provider,egress}` |
| B-P1-6 | Rules engine keyword-only | Open — separate IE layer later |

## P2 — later

| ID | Issue | Notes |
|---|---|---|
| B-P2-1 | No object storage abstraction | Fine for on-prem MVP |
| B-P2-2 | No Redis/Celery | DB queue sufficient |
| B-P2-3 | OpenAPI freeze | Optional |
| B-P2-4 | DATA_REGION default | Confirm with CN compliance |

## Performance / concurrency

| Path | Bottleneck |
|---|---|
| Electronic PDF | PyMuPDF CPU; fine for &lt;100pp |
| Scanned + cloud OCR | ~2–6s/page; 78pp ≈ 3–8 min serial |
| Local RapidOCR | CPU ONNX; Windows Blackwell-safe path |
| Job claim | PG `SKIP LOCKED` — verified; SQLite uses conditional UPDATE |
| Persist | Large JSON updates on `runs` row |

## Security / compliance

- Cloud OCR only after T1 redaction when escalate allowed; default `BIDPROOF_OCR_EGRESS_ALLOWED=0`.
- Fail-closed: OCR failure → no auto PASS.
- Audit / CSRF / ACL preserved.

## Verdict

**Optimize, do not rewrite.** FastAPI + worker + PG remains correct. Remaining backend work is IE/table quality and volume-driven storage shape — not a new architecture.
