# BidProof 前端审查工作台改造记录

第一版记录日期：2026-09-22。本文保留第一版的设计依据、实现范围与当时验证结果；当时的浏览器阻塞、测试数量和 Token 实施状态不代表当前交付。第二轮修复、浏览器记录与最新测试结果见 [第二轮交付记录](ui-hardening-round2-2026-09-22.md)。

## 范围与基线

本轮针对 `detail-view`、上传反馈与全局视觉 Token 改造。源码来自用户提供的本地仓库副本；桌面 `BidProof-main` 保留为只读基线，实际修改位于当前工作区 `BidProof/`。没有向公网部署，也没有将演示扫描写入真实试点台账。

已读取 `AGENTS.md`、`workflow/project-state.json`、`workflow/master-brief.md`、`workflow/agent-operating-instructions.md`、`workflow/roadmap.md`。本轮工程工作由用户明确授权；`T-005` 真实企业试运行与 OCR 质量门槛仍保持原有未完成状态。视觉改造不能证明抽取质量、投标结果或业务验收。

本轮基线观察来自源码，尚不能替代浏览器视觉实测：

| 位置 | 已确认基线行为 | 改造目的 |
| --- | --- | --- |
| `frontend/src/app.js` 的 `renderDetail()` | 顶部四张平级指标卡；“致命风险”直接使用 `blocker_count`；没有人工逐项复核进度 | 主结论优先，计数文案与后端口径一致，单独展示人工进度 |
| `static/index.html` 的 `detail-view` | 页头六个平级操作；原始文件区、审计、协作、整改与要求矩阵分散 | 缩短进入逐项核验的路径，次要管理信息折叠 |
| `frontend/src/features/runs/matrix.js` | 高风险最多四张；普通要求用 `details`；有双侧文字引文，但无持续原页阅读区 | 高风险优先，同时提供持续的招标 / 企业证据阅读 |
| 同上 `footer()` / `review()` | `CONFIRM`、`REJECT` 等动作直接提交；未提交 `new_status`；没有条款内备注 | “确认通过”与真实请求一致，保存后状态、统计与留痕同步 |
| `frontend/src/styles/tokens.css` | 八档字号，引用使用等宽字体；卡片不使用柔和阴影 | 收敛到四档字号，中文正文与引文更易读，边界轻而清晰 |
| `frontend/src/styles/layout.css` | 新样式以 `.shell` 为作用域，真实页面仍有 `.app-shell` 与 legacy 样式 | 避免重复发生整页替换后的壳层布局回归 |
| `frontend/src/state.js`、`core/store.js` | 详情入口使用旧状态对象，矩阵使用可订阅状态容器 | 处理成功后必须同步同一个任务快照，避免顶部与卡片不一致 |
| 上传拖拽事件 | 把拖入文件赋给 input；未见完整文件级可读反馈 | 招标与企业文件分区、已选文件可见、解析状态明确 |

## 已核实的后端契约

以下以 `app/presenters.py`、`app/services/run_service.py`、`app/schemas.py` 为准，不能仅凭按钮名称推断：

| 输入 / 字段 | 实际含义 | 界面约束 |
| --- | --- | --- |
| `CONFIRM`，无 `new_status` | 原状态是 `PASS` / `FAIL` 时保留；其余状态变为 `NEEDS_REVIEW` | 不能把这种请求反馈为“已通过” |
| `CONFIRM` + `new_status: PASS`，或 `decision: PASS` | 请求转为通过；后端仍检查双向引用 | “确认无误通过”必须显式请求 PASS，并等待服务端成功 |
| `REJECT` | 转为 `NEEDS_REVIEW` | 驳回仍是未解决风险，不能降低风险计数 |
| `REQUEST_EVIDENCE` | 转为 `UNKNOWN` | 请求材料不是通过，也不是人工已解决 |
| PASS 双引用门槛 | 招标 `locator.label` + `quote`，以及至少一份企业证据的 `locator.label` + `quote` | 来源不完整时禁用通过；422 失败不得乐观更新 |
| `review.items` | 追加人工复核事件，包含旧 / 新状态、备注与时间 | 按条款去重计算进度，不按事件条数计数 |
| `revision` | 乐观并发版本 | 每次提交携带当前版本；409 后重新获取最新状态，不能静默覆盖 |
| `blocker_count` | FATAL 或 QUALIFICATION 且状态为 FAIL / UNKNOWN / NEEDS_REVIEW | 名称需包含废标 / 资格风险，不能当成仅 FATAL 数量 |
| `fatal_risk_count` | 所有 FATAL 类别条款数量，包含 PASS | 不能直接当作“未解决废标风险” |
| `unresolved_count` | 所有 UNKNOWN / NEEDS_REVIEW，不含 FAIL | 不能把它单独作为全部风险数量 |
| `accuracy-review-complete` | 全文漏项复核口径，决定准确率数据是否完整 | 保留人工勾选；不能随卡片处理进度自动置真 |

原始系统判定与人工操作不能被“安心”文案混淆。人工进度达到 100% 仍可能有 FAIL 或驳回项；“已处理”不等于“风险解除”。对风险项的通用处置建议继续标明来源是类别规则，不冒充逐文档分析。

## 页面结构与视觉方案

页面阅读顺序为：项目标题 → 一个主结论 → 未解除 FATAL 废标风险与待复核计数 → 人工进度 → 高风险凭证 → 普通条款。证据阅读区保留当前条款上下文；协作、整改与审计记录作为次要区域可展开。

```html
<section id="detail-view" aria-labelledby="detail-title">
  <header class="detail-header"><h1 id="detail-title">项目标题</h1></header>
  <section aria-label="本轮审查概况">
    <!-- 一个主结论、风险数量、明确口径的人工进度 -->
  </section>
  <div class="detail-workspace">
    <div class="review-stream">
      <section aria-labelledby="priority-title">
        <h2 id="priority-title">优先核验</h2>
        <div id="risk-list"><!-- 独立审查凭证卡 --></div>
      </section>
      <section aria-labelledby="matrix-title">
        <h2 id="matrix-title">逐项核验</h2>
        <div id="requirements"><!-- 普通条款紧凑列表 --></div>
      </section>
    </div>
    <aside aria-label="招标与企业证据原文对照">
      <!-- 当前条款、来源入口、真实原页 / 明确标注的文字摘录 -->
    </aside>
  </div>
  <details><summary>协作与审计</summary><!-- 原有管理功能 --></details>
</section>
```

此片段表达语义关系，不替代实际页面 DOM。真实实现需保留原有事件依赖的 ID，并用构建后的 `static/app.js`、`static/style.css` 验收。

视觉使用冷灰底、白色表面、深青主动作、低饱和风险色。字号收敛至 20 / 16 / 14 / 12 px；使用 4 px 间距基准，正文行高约 1.5–1.6。引用区采用微灰底和有限关键词高亮；无依据的强调不可被解释为已核实结论。宽屏持续对照，窄屏改为上下排列，核心动作不能因适配被隐藏。

## 处理状态与阅读反馈

| 场景 | 行为与统计 |
| --- | --- |
| 确认无误通过 | 校验引用 → 提交显式 PASS → 使用服务端回包 → 更新卡片及统计 → 给出保存成功反馈并收起卡片 |
| 存疑驳回 | 必填原因；服务端回包为 NEEDS_REVIEW；仍留在风险列表 |
| 人工备注 | 条款关联备注走 comments API，保留条款编号；不改变判定、不计入人工核销进度 |
| 修正已核销项 | 在逐项核验中重新展开，通过存疑驳回重新进入复核；追加审计事件，不删除原记录。本轮未增加一键撤销功能 |
| 缺页码 / 缺引文 | 明确显示缺失内容；不伪造页码，禁用确认通过；保留补材料路径 |
| 非 PDF 原文 | 明确标注文字摘录，保留原文件下载；不伪装成已渲染原页 |
| 原页加载中 / 失败 | 区域内加载反馈；失败说明并保留下载入口；不展示上一条原文冒充当前证据 |
| 保存失败 / 冲突 | 保留输入和当前操作上下文；不把未保存动作显示为成功；冲突后按最新版本重试 |
| 解析中 | 上传 / 解析阶段与人工进度分开；未知总量用不定进度，不显示零风险结论 |
| 解析失败 / 局部缺失 | 明确标注范围不完整；保留可用文件与重试入口，不宣布本轮审查完成 |

状态切换使用短暂色彩反馈与收起效果；遵守 `prefers-reduced-motion`。收起当前卡片时焦点应进入稳定可见控件。缺失状态、危险等级和成功反馈均以文字表达，不能只靠颜色。

## 原页接口

新增 `GET /api/runs/{run_id}/files/{source_id}/pages/{page_number}`，供同源 `<img>` 加载真实 PDF 原页。

- 鉴权与原文件下载一致：`EVIDENCE_DOWNLOAD` + 工作区 / 项目可见性检查。
- 复用 `run_service.source_file()` 的来源 ID 与任务目录限制；不接受调用方提供任意路径。
- 页码从 1 开始，并以实际 PDF 页数校验，不能依赖提取元数据中的页数。
- 仅支持 PDF；非 PDF 返回 415，超界返回 404，非法页码 / 加密或损坏文件返回 422。
- 通过 PyMuPDF 渲染 RGB PNG，最大边长 2000 px；调用方不能请求任意分辨率。响应为 `private, no-store`。
- 保持现有 CSP 与会话鉴权，不加入 `blob:`、远程预览服务或公共文件地址。

实现：`app/api/runs.py`、`app/services/document_service.py`。专项测试：`tests/test_source_page_preview.py`。它只证明原页读取链路；不会将 OCR 摘录自动升级为合规结论。

## SafeHtml 与可访问性要求

现有 `frontend/src/ui/render.js` 已提供 `html` / `mount` 的 SafeHtml 契约。新增项目名、条款、页码标签、文件名、备注和错误信息均走转义模板或 `textContent`；不得把来源文字传入 `raw()`。高亮需组合安全文本片段，不直接对未转义原文替换 HTML。

URL 由受控路径及 `encodeURIComponent()` 构造。文字转义不能替代协议校验。原页来自受保护的同源 PNG 端点；前端应处理未授权、失效文件、错误页码和加载失败。

使用原生按钮、表单、`details`；上传同时提供文件选择入口。焦点清晰、按钮有可读名称。若采用 tabs，需完整实现键盘和 ARIA 关联；简单筛选按钮应使用组语义及 `aria-pressed`。核销结果通过温和的 live region 通知，避免连续播报所有统计变化。

## 验收记录

| 验收项 | 当前状态 / 应保留的证据 |
| --- | --- |
| Workflow 状态检查 | 已由主执行代理使用 Python 运行通过；不修改 T-005 业务结果 |
| 原页 API：真实 PNG、实际第 2 页、2000 px 限制 | 通过；验证第 1 / 2 页实际红 / 蓝像素与大幅面缩放后的尺寸 |
| 原页 API：未登录、VIEWER、跨工作区、目录越界 | 通过；分别验证 401 / 403 / 404 与存储路径越界拒绝 |
| 原页 API：非法页码、非 PDF、损坏文件 | 通过；验证 0、负数、非数字、超界页、415 与损坏文件 422 |
| 前端构建、lint、类型检查 | build / check 通过；ESLint 0 errors、4 个原有 warnings |
| SafeHtml 与新增交互行为验证 | 14 项纯逻辑测试通过；恶意文本、高亮、伪造 SafeHtml 对象、状态同步与文件预检均覆盖 |
| CONFIRM / REJECT / 备注与统计一致 | 13 项 DOM 行为 + 4 项完整 app 入口测试通过；本机 HTTP 联调验证显式 PASS、驳回、备注不改状态、缺引用 422、旧版本 409 |
| 桌面、平板、手机布局及文字溢出 | 未完成：Browser 在 GitHub 和 localhost 均因管理员策略检查不可用而拒绝访问；未采用替代浏览器绕过 |
| 键盘、减少动画、原页加载失败 | DOM 已验焦点/原页错误回退，CSS 提供 reduced-motion；真实浏览器键盘与动效仍待实测 |
| 后端与既有页面契约回归 | 完整 pytest：310 passed、12 skipped。跳过项涉及缺少真实文件、PostgreSQL 等本地条件，不计为通过 |

本表记录本轮实际运行结果；未执行的检查保留为未验证。

原页专项运行命令：`.venv/bin/python -m pytest -q tests/test_source_page_preview.py tests/test_enterprise_workflow_gaps.py::test_run_source_files_are_downloadable_only_with_workspace_scope`。结果：**9 passed**（8 个新用例，加既有下载权限回归 1 个）；仅有依赖弃用警告。

## 工程联调修正与可追溯边界

- `state.js` 为 currentRun/currentUser 建立与 `core/store.js` 的兼容访问器，避免旧详情入口与新矩阵读不同状态。
- 为迁移后的 router 注册现有视图入口；初始无 hash 的 `/app` 明确挂载首页事件，修复任务列表点击无响应。
- 风险排序先处理未通过 FATAL，再按其他条款类别与状态排序；PASS 项放在后面。
- SafeHtml 加入内部 WeakSet 能力标记和冻结对象。外部 JSON 即使携带 `__safe: true` 也不能伪造可信 HTML。未把用户文本传入 raw。
- 本轮没有添加一键撤销；已核销条款可重新展开并存疑驳回，服务端追加复核记录。
- 上传进度反映网络提交和后端解析；未宣称浏览器已做本地 PDF 解析。客户端没有服务端实际上限配置时，由既有后端校验大小。
- 原页加载不使用外部文档服务，文件与页码均经过原有权限和目录检查；没有放宽 CSP。

Python 静态检查：新增/修改原页接口文件通过 Ruff；整库 Ruff 仍有 140 个既有问题，基线为 141 个，集中在导入排序等旧代码。保留报告在 `outputs/ui-redesign/ruff-*.json`。未为前端改版批量改写无关 Python 文件。ESLint 的 4 个警告同样来自原有构建/请求/列表代码。

演示材料由 `scripts/seed-ui-review.py` 生成，明确标记为界面验收示例。数据位于隔离的本机目录，没有写入 pilot/ICP 台账。真实 HTTP 验收结果见 `outputs/ui-redesign/http-smoke.json`。

## 本机查看

当前预览：`http://127.0.0.1:8768/app`。示例账号 `ui-review`，密码 `LocalReview2026!`，仅用于这份隔离本机演示。打开后进入“政务协同平台建设项目_示例招标.pdf”。

源码工作目录为当前交付的 `BidProof/`；原始下载目录 `/Users/g71/Desktop/bid/BidProof-main` 未覆盖。没有推送 GitHub 或部署公网。

复现构建：进入项目根目录，使用 Node.js 22+ 执行 `npm ci --prefix frontend` 后 `npm run build --prefix frontend`。服务依赖与演示客户端安装、数据库隔离变量及完整启动顺序见 `START-HERE.md`。生成示例时需要额外的 `httpx2>=2.12`；命令清空 `BIDPROOF_DATABASE_URL` / `DATABASE_URL`，避免已有连接配置覆盖本机示例目录。

测试命令：`node frontend/scripts/test-review-workbench.mjs`；DOM 测试可另行临时安装 jsdom，并设置 `JSDOM_MODULE` 到其 `lib/api.js` 后运行 `node frontend/scripts/test-workbench-dom.mjs` 及 `node frontend/scripts/test-app-smoke-dom.mjs`。jsdom 没有进入产品依赖；DOM 测试没有浏览器渲染能力，不能替代视觉验收。
