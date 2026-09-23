# 单机生产部署准备

本轮支持一个 Linux 主机上的 Docker Compose：Caddy HTTPS → Web API，独立扫描 Worker，PostgreSQL 16，一次性迁移任务。代码已提供；真实域名、证书、服务器、备份保管及真实企业验收尚需在目标环境执行。这里没有替用户公开发布服务。

## 架构与默认边界

- 镜像用 Node 24 构建工作台和 Landing Page，然后只在 Python 3.12 非 root 运行层交付应用。依赖来自 `requirements-production.lock`；镜像不含源码仓库的环境文件、企业上传、历史数据库、输出截图或测试语料。
- 只拷贝运行时必需的 `work/backup_restore.py` 与 `work/eval/sandbox_gates.py`。不携带 OCR benchmark 报告意味着评估状态保持未验证、机器 PASS 关闭，不能据此声称识别达标。
- 只有 Caddy 暴露主机 80/443。Web、Worker 和数据库不对主机映射端口。固定 Caddy 私网 IP 是唯一受信代理；禁止 `--forwarded-allow-ips=*`。
- Web/Worker 使用只读根文件系统、受限权限、PID/CPU/内存限制和临时目录；`/data` 是持久卷。Web 默认两个进程，每进程并发上限 64、监听积压 128；达到限额返回 503。Worker 默认只有内部网络，禁止外部 OCR 传输。SSO、外部OCR和多主机扩展不属于默认配置。
- 迁移只由 `migrate` 服务执行。Web 和 Worker 等待迁移成功；入口脚本不会偷偷再启动 Worker 或运行迁移。Web `/readyz` 与 Worker 心跳分别检查。
- 默认仅管理员邀请。生产没有共享试用邀请码。首次管理员需要独立随机 bootstrap token；后续须保护或移除该令牌并保留账号恢复流程。
- 字段加密是部分 JSON 字段的应用层保护，不代表数据库、原始PDF或MFA密钥都已加密。主机与持久卷应使用受控访问和磁盘加密。备份密钥必须单独保管，不要与数据备份放在同一公开位置。

## 首次配置

至少准备 4 CPU / 6 GiB RAM 和按文件量规划的持久磁盘空间。安装 Docker Engine 与 Compose v2；域名 A/AAAA 记录指向该主机，放行 80/443。

```sh
cp .env.production.example .env.production
chmod 600 .env.production
# 分别生成三个不同的值，填入 PostgreSQL 密码、bootstrap token、字段加密 key。
openssl rand -hex 32
```

编辑 `.env.production`：填真实 `BIDPROOF_DOMAIN`、与之对应的 `BIDPROOF_PUBLIC_ORIGIN=https://你的域名`、证书联系人邮箱，以及三个独立随机值。`BIDPROOF_DATA_REGION` 应按真实主机地域填写，默认 `deployment-defined` 不承诺具体驻留位置。必填项为空会让 Compose 直接拒绝启动。不要把填好的文件或 `docker compose config` 的明文输出提交到仓库。

```sh
docker compose --env-file .env.production config --quiet
docker compose --env-file .env.production build --pull
docker compose --env-file .env.production up -d
# 查看状态与迁移结论，不输出环境密钥。
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs --tail=80 migrate web worker
```

`up -d` 会触发真实部署和证书申请，必须在用户授权的目标主机执行。此交付的本地构建/配置检查不等于已执行该部署。

访问 `https://你的域名/app` 完成管理员初始化。检查匿名健康探针、登录、上传、Worker处理、双页码核验、人工备注/核销、权限隔离、退出/重新登录及备份恢复。应用不会自动消费或发布投标文件。

## 升级与回退

先记录当前镜像 tag，并制作包含数据库、原始上传和独立加密密钥的可恢复备份。使用 `work.backup_restore` 支持的 PostgreSQL 归档流程，执行恢复演练再升级；不能只复制正在运行的数据库卷。

```sh
docker compose --env-file .env.production stop web worker
docker compose --env-file .env.production build --pull
docker compose --env-file .env.production run --rm migrate
docker compose --env-file .env.production up -d web worker caddy
```

先停写再迁移，禁止多个迁移实例并发。失败时停止升级、保留备份；数据库结构回退不能只替换镜像，应按对应版本的备份恢复方案进行。`down -v` 会删除持久卷，不能用作日常重启。

## 运行限制与待验收项

- 默认最多 20 份企业证据，每份 50 MiB，单请求 110 MiB，PDF 500 页，单作业 600 秒。解析在子进程内隔离；超时、取消、租约丢失均不能发布失效结果。
- 此版本不支持 HTTP `Idempotency-Key`；携带该头的写入明确 501且未执行。重试写入前应先查任务状态。
- Docker 命名卷是单机持久化，不是异地备份或高可用。单机故障、备份保留/恢复目标、真实CPU/RAM负载、生产证书和真实IdP测试不能由源码测试替代。
- 原有 `deploy/helm/bidproof` 是历史脚手架，本轮未验收，不应直接用于生产。不同主机上增加 API/Worker 副本需要共享文件存储和额外调度、权限、恢复测试。
- 运行时容器不包含前端 sourcemap。CI如需外部监控，应将私有 sourcemap单独上传至已授权的监控服务，不能放在公开 static。

## 本轮实际验证

2026-09-23，在本机 Docker Desktop 的 Linux ARM64 环境完成：

- `docker compose config --quiet` 与两个入口脚本的 `sh -n` 通过；Caddy 2 容器对最终 Caddyfile 返回 `Valid configuration`。
- Node 24 构建工作台及 Landing，Python 3.12 运行镜像构建成功。镜像实际用户为 `10001:10001`；在只读根文件系统下导入 API、Worker 与两个必需 `work` 模块成功。镜像白名单检查确认无环境密钥文件、历史数据库、源码仓库的业务数据或 sourcemap。
- 实际 PostgreSQL 16 完成五项集成测试，包括空库迁移、JSONB、租户隔离、反馈幂等更新和作业领取；生产镜像又在独立空库运行迁移成功。
- Web 与独立 Worker 以生产模式、非 root、资源约束和共享命名卷运行，`/readyz` 与 Worker 心跳检查通过，六个公开页面/健康/SEO 路由均返回 200 且携带 request ID 和安全响应头。
- 临时 Caddy 使用本机内部 CA；客户端通过 `SSL_CERT_FILE` 显式信任该 CA，未关闭证书校验。完整 HTTPS → Web → PostgreSQL → 独立 Worker 链路的九项合成烟测全部通过：Cookie/CSRF、上传排队、原文件与双侧预览、人工核验、revision 冲突拒绝、报告导出、删除及注销。此测试同时验证生产 Secure Cookie 能真实工作。烟测后核实 `runs=0`、`scan_jobs=0`，上传与暂存目录为空；容器内 `pip check` 无依赖冲突。

最终冻结后增量镜像重新构建成功；运行时代码、依赖锁和静态资源共 95 个文件逐一 SHA-256 对齐，无差异（按设计剔除 sourcemap 与指针）。最后增量包含隐私文案、地域默认值与跨标签会话资源；九阶段 API 烟测在此前镜像上执行，这次增量以构建和文件一致性验证覆盖。

机器可读记录：`outputs/production/container-smoke-2026-09-23.json`。这些是合成工程数据，不代表业务验收、OCR 准确率或真实企业投标成功。实际公网域名/ACME 证书、Linux AMD64、多主机、负载与备份恢复尚未验证；本轮没有启动公开生产服务。
