# Project-025 前端成品化重构验收（2026-08-26）

## 交付范围

- 使用 `ui-ux-pro-max` 设计系统将内部工具重构为“证据审计工作台”：固定侧栏、任务总览、扫描详情、逐项核验、人工决策和原生上传对话框。
- 设计基线：`design-system/bid-evidence-agent/MASTER.md`。
- 主要实现：`static/index.html`、`static/style.css`、`static/app.js`、`static/vendor/lucide.min.js`。
- 新增契约回归：`tests/test_ui_product_contract.py`；移动端回归：`tests/test_mobile_layout.py`。

## 自动化与现场证据

| 检查项 | 结果 | 证据 |
|---|---|---|
| JavaScript 语法 | PASS | `node --check static\\app.js` |
| 全量 Python 回归 | PASS | `uv run --group dev pytest -q`，38 passed |
| 工作流状态 | PASS | `uv run python -m app.workflow check` |
| 桌面 1440px 首页 | PASS | `outputs/playwright/ui-final-home-1440.png` |
| 详情页 1440px | PASS | 76 条要求、每页 12 条；双页码引用展示 |
| 平板 768px | PASS | `htmlScrollWidth=768`、`bodyScrollWidth=768` |
| 手机 390px 详情 | PASS | `htmlScrollWidth=390`、`bodyScrollWidth=390`，高风险区 4 条 |
| 人工决策 390px | PASS | 3 个决策选项、62 条未解决项、无横向溢出；`outputs/playwright/ui-final-decision-390.png` |
| 上传对话框 390px | PASS | 宽 356px、焦点进入企业名称、招标 PDF `required=true`；`outputs/playwright/ui-final-upload-390-open.png` |
| 要求项分页与搜索 | PASS | `1-12` → `13-24`；`SCORING` 搜索 1 条，清空恢复 76 条 |
| 浏览器控制台 | PASS | 0 errors、0 warnings |

## 成品边界

本记录证明本地前端、FastAPI 后端和 SQLite 现场可运行，并完成 UI 可交付级结构、交互、可访问性和响应式验收。它不等于生产部署、真实客户验收、商业可用性或付款意愿验证；真实业务输入仍须通过 `outputs/pilot-ledger.csv` 记录。验收未提交真实任务、未调用上传提交，因此未改写现有任务数据。

## 本地访问

当前现场服务：`http://127.0.0.1:8016`
