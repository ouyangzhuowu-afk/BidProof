# 0924：看懂用途，顺畅进入，完成第一次检查

输入基线：`BID_0924.zip`，SHA-256 `fe564dacb212d159726e8dbb8f69f82053e4d564c5d466f7204aca310da85da5`。原文件保留。本包是独立改版，未推送 GitHub 或部署到公网。

## 四项交付

1. [文案前后对照与极简线框](docs/ux-0924/landing-blueprint.md)：H1「投标前，先查漏交材料。」；21 字副标题；单个开始检查主按钮；可玩示例；三个用途卡片。
2. [认证状态机与组件设计](docs/ux-0924/auth-flow.md)：邮箱/手机/密码/OAuth、MFA、格式校验、重发、过期、限流、离线及页面恢复。
3. 完整代码：[Hero](landing/index.html)、[演示控制器](landing/src/demo.ts)、[AuthModal](frontend/src/features/auth/unified.js)、[倒计时与输入规则](frontend/src/features/auth/passwordless-state.js)、[首次使用进度](frontend/src/features/runs/onboarding.js)。使用现有 ES 模块 / Vite / Tailwind，动态内容保持 SafeHtml 或原生文本节点。
4. [真实认证接口、供应商配置与身份边界](docs/production/passwordless-auth-2026-09-24.md)，以及[审计与改造路径](docs/ux-0924/system-audit.md)、[验收记录](docs/ux-0924/acceptance.md)。

## 启动

Python 3.11+，Node 22.12+。原依赖锁文件保留。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-production.lock
npm ci --prefix frontend
npm ci --prefix landing
npm run build --prefix frontend
npm run build --prefix landing
.venv/bin/python -m app.dbctl upgrade
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8772
```

首页 `http://127.0.0.1:8772/`，工作台 `/app`。没有配置邮件/短信/OAuth 时，保留原密码入口；空数据库仍需要管理员初始化。配置验证码服务且开放个人注册后，新用户无需先建管理员，验证身份即可创建独立工作区。示例任务为合成材料，不能计入客户或业务验证。

Render Free 的常用 SMTP 端口受平台限制，应配置 HTTPS 邮件适配器。服务端至少设置 `BIDPROOF_EMAIL_PROVIDER=resend`、`BIDPROOF_RESEND_API_KEY`、`BIDPROOF_EMAIL_FROM`、`BIDPROOF_OTP_SECRET`，并设置 `BIDPROOF_PERSONAL_SIGNUP=1`。供应商密钥和已验证发信域名由运营方提供；本包没有任何可用于真实发送的密钥。

独立服务器部署沿用 `docker-compose.yml`：复制 `.env.production.example` 填写部署参数与所需认证渠道，`docker compose --env-file .env.production up --build -d`。新增认证密钥只传给 Web 进程。Render 继续沿用 `Dockerfile.render` 和 `scripts/render-serve.sh`，在平台环境变量中配置上述渠道后部署；本次未更改现有试点的持久化和 Worker 方式。

## 验证

```sh
.venv/bin/python -m pytest -q
npm run verify --prefix frontend
npm run verify --prefix landing
.venv/bin/python -m app.workflow check
```

本机 SMTP 协议验收（仅回环接收器，虚构地址，不外发）：`BIDPROOF_TEST_SMTP=1 .venv/bin/python -m pytest tests/test_smtp_integration.py -q`。
实库迁移与并发验收：设置独立测试库 `BIDPROOF_TEST_POSTGRES_URL`，运行 `tests/test_postgres_integration.py`。不要使用生产库进行测试。

完整依赖、Docker 构建和自动化验证已在本轮检查；真实邮件/短信投递与 OAuth 授权需要实际供应商配置。浏览器因管理员安全策略无法验证而拒绝本地页面，桌面/手机视觉与真实浏览器交互仍待验收，不能用 DOM 测试代替此结论。
