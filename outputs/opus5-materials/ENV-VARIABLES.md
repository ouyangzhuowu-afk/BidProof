# BidProof 环境变量清单

权威模板：仓库根目录 `.env.example`。下表为评分用摘要。

## 核心运行

| 变量 | 默认 / 试点值 | 作用 |
|---|---|---|
| `BIDPROOF_ENV` | `development` / 试点 `production` | 环境闸门（信任头、CSRF、作业 runner 默认） |
| `BIDPROOF_DATA_ROOT` | 空 → `work/data` / 试点 `/data` | 上传、备份、SQLite、job-staging 根目录 |
| `BIDPROOF_DATABASE_URL` | 空 → SQLite | 显式库连接串 |
| `DATABASE_URL` | Render 注入 | PaaS 标准别名；`app/database.py` 同样读取并规范为 `postgresql+psycopg://` |
| `POSTGRES_PASSWORD` | compose 用 | 仅 docker-compose 捆绑 Postgres |
| `BIDPROOF_JOB_RUNNER` | 非生产 `inline`；生产默认 `worker`；**Render 试点强制 `inline`** | 作业执行形态 |
| `BIDPROOF_JOB_STALE_SECONDS` | `900` | 僵死作业回收 |
| `BIDPROOF_JOB_POLL_SECONDS` | `1` | worker 轮询间隔 |
| `BIDPROOF_JSON_LOGS` | 生产默认开 | structlog JSON |
| `BIDPROOF_METRICS` | `0` | `/metrics` |
| `BIDPROOF_OTEL` | `0` | OpenTelemetry |

## 认证与引导

| 变量 | 说明 |
|---|---|
| `BIDPROOF_BOOTSTRAP_TOKEN` | 生产首个 OWNER 初始化令牌（Render `generateValue`） |
| `BIDPROOF_PERSONAL_SIGNUP` | `1` 允许个人注册独立工作区；企业专属部署可 `0` |
| `BIDPROOF_TRIAL_JOIN_CODE` | 非空则开放「试用加入」进入主企业空间（默认 REVIEWER） |
| `BIDPROOF_ALLOW_TRUSTED_HEADERS` | **仅 `BIDPROOF_ENV=test` 生效**；生产忽略 |
| `BIDPROOF_ENFORCE_CSRF` | 可强制测试环境也验 CSRF |
| `BIDPROOF_ENFORCE_WRITE_LIMITS` | 可强制测试环境也验写限流 |

## 许可证

| 变量 | 说明 |
|---|---|
| `BIDPROOF_LICENSE_KEY` | 可选 on-prem 许可证 |
| `BIDPROOF_LICENSE_REQUIRED` | `1` 则无密钥拒绝启动 |

## SSO（可选，默认注释）

| 变量 | 说明 |
|---|---|
| `BIDPROOF_OIDC_ISSUER` | OIDC Issuer |
| `BIDPROOF_OIDC_CLIENT_ID` / `CLIENT_SECRET` | 客户端凭证 |
| `BIDPROOF_OIDC_SCOPES` | 默认 `openid profile email` |
| `BIDPROOF_OIDC_USERNAME_CLAIM` | 默认 `preferred_username` |
| `BIDPROOF_OIDC_DEFAULT_ROLE` | 默认 `REVIEWER` |
| `BIDPROOF_LDAP_URI` | LDAP/AD |
| `BIDPROOF_LDAP_USER_DN_TEMPLATE` | DN 模板（拒绝含 DN 元字符的用户名） |
| `BIDPROOF_LDAP_BASE_DN` / `ROLE_ATTRIBUTE` / `DEFAULT_ROLE` / `USE_TLS` | LDAP 其余项 |

## Session（代码常量，非 env）

- Cookie 名：`bidproof_session`
- 有效期：`SESSION_HOURS = 12`（`app/identity.py`）
- 无 refresh token；到期重新登录
