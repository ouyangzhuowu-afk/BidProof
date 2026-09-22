# BidProof 第二轮交付与验证记录

实施日期：2026-09-22 至 2026-09-23。交付包为 `BidProof-frontend-redesign-round2-20260923.zip`，首版 ZIP 保留用于对照。本轮在独立本地源码副本中完成阅读器、连续核验、上传与请求一致性修复，没有覆盖桌面原版、推送 GitHub 或部署公网。

前端 **83 个实质场景通过**，后端 **314 passed / 12 skipped**，构建与类型检查通过。浏览器已检查四档视口和浅色 / 深色主题，完成主要核验操作；下文分别记录工程证据、实际页面结果与未覆盖范围。生成示例不计入真实企业 pilot / ICP 台账，也不代表 OCR 质量或投标业务验收。

## 首版发现与第二轮处理

| 实际发现 | 第二轮处理 | 验证依据 |
| --- | --- | --- |
| 阅读器只能看引用页；多份证据同时生成许多原页图 | 原件内前后翻页、回引用页；证据选择器只加载选中一份 | 10 个阅读器 DOM 场景、原页 API 测试与真实 PDF 页面操作 |
| 优先区只显示少量风险；连续核验缺少明确入口 | 优先风险分批查看；全任务上一条 / 下一待办；人工状态筛选 | 11 个导航场景及浏览器核销、筛选操作 |
| 文件选择与提交期间的状态容易不一致 | 累加企业材料、同名提示、移除反馈、提交期间锁定并恢复控件 | 12 个上传 / 监视场景及原生 PDF 选择 |
| 同名文件或清理后同名文件可能写到相同路径 | 招标与每份企业证据分别命名内部路径，显示名称不变 | 4 个真实 API 回归，检查字节、SHA-256 和原页色块 |
| 旧任务慢请求可能覆盖新任务；离开详情后被旧回包拉回 | 取消旧读取并检查请求身份；异步数据限定当前任务 | app 入口回归覆盖先后返回、离开页面与加载状态 |
| 无效成功响应、较低版本回包、保存期间编辑可能造成误报或丢稿 | 无效 JSON 视为失败；较低 revision 不回退；备注保存锁定编辑器并按提交快照清草稿 | HTTP、导航与备注回归 |
| 首版 Token 说明与实际变量值不一致 | 按 Token 映射修正源码并重新构建，核对真实元素计算样式 | 浅 / 深色实际背景、品牌色、字号、行高、侧栏及按钮样式 |

首版存在“说明和部分注释已更新，实际变量值仍保留旧值”的实施遗漏。第二轮修正了实际定义，并验证生成 CSS 在浏览器中生效；这不是新的审美取舍，也不能用构建通过替代样式检查。

## 原文阅读：页码真实、上下文连续

实现位于 `frontend/src/features/runs/evidence-reader.js`，对应样式为 `frontend/src/styles/views/reader-navigation.css`。

- 招标与企业证据两侧分别提供“上一页 / 下一页 / 回到引用页”。翻动一侧不重新加载另一侧；当前条款重渲染及切换证据时保留各份证据的阅读位置，切换条款则从新条款的引用页开始。
- 当前浏览页与引用页分别显示。查看相邻页面时提示“上方摘录仍来自引用第 X 页”，避免把引用摘录误认作当前页内容。
- 总页数只读取 `source_documents[].pages` 中有效、且不与引用页冲突的记录，标注“文件记录共 N 页”。缺失时显示“总页数未记录”，记录小于引用页时显示冲突。PNG 接口没有 `page_count`；前端不会从引用页、摘录数量或图片加载失败推断总页数。
- 多份企业证据使用有标签的原生选择器，保留文件名与引用定位。最多同时生成招标原页与当前企业证据两张图；35 份证据的测试验证没有一次创建 35 张原页图。
- 图片加载提供可读状态与 `aria-busy`。失败时保留摘录、下载入口及重试按钮；旧图片延迟触发的事件不能覆盖新页面。图片失败不等同于已到最后一页。
- 非 PDF、无物理页码、无法唯一映射原件时继续显示摘录及明确说明，不编造原页位置。原页使用受原有鉴权保护的同源 PNG 接口，SafeHtml、CSP 和下载权限没有放宽。

## 审查导航：待办与人工核销分开

实现位于 `frontend/src/features/runs/matrix.js` 和 `review-model.js`。

- “待处理 / 已核销 / 全部”按人工核销语义筛选。机器 PASS 仍标为“系统已满足 · 待核销”；已驳回或证据不足的条款留在待处理。
- “已核销”要求当前条款为 PASS，且最新人工复核记录的新状态也为 PASS。顶部“人工已处理”记录处理覆盖率，可能包含驳回；它不等于“风险解除”或“已核销通过”。
- 优先风险按三项分批显示，附总量与前后批次入口；第四条以后的风险也有明确入口。
- “上一条 / 下一待办”面向全任务，必要时跨越每页 25 条的列表分页。若目标被筛选隐藏，会清除阻挡筛选并提示原因；随后展开目标卡片、定位原文并放置焦点。导航不会自动确认条款。
- 备注与驳回原因各自保留草稿。当前任务内切换条款、筛选、编辑模式或核销通过不会相互覆盖；草稿不是服务端自动保存，不承诺刷新或切换任务后仍存在。
- 保存备注期间，同一条款在优先卡片和普通列表中的两个编辑器都锁定。成功后只按提交快照清理草稿，失败保留内容；备注不改变判定，也不增加人工处理计数。
- 只读角色可以浏览和导航，不能取得可写核销控件。使用原生按钮的键盘语义，没有新增全局快捷键。

“确认无误通过”显式提交 `CONFIRM + new_status: PASS`，等待服务端成功后更新。缺少双向页码引用时不允许通过；驳回必填原因并保持 NEEDS_REVIEW；409 冲突后读取最新版本再由用户重试。界面没有把后端默认 CONFIRM 行为误当成 PASS。

## 上传与后台扫描

实现位于 `frontend/src/features/scan/intake.js`、`watcher.js`，由 `app.js` 调用。

- 招标保持单文件，企业材料支持多次选择累加。文件名、大小和修改时间一致的重复选择会去重；其他同名材料或招标 / 企业区域间重名会提示先改名，错误批次不覆盖之前有效选择。这是文件选择校验，不宣称逐字节内容比对。
- 移除文件后更新数量、容量和可读提示，并将焦点移到剩余移除按钮或文件选择控件。文件名仍作为文本渲染。
- 提交前重新检查原生文件输入。先生成 `FormData`，再锁定输入、选择框、备注、按钮和关闭入口，避免禁用控件导致上传内容遗漏。
- 请求结束后恢复各控件原先的禁用状态；失败保留已选文件。原生 required 校验也提供行内错误；未知服务端大小上限时不自设一个看似权威的限制。
- 收起后台扫描卡只隐藏界面，仍保留扫描监视；后续进度、成功或失败不会重建已收起卡片，完成与失败仍可提示。
- 骨架与进度描述网络提交和服务端解析，不宣称浏览器已完成本地 PDF 内容解析。

## 来源身份：防止同名原件相互覆盖

`app/services/scan_service.py` 的最终存储路径区分招标与每份企业证据：招标使用 `tender-清理后原名`，企业证据使用 `evidence-序号-清理后原名`。来源编号继续为 `TENDER-001`、`EVD-001`、`EVD-002` 等，元数据中的上传原名保持不变。

前端重名提示降低操作歧义，后端路径隔离保证其他客户端直接上传同名文件时仍不覆盖。`safe_filename()` 会移除路径部分并把连续两个点替换成下划线，不同原名也可能清理为同名；测试包含 `proof..copy.pdf` 与 `proof_copy.pdf` 的碰撞。

`tests/test_upload_source_identity.py` 通过真实同步上传和排队上传 API、真实 PDF 解析、下载与原页接口验证：

1. 三个来源分别保持自己的完整下载字节与 SHA-256。
2. `source_documents` 和 `evidence_assets` 中的原始文件名不被内部存储名替换。
3. 下载 PDF 中的来源编号分别正确；预览图中的红 / 绿 / 蓝色块分别来自各自原件。
4. 排队任务完成且暂存目录清理后，最终原件仍可正确下载和预览。

该修复保护新上传和新扫描。若旧任务原件此前已经被覆盖，升级源码不能恢复丢失字节，需要从保留原件重新上传。旧引用不能唯一映射文件时，阅读器继续显示歧义，不猜测某个同名文件。

## 请求竞态与错误处理

- `app.js` 为当前任务读取建立 `AbortController`，切换任务或离开页面时取消旧读取；即使传输在取消后仍返回，也只有当前请求身份可更新任务及加载遮罩。
- 异步负责人 / 复核人选项和版本差异回包检查当前任务及视图；较低 revision 回包不能把矩阵和当前任务状态退回旧版本。
- `core/http.js` 仅对读请求的网络错误及 502 / 503 / 504 进行重试。401、403、404、409、422 等错误明确返回；写请求不自动重放。
- HTTP 成功码不能掩盖无效 JSON：期待 JSON 的响应无法解析时按失败处理，不显示保存成功。
- 并发读取去重在成功和失败两条路径都清理，不再因忽略 `finally()` 产生额外未处理拒绝。兼容不支持 `AbortSignal.any` 的环境，并保留预先取消状态。
- 备注保存锁定两个编辑入口，以提交时的内容快照确定清稿范围，避免保存期间输入被成功回包抹掉。

## 工程验证与复现

最终前端回归共 **83 个实质场景**；Node 报告 **89 / 89**，其中 6 项为组织子测试的容器，未重复计入业务场景。最后的主题按钮文案、移动端新建按钮可访问名称和上传按钮样式修复后已复跑；320 px 溢出修复后重新构建通过。

机器可读的结果汇总见 [verification-summary.json](../outputs/ui-redesign-round2/verification-summary.json)。前端单元与 DOM 测试使用模拟 HTTP 响应；后端 API 测试和下节实际浏览器检查分别提供真实接口与页面证据。

| 检查 | 结果 | 主要覆盖 |
| --- | --- | --- |
| `test-review-workbench.mjs` | 14 个场景通过 | 风险 / 人工进度口径、引用门禁、SafeHtml |
| `test-http-reliability.mjs` | 17 个场景通过 | 读重试、取消、去重清理、写请求不重放、无效 JSON |
| `test-workbench-dom.mjs` | 13 个场景通过 | 确认、驳回、备注、缺引用、冲突与失败恢复 |
| `test-app-smoke-dom.mjs` | 6 个场景通过 | 入口、任务切换竞态、离开页面和状态同步 |
| `test-reader-navigation-dom.mjs` | 10 个场景通过 | 翻页 / 回引用、页数缺失与冲突、重试、多证据限量、旧图片事件 |
| `test-review-navigation-round2.mjs` | 11 个场景通过 | 人工筛选、分页待办、草稿、只读角色、版本回退和备注保存 |
| `test-intake-lifecycle-dom.mjs` | 12 个场景通过 | 文件累加 / 冲突、移除、提交锁定 / 恢复、扫描卡收起 |
| 后端完整 `pytest -q` | **314 passed / 12 skipped** | 原有后端回归，以及原页鉴权 / 页码 / 类型和文件身份测试 |
| `tests/test_upload_source_identity.py` | 4 passed，已计入 314 | 同步 / 排队 × 同名 / 清理后碰撞 |
| `npm run build` / `npm run check` | 通过 | 生成产物与类型检查 |
| `npm run lint` | 0 错误、2 个既存警告 | 前端源码与脚本静态检查 |

12 个跳过项不视作通过；完整测试计数不代表未提供的真实企业输入已验证。DOM 测试不执行浏览器排版，实际页面检查另列于下节。

在根目录按 [START-HERE](../START-HERE.md) 安装 Python 依赖后，可运行：

```sh
python -m pip install 'pytest>=8'
python -m pytest -q
```

前端测试使用独立临时安装的 **jsdom 29.1.1**，没有加入产品依赖。使用支持该版本的 Node.js（建议 24 或更新版本），在根目录执行：

```sh
BIDPROOF_UI_TEST_DEPS="$(mktemp -d /tmp/bidproof-ui-tests.XXXXXX)"
npm install --prefix "$BIDPROOF_UI_TEST_DEPS" --no-save --package-lock=false jsdom@29.1.1
export JSDOM_MODULE="$BIDPROOF_UI_TEST_DEPS/node_modules/jsdom/lib/api.js"

node frontend/scripts/test-review-workbench.mjs
node frontend/scripts/test-http-reliability.mjs
node frontend/scripts/test-workbench-dom.mjs
node frontend/scripts/test-app-smoke-dom.mjs
node frontend/scripts/test-reader-navigation-dom.mjs
node frontend/scripts/test-review-navigation-round2.mjs
node frontend/scripts/test-intake-lifecycle-dom.mjs
```

API 回归使用程序生成 PDF 和 pytest 临时数据目录，不写入 pilot / ICP 台账。

## 浏览器实测

以下来自本轮本地实际页面检查。预览地址为 <http://127.0.0.1:8768/app>，数据来自临时隔离空间中的 9 项生成示例。

| 视口 | 页面宽度检查 | 结果 |
| --- | --- | --- |
| 桌面 1440 × 1000 | `clientWidth = scrollWidth = 1425` | 无横向溢出 |
| 平板 768 × 1024 | `clientWidth = scrollWidth = 753` | 无横向溢出 |
| 手机 390 × 844 | `clientWidth = scrollWidth = 375` | 无横向溢出 |
| 窄屏手机 320 × 740 | `clientWidth = scrollWidth = 305` | 修复后无横向溢出 |

宽度差 15 px 来自系统滚动条。320 px 首次检查发现 `html` 的 320 px 最小宽度造成横向溢出；`base.css` 调整为 `min-width: 0` 后，重新构建、刷新并复测通过。

计算样式与截图检查结果：

- 浅色画布为 `#F4F5F7`，品牌色为 `#0F766E`；主标题字号 / 行高为 20 / 30 px，桌面侧栏宽 208 px。
- 深色画布为 `#0E151C`；浅 / 深色截图均已人工查看。主题按钮明确展示当前浅色、深色或跟随系统状态及下一选择。
- 上传弹窗“开始扫描”按钮实际背景为 `rgb(15, 118, 110)`，白色文字，高 43 px；截图确认全局按钮样式已应用。
- 原 PDF 图像实际加载，`naturalWidth > 0`。下一页和回引用页操作不改变摘录的引用定位。
- 保存备注后，待办数量与人工进度不变；确认一项后，待办由 9 变为 8，已核销为 1；切换“已核销”筛选显示 1 项。
- 原生文件选择器成功选择 PDF，上传区展示已选文件。
- 最终浏览器会话的控制台错误与警告均为空；检查结束后恢复原视口及“跟随系统”主题偏好。

视口与计算样式原始记录见 [browser-checks.json](../outputs/ui-redesign-round2/browser-checks.json)。

截图保存在 `outputs/ui-redesign-round2/`：

| 截图 | 内容 |
| --- | --- |
| [desktop-light-1440.jpg](../outputs/ui-redesign-round2/desktop-light-1440.jpg) | 桌面浅色工作台 |
| [desktop-dark-1440.jpg](../outputs/ui-redesign-round2/desktop-dark-1440.jpg) | 桌面深色工作台 |
| [tablet-light-768.jpg](../outputs/ui-redesign-round2/tablet-light-768.jpg) | 平板布局 |
| [mobile-390.jpg](../outputs/ui-redesign-round2/mobile-390.jpg) | 手机布局 |
| [mobile-light-320.jpg](../outputs/ui-redesign-round2/mobile-light-320.jpg) | 320 px 窄屏布局 |
| [upload-light-1440.jpg](../outputs/ui-redesign-round2/upload-light-1440.jpg) | 上传弹窗 |

验证边界：尚未逐项完成真实键盘操作流程，也未在操作系统中切换“减少动态效果”设置进行实测；相关实现只有 CSS / DOM 层面的覆盖。本轮不宣称完成全面可访问性审计。截图和生成示例验证不能替代真实企业文档的抽取、合规或业务验收。

## 交付与运行边界

`BidProof-frontend-redesign-round2-20260923.zip` 与首版分开保留。交付范围为当前源码、已构建静态产物、文档、上述六张截图与相关测试；排除虚拟环境、`node_modules`、依赖 / 测试缓存、会话数据库、上传原件、历史恢复数据及密钥，也排除 `outputs/opus5-materials/` 中的历史环境日志 / 登录截图和 `work/source-docs/*.docx` 原规划附件。最终压缩包校验值和清洁解压启动结果见随包交付的验收记录。

ZIP 同级的 `BidProof-round2-archive-acceptance.json` 记录 CRC、必需文件、排除项与解压启动结果；`.zip.sha256` 提供完整压缩包校验值。解压启动复用本机已安装的 Python 依赖，另建示例数据目录，不等同于在全新系统中安装依赖。

运行说明以 [START-HERE](../START-HERE.md) 为准：现成静态产物预览无需 Node 构建；Python 服务依赖之外，生成示例需要 `httpx2`；同时清空 `DATABASE_URL` 和 `BIDPROOF_DATABASE_URL`，将 `BIDPROOF_DATA_ROOT` 指向新建临时目录。示例账号为 `ui-review` / `LocalReview2026!`，服务仅绑定本机地址。
