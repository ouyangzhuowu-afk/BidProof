# 45 天 ICP 触达台账

## 当前状态

- 已记录触达：0 / 30
- 已有反馈或跟进：0 条
- 已关联真实 pilot 任务：0 条
- 触达进度：`NOT_STARTED`

## 使用边界

此台账只记录真实 ICP 触达与反馈，不将 demo、测试或内部演练计入 30 个 ICP 目标。
产生真实 pilot 任务后，在 `linked_pilot_task_id` 填写对应 `task_id`，并与 `outputs/pilot-ledger.csv` 对齐。

## 下一步

距离 45 天目标还差 30 个 ICP 触达记录。
追加一行 UTF-8 JSON：`uv run python -m work.icp_ledger --row-json work/icp-row.json`。
刷新本报告：`uv run python -m work.icp_ledger --render-review`。
