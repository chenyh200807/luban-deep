# Prometheus + Alertmanager 可部署观测栈 — 实施计划

- **状态**：Step 1 Implemented（基础设施已准备，未部署）；Step 2 Proposed（多进程迁移，独立 PR）
- **日期**：2026-06-30
- **分支 / PR**：`feat/observability-prometheus-standup`
- **主线**：`观测发布与生产上线/` — eval 观测体系 L2→L3→L4
- **关联**：`docs/plan/观测发布与生产上线/2026-06-29-observability-production-hardening-execution.md`（P0/P1 加固，已上线）、`2026-05-30-system-maturity-audit.md`（M1 把 `*.example.yml` 落成真实 Prometheus+Alertmanager 的缺口）

## 背景

P0/P1 加固已把"干净代码接线"做完（持久化 + 假绿闸 + eval 通电），整体 L2→L3。但
告警仍是批处理（nightly cron 红即 GitHub 邮件），**生产无 Prometheus/Alertmanager
容器**，`deployment/observability/*.example.yml` 仍是模板。到 L4（实时主动告警）缺的
关键基础设施一步，就是把这套栈真正立起来。

## 目标

1. 提供一套**可部署、可审阅**的 Prometheus + Alertmanager 独立 compose，scrape
   `deeptutor:8001/metrics/prometheus`，实时评估告警规则并外发。
2. 复用 CI 校验过的 `prometheus.alerts.example.yml` 作为告警规则单一 authority，
   不另起第二份。
3. 新增 scrape 存活自监控告警（`DeepTutorMetricsScrapeDown`），让观测能发现"自己死了"。
4. Secret（metrics token / SMTP 口令）全部走文件挂载，永不入库。
5. 把多 worker 少计的已知限制**显式文档化**，给出可信/不可信指标清单。

## 非目标（明确不在本 PR）

- **不部署**：拉起 = 生产宿主跑两个新容器，属基础设施变更，需单独决定后执行。
- **不做 prometheus_client 多进程迁移**：根治多 worker 少计是一次触及热路径
  （`record_request` 中间件、turn 生命周期）的重新埋点，blast radius 远大于"立
  Prometheus"，按 surgical-changes 拆成 Step 2 独立 PR。
- **不接飞书**：Alertmanager 原生 webhook 与飞书 JSON schema 不兼容，需适配器；
  本 PR 默认邮件出口（与现有 cron 同渠道），飞书在配置里文档化为可选。

## 单一 authority

- **告警规则**：`prometheus.alerts.example.yml`（CI `verify_runtime_assets.py` 校验，
  compose 挂为 prometheus rule file）。
- **指标语义**：`deeptutor/api/runtime_metrics.py: render_prometheus_metrics`（不动）。
- **端点鉴权**：`DEEPTUTOR_METRICS_TOKEN` + `require_metrics_access`（不动）。

## 实施阶段

### Step 1（本 PR，Implemented）

- `prometheus.yml`：容器化 standalone 主配置（target `deeptutor:8001`、credentials_file、
  alerting→alertmanager、rule_files 复用 example alerts）。
- `prometheus.alerts.example.yml`：+1 条 `DeepTutorMetricsScrapeDown`（`up==0`）。
- `alertmanager.yml`：route + 邮件 receiver（SMTP 口令走 `*_file`，占位待替换）。
- `docker-compose.observability.yml`：prometheus + alertmanager 两容器，join 外部
  `deeptutor-network`，loopback 端口，持久卷。
- `secrets/.gitignore`：secret 文件永不入库。
- `README.md`：部署 runbook + 多 worker 限制文档 + Step 2 指针。
- `docs/zh/guide/runtime-observability.md`：新增"用仓库自带观测栈"接法 B。

### Step 2（独立 PR，Proposed）

prometheus_client 多进程迁移：5 个进程内单例 → Counter/Gauge/Histogram +
`PROMETHEUS_MULTIPROC_DIR` + `MultiProcessCollector`。counter 跨 worker 自动汇总、
gauge 用 `livesum`、均值改 histogram 或 sum+count。需热路径回归测试。

## 验收标准

- [x] `promtool check rules prometheus.alerts.example.yml` → 5 rules SUCCESS
- [x] `promtool check config prometheus.yml`（rule_files 重定向本地后）→ syntax valid
- [x] `docker compose -f docker-compose.observability.yml config -q` → OK
- [x] `python scripts/verify_runtime_assets.py` → PASS（CI 门未破坏）
- [x] `pytest tests/scripts/test_runtime_assets.py` → PASS
- [ ] 部署前（执行时）：`amtool check-config alertmanager.yml`（README 已列，需 docker daemon）
- [ ] 部署后（执行时）：`/api/v1/targets` 显示 deeptutor target up

## 相关代码入口

- `deeptutor/api/main.py:773` `/metrics/prometheus` 端点
- `deeptutor/api/runtime_metrics.py:214` `render_prometheus_metrics`
- `deeptutor/api/dependencies/auth.py:217` `require_metrics_access`
- `scripts/verify_runtime_assets.py` + `.github/workflows/runtime-ops.yml` CI 门
- `deployment/observability/` 全部新增/改动文件
