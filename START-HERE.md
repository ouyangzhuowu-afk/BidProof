# BidProof 审查工作台 · 第二轮交付

交付包：`BidProof-frontend-redesign-round2-20260923.zip`。首版 ZIP 与桌面原项目保留用于对照；本次修改在独立本地副本完成，未推送 GitHub、未部署公网。

工作台现在支持连续核验、人工状态筛选、双向 PDF 原页翻阅、证据切换和上传状态反馈。同名原件覆盖、旧请求覆盖新任务、备注保存期间丢失草稿等问题已修复。改动详情与验证边界见 [第二轮交付记录](docs/ui-hardening-round2-2026-09-22.md)。

## 直接预览

本机已启动时，打开 <http://127.0.0.1:8768/app>。

- 演示账号：`ui-review`
- 演示密码：`LocalReview2026!`
- 示例任务由程序生成 PDF，初始包含 9 个审查项。它用于界面体验，不代表真实企业资质、采购材料或业务验收结果。

## 从解压目录启动

需要 Python 3.11 或更新版本。ZIP 已包含 `static/app.js`、`static/style.css` 等构建产物，预览不需要 Node.js，也不需要重新构建前端。

在终端进入同时包含本文件、`requirements.txt` 和 `app/` 的目录，然后依次执行以下命令（macOS / Linux）。首次安装依赖需要网络；请在同一个终端完成生成示例和启动服务：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt 'httpx2>=2.12'

export BIDPROOF_DATABASE_URL=
export DATABASE_URL=
export BIDPROOF_ENV=development
export BIDPROOF_DATA_ROOT="$(mktemp -d /tmp/bidproof-review.XXXXXX)"

PYTHONPATH=. python scripts/seed-ui-review.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8768
```

`httpx2` 是生成示例脚本使用 FastAPI `TestClient` 所需的依赖，不能只安装 `requirements.txt` 后跳过它。上面的命令清空两个数据库连接覆盖项，并把示例数据库和生成 PDF 放入新建的临时目录。该目录不用于保存正式任务；终端关闭后如需继续使用同一示例，重新设置为原来的 `BIDPROOF_DATA_ROOT`。再次运行整段命令会创建新示例空间。

看到服务启动提示后打开 <http://127.0.0.1:8768/app>，使用上面的演示账号登录。停止服务用 `Ctrl+C`。若 8768 已被其他服务占用，可将启动命令的端口改为 8769，并打开对应地址。

## 验证记录

后端完整回归 **314 passed / 12 skipped**；前端 **83 个实质场景通过**（Node 汇总 89，包含 6 个测试容器）；构建与类型检查通过；前端 lint **0 错误、2 个既存警告**。

浏览器已验证 1440 × 1000、768 × 1024、390 × 844、320 × 740 四档视口无横向溢出，并检查浅色 / 深色截图。真实 PDF 翻页及回引用页、备注保存、确认核销、已核销筛选和原生 PDF 选择均已操作验证。键盘完整流程与操作系统“减少动态效果”设置尚未实测；完整记录见 [第二轮交付记录](docs/ui-hardening-round2-2026-09-22.md)。

## 继续开发

前端采用原生 ES 模块与 Vite。修改前端源码后，使用 Node.js 22 或更新版本重新生成静态产物：

```sh
npm ci --prefix frontend
npm run build --prefix frontend
npm run check --prefix frontend
npm run lint --prefix frontend
```

- [色彩、尺寸与排版 Token](docs/design-tokens.md)：对应 `frontend/src/styles/tokens.css`。
- [第一版设计与 HTML 骨架](docs/ui-redesign-2026-09-22.md)：保留首版设计依据及当时记录。
- [第二轮交互、修复与测试复现](docs/ui-hardening-round2-2026-09-22.md)：以本轮验证结果为准。
- 截图：`outputs/ui-redesign-round2/`。

ZIP 交付源码、构建产物、文档与测试，不携带虚拟环境、`node_modules`、会话数据库、本机上传原件、历史恢复数据、密钥或依赖缓存。所有核销和原页读取仍经过原有鉴权、双引用门禁与版本校验。
