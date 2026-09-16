#!/usr/bin/env bash
set -eu
echo "PY=$(python3 -V 2>&1)"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true
echo "CORPUS=$(test -f /mnt/c/BidProof/work/training-corpus/paddle-rec/meta.json && echo ok || echo missing)"
python3 -c 'import importlib.util as u; print("paddle", bool(u.find_spec("paddle"))); print("paddleocr", bool(u.find_spec("paddleocr")))'
test -f /mnt/c/BidProof/third_party/PaddleOCR/tools/train.py && echo PADDLEOCR_CLONE=ok || echo PADDLEOCR_CLONE=missing
df -h /home | tail -1
