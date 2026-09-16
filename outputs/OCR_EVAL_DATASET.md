# OCR Evaluation Dataset

## Status

| Tier | Count | Path | Quality |
|---|---:|---|---|
| Public electronic PDFs | 3 | `work/public-eval/pdfs/` | Real published tenders; text layer present |
| Requirement quote GT | 15 rows (5×3) | `work/ground-truth/fixture-00*.md` | Draft; needs second reviewer |
| Key-field labels | 14 fields / 3 docs + 4 scan-cover | `work/eval/key_fields.json` | Minimal; engineering only |
| Page JSONL schema + sandbox samples | 3 pages | `work/eval/fixtures/sandbox_pages.jsonl` | Synthetic/public; S-A-01 contract |
| Scanned OCR cache | 78 pages / 1 doc | `work/ocr/akss-water-it/` | **PII — internal only**; no char-level GT |
| Synthetic degraded / fax / handwriting / seals | **0** (flags only) | `has_seal` / `has_hw` on JSONL | Gap |
| Table structure GT (TEDS) | **0** | `table_html` null in sandbox | Gap |

Sandbox engineering only. This file does **not** record a product PASS, T-005 business PASS, or enterprise acceptance.

## Domain focus (2026-09-15)

First customer ICP: **医疗器械经销 → 医院招标**. Prefer hybrid local OCR; see
`outputs/CUSTOMER_MEDDEVICE_HOSPITAL.md`. Priority label targets for the next 50 docs:

- 医院设备/耗材招标、集采代理文件
- 扫描件授权委托书、注册证复印件、经营许可证
- 开标一览表 / 报价明细表（仍无 TEDS GT）

## Coverage matrix (target vs have)

| Doc difficulty | Have? | Notes |
|---|---|---|
| Electronic PDF | Yes | 3 public fixtures, 33–67 pages |
| Scanned PDF | Partial | 1 AKSS cache; source PDF may be absent from `work/uploads` (gitignored) |
| Photo / fax / low-quality copy | No | |
| Multi-column / TOC | Yes (proxy) | Shaanxi TOC page exposes VL truncation |
| Tables (报价/偏离/评分) | No GT | Extraction has no table model; TEDS GT = 0 |
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

## Line-CER harness (S-A-02)

`work/eval/rapidocr_line_cer.py` compares annotation `text_gt` to hypothesis `text_hyp` / `lines_hyp`.

- `page_cer` and `line_cer` are computed separately and never mixed.
- Engineering gate: **line CER ≤ 2%**. If not met the report is `GATE_FAIL`.
- `GATE_PASS` is an engineering threshold only. The harness always sets `product_pass=false` and `business_pass=false`.
- TEDS / key-field F1 ≥ 97% are later gates; this command does not claim them.
- Writes only under `outputs/ocr-benchmark/` (or `--out-dir`). Refuses paths containing `pilot-ledger` or `icp-outreach`.

Prior RapidOCR soak baseline (not this sandbox fixture): page CER ≈ 18%, line CER ≈ 8.9%, TEDS GT = 0.

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

1. Add more **public** provincial portal PDFs (rate-limit friendly, record SHA256 in manifest).
2. Render 10% pages to images; create **synthetic scan** by downsample+JPEG Q40 for CER without customer data.
3. Manually label 200 key pages for fields + 50 table pages for TEDS (`table_html` with a `<table>`).
4. Keep AKSS only for internal soak; replace with redacted clone before any share.
5. Keep new pages in the S-A-01 JSONL contract; bump `schema_version` only when adding required fields.

## Reproduce

```bash
uv run python -m work.eval.page_annotation work/eval/fixtures/sandbox_pages.jsonl
uv run python -m work.eval.rapidocr_line_cer
uv run python -m work.eval.ocr_benchmark --skip-live
```
