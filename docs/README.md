# BidProof 文档索引

最后更新：2026-09-23

## 交付文档（给客户与运维）

- [用户手册](user-guide.md) — 投标专员如何扫描、复核、导出
- [API 集成](api-integration.md) — Token、错误码、限流、`/api/v1` 与幂等键
- [升级](upgrade.md) — Alembic / 备份
- [信创适配矩阵](xinchuang-matrix.md)
- [ISO 27001 差距分析](iso27001-gap.md) — 内部草稿，**不是认证声明**

## 前端工程

- 源码唯一真源：`frontend/src/`；`static/` 是 Vite 构建产物，**不要手改**。
- [前端迁移说明](frontend-MIGRATION.md) — 视图模块化迁移记录、验证方式与回滚路径
- [BATCH8 设计](frontend-BATCH8-DESIGN.md) — 批次 8 的界面设计与契约
- 构建：`npm ci --prefix frontend && npm run build --prefix frontend`（CI 会校验产物与源码一致）

## 内部材料（不作为交付物）

- `superpowers/` — 历史设计稿与实施计划
- `archive/` — 已回退或已被取代的材料（工作台补丁 002、早期原型、旧前端打包说明），不代表当前实现
- 交接材料在仓库 `outputs/` 下：`outputs/handover-2026-09-23/`（前端交接文档与代码包分析）

## 相关入口

- 项目总览与边界：仓库根 `README.md`
- Agent 协作与当前优先级：`AGENTS.md`
- 控制面状态（唯一进度真源）：`workflow/project-state.json`
