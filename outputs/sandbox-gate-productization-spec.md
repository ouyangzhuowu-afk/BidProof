# Sandbox gate productization (S-A-08 / S-A-06 wiring)

Engineering / sandbox only. This is **not** a product PASS and **not** T-005.

## Hard OR

| Gate | Threshold | Harness |
|---|---|---|
| Line CER | ≤ 2% | `uv run python -m work.eval.rapidocr_line_cer` |
| Key-field F1 | ≥ 97% | S-A-03 (pending) |
| TEDS | ≥ 90% | `uv run python -m work.eval.teds_harness` |

Any **evaluated** gate below threshold, or any gate still **unevaluated**, keeps the product path on `NEEDS_REVIEW`.

Shared aggregator: `work/eval/sandbox_gates.py`  
Product snapshot: `app/quality_gates.py` → attached to `scan_quality.ocr_engineering_gates`

## Invariants

- `product_pass` / `business_pass` remain `false` in harness reports.
- Demo / sandbox fixtures ≠ T-005 enterprise acceptance.
- Harnesses refuse writes to `pilot-ledger` / `icp-outreach` paths.
- Dual-page citation PASS gate is unchanged; OCR quality gates are additive fail-closed signals.

## Reproduce

```bash
uv run python -m work.eval.rapidocr_line_cer
uv run python -m work.eval.teds_harness
uv run --group dev pytest -q tests/test_teds_harness.py tests/test_sandbox_gates.py tests/test_quality_gates.py
```
