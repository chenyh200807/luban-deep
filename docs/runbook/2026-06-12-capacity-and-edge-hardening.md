# 容量与边缘加固 — 应用步骤 + 内存发现

> nginx 配置文件在 `/root/deeptutor/deployment/aliyun/nginx/`(写边界内)。
> 涉及 `/etc/nginx`、`/root/luban`、`/www/server` 的步骤是**宿主机操作**
> (§3.7 边界外),需由运维执行或显式授权。

## 1. 内存真相(2026-06-12 实测)

容器内存其实都不大,真正吃内存的是**宿主机非容器进程**:

| 进程 | RSS | 归属 |
|---|---|---|
| `/www/server/mysql/bin/mysqld` | **6.88 GB** | 宝塔面板 MySQL,**deeptutor 不用**(用 Supabase+SQLite) |
| next-server / node ×N | ~1.5 GB | 其它前端应用 |
| jgzk-langfuse 全栈(6 容器) | ~2.4 GB | 观测,中等 |
| deeptutor(2 worker) | 0.76 GB | 本应用 |

**减负最大杠杆是那个 6.88GB MySQL,不是 Langfuse。** 处置(需你决定,边界外):
- 确认这个 MySQL 服务于谁。deeptutor / BI 都不用则可停,省 7GB。
- 若在用 → 调 `innodb_buffer_pool_size` 到 1–2GB(宝塔→数据库→性能调整,
  或 `/www/server/mysql/etc/my.cnf`)。
- Langfuse 次要(~1GB):`/root/luban/langfuse/docker-compose.yml` 给
  clickhouse/minio 加 `mem_limit`(如 `mem_limit: 1g`)后 `docker compose up -d`。

## 2. nginx 边缘限流 + WAF + 安全头(配置已在仓库)

- `deployment/aliyun/nginx/deeptutor-ratelimit.conf.example` — http 上下文限流/连接 zone
- `deployment/aliyun/nginx/deeptutor-api.conf.example` — server 块:分级限流/连接上限/WAF/安全头

**应用(宿主机 /etc/nginx,边界外,需运维执行):**
```bash
sudo cp /root/deeptutor/deployment/aliyun/nginx/deeptutor-ratelimit.conf.example \
        /etc/nginx/conf.d/deeptutor-ratelimit.conf
# 把现有 api server 块替换/合并为新版(server_name 改成真实域名)
# 定位现有配置:nginx -T | grep -n test2  或宝塔面板
sudo nginx -t && sudo systemctl reload nginx   # 校验不过不要 reload
```

限流口径:认证端点 1r/s+burst5(挡 OTP 暴力/刷注册);其它 API 20r/s+burst40;
per-IP 并发连接 ≤30;WAF 对 `.env`/`.git`/`wp-admin` 等扫描路径 444。

> 配套:应用侧 `DEEPTUTOR_TRUST_PROXY_HEADERS` 当前为关。要让应用层限流也按真实
> 客户端 IP,需 nginx `proxy_set_header X-Forwarded-For $remote_addr;`(覆盖非追加,防伪造)
> 后再开该开关。nginx 边缘用 `$binary_remote_addr`(真实 IP)已是强保护。

## 3. 真负载压测(harness 已就绪)

`scripts/loadtest_ws_capacity.py` — 默认安全(只测连接容量,不发 LLM turn)。

```bash
pip install websockets
python scripts/loadtest_ws_capacity.py --url wss://<host>/api/v1/ws \
    --connections 200 --ramp-seconds 20 --hold-seconds 30
# 含真实 turn(烧 $,小并发,需 token,勿对真实用户群跑):
python scripts/loadtest_ws_capacity.py --url wss://<host>/api/v1/ws \
    --connections 20 --with-turns --token "<JWT>"
```

测前测后抓内存:`ssh <host> 'docker stats --no-stream deeptutor; free -h'`。
有效容量数需 seeded 测试 token + 维护窗口/staging。当前 2 worker 是稳妥起点;
拿到 p95 + 内存峰值后再据数据定 worker(内存放开后可往 4 提)。
