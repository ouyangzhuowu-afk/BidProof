# TEDS engineering report (sandbox)

- Claim scope: **engineering gate only**. This is **not** a product PASS and **not** a T-005 / business / enterprise acceptance.
- TEDS gate (S-A-06): **≥ 90.00%** (`0.9`)
- Observed mean `teds`: **87.85%** → **GATE_FAIL**
- Pages scored: **16** / GT pages with `<table>`: **16**
- Hard OR with line CER / key-field F1 still forces product `NEEDS_REVIEW` while any gate fails or stays unevaluated (see `sandbox_gates`).
- Data: public / synthetic sandbox table labels only

| Metric | Value | Role |
|---|---|---|
| `teds` | 87.85% | gate metric (micro-mean) |
| `teds_min` | 0.9 (≥ 90%) | S-A-06 threshold |
| `gate` | GATE_FAIL | engineering only |
| `product_pass` | false | never claimed by this harness |
| `business_pass` | false | never claimed by this harness |
| `forced_requirement_status` | NEEDS_REVIEW | product path while gates open |

## Pages

| doc_id | page | teds |
|---|---:|---:|
| fixture-001 | 14 | 100.00% |
| fixture-001 | 32 | 73.33% |
| fixture-002 | 33 | 87.30% |
| fixture-002 | 37 | 100.00% |
| fixture-003 | 29 | 100.00% |
| fixture-003 | 35 | 73.33% |
| pub-gx-nanning-vascular-doppler | 3 | 100.00% |
| pub-gx-nanning-vascular-doppler | 16 | 75.00% |
| pub-gx-nanning-vascular-doppler | 17 | 94.32% |
| pub-gx-ventilator-monitors | 15 | 100.00% |
| pub-gx-daxin-ultrasound-anesthesia | 51 | 74.14% |
| pub-gx-daxin-ultrasound-anesthesia | 73 | 81.58% |
| synthetic-teds-bid-opening | 1 | 100.00% |
| synthetic-teds-quote-detail | 1 | 64.71% |
| synthetic-teds-score | 1 | 81.82% |
| synthetic-teds-deviation | 1 | 100.00% |

## Reproduce

```bash
uv run python -m work.eval.teds_gt
uv run python -m work.eval.teds_harness
```

This command writes only under `--out-dir` (default `outputs/ocr-benchmark/`). It refuses paths containing `pilot-ledger` or `icp-outreach`.

- Generated at: `2026-09-18T09:37:10.338210+00:00`
- Annotations: `work/eval/fixtures/teds_gt.jsonl`
- Hypotheses: `work/eval/fixtures/teds_hypotheses.jsonl`
