# Reproduce public-eval PDF fetch (S-A-09)

Engineering fixtures only. This is **not** a product PASS, **not** T-005, and **not** enterprise/PII intake.

Canonical registry: `work/public-eval/manifest.json`  
PDF store: `work/public-eval/pdfs/`  
Candidate catalog: `work/eval/public_tender_candidates.json`

`work/fixtures/public-eval/` remains a legacy duplicate of the original three IT fixtures. New S-A-09 files live only in the canonical tree so we do not double-commit binaries.

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
