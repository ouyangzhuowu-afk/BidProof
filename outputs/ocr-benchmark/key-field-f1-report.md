# Key-field F1 engineering report (sandbox)

- Claim scope: **engineering gate only**. This is **not** a product PASS and **not** a T-005 / business / enterprise acceptance.
- Key-field F1 gate (S-A-03): **≥ 97.00%** (`0.97`)
- Observed micro `key_field_f1`: **76.00%** → **GATE_FAIL**
- TP / FP / FN: **57 / 15 / 21**
- Matching: exact NFKC-normalized value equality on frozen `(doc_id, name)` keys.
- Hard OR with line CER / TEDS still forces product `NEEDS_REVIEW` while any gate fails or stays unevaluated.

| Metric | Value | Role |
|---|---|---|
| `precision` | 79.17% | diagnostic |
| `recall` | 73.08% | diagnostic |
| `key_field_f1` | 76.00% | gate metric |
| `key_field_f1_min` | 0.97 (≥ 97%) | S-A-03 threshold |
| `gate` | GATE_FAIL | engineering only |
| `product_pass` | false | never claimed |
| `business_pass` | false | never claimed |
| `forced_requirement_status` | NEEDS_REVIEW | product path |

## Reproduce

```bash
uv run python -m work.eval.key_field_gt
uv run python -m work.eval.key_field_f1
```

Writes only under `--out-dir` (default `outputs/ocr-benchmark/`). Refuses `pilot-ledger` / `icp-outreach` paths.

- Generated at: `2026-09-18T14:13:17.137714+00:00`
- Annotations: `work/eval/fixtures/key_field_gt.jsonl`
- Hypotheses: `work/eval/fixtures/key_field_hypotheses.jsonl`
