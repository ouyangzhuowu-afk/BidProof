# BidProof 前端交接文档（草稿）

> 状态：**草稿 / 待团队确认**。本文件由接手方依据只读分析产出，所有事实附命令或文件证据；未验证项标注 [待确认]。
> 分析基准：仓库 `C:\BidProof` HEAD `e484a2f`（2026-09-22）；交接代码包 `BidProof-frontend-redesign-20260922.zip`、`BidProof-frontend-redesign-round2-20260923.zip`。
> 分析日期：2026-09-23。分析环境：Windows / Python 3.13（uv 管理）/ Node v26.4.0 / npm 11.17.0 / git 2.54.0。

## 1. 项目简介与业务背景

BidProof（Workspace 内编号 project-025-bid-evidence-agent）是面向 IT 服务、软件实施类中小企业的投标资格与废标风险扫描工具。产品定位与红线见 `workflow/master-brief.md`：

- 输入：招标文件 PDF（优先中文）与企业证据材料。
- 处理：逐页抽取要求项（资格 / 废标 / 评分 / 关键日期），与企业证据做匹配。
- 输出：每条结论必须带招标文件页码 + 企业证据页码 + 可核对原文；缺任一侧必须降级为 `UNKNOWN` / `NEEDS_REVIEW`，不得为 `PASS`。
- 边界：不替用户做投标决策、不生成标书、不出法律意见；`PASS` 门禁由确定性规则与人工复核决定。
- 当前阶段：sandbox-campaign-A 工程阶段；真实企业试运行（T-005）处于 blocked，等真实输入。

本次交接对象是**前端重构代码包**（GPT-6 Astra 产出，两轮），它挂在上述产品之上，未合并进 main。

## 2. 技术栈与架构（文字版）

服务端（Python，前端无法绕过的契约方）

```
浏览器 ──HTTP──> FastAPI(app/main.py)
                  ├─ app/api/*.py        路由（runs / auth / jobs / members / projects / reports / admin / health）
                  ├─ app/authz.py        权限枚举 + 角色矩阵 + require()
                  ├─ app/csrf.py         双提交 CSRF（Cookie 会话请求必须带 X-CSRF-Token）
                  ├─ app/services/*      业务编排（scan / run / report / workspace / document）
                  ├─ app/rules.py        确定性判定与双页码门禁（PASS 必须双侧可定位）
                  ├─ app/extraction.py + app/ocr.py   页级抽取 / OCR fail-closed
                  ├─ app/db.py + SQLAlchemy + Alembic  SQLite（默认）/ PostgreSQL（生产）
                  └─ static/             构建产物目录，FastAPI 直接托管
```

前端（原生 ES 模块 + Vite，无框架）

```
frontend/src/main.js        入口：装载主题、i18n、路由、鉴权、各 feature
frontend/src/app.js         应用装配层：视图切换、详情/决策控制器、任务读取竞态控制
frontend/src/core/          基础设施：http（重试/取消/CSRF）、router（hash）、store+state、theme、toast、icons、permissions、format、dom
frontend/src/api/           接口层：paths.js（路径唯一来源）+ auth/runs/jobs/workspace
frontend/src/ui/            render（SafeHtml 标签模板 + 三态）、confirm、secret-reveal
frontend/src/features/      auth / runs(list·matrix·decision·collab·evidence-reader·review-model) / scan(intake·watcher) / jobs / admin(account·members·operations·projects)
frontend/src/i18n/          中英文案表
frontend/src/styles/        tokens → reset/base → layout → components → views → legacy（@layer 分层，legacy 兜底未迁移视图）
vite build ──> ../static/{app.js, style.css, index.html(注入 ?v= 戳)}
```

关键形态：**hash 路由单页应用 + 服务端托管静态文件 + 无前端服务端渲染**；无 npm 运行时依赖（devDependencies 只有 vite/typescript/eslint）。

## 3. 目录结构说明

| 路径 | 作用 | 交接注意 |
|------|------|----------|
| `app/` | FastAPI 后端（api / services / repositories / models / rules） | 代码包含后端改动（新增原页预览接口、原件命名隔离） |
| `static/` | 前端**构建产物**，由 FastAPI 托管；不要手改 | 产物改动会进 diff，CI 会校验是否与源码一致 |
| `frontend/src/` | 前端源码唯一真源 | 改这里，然后 `npm run build` |
| `frontend/preview/` | 早期静态预览页，不参与线上 | 历史遗留，可评估删除 |
| `frontend/scripts/` | build-css / stamp-assets / 各 DOM 测试脚本 | 测试脚本不在 package.json 的 scripts 里，需手动 node 执行 |
| `frontend/types/api.d.ts` | 手写接口类型（非生成） | 与后端 schema 靠人对齐，无自动校验 |
| `tests/` | pytest 后端 + 前端契约测试 | `test_frontend_contract.py`、`test_ui_product_contract.py`、`test_mobile_layout.py` 约束前端 |
| `docs/` | 设计/迁移/交付记录 | round-1/round-2 交付记录在包内 `docs/ui-redesign-2026-09-22.md`、`docs/ui-hardening-round2-2026-09-22.md` |
| `workflow/` | 控制面（project-state / master-brief / 执行说明） | 每轮启动必读；状态文件是进度唯一真源 |
| `outputs/` | 验收报告、台账、截图、基准数据 | pilot/ICP 台账空置，禁止写入测试数据 |
| `deploy/helm/` | K8s Helm chart | 本地部署可选路径 |
| `migrations/` | Alembic 迁移 | 数据库变更必须走迁移 |

## 4. 本地启动、构建、测试、部署

仓库主流程（本次实测）

```powershell
uv run python -m app.workflow check                 # PASS: Project-025 workflow state is valid
uv run --group dev pytest -q                        # 303 passed, 11 skipped in 43.24s
npm run check  --prefix frontend                    # tsc --noEmit，exit 0
npm run lint   --prefix frontend                    # 0 error, 4 warning（既存）
npm run build  --prefix frontend                    # build:css → vite → stamp-assets
```

只看前端页面（无需 Node，包内含构建产物）

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt 'httpx2>=2.12'    # httpx2：pydantic 维护的 HTTP 客户端，供 FastAPI TestClient 使用
export BIDPROOF_DATABASE_URL= DATABASE_URL= BIDPROOF_ENV=development
export BIDPROOF_DATA_ROOT="$(mktemp -d /tmp/bidproof-review.XXXXXX)"
PYTHONPATH=. python scripts/seed-ui-review.py        # 生成 9 条示例审查项的隔离空间
python -m uvicorn app.main:app --host 127.0.0.1 --port 8768
# 打开 http://127.0.0.1:8768/app ，账号 ui-review / LocalReview2026!（仅本地示例空间）
```

Windows 等价写法（本次实测通过）：`& .\.venv\Scripts\python.exe scripts/seed-ui-review.py`，环境变量用 `$env:BIDPROOF_DATA_ROOT='...'` 设置。

测试

```
后端：uv run --group dev pytest -q
前端：node frontend/scripts/test-review-workbench.mjs 等 7 个脚本（需 jsdom，见包内 round-2 记录）
```

部署

| 方式 | 命令/文件 | 实测状态 |
|------|-----------|----------|
| 本机开发 | `uvicorn app.main:app` | 本次跑通（/healthz、/app、登录、原页预览均 200） |
| 容器 | `Dockerfile` + `docker-compose.yml`（postgres + bidproof + worker，端口 8016→8080） | [未执行] 未在本机构建镜像 |
| K8s | `deploy/helm/bidproof`（含 secret/configmap/deployment） | [未执行] |
| 公网试点 | `render.yaml`（Render 免费 Web Service）；历史记录另见 `scripts/start-pilot.ps1`（Cloudflare Tunnel） | [未执行] 需账号与域名 |

CI（GitHub Actions，`.github/workflows/ci.yml`）：ruff → pip-audit → workflow check → Alembic 迁移（SQLite + PostgreSQL）→ 前端构建 + `git diff --exit-code -- static/app.js static/style.css` → pytest。

## 5. 环境变量清单

来源：`.env.example`（17 项）。常用分组：

| 变量 | 用途 | 备注 |
|------|------|------|
| `BIDPROOF_ENV` | 运行环境（development/test/production） | 测试用 `test` |
| `BIDPROOF_DATA_ROOT` | 数据根目录（uploads/backups/job-staging） | 本地部署关键项 |
| `BIDPROOF_DATABASE_URL` / `DATABASE_URL` | 数据库连接 | 同时清空可回落到本地 SQLite |
| `POSTGRES_PASSWORD` | docker-compose 用 | 不提交 |
| `BIDPROOF_PERSONAL_SIGNUP` / `BIDPROOF_TRIAL_JOIN_CODE` / `BIDPROOF_BOOTSTRAP_TOKEN` | 注册、邀请码、初始化令牌 | 控制"邀请制空间"入口 |
| `BIDPROOF_ALLOW_TRUSTED_HEADERS` | 信任身份头（仅测试） | 生产必须关闭，否则可伪造身份 |
| `BIDPROOF_JOB_RUNNER` / `BIDPROOF_JSON_LOGS` / `BIDPROOF_METRICS` / `BIDPROOF_OTEL` | 作业执行与可观测性 | worker 模式用于容器拆分 |
| `BIDPROOF_LICENSE_KEY` / `BIDPROOF_LICENSE_REQUIRED` | 本地部署授权 | 企业内网部署用 |
| `BID_OCR_PROVIDER` / `BIDPROOF_OCR_EGRESS_MODE` / `BIDPROOF_OCR_EGRESS_ALLOWED` | OCR 提供方与出网白名单 | 数据安全关键开关 |
| `BIDPROOF_UI_TEST_DEPS` / `JSDOM_MODULE` | 仅前端 DOM 测试脚本用 | 非产品依赖 |

前端**没有**独立环境变量或 `.env`：API 基址为空（同源相对路径），因此天然适配本地部署与反向代理；这是本地部署兼容性的加分项。

## 6. 路由与页面清单

hash 路由（`frontend/src/core/router.js` + `app.js:664-668`）

| 路由 | 页面 | 视图容器 |
|------|------|----------|
| `#home` | 扫描任务工作台（列表、概览指标、筛选、批量操作、精度看板） | `#home-view` |
| `#jobs` / `#jobs/{id}` | 扫描作业（进度、失败原因、重试、取消） | `#jobs-view` |
| `#admin` | 成员与设置（成员、项目、账号/MFA/令牌/会话、运维：备份、保留策略、用量、隐私） | `#admin-view` |
| `#detail/{runId}` | 审查工作台（条款清单、优先风险、双向原文对照、材料、协作与审计） | `#detail-view` |
| `#decision/{runId}` | 人工决策（逐条确认/驳回、缺口处置） | `#decision-view` |
| 落地页 | `/static/landing.html`（外链自 `/`） | 独立页面，非 SPA 路由 |

弹层/面板（非路由）：上传（`#intake-panel`）、报告漏项（`#missed-panel`）、登录/注册/激活（`#auth-panel`）、账号激活与重置（`#account-action-panel`）。

## 7. 核心组件与状态管理

- 渲染：`ui/render.js` 提供标签模板 `html`，默认转义；只有 `raw()` 铸造的对象能通过 `trustedMarkup` WeakSet 校验进入 innerHTML；eslint 拦截直接操作 innerHTML。
- 状态：**目前两套并存**——`state.js`（供 app.js）与 `core/store.js`（供 features/*）。作者已在 `core/permissions.js` 注释中承认这一技术债，接口层因此用 `setCurrentRole()` 手动同步。
- 请求：`core/http.js` 只对读请求的网络错误与 502/503/504 重试；写请求不自动重放；期待 JSON 的响应解析失败即失败；并发读去重在成功/失败两路径都清理；兼容无 `AbortSignal.any` 的环境。
- 竞态：`app.js` 为"当前任务读取"建立 AbortController，切换任务/离开详情即取消，迟到的响应不能改写当前任务与加载遮罩。
- 路由：区分 `navigate()`（用户跳转写历史）与 `apply()`（响应历史），修掉了旧实现"后退要按两次"的问题。
- 主题/国际化：`core/theme.js`（浅/深/跟随系统，可访问名称明确）+ `i18n/index.js`（中英两套，`verdict.*` 四态文案）。
- 组件形态：不是组件库，而是"视图模块 + 标签模板函数 + 事件委托"；共用交互（确认框、密钥一次性展示、Toast）在 `ui/`。

## 8. API 契约与 mock 说明

- 路径唯一来源：`frontend/src/api/paths.js`（约 60 条），改路径只改这里。
- 类型：`frontend/types/api.d.ts`（手写，9178 字节）经 jsconfig/JSDoc 生效；`npm run check` 覆盖。
- 契约入口：`docs/api-integration.md`；后端路由表由 `tests/test_architecture_boundaries.py`、`tests/test_queue_observability.py` 锁定路由数量（当前 80 个 operation）。
- Mock：**产品代码没有 mock 层**。测试用替身：Python 侧 monkeypatch + TestClient；前端 DOM 测试用自建 HTTP stub（`frontend/scripts/test-*.mjs`，需外部 jsdom）。
- 与前端不一致处（详见分析文档第 5 节）：新原页接口未登记进 `paths.js`；后端 `GET /api/evidence`、`GET /api/audit/chain` 无前端入口。

## 9. 权限与角色说明

| 角色 | 后端（`app/authz.py` 事实） | 前端（`core/permissions.js`） |
|------|------------------------------|-------------------------------|
| OWNER | 全部权限 | members/projects/retention/backups/tokens/account |
| ADMIN | 管理类权限（成员、项目、保留、备份等，不含 OWNER 专属） | 同 OWNER 的前端可见性 |
| REVIEWER | 读取 + 复核 + 导出类 | 仅 account.self |
| VIEWER | 只读 | 仅 account.self |

前端是**可见性门禁**，不是授权层；`isPermissionError()` 只在 403 时提示权限，其余错误按普通错误态处理。矩阵中 `backups.manage`、`tokens.manage` 两项在源码注释里被明确标注为"按同级推定"，需与后端 `Permission.BACKUP_MANAGE` 对齐后确认 [待确认]。

企业空间隔离：请求经 `X-Workspace-ID` / 会话绑定的工作区作用域，后端 `require_scoped()` 强制校验；跨工作区访问返回 404（本次实测原页接口匿名 401、越权 404 均由后端测试覆盖）。

## 10. 已知问题、TODO、技术债

1. 代码包未合并：`static/index.html` 整页替换了详情视图 DOM，与 C-022 记录的回退决定冲突，需要产品/技术共同裁决 [待确认]。
2. Windows 上 `pytest` 出现 1 项 teardown error（原页预览 + 删除任务的文件占用），Linux/macOS 不可见，见分析文档第 3、6 节。
3. 构建产物跨平台漂移：`style.css` 注释中的路径分隔符与 `index.html` 的 `?v=` 戳随平台变化，Windows 本地 `npm run build` 后 CI 门禁会红。
4. 双 store 并存（state.js + core/store.js）；`app.js` 仍是最大的装配文件（约 29.5 KB）。
5. `core/permissions.js` 的两条能力映射为推定值。
6. 后端能力未进前端：`/api/evidence`（企业证据库）、`/api/audit/chain`（追加写审计链导出）。
7. 可访问性只做到 CSS/DOM 层覆盖，键盘全流程与"减少动态效果"未实测（包内记录自述）。
8. 技术债入口：`frontend/src/styles/legacy.css`（60 KB 旧样式归档层）、`frontend/preview/`（早期预览页）。

## 11. 下一步迭代建议

短期（2 周交接期）先做三件事：把代码包合并方式定下来（分支 + 灰度开关，不与 main 的落地页/工作台改动硬碰）、把 Windows 单测 error 与构建产物漂移修掉、把新原页接口登记进 `paths.js` 并把 `/api/evidence`、`/api/audit/chain` 的 UI 缺口登记为需求。中期（4–12 周）按分析文档第 8 节需求池推进，优先保证"判定可追溯、复核可交班、审计可导出"三件事，再做体验与本地部署收尾。

## 12. 关键联系人与负责人角色

| 角色 | 负责人 | 状态 |
|------|--------|------|
| 上一阶段前端实现（代码包产出方） | GPT-6 Astra | 交接已完成代码包，问答通道 [待确认] |
| 本次接手（前端负责人） | [待确认] | 待指派 |
| 后端 / 契约负责人 | [待确认] | 需回答第 10 节接口问题 |
| 产品 / 业务验收负责人 | [待确认] | 需裁决工作台整页替换是否采纳 |
| 控制面（workflow state）维护 | 仓库 Agent（Javis 在 state 中登记为 sandbox campaign owner） | 现状 |

