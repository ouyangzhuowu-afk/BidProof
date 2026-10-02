# OCR provider compare (frozen public-expand cohort)

Engineering compare only. Not a product PASS, not T-005, not business acceptance.
TEDS uses PDF table ruling-line assist for cell placement; that is documented and is not a pure E2E OCR table score.

- Run status: **APPROVED_NOT_RUN**
- Cohort: `public-expand-54` · pages **54** · CER denom **29835**
- Scorer: `line-cer-v1+toc-segment` · mainline baseline `a99014f3f265`
- Cloud HTTP sends: **0**
- Documented approval id (set as env to send): `T1-JOE-CLOUD-COMPARE-2026-10-02`

## Side-by-side

| Provider | CER | CER gate | F1 | F1 gate | TEDS | TEDS gate | sends |
|---|---:|---|---:|---|---:|---|---:|
| Local RapidOCR (committed) | 4.96% | GATE_FAIL | 97.17% | GATE_PASS | 95.80% | GATE_PASS | 0 |
| Cloud Qwen-VL-OCR | n/a | NOT_RUN | n/a | NOT_RUN | n/a | NOT_RUN | 0 |

Gate claim: **NOT_CLAIMED**. `product_pass=false`.

## Env vars Joe must set (Render / local) for a live send

- `BIDPROOF_OCR_EGRESS_ALLOWED`
- `BIDPROOF_OCR_EGRESS_MODE`
- `BIDPROOF_OCR_EGRESS_APPROVAL`
- `QWEN_OCR_API_KEY`
- `BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT (optional)`
- `BIDPROOF_OCR_EGRESS_DOC_SHA256 (optional pin)`
- `BIDPROOF_OCR_EGRESS_ALLOWED_HOSTS (optional; defaults to DashScope/VPC OCR hosts)`
- `QWEN_OCR_ENDPOINT (optional)`

## Cloud skip / page failures

APPROVED_NOT_RUN: zero cloud HTTP sends. Set BIDPROOF_OCR_EGRESS_ALLOWED=1, BIDPROOF_OCR_EGRESS_MODE=redacted_only|vpc_private, BIDPROOF_OCR_EGRESS_APPROVAL=T1-JOE-CLOUD-COMPARE-2026-10-02 (or another T1-/T2- token), and QWEN_OCR_API_KEY before a live compare.

Page-level failure rows: **54** (pages remain in the CER denominator).

Generated at `2026-10-02T13:16:48.557611+00:00`.
