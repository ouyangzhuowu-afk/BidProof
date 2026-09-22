# 归档目录（历史材料，不代表当前实现）

这里的文件是**历史记录**，用于追溯决策，不是当前的 UI 契约或交付文档。

| 文件 | 日期 | 归档原因 |
|------|------|----------|
| `workbench-patch-002.md` | 2026-09 | 工作台补丁 002 打乱扫描任务页对齐，已按 C-022 回退到 `4516b3f` 布局；保留补丁说明作为设计参考 |
| `workbench-prototype-v2.html` | 2026-08 | 早期静态原型，早于当前 Vite 构建的前端，仅作视觉参考 |
| `frontend-refactor-README.md` | 2026-09-14 | 旧「前端代码包」说明，内容仍是 `frontend/src/app.js` 单文件时代的布局，已被 `docs/frontend-MIGRATION.md` 取代 |

判定当前 UI 契约请以 `frontend/src/`（源码）与 `static/`（构建产物）为准。
