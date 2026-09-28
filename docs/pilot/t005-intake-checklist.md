# T-005 真实企业输入清单（给 Joe）

决策 `D-T005-UNBLOCK-2026-09-28` 已解除沙箱阶段对 T-005 的**流程门禁**。台账与 CLI 已就绪；**仍禁止**把 demo / 测试 / 内部演练写入 `outputs/pilot-ledger.csv` 或 `outputs/icp-outreach.csv`。

## 首批真实 pilot 任务（目标 10）

每条真实任务请至少提供：

| 字段 | 说明 |
|------|------|
| `enterprise_name` | 真实企业名称（可约定脱敏写法，但必须是真实客户） |
| `tender_filename` | 招标文件名或可追溯标识 |
| 招标 PDF + 企业证据 | 通过产品上传；**不要**把客户 PDF 提交进 Git |
| `input_scope` | 例如「资格与废标风险扫描」 |
| `output_run_id` | 产品内真实 run / task id |
| `requirement_count` / `unresolved_count` | 扫描结果计数 |
| `human_confirmation` | `pending` → 人工确认后改为 `confirmed` |
| `payment_signal` / `payment_note` | 仅在真实表达付费意愿时填写 |
| `evidence_boundary` | 必须标明「真实企业输入」 |

写入方式（收到真实输入后由 Agent 或 Joe 执行）：

```bash
cp work/pilot-row.template.json work/pilot-row.json
# 编辑 work/pilot-row.json —— 只填真实字段
uv run python -m work.pilot_ledger --row-json work/pilot-row.json
uv run python -m work.pilot_ledger --render-review
```

## 45 天 ICP 触达（目标 30）

每条真实触达请至少提供：`company_name`、`icp_segment`、`channel`、`contact_role`、`response_status`、`next_step`、`next_step_due`。产生 pilot 任务后再填 `linked_pilot_task_id`。

```bash
cp work/icp-row.template.json work/icp-row.json
# 编辑 work/icp-row.json
uv run python -m work.icp_ledger --row-json work/icp-row.json
uv run python -m work.icp_ledger --render-review
```

## 明确不计入

- 历史 demo 任务、自动化测试、公网公开招标 fixture、沙箱 OCR 评测页
- 无真实企业授权的材料
- 无页码证据的「验收通过」宣称

## 工程就绪自检（不写业务行）

```bash
uv run python -m work.pilot_readiness --json
```

`ready=true` 且 `pilot.rows=0` / `icp.rows=0` 表示脚手架可用、业务台账仍为空——这是诚实初始态，不是业务验收。
