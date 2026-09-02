# Project-025 栈现场验收（2026-08-26）

## 运行入口

- 服务：`uvicorn app.main:app --host 127.0.0.1 --port 8015`
- 地址：`http://127.0.0.1:8015`

## 后端与数据库

- `/healthz`：HTTP 200，返回 `status=ok`、`service=bid-evidence-agent`。
- `/`：HTTP 200，返回“投标证据链 Agent”主页。
- `/api/runs`：返回 3 个持久化任务；目标运行 `934c0cc93ea847ad9180421367bcecb0` 可恢复，76 条要求、62 条待复核、决策 `HOLD`。
- SQLite：`work/data/bid_agent.sqlite3` 存在 `runs` 表，包含来源文档、证据资产、要求项、复核和决策 JSON 字段；数据库内 3 个任务。

## 前端

- Playwright 桌面页：主页可见最近任务和新建扫描入口；点击目标任务进入扫描详情。
- Playwright 390px：详情页初次发现 `scrollWidth=475` 横向溢出；增加收缩和长文本换行约束后复测为 `scrollWidth=390`，与视口一致。
- 截图：`outputs/playwright/desktop-home.png`、`outputs/playwright/mobile-detail-fixed.png`。

## 边界

本报告证明本地前端、FastAPI 后端和 SQLite 持久化现场可运行，不证明生产部署、商业验收或付费意愿。业务输入仍须通过 `outputs/pilot-ledger.csv` 记录。
