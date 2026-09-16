#!/usr/bin/env bash
# Install Miniforge from Windows-downloaded installer (WSL often cannot reach GitHub).
set -eu
ROOT=/mnt/c/BidProof
MF="$HOME/miniforge3"
ENV_DIR="$HOME/bidproof-ocr-conda"
PADDLE_DIR="$ROOT/third_party/PaddleOCR"
DATA="$ROOT/work/training-corpus/paddle-rec"
INSTALLER="$ROOT/work/tools/Miniforge3-Linux-x86_64.sh"
LOG="$ROOT/outputs/ocr-benchmark/wsl-train-setup.log"
mkdir -p "$ROOT/outputs/ocr-benchmark" "$HOME/bidproof-ocr-models"

echo "=== $(date -Iseconds) setup from local Miniforge ===" | tee -a "$LOG"
test -f "$INSTALLER"
test "$(wc -c < "$INSTALLER")" -gt 1000000

if [ ! -x "$MF/bin/conda" ]; then
  bash "$INSTALLER" -b -p "$MF"
fi
# shellcheck disable=SC1091
source "$MF/etc/profile.d/conda.sh"
if [ ! -d "$ENV_DIR" ]; then
  conda create -y -p "$ENV_DIR" python=3.11 pip
fi
conda activate "$ENV_DIR"
python -V | tee -a "$LOG"

if ! python -c "import paddle" 2>/dev/null; then
  echo "Installing paddlepaddle CPU from paddle mirror..." | tee -a "$LOG"
  pip install paddlepaddle==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
    || pip install paddlepaddle==2.6.2 -i https://pypi.tuna.tsinghua.edu.cn/simple
fi
pip install "paddleocr==2.9.1" opencv-python-headless pyyaml tqdm scikit-image lmdb rapidfuzz \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
python -c "import paddle; print('paddle', paddle.__version__, 'cuda?', paddle.is_compiled_with_cuda())" | tee -a "$LOG"

if [ ! -f "$PADDLE_DIR/tools/train.py" ]; then
  echo "PaddleOCR checkout missing at $PADDLE_DIR — clone on Windows first" | tee -a "$LOG"
  exit 2
fi

echo "DATASET train=$(wc -l < "$DATA/rec_gt_train.txt") val=$(wc -l < "$DATA/rec_gt_val.txt")" | tee -a "$LOG"
echo "=== setup done ===" | tee -a "$LOG"
