# Line-CER engineering report (sandbox)

- Claim scope: **engineering gate only**. This is **not** a product PASS and **not** a T-005 / business / enterprise acceptance.
- Line CER gate (S-A-02): **≤ 2%** (`0.02`)
- Observed `line_cer`: **3.17%** → **GATE_FAIL**
- Observed `page_cer`: **46.03%** (diagnostic only; never mixed into the line-CER gate)
- TEDS GT pages: **0** (no TEDS claim this run)
- Later gates (not evaluated here): key-field F1 ≥ 97%; TEDS ≥ 90%
- Data: public / synthetic / redacted sandbox labels only

| Metric | Value | Role |
|---|---|---|
| `page_cer` | 46.03% | diagnostic, page-level |
| `line_cer` | 3.17% | gate metric |
| `line_cer_gate` | 0.02 (≤ 2%) | S-A-02 threshold |
| `gate` | GATE_FAIL | engineering only |
| `product_pass` | false | never claimed by this harness |
| `business_pass` | false | never claimed by this harness |
| `teds_gt_pages` | 0 | TEDS GT still 0 unless `<table>` labels exist |

## Pages

| doc_id | page | page_cer | line_cer |
|---|---:|---:|---:|
| sandbox-public-001 | 1 | 59.57% | 2.13% |
| sandbox-public-002 | 1 | 9.09% | 9.09% |
| sandbox-weak-001 | 1 | 0.00% | 0.00% |

## Reproduce

```bash
uv run python -m work.eval.page_annotation work/eval/fixtures/sandbox_pages.jsonl
uv run python -m work.eval.rapidocr_line_cer
```

This command writes only under `--out-dir` (default `outputs/ocr-benchmark/`). It refuses paths containing `pilot-ledger` or `icp-outreach`.

- Generated at: `2026-09-16T11:31:29.258551+00:00`
- Annotations: `work/eval/fixtures/sandbox_pages.jsonl`
- Hypotheses: `work/eval/fixtures/sandbox_hypotheses.jsonl`
