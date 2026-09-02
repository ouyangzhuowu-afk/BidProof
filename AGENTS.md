# BidProof Agent 协作说明

本仓库**不需要**长期并行维护多个独立 Cursor Agent。当前阶段用 **1 个 Cloud/Local Agent + 仓库内三角色工作流** 即可。

## 何时需要「多 Agent」

| 场景 | 建议 |
|------|------|
| 日常改代码、跑测试、推 GitHub | **1 个 Agent** 足够 |
| T-005 等业务验收（缺真实企业输入） | **人工输入** + 1 个 Agent 记台账 |
| 大规模并行（CI 修复 + 前端 + 文档同时推进） | **短期开 2–3 个子任务**，完成后合并，不常驻 |

仓库内已有 **Planner → Executor → Reviewer** 控制面（见 `workflow/`），这是逻辑上的「多角色」，不必再拆成多个常驻 Bot。

## 每个 Agent 启动必读

1. `workflow/project-state.json` → `next_best_action`
2. `workflow/master-brief.md` → 目标与边界
3. `workflow/agent-operating-instructions.md` → 执行循环
4. `uv run python -m app.workflow check`

## 当前优先级（2026-09-02）

- **P1 / 进行中**：`T-005` 真实任务验收与 45 天 ICP 试运行
- **阻塞**：尚无首批真实企业任务（不可用 demo 冒充）
- **可做**：工程优化、CI、台账工具、文档；收到真实输入后追加 `pilot-row.json` / `icp-row.json`

## 标准命令

```bash
pip install -r requirements.txt   # 或 uv sync
uv run python -m app.workflow check
uv run --group dev pytest -q
uv run python -m work.pilot_ledger --render-review
uv run python -m work.icp_ledger --render-review
```

## 环境约定

- 测试：`BIDPROOF_ENV=test`，`BIDPROOF_ALLOW_TRUSTED_HEADERS=1`（见 `tests/conftest.py`）
- 真实 upload PDF 不在 Git 中；完整回归：`.\scripts\sync-real-upload-fixtures.ps1`
- 公网试点（仅 PC）：`.\scripts\start-pilot.ps1` → `https://bidproof.marketcase.net/app`
- 试用加入码（试点）：`BIDPROOF_TRIAL_JOIN_CODE=BidProof-Trial-2026`

## 子任务分工（临时并行时）

| 角色 | 职责 | 典型产出 |
|------|------|----------|
| **Planner** | 读 state，定本轮目标与验证方式 | 任务列表、不重复已 verified 项 |
| **Executor** | 改代码、跑测试、更新台账 | PR/commit、pytest 绿 |
| **Reviewer** | 挑战证据链、fail-closed、不冒充业务验收 | 验收说明、state 更新 |

## 禁止

- 把测试/demo 任务写入 `pilot-ledger.csv` 或 `icp-outreach.csv`
- 无页码引用判定 PASS
- 提交 `.env`、tunnel token、upload 大文件
- 未验证就宣称「生产就绪」或「企业已验收」

## 云端 / 平板 Cursor

克隆 `https://github.com/ouyangzhuowu-afk/BidProof`，开 **Cloud Agent**，首条消息示例：

```
读 AGENTS.md 和 workflow/project-state.json，执行 next_best_action 的 fallback（T-005 台账与工程优化），跑 pytest 后 push。
```
