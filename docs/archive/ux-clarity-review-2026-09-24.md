# 产品与落地页清晰度改造（2026-09-24）

用户反馈：**产品和落地页不够清晰，不知道要干嘛、不知道能干嘛**；要求站在客户需求立场，简洁明了，不要越花哨越好、满屏文字。

本次先复现"用户看到的东西"，再改。过程中发现两个会直接让人卡住的功能缺陷，一并修复。

---

## 一、实际看到的问题

在本地 test 实例（`BIDPROOF_ENV=test`，独立 data root，无真实客户材料）逐屏走查落地页与工作台：

1. **落地页首屏答不出"这是什么"。** H1 是口号"截标之前，把每一条风险核对清楚。"，没有一句话说明是给谁用的什么工具、点进去会发生什么。页面有 7 处英文小标题（LESS SEARCHING / TRY THE EVIDENCE FLOW / …），对中文投标负责人是纯噪声。
2. **"怎么用"排在页面第 4 屏**，而第 2 屏是交互演示；第一次来的人先看到演示，最后才看到步骤。
3. **价格区三张卡都写"按需求报价"**，没有回答"我现在怎么开始"。
4. **工作台空状态只有四张 0 值指标卡 + 一个按钮**，且该按钮必然报错（见下）。
5. **任务详情页根本打不开**：点进任何一条扫描结果，界面弹"登录状态已过期，请重新登录"并清空回登录框 —— 这是"不知道要干嘛"最直接的来源。

---

## 二、缺陷 1：打开任务详情被踢下线（SQLite 部署）

### 复现

进入 `/app#detail/<run_id>` 时前端并发发出 6+ 个请求。服务端日志：

```
GET /api/runs/<id>/audit       500  sqlite3.InterfaceError: bad parameter or other API misuse
GET /api/runs/<id>/comments    401
GET /api/notifications         401
```

401 让前端执行"重新登录"（`core/http.js` 的 401 处理），用户看到的即"登录状态已过期"。

### 根因

- **A. 连接被多线程共用。** `app/database.py` 对 SQLite 使用 `StaticPool`：整个进程共用一条 DBAPI 连接。FastAPI 的同步路由跑在线程池里，两条线程同时驱动同一个 cursor，SQLite 抛 `InterfaceError`。
- **B. 写操作绕过请求级事务。** `db.ensure_workspace()` 用 `engine.begin()` 另开一条连接，而 `uow.transaction()` 已在另一条连接上持有写锁。修好 A 之后这个隐藏问题立刻显形为 `sqlite3.OperationalError: database is locked`（同时打断 `tests/test_production_identity_hardening.py` 两个用例）。

### 修复

| 文件 | 改动 |
|------|------|
| `app/database.py` | SQLite 文件库改 `QueuePool`（默认 5 + 10），连接不再跨线程共用；`:memory:` 仍保留 `StaticPool`，否则每次连接都会得到空库 |
| `app/db.py` | `ensure_workspace()` 改走 `connect()`，在 `uow.transaction()` 内复用同一连接 |

### 证据

- 新增 `tests/test_sqlite_concurrency.py`（3 例）：并发取连接不再共用同一条 DBAPI 连接；8 线程读写混跑 0 异常且写入条数正确；内存库仍共享一条连接。
- 把 `poolclass` 临时改回 `StaticPool`，该测试立即失败（回归测试有效，不是装饰）。
- 并发脚本（12 个详情页端点 × 8 轮，柱栅同步启动）：修复前出现 500 与假 401，修复后全部 200。

### 影响范围

影响 **SQLite 部署**：本地开发、测试、单机 docker compose 安装。当前 Render 试点走 Postgres（`render.yaml` 的 `fromDatabase`），不受该缺陷影响；但测试与单机交付路径此前一直被这个问题污染。

---

## 三、缺陷 2：空状态唯一的按钮是坏的（影响所有环境）

`frontend/src/api/workspace.js` 的 `getSampleTender()` 用 JSON 通道请求 `/api/sample-tender`，而该接口返回 `application/pdf`，必然抛"服务未返回可读取的结果，请刷新重试"，上传窗口也不会打开。

修复：改走 `requestBlob()` 并把 Blob 通过 `bidproof:start-sample-scan` 事件传给扫描弹窗（不再重复请求）。实测：空状态点击后上传框打开、`sample-tender.pdf` 已填入，可直接开始扫描。

---

## 四、文案与结构改造

### 落地页 `landing/index.html`

- 首屏 H1 改为动作句：**"上传招标文件，逐条找出可能废标的地方。"**；副标题一句话说清输入、输出和"结论由人确认"。
- 主按钮改为"进入工作台，上传招标文件"，副按钮改为"先看一条怎么核"。
- **删掉全部 7 处英文小标题**和空泛小标题；章节标题改为陈述句："怎么用：三步 / 具体能帮你做什么 / 先亲手核一条，再决定要不要用 / 它不做哪些事 / 现在怎么参与"。
- 把"怎么用：三步"从第 4 屏提到首屏之后（原来在交互演示之后）。
- 四张能力卡从"先看到，最不能漏的"改为直白功能句："先看可能废标的条款 / 每条结论都带页码 / 缺哪份材料，写在条目上 / 谁核的、什么时候核的"。
- 价格区从三张"按需求报价"卡改为"现在怎么参与"：个人工作区 / 团队协作 / 私有部署，各一句适用场景；保留合规措辞"当前为试点方案，价格与服务范围按需确认"。
- 修复首屏浮动标注压住演示卡文字（`.hero-visual` / `.citation-float` 垂直位置）。

### 工作台 `frontend/src`

- 空状态三步改为可执行动作："点「新建扫描」，选一份准备投的招标文件 / 顺手把企业资质、人员证书、业绩材料一起传上去 / 扫描完成后回到这个任务，逐条确认每条风险的证据"（原来第 3 步写"在作业页查看进度"，与界面用词不一致）。
- 检出质量面板的免责文案从"复核样本尚未覆盖全量，以上为抽样估计，不能作为对外承诺的指标"改为"还没有足够的真实样本，这两项暂时算不出来。样本积累后会显示在这里"——保持"不得呈现为已验证指标"的合规前提，但让客户看得懂。
- 详情页导航标签"全任务核验 · 1 / 17"容易被读成进度，改为"正在看第 1 / 17 条"，无条目时显示"暂无可核验的条目"。

---

## 五、验证

| 项目 | 结果 |
|------|------|
| `pytest -q` | 379 passed, 11 skipped |
| `npm test --prefix frontend` | 124 passed |
| `npm run verify --prefix landing` | tsc + 10 passed + vite build |
| `python -m app.workflow check` | PASS |
| 浏览器实测（本地 127.0.0.1:8017） | 落地页首屏/三步/怎么参与/常见问题截图核对；工作台空状态 → 示例试跑 → 扫描完成 → 任务详情全程可用 |

限制与未覆盖：

- **未在生产环境验证。** 上述浏览器实测在本机 test 实例完成；Render 上的 `bidproof.marketcase.net` 需要发布后才能确认，本次未发布。
- 未触碰 OCR 准确率口径。行级 CER / 关键字段 F1 / TEDS 三项门禁仍是 GATE_FAIL，产品侧继续强制 `NEEDS_REVIEW`。
- 未产生真实企业任务或业务台账记录；`pilot-ledger.csv` / `icp-outreach.csv` 保持为空。
