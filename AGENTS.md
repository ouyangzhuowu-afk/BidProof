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

## 当前优先级（2026-09-23）

- **P1 / 进行中**：`sandbox-campaign-A` 沙箱工程门禁（S-A-01..07）。OCR 三项门禁现状：行级 CER `GATE_FAIL`（3.17% / 阈值 ≤ 2%）、关键字段 F1 `GATE_FAIL`（76.00% / 阈值 ≥ 97%）、TEDS `NOT_EVALUATED`；未达标时产品侧强制 `NEEDS_REVIEW`，不得当作通过。
- **阻塞**：`T-005` 真实任务验收与 45 天 ICP 试运行——沙箱阶段已推迟（2026-09-16 决策），尚无首批真实企业任务，不可用 demo 冒充。
- **待裁决**：2026-09-23 前端交接代码包（`outputs/handover-2026-09-23/`）**未合并**；它整页替换详情视图，与 C-022 回退决定冲突，先定合并方式再动代码。
- **可做**：工程优化、CI、台账工具、文档、性能；收到真实输入后追加 `pilot-row.json` / `icp-row.json`
- **已回退（C-022）**：工作台补丁 002 打乱扫描任务页对齐，已恢复 `4516b3f` 布局；相关材料已移入 `docs/archive/`，勿整页落地

## 标准命令

```bash
pip install -r requirements.txt   # 或 uv sync
uv run python -m app.workflow check
uv run python -m app.workflow next-action
uv run --group dev pytest -q
npm ci --prefix frontend && npm run build --prefix frontend   # 产物写入 static/，勿手改
uv run python -m work.pilot_ledger --render-review
uv run python -m work.icp_ledger --render-review
```

## 环境约定

- 测试：`BIDPROOF_ENV=test`，`BIDPROOF_ALLOW_TRUSTED_HEADERS=1`（见 `tests/conftest.py`）
- 真实 upload PDF 不在 Git 中；完整回归：`.\scripts\sync-real-upload-fixtures.ps1`
- 公网试点：Render 免费 Web Service（`render.yaml`）；本机备用 `.\scripts\start-pilot.ps1`（Tunnel HTTP/2）
- 试用加入码（试点）：`BIDPROOF_TRIAL_JOIN_CODE=BidProof-Trial-2026`
- 新增 gitignore 门禁（2026-09-23）：`work/uploads/*`、`work/backups/`、`work/restore-drill-*/uploads/`、`third_party/`、训练语料二进制、zip/tgz、覆盖率与日志均不入库
- 本地隔离区：`_cleanup-archive-2026-09-23/`（2026-09-23 清扫移出的过期文件，已被忽略，确认后可整体删除）

## 子任务分工（临时并行时）

| 角色 | 职责 | 典型产出 |
|------|------|----------|
| **Planner** | 读 state，定本轮目标与验证方式 | 任务列表、不重复已 verified 项 |
| **Executor** | 改代码、跑测试、更新台账 | PR/commit、pytest 绿 |
| **Reviewer** | 挑战证据链、fail-closed、不冒充业务验收 | 验收说明、state 更新 |

## 禁止

- 把测试/demo 任务写入 `pilot-ledger.csv` 或 `icp-outreach.csv`
- 提交 `work/restore-drill-*/uploads/` 等真实客户材料副本（历史中已发生过一次，勿再发生）
- 提交第三方克隆（`third_party/`）、训练语料二进制、交付 zip/tgz、覆盖率与日志
- 无页码引用判定 PASS
- 提交 `.env`、tunnel token、upload 大文件
- 未验证就宣称「生产就绪」或「企业已验收」

## 云端 / 平板 Cursor

克隆 `https://github.com/ouyangzhuowu-afk/BidProof`，开 **Cloud Agent**，首条消息示例：

```
读 AGENTS.md 和 workflow/project-state.json，执行 next_best_action 的 fallback（T-005 台账与工程优化），跑 pytest 后 push。
```
