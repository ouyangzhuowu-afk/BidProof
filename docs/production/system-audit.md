# BidProof 上线审计与实施路径

2026-09-23。基线为第二轮工作台交付包，桌面原件与该 ZIP 保留。本文在最终代码实施前形成。目标是可部署、可验证的上线候选版本；真实采购文档准确度、业务付款与正式环境验收独立设门禁。

## P0：开放真实企业数据前修复

| 问题 | 初始证据 | 路径 |
| --- | --- | --- |
| Token 非法 scopes 被过滤为空后扩大权限；降权后仍用旧角色 | auth_service.create_api_token / identity.principal / db.authenticate_api_token，隔离DB实证 | 非法scope拒绝；当前账号角色与签发权限交集 |
| OIDC不验签、SSO按同名账号绑定导致跨空间身份混淆 | oidc.py / auth_service._provision_federated_user | 成熟JWT库验签、issuer/audience/expiry/nonce校验、浏览器state绑定、显式workspace、禁止同名接管 |
| 任意XFF可改限流桶，生产代理信任过宽 | request_context.client_ip；serve.sh的forwarded-allow-ips=* | 应用只读取可信ASGI peer，明确代理白名单与Host/Origin |
| A任务决策迟到回包覆盖B，过期会话残留旧数据 | decision.js / auth/index.js / collab.js，DOM复现 | epoch、取消和版本守卫；会话清理；后端决策revision |
| 取消后仍发布run；多worker缺少执行权约束 | scan_service最后保存无取消检查；start_scan_job可重复启动 | 事务内执行租约检查、取消不发布、心跳和旧worker结果隔离 |

## P1：上线稳定性与可维护性

1. 幂等中间件目前不缓存且设计存在跨身份回放危险。移除伪支持，传入幂等键时明确拒绝，写操作不自动重试；以后采用认证后事务式业务去重，不直接缓存通用HTTP响应。
2. 限制总请求字节、文件数量、元数据与PDF页数，避免在事件循环中执行生产扫描；长任务使用独立worker进程和明确超时。
3. 保留存活探针，增加数据库、schema及存储就绪探针；Web与worker各有健康检查，迁移单独运行。
4. 前端建立异常/离线反馈与可注入脱敏监控适配器；规范后端关联ID、时间和耗时。
5. 原工作台 `checkJs=false`，不能把旧tsc通过称为严格类型安全。新增严格契约边界与完整严格TS落地页，并明确旧模块迁移范围。
6. CI加入前端行为测试、类型检查、生产镜像构建、SQLite/PostgreSQL迁移与接口流程；修正依赖与已构建文件校验。
7. 非root镜像、明确COPY白名单、依赖锁定、生产环境校验、HTTPS反代、资源边界和备份恢复说明。

## 架构选择

保留现有 API → services → repositories / SQLAlchemy 分层、服务端Cookie会话、CSRF和SafeHtml。已有机制经回归加固，不为形式统一更换成JWT登录。公共Landing使用独立Vite + TypeScript strict + Tailwind构建，生成静态HTML/CSS/JS，继续由FastAPI同源提供，不增加常驻Node服务。审查核销仅在服务器确认后更新，不对合规结论做乐观通过。

## 外部验收门禁

目前缺少正式域名/服务器、正式价格与商业联络渠道、真实客户评语和效率证据。按单机Docker Compose + PostgreSQL + HTTPS反向代理交付候选配置；价格按需报价。不得编造客户、认证或转化率，不把合成演示或工程测试转换成准确率、法律合规或生产SLA。
