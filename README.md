# Relay · 共享 Pro 中转部署

用 Docker Compose 在一台 Linux 服务器上部署私有 [sub2api](https://github.com/Wei-Shaw/sub2api) 实例:朋友各自持有独立用户与 API Key 共享一个 OpenAI Pro 账号,每个人的用量直接在 sub2api 管理台按成员、按时间段查看。本仓库不包含任何自建网站或统计页面——之前的中转看板已下线。

## 部署(腾讯云,IP HTTPS)

需要 Linux、Docker Compose、80/443/8443 入站可达,以及可访问 OpenAI 的上游网络。

```sh
git clone https://github.com/mglyn/relay.git /opt/relay
cd /opt/relay
python3 scripts/init_env.py <公网IP>
docker compose up -d
python3 scripts/bootstrap.py
```

`.env` 自动生成随机密码,权限 0600,不提交 Git;`DASHBOARD_ADMIN_PASSWORD` 等历史变量已无用,可删。`bootstrap.py` 关闭公开注册并生成管理 API Key(写入 `.env`);首次登录 sub2api 管理台需阅读并确认部署承诺,未确认前该脚本会收到 HTTP 423,确认后重跑即可。

服务器拉取镜像较慢时,可在网络可用的机器上运行 `python scripts/export_image.py sub2api.tar`,把镜像传到服务器后 `docker load -i sub2api.tar`。该脚本只从官方 GHCR 拉取并逐个校验 blob SHA-256。不可把 `.env` 或凭据文件打包进镜像或 Git。

Caddy 使用 Let's Encrypt `shortlived` ACME profile 为裸 IP 签发 6 天短期证书并自动续期,是公网可信证书,无需忽略浏览器警告。443 端口仅为证书验证保留(返回 410),实际服务在 8443。使用自己的域名时,把 `.env` 的 `CADDY_CONFIG` 改为 `Caddyfile` 并填写 `GATEWAY_DOMAIN`。

## 查看每个人的用量

登录 sub2api 管理台(见 `DEPLOYMENT.md`):

- **使用统计/仪表盘**:按日期范围查看总请求、token 与费用,可按成员(user)筛选。
- **使用日志**:逐条请求记录,支持按成员、时间、模型过滤。
- **用户详情**:单个成员的累计与明细统计。

朋友也可以用自己的 sub2api 账号登录,查看个人用量。程序化读取可用管理 API(请求头 `x-api-key`,值即 `.env` 中的 `SUB2API_ADMIN_KEY`),例如:

```
GET /api/v1/admin/usage/stats?user_id=<id>&start_date=2026-09-17&end_date=2026-09-22&timezone=Asia/Shanghai
GET /api/v1/admin/users?page=1&page_size=100
GET /api/v1/admin/accounts?page=1&page_size=100
```

接口以实际部署版本为准,升级镜像后应重新核验。

## 上线步骤(管理台内)

1. 导入/授权你自己的 Pro 上游账号(不要把 OAuth token 发到聊天或 Git)。
2. 建立共享分组,为每人创建一个用户及各自 API Key,将请求路由到该账号。
3. 外部客户端使用网关地址及成员自己的 sub2api API Key。子服务、Postgres 与 Redis 不映射公网端口。

## 运维

```sh
cd /opt/relay
git pull --ff-only
docker compose up -d
docker compose up -d --force-recreate --no-deps caddy   # 改过 Caddyfile 后
docker compose ps
```

更新前先备份;`.env` 的 `SUB2API_IMAGE` 固定 digest,不会随 `latest` 自动升级。修改 Caddy 配置后须 `--force-recreate`,确保文件挂载与配置都更新。

备份:对 Postgres 用 `pg_dump`,同时保存 `.env`、sub2api 数据卷和 Caddy 数据卷。不要运行 `docker compose down -v`,它会删除数据卷。生产账本时期的 `relay_ledger` 卷已随看板下线失去用途,可 `docker volume rm relay_ledger` 清理(内容为空)。

如 GitHub 连接临时失败,可从已推送的本地仓库制作 Git bundle,服务器 `git fetch /tmp/relay.bundle main` 后 `git merge --ff-only FETCH_HEAD`;必须核对服务器 HEAD 与 GitHub main 一致,不能用未提交文件覆盖生产代码。
