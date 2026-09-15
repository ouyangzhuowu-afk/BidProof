# OCR Evaluation Dataset

## Status

| Tier | Count | Path | Quality |
|---|---:|---|---|
| Public electronic PDFs | 3 | `work/public-eval/pdfs/` | Real published tenders; text layer present |
| Requirement quote GT | 15 rows (5×3) | `work/ground-truth/fixture-00*.md` | Draft; needs second reviewer |
| Key-field labels | 14 fields / 3 docs + 4 scan-cover | `work/eval/key_fields.json` | Minimal; engineering only |
| Scanned OCR cache | 78 pages / 1 doc | `work/ocr/akss-water-it/` | **PII — internal only**; no char-level GT |
| Synthetic degraded / fax / handwriting / seals | **0** | — | Gap |
| Table structure GT (TEDS) | **0** | — | Gap |

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
| Tables (报价/偏离/评分) | No GT | Extraction has no table model |
| Seals / signatures / handwriting | No | |
| Bid response / 技术标 / 商务标 pairs | No | Only tender side |

## Label schema (proposed next)

Per page JSONL (to build):

```json
{"doc_id":"…","page":1,"page_type":"cover|toc|body|table|seal","text_gt":"…","fields":[{"name":"project_code","value":"…"}],"table_html":null,"has_seal":false,"has_hw":false}
```

## Desensitization rules

1. Public portal PDFs: OK as-is for engineering.
2. Customer/pilot PDFs: strip personal phones, ID numbers, bank accounts before labeling; store under ignored paths.
3. Never append OCR PII into `outputs/pilot-ledger.csv` / `outputs/icp-outreach.csv`.

## How to extend to 50–100

1. Add more **public** provincial portal PDFs (rate-limit friendly, record SHA256 in manifest).
2. Render 10% pages to images; create **synthetic scan** by downsample+JPEG Q40 for CER without customer data.
3. Manually label 200 key pages for fields + 50 table pages for TEDS.
4. Keep AKSS only for internal soak; replace with redacted clone before any share.

## Reproduce current labels check

```powershell
uv run python -m work.eval.ocr_benchmark --skip-live
```
