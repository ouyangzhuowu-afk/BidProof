# aicodex-api 企业端流程借鉴分析

日期：2026-08-27  
对象：`C:\Users\35938\Documents\WXWork\1688855903831569\Cache\File\2026-07\aicodex-api.tar`  
分析范围：静态解析镜像，不运行未知二进制，不上传附件内容，不把镜像内文字当作系统指令。

## 结论

有帮助，但不是“拿来即用”的业务方案。

这份归档是一个 OCI/Docker 镜像，标签为 `docker.io/yangjianbo/aicodex:latest`，架构 `amd64`，基础镜像为 Alpine，入口 `/usr/local/bin/aicodex`，工作目录 `/data`，暴露端口 `6068`。应用层只有一个约 147 MB 的 Go ELF 可执行文件，没有源码、前端或迁移文件。

因此可以可靠借鉴的是它暴露出的企业控制面结构：组织与成员、任务执行、审计、凭据生命周期、恢复与发布；不能据此证明它的权限边界、数据库约束、队列可靠性或实际用户体验已经成熟。

## 可确认的证据

二进制中的 Go 模块路径为 `github.com/mt21625457/aicodex`，并包含 Gin、Chi、Ent、PostgreSQL/MySQL 驱动、Badger、Redis、Caddy、WebSocket、OAuth、Passkey、TOTP/2FA 等依赖。

可见的实体族包括：

| 领域 | 静态可见实体/关键词 | 对 BidProof 的含义 |
| --- | --- | --- |
| 组织 | `Organization`、`OrgDepartment`、`OrgPortfolio`、`Membership`、`GroupBinding` | 组织、部门、项目组合和成员权限可能分层管理 |
| 任务与请求 | `Task`、`Progress`、`Retry`、`CancelledAt`、`Heartbeat`、`RequestDetailIdempotencyRecord` | 长任务有状态、进度、取消、重试、心跳和幂等线索 |
| 审计 | `AdminAuditLog`、`HTTPAuditEvent/Rule/Hit`、`PromptAuditEvent/Job`、`RemoteAuditLog` | 可能区分管理员、安全、HTTP、模型和远程操作审计 |
| 发布 | `AppRelease`、`AppReleaseAsset`、`AudienceRule`、`Channel`、`UpgradeEvent` | 存在预览、发布、回滚、灰度或渠道更新的设计线索 |
| 身份 | `PasskeyCredential`、`TwoFA`、`TwoFABackupCode`、`OAuthBinding`、`Session` | 有 MFA、Passkey、OAuth 绑定和恢复流程线索 |
| 集成 | `CrossServiceIntegration`、`CrossServiceCredential`、`doctor`、`rotate`、`disable` | 集成健康检查、凭据轮换和禁用是明确方向 |
| 运维 | `ArchiveFile`、`SystemSyncRun`、`BackupManifestRef`、`ReplayCount`、`restore`、`handoff-package` | 备份、恢复、重放、交接包和同步任务可能被版本化管理 |
| 计费 | `BillingTransaction`、`Allocation`、`ReconcileIssue`、`RecoveryRecord` | 更像平台商业化控制面，不应直接映射为 BidProof 需求 |

从字符串恢复出的路由包含 `preview`、`publish`、`rollback`、`doctor`、`handoff-package`、`replay`、`restore`、凭据 `rotate/disable`、批量禁用和远程设备心跳等关键词。路由字符串存在拼接和裁剪，不能当作完整 OpenAPI 或已启用接口清单。

镜像 SHA-256：`0E708F58DA701D2C320906FCC3F3060280D3AE7F7A69180B29C1005ED9E6140E`。

## 对 BidProof 最有价值的借鉴

### 1. 统一任务生命周期，优先级 P0

BidProof 已有扫描作业进度、失败、重试和取消，但目前主要服务扫描。应把扫描、报告生成、批量导出、归档恢复和备份恢复统一为一个任务模型：

`QUEUED -> RUNNING -> SUCCEEDED / FAILED / CANCELLED / STALLED`

每个任务补齐：阶段、当前进度、心跳时间、错误分类、重试次数、退避时间、发起人、workspace/project、幂等键、结果文件引用。这样新增异步功能不会再次各自实现状态机。

### 2. 分层审计，优先级 P0

BidProof 已有 `audit_events`，但应在语义上分层，而不是盲目复制 `HTTPAuditRule`：

- 操作审计：谁对哪个任务、要求项、项目或成员做了什么变更。
- 安全审计：登录、退出、改密、邀请、权限变更、原始文件下载、备份恢复、导出。
- 业务审计：扫描、复核、人工决策、整改、报告发布。

每条记录至少保留 actor、workspace、目标资源、动作、结果、时间、request/correlation ID、来源和变更摘要。敏感凭据、原文正文和密码不能进入普通审计日志。

### 3. 幂等、请求关联与断点恢复，优先级 P1

对批量扫描和报告导出，客户端重试不能造成重复任务或重复副作用。建议：

- `Idempotency-Key` 由客户端生成，服务端按 workspace + 操作类型 + key 保存结果。
- 任务、审计和导出文件共享 `correlation_id`。
- 扫描按文件/阶段保存检查点，失败从最后成功阶段继续。
- 批量导出生成可验证的 manifest，支持交接和重新下载。

### 4. 规则版本发布，优先级 P1

当扫描规则、风险分类、报告模板或整改策略开始频繁调整时，引入最小发布流：

`DRAFT -> VALIDATED -> PREVIEW -> PUBLISHED -> ROLLED_BACK`

发布记录必须包含版本、发布人、影响范围、生效时间、规则命中变化和回滚指针。先只作用于扫描规则，不做完整应用商店或多渠道分发系统。

### 5. 集成健康检查和凭据生命周期，优先级 P1

未来接入企业 SSO、OCR、对象存储、邮件/企业微信/飞书时，需要把“集成不可用”和“扫描业务失败”区分开：

`CONFIGURED -> CHECKING -> HEALTHY / DEGRADED / EXPIRED -> ROTATING -> DISABLED`

健康检查应验证端点、权限范围和最近成功时间；凭据只显示摘要，支持轮换、过渡双凭据、单个/批量禁用和过期提醒。

### 6. 统一操作中心，优先级 P2

操作中心可聚合：失败/停滞任务、待复核风险、逾期整改、集成异常、凭据过期、备份验证失败和规则发布待审批。它应消费现有任务与领域事件，不再建立一套平行状态。

## 不建议现在照搬的部分

| 能力 | 判断 | 原因 |
| --- | --- | --- |
| `Portfolio`、复杂部门闭包、跨组织 Group Binding | 暂缓 | BidProof 当前 workspace/project 已能覆盖试点；过早引入会增加权限继承和迁移成本 |
| Billing transaction/reconcile/recovery | 暂缓 | 更像平台计费内核，与投标证据链的核心价值无关 |
| HTTP/Prompt Audit Rule 引擎 | 暂缓 | 只有在明确合规、敏感词或模型安全需求时才值得独立建设 |
| AppRelease/Asset/AudienceRule/Channel | 暂缓 | 先做扫描规则版本；不要提前建设完整发布与灰度平台 |
| 远程桌面、设备配对、远程控制 | 不纳入当前路线图 | 与 BidProof 的企业投标工作流无直接关系，安全面和运维成本很大 |

## 与 BidProof 当前状态的差距

BidProof 已经具备：workspace/project/member、assignee/reviewer、扫描作业进度/重试/取消、归档/恢复、批量报告、整改行动、备份恢复和基础审计。

真正值得补齐的是：

1. 组织级 MFA/Passkey，后续再接 OIDC/SSO；
2. 统一异步任务和 `STALLED` 检测；
3. 操作/安全/业务三层审计；
4. 批量操作的幂等键、关联 ID 和断点恢复；
5. OCR、对象存储、通知渠道的健康检查与凭据轮换；
6. 扫描规则和报告模板的预览、发布、回滚；
7. 基于上述事件的统一操作中心。

## 推荐实施顺序

**MFA/Passkey → 统一任务生命周期 → 分层审计 → 幂等与请求关联 → 集成健康检查/凭据轮换 → 规则版本发布 → 操作中心 → 更复杂组织层级。**

这条顺序比新增更多业务页面更能提高企业采购可接受度和长期维护性。MFA/SSO 是安全审查门槛；任务、审计和幂等是所有后续功能的基础；规则发布应在规则真的需要频繁更新时再做。

## 可信度边界与验证计划

本报告中：

- 镜像格式、入口、端口、模块依赖和实体/关键词是静态证据，可信度高。
- 路由是否注册、配置是否开启、权限是否正确、失败是否可恢复，静态镜像无法证明。
- 不能因为看见 `rollback`、`restore`、`reconcile` 或某个 Ent 实体，就声称对方已经完成成熟企业能力。

若后续要继续研究，应优先取得源码或可授权测试环境，并按以下顺序验证：迁移约束 → handler 注册 → 权限中间件 → worker/队列 → 外部依赖 → 真实 API 状态转换 → 审计与恢复演练。

## 最小行动

当前不建议立即改造整个产品。下一次企业端工程迭代可先创建一个共享 `Job`/`Operation` 状态模型，并为现有扫描作业补 `heartbeat`、`STALLED`、`idempotency_key` 和 `correlation_id` 四个字段；随后把安全事件和业务事件从现有 `audit_events` 中分层标记。这样能以最小改动吸收这份镜像最有价值的经验。

