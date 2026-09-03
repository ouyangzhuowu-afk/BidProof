# BidProof · Opus 5 评估材料清单回执

生成时间：2026-09-04（UTC+8）  
Git HEAD：`f6112bef5803cf43cd535b268890bac70f34a1da`  
公网试点：https://bidproof.marketcase.net/

本文件按 P0 / P1 / P2 逐条标注：**已提供证据** / **部分可证** / **需人工补充**。

---

## P0 · 缺失将导致对应维度无法给出可信分数

### 1. `.env.example` / 环境变量清单 — **已提供**

| 项 | 说明 |
|---|---|
| 仓库文件 | `.env.example`（仓库根目录，2325 bytes） |
| 上次 zip 缺陷 | 打包时 `/XF .env .env.*` 误排除了 `.env.example`；**本包已修正** |
| README 引用 | `README.md` L97：`环境变量见 .env.example` |
| 补充清单 | 见同目录 `ENV-VARIABLES.md` |

关键变量（试点 Render Blueprint `render.yaml`）：

- `BIDPROOF_ENV=production`
- `BIDPROOF_DATA_ROOT=/data`
- `BIDPROOF_JOB_RUNNER=inline`
- `BIDPROOF_PERSONAL_SIGNUP=1`
- `BIDPROOF_JSON_LOGS=1`
- `BIDPROOF_TRIAL_JOIN_CODE=BidProof-Trial-2026`
- `BIDPROOF_BOOTSTRAP_TOKEN`（Render `generateValue`）
- `DATABASE_URL` ← Render Postgres `bidproof-db` connectionString

---

### 2. 数据库真实形态与规模 — **部分可证（形态已确认；行数需运维查询）**

| 环境 | 引擎 | 证据 |
|---|---|---|
| 公网试点（Render） | **PostgreSQL**（Free，Singapore） | `render.yaml` `databases: bidproof-db` + `DATABASE_URL fromDatabase`；应用侧 `app/database.py` 将 `postgres://` 规范为 `postgresql+psycopg://` |
| 本机开发 / CI | **SQLite**（默认） | `BIDPROOF_DATABASE_URL` 为空时用 `BIDPROOF_DATA_ROOT/bid_agent.sqlite3` |
| Docker Compose | PostgreSQL（可选） | `docker-compose.yml` + `POSTGRES_PASSWORD` |

**行数量级（试点）— 需人工用 Render Shell / `psql` 执行：**

```sql
SELECT 'runs' AS t, COUNT(*) FROM runs
UNION ALL SELECT 'scan_jobs', COUNT(*) FROM scan_jobs
UNION ALL SELECT 'audit_events', COUNT(*) FROM audit_events
UNION ALL SELECT 'workspaces', COUNT(*) FROM workspaces
UNION ALL SELECT 'users', COUNT(*) FROM users;
```

**业务边界（代码可证，非生产实测）：**

- 单租户最大文档数：**无硬编码上限**；上传有体积与文件类型校验（`app/uploads.py` / `app/file_safety.py`）。
- 日均扫描任务数：**无生产遥测**；当前处于 T-005 真实任务验收前，**真实企业任务数 = 0（不可用 demo 冒充）**（见 `AGENTS.md` / `workflow/project-state.json`）。
- 工作区用量 API：`GET /api/workspace/usage` 返回 `runs` / `scan_jobs` / `remediations` / `audit_events`（登录后可在「设置 → 用量与隐私」查看）。

---

### 3. 前端运行时性能实测 — **已提供（非完整 Lighthouse，含 Web Vitals 替代）**

测量对象：`https://bidproof.marketcase.net/app`（2026-09-04，已登录会话浏览器 CDP）

| 指标 | 数值 | 来源 |
|---|---|---|
| FCP | **1344 ms** | `PerformanceObserver` / paint timing |
| DOMContentLoaded | **1339 ms** | Navigation Timing |
| Load | **1339 ms** | Navigation Timing |
| TTFB（`/app`，冷请求近似） | **~526 ms** | PowerShell `Invoke-WebRequest` stopwatch |
| `static/app.js` raw | **80,519 B（78.6 KB）** | 本地构建产物 |
| `static/app.js` gzip（本地 Optimal） | **19,923 B（19.5 KB）** | .NET GZipStream |
| `static/app.js` 网络 transferSize | **~20.9 KB** | CDP resource timing |
| `static/style.css` 网络 transferSize | **~12.9 KB** | CDP resource timing |
| `Cache-Control`（`/static/app.js`） | **`max-age=14400`** | 响应头；`cf-cache-status=HIT` |
| HTML `/app` Cache-Control | **未设置**（动态页，合理） | 响应头 |

说明：未跑完整 Chrome Lighthouse CLI（本机未装）；上表足以支撑 FCP/体积/缓存维度。完整 Lighthouse 可本地执行：

```bash
npx lighthouse https://bidproof.marketcase.net/app --only-categories=performance --view
```

产物文件：`FRONTEND-PERF.md`（同目录）。

---

### 4. 3 年业务目标数字 — **部分可证（仅有 45 天试点目标；3 年规模需人工定稿）**

来自 `workflow/master-brief.md`（**已验证的书面目标**）：

| 窗口 | 目标 |
|---|---|
| 45 天 ICP | 接触 30 个明确 ICP |
| 真实任务 | 完成 10 个真实任务（非 demo） |
| 付费意愿 | 至少 2–3 个 |
| 失败门槛 | 未达则暂停扩展功能，重定 ICP |

**明确不做（同文件）：** 生产部署承诺、多租户商业化、法规达标声明等未经验证的市场承诺。

**3 年租户 / 并发 / 日扫描峰值 / SLA / SaaS:私有化占比 — 仓库内无定稿数字。**  
评分时请勿把「100 倍流量崩溃点」写成已承诺容量；当前工程形态为：

- Render Free：冷启动 ~15 min idle、inline job runner、512MB 级内存假设
- Session：12h cookie（`app/identity.py` `SESSION_HOURS = 12`）
- 写限流：240/60s；导出：30/5min；登录：5/15min（`app/ratelimit.py`）

若需推演假设，建议标注为 **「规划假设·非承诺」**，例如试点档：≤20 租户 / 日扫描 <50 / 私有化 POC 为主。

---

### 5. 合规制度类文件 — **部分可证（产品内嵌声明；无正式法务全文 / 无等保 ISO）**

| 项 | 状态 | 证据 |
|---|---|---|
| 隐私政策全文 | **无独立法务全文**；有工作区 API 声明 | `GET /api/workspace/privacy` → `workspace_service.privacy()` |
| 前端入口 | 「设置 → 用量与隐私」展示 `boundary` / `deletion` / 保留天数 | `static/index.html` `#workspace-privacy`；截图见 `screenshots/` |
| 数据留存与删除 | **可配置归档保留天数**（默认 365，范围 1–3650）+ `retention/preview` + `retention/purge` | `app/schemas.py` / `app/api/admin.py` |
| 身份证 / 手机号 | **代码路径不强制收集**；登录字段为用户名+密码；OIDC/LDAP 可选 | `app/schemas.py` auth；上传物为企业投标 PDF/Office，**可能含敏感信息属客户自带数据** |
| 数据存储地域 | 试点：**Render Singapore**（`render.yaml` `region: singapore`） | 文件 + DB 同区 |
| 等保三级 / ISO 27001 | **未启动 / 无证书材料** | — |

内嵌边界文案（代码原文）：

> BidProof 不提供法律意见 (not legal advice)；上传内容按企业数据处理，权限和保留策略由企业管理员配置。  
> 永久删除会移除任务、评论、反馈、作业和上传文件；备份副本需按运维策略单独处理。

---

## P1 · 强烈建议

### 演示账号 / 核心链路录屏 — **需人工补充**

试点试用加入码（非万能管理员）：`BIDPROOF_TRIAL_JOIN_CODE=BidProof-Trial-2026`（见 `render.yaml` / `AGENTS.md`）。  
**不在材料中写入生产 OWNER 密码。** 录屏请自备：上传 → 扫描 → 复核 → 导出。

### 最近一次 CI + pytest --cov — **已提供（本地全量）**

| 项 | 结果 |
|---|---|
| 本地全量 | **183 passed, 11 skipped**（2026-09-04） |
| 覆盖率 | **`app` TOTAL 82%**（3845 stmts，675 miss） |
| JSON | `outputs/pytest-cov.json` |
| GitHub Actions | 本机无 `gh` CLI；workflow 见 `.github/workflows/ci.yml`（push/PR → pytest -q） |

覆盖率偏低模块（供评分）：`auth_service` 63%、`workflow` 57%、`worker` 0%（worker 路径在 CI 未跑）。

### 依赖漏洞扫描 — **已提供**

```
pip-audit -r requirements.txt
→ No known vulnerabilities found（26 packages）
```

报告：`outputs/pip-audit.json`。  
SAST：仓库无固定 CodeQL/Bandit 流水线；**本次未跑 SAST**。

### 压测 — **未提供**

无 k6/locust 脚本与结果。当前限流与 inline runner 意味着压测前应先换 worker 部署形态。

### Git 提交历史 — **已提供（导出，因 zip 不含 .git）**

- `git-log.txt`：完整 oneline 历史（21 commits）
- `git-hotspots.tsv`：文件变更频次 Top（`README.md` 8、`static/index.html` 7、`app/db.py` 6、`static/app.js` 6…）

### SSO / Session 策略 — **部分可证**

| 项 | 值 |
|---|---|
| 实际对接 IdP | **无生产对接清单**；代码支持可选 OIDC + LDAP |
| Session | Cookie `bidproof_session`，**12 小时**，HttpOnly，SameSite=Strict，HTTPS 时 Secure |
| 刷新策略 | **无 refresh token 轮换**；到期需重新登录 |
| MFA | TOTP + 恢复码（可选绑定） |
| API Token | SHA-256 摘要存储，创建时明文只显示一次 |

### 生产日志 / 监控 — **部分可证**

- `BIDPROOF_JSON_LOGS=1`（生产）→ structlog JSON
- `/metrics` 可选（`BIDPROOF_METRICS`）
- **无**托管 APM 截图 / 错误率 / P95 面板（Render Free 无现成截图）

---

## P2 · 有则更好

| 项 | 状态 |
|---|---|
| 试点客户原始反馈 | ICP 台账模板与 outreach CSV 存在（`work/icp_*`、`outputs/icp-outreach*`）；**真实企业反馈行仍为空**（规则禁止写入 demo） |
| 定价套餐与配额 | **无** |
| 研发团队规模与节奏 | 控制面为 Planner→Executor→Reviewer（`workflow/`）；**非人头编制说明** |

---

## 打包修正说明

上一版 `BidProof-opus5-analysis-20260903-0144.zip` / `20260904-0035.zip` 因 robocopy 排除规则遗漏 `.env.example`。  
新包必须包含：`.env.example`、`outputs/opus5-materials/**`、本回执文件。
