# S-A-07 seal / handwriting page-type slot GT seed report

Engineering / sandbox labels only. This is **not a product PASS**, **not T-005**,
and **does not evaluate seal/handwriting detection accuracy**. Missing GT is
`INSUFFICIENT`, not a high score. Pixel-level GT is still a gap.

- Generated_at: `2026-09-18T14:31:51Z`
- Coverage status: **SUFFICIENT_SEED**
- `product_pass`: `false`
- `detection_status`: `NOT_EVALUATED`
- Source: `work/eval/fixtures/seal_hw_gt.jsonl`

| Metric | Count | Minimum |
|---|---:|---:|
| Seal slots (`has_seal` or `page_type=seal`) | 10 | 6 |
| Handwriting slots (`has_hw` or `page_type=handwriting`) | 4 | 3 |
| `page_type=seal` | 7 | 3 |
| `page_type=handwriting` | 3 | 2 |
| Public documents | 4 | 3 |
| Synthetic documents | 6 | — |

## Reproduce

```bash
uv run python -m work.eval.seal_hw_gt
uv run python -m work.eval.page_annotation work/eval/fixtures/seal_hw_gt.jsonl
```

`SUFFICIENT_SEED` is not seal/handwriting detection ≥95%/≥90% and is not a product PASS.
