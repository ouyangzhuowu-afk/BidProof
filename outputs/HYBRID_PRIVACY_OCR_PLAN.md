# Hybrid Privacy OCR — use cloud quality without shipping raw hospital tenders

## Problem

- Local OCR (RapidOCR / Paddle) is good enough for many pages, but **dense TOC / complex tables / low-quality scans** still trail top cloud VL-OCR.
- Hospital / 医疗器械 packs contain **联系人、电话、地址、医院名、印章、证照复印件** — raw page images must not go to a public cloud endpoint by default.
- Goal: approach cloud accuracy **without** treating “cloud OCR” as “upload the whole PDF”.

## Verdict (recommended)

**Adopt “Local-first + Redacted Escalation + Optional Private Cloud”.**

Do **not** use unrestricted public DashScope/Qwen on original pages for this ICP.

```
┌──────────────┐
│ Upload PDF   │
└──────┬───────┘
       ▼
┌──────────────────────────┐
│ Electronic text layer?   │──yes──► PyMuPDF / OOXML (no OCR)
└──────┬───────────────────┘
       │ no / low text
       ▼
┌──────────────────────────┐
│ Local OCR (rapid/paddle) │ + tiling
└──────┬───────────────────┘
       ▼
┌──────────────────────────┐
│ Page risk classifier     │
│ seal / ID / license /    │
│ contact header?          │
└──────┬───────────────────┘
       │ high-sensitivity ──► keep local only + NEEDS_REVIEW
       │ low-confidence OR dense TOC/table
       ▼
┌──────────────────────────┐
│ Redaction gate           │  mask phones, names, addresses,
│ (image + optional text)  │  hospital/agency tokens, QR/barcodes
└──────┬───────────────────┘
       ▼
┌──────────────────────────┐
│ Cloud / private OCR      │  only redacted tiles
│ (CN region / VPC / DPA)  │
└──────┬───────────────────┘
       ▼
┌──────────────────────────┐
│ Merge + confidence vote  │  rehydrate placeholders locally
│ Audit: page hash, mode   │  never auto PASS
└──────────────────────────┘
```

## Three compliance tiers (ask customer which they mean by「不能出网」)

| Tier | Meaning | Allowed cloud? | Typical contract |
|---|---|---|---|
| **T0 Absolute air-gap** | No packet leaves the building | No | Local only (Rapid + WSL Paddle) |
| **T1 Controlled egress** | Redacted crops may leave; originals stay | Yes, **redacted_only** | DPA + allow-list domains + retention=0 |
| **T2 Private cloud** | Traffic only to customer’s VPC / 专有云 OCR | Yes, **vpc_private** | Aliyun 私有化 Docker / 离线 SDK / VPC Endpoint |

Many hospital-side statements of「不能出网」are really **T1 or T2**, not T0. Confirm in writing.

Aliyun public docs: public OCR claims **不落盘**; for strict regulation they also sell **私有化部署 / 离线 SDK**, and VPC inner endpoints (e.g. `ocr-vpc.cn-shanghai.aliyuncs.com`). That is still “cloud compute”, but not “random public SaaS with full tender PDF”.

## Why this is better than pure local or pure cloud

| Approach | Accuracy | Sensitivity risk | Ops |
|---|---|---|---|
| Pure local | Medium–high | Lowest | Simple |
| Pure public cloud on raw pages | Highest raw | **Unacceptable** for ICP | Simple but non-compliant |
| **Redacted escalation (recommended)** | Near-cloud on hard pages | Low if redaction is strong | Medium |
| Vendor private OCR appliance | Highest + compliant | Lowest among cloud options | Cost / sales cycle |

## Escalation policy (concrete)

Escalate to cloud **only if all** hold:

1. `BIDPROOF_OCR_EGRESS_MODE` ∈ `{redacted_only, vpc_private}` (not `never`).
2. Local OCR `confidence < 0.55` **or** hyp/ref length ratio suggests truncation **or** page_type ∈ `{toc, dense_table}`.
3. Page_type ∉ `{seal, id_card, license_scan, bank_receipt, handwritten_signature}`.
4. Redaction gate reports `residual_pii_scan == clean` on the payload that will be sent.
5. Customer allow-list DNS only (DashScope / OCR VPC endpoint); TLS; no retry body logging.

## Redaction gate (must be local)

Before any bytes leave:

1. **Text-layer PII map** (phones, 身份证, 医院/代理名, 地址) → placeholders `[医院A]`… (reuse cryostat redaction map pattern).
2. **Image scrub**: cover detected face-less but high-risk zones — header/footer contact bands, QR, barcode; optional seal bounding boxes stay local-only (do not send seal crops).
3. Prefer sending **vertical tiles of body text**, not cover pages.
4. Keep a local **token map** to rehydrate OCR text after return (cloud never sees real hospital name if scrubbed to placeholder glyphs burned into the image).

Important: cloud OCR on images needs **pixels scrubbed**, not only JSON text redaction.

## Cloud endpoint choices (ordered)

1. **Best compliance**: Aliyun OCR **私有化 Docker / 离线 SDK** on customer GPU box (still “cloud-grade models”, no egress of docs).
2. **Good**: Customer Alicloud account + **VPC Endpoint** + RAM/STS; BidProof worker runs in same VPC or via专线/VPN.
3. **Acceptable with DPA**: Public DashScope Qwen-VL-OCR **only on redacted tiles**, CN region, retention off, audit every call.
4. **Forbidden**: Multi-region foreign endpoints; logging full base64; training opt-in.

## BidProof config sketch (additive, no frontend break)

```text
BIDPROOF_OCR_EGRESS_MODE=never|redacted_only|vpc_private
BID_OCR_PROVIDER=hybrid
BID_OCR_PRIMARY=rapid          # or paddle in WSL
BID_OCR_FALLBACK=qwen          # only used after redaction gate
BIDPROOF_OCR_EGRESS_ALLOWED=1  # master switch; still gated by MODE
BID_OCR_ESCALATE_MIN_CONF=0.55
BID_OCR_CLOUD_ENDPOINT=...     # VPC or public allow-listed
```

Audit fields on each page (already compatible with page JSON):

- `ocr_provider`, `ocr_confidence`, `ocr_status`
- add: `ocr_egress=none|redacted_cloud|vpc`, `ocr_redaction_version`, `ocr_escalation_reason`

## Cost / latency (expected)

- Most hospital electronic PDFs: **0 cloud calls** (text layer).
- Scanned 80-page pack: local OCR all pages; escalate ~5–15% hard pages → cloud cost ≪ full-doc cloud.
- P95: local ~0.3–2s/page; escalated page +2–6s + redaction overhead.

## What not to do

- Do not “anonymize after upload”.
- Do not send cover pages with hospital letterhead “because the model is better”.
- Do not claim HIPAA/等保 compliance from redaction alone without legal review.
- Do not train on customer pages.

## Implementation status (2026-09-16)

Customer selected **T1**. Landed on branch `assessment/ocr-backend-db`:

| Piece | Location |
|---|---|
| Page risk + redaction gate | `app/ocr_privacy.py` |
| Local-first + escalate after scrub | `app/extraction.py` (`_maybe_escalate_cloud`) |
| Cloud adapter gated by mode | `app/ocr.py` (`get_cloud_ocr_adapter`) |
| Tests | `tests/test_ocr_privacy_t1.py` (28 passed with OCR suite) |
| Config | `.env.example` |

Default in `.env.example` keeps `BIDPROOF_OCR_EGRESS_ALLOWED=0` until the operator sets the key.


## Recommendation for the current medical-device customer

1. Ask them to pick **T0 / T1 / T2** in writing (one sentence).
2. If **T0**: stay Rapid/WSL-Paddle only (previous plan).
3. If **T1**: implement **redacted escalation** — this is the **accuracy/privacy optimum** for a laptop pilot.
4. If **T2**: sell/implement **私有化 OCR** as the long-term enterprise answer; BidProof stays orchestrator.

Until they upgrade from absolute「不出网」, default remains **T0**. The architecture above is ready when they allow controlled, redacted, China-region compute.
