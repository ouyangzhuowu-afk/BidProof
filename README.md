# BidProof — 投标证据链 Agent

面向 IT 服务、软件实施类中小企业的投标资格与废标风险扫描工具：上传招标文件与企业证据后，逐页抽出要求项，给出带双向页码引用的风险结论。

- 创建日期：2026-08-21 ｜ 最后更新：2026-09-23
- 当前阶段：`sandbox-campaign-A`（沙箱工程阶段，2026-09-16 锁定）
- 进度唯一真源：[workflow/project-state.json](workflow/project-state.json) ｜ Agent 协作说明：[AGENTS.md](AGENTS.md)

## 一条红线

每条结论都必须能定位到**招标文件页码 + 企业证据页码 + 可核对原文**。缺任一侧只能给 `UNKNOWN` 或 `NEEDS_REVIEW`，**不允许给 `PASS`**。系统把外部文件内容当作数据（DATA），不当作指令。

## 在线入口

| 入口 | 地址 | 说明 |
|------|------|------|
| 产品页 | <https://bidproof.marketcase.net/> | 公开介绍页 |
| 企业工作台 | <https://bidproof.marketcase.net/app> | 需登录 |
| 健康检查 | `/healthz` | 部署与试用探活 |

公网试点跑在 Render 免费 Web Service（新加坡节点）：空闲约 15 分钟休眠，下次请求约 1 分钟冷启动，Free Postgres 自创建起 30 天到期；**不是高可用生产托管**。
本机备用：`.\scripts\start-pilot.ps1`（Cloudflare Tunnel + HTTP/2）。

## 账号流程

- 个人可自行注册，得到独立个人工作区（与其他企业空间隔离）；企业专属部署可设 `BIDPROOF_PERSONAL_SIGNUP=0` 关闭。
- 首个企业所有者由运维用初始化令牌创建；生产环境缺少令牌时默认锁定初始化。
- 所有者或管理员可「生成邀请」（72 小时激活链接）或「直接开户」（立刻设好用户名与密码）。
- 团队试用：设 `BIDPROOF_TRIAL_JOIN_CODE=BidProof-Trial-2026`，登录页出现「试用加入」，成员自助开户并加入主企业空间（默认复核人）。
- 登录失败限速；改密与密码重置完成后旧会话全部撤销。

## 快速开始

```bash
pip install -r requirements.txt          # 或 uv sync
uv run python -m app.workflow check      # 控制面状态校验，必须 PASS
uv run --group dev pytest -q             # 2026-09-23 实测：303 passed, 11 skipped
uv run uvicorn app.main:app --host 127.0.0.1 --port 8016   # 打开 http://127.0.0.1:8016/app
```

前端源码在 `frontend/src/`（Vite + 原生 ES 模块，无框架），构建产物在 `static/`，由 FastAPI 直接托管：

```bash
npm ci --prefix frontend && npm run build --prefix frontend   # build:css → vite → stamp-assets
npm run check --prefix frontend && npm run lint --prefix frontend
```

`static/` 是产物，不要手改；CI 用 `git diff --exit-code -- static/app.js static/style.css` 校验产物与源码一致。

容器方式：`docker compose up -d --build`（postgres + app + worker，端口 8016→8080）。

## 架构与目录

```
浏览器 → FastAPI(app/) → app/api/*         路由（runs / auth / jobs / members / projects / reports / admin / health）
                        ├ app/authz.py     权限矩阵，require() 强制校验
                        ├ app/csrf.py      双提交 CSRF
                        ├ app/services/*   扫描、任务、报告、工作区编排
                        ├ app/rules.py     确定性判定 + 双页码门禁
                        ├ app/extraction.py + app/ocr.py   页级抽取 / OCR fail-closed
                        └ app/db.py + Alembic   SQLite（默认）/ PostgreSQL（生产）
静态托管：static/  ←  frontend/src/ 的构建产物
```

| 目录 | 用途 |
|------|------|
| `app/` | 后端服务（FastAPI） |
| `frontend/` `static/` | 前端源码 / 构建产物 |
| `tests/` | pytest，含前端契约与移动端布局断言 |
| `workflow/` | 控制面：状态、纲领、执行说明（每轮先读） |
| `outputs/` | 验收报告、台账、基准数据、截图 |
| `work/` | 工作数据：上传、OCR、语料、恢复演练记录 |
| `docs/` | 文档索引见 [docs/README.md](docs/README.md)，历史材料在 `docs/archive/` |

## OCR（默认关闭）

默认不调用任何外部模型，确定性规则先行。需要处理扫描件时按需启用；密钥只从进程环境注入，不写进 `.env`、代码、数据库或日志：

```powershell
$env:BID_OCR_PROVIDER = "qwen-vl-ocr"
$env:QWEN_OCR_API_KEY = "<从密钥管理器注入>"
```

OCR 失败、超时或返回空文本时保留 `ocr_status=FAILED` 并按缺证据处理，不会因此产生 `PASS`。云端 OCR 出网受 `BIDPROOF_OCR_EGRESS_MODE` / `BIDPROOF_OCR_EGRESS_ALLOWED` 白名单控制。

OCR 质量门禁现状（如实记录，不掩盖）：

| 门禁 | 阈值 | 当前观测 | 状态 |
|------|------|----------|------|
| 行级 CER | ≤ 2% | 3.17% | `GATE_FAIL` |
| 关键字段 F1 | ≥ 97% | 76.00% | `GATE_FAIL` |
| 表格结构 TEDS | ≥ 90% | GT 种子 16 页 | `NOT_EVALUATED` |

任一门禁未达标时，产品侧强制 `NEEDS_REVIEW`。这些是工程门禁，**不是**业务验收结论。

## 数据库与迁移

- 架构定义只有一处：`app/models.py`（SQLAlchemy Core metadata），Alembic 基线由它生成，一致性有测试守护。
- `BIDPROOF_DATABASE_URL` 为空时使用 `BIDPROOF_DATA_ROOT` 下的 SQLite 文件；生产建议 PostgreSQL（`requirements-postgres.txt`）。
- 升级用 `python -m app.dbctl upgrade`，不要直接 `alembic upgrade head`：试点期的 SQLite 库有表但没有版本行，需要先按基线纳管（adopt）再升级。
- 私有化交付：`python scripts/preflight.py` 做升级前校验，离线包见 `scripts/pack-offline.sh`，回滚见 [docs/upgrade.md](docs/upgrade.md)。

## 部署

| 方式 | 文件 / 命令 | 状态 |
|------|-------------|------|
| 公网试点 | `render.yaml`（Render Blueprint，免费档 + Free Postgres） | 已上线 |
| 本机备用 | `.\scripts\start-pilot.ps1`（Tunnel 回源 127.0.0.1:8016） | 可用 |
| 容器 | `docker-compose.yml`（扫描作业在独立 `worker` 进程：`python -m app.worker`） | 可用 |
| 私有化 | `scripts/preflight.py` + 离线包 | 需按客户环境验证 |

## 业务验收台账（T-005：当前 blocked）

真实企业试运行在本沙箱阶段被推迟（2026-09-16 决策），两张台账保持空置，**禁止**把测试或演示任务写进去：

```bash
uv run python -m work.pilot_ledger --render-review    # outputs/pilot-ledger.csv
uv run python -m work.icp_ledger --render-review      # outputs/icp-outreach.csv
# 收到真实输入后：
uv run python -m work.pilot_ledger --row-json work/pilot-row.json
uv run python -m work.icp_ledger --row-json work/icp-row.json
```

缺少 `task_id` 或表头不匹配时命令会拒绝写入。

## 仓库卫生与保密

- 真实上传材料不得进入 Git：`work/uploads/*`、`work/backups/`、`work/restore-drill-*/uploads/` 已被 `.gitignore` 拦截。
- 第三方克隆、训练语料二进制、交付 zip/tgz、覆盖率与日志同样不入库（见 `.gitignore` 尾部 2026-09-23 段）。
- 2026-09-23 做过一次过期内容清扫，被移出仓库的文件暂存于本地隔离区 `_cleanup-archive-2026-09-23/`（已被忽略），确认无误后可整体删除。
- 禁止提交 `.env`、tunnel token、密钥、大文件；禁止无页码引用判定 `PASS`；禁止未验证就宣称「生产就绪」或「企业已验收」。

## 已知边界

- 输入支持可检索文字的中文 PDF/DOCX/XLSX/PPTX/TXT/MD 及企业证据文件；旧版二进制 Office（DOC/XLS/PPT）需先转换为现代 OOXML 格式。
- 不自动生成或提交标书、不自动报价、不提供法律意见、不执行外部操作；人工决策只记录 `CONTINUE`/`HOLD`/`STOP`。
- 准确度指标按 `TEST`/`PILOT`/`ENTERPRISE` 数据集隔离，反馈行未完成复核时保持 `INSUFFICIENT`。
- 面向国内政企的境内节点与等保测评是独立交付线，不在本 Render 部署内完成；ISO 27001 认证未启动，差距清单见 [docs/iso27001-gap.md](docs/iso27001-gap.md)。
- 2026-09-23 的前端交接代码包（见 `outputs/handover-2026-09-23/`）**尚未合并**：它整页替换详情视图，与 C-022 的回退决定冲突，需要产品与技术共同裁决后再定合并方式。

## 相关文档

- 文档索引：[docs/README.md](docs/README.md)｜用户手册：[docs/user-guide.md](docs/user-guide.md)｜API 集成：[docs/api-integration.md](docs/api-integration.md)
- 控制面：[workflow/master-brief.md](workflow/master-brief.md)（目标与边界）、[workflow/agent-operating-instructions.md](workflow/agent-operating-instructions.md)（执行循环）、[workflow/roadmap.md](workflow/roadmap.md)
- Agent 启动顺序：`workflow/project-state.json` → `workflow/master-brief.md` → `workflow/agent-operating-instructions.md` → `uv run python -m app.workflow check`
