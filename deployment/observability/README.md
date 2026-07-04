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
| `../../data/observability-secrets/` | 运行期 secret 文件（`metrics_token` / `smtp_password`）。放在 `data/` 下因为它被 `sync_to_aliyun.sh` 排除，全量发布 (`rsync --delete`) 删不掉；永不入库。 |

## 部署 runbook

```bash
cd /root/deeptutor   # 生产宿主，主 compose 所在目录

# 1. 确认外部网络名（compose 文件默认假设 deeptutor_deeptutor-network）
docker network ls | grep deeptutor
# 若不是 deeptutor_deeptutor-network，改 docker-compose.observability.yml 里 networks.*.name

# 2. 创建 secret 文件（不入库）
# Secret 放在 data/ 下 (sync 排除, 全量发布删不掉)
mkdir -p data/observability-secrets
printf '%s' "$DEEPTUTOR_METRICS_TOKEN" > data/observability-secrets/metrics_token   # 必须等于 .env 里的同名值
printf '%s' "$SMTP_PASSWORD"           > data/observability-secrets/smtp_password   # 邮件出口口令

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

## 多 worker 正确性（Step 2 已治本，方案 B）

生产 `UVICORN_WORKERS=2`。`/metrics/prometheus` 由自写渲染器
（`deeptutor/api/runtime_metrics.py: render_prometheus_metrics`）读进程内单例。Step 2
（`deeptutor/services/observability/multiworker_metrics.py`）让每个 worker 后台定时把自己的
`snapshot()` dump 到 `data/runtime/observability/worker_metrics/worker-<pid>.json`，scrape
端点读所有 fresh worker 文件 + 自己的 live 快照，**按字段语义合并**后再渲染：

- **计数类** counter 求和；**均值**按各自 count 重新加权（精确）。
- **per-worker 状态闸**（`deeptutor_circuit_breaker_open` / `deeptutor_provider_threshold_exceeded`）
  用 **OR** 合并——任一 worker 开闸/超阈即上报，不再漏报。
- **崩溃安全**：死 worker 的文件按 **pid 存活**立即剔除并 reap（不只按 age），避免 OOM 崩溃 +
  新 pid 重启时短暂双计数（counter 虚高后跌落 = rate() 假象）。
- 热路径零改动（专家面板否决了 `prometheus_client` multiproc 的双重埋点方案：会给延迟敏感的
  `record_request` / turn 生命周期加开销）。

**生效前提**：deeptutor 容器跑的镜像必须已含 Step 2。用
`scripts/verify_aliyun_observability_stack.sh` 的 worker_metrics 检查确认 dump loop 在生产 live
（没有 fresh 文件 = Step 2 未部署，合并退回单 worker 视图）。

## 验证（可重复，替代一次性手动 curl）

```bash
bash scripts/verify_aliyun_observability_stack.sh
```

只读、走 SSH/127.0.0.1。检查 Prometheus/Alertmanager 存活、`up{job="deeptutor"}==1`
（端到端证明 scrape + metrics_token 字节匹配）、6 条规则加载且 health=ok、Prometheus→Alertmanager
投递通路、worker_metrics 新鲜度（Step 2 dump loop 活体）。硬失败退出 1，软问题 WARN。

> **兼容性**：生产宿主的 python 是 **3.6.8**，脚本刻意零变量注解（PEP 585 `list[str]` 在
> 3.6 运行时不可下标，`from __future__ import annotations` 也要 3.7+）。改这个脚本时保持
> 3.6 兼容，别加 `x: list[str]` 之类的注解。

> **告警交付（重要）**：`alertmanager.yml` 默认是 `example.com` 占位——规则会计算、在 UI 可见，
> 但**不会真正外发通知**。验证脚本会以 WARN 提示"ALERT DELIVERY NOT CONFIGURED"。配好真实
> SMTP/飞书/企微出口前，**不要把绿状态读成"会被 page"**。

## 关系

- 与 `docs/zh/guide/runtime-observability.md`：那篇是端点与指标语义的总说明，本目录是
  可部署的容器化实现。
- 与 nightly cron 告警：cron 是批处理（红即 GitHub 邮件），本栈是实时 scrape + 阈值告警，
  两者互补，不替代。
