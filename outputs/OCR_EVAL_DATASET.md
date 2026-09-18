# OCR Evaluation Dataset

## Status

| Tier | Count | Path | Quality |
|---|---:|---|---|
| Public electronic PDFs | 12 | `work/public-eval/pdfs/` | Real published tenders; text layer present. S-A-09 added 9 hospital docs; 8 failed URLs recorded and not counted |
| Requirement quote GT | 15 rows (5×3) | `work/ground-truth/fixture-00*.md` | Draft; needs second reviewer |
| Key-field labels | **7 public docs / 78 unique `(doc, name)` + 1 synthetic page** | `work/eval/fixtures/key_field_gt.jsonl` | S-A-04 seed; frozen enum; F1 **not** evaluated; engineering only |
| Page JSONL schema + sandbox samples | 3 pages | `work/eval/fixtures/sandbox_pages.jsonl` | Synthetic/public; S-A-01 contract |
| Training line crops | 4316 train / 480 val | work/training-corpus/paddle-rec/ | Weak labels from PDF text dict |
| RapidOCR CER baseline | 18 pages x2 modes | outputs/ocr-benchmark/RAPIDOCR_CER_REPORT.md | Mean CER ~18% clean / ~17% synthetic - gate fail |
| Scanned OCR cache | 78 pages / 1 doc | `work/ocr/akss-water-it/` | **PII — internal only**; no char-level GT |
| Synthetic degraded / fax / handwriting / seals | Partial | `work/training-corpus/tender-public/synthetic-scans/` + JSONL flags | JPEG Q40 CER probes; seal/HW GT still gap |
| Table structure GT (TEDS) | **16 pages** (12 public + 4 synthetic) | `work/eval/fixtures/teds_gt.jsonl` | S-A-05 Week-1 single-page seed; TEDS score **not** evaluated |

Sandbox engineering only. This file does **not** record a product PASS, T-005 business PASS, or enterprise acceptance.

## Domain focus (2026-09-15)

First customer ICP: **医疗器械经销 → 医院招标**. Prefer hybrid local OCR; see
`outputs/CUSTOMER_MEDDEVICE_HOSPITAL.md`. Priority label targets for the next 50 docs:

- 医院设备/耗材招标、集采代理文件
- 扫描件授权委托书、注册证复印件、经营许可证
- 开标一览表 / 报价明细表（S-A-05 已有 Week-1 单页 GT；跨页表仍缺）

## Coverage matrix (target vs have)

| Doc difficulty | Have? | Notes |
|---|---|---|
| Electronic PDF | Yes | 12 public fixtures (3 prior IT + 9 S-A-09 hospital / med-device) |
| Scanned PDF | Partial | 1 AKSS cache; source PDF may be absent from `work/uploads` (gitignored) |
| Photo / fax / low-quality copy | No | |
| Multi-column / TOC | Yes (proxy) | Shaanxi TOC page exposes VL truncation |
| Tables (报价/偏离/评分) | Week-1 seed (16 pages) | S-A-05 `table_html` GT; TEDS ≥90% **not** measured |
| Seals / signatures / handwriting | No | Schema flags exist; no labeled pixels |
| Bid response / 技术标 / 商务标 pairs | No | Only tender side |

## Page-level JSONL schema (S-A-01)

Machine-readable schema: `work/eval/page_annotation.schema.json`.  
Fail-closed validator: `work/eval/page_annotation.py`.

One JSON object per line. Current version is `1.0`. Weak `0.1` labels (or a missing `schema_version`) stay compatible if they have `doc_id`, `page`, and `text_gt`; other fields default. Unknown versions are rejected.

```json
{"schema_version":"1.0","doc_id":"sandbox-public-001","page":1,"page_type":"body","text_gt":"…","fields":[{"name":"project_code","value":"…"}],"table_html":null,"has_seal":false,"has_hw":false}
```

| Field | v1.0 | Notes |
|---|---|---|
| `schema_version` | required | `1.0` current; `0.1` weak-compatible |
| `doc_id` | required | Non-empty string |
| `page` | required | Positive integer |
| `page_type` | required | `cover` \| `toc` \| `body` \| `table` \| `seal` |
| `text_gt` | required | Page ground-truth text |
| `fields` | required | List of `{name, value}` objects |
| `table_html` | required | HTML string or `null` (null ⇒ no TEDS GT) |
| `has_seal` | required | Boolean |
| `has_hw` | required | Boolean (handwriting) |

Illegal samples fail closed: bad JSON, wrong types, unknown `page_type`, non-positive `page`, duplicate `(doc_id, page)`, unsupported `schema_version`. The validator does not skip bad lines.

```bash
uv run python -m work.eval.page_annotation work/eval/fixtures/sandbox_pages.jsonl
```

Exit `0` if every sample is legal; exit `1` otherwise.

## Key-field GT seed (S-A-04)

Canonical labels: `work/eval/fixtures/key_field_gt.jsonl` (S-A-01 page JSONL).  
Frozen names: `work/eval/key_field_names.json` and `page_annotation.schema.json` `$defs.key_field_name`.  
Runbook: `work/eval/KEY_FIELD_GT.md`.

S-A-03 F1 **must** use this enum. Unknown names fail closed. Legacy aliases `bond` / `bond_required` / `bond_section` / `no_bond` are not part of F1 vocabulary. `table_title` remains allowed on page JSONL for TEDS pages, not as a key field.

Public rows are traceable to `work/public-eval/manifest.json` `source_url` + `sha256`. Synthetic rows use `origin=synthetic` and `doc_id` prefix `synthetic-`. Seed minima: **5 public documents** and **30 unique labeled key fields**. Below that the report is `INSUFFICIENT` (missing GT), never a fabricated F1.

```bash
uv run python -m work.eval.key_field_gt
uv run python -m work.eval.page_annotation work/eval/fixtures/key_field_gt.jsonl
```

Exit `0` = schema valid and seed minima met (`SUFFICIENT_SEED`). Exit `2` = `INSUFFICIENT`. Exit `1` = validation error.  
`SUFFICIENT_SEED` is **not** F1 ≥ 97% and **not** a product/business PASS. T-005 ledgers are not written.

## Key-field F1 harness (S-A-03)

`work/eval/key_field_f1.py` scores micro-averaged F1 on frozen `(doc_id, name)` with NFKC value match.

- Engineering gate: **F1 ≥ 97%**. Sandbox hypotheses intentionally below → `GATE_FAIL` (observed ≈76%).
- Report: `outputs/ocr-benchmark/key-field-f1-report.md`. Product snapshot reads it via `app/quality_gates.py`.

```bash
uv run python -m work.eval.key_field_f1
```

## TEDS table-structure GT seed (S-A-05)

Canonical labels: `work/eval/fixtures/teds_gt.jsonl` (S-A-01 page JSONL).  
Runbook: `work/eval/TEDS_GT.md`.  
Report: `outputs/ocr-benchmark/teds-gt-report.md`.

Public rows are traceable to `work/public-eval/manifest.json` `source_url` + `sha256`. Synthetic rows use `origin=synthetic` and `doc_id` prefix `synthetic-`. Week-1 labels are **single-page complete tables** only. Seed minima: **15 TEDS GT pages** and **3 public documents**. Below that the report is `INSUFFICIENT` (missing GT), never a fabricated TEDS score.

```bash
uv run python -m work.eval.teds_gt
uv run python -m work.eval.page_annotation work/eval/fixtures/teds_gt.jsonl
```

Exit `0` = schema valid and seed minima met (`SUFFICIENT_SEED`). Exit `2` = `INSUFFICIENT`. Exit `1` = validation error.  
`SUFFICIENT_SEED` is **not** TEDS ≥ 90% and **not** a product/business PASS. T-005 ledgers are not written.

## TEDS harness (S-A-06)

`work/eval/teds_harness.py` scores HTML-table TEDS (tree edit similarity) against S-A-05 GT.

- Engineering gate: **mean TEDS ≥ 90%**. Sandbox hypotheses are intentionally below → `GATE_FAIL`.
- Hard OR with line CER / key-field F1: `work/eval/sandbox_gates.py`; product snapshot `app/quality_gates.py` forces `NEEDS_REVIEW` while gates fail or stay unevaluated.
- Always `product_pass=false` / `business_pass=false`. Spec: `outputs/sandbox-gate-productization-spec.md`.

```bash
uv run python -m work.eval.teds_harness
```

## Line-CER harness (S-A-02)

`work/eval/rapidocr_line_cer.py` compares annotation `text_gt` to hypothesis `text_hyp` / `lines_hyp`.

- `page_cer` and `line_cer` are computed separately and never mixed.
- Engineering gate: **line CER ≤ 2%**. If not met the report is `GATE_FAIL`.
- `GATE_PASS` is an engineering threshold only. The harness always sets `product_pass=false` and `business_pass=false`.
- Key-field F1 ≥ 97% is a later gate (S-A-03). TEDS ≥ 90% is evaluated by S-A-06.
- Writes only under `outputs/ocr-benchmark/` (or `--out-dir`). Refuses paths containing `pilot-ledger` or `icp-outreach`.

Prior RapidOCR soak baseline (not this sandbox fixture): page CER ≈ 18%, line CER ≈ 8.9%. TEDS GT seed (S-A-05) lives in `work/eval/fixtures/teds_gt.jsonl` (16 pages); the sandbox line-CER fixture still has `table_html=null`.

```bash
uv run python -m work.eval.rapidocr_line_cer
```

Optional paths:

```bash
uv run python -m work.eval.rapidocr_line_cer \
  --annotations work/eval/fixtures/sandbox_pages.jsonl \
  --hypotheses work/eval/fixtures/sandbox_hypotheses.jsonl \
  --out-dir outputs/ocr-benchmark
```

Exit `0` = `GATE_PASS` (engineering only). Exit `2` = `GATE_FAIL`. Exit `1` = validation/IO error.

The committed sandbox hypotheses are synthetic and **intentionally above 2% line CER** so Day-1 leaves a `GATE_FAIL` report rather than a fake pass.

## Desensitization rules

1. Public portal PDFs: OK as-is for engineering.
2. Customer/pilot PDFs: strip personal phones, ID numbers, bank accounts before labeling; store under ignored paths.
3. Never append OCR PII into `outputs/pilot-ledger.csv` / `outputs/icp-outreach.csv`.
4. JSONL annotations and line-CER reports in this campaign are sandbox-only (public / synthetic / redacted).

## How to extend to 50–100

1. Add public government tender URLs to `work/eval/public_tender_candidates.json` (hospital / medical-device preferred).
2. Rate-limited fetch; record SHA-256. Failed/dead URLs go to `fetch_failures` and do **not** count:

```bash
uv run python -m work.eval.collect_public_tenders --delay 2
uv run python -m work.eval.collect_public_tenders --check
```

See `work/public-eval/FETCH.md`.
3. Render 10% pages to images; create **synthetic scan** by downsample+JPEG Q40 for CER without customer data.
4. Add key-field pages to `work/eval/fixtures/key_field_gt.jsonl` using the frozen enum (`work/eval/KEY_FIELD_GT.md`). TEDS Week-1 seed is `work/eval/fixtures/teds_gt.jsonl` (16 single-page tables). Expand toward 50 pages later; cross-page tables stay out of scope until S-A-06.
5. Keep AKSS only for internal soak; replace with redacted clone before any share.
6. Keep new pages in the S-A-01 JSONL contract; bump `schema_version` only when adding required fields.

## Reproduce

```bash
uv run python -m work.eval.collect_public_tenders --check
uv run python -m work.eval.page_annotation work/eval/fixtures/sandbox_pages.jsonl
uv run python -m work.eval.page_annotation work/eval/fixtures/key_field_gt.jsonl
uv run python -m work.eval.page_annotation work/eval/fixtures/teds_gt.jsonl
uv run python -m work.eval.key_field_gt
uv run python -m work.eval.teds_gt
uv run python -m work.eval.rapidocr_line_cer
uv run python -m work.eval.ocr_benchmark --skip-live
```
