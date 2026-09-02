# Project-025 过夜执行目标

## 目标截止

2026-08-25 09:00（Asia/Shanghai）。

## 单一目标

完成一条可恢复、可审计的真实扫描闭环：

`真实招标 PDF + 企业证据 -> 页级抽取 -> 风险矩阵 -> 人工 HOLD 决策 -> 任务恢复`

## 已启动基线

- 运行 ID：`934c0cc93ea847ad9180421367bcecb0`
- 输入：真实上传招标文件 `招标文件正文.pdf` 与企业证据 `company.txt`
- 初始结果：76 条要求、4 条资格/废标阻塞项、62 条未解决项
- 人工决策：`HOLD`
- 恢复验证：已返回 `200`，决策仍为 `HOLD`

## 明早验收门槛

1. OCR 扫描文件页级结果保持 78/78 `EXTRACTED`。
2. 上述运行可从 SQLite 恢复，要求项和 `HOLD` 决策不丢失。
3. 至少抽查 5 条资格/废标/日期要求，全部有招标页码和原文 quote。
4. 企业证据不足的条目保持 `UNKNOWN` 或 `NEEDS_REVIEW`。
5. 任意 `PASS` 同时具备招标页码与企业证据页码。
6. `uv run --group dev pytest -q` 全量通过。
7. `uv run python -m app.workflow check` 返回 `PASS`。

## 今晚执行顺序

- 核验运行 `934c0cc93ea847ad9180421367bcecb0` 的恢复结果和引用完整性。
- 对 OCR 页级结果与 API 扫描结果做一致性检查。
- 修复发现的真实闭环问题，只改影响上述门槛的代码。
- 明早重新执行测试、workflow check 和运行恢复验收。

## 明确不做

今晚不扩展自动报价、自动标书生成、Bid/No-Bid 自动决策、多租户或生产部署；正式召回率仍需独立 Ground Truth 复核后再计算。

## 实际验收结果（2026-08-25）

- 状态：已完成本轮工程验收。
- OCR：78/78 页 `EXTRACTED`。
- SQLite 恢复：运行 `934c0cc93ea847ad9180421367bcecb0` 可恢复，76 条要求和 `HOLD` 决策保留。
- 引用门禁：抽查 5 条要求均有招标页码和 quote；0 条无双页码的 `PASS`。
- 未解决项：62 条保持 `UNKNOWN/NEEDS_REVIEW`。
- 测试：`30 passed`；workflow check 返回 `PASS`。
- 业务边界：正式 Ground Truth 可计量样本仍为 0，等待独立人工复核。
- 详细报告：`outputs/overnight-verification-2026-08-25.md`。
