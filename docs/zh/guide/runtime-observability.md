# DeepTutor 运行态观测与告警

这份说明只覆盖仓库内已经落地的最小观测闭环：

- `healthz`：进程存活
- `readyz`：启动期 readiness
- `metrics`：机器可读 JSON 快照
- `metrics/prometheus`：Prometheus 文本导出
- `control plane`：OM / ARR / AAE / ObserverSnapshot / OA / Release Gate 的 best-effort run history

控制面说明见：

- [docs/zh/guide/observability-control-plane.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/observability-control-plane.md)

注意：`/metrics` 与 `/metrics/prometheus` 不是匿名开放端点。它们要求：

- 管理员 bearer token，或
- 专用只读抓取令牌 `DEEPTUTOR_METRICS_TOKEN`

对当前阿里云生产环境，默认收口方式是：

- 公网域名 `https://test2.yousenjiaoyu.com` 不作为 metrics 抓取入口
- metrics / prometheus 统一通过 SSH 登录到 `Aliyun-ECS-2` 后访问 `127.0.0.1:8001`
- 发布链中的标准验收脚本是 [scripts/verify_aliyun_observability.sh](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/verify_aliyun_observability.sh)

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
- release lineage 快照
- turn runtime 快照
- surface ack coverage 快照
- readiness 快照
- provider error rate 快照
- circuit breaker 快照

### 4. Prometheus 指标

```bash
curl -fsS -H "X-Metrics-Token: $DEEPTUTOR_METRICS_TOKEN" http://127.0.0.1:8001/metrics/prometheus
```

### 4.1 阿里云生产验收

```bash
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor
bash scripts/verify_aliyun_observability.sh
```

脚本会通过 SSH 到 `Aliyun-ECS-2`，读取远端 `.env` 中的 `DEEPTUTOR_METRICS_TOKEN`，再对 `127.0.0.1:8001/metrics` 与 `127.0.0.1:8001/metrics/prometheus` 做只读校验。

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
- `deeptutor_billing_capture_total{status,reason,chargeable}`
- `deeptutor_wallet_mutation_total{event_type,direction,cause,outcome}`
- `deeptutor_wallet_mutation_requested_points_total{event_type,direction,cause,outcome}`

账务指标只使用固定低基数标签，不包含用户 ID、手机号、钱包 UUID、turn/session
或幂等键。`wallet_mutation_requested_points_total` 表示 RPC 请求/返回的观测量；
幂等重放是否真正产生新入账仍只能由 canonical `wallet_ledger` 审计确认。

## Prometheus 接入样例

仓库里提供了两个可直接改路径后使用的样例文件：

- scrape 配置：[deployment/observability/prometheus.scrape.example.yml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/observability/prometheus.scrape.example.yml)
- alert rules：[deployment/observability/prometheus.alerts.example.yml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/observability/prometheus.alerts.example.yml)

仓库内还提供了一个最小一致性校验脚本和工作流：

- 校验脚本：[scripts/verify_runtime_assets.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/scripts/verify_runtime_assets.py)
- 工作流：[.github/workflows/runtime-ops.yml](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.github/workflows/runtime-ops.yml)

它们只负责验证仓库内的约定是否还对齐，不替代生产环境里的 Prometheus / Alertmanager 接线。

典型接法（两选一）：

**A. 已有自己的 Prometheus —— 只合并 DeepTutor job**

1. 把 `prometheus.scrape.example.yml` 合并到你们现有 Prometheus 配置。
   确保目标环境注入 `DEEPTUTOR_METRICS_TOKEN`，让 scrape job 走只读 token。
2. 把 `prometheus.alerts.example.yml` 放到 Prometheus `rule_files` 路径。
3. 把告警接到你们自己的 Alertmanager、飞书或 PagerDuty。

**B. 没有 Prometheus —— 用仓库自带的可部署观测栈**

`deployment/observability/docker-compose.observability.yml` 提供一套独立 compose，
按需在生产宿主拉起 Prometheus + Alertmanager，scrape `deeptutor:8001` 并实时告警。
完整 runbook、secret 处理、部署前校验命令、以及多 worker 少计的已知限制，见
[`deployment/observability/README.md`](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deployment/observability/README.md)。

## 最小告警建议

基础可用性优先接以下 4 条：

1. `DeepTutorNotReady`
2. `DeepTutorServerErrors`
3. `DeepTutorProviderThresholdExceeded`
4. `DeepTutorCircuitBreakerOpen`

涉及真实钱包时还必须接入：

1. `DeepTutorBillingCaptureError`
2. `DeepTutorBillingEnforcementDisabled`
3. `DeepTutorBillingContextIncomplete`
4. `DeepTutorChargeableTurnNotCaptured`
5. `DeepTutorBillingCounterReset`
6. `DeepTutorNonChargeableCaptured`
7. `DeepTutorSuspiciousWalletCredit`
8. `DeepTutorWalletCounterReset`

如果你想减少人工核对，这个工作流会在相关文件变更时自动校验：

- `docker-compose.yml` 的 `readyz` healthcheck
- `prometheus.scrape.example.yml` 的 `metrics_path`
- `prometheus.alerts.example.yml` 的核心告警名
- 两份 runbook 是否仍引用正确脚本和端点

## 仍需在环境侧完成的动作

这些不能只靠仓库代码自动算“完成”：

- 把 `127.0.0.1:8001/metrics/prometheus` 真正接入 Prometheus
- 在目标环境配置 `DEEPTUTOR_METRICS_TOKEN`
- 把告警规则接到你们真实通知渠道
- 在目标环境跑一次 `readyz`、`verify_aliyun_observability.sh` 实机验证
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
