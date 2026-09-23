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
- [色彩、尺寸与排版 Token](design-tokens.md) — 对应 `frontend/src/styles/tokens.css`
- [第一版设计（2026-09-22）](ui-redesign-2026-09-22.md) — GPT-6 Astra 首轮重构的设计依据
- [第二轮交付记录（2026-09-22）](ui-hardening-round2-2026-09-22.md) — 第二轮交互、修复与测试复现，以本轮结果为准
- [Astra 第二轮合并与上线（2026-09-23）](astra-frontend-round2-2026-09-23.md) — 合并范围、C-022 证据与上线验收
- [前端生产边界](frontend-production-boundaries.md) — 严格类型范围、状态与监控的已知边界
- 构建：`npm ci --prefix frontend && npm run build --prefix frontend`（CI 会校验产物与源码一致）

## 生产候选（2026-09-23）

- [生产候选版集成报告（2026-09-24）](../docs/production-candidate-merge-2026-09-24.md) — 合并范围、门禁结果、上线前必须处理的生产配置
- [系统审计与改造路径](production/system-audit.md) — P0/P1 问题与处置
- [Landing 文案与组件蓝图](production/landing-blueprint.md) — 新首页 `landing/` 的设计依据
- [改造前后与验收边界](production/acceptance.md) — 验证范围与未覆盖项
- [生产部署、升级与回退](production/deployment.md) — Caddy → Web + Worker → PostgreSQL
- [API 端到端烟测与 CI](production/api-smoke.md) — 真 HTTP 排队扫描链路与 CI 门禁
- [安全加固记录](security-hardening-2026-09-23.md) — 身份、会话与请求预算加固

## 内部材料（不作为交付物）

- `superpowers/` — 历史设计稿与实施计划
- `archive/` — 已回退或已被取代的材料（工作台补丁 002、早期原型、旧前端打包说明），不代表当前实现
- 交接材料在仓库 `outputs/` 下：`outputs/handover-2026-09-23/`（前端交接文档与代码包分析）

## 相关入口

- 项目总览与边界：仓库根 `README.md`
- Agent 协作与当前优先级：`AGENTS.md`
- 控制面状态（唯一进度真源）：`workflow/project-state.json`
