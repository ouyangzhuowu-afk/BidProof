# S-A-09 public tender fetch report

Engineering fixtures only. This is **not a product PASS** and is not T-005 / business acceptance.
Failed/dead URLs recorded in the manifest do **not** count as completed documents.
OCR/scan PASS gates were not relaxed (line CER remains ≤ 2%).

| Metric | Count |
|---|---:|
| newly added | 9 |
| newly failed | 8 |
| completed documents (corpus total) | 12 |
| failed URLs (corpus total, not counted) | 8 |

## Reproduce

```bash
uv run python -m work.eval.collect_public_tenders --delay 2
uv run python -m work.eval.collect_public_tenders --check
# Known fetch_failures are skipped unless you pass --retry-failures
```

See `work/public-eval/FETCH.md`.
