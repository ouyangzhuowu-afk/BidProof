# BidProof 产品入口、认证与公网验收（2026-08-27）

## 本轮结论

BidProof 已具备邀请制企业试点所需的完整账号入口和公开产品页，`https://bidproof.marketcase.net` 已恢复公网访问。当前仍是依赖本机 FastAPI、SQLite 与 Cloudflare Tunnel 的试点部署，不是企业生产级高可用托管。

## 已完成

- `/` 为公开产品页，`/app` 为登录与企业工作台。
- 生产环境使用初始化令牌创建首个所有者；缺少令牌时 fail-closed。
- 管理员可生成 72 小时成员邀请，成员一次性设密激活。
- 管理员可生成 1 小时密码重置链接；重置后旧会话立即失效。
- 登录失败限速、密码显示切换、确认密码、退出后页面重新载入均已接入。
- 修复异步表单在 `await` 后访问失效 `event.currentTarget` 的浏览器错误，并覆盖登录、项目、邀请和漏项反馈处理器。
- 工作台筛选栏在中等桌面宽度改为两行布局，避免侵入右侧规则栏。
- 工作台产品截图、公开落地页桌面图和移动图已更新。

## 验收证据

- `uv run --group dev pytest -q`：110 passed。
- `node --check static/app.js`：通过。
- `npm test`（`deploy/cloudflare-container`）：1 passed。
- `uv run python -m app.workflow check`：PASS。
- 浏览器认证链路：生成邀请、成员激活、角色显示、管理员生成重置链接、旧会话失效、新密码登录、退出后动态账号与成员数据清空，全部通过。
- 响应式边界：1440、1100、820、390px 均无筛选控件越界或页面横向滚动。
- 公网：`/healthz`=200，`/api/auth/status`=200，未登录 `/api/runs`=401，伪造 `X-Workspace-ID` / `X-User-Role` 仍为 401。
- 公网页面：1440/390px 产品图正常加载；`/app` 显示“登录企业空间”；console error=0。

截图位于：

- `outputs/playwright/bidproof-public-landing-1440.png`
- `outputs/playwright/bidproof-public-landing-390.png`
- `outputs/playwright/bidproof-public-login-390.png`
- `outputs/playwright/bidproof-workspace-desktop-1440.png`

## 部署边界

Cloudflare Worker 上传和本地容器镜像构建均成功，但当前账号访问 Containers 专用端点 `/accounts/.../containers/me` 返回 HTTP 401。失败 Worker 已删除，未留下不可运行的域名拦截层；公网继续使用既有 `bidproof-local` Tunnel 回源 `127.0.0.1:8016`。

当前后台进程：

- FastAPI 启动器 PID：15620。
- cloudflared PID：74192。

本机重启或任一进程退出都会使公网试点不可用。正式企业部署仍需持久化存储、进程托管、集中日志、告警、备份恢复与高可用入口。

## 未完成的业务验证

当前真实企业试点台账仍为 0 条任务、0 条人工确认、0 个付款信号。工程验收不能替代真实召回率、严重风险漏报率和付费意愿验证。
