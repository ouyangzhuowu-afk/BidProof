#!/usr/bin/env bash
# Windows-friendly short fine-tune launcher (PowerShell will call via cmd).
# Prefer: run from repo root with .venv-ocr-train activated.
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv-ocr-train/Scripts/python.exe"
PADDLE="$ROOT/third_party/PaddleOCR"
DATA="$ROOT/work/training-corpus/paddle-rec"
OUT="$ROOT/work/models/ocr/paddle-rec-finetune"
PRE="$ROOT/work/models/ocr/ch_PP-OCRv4_rec_train"
CFG="$PADDLE/configs/rec/PP-OCRv4/PP-OCRv4_mobile_rec.yml"
LOG="$ROOT/outputs/ocr-benchmark/win-train.log"

mkdir -p "$OUT" "$(dirname "$LOG")"
export PYTHONPATH="$PADDLE${PYTHONPATH:+:$PYTHONPATH}"
export FLAGS_cudnn_exhaustive_search=0

PRE_ARG=""
if [ -f "$PRE/best_accuracy.pdparams" ]; then
  PRE_ARG="Global.pretrained_model=$PRE/best_accuracy"
elif [ -f "$PRE/student.pdparams" ]; then
  PRE_ARG="Global.pretrained_model=$PRE/student"
fi

cd "$PADDLE"
"$PY" tools/train.py -c "$CFG" \
  -o Global.use_gpu=False \
     Global.epoch_num=2 \
     Global.save_epoch_step=1 \
     Global.print_batch_step=20 \
     Global.eval_batch_step=500 \
     Global.save_model_dir="$OUT" \
     Global.character_dict_path="$PADDLE/ppocr/utils/ppocr_keys_v1.txt" \
     Global.distributed=False \
     Train.loader.batch_size_per_card=8 \
     Train.loader.num_workers=0 \
     Train.dataset.data_dir="$DATA" \
     "Train.dataset.label_file_list=['$DATA/rec_gt_train.txt']" \
     Eval.loader.batch_size_per_card=8 \
     Eval.loader.num_workers=0 \
     Eval.dataset.data_dir="$DATA" \
     "Eval.dataset.label_file_list=['$DATA/rec_gt_val.txt']" \
     $PRE_ARG \
  2>&1 | tee "$LOG"
