# S-A-04 key-field GT seed report

Engineering / sandbox labels only. This is **not a product PASS**, **not T-005**,
and **does not evaluate key-field F1**. Missing GT is `INSUFFICIENT`, not a high score.

- Generated_at: `2026-09-16T15:23:40Z`
- Coverage status: **SUFFICIENT_SEED**
- `product_pass`: `false`
- `business_pass`: `false`
- `f1_status`: `NOT_EVALUATED` (gate F1≥97% remains unevaluated)

## Counts

| Metric | Count | Minimum |
|---|---:|---:|
| public documents with key-field GT | 7 | 5 |
| unique labeled key fields `(doc_id, name)` | 78 | 30 |
| labeled field instances | 78 | — |
| synthetic documents | 1 | — |

## Limitations

- Public rows must match `work/public-eval/manifest.json` `source_url` + `sha256`.
- Synthetic rows are labeled `origin=synthetic` and `doc_id` prefix `synthetic-`.
- S-A-03 F1 is **not** computed here; do not treat seed coverage as gate PASS.
- TEDS / seal / handwriting GT are out of scope for this leaf.
- No PII or enterprise pilot rows. T-005 ledgers were not written.

Insufficient reasons:

- `none`

Frozen enum names with zero labels in this seed:

- `device_registration`

## Documents

| doc_id | origin | fields | pages | sha256 |
|---|---|---|---:|---|
| `fixture-001` | public | 7 | 2 | `b90b22d14736…` |
| `fixture-002` | public | 9 | 3 | `a6c1f042b077…` |
| `fixture-003` | public | 9 | 4 | `e233f7b45ec3…` |
| `pub-gx-daxin-ultrasound-anesthesia` | public | 12 | 3 | `ee2a69cba1ae…` |
| `pub-gx-youjiang-ultrasound` | public | 11 | 4 | `c385256a47c8…` |
| `pub-gx-qintang-flow-cytometer` | public | 12 | 3 | `ff8495e75653…` |
| `pub-gx-ventilator-monitors` | public | 12 | 4 | `c52e7d6e84dd…` |
| `synthetic-keyfield-001` | synthetic | 6 | 1 | — |

## Reproduce

```bash
uv run python -m work.eval.key_field_gt
uv run python -m work.eval.page_annotation work/eval/fixtures/key_field_gt.jsonl
uv run --group dev pytest -q tests/test_key_field_gt.py tests/test_page_annotation.py
```

