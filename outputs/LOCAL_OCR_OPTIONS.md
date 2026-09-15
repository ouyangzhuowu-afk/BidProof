# Local OCR options (sensitive hospital tenders — no egress)

Generated: 2026-09-15  
Constraint: **customer documents must not leave the machine** (no cloud OCR).  
Models may be downloaded once on an internet-capable session, then used fully offline.

## This machine

| Item | Value |
|---|---|
| OS | Windows 11 24H2 |
| CPU | AMD Ryzen 7 H 260 (8C/16T) |
| RAM | **15.3 GB** (tight for large VLMs) |
| GPU | **NVIDIA GeForce RTX 5060 Laptop, 8 GB** (Blackwell / sm_120) |
| Driver / CUDA | 596.13 / CUDA 13.2 capable |
| Python (BidProof) | **3.13** |
| WSL2 | Ubuntu installed (currently Stopped) |
| Docker Desktop | Installed (daemon currently stopped) |
| Installed OCR pkgs | none yet |

## Candidate survey (GitHub / vendors / docs)

| Option | What it is | Chinese quality | Layout/tables | License | Local offline | Fit on this PC |
|---|---|---|---|---|---|---|
| **PaddleOCR 3 + PP-OCRv5/v6** ([PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [docs](https://www.paddleocr.ai/)) | Det+rec pipeline; optional PP-StructureV3 | **Top-tier for CN print/handwriting** (tech report: beats many VLMs on Chinese edit-distance) | StructureV3 for tables | Apache-2.0 | Yes after model cache | **GPU on native Windows is risky on RTX 5060** ([Paddle#79354](https://github.com/PaddlePaddle/Paddle/issues/79354): det returns 0 boxes). Prefer **WSL2/Linux** or CPU |
| **MinerU** ([opendatalab/MinerU](https://github.com/opendatalab/MinerU)) | Doc parsing (PDF/DOCX→MD/JSON), VLM+OCR dual engine; pipeline uses PP-OCR | OmniDocBench ~**86** (pipeline) / ~**95** (hybrid/VLM) | Strong (tables→HTML, reading order) | AGPL-3.0 ⚠️ | Yes | pipeline: 4GB+ VRAM / 16GB+ RAM OK; hybrid wants **8GB+ VRAM & ideally 32GB RAM**. Windows VLM needs **Python 3.10–3.12** (ray). AGPL may be problematic for commercial BidProof |
| **DeepSeek-OCR / OCR-2** ([deepseek-ai](https://github.com/deepseek-ai)) | Vision-language OCR → markdown | Very strong on complex layout | Good | MIT | Yes after weights | **8GB VRAM + 16GB RAM = tight**; better on 24GB+; slower ops risk |
| **RapidOCR** ([RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)) | ONNX Runtime wrapper around PP-OCR exports | Slightly below latest Paddle native; still strong CN | Text lines only (no full structure) | Apache-2.0 | Yes | **Best Windows-native reliability** on Blackwell; CPU or ORT-GPU/DirectML |
| **GOT-OCR2 / Qwen2.5-VL local** | General VLMs | Good but heavier | Layout-aware | Apache/other | Yes | VRAM/RAM usually exceed comfort on 8+16GB |
| **Tesseract** | Classical OCR | Weak on CN tenders | Poor | Apache-2.0 | Yes | **Not recommended** as primary |

Sources: PaddleOCR 3.0 technical report (arXiv 2507.05595), MinerU quick start hardware table, DeepSeek-OCR local guides, RapidOCR discussions, Paddle Blackwell Windows issues.

## Recommendation for BidProof + 医疗器械/医院 (this laptop)

### Tier A — ship now (Windows-native, safest)

**RapidOCR (ONNX) + BidProof `paddle`/`rapid` adapter path, models vendored offline.**

- Why: avoids RTX 5060 Windows Paddle **zero-detection** bug; Apache-2.0; small footprint; works with Python 3.13; no Docker required.
- Accuracy: high enough for scan pages after tiling; slightly behind latest native PP-OCRv5/v6.
- Cost: free; ~tens of MB models.
- Use: `BID_OCR_PROVIDER=rapid` (or keep `paddle` name mapping to Rapid when Paddle GPU broken).

### Tier B — highest quality on this hardware (recommended production)

**WSL2 Ubuntu + PaddleOCR 3 (PP-OCRv5 server) ± PP-StructureV3**, GPU via CUDA 12.9 Linux wheels.

- Why: best CN CER for 医院扫描件 / 注册证 / 授权书; fits 8GB VRAM; official guidance for Blackwell is **Linux/WSL**, not native Windows.
- Optional later: MinerU **pipeline** backend in same WSL env for TOC/tables (watch **AGPL** — keep as optional sidecar, not linked into BidProof core if product is proprietary).
- Do **not** enable MinerU hybrid-VLM as default on 16GB RAM.

### Tier C — deferred

| Stack | When to revisit |
|---|---|
| DeepSeek-OCR-2 | After ≥24GB VRAM or dedicated workstation |
| MinerU hybrid-engine | After +RAM and AGPL legal OK |
| Cloud Qwen | Never for this customer (egress forbidden) |

## Deployment pattern (air-gap)

1. On a networked machine (or temporarily allow net **only** for model pull): download PP-OCR / RapidOCR ONNX weights into `work/models/ocr/` (gitignored).
2. Copy model directory to customer laptop via USB.
3. Set `BID_OCR_PROVIDER=rapid` (Windows) or WSL Paddle; `BIDPROOF_OCR_EGRESS_ALLOWED=0`.
4. Electronic DOCX/PDF text layer still preferred when present (no OCR).

## Decision matrix (this PC)

| Goal | Pick |
|---|---|
| Works this week on Windows without fighting Blackwell | **RapidOCR ONNX** |
| Max CN accuracy for scan tenders | **WSL2 + PaddleOCR PP-OCRv5** |
| Tables / reading-order / Markdown dump | MinerU pipeline in WSL (**AGPL check first**) |
| VLM “wow” OCR | Wait for more VRAM |

## Next engineering steps (BidProof)

1. Add `RapidOCRAdapter` behind `BID_OCR_PROVIDER=rapid` (done in follow-up commit on this branch).
2. Keep `PaddleOCRAdapter` for WSL/Linux.
3. Document model vendoring path; never auto-download during customer document processing.
4. Smoke-test on redacted cryostat scans once a scan PDF is available (current sample is electronic DOCX — OCR not required).
