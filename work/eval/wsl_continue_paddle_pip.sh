#!/usr/bin/env bash
# Continue setup using base Miniforge Python (skip conda create — needs outbound).
set -eu
ROOT=/mnt/c/BidProof
MF="$HOME/miniforge3"
PADDLE_DIR="$ROOT/third_party/PaddleOCR"
DATA="$ROOT/work/training-corpus/paddle-rec"
LOG="$ROOT/outputs/ocr-benchmark/wsl-train-setup.log"
PY="$MF/bin/python"
PIP="$MF/bin/pip"

echo "=== $(date -Iseconds) continue with base miniforge python ===" | tee -a "$LOG"
test -x "$PY"
"$PY" -V | tee -a "$LOG"

if ! "$PY" -c "import paddle" 2>/dev/null; then
  echo "Installing paddlepaddle CPU (tuna/paddle mirrors)..." | tee -a "$LOG"
  "$PIP" install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
    || "$PIP" install paddlepaddle==2.6.2 -i https://pypi.tuna.tsinghua.edu.cn/simple
fi
"$PIP" install "paddleocr==2.9.1" opencv-python-headless pyyaml tqdm scikit-image lmdb rapidfuzz \
  -i https://pypi.tuna.tsinghua.edu.cn/simple || true
"$PY" -c "import paddle; print('paddle', paddle.__version__, 'cuda?', paddle.is_compiled_with_cuda())" | tee -a "$LOG"

test -f "$PADDLE_DIR/tools/train.py"
echo "DATASET train=$(wc -l < "$DATA/rec_gt_train.txt") val=$(wc -l < "$DATA/rec_gt_val.txt")" | tee -a "$LOG"
echo "=== continue done ===" | tee -a "$LOG"
