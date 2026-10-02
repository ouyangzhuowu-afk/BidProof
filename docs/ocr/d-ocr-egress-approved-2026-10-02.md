# D-OCR-EGRESS-APPROVED-2026-10-02 — controlled cloud OCR compare

| Field | Value |
|------|--------|
| id | `D-OCR-EGRESS-APPROVED-2026-10-02` |
| date | 2026-10-02 |
| decided_by | Joe |
| scope | controlled 54-page cloud OCR compare under written T1/T2 egress policy |
| decision | Product owner approved cloud compare **purpose** (local vs cloud on the frozen public-expand cohort). This is **not** blanket egress enablement. |

## What this authorizes

- Engineering infrastructure to freeze the 54-page expanded public cohort (CER denom 29835 after TOC segmentation).
- Side-by-side local RapidOCR vs cloud provider compare using the same pages, fields, table subset, and scorer.
- Real HTTP sends **only** when runtime gates all pass: master switch + mode + written `T1-`/`T2-` approval token + API key + host allow-list (`app/egress_policy.py`).

## What this does **not** authorize

- Claiming OCR GATE_PASS, product PASS, or T-005 business unblock.
- Substituting draft PR #18/#19–#25 scores for mainline baseline `a99014f3f265`.
- Enabling egress in production by default.
- Writing pilot/ICP ledger rows.

## Documented approval token (env value; not a secret key)

Suggested runtime token once Joe sets Render/local env:

```text
BIDPROOF_OCR_EGRESS_APPROVAL=T1-JOE-CLOUD-COMPARE-2026-10-02
```

Also required for a live send:

- `BIDPROOF_OCR_EGRESS_ALLOWED=1`
- `BIDPROOF_OCR_EGRESS_MODE=redacted_only` (T1) or `vpc_private` (T2)
- `QWEN_OCR_API_KEY` (key material — never commit)
- Optional: `BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT`, `BIDPROOF_OCR_EGRESS_DOC_SHA256`, `BIDPROOF_OCR_EGRESS_ALLOWED_HOSTS`, `QWEN_OCR_ENDPOINT`

Without the API key / switch, compare status is `APPROVED_NOT_RUN` with **zero** egress sends.

## TEDS口径

TEDS hypotheses place OCR text into the PDF ruling-line / table grid (PDF table lines assist). That is not a pure E2E OCR-only table tree score; any E2E-only path must be reported separately.

## Reproduce (no keys → APPROVED_NOT_RUN)

```bash
uv run python -m work.eval.cohort_manifest --write
uv run python -m work.eval.cohort_manifest --verify
uv run python -m work.eval.provider_compare --run
```
