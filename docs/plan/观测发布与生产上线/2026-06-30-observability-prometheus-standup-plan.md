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

### Step 2（独立 PR，Implemented — 改用方案 B，非原计划 A）

多 worker 少计根治。**原计划 A（prometheus_client multiproc）经复审否决**：5 个单例
同时喂 JSON `/metrics`(BI) + observer nightly 滚动 + turn 域逻辑，A 需热路径双重埋点 +
新依赖 + avg→histogram 改契约，且给延迟敏感热路径加开销（与本程序的延迟关切冲突）。

**改用方案 B（旁路文件合并，热路径零改动）**：每个 worker 后台定时器（15s）把现有
`snapshot()` dump 到 `<observability_dir>/worker_metrics/worker-<pid>.json`；
`/metrics/prometheus` 读所有 fresh worker 文件 + 自己 live 快照，按字段语义合并
（counter sum、avg 按 count 重新加权、provider 阈值/熔断器 OR——确保任一 worker 开闸
不被漏报），喂给**未改的渲染器**。陈旧 worker 文件按 mtime 窗口（60s）自动剔除；端点
fail-safe（合并出错回退 live）。无新依赖、无契约变更、复用现有 snapshot/render（单一真相）。
合并所需原始计数全用现成字段（`turn_latency_count == completed+failed+cancelled` 可派生），
零 snapshot 改动。`deeptutor/services/observability/multiworker_metrics.py` + 15 条
TDD 测试（含真实渲染器 shape 契约）。

## 验收标准

- [x] `promtool check rules prometheus.alerts.example.yml` → 5 rules SUCCESS
- [x] `promtool check config prometheus.yml`（rule_files 重定向本地后）→ syntax valid
- [x] `docker compose -f docker-compose.observability.yml config -q` → OK
- [x] `python scripts/verify_runtime_assets.py` → PASS（CI 门未破坏）
- [x] `pytest tests/scripts/test_runtime_assets.py` → PASS
- [ ] 部署前（执行时）：`amtool check-config alertmanager.yml`（README 已列，需 docker daemon）
- [ ] 部署后（执行时）：`/api/v1/targets` 显示 deeptutor target up

### Step 3（独立 PR，Implemented）验证体系加固

诚实自审发现"可验证体系"在 3 处其实没成立（共因 = borrowed-coverage / green-by-omission：
成功信号借自不真正行使被保证属性的 proxy）。4 专家团队对抗性加强后治本：

- **CI 触发边界（dormant authority）**：`runtime-ops.yml` 的 `paths:` 是"哪些文件重要"的第二份
  副本，与 guard 实际读的文件漂移（sync_to_aliyun.sh / Dockerfile / docker-compose.ghcr.yml
  都不在内）→ 删掉 `paths:`，让轻量不变量校验器每个 PR 无条件跑，杀整类。
- **告警从未行为级验证**：`promtool test rules`（`prometheus.alerts.test.yml`）真测 6 条告警
  fire/no-fire；CI 装 pinned promtool 跑 `check rules`+`test rules`。
- **端点 merge wiring 从未被测**（FakePathService 缺 `get_observability_dir` → 端点静默 fallback）
  → 补该方法 + 真 merge 端点测试（sibling-only 熔断器证明合并）+ fallback 测试。
- **Step 2 崩溃双计数 SEV-1 bug**：死 worker 文件 60s 内仍 fresh + 新 pid 文件 → 2× 虚高再跌
  → 按 **pid 存活**剔除+reap（治本 + 治文件泄漏）；+ 非 dict JSON 守卫 + merge 边界测试。
- **可重复栈验证件**：新建 `scripts/verify_aliyun_observability_stack.sh`（8 检查含 up==1 证
  token 字节匹配 + worker_metrics 活体）替代一次性手动 curl。
- **watch-the-watcher**：prometheus 加 `job_name: alertmanager` + 第 6 条 `AlertmanagerDown`。
- **诚实门**：`verify_runtime_assets.py` 校验 `alertmanager.yml` 结构；验证脚本检测 example.com
  占位 → WARN "交付未配置"，杜绝把绿读成"会被 page"。

**明确 GATED（不假绿）**：真 SMTP/飞书/企微交付（用户 defer）；Step 2 + 本 PR 的 live 2-worker
数值正确性（随下次发布上线后用验证脚本确认）；sidecar 宿主重启竞态 + OOM 余量（部署时验）。

## 相关代码入口

- `deeptutor/api/main.py` `/metrics/prometheus` 端点 + `_metrics_dump_loop` + lifespan 起停
- `deeptutor/services/observability/multiworker_metrics.py` 跨 worker 合并 + pid 存活剔除
- `deeptutor/api/runtime_metrics.py` `render_prometheus_metrics`
- `scripts/verify_runtime_assets.py` + `.github/workflows/runtime-ops.yml` CI 门（已删 paths）
- `scripts/verify_aliyun_observability_stack.sh` 可重复栈健康验证
- `deployment/observability/` 全部新增/改动文件（含 `prometheus.alerts.test.yml`）
