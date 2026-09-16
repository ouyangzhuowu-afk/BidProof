# RapidOCR CER Report

- Generated_at: `2026-09-16T13:00:48.842127+08:00`
- Egress allowed: `False` (mode=never)
- Docs evaluated: 9
- T1 hard-page escalate: **blocked_policy** (no cloud re-measure until `BIDPROOF_OCR_EGRESS_ALLOWED=1`)

## Summary

| Mode | Pages | Mean CER | Median CER | P95 CER | Mean WER | Mean latency | Gate ≤2% |
|---|---:|---:|---:|---:|---:|---:|---|
| `rapidocr_clean_render` | 18 | 0.1819 | 0.0920 | 0.7262 | 0.4836 | 2676 ms | NO |
| `rapidocr_synthetic_scan` | 18 | 0.1697 | 0.1444 | 0.3173 | 0.5120 | 2171 ms | NO |

## Method notes

- Reference = native PDF text layer (electronic tenders).
- Hypothesis = RapidOCR ONNX on rendered page (and optional JPEG Q40 synthetic scan).
- T1 redacted cloud only runs when egress is explicitly allowed; otherwise hard pages stay local.

Raw: `outputs/ocr-benchmark/rapidocr-cer.json`

