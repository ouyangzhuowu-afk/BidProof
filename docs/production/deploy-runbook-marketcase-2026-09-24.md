# BidProof 单机生产上线操作单（2026-09-24）

适用方案：**选项 A**，单机 Docker Compose（Caddy HTTPS → Web → 独立 Worker → PostgreSQL）。上层依据是 \`docs/production/deployment.md\`，本文件只把它落成可执行步骤，并写明哪些步骤需要人来操作。

> 2026-09-24 更新：用户决定先不采购服务器，试点继续用 Render 免费实例（见 \`docs/production/render-pilot-2026-09-24.md\`）。本操作单保留给后续正式部署，步骤本身仍然有效。

## 本机已经准备好的东西

| 项 | 位置 |
|----|------|
| 上线代码包（729 个文件，已含新版首页与安全加固） | \`C:\BidProof\bidproof-deploy-2026-09-24.tgz\`（20.7 MB，sha256 \`42cadb70…3249\`） |
| 生产环境变量（含 3 个独立随机密钥） | \`C:\BidProof\.env.production\`（已被 Git 忽略，不会进仓库） |
| 代码分支 | \`codex/production-candidate-20260923\`（提交 \`ffc3636\`，已推 GitHub，**未合并 main**） |
| 本机已通过的检查 | \`docker compose --env-file .env.production config --quiet\` 通过；Dockerfile 全部 COPY 源存在；\`app/worker.py --healthcheck\` 存在；生产锁含 pyjwt 2.14.0 / cryptography 50.0.1 / psycopg 3.3.6 / greenlet 3.5.6 |

三个密钥的用途，别混：\`POSTGRES_PASSWORD\` 是数据库密码；\`BIDPROOF_BOOTSTRAP_TOKEN\` 是首次创建管理员用的一次性令牌；\`BIDPROOF_FIELD_ENCRYPTION_KEY\` 是字段加密密钥，**丢失后已加密字段无法恢复，必须单独离线备份**。\`ACME_EMAIL\` 暂填 \`ouyangzhuowu@gmail.com\`（证书到期通知用），可改。

## 第 1 步【人】：准备服务器

- 一台 Linux 服务器（Ubuntu 22.04 / 24.04），建议 ≥4 核 / 6 GiB 内存 / 40 GB 磁盘，带公网 IPv4。
- 云厂商安全组放行 80、443；**不要**对公网开放 5432 / 8080。
- 一个能 SSH 登录的账号（root 或带 sudo）。

## 第 2 步【人】：安装 Docker

\`\`\`sh
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
\`\`\`

重新登录 SSH 后，\`docker compose version\` 有输出即成功。

## 第 3 步【人】：把代码包与环境文件传上去

在本机 \`C:\BidProof\` 目录执行（把 \`SERVER_IP\` 换成服务器地址）：

\`\`\`sh
scp bidproof-deploy-2026-09-24.tgz .env.production root@SERVER_IP:/root/
\`\`\`

在服务器上解包：

\`\`\`sh
mkdir -p /opt/bidproof
tar -xzf /root/bidproof-deploy-2026-09-24.tgz -C /opt/bidproof
mv /root/.env.production /opt/bidproof/.env.production
chmod 600 /opt/bidproof/.env.production
cd /opt/bidproof
\`\`\`

用压缩包而不是 \`git clone\`，因为仓库是私有的，服务器直连 clone 需要额外配置访问令牌；压缩包里不含任何环境密钥。

## 第 4 步【人】：先做只读检查

\`\`\`sh
docker compose --env-file .env.production config --quiet && echo CONFIG_OK
docker compose --env-file .env.production build --pull
\`\`\`

\`build\` 会拉取基础镜像并编译工作台与首页，首次通常需要几分钟。

## 第 5 步【人】：先切 DNS，再启动

\`bidproof.marketcase.net\` 现在指向 Render。Caddy 要拿到 HTTPS 证书，域名必须已经指向这台服务器，所以先改 A 记录为服务器公网 IP。

- **切换前需要你确认一件事**：Render 上现有的账号与任务数据要不要保留。我没有 Render 的访问权限，无法代查；需要保留的话先做一次数据库导出再切换。
- 回退成本很低：把 A 记录改回 Render 的地址即可，老服务保持原样不动。
- 切换后旧域名会指向空库的新服务，老站点上的账号不会自动搬过来。

## 第 6 步【人】：启动并自检

\`\`\`sh
docker compose --env-file .env.production up -d
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs --tail=80 migrate web worker
docker compose --env-file .env.production exec web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=5).status)"
\`\`\`

\`ps\` 里 postgres / web / worker / caddy 应为 running 或 healthy，\`migrate\` 显示 exited(0) 表示迁移成功。

## 第 7 步【人】：创建第一个管理员（浏览器里做）

打开 \`https://bidproof.marketcase.net/app\` → 选择"初始化企业管理员" → 填工作区名称、管理员用户名与密码，初始化令牌填 \`.env.production\` 里的 \`BIDPROOF_BOOTSTRAP_TOKEN\`。

创建成功后建议把该令牌清空并重启 web/worker，避免令牌长期有效：

\`\`\`sh
# 编辑 .env.production，把 BIDPROOF_BOOTSTRAP_TOKEN 改成空值
docker compose --env-file .env.production up -d web worker
\`\`\`

## 第 8 步【人】：验收清单

- [ ] \`https://bidproof.marketcase.net/\` 是新版首页（含交互演示），\`/app\` 是工作台
- [ ] 匿名访问 \`/healthz\`、\`/readyz\` 返回 200，\`/api/runs\` 返回 401
- [ ] 用新管理员登录，上传一份招标 PDF，作业页看到 worker 处理完成
- [ ] 打开任务详情：条款带页码引用，原页预览可翻页，越界页码报错
- [ ] 做一次人工核销、加一条备注、导出报告
- [ ] 退出登录后确认匿名打不开任务数据

## 第 9 步【人】：备份与后续升级

\`\`\`sh
docker compose --env-file .env.production exec -T postgres pg_dump -U bidproof bidproof | gzip > /root/bidproof-$(date +%F).sql.gz
\`\`\`

再把 \`/data\` 卷一起备份，并把 \`BIDPROOF_FIELD_ENCRYPTION_KEY\` 单独离线抄一份（不要与数据备份放在同一处）。升级顺序：换新版本 → \`build\` → \`run --rm migrate\` → \`up -d web worker caddy\`，先停写再迁移。

## 需要我继续的部分

第 2–4、6、9 步的命令我可以按你的机器逐条写好，陪你执行；但需要先拿到服务器信息（地址、SSH 是否可用、Docker 是否已装）。如果你希望保留 Render 上的数据，我可以先带你把库导出来再切换。上线验收通过后，我再把分支合并到 \`main\`、更新 \`AGENTS.md\` 与状态文件，并给出 Render 保留或下线的建议。
