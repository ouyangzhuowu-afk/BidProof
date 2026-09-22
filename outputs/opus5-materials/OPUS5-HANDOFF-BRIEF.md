# BidProof · 给 Opus 5 的评估材料简报（清单逐条答复）

**用途**：回答「所需材料清单」P0 / P1 / P2 每一项。  
**生成日期**：2026-09-04（UTC+8）  
**代码版本**：GitHub `main` @ `848a220`（材料提交）/ 功能基线 `f6112be`  
**仓库**：https://github.com/ouyangzhuowu-afk/BidProof  
**公网试点**：https://bidproof.marketcase.net/（`/healthz`、`/app`）  
**配套源码包**：`BidProof-opus5-analysis-20260904-0136.zip`（含 `.env.example` 与本目录全部附件）

**诚实边界**：下列标注为「代码/部署可证」「实测」「书面目标」「未定稿/无法提供」。未定稿项请勿按生产承诺评分。

---

# 三、所需材料清单 · 逐条答复

## P0 · 缺失将导致对应维度无法给出可信分数

### P0-1. `.env.example` 或完整环境变量清单

**状态：已提供**

#### 权威模板（仓库根目录 `.env.example` 全文）

```env
# Copy to .env for local/docker runs (do not commit .env)
BIDPROOF_ENV=development
BIDPROOF_DATA_ROOT=

# Leave empty to use the SQLite file under BIDPROOF_DATA_ROOT. PostgreSQL is recommended for
# production; SQLite has a single-writer model and does not survive concurrent load.
#   postgresql+psycopg://bidproof:PASSWORD@postgres:5432/bidproof
BIDPROOF_DATABASE_URL=

# Required by docker-compose when the bundled PostgreSQL service is used.
POSTGRES_PASSWORD=

# Personal self-registration creates an isolated workspace owned by the new account.
# Set to 0 for enterprise-only installs that only allow bootstrap, invite, trial-join, or SSO.
BIDPROOF_PERSONAL_SIGNUP=1

# Leave empty to keep self-service trial join disabled. Generate a unique value per
# deployment; anyone holding it can create a REVIEWER account in the primary workspace.
BIDPROOF_TRIAL_JOIN_CODE=

# Required to bootstrap the first OWNER when BIDPROOF_ENV=production.
BIDPROOF_BOOTSTRAP_TOKEN=

# Test-harness only. Ignored unless BIDPROOF_ENV=test, because self-asserted identity
# headers would let any caller claim any workspace and role.
BIDPROOF_ALLOW_TRUSTED_HEADERS=0

# Job runner. Tests and local development stay `inline` so POST /api/jobs finishes in-process.
# Production compose sets this to `worker` and runs `python -m app.worker`.
BIDPROOF_JOB_RUNNER=inline
BIDPROOF_JSON_LOGS=0
BIDPROOF_METRICS=0
BIDPROOF_OTEL=0

# Optional on-prem license gate. Empty means the process starts without a key.
BIDPROOF_LICENSE_KEY=
BIDPROOF_LICENSE_REQUIRED=0

# Optional OpenID Connect. Local password login remains available as a fallback.
# BIDPROOF_OIDC_ISSUER=https://login.example.com/realms/company
# BIDPROOF_OIDC_CLIENT_ID=
# BIDPROOF_OIDC_CLIENT_SECRET=
# BIDPROOF_OIDC_SCOPES=openid profile email
# BIDPROOF_OIDC_USERNAME_CLAIM=preferred_username
# BIDPROOF_OIDC_DEFAULT_ROLE=REVIEWER

# Optional LDAP / Active Directory bind. Username is substituted into the DN template
# and rejected if it contains DN metacharacters.
# BIDPROOF_LDAP_URI=ldaps://directory.example.com
# BIDPROOF_LDAP_USER_DN_TEMPLATE=uid={username},ou=people,dc=example,dc=com
# BIDPROOF_LDAP_BASE_DN=dc=example,dc=com
# BIDPROOF_LDAP_ROLE_ATTRIBUTE=
# BIDPROOF_LDAP_DEFAULT_ROLE=REVIEWER
# BIDPROOF_LDAP_USE_TLS=1
```

#### 公网试点实际生效配置（`render.yaml`，非密钥明文）

| 变量 | 试点值 |
|---|---|
| `BIDPROOF_ENV` | `production` |
| `BIDPROOF_DATA_ROOT` | `/data` |
| `BIDPROOF_JOB_RUNNER` | `inline` |
| `BIDPROOF_PERSONAL_SIGNUP` | `1` |
| `BIDPROOF_JSON_LOGS` | `1` |
| `BIDPROOF_TRIAL_JOIN_CODE` | `BidProof-Trial-2026` |
| `BIDPROOF_BOOTSTRAP_TOKEN` | Render `generateValue`（不在仓库） |
| `DATABASE_URL` | 来自 Postgres 服务 `bidproof-db` 的 connectionString |

#### 补充说明（代码常量，非 env）

- Session Cookie：`bidproof_session`，**12 小时**，HttpOnly，SameSite=Strict，HTTPS 时 Secure  
- 无 JWT refresh；到期重新登录  
- PaaS 同时认 `DATABASE_URL` 与 `BIDPROOF_DATABASE_URL`，并把 `postgres://` 规范为 `postgresql+psycopg://`

---

### P0-2. 数据库真实形态与规模

**状态：形态已确认；规模为试点早期数量级（无大规模生产遥测）**

| 环境 | 引擎 | 证据 |
|---|---|---|
| **公网试点** | **PostgreSQL（Render Free，region=singapore）** | `render.yaml` → `databases: bidproof-db` + `DATABASE_URL fromDatabase` |
| 本机开发 / CI | SQLite（默认） | `BIDPROOF_DATABASE_URL` 为空 → `work/data/bid_agent.sqlite3` |
| docker-compose | PostgreSQL（可选） | `POSTGRES_PASSWORD` + compose 服务 |

**核心表行数量级（截至材料生成日的业务事实）：**

| 指标 | 答复 |
|---|---|
| 真实企业扫描任务（业务台账） | **0**（`AGENTS.md`：T-005 阻塞于「尚无首批真实企业任务」；禁止用 demo 冒充） |
| 工程可写入的 runs/jobs/audit | 试点库可能有自测/试用账号产生的少量行；**未做运维侧 `COUNT(*)` 导出**，不能伪造成千上万 |
| 单租户最大文档数硬上限 | **无**；有上传体积与类型校验 |
| 日均扫描任务数 | **无生产日活遥测**；当前不按「日均」承诺容量 |

**评分建议**：按「PostgreSQL 试点 + 近似零真实业务负载」计，不要按「已有企业生产库规模」计。

---

### P0-3. 前端运行时性能实测

**状态：已提供（CDP + 构建产物；非完整 Lighthouse JSON）**

测量 URL：`https://bidproof.marketcase.net/app`（2026-09-04）

| 指标 | 数值 |
|---|---|
| **FCP** | **1344 ms** |
| DOMContentLoaded | 1339 ms |
| Load | 1339 ms |
| responseStart（文档） | 945 ms |
| `/app` 端到端耗时（脚本侧） | ~526 ms |
| `static/app.js` raw | 80,519 B（78.6 KB） |
| **`static/app.js` gzip** | **19,923 B（≈19.5 KB）** |
| `app.js` 网络 transferSize | ≈20.9 KB |
| `style.css` 网络 transferSize | ≈12.9 KB |
| **`Cache-Control`（静态 JS）** | **`max-age=14400`**（Cloudflare `cf-cache-status=HIT`） |
| HTML `/app` Cache-Control | 未设置长期缓存（动态页） |

构建方式：Vite + esbuild minify（保留 UI 契约函数名）。  
完整 Lighthouse：本次未出 JSON；可用 `npx lighthouse https://bidproof.marketcase.net/app --only-categories=performance` 复现。

附件：`FRONTEND-PERF.md`、登录页截图 `screenshots/login-dialog.png`。

---

### P0-4. 3 年业务目标数字

**状态：仅有 45 天书面目标；3 年规模未定稿**

#### 已写入 `workflow/master-brief.md` 的目标（可引用）

| 窗口 | 数字 |
|---|---|
| 45 天 ICP 接触 | **30** 个明确 ICP |
| 真实任务验收 | **10** 个真实任务（非 demo） |
| 付费意愿 | **至少 2–3** 个 |
| 失败动作 | 未达标则暂停扩功能、重定 ICP |

**明确不做（同文件）**：未经验证的生产部署承诺、多租户商业化、法规达标声明等。

#### 3 年目标（租户 / 并发 / 日扫描峰值 / SLA / SaaS:私有化）

| 项 | 答复 |
|---|---|
| 目标租户数 | **未定稿** |
| 并发用户数 | **未定稿** |
| 日扫描量峰值 | **未定稿** |
| SLA | **未承诺**（当前为 Render Free 试点，冷启动约 15 分钟 idle） |
| SaaS : 私有化占比 | **未定稿**（代码同时支持 SaaS 形态与私有化 Docker/许可证门控） |

**供「100 倍流量崩溃点」推演时的工程事实（非业务承诺）：**

- 试点：`BIDPROOF_JOB_RUNNER=inline`（作业跑在 Web 进程内）  
- 写限流 240/60s；导出 30/5min；登录 5/15min  
- Session 12h  
- Free 档冷启动与内存上限会先于「算法」成为瓶颈  

若必须用假设做推演，请标注 **「规划假设·非承诺」**，建议试点档：≤20 租户 / 日扫描 <50 / 以 POC/私有化试用为主。

---

### P0-5. 合规制度类文件

**状态：产品内嵌声明可证；正式法务/等保/ISO 无法提供**

| 项 | 答复 |
|---|---|
| 隐私政策全文 | **无独立法务全文** |
| 前端入口 | 登录后「设置 → 用量与隐私」；内容来自 `GET /api/workspace/privacy` |
| 数据留存与删除 | 默认归档保留 **365** 天（可配 1–3650）；`/api/retention/preview` + `/api/retention/purge`；永久删除移除任务/评论/反馈/作业/上传文件；备份需单独处理 |
| 是否收集身份证/手机号 | **认证路径不强制收集**（用户名+密码；可选 OIDC/LDAP）。上传的投标材料**可能含敏感信息，属客户自带数据** |
| 数据存储地域 | 试点：**新加坡（Render Singapore）** |
| 等保三级 / ISO 27001 | **未启动，无证书/测评材料** |

**内嵌声明原文（代码）：**

> BidProof 不提供法律意见 (not legal advice)；上传内容按企业数据处理，权限和保留策略由企业管理员配置。  
> 永久删除会移除任务、评论、反馈、作业和上传文件；备份副本需按运维策略单独处理。

---

## P1 · 强烈建议

### P1-1. 演示账号 / 核心链路录屏

**状态：可自助试用；无 OWNER 密码随材料分发；无现成录屏文件**

| 项 | 内容 |
|---|---|
| 公网入口 | https://bidproof.marketcase.net/app |
| 试用加入码 | `BidProof-Trial-2026`（创建 REVIEWER 加入主企业空间） |
| 个人注册 | 开启（`BIDPROOF_PERSONAL_SIGNUP=1`）→ 独立工作区 OWNER |
| 录屏 | **材料包内无视频**；链路应为：上传 → 扫描作业 → 人工复核 → 决策 → 报告导出 |

### P1-2. 最近一次 CI 全量 + pytest --cov

**状态：已提供（本地全量等价于 CI 测试步骤）**

| 项 | 结果 |
|---|---|
| 日期 | 2026-09-04 |
| 结果 | **183 passed，11 skipped** |
| 覆盖率 | **`app` 合计 82%**（3845 statements，675 missed） |
| 偏低模块 | `auth_service` 63%；`workflow` 57%；`worker` 0%（worker 路径未在默认测试中跑） |
| CI 定义 | `.github/workflows/ci.yml`：push/PR → install → `workflow check` → migrations → `pytest -q` |
| 附件 | `pytest-cov.json` |

### P1-3. 依赖漏洞扫描与 SAST

| 项 | 结果 |
|---|---|
| `pip-audit -r requirements.txt` | **No known vulnerabilities found**（26 packages） |
| 附件 | `pip-audit.json` |
| SAST（CodeQL/Bandit 等） | **未跑**；仓库无固定 SAST 流水线 |

### P1-4. 压测数据

**状态：无法提供**

无 k6/locust 脚本与结果。当前试点为 inline runner + Free 冷启动，压测结论若出现，也应标明「非生产 worker 架构」。

### P1-5. Git 提交历史（zip 无 .git）

**状态：已导出**

- 总提交数：**21**  
- 附件：`git-log.txt`、`git-hotspots.tsv`

**变更热点（次数↓）：**

| 次数 | 文件 |
|---|---|
| 8 | README.md |
| 7 | static/index.html |
| 6 | static/app.js、static/style.css、app/db.py、app/main.py、.env.example、tests/test_ui_product_contract.py |
| 5 | tests/test_auth_lifecycle.py、docker-compose.yml |
| 4 | Dockerfile、app/config.py、app/schemas.py、app/services/auth_service.py、CI、pyproject.toml 等 |

### P1-6. SSO 实际对接与 JWT/Session 策略

| 项 | 答复 |
|---|---|
| 已对接 IdP 清单 | **无**（代码支持可选 OIDC + LDAP，试点未配置） |
| Session | Cookie `bidproof_session`，**12h**，HttpOnly，SameSite=Strict，Secure@HTTPS |
| JWT / Refresh | **无应用层 JWT 会话刷新**；OIDC 校验标准 ID Token 声明（含 exp） |
| MFA | 可选 TOTP + 恢复码 |
| API Token | 仅存 SHA-256 摘要；明文创建时显示一次 |

### P1-7. 生产日志样例与监控截图

| 项 | 答复 |
|---|---|
| 日志形态 | 生产 `BIDPROOF_JSON_LOGS=1` → structlog JSON；请求带 `x-request-id` |
| 监控截图 / 错误率 / P95 | **无法提供**（无 APM 面板导出） |
| 可选指标端点 | `BIDPROOF_METRICS=1` 时暴露 `/metrics`（试点默认关） |

---

## P2 · 有则更好

| 项 | 答复 |
|---|---|
| 试点客户原始反馈与异议清单 | 台账模板存在（`work/icp_*`、`outputs/icp-outreach*`）；**真实企业反馈行为空**（规则禁止写入 demo） |
| 定价套餐与配额 | **无** |
| 研发团队规模与迭代节奏 | 仓库内为 **Planner → Executor → Reviewer** 控制面（`workflow/`），**非人头编制表**；当前优先 T-005 真实任务验收 |

---

## 给 Opus 5 的评分使用说明（请务必阅读）

1. **配置治理**：以 `.env.example` + `render.yaml` 为准，可评密钥分离与环境闸门。  
2. **架构伸缩**：按「Postgres 试点 + inline jobs + Free 冷启动」评，勿假设已有独立 worker 集群。  
3. **业务规模**：「真实企业任务 = 0」是当前阶段事实，不是隐瞒；45 天目标见 master-brief。  
4. **合规**：只能评「产品内嵌边界与留存能力」，不能评「已通过等保/ISO」。  
5. **性能**：可用 FCP≈1.3s、app.js gzip≈19.5KB、静态 `max-age=14400`；完整 Lighthouse 未附。  
6. **安全工程**：pytest 183 绿、覆盖率 82%、pip-audit 0 洞；无压测、无 SAST、无生产 APM。

---

## 附件索引（同目录）

| 文件 | 内容 |
|---|---|
| `ENV-VARIABLES.md` | 环境变量表 |
| `FRONTEND-PERF.md` | 性能实测细节 |
| `pytest-cov.json` | 覆盖率原始数据 |
| `pip-audit.json` | 漏洞扫描原始数据 |
| `git-log.txt` / `git-hotspots.tsv` | 提交历史与热点 |
| `screenshots/login-dialog.png` | 登录入口截图 |
| `EVALUATION-MATERIALS.md` | 材料回执（过程版） |
| `HUMAN-INPUT-NEEDED.md` | 若产品方后续补数字的填空表 |
