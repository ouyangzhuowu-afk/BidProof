# S-A-05 TEDS table-structure ground-truth seed

Engineering / sandbox labels only. This is **not a product PASS**, **not T-005**, and **does not evaluate TEDS**.

Canonical seed: `work/eval/fixtures/teds_gt.jsonl` (S-A-01 page JSONL)  
Validator / report: `work/eval/teds_gt.py`  
Rebuild from public PDFs: `work/eval/build_teds_gt.py`  
Counting hook (no TEDS score): `work.eval.teds_gt.has_teds_gt` used by `work/eval/rapidocr_line_cer.py`

## Rules

- Public rows must use a completed `work/public-eval/manifest.json` document (`source_url` + `sha256` matching the local PDF).
- Synthetic rows use `origin=synthetic` and `doc_id` prefix `synthetic-`. They are never counted as public documents.
- `table_html` must contain a `<table>` with at least one `<tr>` and two cells. `null` is not TEDS GT.
- Week-1 labels are **single-page complete tables** (`table_span=single_page`). Cross-page / `续表` tables are rejected.
- `text_gt` is the labeled table span. Non-empty cells must appear in `text_gt`. Phone numbers and national IDs are fail-closed.
- Missing GT is `INSUFFICIENT`, not a high TEDS score. This leaf never sets `product_pass` or computes TEDS.
- Never write `outputs/pilot-ledger.csv` or `outputs/icp-outreach.csv`.

## Seed minima

| Metric | Minimum |
|---|---:|
| TEDS GT pages (`table_html` with `<table>`) | 15 |
| public documents with at least one table page | 3 |

## Limitations

- Does not claim the TEDS ≥ 90% gate.
- Does not wire the S-A-06 similarity harness beyond the `has_teds_gt` count hook.
- Seal / handwriting (S-A-07) and key-field F1 (S-A-03) are out of scope.
- Empty template cells (报价/偏离表 blanks) are structural GT, not filled commercial bids.

## Reproduce

```bash
uv run python -m work.eval.build_teds_gt
uv run python -m work.eval.teds_gt
uv run python -m work.eval.page_annotation work/eval/fixtures/teds_gt.jsonl
uv run --group dev pytest -q tests/test_teds_gt.py tests/test_page_annotation.py tests/test_rapidocr_line_cer.py
```

Exit `0` = schema valid and seed minima met (`SUFFICIENT_SEED`).  
Exit `2` = schema valid but coverage `INSUFFICIENT`.  
Exit `1` = validation / IO error.

`SUFFICIENT_SEED` is not TEDS ≥ 90% and is not a product/business PASS.
