# 独立复核交接

当前 `T-002` 已进入 `in_progress`，但正式计量仍被人工输入阻塞。

## 已准备

- `outputs/independent-review-packet.json`：33 条完整候选，包含源文件、SHA-256、页码和 quote。
- `outputs/independent-review-packet.md`：逐条可读核对清单。
- `work/apply_independent_reviews.py`：完整提交校验、源哈希复验、冲突分流、原子输出；不会覆盖原始 ledger。

## 需要独立复核人完成

1. 重新打开每条 `source_path` 指向的 PDF。
2. 核对源 SHA-256、页码、quote、类别和严重性。
3. 在复核包副本中填写同一个真实 reviewer 名称、`CONFIRM` 或 `REJECT`，以及非空复核说明。
4. 保存为 `outputs/independent-review-submission.json`。
5. 运行：`uv run python -m work.apply_independent_reviews outputs/independent-review-submission.json`。

未完成上述步骤前，正式可计量样本必须保持为 `0`；不能用 Codex 自己生成的决定冒充独立复核。
