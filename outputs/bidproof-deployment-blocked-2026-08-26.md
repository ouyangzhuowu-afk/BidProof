# BidProof 域名部署记录（2026-08-26）

## 目标

将 BidProof 挂载到 `bidproof.marketcase.net`，不覆盖现有 `marketcase.net` / `www.marketcase.net` 的 MarketCase 站点。

## 已完成

- Cloudflare OAuth 登录态验证通过，账号为当前项目既有 Cloudflare 账号。
- 新增独立 Cloudflare Container 发布骨架：`deploy/cloudflare-container/`。
- 本地 Worker 契约测试通过，Docker 镜像 dry-run 构建通过。
- 发布尝试已上传 `bidproof-marketcase` Worker 并开始构建容器镜像。
- 失败 Worker 已删除，未留下可访问的半成品服务。
- 根域复核：`https://marketcase.net` 与 `https://www.marketcase.net` 仍返回 MarketCase 页面。
- 已创建独立 Cloudflare Tunnel：`bidproof-local`（ID：`dfb4dc57-856e-4533-addd-6c1e209d408e`）。
- DNS 已将 `bidproof.marketcase.net` 指向该 Tunnel，入口回源为 `http://127.0.0.1:8016`。
- 本机 FastAPI 服务已恢复监听 `127.0.0.1:8016`，Tunnel 连接已注册。
- 公网验收通过：`https://bidproof.marketcase.net/healthz` 返回 HTTP 200；首页返回 HTTP 200，标题为“投标证据链 Agent”。
- Playwright 浏览器验收通过：工作台、任务总览、扫描记录、证据闸门和本地引擎状态均正常加载。

## 当前上线形态与边界

当前为**公网试点上线**，采用本机服务 + Cloudflare Tunnel，不是生产级托管部署：

- 本机 BidProof 服务必须持续运行于 `127.0.0.1:8016`。
- Cloudflare Tunnel 进程必须持续运行（本机重启或进程退出会导致公网不可用）。
- 任务数据库仍为本机 SQLite，上传文件与任务数据未迁移到托管持久化存储。
- 当前不具备企业生产环境所需的高可用、备份恢复、集中日志、权限隔离和正式运维值守。

Cloudflare Containers 方案仍受账号计划限制，之前返回 HTTP 401：`Deploying containers requires the Workers Paid plan.` 本次未将该限制伪装成已解决，而是采用 Tunnel 完成可访问的试点发布。

## 后续生产化工作

1. 将 FastAPI 服务迁移到具备持久磁盘或托管数据库/对象存储的正式运行环境。
2. 将 Tunnel 改为正式托管入口（或在托管平台配置等价的反向代理、TLS、健康检查和自动重启）。
3. 补充备份恢复、访问控制、审计日志、监控告警和发布回滚演练，再进行企业生产验收。

结论：`bidproof.marketcase.net` 已可公网访问，状态为“试点上线”；不能据此宣称为成熟企业生产部署。
