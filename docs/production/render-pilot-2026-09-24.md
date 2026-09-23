# 最新版跑在 Render 免费实例上（2026-09-24）

## 结论

2026-09-24 决定先不采购服务器，继续用 Render 免费 Web Service 承载试点。最新版（新 Landing + 安全加固）已按"单容器"方式改造，并在本机以 **production 模式**实测通过，随后合并 main 触发 Render 自动部署。

## 为什么必须改造才能上线

新版在 \`BIDPROOF_ENV=production\` 下是 fail-closed 的（\`app/config.py\` 的 \`validate_runtime_security\`）：缺 \`BIDPROOF_PUBLIC_ORIGIN\`、缺显式 \`BIDPROOF_ALLOWED_HOSTS\`、仍配置共享试用码、\`JOB_RUNNER\` 不是 \`worker\`、缺 \`BIDPROOF_DATA_ROOT\`，任意一条都会让进程拒绝启动。\`/readyz\` 在生产下还额外要求：数据库迁移到最新版本、数据目录可写、以及 30 秒内的 worker 心跳。

Render 免费实例没有 Background Worker，而生产又要求独立 worker，因此做了三处改动：

1. \`render.yaml\` 补齐 \`BIDPROOF_PUBLIC_ORIGIN=https://bidproof.marketcase.net\` 与 \`BIDPROOF_ALLOWED_HOSTS=bidproof.marketcase.net,127.0.0.1,localhost\`，并**删除** \`BIDPROOF_TRIAL_JOIN_CODE\`（生产禁止共享试用码）。Render 的健康检查会带"已验证的自定义域名"作为 Host 头（见 Render 官方文档），所以自定义域名必须在白名单里。
2. \`healthCheckPath\` 从 \`/healthz\` 改为 \`/readyz\`：只有数据库版本、数据目录与 worker 心跳同时健康，部署才算通过。这样"worker 悄悄死掉、扫描永远排队"不会再被静默放过。
3. 新增 \`scripts/render-serve.sh\`：先执行一次性数据库迁移，把扫描 worker 以守护循环放进同一个容器，再把进程交给 HTTP 服务。Compose 部署仍保持"迁移一次性服务 + 独立 worker"的原设计，这个脚本只服务于没有 worker 产品的托管方案。

## 本机 production 模式验证（2026-09-24）

用与 render.yaml 完全相同的环境变量、SQLite 空库、自签 HTTPS 证书、真实 worker 进程复现 Render 容器的运行方式：

| 验证项 | 结果 |
|--------|------|
| 迁移 | \`python -m app.dbctl upgrade\` → upgraded（SQLite） |
| 生产模式启动 | 通过（配置闸门全部满足，JSON 日志开启） |
| \`/readyz\`（Host = 自定义域名，即 Render 健康检查的方式） | **200** \`{"status":"ready"}\` |
| \`/readyz\`（Host = evil.example.com） | **400** Invalid host header（Host 白名单生效） |
| \`/\`、\`/app\`、\`/healthz\`、\`/robots.txt\`、\`/sitemap.xml\`、\`/privacy\` | 全部 200；\`/\` 已是新版 Landing（引用 /static/marketing/） |
| 端到端冒烟 \`scripts/production-smoke.py\`（HTTPS + Secure Cookie + 独立 worker） | **9 项检查全部 passed** |
| worker 证据 | worker 进程日志出现 PDF 解析告警，证明队列由独立 worker 消费 |
| shell 语法 | \`sh -n\` 校验 \`render-serve.sh\`、\`entrypoint.sh\`、\`serve.sh\` 均通过 |

## Render 免费实例的已知边界（不掩饰）

- **文件系统是临时的**：上传的 PDF 与 \`/data\` 在重新部署或重启后丢失，任务元数据在 Postgres 里保留。重启后打开旧任务可能显示原件缺失。这是免费实例的固有限制，不是本次改动引入的。
- **空闲约 15 分钟休眠**：下一次请求需要冷启动（实测首次响应约 11 秒）。休眠期间排队的扫描要等下一次访问唤醒容器后才会被 worker 处理。
- **单容器共享 CPU**：worker 与 HTTP 在同一实例里，扫描大文件时网页响应会变慢。
- **强制终止可能中断扫描**：容器被回收时当前扫描会中断，租约 900 秒后自动重新排队。
- **共享试用码已禁用**：试用入口改为"个人注册（独立工作区）"或管理员邀请；旧文档里的 \`BidProof-Trial-2026\` 在生产环境不再可用。
- 只有一份实例，没有高可用、没有异地备份；免费 Postgres 30 天后过期。

## 回退

把 \`main\` 回退到上一版提交并推送，Render 会重新部署旧镜像；或在 Render 面板把 \`healthCheckPath\`、\`dockerCommand\` 改回旧值并加回 \`BIDPROOF_TRIAL_JOIN_CODE\`（不推荐：新版会因此拒绝启动）。

## 与单机方案的关系

## 2026-09-24 追加：共享试用码改为"生产丢弃 + 告警"，不再阻止启动

现场现象：新版镜像构建成功、数据库迁移在线上 PostgreSQL 上执行成功，但容器启动时在 `config.py` 抛
`RuntimeError: Shared trial join codes are disabled in production`，连续三次部署失败，服务一度完全打不开。

根因：交付包的设计是"production 下配了共享试用码就拒绝启动"，而 Render 的蓝本同步**只应用新增与更新，
不会删除已存在的服务变量**。所以服务上一直留着 `BIDPROOF_TRIAL_JOIN_CODE=BidProof-Trial-2026`，新版每次
启动都主动退出（日志里 `config.py` 第 73 行可直接看到）。

处理：`app/config.py` 的生产校验从"抛错"改为"把共享试用码置空并打印 WARNING"。安全效果与删除该变量完全
一致——生产环境永远不会认可共享码——但不会再让服务离线。

本机验证（production 模式 + 故意设置该变量）：启动成功并打印告警；`/api/auth/status` 返回
`trial_join_enabled: false`；用旧码调用 `/api/auth/trial-join` 返回 403「试用加入未开放」；`/healthz` 200；
完整回归 376 passed / 11 skipped；ruff 全绿。

要恢复"严格拒绝启动"的行为，在 Render 面板删除该变量即可：告警消失，行为不变。

\`docs/production/deploy-runbook-marketcase-2026-09-24.md\`（单机 Caddy + Web + Worker + PostgreSQL）没有被废弃：需要正式部署、独立 worker、持久磁盘与 HTTPS 证书时按它执行，本文件只描述当前试点方案。
