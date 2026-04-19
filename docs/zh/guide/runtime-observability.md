# DeepTutor 运行态观测与告警

这份说明只覆盖仓库内已经落地的最小观测闭环：

- `healthz`：进程存活
- `readyz`：启动期 readiness
- `metrics`：机器可读 JSON 快照
- `metrics/prometheus`：Prometheus 文本导出

注意：`/metrics` 与 `/metrics/prometheus` 不是匿名开放端点。它们要求：

- 管理员 bearer token，或
- 专用只读抓取令牌 `DEEPTUTOR_METRICS_TOKEN`

## HTTP 端点

后端默认端口是 `8001`。

### 1. 存活检查

```bash
curl -fsS http://127.0.0.1:8001/healthz
```

用途：

- 容器存活检查
- 反向代理基础探活

### 2. 就绪检查

```bash
curl -fsS http://127.0.0.1:8001/readyz
```

用途：

- 启动完成前不接流量
- 检查配置、LLM、EventBus、TutorBot 是否完成初始化

当前 `docker-compose.yml` 已经把容器 healthcheck 切到 `readyz`。

### 3. JSON 指标

```bash
curl -fsS -H "X-Metrics-Token: $DEEPTUTOR_METRICS_TOKEN" http://127.0.0.1:8001/metrics | jq
```

内容包括：

- HTTP 请求总量、5xx 数量、状态码分布
- route 维度请求量、错误量、平均延迟
- readiness 快照
- provider error rate 快照
- circuit breaker 快照

### 4. Prometheus 指标

```bash
curl -fsS -H "X-Metrics-Token: $DEEPTUTOR_METRICS_TOKEN" http://127.0.0.1:8001/metrics/prometheus
```

当前导出的核心指标包括：

- `deeptutor_ready`
- `deeptutor_readiness_check`
- `deeptutor_http_requests_total`
- `deeptutor_http_errors_total`
- `deeptutor_http_status_total`
- `deeptutor_http_route_requests_total`
- `deeptutor_http_route_errors_total`
- `deeptutor_http_route_avg_latency_ms`
- `deeptutor_provider_total_calls`
- `deeptutor_provider_error_calls`
- `deeptutor_provider_error_rate`
- `deeptutor_provider_threshold_exceeded`
- `deeptutor_provider_alert_open`
- `deeptutor_circuit_breaker_failure_count`
- `deeptutor_circuit_breaker_open`
- `deeptutor_circuit_breaker_half_open`

## Prometheus 接入样例

仓库里提供了两个可直接改路径后使用的样例文件：

- scrape 配置：[deployment/observability/prometheus.scrape.example.yml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/observability/prometheus.scrape.example.yml)
- alert rules：[deployment/observability/prometheus.alerts.example.yml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/observability/prometheus.alerts.example.yml)

仓库内还提供了一个最小一致性校验脚本和工作流：

- 校验脚本：[scripts/verify_runtime_assets.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/verify_runtime_assets.py)
- 工作流：[.github/workflows/runtime-ops.yml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.github/workflows/runtime-ops.yml)

它们只负责验证仓库内的约定是否还对齐，不替代生产环境里的 Prometheus / Alertmanager 接线。

典型接法：

1. 把 `prometheus.scrape.example.yml` 合并到你们现有 Prometheus 配置。
   确保目标环境注入 `DEEPTUTOR_METRICS_TOKEN`，让 scrape job 走只读 token。
2. 把 `prometheus.alerts.example.yml` 放到 Prometheus `rule_files` 路径。
3. 把告警接到你们自己的 Alertmanager、飞书或 PagerDuty。

## 最小告警建议

如果只先接 4 条，优先级建议如下：

1. `DeepTutorNotReady`
2. `DeepTutorServerErrors`
3. `DeepTutorProviderThresholdExceeded`
4. `DeepTutorCircuitBreakerOpen`

如果你想减少人工核对，这个工作流会在相关文件变更时自动校验：

- `docker-compose.yml` 的 `readyz` healthcheck
- `prometheus.scrape.example.yml` 的 `metrics_path`
- `prometheus.alerts.example.yml` 的核心告警名
- 两份 runbook 是否仍引用正确脚本和端点

## 仍需在环境侧完成的动作

这些不能只靠仓库代码自动算“完成”：

- 把 `/metrics/prometheus` 真正接入 Prometheus
- 在目标环境配置 `DEEPTUTOR_METRICS_TOKEN`
- 把告警规则接到你们真实通知渠道
- 在目标环境跑一次 `readyz`、`metrics/prometheus` 实机验证
- 至少做一次告警演练，确认通知链路是通的

## 结论

到这一步，仓库内已经具备：

- 健康检查入口
- 就绪检查入口
- 机器可读指标出口
- Prometheus 接入样例
- 最小告警规则样例

剩下的是环境接线，不再是代码缺失。

## 仓库内自动化守门

为了避免这条链路只停在文档层，仓库里还补了定期演练工作流：

- 运行态演练工作流：[.github/workflows/runtime-drill.yml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.github/workflows/runtime-drill.yml)

它会定期跑备份/恢复与保留策略回归，保证：

- 备份脚本仍可执行
- 恢复脚本仍可执行
- 清理策略不会误删最近归档
