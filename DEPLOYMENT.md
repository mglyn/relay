# Tencent 部署交接

- 项目远端：https://github.com/mglyn/relay （main）。
- SSH 主机：`tencent`，项目目录 `/opt/relay`。
- 出资页面：https://129.211.211.114
- sub2api：https://129.211.211.114:8443
- `.env` 位于服务器项目根目录，权限 0600；本地登录凭据位于 `data/credentials.txt`（被 Git 忽略）。
- 生产账本为空，不包含本地验收示例。
- sub2api v0.2.5，部署镜像固定为 `ghcr.io/wei-shaw/sub2api@sha256:4c5dffab6e5ba4d3bd5382f19aad9654847b4e23de1a3d48e190146a3e6eb977`。

## 尚需账号持有人完成

1. 首次登录 sub2api 阅读并自行确认部署承诺。目前该步骤可能令管理接口返回 HTTP 423。
2. 在服务器执行 `python3 scripts/bootstrap.py`，然后 `docker compose up -d --no-deps dashboard`，连接账本自动采样。
3. 授权 Pro 账号，设置独立成员用户/API Key、共享分组及上游路由。填写订阅月起止日期、成员昵称及对应用户 ID。
4. 验证这台服务器到 OpenAI 的实际请求。如直连不可用，在 sub2api 为上游账号配置可用代理。未授权账号前无法验证真实模型调用或额度采样。

## 运维

```sh
cd /opt/relay
git pull --ff-only
docker compose build dashboard
docker compose up -d
docker compose up -d --force-recreate --no-deps caddy
docker compose ps
```

更新前先备份；固定镜像不会随 `latest` 自动升级。每次官方周重置或使用重置卡后，请到账本管理页核对重置次数及采样空档，建立新基线。月末核对并封账。不要清理生产数据卷。

如 GitHub 连接临时失败，可从已推送的本地仓库制作 Git bundle，服务器 `git fetch /tmp/relay.bundle main` 后 `git merge --ff-only FETCH_HEAD`；必须核对服务器 HEAD 与 GitHub main 一致，不能用未提交文件覆盖生产代码。
