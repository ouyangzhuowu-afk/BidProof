# Rolling Roadmap

## M1 — 产品楔子与可恢复 MVP（当前）

目标：让 Agent 每次启动都能读取状态、判断缺口、执行一个有证据的下一行动，并让用户在扫描详情首屏看到致命风险、证据引用和人工决策闸门。

任务树：

- `T-001` 建立 Workflow Package（当前轮完成）
  - `T-001.1` Master Brief
  - `T-001.2` Project State
  - `T-001.3` Planner/Executor/Reviewer Prompt
  - `T-001.4` QA Gate 与状态检查器
- `T-002` 建立中文招标 PDF fixture 与 ground truth（当前待人工确认，真实材料已提供）
  - 资格条件、废标条款、否定表达
  - 证书有效期、签章、日期、金额
  - 表格/跨页/扫描 OCR
  - 每条 ground truth 固定页码、quote、类别、严重性

当前材料进度：

- `work/uploads/` 已盘点 18 个文件：6 份可检索信息化招标 PDF 建立 33 条类别候选，另有 78 页扫描 PDF 等待 OCR。
- 候选清单位于 `tests/fixtures/real-upload/ground-truth-candidates.json`，全部标记 `PENDING_MANUAL_CONFIRMATION`。
- 第一轮审核位于 `outputs/ground-truth-review.md`：31 条保留候选、2 条类别误报；最终仍需独立复核。
- 扫描 PDF 的 OCR 断点入口为 `work/ocr_batch.py`；未注入密钥时只生成 `batch-summary.json` 阻塞计划。

已完成的产品/API交付：

- 三视图前端：任务首页、扫描详情、人工决策。
- 结构化来源文档、页索引、要求项、证据资产、匹配、复核事件和决策记录。
- 历史任务、要求项筛选、证据索引、人工复核和决策 API；`PASS` 双页码门禁。

验收：`uv run --group dev pytest -q`；`uv run python -m app.workflow check`；状态文件中的任务依赖和下一行动一致。

## M2 — 证据契约与抽取质量

目标：把嵌套 JSON 中的要求项、证据项、引用和人工复核事件提升为可审计契约；引入 layout-aware 规则和 OCR adapter。

退出条件：真实 fixture 达到召回率 >= 97%、严重风险漏报率 <= 2%、页码定位率 100%，否则保持 `UNKNOWN/NEEDS_REVIEW`。

## M3 — 试运行与业务验证

目标：在不扩展长标书生成等功能的前提下完成 10 个真实任务，记录人工修正、耗时、失败原因和付款意愿。

退出条件：45 天内 30 个明确 ICP、10 个真实任务、2–3 个付费意愿；否则暂停功能扩展并重新定义 ICP 或切换 RFQ 赛道。

## M4 — 可选扩展

只有 M2 和 M3 达标后，才评估规则库扩展、检索增强或更多行业。生产部署、多租户和自动投标流程不属于当前自动进入项，必须另行决策。
