# DeepTutor 观测栈（Prometheus + Alertmanager）

把 `/metrics/prometheus` 从"被动可查"变成"主动告警"的可部署基础设施。本目录提供
一套独立 compose，按需在生产宿主拉起 Prometheus + Alertmanager，scrape DeepTutor
并在异常时主动外发告警。

> **本 PR 只准备这套基础设施，不部署。** 拉起 = 在生产宿主跑两个新容器，属于基础设施
> 变更，需明确决定后再执行。下面是部署 runbook，供审阅与日后执行。

## 文件清单

| 文件 | 作用 |
|---|---|
| `prometheus.yml` | 自托管 Prometheus 容器的完整主配置（scrape `deeptutor:8001`、告警→alertmanager、rule_files 复用下面的 alerts）。 |
| `prometheus.alerts.example.yml` | 告警规则（**单一 authority**，被 CI `verify_runtime_assets.py` 校验；compose 把它挂为 prometheus 的 rule file，不另起第二份）。 |
| `prometheus.scrape.example.yml` | 可移植 scrape 片段，给"已有自己 Prometheus、只想合并 DeepTutor job"的场景；本容器化栈不用它。 |
| `alertmanager.yml` | Alertmanager 配置；默认邮件出口，飞书需适配器（见文件内注释）。 |
| `docker-compose.observability.yml` | 拉起 Prometheus + Alertmanager 两容器。 |
| `secrets/` | 运行期 secret 文件（`.gitignore` 排除，永不入库）。 |

## 部署 runbook

```bash
cd /root/deeptutor   # 生产宿主，主 compose 所在目录

# 1. 确认外部网络名（compose 文件默认假设 deeptutor_deeptutor-network）
docker network ls | grep deeptutor
# 若不是 deeptutor_deeptutor-network，改 docker-compose.observability.yml 里 networks.*.name

# 2. 创建 secret 文件（不入库）
mkdir -p deployment/observability/secrets
printf '%s' "$DEEPTUTOR_METRICS_TOKEN" > deployment/observability/secrets/metrics_token   # 必须等于 .env 里的同名值
printf '%s' "$SMTP_PASSWORD"           > deployment/observability/secrets/smtp_password   # 邮件出口口令

# 3. 把 alertmanager.yml 的占位（smtp_smarthost / smtp_from / to）改成真实值

# 4. 部署前校验（不需要拉起容器）
promtool check rules deployment/observability/prometheus.alerts.example.yml
docker run --rm -v "$PWD/deployment/observability/alertmanager.yml:/c.yml:ro" \
  prom/alertmanager:v0.27.0 amtool check-config /c.yml

# 5. 拉起
docker compose -f deployment/observability/docker-compose.observability.yml up -d

# 6. 验证
curl -s http://127.0.0.1:9090/-/ready                 # Prometheus ready
curl -s http://127.0.0.1:9090/api/v1/targets | grep deeptutor   # target up
curl -s http://127.0.0.1:9093/-/ready                 # Alertmanager ready
```

回滚：`docker compose -f deployment/observability/docker-compose.observability.yml down`
（数据卷保留，再 `down -v` 才删历史）。

## ⚠️ 已知限制：多 worker 少计（本 PR 不修，独立跟进）

生产 `UVICORN_WORKERS=2`。`/metrics/prometheus` 由自写渲染器
（`deeptutor/api/runtime_metrics.py: render_prometheus_metrics`）读**进程内单例**，
两个 worker 共享一个监听 socket、各自计数。Prometheus 每次 scrape 只命中其中一个 worker：

- **计数类**（`deeptutor_http_*_total`、`deeptutor_turns_*_total`、`deeptutor_ws_*_total`、
  `deeptutor_surface_event_total`）：约 `1/N` 少计，且 counter 会在 worker 间跳变，
  `rate()/increase()` 不可靠。`DeepTutorServerErrors` 这类阈值告警因此偏**漏报**方向（不会误报）。
- **per-worker 状态闸**（`deeptutor_circuit_breaker_open`、`deeptutor_provider_threshold_exceeded`）：
  scrape 可能恰好落在没开闸的 worker，**漏报**另一 worker 的开闸/超阈。
- **不受影响**：`deeptutor_ready`/`deeptutor_readiness_check`（每 worker 一致）、
  `deeptutor_release_info`（每 worker 一致）。`DeepTutorNotReady` 与
  `DeepTutorMetricsScrapeDown`（scrape 存活自监控）可信。

**为什么这版不修**：根治 = 把这 5 个单例迁到 `prometheus_client` 多进程模式
（`PROMETHEUS_MULTIPROC_DIR` + `MultiProcessCollector`，counter 自动跨 worker 汇总、
gauge 用 `livesum`、均值改 histogram/sum+count）。这是一次触及 `record_request` 中间件
与 turn 生命周期等**热路径**的重新埋点，blast radius 远大于"立 Prometheus"本身，按
surgical-changes 拆成独立 PR 单独测。专家面板已否决用 valkey 手搓 INCR（重造轮子 +
热路径加 RTT 压低并发天花板）。在多进程迁移 PR 落地前，按上面的可信/不可信清单解读看板。

## 关系

- 与 `docs/zh/guide/runtime-observability.md`：那篇是端点与指标语义的总说明，本目录是
  可部署的容器化实现。
- 与 nightly cron 告警：cron 是批处理（红即 GitHub 邮件），本栈是实时 scrape + 阈值告警，
  两者互补，不替代。
