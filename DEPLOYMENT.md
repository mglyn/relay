# Tencent 部署交接

- 项目远端:https://github.com/mglyn/relay (main)。
- SSH 主机:`tencent`(root@129.211.211.114),项目目录 `/opt/relay`。
- 自建中转看板已于 2026-09-22 下线删除;443 端口现在返回 410,仅为 IP 证书 ACME 验证保留。
- sub2api(管理台 + 网关):https://129.211.211.114:8443 。按成员、按时间段的用量在管理台的使用统计/使用日志中查看。
- `.env` 位于服务器项目根目录,权限 0600;本地登录凭据位于 `data/credentials.txt`(被 Git 忽略)。
- sub2api v0.2.5,部署镜像固定为 `ghcr.io/wei-shaw/sub2api@sha256:4c5dffab6e5ba4d3bd5382f19aad9654847b4e23de1a3d48e190146a3e6eb977`。
- 2026-09-22 已执行 `scripts/bootstrap.py`:公开注册已关闭,`SUB2API_ADMIN_KEY` 已生成。
- 出站代理:compose 内 `mihomo` 服务,配置在 `/opt/relay/mihomo/config.yaml`(含机场订阅链接,权限 600,不提交 Git)。管理台已注册 HTTP 代理 `Mihomo`(mihomo:7890);导入 OpenAI 上游账号时选择它。节点经 `scripts/find_openai_node.py` 实测,当前钉住 `🇨🇳 B1019 台湾家宽`(多数节点会被 OpenAI 掐断 TLS);切换节点用 mihomo 控制接口(容器 IP:9090,`PUT /proxies/PROXY`),选择已持久化,重启不丢。
- `relay_ledger` 数据卷已无用途,留在服务器上未删(内容为空),可手动 `docker volume rm relay_ledger`。

## 尚需账号持有人完成

1. 在管理台导入/授权 Pro 上游账号,建立共享分组、成员用户与 API Key,配置上游路由。
2. 验证这台服务器到 OpenAI 的实际请求。如直连不可用,在 sub2api 为上游账号配置可用代理。

## 运维

```sh
cd /opt/relay
git pull --ff-only
docker compose up -d --remove-orphans
docker compose up -d --force-recreate --no-deps caddy   # 改过 Caddyfile 后
docker compose ps
```

更新前先备份;固定镜像不会随 `latest` 自动升级。不要清理 sub2api/postgres/redis/caddy 数据卷,不要运行 `docker compose down -v`。

如 GitHub 连接临时失败,可从已推送的本地仓库制作 Git bundle,服务器 `git fetch /tmp/relay.bundle main` 后 `git merge --ff-only FETCH_HEAD`;必须核对服务器 HEAD 与 GitHub main 一致,不能用未提交文件覆盖生产代码。
