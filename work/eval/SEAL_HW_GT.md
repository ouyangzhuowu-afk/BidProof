# S-A-07 seal / handwriting page-type slot GT

Engineering / sandbox labels only. **Not** a product PASS, **not** T-005, and **does not** score seal/handwriting detection.

Canonical seed: `work/eval/fixtures/seal_hw_gt.jsonl`  
Validator / report: `work/eval/seal_hw_gt.py`  
Schema slots: `page_type` ∈ {`seal`, `handwriting`} plus `has_seal` / `has_hw`

## Rules

- `page_type=seal` ⇒ `has_seal=true`
- `page_type=handwriting` ⇒ `has_hw=true`
- Public rows need manifest `source_url` + `sha256` matching the local PDF
- Synthetic rows use `origin=synthetic` and `doc_id` prefix `synthetic-`
- Missing GT is `INSUFFICIENT`. `detection_status` stays `NOT_EVALUATED` (no pixel GT yet)
- Never write pilot/ICP ledgers

## Seed minima

| Metric | Minimum |
|---|---:|
| Seal slots (`has_seal` or `page_type=seal`) | 6 |
| Handwriting slots (`has_hw` or `page_type=handwriting`) | 3 |
| `page_type=seal` | 3 |
| `page_type=handwriting` | 2 |
| Public documents | 3 |

## Reproduce

```bash
uv run python -m work.eval.seal_hw_gt
uv run python -m work.eval.page_annotation work/eval/fixtures/seal_hw_gt.jsonl
uv run --group dev pytest -q tests/test_seal_hw_gt.py tests/test_page_annotation.py
```

Exit `0` = `SUFFICIENT_SEED`. Exit `2` = `INSUFFICIENT`. Exit `1` = validation/IO error.
