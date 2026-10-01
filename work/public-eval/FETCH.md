# Reproduce public-eval PDF fetch (S-A-09)

Engineering fixtures only. This is **not** a product PASS, **not** T-005, and **not** enterprise/PII intake.

Canonical registry: `work/public-eval/manifest.json`  
PDF store: `work/public-eval/pdfs/`  
Candidate catalog: `work/eval/public_tender_candidates.json`

`work/fixtures/public-eval/` was a legacy duplicate of the original three IT fixtures. Its three duplicated PDFs were removed on 2026-09-23 (the same files stay in the canonical `work/public-eval/pdfs/` store, plus the original `work/fixtures/*.pdf` registered copies); the manifest stays for provenance. New S-A-09 files live only in the canonical tree so we do not double-commit binaries.

## Rules

- Public government tender PDFs only (hospital / medical-device preferred).
- Every **completed** document row must have `source_url` + `sha256` matching the local file.
- Failed or dead URLs are written to `fetch_failures[]` with `counts_as_completed: false`. They do **not** increment completed-document counts.
- Rate limit: default 2 seconds between remote attempts.
- Never write `outputs/pilot-ledger.csv` or `outputs/icp-outreach.csv`.
- Do not relax OCR/scan PASS gates (line CER remains ≤ 2%).

## This leaf (S-A-09)

| Metric | Count |
|---|---:|
| newly added completed PDFs | **9** |
| failed / dead URLs (recorded, not counted) | **8** |
| prior completed reused | 3 |
| corpus total completed | 12 |

All 9 new files are public Chinese hospital tenders from 广西政府采购云平台 (ultrasound, anesthesia, ventilators, monitors, flow cytometer, plus hospital IT systems). Henan SSL timeouts, UK Find a Tender 403, and CCGP 403/dead probes stayed in `fetch_failures` and are not completed docs.

## Fetch

```bash
uv run python -m work.eval.collect_public_tenders --delay 2
uv run python -m work.eval.collect_public_tenders --check
```

Optional:

```bash
uv run python -m work.eval.collect_public_tenders \
  --candidates work/eval/public_tender_candidates.json \
  --manifest work/public-eval/manifest.json \
  --pdfs-dir work/public-eval/pdfs \
  --report-dir outputs/ocr-benchmark \
  --delay 2 \
  --limit 0
```

Already-completed `source_url` / `file_url` values are skipped. Known `fetch_failures` are skipped unless `--retry-failures` is passed. Re-running is therefore idempotent for successful rows.

## Validate without downloading

```bash
uv run python -m work.eval.collect_public_tenders --check
uv run --group dev pytest -q tests/test_collect_public_tenders.py tests/test_page_annotation.py tests/test_rapidocr_line_cer.py
uv run python -m work.eval.page_annotation work/eval/fixtures/sandbox_pages.jsonl
uv run python -m work.eval.rapidocr_line_cer
```

The line-CER command is expected to remain `GATE_FAIL` on the sandbox hypotheses (intentional; not a product PASS).

Key-field GT seed (S-A-04) is separate: `uv run python -m work.eval.key_field_gt`. See `work/eval/KEY_FIELD_GT.md`. That command does **not** compute F1.

## S-A-OCR-PUBLIC-EXPAND (2026-09-29)

Additional public PDFs are appended to this same manifest with `leaf_id=S-A-OCR-PUBLIC-EXPAND`. They are eval samples only.

- Deduplicate against this manifest and against `work/training-corpus/tender-public/manifest.json`. A duplicate SHA is a fetch failure and is not counted.
- `source2-fujian` and anything under `outputs/case-studies/` or `work/training-corpus/` cannot become GT.
- Synthetic rows stay in the OCR report appendix and are excluded from the expanded gate.
- Ground truth is the PDF text layer, or a PyMuPDF table whose cells are confirmed in that text layer. Published HTML notices without an official PDF are stored redacted and marked not-scored. OCR output is never ground truth.
- Thresholds stay CER ≤ 2%, key-field F1 ≥ 97%, TEDS ≥ 90%.
- Line CER segments table-of-contents leaders before alignment. TEDS places RapidOCR text into the PDF ruling-line grid. Stored ground truth stays the text layer. Pages are not dropped.
- Printed-text recognition for this leaf is the PP-OCRv5 server model `ch_PP-OCRv5_rec_server`, loaded by RapidOCR. The line-finding detection model stays the package default.

```bash
uv run --extra ocr python -m work.eval.public_expand --build
uv run python -m work.eval.public_expand --report
```

The report is `outputs/ocr-benchmark/public-expand-report.md`. It repeats the published old-set numbers and the expanded live-OCR numbers. `product_pass` stays false. This leaf does not write pilot or ICP ledgers and does not change T-005.

Joe's 2026-09-29 local drop (`work/eval/fixtures/joe_local_pdfs_2026-09-29.json`, 12 PDFs) matches completed rows already in this manifest by filename and SHA-256. Those 12 stay duplicates: 0 newly added, 0 provenance-unverified. Provenance in the report is the existing `source_url` / `fetched_at` / `license_or_usage_note`.
