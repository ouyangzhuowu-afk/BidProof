# S-A-03 key-field F1 harness

Engineering / sandbox only. **Not** a product PASS, **not** T-005.

Canonical GT: `work/eval/fixtures/key_field_gt.jsonl` (S-A-04)  
Hypotheses: `work/eval/fixtures/key_field_hypotheses.jsonl`  
Harness: `work/eval/key_field_f1.py`  
Frozen names: `work/eval/key_field_names.json`  
Gate: `KEY_FIELD_F1_MIN=0.97` in `work/eval/sandbox_gates.py`  
Product wiring: `app/quality_gates.py` reads `outputs/ocr-benchmark/key-field-f1-report.json`

## Rules

- Micro-averaged F1 over `(doc_id, name)` with NFKC-normalized value equality.
- Unknown field names are ignored (fail-closed enum remains on the GT seed validator).
- `GATE_PASS` is engineering only; harness always sets `product_pass=false`.
- While CER/F1/TEDS fail or stay unevaluated, product snapshot forces `NEEDS_REVIEW`.
- Never write pilot/ICP ledgers.

## Reproduce

```bash
uv run python -m work.eval.key_field_gt
uv run python -m work.eval.key_field_f1
uv run --group dev pytest -q tests/test_key_field_f1.py
```

Exit `0` = `GATE_PASS` (engineering only).  
Exit `2` = `GATE_FAIL`.  
Exit `1` = validation / IO error.

Committed sandbox hypotheses are **intentionally** below 97% F1 for an honest `GATE_FAIL`.
