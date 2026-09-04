# ISO 27001 差距分析（内部草稿，非认证声明）

日期：2026-09-04  
范围：BidProof 试点（Render Free + PostgreSQL Singapore）

| 控制域 | 现状 | 差距 |
|---|---|---|
| A.5 组织 | 有 AGENTS.md / workflow 角色，无正式 ISMS 责任人 | 指定安全责任人与年度评审 |
| A.8 资产 | 上传与 JSON 明文落盘；可选 `BIDPROOF_FIELD_ENCRYPTION_KEY` 字段加密 | 默认仍明文；境内节点与正式 BYOK 流程未上线 |
| A.9 访问控制 | RBAC 23 Permission、MFA、会话上限、项目成员 ACL；VIEWER 不可导出报告 | 多客户项目隔离需管理员配置 project_members |
| A.12 运行安全 | 结构化日志、健康检查、/metrics | 无 24×7 值班 |
| A.14 开发 | Alembic、生产关闭运行时 DDL、PG 已进 CI | 继续补迁移降级演练 |
| A.16 事件 | 审计信封 + 哈希链校验端点 | 无 WORM 外部对象存储 |
| A.18 合规 | 产品内嵌声明、登录前隐私页 | 无法务全文、无等保、数据在新加坡 |

**结论**：ISO 27001 认证未启动。本文件仅作差距清单，不能作为已获证证据。
