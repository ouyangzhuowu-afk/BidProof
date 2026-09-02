# Ground Truth 独立复核提交模板

## 使用边界

- 对象：`outputs/ground-truth-review-ledger.json` 中 `human_status=PENDING_INDEPENDENT_REVIEW` 的候选。
- 复核人必须不同于首轮审核人 `codex_first_pass`。
- 每条候选必须重新核对原始 PDF 的文件 SHA-256、页码和 quote；不能只看候选摘要。
- `CONFIRM` 仅表示该候选的类别、严重性和页码 quote 均成立；不表示企业满足该要求。
- `REJECT` 表示候选不是该类别的真实要求，必须填写原因。
- 首轮与独立复核意见冲突时，系统进入 `NEEDS_ADJUDICATION`，不计入正式指标。

## 提交格式

将每条决定写成 JSON 对象，组成一个数组：

```json
[
  {
    "review_id": "REAL-001-01",
    "reviewer": "reviewer_2",
    "decision": "CONFIRM",
    "note": "已在原始文件第 2 页核对，类别、页码和 quote 一致。"
  },
  {
    "review_id": "REAL-001-03",
    "reviewer": "reviewer_2",
    "decision": "REJECT",
    "note": "该段是评分业绩时间范围，不是投标截止日期。"
  }
]
```

允许的 `decision` 只有 `CONFIRM` 和 `REJECT`。`reviewer` 不能为空，且不能填写 `codex_first_pass`。每个 `review_id` 在一次提交中只能出现一次，`note` 必须非空。

## 计量门禁

只有同时满足以下条件的候选才可用于召回率或漏报率计算：

1. 原始文件存在且 SHA-256 一致；
2. 首轮状态为 `CONFIRMED`；
3. 独立复核状态为 `INDEPENDENTLY_CONFIRMED`；
4. 招标页码和原文 quote 可回归定位。

首轮驳回项、未复核项、冲突项和 OCR 失败页均不得计入正式 ground truth。当前正式可计量样本仍为 `0`。
