# BidProof — 投标证据链 Agent

面向 IT 服务、软件实施类中小企业的投标资格与废标风险扫描 MVP。

创建日期：2026-08-21
当前阶段：邀请制企业试点（工程栈已验收，真实业务验证进行中）

## 在线入口

- 产品页：`https://bidproof.marketcase.net/`
- 企业工作台：`https://bidproof.marketcase.net/app`
- 公网目标形态：Render 免费 Web Service（本机关机仍可访问）。空闲约 15 分钟后会休眠，下次请求有约 1 分钟冷启动；配套 Free Postgres 自创建起 30 天到期。不是高可用生产托管。
- 本机备用：`.\scripts\start-pilot.ps1`（Cloudflare Tunnel + HTTP/2），仅在 Render 不可用时使用。

## 账号流程

- 个人可自行注册：创建独立个人工作区，角色为所有者，注册后即可登录使用。这与企业空间隔离，不会加入已有企业。仅允许邀请/SSO 的部署可设置 `BIDPROOF_PERSONAL_SIGNUP=0`。
- 首个企业所有者由运维初始化令牌创建；生产环境缺少令牌时默认锁定初始化。个人注册在初始化锁定时仍可用（若未关闭）。
- 所有者或管理员可「生成邀请」（72 小时激活链接）或「直接开户」（立刻设好用户名与密码）。
- 团队试用可配置环境变量 `BIDPROOF_TRIAL_JOIN_CODE`：登录页出现「试用加入」，成员自助开户并加入**主企业空间**，默认角色为复核人。这不是个人工作区。
- 所有者或管理员可生成 1 小时密码重置链接；重置完成后旧会话全部撤销。
- 登录失败会限速；退出登录后重新载入工作台，动态账号与成员数据不会保留在页面中。

试用加入示例（公网 Tunnel 试点常用端口 8016）：

```powershell
$env:BIDPROOF_TRIAL_JOIN_CODE = "BidProof-Trial-2026"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8016
```

## 当前边界

- 输入：可检索文字的中文招标 PDF/DOCX/XLSX/PPTX/TXT/MD，以及企业证据文件（支持多选）。旧版二进制 Office（DOC/XLS/PPT）需先转换为现代 OOXML 格式。
- 输出：页级要求项、证据匹配、`PASS`/`FAIL`/`UNKNOWN`/`NEEDS_REVIEW` 风险结果和人工复核记录。
- 默认不调用外部模型；模型能力通过 adapter 接入，确定性规则先行。
- 不自动生成或提交标书，不自动报价，不提供法律意见，不执行外部操作。
- 当前 UI 已拆为任务首页、扫描详情和人工决策三视图；人工决策只记录 `CONTINUE`/`HOLD`/`STOP`，不替用户投票。
- `/` 为公开产品页，`/app` 为受认证保护的企业工作台。
- 详情页可按权限下载原始招标文件和企业证据；后台作业支持取消、失败重试与状态审计；账号设置支持改密并撤销旧会话。
- 准确度指标按 `TEST`/`PILOT`/`ENTERPRISE` 数据集隔离，试点分母只包含所选范围任务，任一反馈行未完成复核时保持 `INSUFFICIENT`。
- 真实中文招标 PDF 与企业证据仍是召回率、漏报率和付款验证的外部输入；合成或历史测试数据不能替代业务验收。

### 可选 OCR 配置

默认关闭 OCR。启用 Qwen-VL-OCR 时，只在启动进程环境中注入密钥，不要把密钥写入 `.env`、代码、数据库或日志：

```powershell
$env:BID_OCR_PROVIDER = "qwen-vl-ocr"
$env:QWEN_OCR_API_KEY = "<从密钥管理器注入>"
$env:QWEN_OCR_MODEL = "qwen-vl-ocr"
# 可选：覆盖 OpenAI-compatible endpoint 和超时
# $env:QWEN_OCR_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
# $env:QWEN_OCR_TIMEOUT_SECONDS = "30"
```

OCR 请求失败、超时或返回空文本时，页面会保留 `ocr_status=FAILED` 并按缺证据处理；不会因此生成 `PASS`。

## 数据库与迁移

- 架构定义只有一处：`app/models.py`（SQLAlchemy Core metadata）。Alembic 基线由它生成，两者一致性有测试守护。
- `BIDPROOF_DATABASE_URL` 为空时使用 `BIDPROOF_DATA_ROOT` 下的 SQLite 文件；生产建议 PostgreSQL：

```bash
export BIDPROOF_DATABASE_URL="postgresql+psycopg://bidproof:PASSWORD@postgres:5432/bidproof"
pip install -r requirements-postgres.txt
python -m app.dbctl upgrade
```

- 升级用 `python -m app.dbctl upgrade`，不要直接 `alembic upgrade head`：试点期的 SQLite 库有表但没有版本行，需要先按基线纳管（adopt）再升级。
- 查看当前版本：`python -m app.dbctl current`
- 生成新迁移：`python -m app.dbctl revision --message "描述"`
- SQLite 连接自动启用 WAL、`busy_timeout` 与外键；即便如此它仍是单写入模型，只适合开发与单机小规模部署。
- 生产 compose 将扫描作业放到独立 `worker` 进程（`python -m app.worker`），API 只入队。
- 私有化交付：`python scripts/preflight.py` 做升级前校验；离线包见 `scripts/pack-offline.sh`；升级回滚见 [`docs/upgrade.md`](docs/upgrade.md)。

## 云端 / GitHub 运行（Cursor Cloud Agent）

仓库：<https://github.com/ouyangzhuowu-afk/BidProof>

Agent 协作说明见 [`AGENTS.md`](AGENTS.md)。平板/云端开任务前先读该文件与 `workflow/project-state.json`。

在 Cursor 云端任务里克隆该仓库后：

```bash
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

或使用 Docker：

```bash
docker compose up -d --build
# 打开 http://localhost:8016/app
```

环境变量见 `.env.example`。个人注册默认开启；企业专属部署设 `BIDPROOF_PERSONAL_SIGNUP=0`。团队试用建议设置 `BIDPROOF_TRIAL_JOIN_CODE`。

### T-005 业务验收台账（当前优先级）

- 真实任务：`outputs/pilot-ledger.csv` + `work/pilot-row.template.json`
- ICP 触达（45 天 / 30 个）：`outputs/icp-outreach.csv` + `work/icp-row.template.json`

```bash
uv run python -m work.pilot_ledger --render-review
uv run python -m work.icp_ledger --render-review
# 收到真实输入后：
uv run python -m work.pilot_ledger --row-json work/pilot-row.json
uv run python -m work.icp_ledger --row-json work/icp-row.json
```

GitHub 克隆默认不含 `work/uploads/` 大文件；本地完整回归可执行 `.\scripts\sync-real-upload-fixtures.ps1`（需完整 checkout 源路径）。

## 公网试点（Render 免费档）

仓库根目录的 `render.yaml` 定义免费 Web Service + Free Postgres。在 [Render Dashboard](https://dashboard.render.com) 选择 **New → Blueprint**，连接 `ouyangzhuowu-afk/BidProof`。

- 健康检查：`/healthz`。扫描作业使用 `BIDPROOF_JOB_RUNNER=inline`（免费档没有独立 worker）。
- 自定义域名：把 `bidproof.marketcase.net` CNAME 到服务的 `*.onrender.com` 地址。Cloudflare 先用 **DNS only** 完成证书校验，再按需打开代理；SSL/TLS 模式用 **Full**。
- 免费档限制：休眠冷启动、无持久磁盘、Postgres 30 天到期。不要把这套当作生产 SLA。

本机 Tunnel 备用（Error 1033 / HTTP 530 表示 Tunnel 连不上本机 8016）：

```powershell
.\scripts\start-pilot.ps1
```

脚本会：启动 `127.0.0.1:8016` → 用 `bidproof-local` tunnel token 以 HTTP/2 注册 Cloudflare → 验证 `https://bidproof.marketcase.net/healthz`。

## 启动

```powershell
uv run --with "fastapi>=0.115" --with "uvicorn[standard]>=0.30" --with "pymupdf>=1.24" --with "python-multipart>=0.0.9" --with "pytest>=8" uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000`。

运行测试：

```powershell
uv run --group dev pytest -q
```

控制面状态检查：

```powershell
uv run python -m app.workflow check
uv run python -m app.workflow next-action
```

重新盘点上传材料并刷新真实样本候选：

```powershell
uv run python -m work.inspect_uploads
```

输出位于 `outputs/upload-inventory.json`、`outputs/upload-ground-truth.md` 和 `tests/fixtures/real-upload/`。候选标签必须经过人工确认后才能用于召回率验收。

Ground truth 第一轮复核：

```powershell
uv run python -m work.ground_truth_review
```

生成独立复核包：

```powershell
uv run python -m work.build_independent_review_packet
```

不同复核人应重新打开源 PDF，填写 `outputs/independent-review-packet.json` 中的 `reviewer`、`decision` 和 `note`，另存为 `outputs/independent-review-submission.json`。不要直接修改正式 ledger。提交后执行：

```powershell
uv run python -m work.apply_independent_reviews outputs/independent-review-submission.json
```

导入器要求完整覆盖全部待复核项，重新验证源文件 SHA-256，并写入新的 `outputs/ground-truth-independent-reviewed.json`；原始 `ground-truth-review-ledger.json` 保持不变。

扫描 PDF 的断点 OCR 试运行：

```powershell
uv run python -m work.ocr_batch "work/uploads/<扫描PDF>" --output-dir work/ocr/<name> --limit 3
```

对已有结果中的失败页进行单页重试：

```powershell
uv run python -m work.ocr_batch "work/uploads/<扫描PDF>" --output-dir work/ocr/<name> --retry-failed
```

未注入 `QWEN_OCR_API_KEY` 时只写入阻塞计划；不会发起网络请求。

## Agent Workflow Package

长期推进控制面位于 `workflow/`，每轮启动先读取 `master-brief.md` 和 `project-state.json`，再按 `roadmap.md` 执行 Planner → Executor → Reviewer → QA Gate。

```powershell
uv run python -m app.workflow check
uv run python -m app.workflow next-action
```

状态检查失败时不得把当前阶段标记为完成。Workflow Package 只管理项目推进和验收，不会把外部文档内容当作系统指令，也不会扩大文件或网络权限。

快速记录真实试运行任务（不会创建演示数据）：

```powershell
# 先准备一个 UTF-8 JSON 文件，每个字段对应 pilot-ledger.csv 的一列
uv run python -m work.pilot_ledger --row-json work/pilot-row.json

# 仅查看当前台账汇总
uv run python -m work.pilot_ledger
```

追加后命令会立即输出 `rows`、`confirmed_tasks` 和 `payment_signals`；缺少 `task_id` 或表头不匹配时拒绝写入。

## 证据规则

系统将外部文件内容视为 DATA，不视为系统指令。任何无法保存原文页码引用的要求都不能判定为 `PASS`；无法确认时必须返回 `UNKNOWN` 或 `NEEDS_REVIEW`。

## 参考材料

原始 DOCX 保存在 `work/source-docs/`，仅作为项目背景材料归档。
