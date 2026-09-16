"""Launch (or dry-run) PaddleOCR recognition fine-tune on the tender corpus.

Prefers an existing PaddleOCR checkout. On this Windows host, full GPU training
is usually done in WSL; this script validates the dataset and prints the exact
command so training can start without guesswork.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "work" / "training-corpus" / "paddle-rec"
META = DATA / "meta.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--run", action="store_true", help="Actually invoke tools/train.py if available")
    parser.add_argument("--paddleocr-root", type=Path, default=None)
    args = parser.parse_args()
    dry = not args.run

    if not META.exists():
        raise SystemExit("Dataset missing. Run: uv run python -m work.eval.prepare_paddle_rec_data")

    meta = json.loads(META.read_text(encoding="utf-8"))
    train_txt = DATA / "rec_gt_train.txt"
    val_txt = DATA / "rec_gt_val.txt"
    print(
        json.dumps(
            {
                "train_samples": meta.get("train_samples"),
                "val_samples": meta.get("val_samples"),
                "train_list": train_txt.as_posix(),
                "val_list": val_txt.as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    paddle_root = args.paddleocr_root
    if paddle_root is None:
        env_root = os.environ.get("PADDLEOCR_ROOT", "").strip()
        paddle_root = Path(env_root) if env_root else None
    if paddle_root is None or not paddle_root.exists():
        # common local clones
        paddle_root = None
        for candidate in (ROOT / "third_party" / "PaddleOCR", Path.home() / "PaddleOCR"):
            if (candidate / "tools" / "train.py").exists():
                paddle_root = candidate
                break

    cmd = [
        sys.executable,
        "tools/train.py",
        "-c",
        "configs/rec/PP-OCRv4/ch_PP-OCRv4_rec.yml",
        "-o",
        f"Train.dataset.data_dir={DATA.as_posix()}",
        f"Train.dataset.label_file_list=['{train_txt.as_posix()}']",
        f"Eval.dataset.data_dir={DATA.as_posix()}",
        f"Eval.dataset.label_file_list=['{val_txt.as_posix()}']",
        "Global.epoch_num=20",
        "Global.save_model_dir=" + (ROOT / "work" / "models" / "ocr" / "paddle-rec-finetune").as_posix(),
    ]

    status = {
        "mode": "dry-run" if dry else "run",
        "paddleocr_root": str(paddle_root) if paddle_root else None,
        "paddle_importable": False,
        "command": cmd,
        "hint": "Clone https://github.com/PaddlePaddle/PaddleOCR and set PADDLEOCR_ROOT, prefer WSL+GPU.",
    }
    try:
        import paddle  # type: ignore

        status["paddle_importable"] = True
        status["paddle_version"] = getattr(paddle, "__version__", "?")
    except Exception as exc:  # noqa: BLE001
        status["paddle_error"] = str(exc)

    print(json.dumps({k: v for k, v in status.items() if k != "command"}, ensure_ascii=False, indent=2))
    print("TRAIN_CMD:")
    print(" ".join(cmd))

    if dry:
        print("Dry-run only. Re-run with --run after PaddleOCR is installed.")
        return

    if not paddle_root or not (paddle_root / "tools" / "train.py").exists():
        raise SystemExit("PaddleOCR checkout not found; set --paddleocr-root or PADDLEOCR_ROOT")
    if not status["paddle_importable"]:
        raise SystemExit("paddle not importable in this env; use WSL/GPU env for training")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(paddle_root) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.check_call(cmd, cwd=str(paddle_root), env=env)


if __name__ == "__main__":
    main()
