# S-A-04 key-field ground-truth seed

Engineering / sandbox labels only. This is **not a product PASS**, **not T-005**, and **does not evaluate key-field F1**.

Canonical seed: `work/eval/fixtures/key_field_gt.jsonl` (S-A-01 page JSONL)  
Frozen name enum: `work/eval/key_field_names.json`  
Schema hook: `work/eval/page_annotation.schema.json` `$defs.key_field_name`  
Document-level projection: `work/eval/key_fields.json` (derived; do not invent extra names here)

## Rules

- Public rows must use a completed `work/public-eval/manifest.json` document (`source_url` + `sha256` matching the local PDF).
- Synthetic rows use `origin=synthetic` and `doc_id` prefix `synthetic-`. They are never counted as public documents.
- Field `name` values must be in the frozen enum. Legacy aliases `bond` / `bond_required` / `bond_section` / `no_bond` are rejected.
- Page JSONL may still use non-key names such as `table_title` (S-A-01). Key-field GT / later S-A-03 F1 may not.
- `text_gt` is the labeled evidence span, not a full-page CER transcript. Phone numbers and national IDs are fail-closed.
- Missing GT is `INSUFFICIENT`, not a high F1. This leaf never sets `product_pass` or computes F1.
- Never write `outputs/pilot-ledger.csv` or `outputs/icp-outreach.csv`.

## Seed minima

| Metric | Minimum |
|---|---:|
| public documents with at least one key field | 5 |
| unique labeled key fields `(doc_id, name)` | 30 |

## Reproduce

```bash
uv run python -m work.eval.key_field_gt
uv run python -m work.eval.page_annotation work/eval/fixtures/key_field_gt.jsonl
uv run --group dev pytest -q tests/test_key_field_gt.py tests/test_page_annotation.py
```

Exit `0` = schema valid and seed minima met (`SUFFICIENT_SEED`).  
Exit `2` = schema valid but coverage `INSUFFICIENT`.  
Exit `1` = validation / IO error.

`SUFFICIENT_SEED` is not F1 ≥ 97% and is not a product/business PASS.
