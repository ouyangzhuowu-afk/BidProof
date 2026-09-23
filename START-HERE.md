# BidProof · 生产候选版（2026-09-23）

本轮交付新 Landing Page、工作台安全与状态加固、独立扫描 worker、生产 Docker Compose、CI 与完整主流程测试。桌面原项目及前两版压缩包保留，本轮未推送 GitHub、未发布公网。

## 直接体验

本机预览运行时：

- 首页与交互演示：<http://127.0.0.1:8770/>
- 审查工作台：<http://127.0.0.1:8770/app>
- 演示账号：`ui-review`，密码：`LocalReview2026!`

示例 PDF、账号和任务仅用于隔离界面验收，不能用于正式部署或真实企业业务验收。首页三种交互示例不需要登录。

## 核心交付入口

- [P0/P1 系统审计与改造路径](docs/production/system-audit.md)
- [Landing 文案与组件蓝图](docs/production/landing-blueprint.md)
- [改造前后、验证范围与遗留边界](docs/production/acceptance.md)
- [生产部署、升级与回退](docs/production/deployment.md)
- [API 端到端烟测与 CI](docs/production/api-smoke.md)
- [前端类型、状态和监控边界](docs/frontend-production-boundaries.md)
- [设计 Tokens](docs/design-tokens.md)、[第二轮工作台视觉与交互记录](docs/ui-hardening-round2-2026-09-22.md)

## 从解压目录本地启动

需要 Python 3.11+。压缩包已带静态产物，体验时无需 Node。请在解压后的项目根目录、同一个终端执行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-production.lock 'httpx2>=2.12'

export BIDPROOF_DATABASE_URL=
export DATABASE_URL=
export BIDPROOF_ENV=development
export BIDPROOF_JOB_RUNNER=inline
export BIDPROOF_DATA_ROOT="$(mktemp -d /tmp/bidproof-candidate.XXXXXX)"

PYTHONPATH=. python scripts/seed-ui-review.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8770
```

这会创建一个独立临时示例空间。重开终端后需要重新指定同一个 `BIDPROOF_DATA_ROOT` 才能继续原示例；需要长期保存的实际数据应放到持久目录。端口被占用时更换端口并访问相应地址。停止服务使用 `Ctrl+C`。

## 生产配置

推荐单机 `Caddy HTTPS → Web + 独立 Worker → PostgreSQL + 私有文件卷`。镜像使用非 root 用户、只读根文件系统、资源上限、显式代理信任、独立迁移和就绪探针。

先阅读 [部署说明](docs/production/deployment.md)，复制 `.env.production.example` 并填写域名和独立随机密钥。填好的环境文件不得提交。确认目标服务器和 DNS 后，按文档启动；本机演示账号与临时目录不能作为生产配置。

## 开发与验证

需要 Node.js 24；两个前端使用各自锁文件，不增加运行时 Node 服务。

```sh
npm ci --prefix frontend
npm run verify --prefix frontend
npm ci --prefix landing
npm run verify --prefix landing

python -m pip install pytest 'httpx2>=2.12' ruff pip-audit
python -m ruff check app tests scripts/production-smoke.py
python -m pytest -q -rs
python -m app.workflow check
pip-audit -r requirements-production.lock
```

PostgreSQL 集成测试需通过 `BIDPROOF_TEST_POSTGRES_URL` 指向隔离测试库。实际测试结果、跳过原因、浏览器验收及容器执行记录在 `outputs/production/`；缺少原始样本和可选 OCR 环境的测试不会被伪报为通过。

工作台保留原生 ES 模块，新增核心边界启用严格类型检查；Landing 为完整严格 TypeScript + Tailwind。遗留全库 JS 严格迁移、真实监控账号接入、真实 IdP、公开部署和商业验证仍有明确边界。OCR CER/F1/TEDS 与真实企业试点未通过，不能据工程测试宣称零漏报或商业验收完成。

## 文件与历史版本

交付包包括源码、构建产物、生产锁文件、迁移、CI、测试与说明；不携带环境密钥、账号数据库、会话、原始上传材料、备份、私钥、虚拟环境或 `node_modules`。`.env.production.example` 只是空配置模板。

第一版和第二版交付文件保持原样，可继续对比。当前压缩包名称为 `BidProof-production-candidate-20260923.zip`，附 SHA-256 与独立验收记录。
