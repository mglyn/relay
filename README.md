# Relay · 共享 Pro 出资比例

给朋友共享一个 OpenAI Pro 账号使用的小站。sub2api 负责转发、独立用户/API Key 与模型用量统计；Relay 负责按订阅月累计周额度消耗、显示出资比例。没有充值、金额或逐次收费页面。

## 分摊规则

`pᵢ = uᵢ / [100 × (1 + R)] + {1 − Σu / [100 × (1 + R)]} / n`

- `uᵢ`：个人跨周累计的额度消耗，单位为百分比点，100 表示完整一周额度。
- `R`：该订阅月内的官方周重置与已使用重置卡的合计次数。初始额度不重复算重置。
- 每次重置按名义增加 100% 计，少补的部分及未使用部分全员均摊。
- 原始比例按最大余数法保留两位小数，显示合计恒为 100.00%。
- 例如三人分别消耗 80、40、20 个百分比点，发生一次重置：50%、30%、20%。

## 自动估算的含义与边界

每 60 秒从 sub2api 的只读 `GET /api/v1/admin/openai/accounts/:id/quota` 读取主 rate_limit 中窗口时长为 604800 秒的周额度。再读取 `/api/v1/admin/usage/stats`，按账号、用户、订阅日期筛选，以 `total_cost`（原始模型价格、非用户倍率后金额）的增量作为个人权重。比例是约定的估算，不是 OpenAI 提供的个人精确账单。

首次采样建立基线，不把已经消耗的额度凭空分配给成员。采样前的用量需要补录。成员须从头使用独立 sub2api 用户且使用同一共享账号；站外使用无法可靠归属。请求、上游额度和日志并非原子快照，缓存、取整、并发与日志延迟都可能影响估算。

**重置处理刻意保留人工核对**：周窗口变化、额度下降或过期会暂停自动归属，不猜测跨重置空档用量或自动使用重置卡。管理员补记重置次数和个人用量修正后，点击“核对完成，建立新基线”。否则前端明确显示待核对。它不会在无观测数据时声称实现精确自动结算。

按上海时区自然日期统计，结束日期包含当天（例如 9 月 17 日至 10 月 16 日）。不支持小时级订阅边界。月末执行最后一次采样、人工核对空档、封账，再创建新周期。封账后的比例冻结，周期内成员名单固定；暂不支持期中入退群或多个 Pro 账号混算。账本使用 SQLite WAL 持久化，所有修正追加记录。

## 腾讯云部署

需要 Linux、Docker Compose、80/443 入站可达，以及可访问 OpenAI 的上游网络。API 与前端使用两个域名，Caddy 自动签发 HTTPS。可临时使用 `relay.<IP>.sslip.io` 与 `api.<IP>.sslip.io`，长期使用建议改为自己的域名。

```sh
git clone https://github.com/mglyn/relay.git /opt/relay
cd /opt/relay
python3 scripts/init_env.py relay.example.com api.example.com
docker compose up -d --build
```

`.env` 自动生成随机独立密码，权限 0600，不提交 Git。管理员可在服务器本地查看该文件：`DASHBOARD_ADMIN_PASSWORD` 是账本管理密码，`VIEWER_PASSWORD` 是朋友查看比例的密码，`SUB2API_ADMIN_PASSWORD` 是中转管理密码。只把查看密码给朋友；不要分享上游 OAuth、管理密码或管理 API Key。

初始化 sub2api 后运行 `scripts/bootstrap.py`（脚本在 dashboard 容器内连接内网），自动关闭公开注册并生成供账本使用的管理 API Key；见脚本帮助。然后重建 dashboard 服务使环境变量生效。

在 sub2api 管理台完成：

1. 导入/授权你自己的 Pro 上游账号（不要把 OAuth token 发到聊天或 Git）。
2. 建立共享分组、每人一个用户及各自 API Key，将请求路由到该账号。
3. 在 Relay 管理页面填写订阅月、上游账号 ID、成员用户 ID 与昵称。
4. 首次采样并核对之前的消耗；朋友用查看密码登录即可查看出资比例。

外部客户端使用中转域名及自己的 sub2api API Key，路径以 sub2api 对应客户端配置为准。子服务、Postgres 与 Redis 不映射公网端口。

更新：`git pull --ff-only && docker compose up -d --build`。生产中把 `.env` 的 `SUB2API_IMAGE` 固定到已验证的镜像 digest。数据库迁移前先备份。

备份：对 `relay_ledger` 用 SQLite 在线备份，对 Postgres 用 `pg_dump`，同时保存 `.env`、sub2api 数据卷和 Caddy 数据卷。不要直接复制正在写入的 SQLite 主文件而忽略 WAL；不要运行 `docker compose down -v`，它会删除数据卷。

## 开发与校验

后端仅使用 Python 标准库，前端为原生 HTML/CSS/JS。容器安装 tzdata 以支持上海时区。

```sh
python -m unittest discover -s tests -v
node --check app/static/app.js
```

本地运行需设置至少 16 位且不同的 `ADMIN_PASSWORD`、`VIEWER_PASSWORD`，以及 `SESSION_SECRET`。仅本地 HTTP 调试设 `COOKIE_SECURE=false`。`SUB2API_ADMIN_KEY` 只留在服务端。未配置真实上游时页面显示空状态，不放置假账单。

参考上游：[Wei-Shaw/sub2api](https://github.com/Wei-Shaw/sub2api)。接口核验于源码提交 `881f3202694c6bc932446931a30c27d9675178b9`；镜像版本升级后应重新核验接口。
