# 生产候选版集成报告（2026-09-24）

## 结论

`BidProof-production-candidate-20260923.zip` 已合入仓库并跑通全部本地质量门禁与端到端冒烟，分支为 `codex/production-candidate-20260923`，`main` 与线上 `bidproof.marketcase.net` 保持现状。

**不要直接把该分支合并到 `main`**：新版在 `BIDPROOF_ENV=production` 下会把缺失的生产边界当作启动错误，而现有 `render.yaml` 不满足这些条件，推送即触发 Render 自动部署并导致启动失败（详见"Action Required"）。

## 来源与基线

| 项 | 值 |
|----|----|
| 交付包 | `BidProof-production-candidate-20260923.zip` |
| 包 sha256 | `472213dca965a005a88318c0dcafb972b5d0313c94875c0d964b0bf08f2be5f3` |
| 包声明的基线 | `BidProof-frontend-redesign-round2-20260923.zip`，sha256 `d5089f2b…55f0f`，与本仓库根目录该压缩包**逐字节一致**（已核验） |
| 合并基准 | `main` @ `af75ded` |

## 合并范围

按分叉点做三方比对（交付包 / 其声明基线 / 仓库 HEAD），逐类处理：

- **取包内版本 129 个**：`app/` 后端（含 `job_runner.py`、`job_leases.py`、`request_limits.py`）、`frontend/`、`static/`、`tests/`、CI、`Dockerfile`、`docker-compose.yml`、`requirements*.txt`、`pyproject.toml`、`scripts/serve.sh`。
- **新增 60 个**：`landing/`（严格 TypeScript + Tailwind 新版首页源码）、`static/marketing/`（首页构建产物与社交卡）、`docs/production/*`、`docs/frontend-production-boundaries.md`、`docs/security-hardening-2026-09-23.md`、`.env.production.example`、`deploy/Caddyfile`、`requirements-production.lock`、`scripts/production-smoke.py`、`migrations/versions/d2e3f4a5b6c7_scan_job_leases.py`、`outputs/production/*`。
- **删除 1 个**：`app/idempotency.py`（包内声明的 removed_files，新代码不再引用）。
- **保留仓库版本 11 个**：`AGENTS.md`、`docs/README.md`、`docs/archive/*`、`OPUS5_MIGRATION_REPORT.md`、`work/fixtures/public-eval/*`（仓库在 2026-09-23 的归档与加固结果，不被包内旧版覆盖）。
- **手工合并 3 个**：`.gitignore`、`README.md`、`workflow/project-state.json`。

**保真校验**：包内 `outputs/production/change-manifest.json` 的 192 条记录中，**189 条与仓库文件 sha256 完全一致**，差异仅为上述 3 个手工合并文件。

## 处理掉的对接问题

1. **依赖新增**：包内 `pyproject.toml`/`requirements.txt` 新增 `PyJWT[crypto]>=2.10.1,<3` 与 `cryptography>=42`；`uv sync --group dev` 后实测 PyJWT 2.14.0 / cryptography 50.0.1，服务可导入启动。
2. **`.gitignore`**：保留仓库 2026-09-23 的加固门禁（真实上传、`third_party/`、训练语料二进制、zip/tgz、覆盖率与日志），只补包内需要的一条 `!.env.production.example`；未回退仓库既有规则。
3. **控制面状态**：以包内 `project-state.json` 为底合并，保留仓库独有的 `C-026`、`D-ASTRA-MERGE-2026-09-23` 与 `Q-HANDOVER-1`（resolved），并登记本轮 `C-PROD-20260923`；`python -m app.workflow check` PASS。
4. **文档索引**：`docs/README.md` 增加生产候选文档与前端边界条目。
5. **构建产物跨平台漂移**：`landing/` 重建产物与包内**逐字节一致**（含哈希文件名）；工作台 `style.css`/`index.html` 仅差 Windows 注释路径分隔符与随之变化的 `?v=` 版本戳（把分隔符归一后 sha256 与包内完全相同），因此提交的是包内 Linux 一致产物。

## 质量门禁（本机实测，2026-09-24）

| 门禁 | 命令 | 结果 |
|------|------|------|
| Python lint | `ruff check app tests scripts/production-smoke.py` | All checks passed（此前全仓 140 项告警已清零） |
| 控制面 | `python -m app.workflow check` | PASS |
| 后端回归 | `pytest -q` | **376 passed, 11 skipped, 0 failed** |
| 前端类型 | `npm run check` / `npm run check:boundaries` | 均通过（含严格边界检查） |
| 前端行为 | `npm test` | **124 tests / 124 pass / 0 fail** |
| 前端 lint | `npm run lint` | 0 error，2 warning（既存） |
| 前端构建 | `npm run build` | 通过；`static/app.js` 与包内逐字节一致 |
| 首页类型/测试/构建 | `npm run verify --prefix landing` | 严格 TS 通过、10/10 测试通过、构建通过 |
| 依赖审计 | `npm audit --audit-level=high`（两处） | 0 vulnerabilities |
| 端到端冒烟 | `scripts/production-smoke.py` | **9 项检查全部 passed** |

跳过原因：本机无 PostgreSQL 与真实上传样本，`test_postgres_integration` 与真实 fixture 相关用例按设计跳过（包作者在其环境为 380 passed / 7 skipped，含 5 项 PostgreSQL）。差值来自环境，不是失败。

手工 HTTP 检查（本地 `127.0.0.1:8770`）：`/`、`/app`、`/healthz`、`/readyz`、`/robots.txt`、`/sitemap.xml`、`/privacy`、`/api/privacy` 全部 200；`/api/sample-tender` 未登录 401、登录后 200（返回示例 PDF）；原页预览 200（PNG，44 119 B）；越界页码 404。

浏览器端到端（本地候选版）：新版 Landing 加载 → 交互演示切换到场景 03 并完成一次人工核销（进度 1/3）→ 点击 CTA 进入 `/app` → 登录 → 任务列表 → 详情"投标审查工作台"（风险摘要、逐项核验、双向原文对照与原页预览均渲染）。

## Action Required（上线前必须由人处理）

新版在 `BIDPROOF_ENV=production` 下执行 fail-closed 检查，`app/config.py` 会在启动时抛错，当前 Render 配置缺以下条件：

1. `BIDPROOF_PUBLIC_ORIGIN` 必须是 HTTPS origin（现有 `render.yaml` 未设置）。
2. `BIDPROOF_ALLOWED_HOSTS` 必须显式列出域名且不含通配符，并包含 `PUBLIC_ORIGIN` 的主机名（未设置）。
3. `BIDPROOF_TRIAL_JOIN_CODE` 在 production 下**必须为空**（现有值为 `BidProof-Trial-2026`），共享试用码被禁用，试用入口改为 `BIDPROOF_PERSONAL_SIGNUP` 或企业邀请。
4. `BIDPROOF_BOOTSTRAP_TOKEN` 需 ≥32 字符（现有为自动生成，需确认长度）。
5. 需要一个**独立 worker 进程**（`python -m app.worker`）：`serve.sh` 只跑 HTTP，compose 里 worker 是单独服务；Render 免费计划没有后台 worker，单服务无法满足该约束。
6. 数据库迁移不再是启动副作用，需显式执行 `python -m app.dbctl upgrade`（Render 需配置 pre-deploy 命令或一次性任务）。
7. 生产额外需要 `BIDPROOF_FIELD_ENCRYPTION_KEY`（字段加密密钥，需安全备份）。

因此公网试点路径需要一次明确决策，三选一：

- **A（推荐）**：按 `docs/production/deployment.md` 用单机 `Caddy + Web + Worker + PostgreSQL` 部署，环境变量取自 `.env.production.example`。
- **B**：保留 Render，但升级到含 worker 的付费实例，并补齐上面 1–7 的配置。
- **C**：暂时不合并该分支，线上继续使用 2026-09-23 的工作台版本。

## Deploy Command

单机生产（推荐路径，先填 `.env.production`）：

```sh
cp .env.production.example .env.production
docker compose build && docker compose up -d
```

本机试跑（演示数据，非生产）：

```sh
uv sync --group dev
BIDPROOF_DATA_ROOT=<临时目录> BIDPROOF_ENV=development BIDPROOF_JOB_RUNNER=inline PYTHONPATH=. python scripts/seed-ui-review.py
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8770
```

推送到 `main` 会触发 Render 自动部署；在完成 Action Required 之前**不要推送**。

## 边界与未覆盖

- 本轮是工程验证，不是业务验收：OCR 行级 CER / 关键字段 F1 / TEDS 仍未达标，`outputs/pilot-ledger.csv` 与 `icp-outreach.csv` 保持空置。
- 未在本机执行：PostgreSQL 集成测试（5 项）、真实上传 fixture 回归（6 项）、容器镜像构建与容器内烟测（CI 会执行）。
- 包内 `outputs/production/browser-checks.json` 记录的是交付方浏览器验收；本次仅补做了本地候选版的链路走查，未做多视口截图比对与"减少动态效果"实测。
