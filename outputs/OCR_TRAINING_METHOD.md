# OCR Training Method (selected)

## Chosen path (GitHub / RapidAI canonical)

1. **Collect** public tender PDFs → `work/training-corpus/tender-public/`
2. **Weak-label** line crops from PDF text dict → `work/training-corpus/paddle-rec/`
3. **Fine-tune** Chinese recognition with [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) (`ch_PP-OCRv4_rec` / SimpleDataSet)
4. **Convert** to ONNX with [PaddleOCRModelConverter](https://github.com/RapidAI/PaddleOCRModelConverter)
5. **Deploy** via [RapidOCR](https://github.com/RapidAI/RapidOCR) in BidProof (`BID_OCR_PROVIDER=rapid`, `BID_OCR_MODEL_DIR=work/models/ocr`)

Why this path: RapidOCR docs explicitly recommend Paddle fine-tune → ONNX → RapidOCR deploy; stays Windows-safe at inference (ONNX Runtime) while training prefers Linux/WSL GPU.

## Status (2026-09-16)

| Step | Status |
|---|---|
| Public corpus collect | Done — 9 OK docs (3 fixtures + 6 downloads); 2 URL failures |
| RapidOCR page CER baseline | Done — clean mean CER **18.2%**, synthetic **17.0%** (gate ≤2% **NO**) |
| RapidOCR **line** CER (val crops) | Done — n=100, mean **8.9%**, median **0%**, exact **60%** (gate ≤2% **NO**) |
| Rec dataset build | Done — **4316 train / 480 val** lines (expanded) |
| Paddle fine-tune epochs | **Done on Windows GPU** (RTX 5060 / Paddle 3.3.0 cu129): PP-OCRv4_mobile_rec, 2 epochs; val **acc=0.911**, **norm_edit_dis=0.985**, fps≈134; artifacts `work/models/ocr/paddle-rec-finetune/{latest,iter_epoch_2,best_accuracy}` + infer `work/models/ocr/paddle-rec-infer/`; logs `win-train-gpu.log`, `paddle-rec-eval.log` |
| ONNX → RapidOCR redeploy | **Blocked** — Windows `paddle2onnx` DLL fails (known vs Paddle 3.3); WSL has no egress (conda/pypi timeout). Inference dir ready at `work/models/ocr/paddle-rec-infer/`. Paddle val proxy: **norm_edit_dis=0.985 ⇒ ~1.5% edit error** on weak-label val (not RapidOCR page CER; gate still open until ONNX deploy + held-out CER) |
| T1 redacted cloud re-measure | **Blocked** — `BIDPROOF_OCR_EGRESS_ALLOWED!=1` (correct) |

## Commands

```powershell
uv run python -m work.eval.collect_public_tenders
uv run --extra ocr python -m work.eval.rapidocr_cer --pages-per-doc 3 --synthetic --try-t1
uv run python -m work.eval.prepare_paddle_rec_data
uv run python -m work.eval.start_paddle_rec_train --dry-run
```

## Notes on CER

Page-level CER vs text-layer is a **harsh** proxy (reading order, headers, multi-column). Use it for regression; recognition fine-tune optimizes **line crops**, which is the RapidOCR/Paddle intended unit.
