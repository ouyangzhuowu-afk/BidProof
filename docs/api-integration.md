# BidProof API 集成说明

当前稳定面为 `/api/*`（语义上即 v1）。生产环境关闭 `/docs` 与 `/openapi.json`。

## 认证

| 方式 | 说明 |
|---|---|
| Session Cookie | `POST /api/auth/login` 后设置 `bidproof_session`（12 小时，HttpOnly，SameSite=Strict） |
| CSRF | 写操作需 `X-CSRF-Token` 与 cookie 双提交；Bearer 令牌路径豁免 |
| API Token | `Authorization: Bearer bp_…`；明文只在创建时显示一次 |
| 试用加入 | `POST /api/auth/trial-join`，需环境变量 `BIDPROOF_TRIAL_JOIN_CODE` |

### 获取令牌（已登录 OWNER/ADMIN）

```bash
curl -sS -X POST "$HOST/api/auth/tokens" \
  -H "X-CSRF-Token: $CSRF" \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"name":"ci","role":"REVIEWER"}'
```

## 限流与 Retry-After

| 范围 | 默认 |
|---|---|
| 登录失败 | 5 / 15 分钟 |
| MFA | 8 / 5 分钟 |
| Token 校验失败 | 20 / 5 分钟 |
| 写接口 | 240 / 60 秒 |
| 导出 | 30 / 5 分钟 |

超限返回 **429**，带 `Retry-After` 秒数。

## 错误形态

JSON `{"detail": "…"}`。常见状态：401 未登录、403 无权限/CSRF、409 冲突、413 文件过大、422 校验失败、429 限流。

## 快速上手（curl）

```bash
# 健康检查（匿名）
curl -sS "$HOST/healthz"

# 登录
curl -sS -c cookies.txt -X POST "$HOST/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"owner","password":"your-password"}'

# 列出任务
curl -sS -b cookies.txt "$HOST/api/runs"
```

无 Webhook。作业进度请轮询 `GET /api/jobs/{job_id}`（`progress_current` / `progress_total` / `progress_message`）。

公开隐私页：`GET /privacy`（HTML）。机器可读：`GET /api/privacy`。
作业进度：`GET /api/jobs/{id}/events`（SSE），或轮询 `GET /api/jobs/{id}`。
API 版本：`/api/v1/*` 与 `/api/*` 等价；`GET /api/v1/healthz` 映射到 `GET /healthz`。
写接口可携带 `Idempotency-Key`（JSON 成功响应会被缓存）。
登录设备：`GET /api/auth/sessions`、`DELETE /api/auth/sessions/{id}`、`POST /api/auth/sessions/revoke-others`。
审计链：`GET /api/audit/chain`；只追加导出：`GET /api/audit/export`（OWNER/ADMIN）。
