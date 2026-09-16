# PaddleOCR recognition fine-tune dataset

- Train lines: **4316**
- Val lines: **480**
- Label format: `images/.../file.png\ttext` (SimpleDataSet)

## Recommended train command (after installing PaddleOCR)

```bash
# In a PaddleOCR checkout with pretrained rec weights:
python tools/train.py -c configs/rec/PP-OCRv4/ch_PP-OCRv4_rec.yml \
  -o Global.pretrained_model=./pretrain/ch_PP-OCRv4_rec_train \
     Train.dataset.data_dir=C:/BidProof/work/training-corpus/paddle-rec \
     Train.dataset.label_file_list=['C:/BidProof/work/training-corpus/paddle-rec/rec_gt_train.txt'] \
     Eval.dataset.data_dir=C:/BidProof/work/training-corpus/paddle-rec \
     Eval.dataset.label_file_list=['C:/BidProof/work/training-corpus/paddle-rec/rec_gt_val.txt']
```

Then convert with [PaddleOCRModelConverter](https://github.com/RapidAI/PaddleOCRModelConverter) and point BidProof `BID_OCR_MODEL_DIR` at the ONNX outputs.
