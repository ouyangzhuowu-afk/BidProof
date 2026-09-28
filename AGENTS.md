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

## 当前优先级（2026-09-28）

- **P1 / 进行中**：`T-005` 真实任务验收与 45 天 ICP 试运行——流程门禁已由 `D-T005-UNBLOCK-2026-09-28`（Joe）解除；脚手架就绪，台账仍为 0 行，等待首批**真实**企业输入。禁止用 demo/测试行冒充验收。摄入清单见 `docs/pilot/t005-intake-checklist.md`。
- **并行工程**：`sandbox-campaign-A` OCR 三项门禁仍为诚实失败态——行级 CER `GATE_FAIL`（3.17% / 阈值 ≤ 2%）、关键字段 F1 `GATE_FAIL`（76.00% / 阈值 ≥ 97%）、TEDS `GATE_FAIL`；未达标时产品侧强制 `NEEDS_REVIEW`，不得当作通过。
- **已合并并上线（2026-09-23）**：GPT-6 Astra 第二轮前端包（`BidProof-frontend-redesign-round2-20260923.zip`）已并入 `main` 并部署到 `bidproof.marketcase.net` 的 `/` 与 `/app`；决策见 `D-ASTRA-MERGE-2026-09-23`，范围与验收见 `docs/astra-frontend-round2-2026-09-23.md`。核对显示该包只替换详情视图，C-022 的扫描任务页布局未被改动。
- **上线方式（2026-09-24）**：最新版（新 Landing + 安全加固）部署在 Render 免费 Web Service 上。生产闸门要求 `BIDPROOF_PUBLIC_ORIGIN`、显式 `BIDPROOF_ALLOWED_HOSTS`、空 `BIDPROOF_TRIAL_JOIN_CODE`、`JOB_RUNNER=worker` 与显式 `DATA_ROOT`，因此 `render.yaml` 已补齐、`healthCheckPath` 改为 `/readyz`，并由 `scripts/render-serve.sh` 在单容器内执行一次性迁移并守护扫描 worker（免费实例没有 Background Worker）。记录见 `docs/production/render-pilot-2026-09-24.md`；单机正式部署路径保留在 `docs/production/deploy-runbook-marketcase-2026-09-24.md`。
- **已落地（2026-09-24，C-UX-AUTH-2026-09-24）**：`BidProof-0924-minimal-auth.zip` 物料包已并入主分支。首页换成极简落地页（H1「投标前，先查漏交材料。」+ 单个主 CTA「开始检查」+ 可玩示例 + 三张用途卡），删除旧的定价 / FAQ / 四步流程 / 轨道动效；认证收敛为统一 AuthModal（邮箱验证码、短信验证码、Google/GitHub OAuth），未配置渠道时自动回落到原密码入口。旧营销页 `static/landing.html`、`static/landing.js` 已下线，`static/landing.css` 改名 `static/legal.css` 只服务 `/privacy`。来源与取舍见 `docs/ux-0924/`、配置见 `docs/production/passwordless-auth-2026-09-24.md`。
- **待运营配置（T-UX-AUTH-EXTERNAL-2026-09-24）**：仓库内没有任何真实投递密钥。未设置 `BIDPROOF_OTP_SECRET`（≥32 字符）与邮件 / 短信 / OAuth 供应商时，验证码与 OAuth 入口**不会展示**，线上仍是密码登录——这是设计行为，不是故障。Render 免费实例封禁常见 SMTP 出网端口，线上应走 Resend（HTTPS）。
- **已上线（2026-09-24，C-UX-AUTH-LIVE-2026-09-24）**：`main` 推送后 Render 自动部署，`bidproof.marketcase.net` 的 `/` 已切到新极简首页（资源指纹 `index-WmSIqwZA.css`），`/app` 弹出统一认证对话框；已下线的 `/static/landing.html` 返回 404。线上 `/api/auth/status` 的 `passwordless` 仍全为 false，说明验证码 / OAuth 入口没有对外开启。证据见 `outputs/playwright/0924-live-*`。
- **可做**：工程优化、CI、台账工具、文档、性能；收到真实输入后追加 `pilot-row.json` / `icp-row.json`
- **已回退（C-022）**：工作台补丁 002 打乱扫描任务页对齐，已恢复 `4516b3f` 布局；相关材料已移入 `docs/archive/`，勿整页落地

## 标准命令

```bash
pip install -r requirements.txt   # 或 uv sync
uv run python -m app.workflow check
uv run python -m app.workflow next-action
uv run --group dev pytest -q
npm ci --prefix frontend && npm run build --prefix frontend   # 产物写入 static/，勿手改
npm ci --prefix landing && npm run build --prefix landing     # 首页产物写入 static/marketing/，勿手改
.scriptsstart-smoke.ps1                                      # 本机回环 SMTP + 应用，验证验证码链路（状态写 %TEMP%）
uv run python -m work.pilot_readiness --json
uv run python -m work.pilot_ledger --render-review
uv run python -m work.icp_ledger --render-review
```

## 环境约定

- 测试：`BIDPROOF_ENV=test`，`BIDPROOF_ALLOW_TRUSTED_HEADERS=1`（见 `tests/conftest.py`）
- 真实 upload PDF 不在 Git 中；完整回归：`.\scripts\sync-real-upload-fixtures.ps1`
- 公网试点：Render 免费 Web Service（`render.yaml`）；本机备用 `.\scripts\start-pilot.ps1`（Tunnel HTTP/2）
- 生产环境**不使用共享试用码**：`BIDPROOF_ENV=production` 下即使 `BIDPROOF_TRIAL_JOIN_CODE` 有值，也会被置空并打印 WARNING（2026-09-24 起；此前是直接拒绝启动，导致 Render 连续部署失败并让服务离线）。原因是 Render 只应用蓝本的新增与更新，不会删除已存在的服务变量。试用入口改为个人注册（`BIDPROOF_PERSONAL_SIGNUP=1`，独立工作区）或管理员邀请；在面板删掉该变量可消除告警，行为不变。
- 新增 gitignore 门禁（2026-09-23）：`work/uploads/*`、`work/backups/`、`work/restore-drill-*/uploads/`、`third_party/`、训练语料二进制、zip/tgz、覆盖率与日志均不入库
- 本地隔离区：`_cleanup-archive-2026-09-23/`（2026-09-23 清扫移出的过期文件，已被忽略，确认后可整体删除）
- 统一认证开关（2026-09-24）：`BIDPROOF_OTP_SECRET` 少于 32 字符、或供应商参数不全时，对应渠道在 `/api/auth/status` 里就是不可用，前端不渲染入口。邮箱走 `BIDPROOF_EMAIL_PROVIDER=resend` 或 `=smtp`；短信另有 `BIDPROOF_SMS_ALLOWED_PREFIXES` 国家码白名单；OAuth 需要成对的 `BIDPROOF_GOOGLE_*` / `BIDPROOF_GITHUB_*`。`BIDPROOF_SMTP_SECURITY=plain` 只在非生产环境且指向回环地址时被接受。
- 物料包原件：`BidProof-0924-minimal-auth.zip` 与解包目录 `_incoming-0924/` 只作来源留档，已加入 `.gitignore`，不要提交。

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
- 在没有真实供应商密钥时宣称「验证码/短信/OAuth 已上线」
- 未验证就宣称「生产就绪」或「企业已验收」

## 云端 / 平板 Cursor

克隆 `https://github.com/ouyangzhuowu-afk/BidProof`，开 **Cloud Agent**，首条消息示例：

```
读 AGENTS.md 和 workflow/project-state.json，执行 next_best_action 的 fallback（T-005 台账与工程优化），跑 pytest 后 push。
```
