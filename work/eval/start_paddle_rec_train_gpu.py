"""Resume PaddleOCR rec fine-tune on GPU if available, else refuse CPU hog."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv-ocr-train" / "Scripts" / "python.exe"
PADDLE = ROOT / "third_party" / "PaddleOCR"
DATA = ROOT / "work" / "training-corpus" / "paddle-rec"
OUT = ROOT / "work" / "models" / "ocr" / "paddle-rec-finetune"
CKPT = OUT / "latest"
PRE = ROOT / "work" / "models" / "ocr" / "ch_PP-OCRv4_rec_train" / "student"
CFG = "configs/rec/PP-OCRv4/PP-OCRv4_mobile_rec.yml"
LOG = ROOT / "outputs" / "ocr-benchmark" / "win-train-gpu.log"


def main() -> None:
    os.environ["PYTHONPATH"] = str(PADDLE)
    os.environ["NO_ALBUMENTATIONS_UPDATE"] = "1"
    probe = subprocess.run(
        [str(PY), "-c", "import paddle; print(paddle.is_compiled_with_cuda()); print(paddle.device.cuda.device_count())"],
        capture_output=True,
        text=True,
        check=False,
    )
    print(probe.stdout)
    print(probe.stderr[-500:] if probe.stderr else "")
    lines = [ln.strip() for ln in probe.stdout.splitlines() if ln.strip()]
    use_gpu = len(lines) >= 2 and lines[0] == "True" and int(lines[1]) > 0
    if not use_gpu:
        raise SystemExit("GPU paddle unavailable — not restarting on CPU (keeps fans down). Fix GPU install first.")

    args = [
        str(PY),
        "tools/train.py",
        "-c",
        CFG,
        "-o",
        "Global.use_gpu=True",
        "Global.epoch_num=5",
        "Global.save_epoch_step=1",
        "Global.print_batch_step=5",
        "Global.eval_batch_step=50",
        f"Global.save_model_dir={OUT.as_posix()}",
        "Global.character_dict_path=" + (PADDLE / "ppocr/utils/ppocr_keys_v1.txt").as_posix(),
        "Global.distributed=False",
        "Train.loader.batch_size_per_card=32",
        "Train.loader.num_workers=2",
        f"Train.dataset.data_dir={DATA.as_posix()}",
        f"Train.dataset.label_file_list=['{(DATA / 'rec_gt_train.txt').as_posix()}']",
        "Eval.loader.batch_size_per_card=32",
        "Eval.loader.num_workers=0",
        f"Eval.dataset.data_dir={DATA.as_posix()}",
        f"Eval.dataset.label_file_list=['{(DATA / 'rec_gt_val.txt').as_posix()}']",
    ]
    if CKPT.with_suffix(".pdparams").exists() or (OUT / "latest.pdparams").exists():
        args.append(f"Global.checkpoints={(OUT / 'latest').as_posix()}")
    elif PRE.with_suffix(".pdparams").exists() or PRE.exists():
        args.append(f"Global.pretrained_model={PRE.as_posix()}")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    print("CMD:", " ".join(args))
    with LOG.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(args, cwd=str(PADDLE), stdout=fh, stderr=subprocess.STDOUT)
        print(f"started pid={proc.pid} log={LOG}")
        sys.exit(proc.wait())


if __name__ == "__main__":
    main()
