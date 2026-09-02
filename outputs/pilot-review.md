# 真实任务验收台账

## 当前状态

- 当前记录：0 / 10 条真实任务
- 已有人工确认任务：0 条
- 已记录付款意愿信号：0 条
- 业务验收结论：`NOT_STARTED`

## 使用边界

此台账只接受真实企业输入、真实人工确认、失败原因和付款意愿记录。历史演示任务、自动化测试和工程验收不计入业务任务数，也不填充为付款意愿。

## 下一步

距离 10 个真实任务目标还差 10 条记录。
收到首个真实企业任务后，复制 `work/pilot-row.template.json` 并填写字段，运行：
`uv run python -m work.pilot_ledger --row-json work/pilot-row.json`
刷新本报告：`uv run python -m work.pilot_ledger --render-review`
