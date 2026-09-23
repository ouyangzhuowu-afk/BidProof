# 身份与 HTTP 安全加固（2026-09-23）

本轮以隔离数据库与生成的签名密钥验证工程行为；未连接真实企业身份提供方，未部署到公网，也不代表真实招标/OCR业务验收通过。

## 已修复的边界

- API Token 必须显式选择至少一项权限。未知、空白或超过当前调用者权限的 scope 返回 422。认证时同时取签发角色、当前账号角色和显式 scope 的交集；降权、禁用和撤销立即生效，角色提升不会扩大旧令牌。旧的空 scope 令牌现在没有操作权限，应按所需最小权限重新签发。
- 请求 IP 仅使用 ASGI peer；应用不会直接信任 `X-Forwarded-For`、`X-Real-IP` 或 `X-Forwarded-Proto`。部署需在 Uvicorn 的 `--forwarded-allow-ips` 显式列出可信代理，且网络入口不得让客户端直连已被当作可信代理的地址。
- OIDC 先验证真实 RS256 / ES256 签名、JWKS key、issuer、audience、expiry、issued-at、subject、nonce 和多受众 azp，再认定身份。只接受 HTTPS discovery/token/JWKS；服务端请求拒绝重定向并限制响应为 1 MiB。未签名、算法混淆、未知 key、无效签名和失配 claims 均失败关闭。
- OIDC 登录 state 与发起浏览器的短期 HttpOnly Cookie 绑定，回调 URI 取配置的公开 origin。只有 issuer + subject 的既有绑定可以登录已有账号；名称碰撞不会自动接管本地账号。JIT 必须显式指定已有企业工作区，首次创建仅允许 REVIEWER / VIEWER。
- LDAP 登录只支持证书校验的 LDAPS，不支持明文 LDAP / 未验证的自签名证书 / 本轮未实现的 StartTLS。它沿用上述独立 subject 绑定与工作区限制。
- MFA 的 TOTP、恢复码和登录 flow 使用条件更新，竞争请求不能消费同一已验证快照两次；绑定确认受限流保护。
- 生产 Host allowlist、Secure Cookie、HSTS 与安全响应头生效；同源架构不开放跨域 CORS。CSP 的 script-src 只允许同源外链脚本，禁止 inline 脚本；style-src 暂保留 inline 以兼容既有组件。
- 未捕获异常返回稳定的 500 文案与 request_id，响应带关联 ID 和安全头；结构化访问日志提供 status_code、duration_ms。不会向客户端回显内部异常。

## 幂等能力的诚实边界

旧版幂等缓存既没有成功缓存真实响应，又以客户端 workspace 标头/IP 为键并在认证之前回放，不能安全修补为“只改类型判断”。本轮移除该执行路径。写入 API 只要携带 `Idempotency-Key` 就明确返回 501，且不执行写入；受到鉴权和 CSRF 校验约束。客户端不要自动重放写入，连接中断后先读取任务状态。持久化的幂等 schema 暂保留以兼容历史数据库，但无运行路径读写响应缓存。可靠的原子请求预占与结果回放需独立版本设计和并发验收。

## 新配置契约

| 配置 | 生产要求 |
|---|---|
| `BIDPROOF_ENV` | `production`，仅另外接受 development / test |
| `BIDPROOF_PUBLIC_ORIGIN` | 必须是完整 HTTPS origin，无路径、query、fragment或内嵌凭据，例如 `https://bid.example`；示例不是已部署域名 |
| `BIDPROOF_ALLOWED_HOSTS` | 逗号分隔的明确主机名，不得含通配符；须包含公开 origin 主机。内网探针所用 Host 也需列入 |
| `BIDPROOF_DATA_ROOT` | 必须显式配置持久化目录 |
| `BIDPROOF_JOB_RUNNER` | 生产必须 worker |
| `BIDPROOF_ALLOW_TRUSTED_HEADERS` | 生产不得启用；测试自报身份标头只在 test 有效 |
| `BIDPROOF_TRIAL_JOIN_CODE` | 生产必须为空；正式成员使用管理员邀请 |
| `BIDPROOF_BOOTSTRAP_TOKEN` | 如配置，至少 32 字符；未配置时已有账号可继续使用，空库不能匿名开通首位管理员 |
| `BIDPROOF_FEDERATED_WORKSPACE_ID` | 开启 OIDC / LDAP 时必须指定已存在、已有管理员的工作区 |
| `BIDPROOF_OIDC_ISSUER` / `BIDPROOF_OIDC_CLIENT_ID` | 开启时必须完整，issuer 为 HTTPS；client_secret 仅在服务器配置 |
| `BIDPROOF_OIDC_DEFAULT_ROLE` | REVIEWER 或 VIEWER |
| `BIDPROOF_LDAP_URI` / `BIDPROOF_LDAP_USER_DN_TEMPLATE` | 开启时必须完整；只支持证书验证 LDAPS，模板包含一个 `{username}` |

启动调用 `config.validate_runtime_security()` 会拒绝不安全配置。OIDC 使用 `PyJWT[crypto]>=2.10.1,<3`；没有依赖不会降级为仅解码 JWT。受众和签名算法不兼容的 IdP 会被拒绝。第三方 SSO 默认关闭，真实客户启用之前仍需使用其测试租户验证 key 轮换、注销、禁用用户、证书链与回调地址。

## 验证

新增 `tests/test_production_identity_hardening.py`，覆盖权限交集/降权/提升/失效、限制令牌再签发、旧空 scope、伪造代理头限流绕过、跨租户同名身份、低权限 JIT、实际 RSA 签名校验、浏览器绑定/重放、幂等拒绝、CSRF/认证优先级、生产配置与 Host、500 关联 ID、MFA快照条件消费。该文件与现有身份/生命周期/队列可观测性/架构边界测试联合运行。

```sh
.venv/bin/python -m pytest -q tests/test_production_identity_hardening.py tests/test_enterprise_identity.py tests/test_identity_boundary.py tests/test_auth_lifecycle.py tests/test_queue_observability.py tests/test_architecture_boundaries.py
```
