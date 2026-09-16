"""Prepare PaddleOCR recognition fine-tune data from public tender PDFs.

Method (industry path used by RapidOCR docs):
  1) Weak-label line crops from PDF text dict (born-digital)
  2) Fine-tune PP-OCR recognition in PaddleOCR
  3) Convert to ONNX via PaddleOCRModelConverter
  4) Point RapidOCR at the new ONNX models

This script only does step 1 (dataset build) so training can start immediately
without waiting on GPU provisioning.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "work" / "training-corpus" / "tender-public" / "manifest.json"
OUT = ROOT / "work" / "training-corpus" / "paddle-rec"


def _clean_label(text: str) -> str:
    text = re.sub(r"\s+", "", text or "")
    return text.strip()


def _docs() -> list[dict]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [d for d in data.get("documents", []) if d.get("ok") and d.get("path")]


def harvest_doc(row: dict, *, max_pages: int, max_lines: int, scale: float = 2.0) -> list[tuple[Path, str]]:
    path = ROOT / row["path"]
    doc = fitz.open(path)
    samples: list[tuple[Path, str]] = []
    img_dir = OUT / "images" / row["document_id"]
    img_dir.mkdir(parents=True, exist_ok=True)
    try:
        page_indices = list(range(min(doc.page_count, max_pages)))
        for page_index in page_indices:
            page = doc[page_index]
            blocks = page.get_text("dict").get("blocks", [])
            line_i = 0
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    text = _clean_label("".join(s.get("text", "") for s in spans))
                    if len(text) < 2 or len(text) > 40:
                        continue
                    if not re.search(r"[\u4e00-\u9fff0-9A-Za-z]", text):
                        continue
                    bbox = line.get("bbox")
                    if not bbox or len(bbox) != 4:
                        continue
                    x0, y0, x1, y1 = bbox
                    pad = 1.5
                    clip = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
                    if clip.width < 8 or clip.height < 6:
                        continue
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
                    line_i += 1
                    rel = Path("images") / row["document_id"] / f"p{page_index + 1:03d}_l{line_i:04d}.png"
                    abs_path = OUT / rel
                    abs_path.write_bytes(pix.tobytes("png"))
                    samples.append((rel, text))
                    if len(samples) >= max_lines:
                        return samples
    finally:
        doc.close()
    return samples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages-per-doc", type=int, default=8)
    parser.add_argument("--max-lines-per-doc", type=int, default=400)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(parents=True, exist_ok=True)

    all_samples: list[tuple[Path, str]] = []
    for row in _docs():
        all_samples.extend(
            harvest_doc(row, max_pages=args.max_pages_per_doc, max_lines=args.max_lines_per_doc)
        )

    random.Random(args.seed).shuffle(all_samples)
    cut = max(1, int(len(all_samples) * (1 - args.val_ratio))) if all_samples else 0
    train, val = all_samples[:cut], all_samples[cut:]

    def write_list(name: str, rows: list[tuple[Path, str]]) -> None:
        path = OUT / name
        path.write_text(
            "\n".join(f"{rel.as_posix()}\t{label}" for rel, label in rows) + ("\n" if rows else ""),
            encoding="utf-8",
        )

    write_list("rec_gt_train.txt", train)
    write_list("rec_gt_val.txt", val)

    meta = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "method": "paddleocr_simpledataset_from_pdf_text_dict",
        "references": [
            "https://rapidai.github.io/RapidOCRDocs/main/",
            "https://github.com/PaddlePaddle/PaddleOCR",
            "https://github.com/RapidAI/PaddleOCRModelConverter",
        ],
        "train_samples": len(train),
        "val_samples": len(val),
        "next_steps": [
            "Install paddleocr/paddlepaddle (uv sync --extra ocr-paddle or WSL GPU env)",
            "Fine-tune ch_PP-OCRv4_rec with SimpleDataSet pointing at this folder",
            "Export ONNX and configure RapidOCR model paths under work/models/ocr/",
        ],
        "out_dir": OUT.relative_to(ROOT).as_posix(),
    }
    (OUT / "DATASET.md").write_text(
        "# PaddleOCR recognition fine-tune dataset\n\n"
        f"- Train lines: **{len(train)}**\n"
        f"- Val lines: **{len(val)}**\n"
        "- Label format: `images/.../file.png\\ttext` (SimpleDataSet)\n\n"
        "## Recommended train command (after installing PaddleOCR)\n\n"
        "```bash\n"
        "# In a PaddleOCR checkout with pretrained rec weights:\n"
        "python tools/train.py -c configs/rec/PP-OCRv4/ch_PP-OCRv4_rec.yml \\\n"
        "  -o Global.pretrained_model=./pretrain/ch_PP-OCRv4_rec_train \\\n"
        f"     Train.dataset.data_dir={OUT.as_posix()} \\\n"
        f"     Train.dataset.label_file_list=['{ (OUT / 'rec_gt_train.txt').as_posix() }'] \\\n"
        f"     Eval.dataset.data_dir={OUT.as_posix()} \\\n"
        f"     Eval.dataset.label_file_list=['{ (OUT / 'rec_gt_val.txt').as_posix() }']\n"
        "```\n\n"
        "Then convert with [PaddleOCRModelConverter](https://github.com/RapidAI/PaddleOCRModelConverter) "
        "and point BidProof `BID_OCR_MODEL_DIR` at the ONNX outputs.\n",
        encoding="utf-8",
    )
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
