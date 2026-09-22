# BidProof 前端代码包交接分析（只读第一轮）

分析日期 2026-09-23 ｜ 仓库 `C:\BidProof` HEAD `e484a2f`（2026-09-22）｜ 环境 Windows + Python 3.13(uv) + Node v26.4.0 + npm 11.17.0

---

## A. 交接摘要

1. 两个 zip 都是**完整项目快照**（含 `app/` 后端、`frontend/` 源码、`static/` 产物、`tests/`、`docs/`、`deploy/`），不是纯前端目录。
2. 代码包**未合并、未推送、未部署**：仓库 working tree 干净，`git log` 中不存在这些改动；两个 zip 位于仓库根且未跟踪。
3. zip 的基线就是当前 main（`e484a2f`）附近：437 个文件中 373 个与仓库逐字节一致（忽略换行符差异），25 个为 Astra 修改（在 git 历史中无任何匹配 blob），39 个为新增文件。
4. 第二轮（09-23）相对第一轮（09-22）改动 54 个文件、+2593 / −717 行：新增阅读器、连续核验、上传生命周期修复，5 个新测试脚本、1 份交付记录、2 个后端文件与 2 个新测试。
5. 后端也被改动：新增原页 PNG 接口（路由数 79→80），并改变原件落盘命名（tender- / evidence-NNN- 前缀），属于对既有数据的**兼容性变更**。
6. 本轮实测：仓库 303 passed / 11 skipped；代码包 315 passed / 11 skipped / **1 error**（Windows 上原页预览测试的 teardown 文件占用）；前端构建、类型检查、lint 均通过。
7. 代码包可真实跑起来：seed 脚本造 9 条示例 + uvicorn 起服务，`/healthz`、`/app`、登录、任务详情、原页 PNG 全部 200；越界页码 422/404、匿名 401 均符合预期。
8. 构建**可复现**：`npm ci && npm run build` 重跑，11 个产物中 9 个逐字节一致；差异只在 style.css 注释里的路径分隔符与由此派生的 index.html 内容戳 ⇒ Windows 本地构建会与提交产物不一致。
9. 最大交接风险不是代码质量（本次审阅的前端源码质量明显在均线之上），而是**决策悬空**：代码包把 static/index.html 的详情视图整页替换，而仓库 C-022 明确记录过"整页替换打乱布局、已回退"，两轮验收口径（作者自测 4 档视口）尚未经团队确认。
10. 后端能力缺口：`GET /api/evidence`、`GET /api/audit/chain` 在后端存在，前端（代码包与仓库）均无入口。

---

## B. 代码包盘点

### B.1 代码包与来源

| 项 | 值 |
|---|---|
| 包 1 | `C:\BidProof\BidProof-frontend-redesign-20260922.zip`（19,071,554 B，sha256 前缀 83745FF46CD718A2…，432 条目） |
| 包 2 | `C:\BidProof\BidProof-frontend-redesign-round2-20260923.zip`（19,199,053 B，sha256 前缀 D5089F2BEEB882C5…，437 条目） |
| 包内根目录 | `BidProof-redesign/` |
| 来源 | GPT-6 Astra 重构产物；包内 START-HERE.md 自述"独立本地副本、未推送 GitHub、未部署公网" |
| 基线判定 | 与仓库 HEAD 大体同源：README.md 与历史 blob `4516b3f` 一致、frontend/src/features/runs/list.js 与 `11a6b55` 一致，其余同源文件与当前工作树一致 |
| 缺失的随包证据 | 包内文档提到同级交付有 BidProof-round2-archive-acceptance.json 与 .zip.sha256；在 `C:\BidProof` 与 Downloads 下**未找到**，CRC/启动验收记录 [待确认] |

### B.2 第二轮相对第一轮的变化（git diff --no-index）

删除（打包瘦身）：outputs/opus5-materials/*（8 个文件 + 1 张登录截图）、work/source-docs/*.docx（3 份规划附件）。

新增（后端/契约/工具）：app/services/document_service.py、tests/test_source_page_preview.py、tests/test_upload_source_identity.py、scripts/seed-ui-review.py、frontend/scripts/stamp-assets.mjs。

新增（前端交互）：frontend/src/features/runs/evidence-reader.js、features/runs/review-model.js、features/scan/intake.js、styles/views/{intake,reader-navigation,review-cards,workbench}.css；5 个新测试脚本。

新增（文档/记录）：docs/ui-redesign-2026-09-22.md、docs/design-tokens.md、docs/ui-hardening-round2-2026-09-22.md、outputs/ui-redesign-round2/*（2 份 JSON + 6 张截图）。

修改（含既有文件）：app/api/runs.py(+21/−3)、app/services/scan_service.py(+4/−2)、frontend/src/{app.js,state.js,core/http.js,core/icons.js,core/theme.js,core/format.js,api/runs.js,ui/render.js,features/runs/matrix.js,features/scan/watcher.js,styles/tokens.css,styles/base.css,styles/index.css,types/api.d.ts}、static/*、tests/{test_api.py,test_architecture_boundaries.py,test_queue_observability.py}。

### B.3 技术栈与工程要素

| 维度 | 现状 |
|---|---|
| 语言/框架 | 前端原生 ES 模块（无 React/Vue）；后端 FastAPI + SQLAlchemy + Alembic |
| 包管理器 | npm（frontend/package-lock.json）；Python 用 uv（uv.lock）或 pip |
| 构建 | Vite 5（IIFE 单文件 → static/app.js）+ 自研 build-css.mjs（@layer 拼装）+ stamp-assets.mjs（注入内容戳） |
| 路由 | 自研 hash 路由（home / jobs / admin / detail / decision） |
| 状态管理 | 自研，**两套并存**：state.js + core/store.js |
| UI 组件库 | 无第三方组件库；自研 ui/render.js（SafeHtml 标签模板）+ Lucide 图标（本地 vendor，无 CDN） |
| 请求层 | core/http.js：读请求有限重试（网络错误 + 502/503/504）、写请求不重放、JSON 解析失败即失败、并发去重、AbortController；CSRF 双提交头 |
| 鉴权 | Cookie 会话 + MFA(TOTP) + API 令牌 + 邀请/激活/重置 + 会话轮换；测试态可用可信身份头 |
| 权限 | 后端 app/authz.py（20 项 Permission × 4 角色）；前端 core/permissions.js 能力矩阵仅控制可见性 |
| 国际化 | i18n/index.js 中英双语（约 170 键），无第三方 i18n 库 |
| 主题 | 浅 / 深 / 跟随系统，tokens.css 变量 + CSS @layer |
| 环境变量 | 前端无环境变量（同源相对路径）；后端 17 项见 .env.example |
| Mock | 产品代码无 mock；前端测试脚本自带 HTTP stub；Python 侧 monkeypatch |
| 测试 | pytest（326 项，含前端契约/移动端布局断言）；前端 7 个 node 脚本（需外部 jsdom 29） |
| CI | GitHub Actions：ruff、pip-audit、workflow check、Alembic（SQLite+PG）、前端构建 + 产物 diff 门禁、pytest |
| 部署 | Dockerfile / docker-compose（postgres+app+worker）/ Helm chart / render.yaml / 本机 Cloudflare Tunnel 脚本 |

### B.4 与预期不符（[实际代码与假设不符]）

1. 任务书假设"交接对象是前端代码包"，实际包内含完整后端、迁移与部署配置，且**含后端行为变更**。
2. 任务书假设"不涉及数据兼容"，实际 scan_service.py 改了原件落盘命名（见 E 节 I-01）。
3. 仓库里已存在一套 Opus5 前端模块化重构（`11a6b55`，2026-09-14）并已在 main；Astra 两轮是在这套结构上的增量 UX 重构，不是"从零重构前端"。

---

## C. 运行与构建验证（实测，含失败）

### C.1 仓库（未合并状态）

| 命令 | 结果 |
|---|---|
| `uv run --group dev pytest -q` | **303 passed, 11 skipped in 43.24s**，exit 0。进程退出时打印 PermissionError: WinError 32 … bid_agent.sqlite3（临时目录清理噪声，不影响结果） |
| `uv run python -m app.workflow check` | PASS: Project-025 workflow state is valid |
| `npm run check --prefix frontend` | exit 0（tsc --noEmit） |
| `npm run lint --prefix frontend` | **0 error, 4 warning**：frontend/scripts/build-css.mjs:63(no-console)、frontend/src/core/http.js:214(no-promise-executor-return)、frontend/src/core/http.js:238(require-await)、frontend/src/features/runs/list.js:117(require-await) |
| `npm run build --prefix frontend` | [未执行] 故意不跑：会覆写仓库 static/ 产物；改在解压副本中验证（见 C.2） |
| `pytest --collect-only -q` | 314 tests collected |

### C.2 代码包（解压到临时目录后）

| 命令 | 结果 |
|---|---|
| `npm ci`（frontend） | 98 packages，3s；npm 提示 esbuild postinstall 未执行（allow-scripts 策略），不影响后续 build |
| `npm run build` | 通过：build:css → static/style.css (198.9 kB)；vite 40 modules → ../static/app.js 183.00 kB、map 442.26 kB；build:stamp → asset URLs match built content |
| `npm run check` / `npm run lint` | 通过（作者记录 0 error / 2 既有 warning） |
| `python -m pytest -q`（复用仓库 venv） | **315 passed, 11 skipped, 1 error in 41.02s**（作者记录为 314 passed / 12 skipped） |
| 失败用例 | tests/test_source_page_preview.py::test_source_preview_handles_a_corrupt_pdf_without_returning_file_bytes → teardown 时 DELETE /api/runs/{id} 触发 PermissionError: [WinError 32]，路径 …/uploads/<run>/tender-tender.pdf |
| 复现性 | 单跑该用例 3/3 稳定复现（1 passed, 1 error）；单独跑整个 test_source_page_preview.py → 8 passed；该文件 + test_upload_source_identity.py → 12 passed（2/2 次）。即**顺序/时序相关**，非随机失败 |

补充探针（独立脚本直接调用 pymupdf）：对损坏 PDF 执行 fitz.open() 抛 FileDataError 后立即 unlink() **成功** ⇒ 不是 document_service 错误分支泄漏句柄这一简单解释。根因 [待确认]，首选排查方向：上传/解析后台线程在响应返回后仍持有原件句柄（测试覆盖的时序竞争）。

### C.3 最小可运行步骤（已在 Windows 实测）

    $env:BIDPROOF_DATABASE_URL=''; $env:DATABASE_URL=''
    $env:BIDPROOF_ENV='development'; $env:BIDPROOF_DATA_ROOT='<临时目录>'; $env:PYTHONPATH='.'
    & .\.venv\Scripts\python.exe scripts/seed-ui-review.py    # {"run_id": "f6c581eb…", "requirements": 9, …}
    & .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8768

实测结果：GET /healthz 200；GET /app 200（含 evidence-reader、review-columns）；GET /static/{app.js,style.css,index.html} 200；GET /api/auth/status（匿名）200 且 setup_required=false、authenticated=false；POST /api/auth/login（ui-review / LocalReview2026!）200，role=OWNER；GET /api/runs/{id} 200 且 requirements=9、source_documents=2；GET /api/runs/{id}/files/TENDER-001/pages/1 200 image/png 44,119 B（PNG 魔数正确、Cache-Control: no-store, private）；EVD-001/pages/1 200 43,767 B；pages/0 → 422；pages/99 → 404；匿名访问该接口 → 401。

### C.4 构建产物可复现性

重建后的 static/ 与 zip 内交付产物对比：app.js、app.js.map、favicon.svg、landing.{html,css,js}、privacy.html、assets/bidproof-workspace.png、vendor/lucide.min.js **逐字节一致**；style.css 仅注释行 src/styles/legacy.css 与 src\styles\legacy.css 之差（长度相同）；index.html 仅内容戳 v=0a26625bfbdf 与 v=8e5b2341f406 之差（由 style.css 内容哈希派生）。

后果：仓库既有 static/style.css 是 **Windows 构建**（含反斜杠），zip 交付产物是 **macOS/Linux 构建**（含斜杠）。合并后在本机重建即产生 diff，CI 的 `git diff --exit-code -- static/app.js static/style.css` 在本地恒红（GitHub Actions 的 Linux runner 反而会绿）。

---

## D. 业务模块映射表

完成度口径：已实现＝有页面 + 接口且本轮实测可见；部分＝有接口或只读展示但缺关键交互；缺失＝无前端入口。

| 业务模块 | 对应页面/路由 | 关键组件 | 接口/数据源 | 完成度 | 缺口 | 风险 |
|---|---|---|---|---|---|---|
| 工作台（任务总览） | #home / #home-view | features/runs/list.js、概览指标、筛选、批量操作、精度卡 | GET /api/runs、/api/notifications、/api/accuracy/metrics | 已实现 | 无 | 低 |
| 项目/标包 | #admin → 项目区 | features/admin/projects.js | GET/POST /api/projects、/api/projects/{id} | 已实现 | 未见"标包/分包"粒度字段承载 [待确认] | 中 |
| 招标文件解析 | 上传面板 #intake-panel + #jobs | features/scan/intake.js、watcher.js、features/jobs/index.js | POST /api/runs、GET /api/jobs、SSE /api/jobs/{id}/events | 已实现 | 解析进度只呈现后端状态，无页级可视化；旧版 Office 需先转换（既有约束） | 中 |
| 条款清单 | #detail/{id} | features/runs/matrix.js（分类筛选、搜索、25 条分页、优先风险分批） | GET /api/runs/{id} 的 requirements | 已实现 | 清单本身不能单独导出（只有整份报告） | 低 |
| 企业资质库 | 无独立页面 | 仅在任务内作为 EVD-* 来源展示 | 后端 GET /api/evidence **前端未接入** | 缺失 | 企业级证据库/材料复用无 UI 与调用 | 中 |
| 投标文件比对 | 无独立页面 | 结果体现在条款卡片与原文对照 | 后端 rules.py 匹配结果 | 部分 | 无"企业材料 × 条款"矩阵视图、无比对进度/覆盖度视图 | 中 |
| 四类判定 | #detail、#decision | i18n verdict.*（已通过/不通过/待确认/待复核）、matrix.js 状态胶囊、review-model.js | requirements[].status + quality_gates 强制降级 | 已实现 | "未找到证据"与"待确认"文案边界需产品确认（当前 UNKNOWN=待确认） | 中 |
| 双页码引用 | #detail | matrix.js citation()（招标/企业两侧引用块）、features/runs/evidence-reader.js（双向原文对照、翻页、回到引用页） | GET /api/runs/{id}/files/{source_id}/pages/{n}（新）、下载接口 | 已实现 | 卡片只展示证据链首条（evidence[0]），多条证据需在阅读器切换 | 中 |
| 人工复核 | #decision/{id}、#detail | features/runs/decision.js、matrix.js（确认/驳回/备注）、collab.js | POST /api/runs/{id}/review、/metadata、/remediations | 已实现 | 无批量复核；复核人可自由指派，无"复核人 ≠ 发起人"强制校验 [待确认] | 中 |
| 邀请制空间 | #auth-panel、#account-action-panel | features/auth/*、ui/secret-reveal.js | /api/auth/invitations、trial-join、activate、reset-password；BIDPROOF_TRIAL_JOIN_CODE | 已实现 | 邀请有效期/名额的可视化管理 [待确认] | 中 |
| 本地部署设置 | #admin → 运维区 | features/admin/operations.js（备份、保留、用量、隐私、健康） | /api/workspace/{settings,privacy,usage}、/api/retention/*、/api/backups、/healthz?detail=true | 部分 | 无环境变量面板（设计如此），许可证/集群/离线安装说明不在前端 | 低 |
| 审计日志 | #detail 协作与留痕区、#admin 用量 | features/runs/collab.js（评论 + 审计事件时间线） | GET /api/runs/{id}/audit；后端 GET /api/audit/chain **前端未接入** | 部分 | 无工作区级审计查询/导出页面（追加写审计链已有接口） | **高** |
| 报告导出 | #detail 头部 | app.js 导出入口 | /api/runs/{id}/report.{pdf,html,csv}、/api/runs/bulk/report.zip | 已实现 | 导出内容与双页码引用的一致性本轮未验证 [待确认] | 中 |
| 指标看板 | #home 精度区、#admin 用量区 | list.js 精度卡（precision/recall + 口径说明） | /api/accuracy/metrics（含 review_population_complete 门禁） | 部分 | 无趋势/时间序列、无按类别细分视图 | 中 |

---

## E. 接口契约与数据流问题

| 编号 | 接口 | 问题 | 影响 | 建议 | 优先级 |
|---|---|---|---|---|---|
| I-01 | POST /api/runs（落盘命名） | 存储名由 <原名> 改为 tender-<原名>、evidence-NNN-<原名> | 老任务磁盘仍是旧名（读取走 run 记录中的路径，不会立刻坏）；但备份校验、报告内文件名、外部脚本按名匹配需逐项确认 | 加一次性迁移或兼容检查；发布说明写明"新上传新命名、旧数据不改名"；补旧数据读取回归 | P0 |
| I-02 | GET /api/runs/{id}/files/{source_id}/pages/{n} | 未登记进 frontend/src/api/paths.js，URL 在 evidence-reader.js:209 字符串拼接 | 违背"路径唯一来源"约定，后端改路径时易漏改 | 在 paths.js 增加 sourcePage(runId, sourceId, page) 并改调用点 | P1 |
| I-03 | GET /api/evidence | 后端存在，前端无引用 | 企业资质库无 UI，材料复用靠重复上传 | 先确认产品是否要该页面；若要，补 UI 与权限（EVIDENCE_DOWNLOAD 已存在） | P1 |
| I-04 | GET /api/audit/chain | 后端存在，前端无入口 | 审计无法在工作区级查询/导出，C-017 的价值未在前端体现 | 在 #admin 增加审计查询 + 导出入口 | P1 |
| I-05 | GET /api/runs/{id} | 判定状态前端按字符串比较，types/api.d.ts 为字面量联合 | 后端新增状态时前端静默降级为未知文案 | 后端状态枚举加契约测试；前端加"未知状态"显式兜底 | P2 |
| I-06 | 原页预览 | 不返回 page_count，前端从 source_documents[].pages 推断并标注冲突 | 元数据缺失时只能显示"总页数未记录"，不能翻到底 | 后端补总页数（响应头或字段） | P2 |
| I-07 | 双页码字段 | 前端依赖 requirement.source / requirement.evidence[] / source_documents[].pages 的既有形状，有类型无运行时校验 | 字段改名会静默退化为"未提取到可核验原文" | 扩展 test_frontend_contract.py 锁字段 | P2 |
| I-08 | 错误/空/加载态 | 前端普遍使用三态渲染，但阅读器图片失败只保留摘录 + 重试，不暴露状态码 | 用户与支持拿不到具体原因 | 失败态附状态码与请求 id | P2 |
| I-09 | CSRF | 前端须把 bidproof_csrf Cookie 回填到 X-CSRF-Token；该约定只在后端 csrf.py 注释 | 前端遗漏时写操作 403，文案只说"CSRF 校验失败" | docs/api-integration.md 补一节并加前端契约测试 | P2 |

---

## F. 代码质量与架构问题

| 编号 | 文件:行号 | 问题 | 严重度 | 证据 | 建议 | 验收标准 |
|---|---|---|---|---|---|---|
| Q-01 | frontend/src/features/runs/evidence-reader.js:209 | 预览 URL 字符串拼接，绕过 api/paths.js | 中 | 该处构造 src 为 sourceUrl 加 "/pages/" 加页码 | 改为 paths.runs.sourcePage(...) | grep "/pages/" 仅出现在 paths.js |
| Q-02 | frontend/src/core/permissions.js（MATRIX 注释） | backups.manage、tokens.manage 为推定值 | 中 | 源码注释自述"后两行是假设…拿到后端权限表后必须核对" | 与 app/authz.py 的 BACKUP_MANAGE 对齐并加断言 | 前后端角色矩阵有自动比对测试 |
| Q-03 | frontend/src/state.js + core/store.js | 两套状态并存，靠 setCurrentRole() 手工同步 | 中 | permissions.js 注释明说 | 合并为单一 store，或加双写断言 | 只有一个 store 模块被 import |
| Q-04 | frontend/src/app.js（29.5 KB） | 装配层过大：详情控制器、视图切换、竞态控制混在一起 | 中 | 文件体积与 app.js:449-520 一带的大段渲染 | 抽出 features/runs/workbench.js | app.js < 12 KB |
| Q-05 | frontend/src/styles/legacy.css（60 KB） | 旧样式归档层与 @layer 并存，优先级靠层序兜底 | 中 | styles/index.css 的 @layer legacy, reset, base, layout, components, views, utilities | 按视图迁移后收缩，迁移期加视觉回归截图 | legacy.css 体积持续下降且有截图基线 |
| Q-06 | frontend/scripts/build-css.mjs:63 附近 | 产物注释写入平台路径分隔符，导致跨平台产物漂移 | 中 | C.4 复现：仅分隔符与派生戳不同 | 生成注释统一用 "/" | Windows 与 Linux 分别 build，git diff 均干净 |
| Q-07 | tests/test_source_page_preview.py | Windows teardown 文件占用导致 1 项 error | 高 | 见 C.2，单跑稳定复现 | 定位持句柄的后台解析线程，或在删除前显式关闭/重试 | 全平台 pytest 无 error |
| Q-08 | core/http.js:214,238、features/runs/list.js:117、scripts/build-css.mjs:63 | 4 条 eslint 既有告警（含 promise executor 返回值） | 低 | npm run lint 输出 | 收敛为 0 告警 | CI lint 门禁 = 0 warning |
| Q-09 | features/scan/intake.js、watcher.js | 上传判重只看文件名+大小+时间，非内容哈希 | 低 | round-2 文档自述"这是文件选择校验，不宣称逐字节内容比对" | 保持文案口径；强校验交给后端 SHA | 文档与实现口径一致 |
| Q-10 | 前端全量 | innerHTML 仅出现在 ui/render.js、core/icons.js、escape.js、main.js 白名单处；标签模板默认转义且有 safeUrl() 协议过滤 | —（正向结论） | rg 扫描（innerHTML / eval / document.write）结果 | 保持 eslint 拦截 | 新增代码不得直接写 innerHTML |
| Q-11 | 全量 | 未发现硬编码密钥/token/私钥；index.html 与源码只出现表单字段名 | —（正向结论） | rg api_key / secret / token / password 结果均为表单与文案 | 保持 .env 不入库 | 定期 pip-audit（CI 已有） |
| Q-12 | 本地部署兼容 | 前端全相对路径、无 CDN、图标与字体本地化；后端 BIDPROOF_DATA_ROOT / LICENSE_* 齐备 | —（正向结论） | index.html 仅引用 /static/*；vendor/lucide.min.js 在包内 | 保持离线可用 | 断网环境可加载页面 |

依赖风险：CI 已含 pip-audit；前端 devDependencies 仅 4 项（eslint/globals/typescript/vite），无运行时 npm 依赖，供应链面很小。httpx2>=2.12 经核验为 pydantic 维护的 HTTP 客户端（仓库 .venv 实装 2.12.0），属仓库既有 dev 依赖，非可疑包。

---

## G. 后续迭代需求池

人时为工程粗估（1 人时 = 1 名熟悉该代码的工程师 1 小时）。

| ID | 优先级 | 模块 | 需求 | 用户故事 | 验收标准 | 依赖 | 负责人角色 | 预计人时 | 验证指标 |
|---|---|---|---|---|---|---|---|---|---|
| F-001 | P0 | 工程/交接 | 确定代码包合并方式（独立分支 + 可回退开关） | 作为团队，我想在不动线上工作台的前提下试用新界面 | 分支可构建可测；static/index.html 差异有开关或书面取舍记录 | 产品裁决 | 前端负责人 + 产品 | 8 | 合并后 main 的 pytest 与前端契约测试全绿 |
| F-002 | P0 | 契约 | 原页接口登记进 paths.js 并补契约文档 | 作为后端，我改路径时希望只改一处 | grep "/pages/" 仅 paths.js；npm run check 通过 | 无 | 前端 | 3 | 契约测试断言 URL 生成 |
| F-003 | P0 | 数据兼容 | 旧任务原件命名兼容核查（备份、报告、下载、恢复） | 作为运维，我不想因为命名变更导致旧任务异常 | 旧数据回归用例通过；发布说明写明变更 | 后端 | 后端 + 前端 | 6 | 旧 run 下载/预览/导出成功率 100% |
| F-004 | P0 | 工程/测试 | 修 Windows teardown 占用（Q-07） | 作为开发者，我希望本机测试结果可信 | Windows/Linux 各跑一次全量无 error | 无 | 后端/前端 | 8 | pytest -q 在 Windows 上 0 error |
| F-005 | P1 | 审计日志 | 工作区审计查询 + 导出页面（接 /api/audit/chain） | 作为投标负责人，我要把"谁在何时核销了哪条"导出交班 | 可筛选导出；越权 403；导出行含时间、人、动作、对象 | 后端契约确认 | 前端 + 后端 | 16 | 导出字段完整率 100%，权限用例覆盖 |
| F-006 | P1 | 企业资质库 | 企业证据库页面（接 /api/evidence），支持跨任务复用 | 作为投标专员，我不想每个项目重复上传营业执照 | 可列表/筛选/预览，复用时来源可追溯 | I-03 确认 | 前端 + 产品 | 24 | 复用率上升、重复上传下降 |
| F-007 | P1 | 判定与引用 | 单条条款支持多条证据并列与逐条核销 | 作为复核人，我要看全部候选证据而非只有第一条 | 卡片展示全部证据；阅读器可逐条切换并保留阅读位置 | 无 | 前端 | 12 | 面板证据条数 = 接口返回条数 |
| F-008 | P1 | 工程 | 构建产物跨平台一致（Q-06） | 作为开发者，我本机 build 后不希望 CI 恒红 | Windows 与 Linux build 后 git diff --exit-code 均通过 | 无 | 前端 | 4 | 两平台产物哈希一致 |
| F-009 | P1 | 权限 | 前端能力矩阵与后端权限表自动比对（Q-02） | 作为管理员，我不想因推定错误而看不到/误看到管理入口 | 单测比对 20 项 Permission × 4 角色 | 无 | 前端 + 后端 | 6 | 矩阵差异用例全覆盖 |
| F-010 | P1 | 双 store | 合并 state.js 与 core/store.js（Q-03） | 作为维护者，我不想再手工同步身份状态 | 只有一个 store；登录/登出/切工作区有回归测试 | 无 | 前端 | 12 | DOM 测试全绿且无 setCurrentRole 手工调用 |
| F-011 | P2 | 可访问性 | 键盘全流程 + 减少动态效果实测与修复 | 作为只用键盘的复核人，我要能完成确认/驳回/翻页 | 4 档视口 + 纯键盘走通确认与驳回；prefers-reduced-motion 生效 | 无 | 前端 | 12 | 键盘用例清单全通过 |
| F-012 | P2 | 指标看板 | 精度指标按类别/时间细分并附口径说明 | 作为负责人，我要知道哪类条款最常漏 | 类别维度可见；INSUFFICIENT 语义保留 | 后端聚合 | 前端 + 后端 | 16 | 口径在页面可见且与后端一致 |
| F-013 | P2 | 本地部署 | 离线安装包与"无外网"启动验证脚本 | 作为企业 IT，我要在内网一次性装好 | 断网环境启动成功；OCR 出网开关默认关闭 | 运维 | 前端 + 运维 | 24 | 断网启动并完成一次扫描 |
| F-014 | P2 | 测试 | 前端 DOM 测试纳入 npm scripts 与 CI（固定 jsdom 版本） | 作为团队，我希望前端测试不再靠手动敲命令 | npm run test:dom 一键跑通；CI 覆盖 | 无 | 前端 | 8 | CI 出现前端测试步骤且全绿 |
| F-015 | P2 | 清理 | 收敛 eslint 告警、清理 legacy.css 与 frontend/preview 死代码 | 作为维护者，我希望静态检查零噪声 | lint 0 warning；删除无引用文件 | 无 | 前端 | 10 | 体积与告警数下降有 diff 证据 |

---

## H. 12 周路线图

| 阶段 | 周次 | 交付物 | 验收标准 | 主要风险 |
|---|---|---|---|---|
| 交接与定调 | W1–W2 | 合并分支 + 回退开关；HANDOVER 与分析两份文档；第 10 节问题清单得到回答；F-002/F-003/F-004/F-008 完成 | 分支可构建可测；Windows/Linux 双平台 pytest 0 error、build diff 干净；产品对整页替换给出书面结论 | 裁决拖延，代码包长期悬空 |
| 证据链补全 | W3–W6 | F-005 审计查询导出、F-006 企业证据库、F-007 多证据核销 | 审计导出字段完整；证据复用可追溯；卡片证据条数与接口一致 | 后端契约未定；审计字段口径变更 |
| 质量与一致性 | W7–W9 | F-009 权限矩阵比对、F-010 单 store、F-014 前端测试入 CI | 权限差异用例覆盖；单 store 回归绿；CI 含前端测试 | 重构触碰鉴权路径需谨慎 |
| 体验与交付 | W10–W12 | F-011 键盘/动效、F-012 指标细分、F-013 离线部署、F-015 清理 | 键盘走通核心流程；断网可启动并完成一次扫描；lint 0 warning | 离线部署受客户环境限制；体验改动需视觉回归支撑 |

每阶段结束必须回写 workflow/project-state.json，并遵守"未验证不得称生产就绪"的既有红线。

---

## I. 待确认问题（按优先级）

1. 代码包的 static/index.html 整页替换详情视图，与 C-022 的"已回退、zip 仅作设计参考"如何取舍？由谁签字？
2. 合并方式：直接覆盖 main，还是分支 + 功能开关灰度？线上工作台是否需要保留旧 DOM 一段时间？
3. 原件命名变更（tender- / evidence-NNN-）是否有存量数据迁移方案？备份校验、报告、外部脚本是否需同步？
4. GET /api/evidence 是否就是"企业资质库"的正式接口？产品是否要这个页面？使用哪条权限？
5. GET /api/audit/chain 的字段与导出格式是否稳定？前端可依赖哪些字段？
6. 四类判定的最终产品文案是什么？（当前 UNKNOWN=待确认、NEEDS_REVIEW=待复核、FAIL=不通过、PASS=已通过）
7. 双页码引用的数据形状是否会变（source / evidence[] / source_documents[].pages）？能否用契约测试锁定？
8. 人工复核流程：是否需要强制"复核人 ≠ 发起人"？是否需要批量复核？
9. 原页预览接口是否返回总页数？加响应头还是扩字段？
10. 前端能力矩阵中 backups.manage、tokens.manage 的角色归属是否与后端 BACKUP_MANAGE 一致？
11. 本地部署的正式形态（docker-compose / Helm / 离线包）？安装文档由谁维护？
12. 设计稿来源与设计走查机制：docs/design-tokens.md 是否为唯一基线？后续改动是否仍需设计走查？
13. 测试环境与发布流程：Render 试点是否继续？公网域名、发布窗口、回滚负责人是谁？
14. 随包交付记录提到的 BidProof-round2-archive-acceptance.json 与 .zip.sha256 在哪里？
15. jsdom 版本与前端测试的长期归属：是否允许进入 devDependencies 并纳入 CI？

---

## J. 自检清单

| 检查项 | 结论 |
|---|---|
| 是否区分了事实、假设、待确认？ | 是。事实附命令或文件证据；基线判定写明依据与不确定性；推断项标 [待确认]（如 teardown 根因、旧数据兼容范围） |
| 是否覆盖全部 P0 风险？ | 覆盖定位/需求（F-001 决策悬空）、技术可行性（F-004 Windows 误差、F-008 产物漂移）、数据安全/合规（Q-11 无密钥泄露、CSRF 约定、工作区隔离实测 401/404、OCR 出网开关保留） |
| 是否每个建议都有验收标准？ | 是。需求池每条含验收标准与验证指标；代码问题表含建议与验收标准 |
| 是否避免空泛建议？ | 是。每条指向具体文件、接口或命令（如 F-002 以 grep "/pages/" 仅出现在 paths.js 为验收） |
| 是否给出可运行的交接路径？ | 是。C.3 为实测通过的最小步骤（含 Windows 写法） |
| 是否明确哪些内容无法验证？ | 是。Docker/Helm/Render 未执行；作者记录的浏览器验收未复现；键盘与减少动效未实测；归档验收 sidecar 缺失 |
| 是否避免编造？ | 是。所有计数与输出摘要均来自本次命令结果；未执行项显式标注 [未执行] |

