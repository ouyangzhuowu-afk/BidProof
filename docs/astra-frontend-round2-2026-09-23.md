# GPT-6 Astra 前端第二轮：合并与上线记录（2026-09-23）

## 结论

GPT-6 Astra 的第二轮前端交付包已合并进 `main`，并部署到 `bidproof.marketcase.net` 的 `/`（落地页）与 `/app`（审查工作台）。C-022 的回退结果没有被推翻：该包的 `static/index.html` 差异只落在详情视图与上传表单，扫描任务页布局未改动（见下"C-022 核对"）。

## 来源与基线

| 项 | 值 |
|----|----|
| 交付包 | `BidProof-frontend-redesign-round2-20260923.zip`（第一轮 `BidProof-frontend-redesign-20260922.zip` 已累积在内） |
| 包内清单 | `outputs/ui-redesign-round2/change-manifest.json`（41 条，含 sha256） |
| 包的分叉点 | `e484a2f`（已包含 C-022 回退 `0de693d`） |
| 合并时的仓库 HEAD | `f5b7154` |
| 合并方式 | 按分叉点逐文件三方比对，取包内改动，保留仓库后续更新 |

## 合并范围

取包内版本（24 项）：`app/api/runs.py`、`app/services/scan_service.py`、`frontend/` 17 项、`static/` 4 项（app.js / app.js.map / index.html / style.css）、`tests/` 3 项。

新增（39 项）：`app/services/document_service.py`、`docs/` 3 篇、`frontend/scripts/` 8 个（含 `stamp-assets.mjs` 与 7 个 DOM 测试）、`frontend/src/` 7 个新模块与视图样式、`outputs/ui-redesign{,-round2}/` 交付证据、`scripts/seed-ui-review.py`、`tests/` 2 个、`START-HERE.md`。

保留仓库版本，不取包内旧版：`.gitignore`、`README.md`、`AGENTS.md`、`docs/README.md`、`docs/archive/*`、`OPUS5_MIGRATION_REPORT.md`（已在 `docs/archive/`）、`work/`。

明确不落地：包内的 `work/restore-drill-20260827/uploads/` 真实客户材料副本。0a25f97 已把它们移出当前分支，本次不回填。

`workflow/project-state.json` 未整体覆盖，改为手工合并：新增 `D-ASTRA-MERGE-2026-09-23`、把 `Q-HANDOVER-1` 置为 `resolved`、更新 `next_best_action.note` 与 `updated_at`。

## 新功能与行为变化

- 新增 `GET /api/runs/{run_id}/files/{source_id}/pages/{page_number}`：双向原文对照所需的原页预览，需 `EVIDENCE_DOWNLOAD` 权限，返回 `image/png` 且 `Cache-Control: private, no-store`；用 PyMuPDF 渲染，最长边上限 2000 px，非 PDF、加密、越界页码分别返回 415 / 422 / 404。
- 上传落盘从"用户文件名"改为"来源身份命名"（`tender-<name>`、`evidence-<NNN>-<name>`），修复同名原件互相覆盖；本地实测来源 ID 为 `TENDER-001`。
- 详情视图改为审查工作台：连续核验导航、人工状态筛选、双向 PDF 原页翻阅、证据切换、上传状态反馈。

## C-022 核对

C-022 记录的是"工作台补丁 002 打乱扫描任务页对齐、已回退到 `4516b3f` 布局"。逐行比对包内 `static/index.html` 与仓库版本，差异仅出现在：

```
@@ -8,6   head 内 style.css 的 ?v= 戳
@@ -432   详情视图（#detail-view）整体结构
@@ -486   详情视图内的证据对照与折叠区块
@@ -590   新建扫描表单（#scan-form）
@@ -739   app.js 的 ?v= 戳
```

扫描任务列表页（`#home-view` 区域）不在差异范围内，因此本次合并保留 C-022 的回退结果。交接分析文档中"与 C-022 冲突"的提示按此证据收束为"不冲突"。

## 验证证据（2026-09-23，本机 Windows / Python 3.13 / Node v26.4.0）

| 项 | 命令 | 结果 |
|----|------|------|
| 控制面 | `uv run python -m app.workflow check` | PASS：Project-025 workflow state is valid |
| 包内一致性 | 按 `change-manifest.json` 校验 sha256 | 41 条中 40 条逐字节一致；唯一差异为手工合并的 `workflow/project-state.json` |
| 后端回归 | `uv run --group dev pytest -q` | 315 passed, 11 skipped, 1 error |
| 前端类型 | `npm run check --prefix frontend` | 通过（tsc --noEmit，无输出） |
| 前端 lint | `npm run lint --prefix frontend` | 0 error, 2 warning（既存） |
| 前端行为 | 7 个 `frontend/scripts/test-*.mjs`（jsdom 30.1.1 外置于产品依赖） | 89 passed / 0 failed |
| 构建一致性 | `npm run build --prefix frontend` | `static/app.js` 与包内产物逐字节一致；`style.css`/`app.js.map`/`index.html` 仅差 Windows 反斜杠注释与随之变化的 `?v=` 戳 |
| 端到端 | `scripts/seed-ui-review.py` + uvicorn + 真实 HTTP | `/healthz` `/` `/app` `/static/app.js` 均 200；登录带 CSRF；run 详情 2 份来源 / 9 条要求；`pages/1` → 200，44 119 B，PNG 魔数正确；`pages/9999` → 404 |

`pytest` 的 1 个 error 是 Windows 专有的 teardown 现象：`tests/test_source_page_preview.py` 结束时 PyMuPDF 仍持有临时 PDF 句柄，临时目录清理报 `WinError 32`；测试本身通过，Linux 运行不出现（CI 是 Linux）。包作者在 macOS 上的记录为 314 passed / 12 skipped，与本次差 1 项来自仓库新增的 `test_pymupdf4llm_extraction.py`。

`ruff check app tests` 全仓仍有 140 项既存告警（包内基线 141、改动文件本身干净），本次合并未新增。

## 上线

推送 `main` 后由 Render（`render.yaml`，docker runtime，自定义域 `bidproof.marketcase.net`）自动部署；容器直接托管 `static/`，因此提交的构建产物即线上产物。验收方式：比对线上 `/static/app.js`、`/static/index.html` 与 `HEAD` 的 blob 是否逐字节一致，并确认 `/app` 出现 `review-workbench`、`evidence-reader` 结构。

## 未决与风险

- 构建产物跨平台漂移未根治：本机 Windows 执行 `npm run build` 会产生反斜杠注释与新的 `?v=` 戳，CI（Linux）比对为绿，本地比对会红。提交产物必须保持 Linux 一致。
- `frontend/scripts/test-*.mjs` 仍不在 `package.json` scripts 中，jsdom 需外部提供；未纳入 CI 门禁。
- 交接分析列出的 `paths.js` 未登记新原页接口、双 store 并存、`/api/evidence` 与 `/api/audit/chain` 无前端入口等问题仍未处理。
- 本轮仍属 UI 与工程改动，不构成业务验收：`pilot-ledger.csv` / `icp-outreach.csv` 保持空置，不得写入示例数据。
