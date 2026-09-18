# S-A-06 TEDS harness

Engineering / sandbox only. **Not** a product PASS, **not** T-005.

Canonical GT: `work/eval/fixtures/teds_gt.jsonl` (S-A-05)  
Hypotheses: `work/eval/fixtures/teds_hypotheses.jsonl`  
Scorer: `work/eval/teds_score.py`  
Harness: `work/eval/teds_harness.py`  
Gate constants / hard OR: `work/eval/sandbox_gates.py` (`TEDS_MIN=0.9`)  
Product wiring: `app/quality_gates.py` + `outputs/sandbox-gate-productization-spec.md`

## Rules

- Mean TEDS across pages that have GT `table_html` must be **≥ 0.9** for `GATE_PASS`.
- Missing hypotheses score as empty trees (TEDS 0 against non-empty GT).
- `GATE_PASS` is engineering only; harness always sets `product_pass=false` / `business_pass=false`.
- While CER/F1/TEDS fail or stay unevaluated, product snapshot forces `NEEDS_REVIEW`.
- Never write `outputs/pilot-ledger.csv` or `outputs/icp-outreach.csv`.

## Reproduce

```bash
uv run python -m work.eval.teds_gt
uv run python -m work.eval.teds_harness
uv run --group dev pytest -q tests/test_teds_harness.py tests/test_teds_gt.py
```

Exit `0` = `GATE_PASS` (engineering only).  
Exit `2` = `GATE_FAIL`.  
Exit `1` = validation / IO error.

The committed sandbox hypotheses are **intentionally** below 90% mean TEDS so Day-1 leaves an honest `GATE_FAIL`.
