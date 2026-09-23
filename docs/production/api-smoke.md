# API 烟测与 CI 门禁

本检查验证工程链路，不代表真实企业验收、OCR 准确率达标或业务试点通过。所有上传文件由脚本现场生成，并明显标注为合成材料；不写入 pilot/ICP 台账。

## 对已有环境运行

需要 Python 3.11+、`requirements-production.lock` 中的 PyMuPDF，以及一个专用、拥有扫描、决策、导出与删除权限的测试账号。登录须无需交互式 MFA。账号密码建议通过环境变量提供，避免命令行参数进入历史或进程列表。

```sh
export BIDPROOF_SMOKE_USERNAME='专用测试账号'
export BIDPROOF_SMOKE_PASSWORD='在本地设置账号密码'
# 仅当同名账号需要指定企业空间时设置：
# export BIDPROOF_SMOKE_WORKSPACE_ID='工作区ID'
python scripts/production-smoke.py --url http://127.0.0.1:8768 --timeout 120
```

远程目标默认拒绝。只有明确准备好测试账号与测试范围后，才使用 `--allow-remote`，且目标必须是 HTTPS：

```sh
python scripts/production-smoke.py --url https://your-service.example --allow-remote
```

脚本不自动注册、初始化企业空间或配置账号，不猜测目标 URL，不跟随重定向，也不跳过 TLS 验证。私有 CA 环境可通过标准 `SSL_CERT_FILE` 指向受信任 CA 文件。`--timeout` 控制队列等待时间（5–600 秒），轮询逐步退避至 2 秒。网络请求有独立 20 秒超时。

## 实际执行链路

1. `/healthz` 与 `/readyz` 均可用，匿名任务接口必须拒绝访问。
2. 使用实际 Cookie 会话登录；故意省略 CSRF Header 的注销请求必须返回 403，且不得注销会话。
3. 生成招标、企业证据两份中文 PDF，提交 `/api/jobs` 并等待完成。
4. 读取要求项与证据索引，逐字节比对原始下载内容，读取两侧第一页 PNG。
5. 以当前 revision 保存一条 `NEEDS_REVIEW` 人工核验，检查版本递增。
6. 保存明确标注合成检查的 `HOLD` 决策；再次以旧版本写入必须返回 409，原决定不得被覆盖。
7. 获取 PDF、CSV 报告并核验基本文件结构。
8. 删除本进程创建的任务并确认 404，最终注销当前测试会话。

任何失败均返回非零退出码。失败清理只查询本次创建的 job/run：待处理作业先取消，已产生的自建任务尝试删除。不枚举、不删除其他任务，也不撤销其他会话。审计记录按系统既定保留策略留存。若网络故障造成清理未完成，脚本会明确报告失败；运维需按测试时间窗口检查服务日志。

输出仅包含检查名、状态及安全失败原因，不输出密码、会话令牌、CSRF Token、材料原文或后端异常响应体。

## 本次本地实测

2026-09-23 在 macOS、本地独立临时数据目录中分别完成两次真实 HTTP 链路：

- 开发模式 + 独立 worker：全部 9 个检查阶段通过，退出码 0。
- **production 模式 + 本机 HTTPS + 独立 worker/supervisor 子进程**：全部 9 个检查阶段通过，退出码 0。临时证书通过 `SSL_CERT_FILE` 显式信任，未关闭证书校验。生产公开源、主机白名单、随机初始化令牌和数据库迁移头均按实际生产约束配置。
- 生产模式执行后，隔离数据库中的 `runs=0`、`scan_jobs=0`，上传与暂存目录为空。
- `tests/test_readiness.py`：9 项通过，覆盖数据库不可用、迁移落后、存储不可写、worker 心跳缺失/过期及异常隐藏。
- 两个新增 Python 文件的 Ruff 检查通过；远程目标未提供授权开关时已实测立即失败。

机器可读记录见 `outputs/production/api-smoke-2026-09-23.json`。

## CI 配置

`.github/workflows/ci.yml` 使用 Python 3.12、Node 24 与 PostgreSQL 16，依次执行：

- 安装锁定生产依赖，安装测试工具，`pip check`、Ruff 与 `pip-audit`。
- 工作台 `npm ci`、常规与严格边界类型检查、行为测试、ESLint、构建和依赖审计。
- Landing `npm ci`、严格类型检查、行为测试、生产构建和依赖审计。
- Workflow 状态检查、空 SQLite 与 PostgreSQL 迁移及 head 校验。
- 启用 PostgreSQL 集成环境变量的完整 pytest。
- 临时 CA、production HTTPS API、独立 worker 与真实合成烟测；随机测试密码与初始化令牌对 CI 日志屏蔽，任务退出时停止进程。
- 生产 Docker 镜像构建。

CI 文件已经过本地 YAML 解析与 shell 语法检查；它需要在 GitHub Runner 上执行才有远端流水线结论。本次 API 实测使用本机 Python 3.11 与 SQLite，不能替代 CI 上的 Python 3.12 / PostgreSQL / Docker 运行，也未覆盖公网网络、负载、备份恢复或外部 OCR 服务。

后续补充：同日已实际完成 Docker Linux ARM64 / Python 3.12 / PostgreSQL 16 / Caddy HTTPS 完整九阶段烟测，见 `outputs/production/container-smoke-2026-09-23.json` 与 [部署说明](deployment.md)。GitHub 托管 Runner 本身仍未执行。上面的本机 SQLite 记录保留为独立证据，不覆盖后续容器记录。
