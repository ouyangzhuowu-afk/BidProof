# Public tender training corpus

Dedicated store for **public** Chinese procurement / tender PDFs used to:

1. Run local RapidOCR CER baselines
2. Build PaddleOCR recognition fine-tune datasets
3. Convert fine-tuned weights to ONNX for RapidOCR (RapidAI recommended path)

## Layout

| Path | Purpose |
|---|---|
| `tender-public/pdfs/` | Downloaded public tender PDFs |
| `tender-public/manifest.json` | SHA256 + source URLs |
| `tender-public/synthetic-scans/` | JPEG-degraded page renders for scan-like CER |
| `paddle-rec/` | SimpleDataSet line crops + `rec_gt_*.txt` |

## Collect

```powershell
uv run python -m work.eval.collect_public_tenders
```

## RapidOCR CER (local; T1 only if egress allowed)

```powershell
uv run --extra ocr python -m work.eval.rapidocr_cer --pages-per-doc 3 --synthetic --try-t1
```

## Start training data prep (PaddleOCR → RapidOCR path)

Canonical method from [RapidOCR docs](https://rapidai.github.io/RapidOCRDocs/main/) + [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR):

```powershell
uv run python -m work.eval.prepare_paddle_rec_data
# then fine-tune in a PaddleOCR env (prefer WSL/Linux GPU), export ONNX via
# https://github.com/RapidAI/PaddleOCRModelConverter
```

## License / safety

- Public government / portal mirrors only.
- Do not write `outputs/pilot-ledger.csv` or `outputs/icp-outreach.csv`.
- Default `BIDPROOF_OCR_EGRESS_ALLOWED=0` — no raw cloud OCR.
