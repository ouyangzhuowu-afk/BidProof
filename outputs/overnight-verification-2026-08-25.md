# Project-025 过夜真实扫描闭环验收

## 输入与恢复

- 运行 ID：`934c0cc93ea847ad9180421367bcecb0`
- 招标文件：`招标文件正文.pdf`
- 企业证据：`company.txt`
- SQLite 恢复：通过 `work/data/bid_agent.sqlite3` 读取成功
- 运行状态：`AUDIT`
- 人工决策：`HOLD`
- 未解决要求：62 条

## 验收结果

| 门槛 | 结果 | 证据 |
|---|---|---|
| OCR 页级结果 78/78 | PASS | `work/ocr/akss-water-it/` 共 78 个结果，全部 `EXTRACTED` |
| 运行可从 SQLite 恢复 | PASS | 指定 run_id 存在，76 条要求和 `HOLD` 决策均可读取 |
| 抽查 5 条资格/废标/日期有页码和 quote | PASS | REQ-0001 至 REQ-0005 均有招标页码和非空原文 quote |
| 企业证据不足降级 | PASS | 62 条状态为 `UNKNOWN` 或 `NEEDS_REVIEW` |
| `PASS` 双页码引用 | PASS | 0 条 `PASS` 缺少招标页码或企业证据页码 |
| 全量测试 | PASS | `30 passed` |
| Workflow QA | PASS | `Project-025 workflow state is valid` |

## 边界

这次运行证明本地单用户闭环可以恢复和追踪，不证明召回率、漏报率或付款价值。Ground Truth 仍需独立审核人确认；当前正式可计量样本保持为 `0`。系统仍不自动作 Bid/No-Bid 决策。
