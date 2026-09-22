# BidProof 前端重构改进文档（来自 Opus 5 会话阅读）

- **来源会话**：`09/14 01:53 代码重构与优化`（mana-x.aizex.net / 会话 ID `d9080098-b787-402b-932b-8958d4c9374f`）
- **阅读方式**：已登录浏览器内提取可见内容（非 zip 下载）
- **阅读范围**：页面内 **220 个代码块**（约 **50 万字符**）、**42k 字符**对话正文、**88 段**可识别源码
- **生成日期**：2026-09-14
- **用途**：供 Cursor / 本地仓库按「绞杀者重构」方案继续落地，**不替代**逐文件 diff 合并

---

## 0. 阅读结论（先说清楚）

| 问题 | 结论 |
|------|------|
| 是否读完了页面上能看到的代码？ | **是**（220 块 pre/code + 正文叙述；含重复块） |
| 是否拿到了完整可运行仓库？ | **否**。batch4–7 的 zip 已 404/过期；Opus 容器也已重置 |
| 能否原样打包上传？ | **不能**。只能基于页面文本做**结构化改进文档 + 局部源码摘录** |
| 与当前 `c:\BidProof` 关系？ | 仓库仍是**旧单体**（`frontend/src/app.js` ~1538 行）；会话产出是**并行重构线**，尚未合并 |

**建议**：把本文当作「架构与批次说明书」，在 Cursor 里按批次 cherry-pick 实现；每批跑 `npm run verify`（会话中定义）+ 现有 `pytest` UI 契约。

---

## 1. 会话任务与约束（用户原始意图）

用户上传 `fc340f0f-6532-4f96-a325-95075ba153e3.zip`（即 BidProof 前端包），要求 Opus 5 以「宽松重构门禁」做**高质量前端重构**：

- **允许**：目录调整、设计系统、状态/API 分层、样式重写、依赖升级（需说明）
- **禁止**：改 API 路径/字段语义、改鉴权/MFA 流程、硬编码密钥、删合规/埋点/i18n
- **策略**：**Strangler Fig**——新模块与旧 `app.js` 并存，按视图搬迁，每批结束可构建可运行
- **用户后期指令**：「你别修，先往前推，报错了我让 cursor 去修」→ 偏速度，遗留项交给 Cursor

---

## 2. 目标架构（会话最终形态，batch 7 止）

```
frontend/
├── preview/index.html              # 设计系统预览（无构建）
├── scripts/
│   ├── build-css.mjs               # 合并 styles → static/style.css
│   └── verify 相关脚本              # node --check / CSS token 校验
├── types/api.d.ts 或 types/api.js   # 服务端契约（从旧 app.js 反推，非 OpenAPI）
├── src/
│   ├── main.js                     # 启动 core + router，再加载 app.js
│   ├── app.js                      # 旧单体，1650→1100 行（会话内计数）
│   ├── core/
│   │   ├── http.js                 # fetch 封装、CSRF、401 处理
│   │   ├── dom.js                  # el/bind/delegate/withLoading
│   │   ├── router.js               # 视图 enter/leave
│   │   ├── store.js                # 全局状态
│   │   ├── theme.js / icons.js     # 主题；lucide 内联 SVG（去 350k vendor）
│   │   ├── toast.js                # 可访问 toast（aria-live）
│   │   └── format.js               # 枚举→中文、日期
│   ├── api/
│   │   ├── paths.js                # 41 个 API 路径唯一来源
│   │   ├── runs.js / jobs.js / auth.js / workspace.js
│   │   └── index.js                # 特性层统一出口
│   ├── ui/render.js                # html 模板 + mount + 空/错/骨架态
│   ├── i18n/index.js
│   ├── features/
│   │   ├── runs/
│   │   │   ├── list.js             # 任务列表（batch 5 接线）
│   │   │   ├── matrix.js           # 要求项矩阵 + 高风险卡片
│   │   │   ├── decision.js         # 人工决策
│   │   │   └── collab.js           # 评论/审计/整改
│   │   ├── jobs/index.js           # 扫描作业页 + 活跃轮询
│   │   └── scan/watcher.js         # 后台扫描监视器（取代全屏遮罩）
│   └── styles/
│       ├── tokens.css / base.css / layout.css / components.css
│       ├── views/{runs,detail,jobs,collab}.css
│       ├── legacy.css              # 未迁移视图过渡（~59 kB）
│       └── index.css               # @layer 顺序入口
├── MIGRATION.md
└── static/index.html               # 壳层逐批替换 #home-view 等段落
```

**CSS 层级（根因修复）**：`reset → base → layout → components → views → utilities`，消除旧 `style.css` 中 **16 处 `!important`** 的层间打架。

**构建变化**：

- `npm run build:css` → 输出 `static/style.css`（会话内 ~146 kB 含 legacy；删 legacy 后目标 ~70 kB）
- `npm run build:js` → 仍产出 `static/app.js`（Vite IIFE 或 main+app 入口，以 MIGRATION 为准）
- dev 依赖新增：`typescript`（checkJs strict）、`eslint@9`；**运行时依赖仍为 0**

---

## 3. 批次进度与 `app.js` 瘦身（会话内数据）

| 批次 | 主题 | app.js 行数（会话） | 关键交付 |
|------|------|---------------------|----------|
| 1–3 | 扫描、诊断、基础设施 | 1650 基线 | core/api/types/styles 骨架、MIGRATION.md |
| 4 | API 层 + 设计系统 | ~1461 | paths/runs/jobs/auth/workspace、tokens/layout/components |
| 5 | 任务列表 + 矩阵 | ~1319 | `list.js` 接线、`matrix.js`、`views/runs.css` / `detail.css` |
| 6 | 扫描作业 + 后台化 | 1222 | `jobs/index.js`、`scan/watcher.js`、去全屏遮罩 |
| 7 | 决策 + 协作区 | **1100** | `decision.js`、`collab.js`、`views/collab.css` |
| 8（计划未做） | 管理/鉴权/弹窗 | — | 容器重置，需 zip 或本文档续做 |

**累计**：`app.js` 从 1650 行降 **33%**（会话自述）；顶层裸 `querySelector().addEventListener` 从 40→**33** 条，且均指向仍存在的 id。

---

## 4. 已搬迁模块的行为改进（应保留）

### 4.1 任务列表 `features/runs/list.js`

- 导出 `mountRunsView` / `unmountRunsView` / `ensureFilterOptions`
- 路由 `enter` 拉筛选选项，`leave` 卸载监听，避免双重绑定
- `loadAccuracy()`：当 `review_population_complete === false` 时**降级展示** precision/recall（合规要求，不得伪装成已验证指标）
- 修复：`loadProjects()` 判空；示例试跑与列表用**事件解耦**

### 4.2 要求项矩阵 `features/runs/matrix.js`

- 产品核心 UI：招标要求 ↔ 企业证据并排、高风险优先
- 修复：**复核请求漏传 `revision`**（会导致静默覆盖）
- 修复：**准确率反馈 body 少四个字段**
- UX：复核后**保留展开状态与滚动位置**；`UNKNOWN/NEEDS_REVIEW` 视觉降级（诚实性）

### 4.3 后台扫描 `features/scan/watcher.js` + 作业页 `features/jobs/index.js`

- **⚠ 需产品确认**：取消 `waitForJob()` **全屏遮罩 + 30 分钟 EventSource 阻塞**
- 改为：提交后**后台监视器 + 停靠区**，用户可继续浏览其他任务
- 作业页：有活跃 job 时**自动轮询**（旧版只拉一次）
- 待 Cursor 修：`app.js:481` **`loading-overlay` 死引用**（会话留给 Cursor）

### 4.4 人工决策 `features/runs/decision.js`

- `<select multiple>` → **复选框列表** `.ack-list`（防误触、触屏/读屏友好）
- **STOP（停止投标）二次确认**
- 保存后**留本页 + 成功反馈**，不强制跳回详情
- 错误：`<span>` → **callout + focus 管理**
- 默认决策 **HOLD**（非 CONTINUE）

### 4.5 协作区 `features/runs/collab.js`

- 拆开 `Promise.all`：评论 / 审计 / 整改**三条独立链路**（修审计面板永久骨架 bug）
- 审计：`user_id` → **用户名映射**；时间线样式
- 整改：状态下拉**委托绑定**；保存失败**还原下拉**；关联要求仅列**非 PASS**

### 4.6 API 层 `api/paths.js` 等

- **41 个路径集中定义**；旧代码 **3 处漏 `encodeURIComponent`** 已修
- 鉴权：`credentials: 'same-origin'`、`X-CSRF-Token`、401 非 auth 路径触发重新登录
- **决策枚举固定**：`CONTINUE | HOLD | STOP`（不是 GO/NO_GO）
- **异步不对称保留**：新建扫描 `POST /api/jobs` vs 重扫 `POST /api/runs/{id}/rescan`

---

## 5. 样式与设计系统要点

- **tokens.css**：颜色、间距、字体、圆角、阴影；深浅色 `[data-theme]`
- **移除** `static/vendor/lucide.min.js`（~350 kB）→ `core/icons.js` 内联 61 个 SVG，`data-lucide` 不变
- **preview/index.html**：不构建即可验收组件四态（空/加载/错/内容）
- **批次 7 返工**：曾误用不存在的 `--focus-ring`、`--leading-normal` → 改为 `--brand`、`--leading-body`；每批跑 **undefined CSS vars** 脚本
- **landing.css** 与工作台 token 重复——会话标记为 P2，未合并

---

## 6. 与当前 BidProof 仓库的差异（Cursor 合并前必读）

| 项 | 当前仓库 `c:\BidProof` | 会话重构线 |
|----|------------------------|------------|
| `frontend/src/app.js` | ~1538 行单体 | 目标 ~1100 行 + features |
| 目录 | `src/{app,state,escape,i18n}.js` | `core/` `api/` `features/` `styles/` |
| 样式 | `static/style.css` 单文件 ~60 kB | 分层 CSS + build-css.mjs + legacy |
| 构建 | `vite build` → `static/app.js` | `main.js` + verify 脚本链 |
| 测试 | `tests/test_ui_product_contract.py` 约束 `#home-view` 等 | **批次 5 要求替换 `#home-view` DOM**——合并前必须跑契约测试或分阶段保留旧 landmark |
| UI 回退历史 | 曾回退 patch-002 布局 | 会话**也**改 `#home-view`——与产品「4516b3f 网格对齐」可能冲突，需**产品择一** |

**硬约束（仓库 AGENTS.md）**：不得破坏 `#overview-grid`、`#nav-new-scan`、`#new-scan-button`、`.task-filter-bar` 等契约 landmark；任何 `#home-view` 替换须同步改测试或保留 id。

---

## 7. 建议落地路线（给 Cursor，按优先级）

### P0 — 基础设施（1–2 天）

1. 新建 `frontend/src/core/`、`api/`、`ui/`、`scripts/build-css.mjs`（可先不删旧代码）
2. 引入 `api/paths.js`，把现有 `app.js` 内 URL **机械搬迁**，跑 diff 确保字符串一致
3. 增加 `npm run verify`：`node --check` 全 src + CSS brace/token 校验（脚本见会话 bash 块）
4. **备份** `static/index.html`、`static/style.css`

### P1 — 已验证价值的视图（3–5 天）

5. 搬迁 `matrix.js` + 修 revision / accuracy body（**直接影响双页码复核正确性**）
6. 搬迁 `decision.js` + `collab.js`（人工决策链、审计 bug）
7. 搬迁 `scan/watcher.js` + `jobs/index.js`——**先与产品确认**是否接受取消全屏遮罩

### P2 — 列表与设计系统（需 UI 契约评审）

8. `list.js` 接线 + `#home-view` 替换——**必须**与 `test_scan_tasks_home_keeps_aligned_workbench_landmarks` 对齐
9. `tokens.css` + 分层样式；legacy.css 保留至 admin/auth 迁完
10. lucide 内联化（减 350 kB）

### P3 — 未完成（会话 batch 8）

11. **管理页**：成员、项目、留存、备份、工作区设置（破坏性操作需单独确认 UX）
12. **鉴权页**、**扫描弹窗**、详情元数据/版本 diff
13. 删 `legacy.css`，CSS 收到 ~70 kB

---

## 8. 验证清单（会话 + 仓库合并）

```bash
cd frontend
npm install
npm run check          # tsc checkJs，0 error
node scripts/build-css.mjs
npm run build          # 或现有 vite build
node --check src/**/*.js

# 仓库现有
cd ..
uv run --group dev pytest tests/test_ui_product_contract.py -q
uv run --group dev pytest tests/test_mobile_layout.py -q
```

**手工**：

- [ ] 新建扫描 → 后台监视器可见，**不**锁全屏（若采用 watcher）
- [ ] 矩阵复核带 `revision`，刷新后不丢
- [ ] 决策页 STOP 二次确认；未解决项用 checkbox
- [ ] 协作区：故意让审计 API 失败，评论/整改仍可用
- [ ] PASS 仍仅双页码（后端契约未改）
- [ ] `review_population_complete=false` 时准确率文案降级

---

## 9. 会话中明确留给 Cursor 的已知项

| 项 | 说明 |
|----|------|
| `loading-overlay` 死引用 | app.js ~481，batch 6 备注 |
| CSS token 幻觉 | 写样式时只引用 `tokens.css` 已定义变量 |
| `types/api` 带 `[假设]` 字段 | 需与后端 schema 对表 |
| batch zip 过期 | 不能依赖 download 链接；以本文 + 页面摘录为准 |
| Opus 容器重置 | batch 8 未开始；管理页需从零按 MIGRATION 续写 |

---

## 10. 附录 A — 页面可见文件清单（去重路径）

**outputs**

- `MIGRATION.md`
- `design-system-preview.html`
- `bidproof-refactor-batch4.zip` … `batch7.zip`（**链接已失效**）

**frontend/src（会话内完整或片段）**

- `core/http.js`, `dom.js`, `router.js`, `store.js`, `toast.js`, `format.js`, `icons.js`
- `api/paths.js`, `runs.js`, `jobs.js`, `auth.js`, `workspace.js`, `index.js`
- `types/api.d.ts` 或 `types/api.js`
- `ui/render.js`
- `features/runs/list.js`, `matrix.js`, `decision.js`, `collab.js`
- `features/jobs/index.js`
- `features/scan/watcher.js`
- `styles/tokens.css`, `base.css`, `layout.css`, `components.css`, `legacy.css`, `index.css`
- `styles/views/runs.css`, `detail.css`, `jobs.css`, `collab.css`
- `scripts/build-css.mjs`
- `preview/index.html`
- `main.js`, `app.js`（缩减版）

**static**

- `index.html`（含新 `#home-view` 片段，与现仓库可能冲突）

---

## 11. 附录 B — 局部源码摘录位置

以下文件为从页面提取的原文片段（供 diff 参考，**非完整仓库**）：

- `outputs/_mana_extract_migration.txt` — MIGRATION.md 早期版
- `outputs/_mana_extract_paths.txt` — API paths 模块
- `outputs/_mana_extract_listView.txt` — 任务列表视图
- `outputs/_mana_extract_matrix.txt` — 矩阵视图
- `outputs/_mana_extract_watcher.txt` — 后台扫描监视器
- `outputs/_mana_extract_decision.txt` — 决策页（页面截断，非全文）
- `outputs/_mana_extract_collab.txt` — 协作区（较完整）

---

## 12. 是否继续让 Opus 5 推进？

**不建议**在 zip 过期、容器重置的情况下让 Opus 从对话文本「还原」全库——误差大、与 Cursor 本地仓库易冲突。

**建议分工**：

- **Opus 5**：继续出 **batch 8 设计说明**（管理页确认流、auth 状态机对照表）或审查 `MIGRATION.md`
- **Cursor（本仓库）**：按本文 §7 在 `c:\BidProof` 分批实现，每批 pytest + verify

若需 Opus 续写，请重新上传 **batch7 完整 zip** 或 Cursor 合并后的 `frontend/` 快照。

---

*文档结束。阅读覆盖：mana-x 会话页全部可见 pre/code 块与正文；不含已过期二进制 zip 内容。*
