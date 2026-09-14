# 批次 8 设计说明 · 管理页与鉴权

> **本文档的依据**：容器已重置，批次 3–7 的产物不在。上传的压缩包是原始 15 文件状态。
>
> 这对本批次反而是好事：**管理页与鉴权从第 1 批到第 7 批一次都没迁移过**，
> 原始 `app.js` 就是它们唯一的真相源。下面每一条都是从代码逐行核对出来的，
> 标了行号，不是凭记忆推的。
>
> 唯一无法完成的是「审查 MIGRATION.md」——那份文件随容器丢了，
> 我手里只有对话记录里的片段。需要补的内容整理在第 6 节。

---

## 0. 契约勘误（已用 batch7 真实文件复核，**撤回其中 9 条**）

> 这一节的上一个版本列了 15 条，是我根据对话记录重建的「批次 3 写了什么」推出来的。
> 拿到真实文件逐条打开之后：**其中 9 条不成立。**
>
> 原因在批次 4 的开头——我当时写的 `src/types/api.d.ts` 被删掉了，
> 保留的是工作区里原有那份 270 行的正确版本，并把 `api/*.js` 的引用改了过去。
> 记录里有这一步，我重建时没算进去。
>
> 教训很直白：**结论不能从对话记录推，必须打开文件。**

### 撤回的 9 条——`types/api.d.ts` 本来就是对的

| 我说的 | 实际 |
|---|---|
| `AuthStatus` 缺 6 个字段 | `personal_signup_enabled` / `trial_join_enabled` / `oidc_enabled` / `bootstrap_locked` / `bootstrap_token_required` / `mfa_enabled` **全部存在**，且 `bootstrap_locked` 还带了注释 |
| `Session` 字段错 | 实际就是 `session_id / current / created_at / expires_at`，正确 |
| `ApiTokenSummary` 字段错 | 实际是 `token_id / name / token_prefix / revoked_at`，另有 `ApiTokenCreated extends` 带明文 `token`，正确 |
| `Project` 缺 `code` | 有，正确 |

### 仍然成立的 10 条

**A 类 · 运行时会炸**

| 位置 | 现状 | 实际契约 | 后果 |
|---|---|---|---|
| `api/auth.js:107` `getMfaStatus()` | `request(paths.auth.mfa.enroll)`（GET） | 读 `/api/auth/status` 的 `mfa_enabled`（原 `app.js:1058`） | GET 打到只接受 POST 的端点，大概率 405 |
| `api/workspace.js:108` `saveWorkspaceSettings()` | `json(..., 'POST', ...)` | `PATCH`，body `{ retention_days }`（原 `app.js:957`） | 保存保留策略 405 |

**B 类 · 类型与实际不符，会把实现者带偏**

| 位置 | 标注的 | 实际 |
|---|---|---|
| `api/auth.js:114` `enrollMfa()` 返回 | `{ secret, otpauth_url }` | `{ secret, recovery_codes[] }` —— **恢复码只回传一次** |
| `api/auth.js:83` `describeAction()` 返回 | `action: 'activate' \| 'reset-password'` | `action: 'INVITE' \| …`，另有 `role` |
| `api/auth.js:57` `bootstrap()` body | `{ username, password }` | 另需 `workspace_name`、`bootstrap_token` |
| `api/workspace.js:45` `resetMemberPassword()` 返回 | `{ url?, token? }` | `{ reset_path }` |
| `api/auth.js:100` `createInvitation()` | 参数与返回都没建模 | 返回 `{ activation_path }` |
| `api/workspace.js:63` `createProject()` body | `{ name }` | 另需 `code`（可为 null） |

**C 类 · 缺失与语义偏差**

| 项 | 说明 |
|---|---|
| `GET /healthz?detail=true` | **完全不在 `paths.js` 里**（grep 命中 0）。它是唯一不在 `/api/` 前缀下的端点，返回 `{ database, backup_status, failed_jobs, last_verified_backup_at, degraded_reasons[] }` |
| `api/auth.js:51` `toOutcome()` | 用 `payload.mfa_token` 是否存在来判断要不要走第二步，实际契约的门是 `mfa_required: true`。当前后端两者同时回传，**所以现在能工作**——但语义不对，后端哪天只保留 `mfa_required` 就会静默失效。归为待修，不是已坏 |

另外一条业务规则在类型与 API 层里没有体现：
**`code === 'DEFAULT'` 的项目不允许归档**（原 `app.js:833`）。

## 1. 管理页确认流

### 1.1 现状：一个有真 bug 的确认原语，还被批次 4 降级了

原始实现已经有 `confirmDanger()`（第 595 行），要求用户输入确认词，
全项目只用在两处：批量删除任务（658）、清理到期归档（968）。

**问题一：Esc 关闭会让 Promise 永不 settle。**

```js
const done = (ok) => { /* 移除监听、close、resolve */ };
submit.addEventListener('click', onSubmit);
cancel.addEventListener('click', onCancel);
dialog.showModal();
```

`<dialog>` 原生支持 Esc 关闭，但那条路径不经过 `done()`。
于是 `await confirmDanger(...)` 永久挂起，调用方的按钮 loading 态永远不消失，
两个监听器也留在 DOM 上。用户看到的是「点了取消，按钮卡住了」。

**问题二：确认词输错等同于取消。**

`onSubmit` 是 `done(input.value === confirmWord)`——输错直接当「不确认」把对话框关掉，
不给任何反馈。用户会以为自己确认成功了，实际什么都没发生。
这是最容易让人困惑的一类失败：**没有报错，也没有生效**。

**问题三：批次 4 把批量删除从 `confirmDanger` 降级成了 `window.confirm`。**

这是我自己引入的回退。迁移 `list.js` 时用了：

```js
const ok = window.confirm(`将永久删除 ${ids.length} 个任务及其证据链，且无法恢复。\n\n确认继续？`);
```

原实现要求输入 `DELETE`，新实现敲一下回车就过了。**批次 8 必须把它改回来。**

### 1.2 设计：四级确认阶梯

先定规则，再逐个动作归类。判据只有两条：**是否可逆**、**失败的代价由谁承担**。

| 级别 | 形式 | 判据 |
|---|---|---|
| **T0** 无确认 | 直接执行 | 幂等、可逆、代价为零。收藏、筛选、展开 |
| **T1** 事后撤销 | 执行 + toast 内「撤销」 | 可逆，且撤销窗口内无副作用。归档 / 恢复 |
| **T2** 一次确认 | `confirm()` 对话框，主按钮 danger | 有后果但可恢复，或影响他人。停用成员、踢会话、取消作业 |
| **T3** 确认词 | 输入指定词，按钮在匹配前 disabled | **不可逆且销毁数据**。批量删除、留存清理、撤销全部会话 |

管理页各动作的归类：

| 动作 | 端点 | 级别 | 理由 |
|---|---|---|---|
| 创建项目 | `POST /api/projects` | T0 | 新增，无破坏性 |
| 归档 / 恢复项目 | `PATCH /api/projects/{id}` | **T1** | 完全可逆。现状是 T0（直接执行），加撤销即可，不必升到 T2 |
| 直接开户 | `POST /api/members` | T0 | 新增。但密码只在本地显示一次 → 见 §1.3 |
| 生成邀请 | `POST /api/auth/invitations` | T0 | 同上 |
| 改成员角色 | `PATCH /api/members/{id}` | **T2** | 改的是别人的权限，降级会让对方立刻失去访问。现状 T0，`<select>` 一 change 就提交 |
| 停用 / 启用成员 | `PATCH /api/members/{id}` | **T2** | 停用会把人踢出工作区 |
| 重置成员密码 | `POST /api/members/{id}/password-reset` | **T2** | 会使对方现有凭据失效 |
| 保存保留策略 | `PATCH /api/workspace/settings` | **T2** | 调小天数等于预告一次批量删除。确认文案应写明「将使 N 个任务进入待清理」 |
| 清理到期归档 | `POST /api/retention/purge` | **T3** | 不可逆。现状已是 T3，保持 |
| 创建备份 | `POST /api/backups` | T0 | 新增 |
| 改自己密码 | `POST /api/auth/password` | T0 | 表单本身即确认，且当前会话继续有效 |
| 踢单个会话 | `DELETE /api/auth/sessions/{id}` | **T2** | 现状 T0 |
| 踢全部其他会话 | `POST /api/auth/sessions/revoke-others` | **T3** | 批量、影响所有设备、无法恢复登录态。现状 T0 |
| 关闭 MFA | `POST /api/auth/mfa/disable` | **T2** | 已经要输 TOTP 码，码本身就是确认，不再叠加对话框 |
| 撤销 API 令牌 | `DELETE /api/auth/tokens/{id}` | **T3** | 不可逆，且会打断正在运行的集成。确认词用令牌名而非 `DELETE` |
| 批量删除任务 | `POST /api/runs/bulk` | **T3** | 恢复批次 4 之前的行为 |

两条贯穿性的规则：

- **确认词就用被删对象的名字**，不要一律 `DELETE`。撤销令牌时输入令牌名、
  清理归档时输入 `PURGE`——让肌肉记忆失效，这正是确认词存在的意义。
  统一成 `DELETE` 之后，用户第三次就是闭着眼睛敲了。
- **确认文案里必须有数字**，而且是**执行前重新取的数字**。
  `purgeRetention()` 这一点做对了：先 `GET /api/retention/preview` 拿实时 count，
  为 0 就直接提示不弹窗。新原语要把这个模式固化下来。

### 1.3 一次性凭据：四个地方，三种做法，两处会丢

这是管理页比确认流更值得改的一块。以下四处都产生**只回传一次、之后服务端只存哈希**的秘密：

| 位置 | 产物 | 现状呈现 | 问题 |
|---|---|---|---|
| 生成邀请 (882) | `activation_path` | `showSecureLink()`：链接 + 复制按钮 | 可用 |
| 重置成员密码 (905) | `reset_path` | `showSecureLink()` | 可用 |
| 创建 API 令牌 (1119) | 明文 `token` | `message.textContent = '请立即保存令牌：xxx'` | **无复制按钮，无警告，刷新即丢** |
| MFA 注册 (1070) | `recovery_codes[]` | `secret.textContent = '密钥：…\n恢复码：\n…'` | **同上，而且丢了恢复码 = 锁死账号** |

设计：抽一个 `ui/secret-reveal.js`，四处共用。要素固定：

1. 醒目边框 + 「仅显示一次」标签，不是普通段落文字
2. 等宽字体 + 复制按钮（`navigator.clipboard` 失败回退到 `window.prompt`，
   `showSecureLink` 已有这个回退，保留）
3. 多行秘密（恢复码）提供「全部复制」与「下载 .txt」
4. **一个「我已保存」确认按钮，点击前不允许关闭所在面板**
5. 离开视图时清空 DOM，不留在内存与页面上

第 4 条是关键：现在没有任何机制阻止用户在保存恢复码之前点走。

### 1.4 权限判定：两套机制并存，其中一套在撒谎

管理页现在用两种方式决定「这个控件给不给看」：

**A. 角色前置**——`['OWNER','ADMIN'].includes(store.currentUser?.role)`
控制 `#member-form` (800)、`#project-form` (830)、`#purge-retention` (950)。

**B. 403 后置**——先发请求，catch 里把表单藏起来：

```js
} catch (error) {
  setHtml(backupTarget, html`<div class="empty-state">当前角色无备份管理权限。</div>`);
  document.querySelector('#create-backup').hidden = true;
}
```

备份 (947) 与 API 令牌 (1105) 走的是 B。

B 的问题不在于多发一次请求，在于**它把所有失败都说成权限问题**。
网络断了、后端 500、超时——用户看到的都是「当前角色无备份管理权限」。
一个管理员会因此以为自己权限被改了。**这是界面在撒谎**，和批次 7 那个
「整改项保存失败却不还原下拉」是同一类问题。

设计：

- 统一到 A。可见性由角色矩阵前置决定，写在一处 `core/permissions.js`
- B 只作为兜底，且**必须按状态码分支**：403 才说权限，其余走正常错误态并给重试

角色矩阵（**标注为假设**——备份与令牌两行是从 403 行为反推的，没有文档依据）：

| 能力 | OWNER | ADMIN | REVIEWER | VIEWER |
|---|:---:|:---:|:---:|:---:|
| 成员管理 | ✓ | ✓ | — | — |
| 改 / 停用 OWNER 自身 | — | — | — | — |
| 项目管理（DEFAULT 除外） | ✓ | ✓ | — | — |
| 留存清理 | ✓ | ✓ | — | — |
| 备份管理 | ✓ | ?（假设） | — | — |
| API 令牌 | ✓ | ?（假设） | — | — |
| 自己的密码 / 会话 / MFA | ✓ | ✓ | ✓ | ✓ |

第二行不是笔误：`loadMembers()` 第 802 行的条件是 `member.role !== 'OWNER'`，
**OWNER 自己也不能通过界面改角色或停用**。这是既有行为，要保留。

> **给后端的建议（不直接改）**：在 `/api/auth/status` 里回传一个 `capabilities: string[]`。
> 现在前端把权限规则硬编码了两份（角色数组 + 403 兜底），后端加一个角色就要改前端。
> 这是建议，不是本批次的改动。

---

## 2. 鉴权状态机对照表

### 2.1 现状：四模式 × MFA 挂起 × 六个开关，全靠嵌套三元表达式

`applyAuthMode()`（第 186–239 行，54 行）对**同一个表单**做了 24 处
`hidden` / `required` / `textContent` / `disabled` 的命令式赋值，其中
`#auth-help` 那一处是**四层嵌套三元**。

后果不是「难看」，是**无法验证**。要确认「个人注册开启 + 需要初始化令牌 + MFA 挂起」
这个组合下界面对不对，只能在脑子里跑一遍 54 行。而 4 模式 × 2 MFA 态 × 6 布尔开关
的组合空间远大于能手工检查的范围。

另外三个具体问题：

1. **`#auth-form` 的提交按钮在 MFA 挂起时被 `disabled`**（第 239 行末），
   但 MFA 验证码正是通过这个表单提交的（第 253 行）。用户只能靠在输入框里按回车，
   点按钮无效。这是个真 bug。
2. **`setAuthMode()` 的模式钳制逻辑（172–185）与 `showAuth()` 的显隐逻辑（150–170）
   各写了一遍同样的开关判断**，两处不一致时以后者为准，但没人保证它们一致。
3. **账号动作（激活 / 重置）是完全独立的第二个对话框**，由 URL 查询参数进入
   （`?token=…&auth_action=activate|reset`），与 `auth-panel` 没有任何共享状态。
   两者都可能同时存在——`initializeAccountAction()` 返回 true 时跳过 `showAuth()`，
   靠调用顺序保证互斥，没有显式约束。

### 2.2 设计：一张表，一个纯函数

把状态机从代码里提出来，做成数据。`resolveAuthView(status, mode, pendingMfa)`
是纯函数，返回一个视图模型，渲染层只负责把模型刷到 DOM 上。
纯函数意味着**每一行都能单测**，不需要起浏览器。

**状态定义**

```
AuthState = { mode: 'setup' | 'login' | 'register' | 'trial',
              pendingMfa: boolean }
AccountActionState = { action: 'INVITE' | 'RESET', token }   // 独立对话框
```

**模式可达性（钳制规则，从 172–178 行提取）**

| 请求模式 | 条件 | 实际落到 |
|---|---|---|
| `setup` | `setup_required` | `setup` |
| `setup` | `!setup_required` | `login` |
| `login` | `setup_required` | `setup` |
| `login` | 否则 | `login` |
| `register` | `personal_signup_enabled` | `register` |
| `register` | 否则 | `setup_required ? 'setup' : 'login'` |
| `trial` | `trial_join_enabled && !setup_required` | `trial` |
| `trial` | 否则 | `login` |

一条不变式：**`setup_required` 为真时，`login` 不可达**。
这条规则现在隐含在两个 if 里，应该写成显式断言。

**四模式对照表**

| | setup | login | register | trial |
|---|---|---|---|---|
| **入口条件** | `setup_required` | 默认 | `personal_signup_enabled` | `trial_join_enabled && !setup_required` |
| **端点** | `/api/auth/bootstrap` | `/api/auth/login` | `/api/auth/register` | `/api/auth/trial-join` |
| **请求体** | `username, password, workspace_name, bootstrap_token?` | `username, password` | `username, password, display_name?` | `username, password, join_code` |
| **标题** | 初始化企业管理员 | 登录工作台 | 注册个人账号 | 试用加入企业空间 |
| **专属字段** | `#setup-fields`（工作区名）+ `#bootstrap-token-wrap`（仅 `bootstrap_token_required`） | — | `#register-fields`（显示名） | `#trial-join-fields`（加入码） |
| **确认密码** | 必填 | 隐藏 | 必填 | 必填 |
| **密码最短** | 12 | 1 | 12 | 12 |
| **autocomplete** | `new-password` | `current-password` | `new-password` | `new-password` |
| **OIDC 入口** | 隐藏 | `oidc_enabled` 时显示 | 隐藏 | 隐藏 |
| **提交按钮** | 创建并进入 | 登录 | 注册并进入 | 加入并进入 |
| **loading 文案** | 正在初始化 | 正在登录 | 正在注册 | 正在加入 |
| **初始焦点** | `#auth-workspace` | `#auth-username` | `#auth-username` | `#auth-join-code` |
| **提交按钮禁用** | `bootstrap_locked` 时 | — | — | — |
| **帮助文案** | 隐藏 | 随 `personal_signup_enabled` / `trial_join_enabled` 三分支 | 已有账号？切换到登录 | 已有账号？切换到登录 |

**MFA 挂起是正交子状态，覆盖以上任意一行**

| | 值 |
|---|---|
| 进入条件 | 任一模式的响应含 `mfa_required: true`，取 `mfa_token` 暂存 |
| 端点 | `/api/auth/mfa/verify` |
| 请求体 | `{ code, mfa_token }` |
| 覆盖行为 | 显示 `#mfa-fields`；`#auth-username` / `#auth-password` 置灰；OIDC 隐藏；按钮文案「完成验证」；焦点 `#auth-mfa-code` |
| **提交按钮** | **必须可用**（现状 bug：被 disabled） |
| 退出 | 成功 → 关闭对话框并进入应用；失败 → 停留，焦点回 `#auth-mfa-code` |
| 取消 | **现状没有取消路径**。建议加「返回登录」，清空 `pendingMfaToken` |

最后一行是设计补充：用户换了手机、拿不到验证码时，现在唯一的出路是刷新整页。

**账号动作（独立对话框 `#account-action-panel`）**

| | INVITE | RESET |
|---|---|---|
| 进入 | `?auth_action=activate&token=…` | `?auth_action=reset&token=…` |
| 探测 | `GET /api/auth/action?token=…` → `{ action, username, role }` | 同 |
| 端点 | `/api/auth/activate` | `/api/auth/reset-password` |
| 请求体 | `{ token, password }` | `{ token, password }` |
| 标题 | 激活企业账号 | 重置账号密码 |
| 副标题 | 接受邀请并设置「{role}」账号密码 | 设置新密码后，旧会话将全部失效 |
| 按钮 | 激活并进入 | 重置并进入 |
| token 失效 | 显示错误并**禁用提交**（342–344），这一点做对了，保留 | 同 |
| 成功后 | `history.replaceState('/app')` 清掉 URL 里的 token，再进入应用 | 同 |

`replaceState` 那一步必须保留——它防止一次性 token 留在浏览器历史与
后续分享的 URL 里。这是安全行为，不是清洁工作。

### 2.3 迁移后的模块形状

```
features/auth/
├── state.js      resolveAuthView() + clampMode()  —— 纯函数，可单测，不碰 DOM
├── view.js       视图模型 → DOM。唯一一处 querySelector
├── submit.js     四模式 + MFA 的端点与请求体映射（即上面两张表）
└── account.js    激活 / 重置对话框
```

分成四个文件的理由只有一个：**`state.js` 必须能在没有浏览器的情况下跑**。
现在这套逻辑之所以没人敢动，正是因为验证它的唯一方式是手工点一遍 24 种组合。

---

## 3. 批次拆分建议

原计划「管理页一批做完」不现实——破坏性操作与一次性凭据集中在这里，
每一个都要单独想清楚语义。建议拆成三批：

**8a · 确认原语与共享组件**（不迁视图，只做地基）
- `ui/confirm.js`：修掉 Esc 挂起；确认词实时校验、不匹配时按钮 disabled；
  焦点返回触发元素；`dialog` 的 `close` 事件兜底 resolve(false)
- `ui/secret-reveal.js`：一次性凭据组件（§1.3）
- `core/permissions.js`：角色矩阵前置判定（§1.4）
- **把批次 4 降级的批量删除改回 T3**
- 同时修完 §0 那 15 条契约错误

**8b · 管理页主体**：成员、项目、工作区设置、留存、备份、健康、用量、隐私

**9 · 鉴权**：`features/auth/` 四个模块 + 账号动作对话框

之后剩扫描弹窗、详情页元数据与版本差异，迁完即可删 `legacy.css`，
CSS 从约 146 kB 落到 70 kB 左右。

8a 不产生任何用户可见变化，但后面两批都依赖它。先做它，8b 和 8c 才是纯粹的搬运。

---

## 4. 本批次会顺手修掉的真 bug

按严重度排序，都是读代码时发现的，不是重构引入的：

1. **`confirmDanger` 按 Esc 后 Promise 永不 settle**（595）——调用方永久挂起
2. **MFA 挂起时提交按钮被禁用**（239）——验证码只能靠回车提交
3. **确认词输错被当成取消**（613）——用户以为确认了，实际没执行
4. **备份 / 令牌把一切错误说成权限不足**（947、1105）——界面撒谎
5. **API 令牌明文与 MFA 恢复码没有复制按钮**（1119、1070）——丢了就锁死
6. **MFA 挂起没有取消路径**——拿不到验证码只能刷新整页
7. **`loadOperations()` 用一个 `Promise.all` 拉五个面板**（938）——
   与批次 7 修掉的协作区是同一个模式，任一失败全部变错误态
8. **`loadMembers` / `loadProjects` 每次渲染后逐个 `addEventListener`**（808-810、834）——
   与前几批相同，改委托

---

## 5. 需要产品确认的两件事

**其一：改成员角色是否升到 T2。**
现在 `<select>` 一 change 就直接提交，没有确认。升到 T2 会让批量调整权限变慢。
如果管理员日常就要频繁改角色，可以改用 T1（提交 + 5 秒内可撤销）。
我倾向 T2——权限降级对被改的人是立即生效的，而对方不在场。

**其二：撤销全部其他会话是否用确认词。**
我按 T3 处理了。反方意见是：这个功能的典型使用场景是「我怀疑账号被盗」，
此时让用户先冷静输入一个词是有成本的。
如果产品认为它属于应急操作，降到 T2 更合适。

---

## 6. MIGRATION.md

已拿到真实文件并逐条复核，修订版见 **`MIGRATION.md`**（与本文档同目录）。

原文件的问题集中在三类：数字过时且自相矛盾（同一份文档里同时写着
126.3 kB 和「约 46 kB」，实际 146.6 kB）、已完成的事写成待办（`jobs` 仍在待办列表里、
`legacy.css` 方案的描述停留在批次 4 之前）、以及**三处真实退步没有记录**——
批量删除确认降级、`openRun()` 仍用全屏遮罩、`inlineDynamicImports: true` 这个
批次 2 判定的 P0 至今未解。最后一条尤其要紧：文档通篇给人「性能已改善」的印象，
而实际上代码分割在构建配置层面仍然是被禁止的。
