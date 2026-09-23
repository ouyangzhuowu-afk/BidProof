# 前端生产边界与可观测性

本轮以现有原生 ES 模块工作台为基础，保持 `/app`、审查凭证卡和 SafeHtml 渲染契约。运行时不新增 UI 框架或监控厂商 SDK。

## 会话与异步状态

- 会话过期或开始登出时，应用停止扫描 SSE/轮询，取消私有请求，清空任务、成员/项目缓存、草稿及私有 DOM。
- 每一轮认证使用独立 session epoch。旧会话已返回响应头、但尚未读完响应体的请求也不能回填数据。
- JSON 与报告二进制响应体均受取消/超时保护；真正创建下载链接前再次核对会话，注销立即释放尚未撤销的 object URL。浏览器已经保存的文件和已写入系统剪贴板的内容无法由网页撤回。
- 旧版兼容 state 与核心 store 同时清空，上传原生 FileList 和缓存引用同步释放；一次性凭据复制失败的延迟提示也不能在注销后重新显示明文。
- 同源标签页用 BroadcastChannel 广播固定失效事件，主动退出或表单重新认证会清空其他已打开页面并显示登录入口；不广播任何身份、令牌或文档数据。通道在 pagehide 关闭，从 bfcache 恢复的页面重新验证会话。浏览器不支持广播或服务器远程撤销时，保留下一次受保护请求返回 401 的清理兜底，不宣称服务器主动推送失效。OIDC 直接在服务器回调中更换身份尚未产生这个本地广播，其他已打开页面须刷新重新验证。
- 重新认证成功后加载全新 `/app`，重建监听与缓存。未保存输入不会跨身份保留。
- 登出接口失败不会显示“退出成功”；刷新后重新检查服务端会话，并显示退出尚未确认的提示。
- 决策、协作、作业页均检查当前任务或视图代际。离开作业页后，迟到响应不能重新启动轮询。
- 新扫描与版本重扫统一使用 `POST /api/jobs`。重扫携带 `parent_run_id`，后台完成后才读取实际结果。

## 决策并发契约

`DecisionRequest` 新增 `revision`。新版工作台始终发送有效正整数，服务端使用 compare-and-swap 保存。

```json
{
  "decision": "HOLD",
  "note": "需要核对证书原件",
  "unresolved_requirement_ids": ["REQ-001"],
  "revision": 7
}
```

- 陈旧版本返回 409，不覆盖已有决定，也不写入成功审计事件。
- UI 保留决策与说明，提供“刷新任务版本，保留输入”；重新读取后由用户再次核对、主动保存，不自动重放写请求。
- `production` 缺少 revision 返回 422；`development/test` 保留旧客户端兼容，并以服务端当前读取的版本保护保存期间的竞争。
- 迟到的保存响应不能将用户切回上一任务，也不能降低已显示的版本号。

## 错误与网络

启动异常、运行时 `error`/`unhandledrejection` 有可恢复提示；不会把失败写操作显示成成功。离线提示说明恢复连接后不会自动重发提交。评论、审计、整改面板独立降级并可单独重试。

GET/HEAD 的网络异常和 502/503/504 使用有上限的指数退避与抖动；写操作从不自动重试。取消在响应体读取期间仍生效，包括不支持 `AbortSignal.any` 的兼容路径。后台进度连接关闭会中止轮询并释放等待计时器。

## 严格类型的实际覆盖

运行：

```sh
cd frontend
npx tsc -p tsconfig.boundaries.json --noEmit
```

严格门禁覆盖 `contracts.ts`、validators、telemetry、runtime、session、session-channel、storage；启用 `strict`、`noUncheckedIndexedAccess`、`exactOptionalPropertyTypes`，不使用 `any` 或 `@ts-ignore` 消除诊断。运行时代码保持 JS + JSDoc，以兼容现有 Node DOM 测试与 Vite。

关键入站校验覆盖任务 ID、正整数 revision、要求项结构及状态；出站校验覆盖决策值、说明长度、关联要求数组及 revision。这是关键边界校验，**并非所有 API 响应的完整 JSON Schema 验证**。

`app.js` 已移除显式 `@ts-nocheck`；遗留视图仍处于 JS 渐进迁移边界。原 `tsconfig.json` 的全库 checkJs 仍关闭，不得将该命令通过描述成“全应用严格 TypeScript 已完成”。后续优先迁移 matrix、reader、intake，并用后端 OpenAPI 固化完整响应契约。

## 监控接入：默认无外发

`core/telemetry.js` 暴露 `configureTelemetry(sink, { release })`，sink 收到冻结的结构化 `DiagnosticEvent`。默认 sink 为 null，不产生监控网络请求，也没有安装或连接 Sentry/Datadog。

白名单仅包含：schema、受控 module/code、错误类型、发布号、固定路由类别、HTTP 状态、符合格式的 request-id、时间。**不包含 error.message/stack、URL query/hash 中的任务 ID、用户、文件名、正文、引文、备注、输入、cookie 或 token**。

同类事件一分钟内去重；每分钟最多 10 个事件；可选传输限制 2 KB；sink 自身异常被隔离，不递归上报。

同源接收端部署完成后，在可信构建入口显式接入：

```js
import { configureTelemetry, sameOriginSink } from './core/telemetry.js';
configureTelemetry(sameOriginSink('/api/frontend-diagnostics'), { release: '2026.09.23' });
```

上述路径是可配置示例，**当前代码不假设该接口已部署**。`sameOriginSink` 拒绝跨源、含查询参数或片段的地址；不自动重试监控请求。接收端需要独立限流及保留策略，并根据部署的 CSRF 规则接入。

已有监控 SDK 的团队可将白名单事件映射到标准接口：

```js
configureTelemetry((event) => {
  sentryClient.captureMessage('BidProof frontend diagnostic', {
    level: 'error',
    tags: { module: event.module, code: event.code, release: event.release },
    extra: { bidproof: event },
  });
}, { release: '2026.09.23' });

// 或：configureTelemetry(event => datadogLogger.error('BidProof frontend diagnostic', { bidproof: event }));
```

这段适配器只接收上面的安全事件。厂商 SDK 可能另行收集浏览器 URL、自动 breadcrumb、用户上下文或 session replay，须在接入时关闭并审计这些功能；本项目不把厂商默认行为算作已经满足的数据边界。密钥/接收端鉴权凭据留在服务端环境，不能放入客户端配置。

## 自动化证据

- `test-http-reliability.mjs`：只读重试、写入不重放、无效响应、响应体取消、会话失效、SSE 释放。
- `test-production-lifecycle-dom.mjs`：决策跨任务/版本竞态、409 保留输入、评论草稿、三面板降级、整改 FormData/状态契约、令牌显式 scope、卸载轮询、错误/离线提示。
- `test-runtime-boundaries.mjs`：关键输入/响应校验、遥测脱敏/去重/体积边界、同源限制、存储不可用降级。
- `test-session-channel.mjs`：双标签固定信号、不回响、未知消息拒绝、旧通道消息丢弃、pagehide/bfcache 生命周期与不支持时降级。
- `test-app-smoke-dom.mjs`：整应用真实 FormData 异步重扫及会话清理，保留上一轮详情与核销回归。
- `tests/test_decision_revision.py`：陈旧决策 409、成功版本递增、无重复成功审计、生产 revision 必填。

以上为自动化工程验证，不替代真实企业试运行、人工审批责任、浏览器支持矩阵或 OCR 质量门禁。
