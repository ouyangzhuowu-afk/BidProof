#!/usr/bin/env bash
set -eu
source "${HOME}/miniforge3/etc/profile.d/conda.sh"
ENV=bidproof-p2o
if ! conda env list | grep -q "^${ENV} "; then
  conda create -y -n "$ENV" python=3.11
fi
conda activate "$ENV"
python -V
python -m pip install -U pip
python -m pip install "paddle2onnx==2.0.2" "onnx==1.17.0" || python -m pip install paddle2onnx onnx==1.17.0
python -c "import paddle2onnx; print('paddle2onnx', getattr(paddle2onnx,'__version__','?'))"
INFER=/mnt/c/BidProof/work/models/ocr/paddle-rec-infer
OUT=/mnt/c/BidProof/work/models/ocr/paddle-rec-onnx
mkdir -p "$OUT"
python -m paddle2onnx.convert \
  --model_dir "$INFER" \
  --model_filename inference.json \
  --params_filename inference.pdiparams \
  --save_file "$OUT/rec.onnx" \
  --opset_version 14 \
  --enable_onnx_checker True \
  || paddle2onnx \
  --model_dir "$INFER" \
  --model_filename inference.json \
  --params_filename inference.pdiparams \
  --save_file "$OUT/rec.onnx" \
  --opset_version 14 \
  --enable_onnx_checker True
ls -lh "$OUT"