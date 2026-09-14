# BidProof 前端重构 · 迁移说明

本文件描述当前重构进度、验证方式与回滚路径。

> **本版修订自批次 7 产物，所有数字均已对照真实文件核过**（2026-09-14）。
> 上一版里 `app.js 1650 行`、`style.css 126.3 kB`、`build:css 约 46 kB`
> 三处数字都是旧批次留下的，其中后两条还互相矛盾。
> 修订时同步补进了三处此前未记录的**退步**，见「已知退步」一节。

---

## 当前状态

采用**绞杀者（strangler fig）**策略：新架构与旧 `app.js` 并存，按视图逐个搬迁，
每搬走一块就从 `app.js` 删掉对应的一块。任何一个批次结束时项目都是可构建、可运行的。

| 指标 | 值 | 核对方式 |
|---|---|---|
| `src/app.js` | **558 行**（起点 1650，**降 66%**） | `wc -l` |
| `static/style.css` | **160.7 kB**（legacy 59.8 kB + 新系统 100.9 kB） | `build:css` 输出 |
| `app.js` 顶层裸监听器 | 20 条，全部指向存在的 id | 脚本扫描 |
| 运行时依赖 | 0 | `package.json` |

```
frontend/
├── preview/index.html        ← 设计系统预览（浏览器直接打开，无需构建）
├── types/api.d.ts            ← 服务端契约的唯一声明处
├── scripts/build-css.mjs     ← CSS 展开脚本（支持 @import … layer(name)）
├── src/
│   ├── main.js               ← 入口：启动核心设施，再加载 app.js
│   ├── app.js                ← 旧单体，1100 行，逐批缩小中
│   ├── state.js              ⚠ 旧 store，仍被 app.js 使用（见「已知退步 4」）
│   ├── core/                 ✅ http / dom / router / store / theme / icons / toast / format
│   │                            + permissions（角色能力矩阵）
│   ├── api/                  ✅ paths / runs / jobs / auth / workspace
│   ├── ui/render.js          ✅ 转义模板 + 空/错/骨架三态
│   ├── ui/confirm.js         ✅ 确认原语（T2 一次确认 / T3 确认词）
│   ├── ui/secret-reveal.js   ✅ 一次性凭据（链接 / 令牌 / 恢复码）
│   ├── i18n/index.js         ✅
│   ├── features/
│   │   ├── runs/
│   │   │   ├── list.js       ✅ 任务列表
│   │   │   ├── matrix.js     ✅ 要求项对照矩阵 + 高风险卡片
│   │   │   ├── decision.js   ✅ 人工决策页
│   │   │   └── collab.js     ✅ 评论 / 审计 / 整改项
│   │   ├── admin/            ✅ members / projects / operations / account
│   │   ├── auth/             ✅ state（纯函数状态机）/ view / index
│   │   ├── jobs/index.js     ✅ 扫描作业页（含活跃轮询）
│   │   └── scan/watcher.js   ✅ 后台扫描监视器（取代全屏遮罩）
│   └── styles/
│       ├── tokens.css        ✅ 设计令牌
│       ├── base.css          ✅ reset + 排版 + 状态原语
│       ├── layout.css        ✅ 应用外壳
│       ├── components.css    ✅ 业务组件
│       ├── views/runs.css    ✅ 任务列表
│       ├── views/detail.css  ✅ 要求项行、风险卡、处置指引
│       ├── views/jobs.css    ✅ 停靠区、作业表格、决策卡片
│       ├── views/collab.css  ✅ 评论流、审计时间线、整改项、确认清单
│       ├── views/admin.css   ✅ 管理页分区、通用行、统计块
│       ├── views/auth.css    ✅ 鉴权对话框、密码显隐、模式切换器
│       ├── legacy.css        ⏳ 旧 style.css 快照，@layer legacy 兜底未迁移视图
│       └── index.css         ✅ 层级顺序 + 入口
```

**尚未迁移**：扫描弹窗与漏项反馈弹窗、详情页（要求项矩阵已迁，元数据表单与
版本差异未迁）、应用外壳（侧栏 / 顶栏 / 移动端底栏）。
这三块迁完即可删除 `legacy.css` 与 350 kB 的 lucide UMD。

### 层级顺序

`styles/index.css` 第 17 行一次性定死：

```
legacy → reset → base → layout → components → views → utilities
```

`legacy` 排在最前 = 优先级最低。之后任何一层内部的选择器特异性都不会跨层打架——
这是旧版 `style.css` 里 16 处 `!important` 的根因。

---

## 已知退步

以下三条是重构**引入的**回退，不是旧代码的问题。修复它们优先于继续迁移新视图。

**1. 批量删除的确认被降级（批次 4 引入）**

原实现 `confirmDanger()`（`app.js:432`）要求用户输入 `DELETE` 才执行。
迁移 `features/runs/list.js` 时换成了 `window.confirm`（`list.js:511`），
敲一下回车就过。`confirmDanger` 现在全项目只剩留存清理一处在用（`app.js:696`）。

修复方向见批次 8 设计说明的确认阶梯：批量删除属 T3，必须恢复确认词。

**2. `openRun()` 仍用全屏遮罩做一次 GET（`app.js:473`）**

```js
const overlay = document.getElementById('loading-overlay');
if (overlay) overlay.hidden = false;
```

这与批次 6 自己定下的原则冲突——`components.css` 的 `.boot-overlay` 注释写着
「仅用于首帧鉴权判定，不用于数据请求；数据请求一律用骨架屏」。
批次 6 曾把这处记成「死代码」，那是**错的**：它是活的，元素也还在
`static/index.html:12`。正确的处理是把它换成详情页骨架屏。

**3. `inlineDynamicImports: true` 仍在（`vite.config.js`）**

批次 2 把「构建配置从根本上禁止代码分割」列为 **P0**，至今未解。
`build.lib` + `formats: ['iife']` + `inlineDynamicImports: true` 三者叠加，
产物必然是单文件 IIFE，任何懒加载与路由级分割都不生效。

这一条最容易被文档误导：前面几批都在讲性能与体积，容易让人以为包体积问题
已经在改善。**实际上并没有。** 要么在迁完全部视图后切成 ESM 多入口，
要么明确记录「本次重构不处理包体积，只处理设计系统与可维护性」。
目前的事实是后者。

**4. 双 store 并存**

`app.js` 用旧的 `src/state.js`（62 行，裸 mutable 对象），
`features/*` 用 `src/core/store.js`（162 行，带订阅与 TTL）。
两者互不通知。目前没有出问题，是因为迁移时刻意让共享字段只在一侧写；
但这是约定，不是机制。`app.js` 清空后 `state.js` 整文件删除。

`npm run check`（tsc strict）与 `npm run lint` 的报错大概率集中在这里，
以及 `app.js` 里大量未标注类型的旧代码。**这两条命令至今一次都没跑过。**

---

## 契约勘误 —— 批次 8a 已全部修复

`types/api.d.ts` 本身一直是准确的，问题在 `api/*.js` 的实现与 JSDoc。
完整清单与判定依据见批次 8 设计说明第 0 节。已修的 10 条：

| 位置 | 原 | 现 |
|---|---|---|
| `auth.js` `getMfaStatus()` | `GET /api/auth/mfa/enroll` | 读 `/api/auth/status` 的 `mfa_enabled` |
| `workspace.js` `saveWorkspaceSettings()` | `POST` | `PATCH`，body `{ retention_days }` |
| `auth.js` `toOutcome()` | 按 `mfa_token` 是否存在判断 | 按 `mfa_required` 判断 |
| `auth.js` `enrollMfa()` | 返回标 `otpauth_url` | `{ secret, recovery_codes[] }` |
| `auth.js` `describeAction()` | `'activate' \| 'reset-password'` | `'INVITE' \| 'RESET'`，并补 `role` |
| `auth.js` `bootstrap()` | `{ username, password }` | 补 `workspace_name`、`bootstrap_token` |
| `auth.js` `createInvitation()` | 未建模 | 参数 + 返回 `{ activation_path }` |
| `workspace.js` `resetMemberPassword()` | 返回标 `{ url?, token? }` | `{ reset_path }` |
| `workspace.js` `createProject()` | `{ name }` | `{ name, code \| null }` |
| `paths.js` | 无 `/healthz` | 新增 `health: '/healthz?detail=true'` + `workspace.getHealth()` |

`getMfaStatus()` 那条尤其值得记一笔：它对一个**只接受 POST 且 POST 会轮换密钥**
的端点发 GET。最好的结果是 405，最坏的结果是把用户已绑定的验证器搞失效。

---

## 批次记录

### 批次 9：鉴权

`app.js` 782 → **558 行**，累计从 1650 降 **66%**。

```
features/auth/
├── state.js   纯函数：clampMode / resolveAuthView / buildPayload —— 不碰 DOM
├── view.js    视图模型 → DOM。唯一一处 querySelector
└── index.js   装配、提交、MFA 两步、账号动作、登出、401 重开
```

#### 为什么要把状态机做成纯函数

旧 `applyAuthMode()` 是 54 行，对同一个表单做了 24 处
`hidden` / `required` / `textContent` / `disabled` 的命令式赋值，
其中 `#auth-help` 那一处是**四层嵌套三元**。

问题不是难看，是**无法验证**。要确认「个人注册开启 + 需要初始化令牌 + MFA 挂起」
这个组合下界面对不对，只能在脑子里跑一遍 54 行；而 4 模式 × 2 MFA 态 × 6 布尔开关
的组合空间远大于能手工检查的范围。

拆开之后 `state.js` 可以在 node 里直接断言。本批实跑了 14 条：

```
setup_required 时 login 不可达 · 未开个人注册时 register 落到 login
初始化阶段 trial 不可达 · MFA 挂起时提交按钮可用 · MFA 挂起时锁住用户名密码
bootstrap 被锁时禁用提交 · 需要令牌时显示令牌字段 · 只有一种模式时隐藏切换器 …
```

**这是整个重构里第一次有可执行的验证。** `view.js` 里不允许出现业务条件判断 ——
一旦那里开始写 `if (mode === ...)`，说明状态机漏了字段，应该回去补。

#### 修掉的三个真 bug

**1. MFA 挂起时提交按钮被禁用。** 旧实现第 196 行：

```js
submitButton.disabled = lockedSetup || Boolean(store.pendingMfaToken);
```

而验证码正是通过同一个表单提交的。用户只能靠在输入框里按回车，点按钮毫无反应。

**2. MFA 挂起没有取消路径。** 换了手机、拿不到验证码时，唯一的出路是刷新整页。
现在 `#mfa-fields` 里有「返回登录」，清 token 的同时清表单 ——
上一次的密码不该留在 DOM 里。

**3. 401 事件没有任何人监听。** `core/http.js` 派发 `bidproof:unauthorized`，
`main.js` 也接上了，但 `app.js` 里没有处理 —— 会话过期后用户看到的是
一连串请求失败，而不是一个登录框。现在会重新拉一次 status 再开框
（过期期间管理员可能改过开关，用旧 status 渲染会给出已经不存在的入口）。

#### 其它

- 模式钳制逻辑此前在 `setAuthMode()` 与 `showAuth()` 各写了一遍，
  两处不一致时以后者为准，但没有任何机制保证一致。现在只有 `clampMode()`。
- 端点与请求体的映射从 `submitAuth()` 的 if/else 链里提出来，
  与文案、字段可见性解耦。`register` 的 `display_name` 为空时不发送 ——
  后端会把空字符串当成一个合法的空名字。
- `#auth-message` 从一行小字改成 callout。在一个有六个输入框的表单里，
  错误提示必须看得见。
- 密码显隐按钮的 `aria-label` 方向修正：它描述的是**点下去会发生什么**，
  旧实现把两者写反了一半。加了 `aria-pressed`。
- 两个对话框仍禁止 Esc 关闭（背后没有可用界面），这是既有行为，保留。
- 账号动作成功后 `history.replaceState('/app')` 保留 —— 这是安全行为不是清洁工作，
  否则一次性 token 会留在浏览器历史与用户之后可能分享的地址里。

### 批次 8b：管理页

`app.js` 1123 → **782 行**，累计从 1650 降 **53%**。迁出 22 个函数与 19 条顶层监听器。

拆成四个模块，因为三者的读者、权限与变更频率都不一样，
放一个文件里迟早长回 500 行：

```
features/admin/
├── members.js      成员：创建（邀请 / 直接开户）、改角色、停用、重置密码
├── projects.js     项目：创建、归档 / 恢复
├── operations.js   留存策略、备份、服务健康、用量、隐私声明
├── account.js      改密码、登录设备、二次验证、API 令牌
└── index.js        一起挂、一起卸
```

#### 信息架构：按「后果」分区

旧版把九个面板平铺成一个 `auto-fill` 网格，于是**「停用成员」和
「清理到期归档」长得一模一样、还挨在一起** —— 一个可以随时撤销，
另一个永久删除证据材料。

现在分四区，每区一句话说明这一区的操作会造成什么：
工作区治理 / 数据生命周期 / 运行状态 / 账号安全。
分区标题是唯一的层级线索，不加边框也不加底色 —— 再套一层盒子只会更乱。

#### 拆开 `loadOperations()` 的 Promise.all

旧实现：

```js
const [settings, preview, health, usage, privacy] = await Promise.all([...]);
```

五个互不相关的面板共用一个 try/catch，任何一个接口挂掉五块一起变成
「运行状态加载失败」—— 而其中四块的数据其实已经拿到了。
这和批次 7 修掉的协作区是同一个模式。现在每块自己取数、自己显示状态。

（保留策略那一块仍用 `Promise.all` 取 settings + preview：
缺任何一个这块都没法显示，这个合并是有依据的。）

#### 权限：403 不再等于「你没权限」

备份与 API 令牌此前没有角色判断，只有 403 兜底 ——
网络断了、后端 500、超时，用户看到的都是「当前角色无备份管理权限」，
管理员会因此以为自己权限被改了。

现在可见性由 `core/permissions.js` 前置判定，403 兜底必须经过
`isPermissionError()`：**只有 403 才说权限，其余走错误态并给重试**。

#### 确认阶梯落地（产品已确认）

| 动作 | 级别 | 说明 |
|---|---|---|
| 改成员角色 | **T2** | 产品确认升级。取消确认时把下拉还原 —— 不还原界面就在说谎 |
| 停用成员 | T2 | 启用不确认：恢复访问没有破坏性 |
| 重置成员密码 | T2 | 会使对方现有凭据失效 |
| 归档 / 恢复项目 | **T1** | 立即执行 + 8 秒内可撤销。为此给 `core/toast.js` 加了 `toastWithUndo()` |
| 缩短保留期 | **T2** | 调小等于预告一次批量删除；调大或不变直接保存 |
| 清理到期归档 | T3 `PURGE` | 确认前**重新取一次预览**，文案里的数字必须是执行前的实时值 |
| 踢出单个设备 | T2 | |
| 踢出全部其他设备 | **T3 `REVOKE`** | 产品确认用确认词。误触代价（全公司设备被踢）高于多打六个字母 |
| 撤销 API 令牌 | T3 **令牌名** | 同时是一次「你选对那一条了吗」的校验 |
| 关闭 MFA | — | **刻意不加确认**：它已经要求输入 TOTP 码，那个码本身就是确认 |

`toastWithUndo()` 的撤销按钮是真 `<button>` 而不是点整条提示 ——
提示本来就绑了「点击即关」，做成点整条的话，想关掉反而会触发撤销。
撤销实现必须是一次幂等的反向请求：提示只活 8 秒，这期间页面上的任何
中间状态都可能已经变了。

#### 其它改动

- **绑定验证器前加确认。** `POST /api/auth/mfa/enroll` **调用即轮换密钥**，
  用户没完成绑定就离开，此前生成的密钥与恢复码已经失效。旧实现点一下就发请求。
  已启用 MFA 时「开始绑定」按钮直接隐藏。
- 会话列表的 `created_at` / `expires_at` 此前原样打印 ISO 时间戳，现在走 `format.js`；
  当前设备排最前、高亮、且不给撤销按钮（踢自己等于登出，那是别的入口的事）。
- 只有一台设备时隐藏「踢出全部其他设备」。
- 成员表改真 `<table>`，事件全部委托。旧实现每次渲染后遍历三种控件逐个绑定。
- `loadProjects()` 留在 app.js 但只负责填两个下拉。旧版它同时渲染管理页列表，
  于是管理页刷新一次会顺手重置用户在别处选好的筛选。
- 新建项目时 `code` 留空传 `null` 而不是 `''` —— 后端会把空字符串当成一个合法编号存下来。

### 批次 8a：确认阶梯、一次性凭据、权限矩阵

本批**不迁移任何视图**，只做后面两批共用的地基。
`app.js` 1100 → 1123 行（补确认与凭据逻辑，净增 23 行；同时删掉了 `confirmDanger`
与 `showSecureLink` 两个函数）。

#### 新确认原语 `ui/confirm.js`

旧 `confirmDanger()` 有三个问题，逐一修掉：

1. **按 Esc 会让 Promise 永不 settle。** `<dialog>` 原生支持 Esc 关闭，
   但那条路径不经过 `done()`，于是 `await` 永久挂起，调用方按钮的 loading
   永远不消失，监听器也留在 DOM 上。用户看到的是「点了取消，按钮卡住了」。
   新实现把 **dialog 的 `close` 事件作为唯一 settle 出口** ——
   Esc、点背景、点任意按钮最终都走到它，不存在漏网路径。
2. **确认词输错等同于取消。** 旧实现 `done(input.value === confirmWord)`，
   输错直接关闭且无反馈，用户会以为确认成功了。
   新实现实时校验，不匹配时确认按钮 `disabled`，根本无法提交。
   输入允许首尾空白（从密码管理器粘贴几乎必然带空格）。
3. **关闭后焦点掉回文档开头。** 改用 `core/dom.js` 的 `openDialog()`，归还焦点。
   有确认词时聚焦输入框，否则聚焦**取消**——危险操作的默认焦点不该落在「确认」上。

对话框 DOM 由模块自己创建，不再依赖 `static/index.html` 的 `#confirm-panel`
（该标记已删除）。理由：这个原语要能被任意视图调用，包括还没迁移的页面，
依赖外部标记等于给它绑一个隐式前置条件。

**确认阶梯**（完整归类见批次 8 设计说明 §1.2）：

| 级别 | 形式 | 本批已接入 |
|---|---|---|
| T2 | 一次确认 | 取消扫描作业、踢出单个会话、记录「停止投标」、决策说明为空 |
| T3 | 确认词 | 批量删除任务（`DELETE`）、清理到期归档（`PURGE`）、踢出全部其他设备（`REVOKE`）、撤销 API 令牌（**令牌名本身**） |

确认词刻意不统一成 `DELETE`：同一个词用在所有破坏性操作上，敲第三次就成了
肌肉记忆，确认也就失去意义。撤销令牌时输入令牌名，同时还是一次
「你选对那一条了吗」的校验。

#### 一次性凭据 `ui/secret-reveal.js`

四处产生只回传一次的秘密，旧实现有三种做法，其中两处只是
`element.textContent = '请立即保存令牌：' + token`：

| 位置 | 产物 | 旧做法 |
|---|---|---|
| 生成邀请 | `activation_path` | 链接 + 复制按钮（可用） |
| 重置成员密码 | `reset_path` | 同上 |
| 创建 API 令牌 | 明文 `token` | **裸 textContent，无复制按钮** |
| MFA 注册 | `recovery_codes[]` | **同上。丢了等于账号锁死** |

统一为一个组件：虚线警示边框 + 「仅显示一次」标签、等宽展示、
复制 / 打开 / 下载、以及旧实现完全没有的**「我已保存」确认**。
点击后卸掉警示色但不隐藏内容——用户可能还想再核对一遍。
`revokeObjectURL` 也补上了（旧的两处下载里有一处漏了，每次导出泄漏一个 blob）。

> 配套改了 `static/index.html` 三个挂载点的标签：`#mfa-secret` 从 `<pre>`、
> `#member-message` 与 `#token-message` 从 `<span>` 改为 `<div>`。
> 前两者只允许短语内容，嵌进一个 `<section>` 会被浏览器纠正成错误的 DOM。

#### 权限矩阵 `core/permissions.js`

把可见性判定统一为角色前置，403 只作为兜底且**必须按状态码分支**
（`isPermissionError()` 只认 403）。同时把两条此前只存在于内联三元里的
业务规则提成具名函数：`isMemberMutable()`（OWNER 自身不可改角色或停用）、
`isProjectArchivable()`（`code === 'DEFAULT'` 的项目不可归档）。

矩阵里备份与 API 令牌两行**标注为假设**——旧实现对它们没有角色判断，
只有 403 兜底，这里按「与其它管理能力同级」推定，拿到后端权限表后需核对。

本批只接入了 `setCurrentRole()`；把 403 兜底改成矩阵前置在批次 8b
随管理页一起做，因为那需要同时重写渲染。

### 批次 4：任务列表接线 + 级联层方案

1. `static/index.html` 的 `#home-view` 整段替换为新设计系统标记。
   其余视图与外壳未动，靠级联层兜底。
2. `app.js` 1650 → 1456 行。删除 11 个已迁移函数与 15 条指向已删除 DOM 的顶层监听器。
3. `loadProjects()` 加判空——它往 `#run-project-filter` 填选项，
   而该下拉现在只存在于任务列表视图。旧实现是裸 `querySelector(...).innerHTML`，
   不在该视图时会抛 `TypeError`，把整个管理页拖垮。
4. 示例试跑用 `bidproof:start-sample-scan` 事件解耦，避免新模块反向依赖旧单体。

**为什么不给旧 CSS 加前缀**：`styles/legacy.css` 是旧 `static/style.css` 的原样快照，
通过 `@import "./legacy.css" layer(legacy);` 整体包进优先级最低的级联层。
新设计系统在任何选择器上稳定胜出，只有旧 class 的元素仍被旧规则兜底。
不需要给 559 条旧选择器逐条加前缀，也不会出现新旧互相 `!important`。
`scripts/build-css.mjs` 为此加了 `@import "x.css" layer(name);` 语法支持（约 6 行）。

代价是过渡期体积上去了。**146.6 kB 是峰值不是终点**：四块视图迁完后
`legacy.css` 整文件删除，预计落在 85 kB 左右，比旧版 60 kB 大，
但覆盖了深色模式、响应式断点与四种完整状态——旧版这些要么没有，要么靠 JS 拼。

### 批次 5：要求项对照矩阵

`app.js` 1456 → 1319 行。迁出 14 个函数 + 7 条顶层监听器 + 死常量 `PAGE_SIZE`。

**顺带修掉的两处契约违规**（旧代码的真问题，不是重构引入的）：

- 复核请求漏传 `revision`。这是后端的乐观并发字段，省略它会让两个人
  同时复核同一任务时**静默覆盖**对方的判定。
- 准确率反馈的 body 少了四个字段。真实契约是
  `{ category, predicted, actual, requirement_id, note, dataset_scope: 'PILOT', review_complete }`。
  其中 `review_complete` 读界面上「完成全文漏项复核」复选框，
  直接决定 `/api/accuracy/metrics` 的 `review_population_complete`，
  进而决定准确率能否对外引用——**不能默认填 true**。

**一处产品诚实性问题**：旧 `explanationMarkup()` 用 `category` + `status` 查表生成
「证据缺口 / 风险影响 / 建议动作」，但排版与真实判定结果完全一样，
读起来像系统对这份文档的分析结论。对一个卖可追溯性的合规工具，
这是把硬编码猜测冒充成证据。处理：内容保留，整块视觉降级并加明确声明。
将来后端若提供真正的逐项分析，应替换 `guidance()` 而不是在它之上叠加。

其它：分类筛选带每类数量；复核后保留展开状态与滚动位置；
复核组与质量组按钮视觉分开（前者写审计链，后者不改判定）；
`scrollIntoView` 尊重 `prefers-reduced-motion`；切换任务时 `resetMatrixView()`。

### 批次 6：扫描作业 + 后台化扫描流程

`app.js` 1319 → 1222 行。

**✅ 产品已确认（2026-09-14）**：接受后台扫描监视器，不再使用全屏遮罩阻塞。
旧 `waitForJob()` 提交扫描后弹全屏遮罩，EventSource 等作业结束，超时 30 分钟，期间整个应用锁死。
但扫描在契约上本来就是后台作业（`POST /api/jobs` 立刻返回 `job_id`），
后端从未要求前端等待。现在提交后立刻关窗，作业进右下角停靠区（上限 5 个）。
卡片上的 × 是收起界面、**不取消作业**——取消要去作业页。

若日后因计费/配额需要「提交后必须等」，再单开需求改回；当前试点路径以停靠区为准。

**顺带修掉的连接泄漏**：旧实现在正常终态会 `close()`，但用户中途离开页面时
Promise 永不 settle，EventSource 一直挂着。现在连接登记在 `watchers`，
`pagehide` 统一关闭（不用 `unload`：在 iOS Safari 的 bfcache 下不可靠）。

其它：有活作业时 5s 轮询、全部终态自动停；轮询刷新不显示骨架屏也不覆盖已渲染列表；
总数未知时走不确定态；改用真 `<table>`；失败行整行着色。

### 批次 7：人工决策页 + 详情页协作区

`app.js` 1222 → 1100 行。

**决策页**：「未解决要求项」原本是 `<select multiple size="7">`——
整个产品最重要的一次输入用了 Web 上最容易误操作的控件，点一下清空全部选择，
触屏几乎无法多选。改为复选框列表 `.ack-list`。
另：「停止投标」加二次确认；说明为空时提醒（提示而非阻断）；
保存后停在本页重渲染；错误改 callout 并**把焦点移到错误处**；
选中态用描边而非填充（整块变红会让「停止投标」看起来像系统建议）。

**协作区**：旧实现用一个 `Promise.all` 拉评论、审计、整改，共用 try/catch。
任一接口挂掉三个面板一起变错误态，而且 catch 分支**只写了两个面板**，
审计面板会永远停在骨架屏。现在三条链路独立。
另：审计记录把 `user_id` 映射成用户名；状态下拉保存失败时还原
（否则界面在说谎）；关联要求项只列非 PASS 项；评论保留 `pre-wrap`。

---

## 验证命令

```bash
cd frontend
npm install
npm run check      # tsc --noEmit，strict + checkJs
npm run lint       # eslint src scripts
npm run build      # build:css + build:js
npm run verify     # 以上三条串联
```

| 命令 | 预期 |
|---|---|
| `npm run check` | **尚未跑过**。预期有报错，集中在 `app.js` 未标注类型的旧代码与双 store |
| 状态机自测 | `node --input-type=module` 断言 `features/auth/state.js`，本批 14 项全过。建议正式化为测试文件 |
| `npm run lint` | **尚未跑过** |
| `npm run build:css` | 输出 `static/style.css`，当前 **160.7 kB**（含 legacy 层）。这是过渡期峰值 |
| `npm run build:js` | 输出 `static/app.js` + `.map`。注意仍是单文件 IIFE，见「已知退步 3」 |

**不需要构建的验证**：浏览器直接打开 `frontend/preview/index.html`，
可看到全部令牌、组件与四种状态，右上角切换深浅色。这是最快的验收入口。

---

## 依赖变更

只新增 devDependencies，运行时依赖仍为 **0**。

| 包 | 用途 | 许可证 | 替代方案 |
|---|---|---|---|
| `eslint@^9` | 静态检查 | MIT | 无（oxlint 更快但规则生态不足） |
| `globals@^15` | eslint 环境全局变量表 | MIT | 手写 globals 列表 |
| `typescript@^5.6` | `checkJs` 类型检查，不产出代码 | Apache-2.0 | 保留 jsconfig（会丢掉 strict） |

**lucide 替换：已就绪，尚未拆除。** `core/icons.js`（6.9 kB）已内联所用图标的
SVG path，名称与 lucide 一致，HTML 里的 `data-lucide="x"` 一字不用改。
但 `static/index.html:349` 仍在加载 `/static/vendor/lucide.min.js`（约 350 kB）。

> 删除条件：全部视图迁完。在此之前删掉会让未迁移视图丢图标。
> 这一步能一次性拿掉 350 kB，是目前**唯一确定的体积收益**。

## 环境变量变更

无。项目不读取任何 `import.meta.env` 业务变量，
仅 `core/dom.js` 用 `import.meta.env?.DEV` 决定是否打印开发期警告。

---

## 契约约束（重构不得触碰）

- **API 路径、方法、字段语义、错误码**：集中在 `src/api/paths.js`。改它等于改对外契约。
- **鉴权**：`credentials: 'same-origin'`；CSRF 从 cookie `bidproof_csrf` 读取，
  写入 `X-CSRF-Token` 头；401（非 `/api/auth/` 路径）触发重新登录。
- **决策枚举**：`CONTINUE | HOLD | STOP`。**不是** `GO / NO_GO`。
- **异步不对称**：新建扫描走 `POST /api/jobs`（返回 job），
  重扫走 `POST /api/runs/{id}/rescan`（同步返回 Run）。既有契约，前端不统一。
- **复核并发**：`POST /api/runs/{id}/review` 必须带当前 Run 的 `revision`。
- **MFA 两步**：登录响应的门是 `mfa_required: true`，不是 `mfa_token` 存在与否。
- **一次性凭据**：邀请链接 `activation_path`、重置链接 `reset_path`、
  API 令牌明文 `token`、MFA 恢复码 `recovery_codes[]` —— 四者**只回传一次**，
  服务端之后只存哈希。界面必须让用户在这一刻拿走。
- **默认项目不可归档**：`Project.code === 'DEFAULT'` 的项目没有归档入口。
- **合规**：`AccuracySummary.review_population_complete` 为 `false` 时，
  precision / recall 只是抽样估计，界面必须显式声明，不得呈现为已验证指标。
  降级逻辑在 `features/runs/list.js` 的 `loadAccuracy()`。
- **埋点 / 监控 / i18n**：未删除任何相关逻辑。i18n 从 `i18n.js` 拆为 `i18n/index.js`，
  键名与取值全部保留。

---

## 回滚

每个批次都是纯增量。

| 想回滚的 | 做法 |
|---|---|
| 全部新架构 | `vite.config.js` 的 `lib.entry` 改回 `src/app.js`；恢复 `static/style.css` 与 `static/index.html` 备份。`src/{core,api,ui,features,styles}` 可原地留着不参与构建 |
| 仅样式 | 恢复 `static/style.css` 备份。JS 层不依赖任何 class 名 |
| 仅某个已接线视图 | 恢复 `static/index.html` 对应段落 + 撤销 `app.js` 的函数删除 + 移除 `main.js`／`app.js` 里对应模块的挂载调用 |

**必须备份两个文件**：`static/style.css`（`build:css` 会直接覆盖）
与 `static/index.html`。后者已被批次 4 / 5 / 7 改过三段：

| 段落 | 批次 |
|---|---|
| `#home-view` 整段 | 4 |
| 矩阵工具条 + `#requirements` + `#matrix-pagination` | 5 |
| `#decision-view` 整段 | 7 |

上一版的回滚表漏了 `index.html`，按它操作会只回滚一半。

---

## 已知问题 / 待确认

1. **`npm run check` 与 `npm run lint` 从未执行过**（容器内无 `node_modules`、无网络）。
   这是当前最大的未知。建议在继续迁移前先跑一次。
2. `types/api.d.ts` 中标有 `[假设]` 的字段是从 `app.js` 读取路径反推的，
   没有 OpenAPI 可核对。建议拿后端 schema 对一遍，尤其
   `Notification.severity`、`Requirement.severity`、`AccuracySummary` 的顶层汇总字段、
   以及 `Session.created_at / expires_at` 是否已是可读字符串。
3. `core/permissions.js` 里备份与 API 令牌两行是**推定** ——
   旧实现对它们没有角色判断，这里按「与其它管理能力同级」推。需与后端权限表核对。
   推错的方向是「该显示的没显示」，比反过来安全，但仍然是推定。
5. `landing.css`（18 kB）与 `style.css` 之间存在重复的排版与按钮规则，
   本轮未处理。营销页与工作台共用 `tokens.css` 是后续优化项。
6. 运行时行为尚未在浏览器中验证。批次 8a 新增两处要看：
   确认框按 Esc 后调用方按钮能否正常恢复；确认词输错时确认按钮是否保持禁用。
   另外：建议重点看三处：
   筛选连续改动时列表是否显示最后一次的结果（`AbortController` 竞态）、
   离开再回到视图时监听器有无重复挂载、批量选中后切换筛选选中态是否正确清空。
