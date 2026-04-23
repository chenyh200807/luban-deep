# DeepTutor 观测控制面

这份说明覆盖 `OM / ARR / AAE / ObserverSnapshot / ChangeImpactRun / OA / Release Gate` 的仓库内最小控制面。

目标不是替代生产 BI，而是保证当前仓库已经具备：

1. 统一 run history
2. 统一 release spine
3. best-effort artifact fallback
4. 可直接调用的脚本与 API

## 1. 存储位置

默认落盘目录：

- `tmp/observability/control_plane`

按 kind 分目录：

1. `om_runs`
2. `arr_runs`
3. `aae_composite_runs`
4. `oa_runs`
5. `release_gate_runs`
6. `incident_ledger`
7. `benchmark_runs`
8. `daily_trends`
9. `observer_snapshots`
10. `change_impact_runs`

每个 kind 都包含：

1. `<run_id>.json`
2. `latest.json`
3. `history.jsonl`

环境变量：

- `DEEPTUTOR_OBSERVABILITY_STORE_DIR`

可重定向控制面目录。

## 2. 脚本入口

### 2.1 ARR

```bash
python3.11 scripts/run_arr_lite.py --mode lite
python3.11 scripts/run_arr_lite.py --mode full --baseline /path/to/prev.json
```

当前产物：

1. `tmp/arr/*.json`
2. `tmp/arr/*.md`
3. `tmp/observability/control_plane/arr_runs/*.json`

### 2.2 OM

live 模式：

```bash
python3.11 scripts/run_om_snapshot.py --api-base-url http://127.0.0.1:8001
```

离线模式：

```bash
python3.11 scripts/run_om_snapshot.py --metrics-json tmp/observability/mock_metrics.json
```

可选 stack probes：

```bash
python3.11 scripts/run_om_snapshot.py \
  --api-base-url http://127.0.0.1:8001 \
  --langfuse-url http://127.0.0.1:3000 \
  --grafana-url http://127.0.0.1:3001 \
  --prometheus-url http://127.0.0.1:9090
```

### 2.3 AAE

```bash
python3.11 scripts/run_aae_snapshot.py
python3.11 scripts/run_aae_snapshot.py --arr-json /path/to/arr.json --om-json /path/to/om.json
```

### 2.4 ObserverSnapshot

`ObserverSnapshot` 是 OA 的 raw evidence bundle。它只聚合已存在事实源：control-plane runs、turn event log、surface ack、以及可选 `/metrics` JSON；它不是新的 turn/session/trace authority。

```bash
python3.11 scripts/run_observer_snapshot.py
python3.11 scripts/run_observer_snapshot.py --metrics-json tmp/observability/mock_metrics.json
```

每个 source 都必须显式暴露：

1. `has_data`
2. `source_id`
3. `recorded_at`
4. `age_seconds`
5. `freshness`
6. `sample_count`
7. `confidence`

当前 schema：

1. `schemas/observer_snapshot_v1.json`
2. `schemas/oa_run_v1.json`

当前产物：

1. `tmp/observability/observer/raw_data_latest.json`
2. `tmp/observability/observer/raw_data_latest.md`
3. `tmp/observability/control_plane/observer_snapshots/*.json`

### 2.5 ChangeImpactRun

`ChangeImpactRun` 是每次 commit 或本地修改的变更影响 authority。它只读 git changed files、最新 `ObserverSnapshot`、`OM`、`ARR`、`AAE`，输出 changed domains、required gates、first failing signal、risk 与下一步命令；`OA` 和 `Release Gate` 消费这份结果，不再各自发明第二套 change impact 语义。

```bash
python3.11 scripts/run_change_impact.py
python3.11 scripts/run_change_impact.py --changed-file deeptutor/services/session/turn_runtime.py
python3.11 scripts/run_change_impact.py --observer-json tmp/observability/observer/raw_data_latest.json
```

当前产物：

1. `tmp/observability/control_plane/change_impact_runs/*.json`
2. `tmp/observability/control_plane/change_impact_runs/*.md`
3. `tmp/observability/control_plane/change_impact_runs/latest.json`

### 2.6 OA

```bash
python3.11 scripts/run_oa.py --mode daily
python3.11 scripts/run_oa.py --mode pre-release
python3.11 scripts/run_oa.py --mode incident
python3.11 scripts/run_oa.py --mode pre-release --observer-json tmp/observability/observer/raw_data_latest.json
python3.11 scripts/run_oa.py --mode pre-release --change-impact-json tmp/observability/control_plane/change_impact_runs/latest.json
```

未显式传 `--observer-json` 或 `--change-impact-json` 时，`OA` 会 best-effort 读取控制面最新 `observer_snapshots/latest.json` 与 `change_impact_runs/latest.json`。

`OA` 会额外输出 `causal_candidates`，schema 为 `causal_oa_v1`。它不是第二套变更影响判断，只是把 canonical `ChangeImpactRun.first_failing_signal`、`changed_domains`、source run ids、验证命令组织成可排序的因果候选。

### 2.7 Release Gate

```bash
python3.11 scripts/run_release_gate.py
python3.11 scripts/run_release_gate.py --change-impact-json tmp/observability/control_plane/change_impact_runs/latest.json
```

### 2.7.1 Benchmark 单一主脊梁

canonical benchmark runbook 见：

- [docs/zh/guide/benchmark-spine.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/guide/benchmark-spine.md)

三个固定消费视图：

```bash
python3.11 scripts/run_benchmark.py pr_gate_core --output-dir tmp/benchmark/pr-gate
python3.11 scripts/run_daily_benchmark.py --output-dir tmp/benchmark/daily
python3.11 scripts/run_incident_replay.py --incident-id INC-001 --output-dir tmp/benchmark/incident
```

控制面新增：

1. `benchmark_runs`
2. `daily_trends`

### 2.7.2 Failed Turn Promotion

真实 failed / timeout turn 进入 incident replay 候选，不直接改 benchmark registry。它先写 `incident_ledger`，后续仍按 benchmark promotion 规则人工或半自动晋升。

```bash
python3.11 scripts/run_failed_turn_promotion.py --incident-id INC-TURN-001
python3.11 scripts/run_failed_turn_promotion.py --incident-id INC-TURN-001 --days 1 --limit 20
```

当前产物：

1. `tmp/observability/failed_turn_incidents/*.json`
2. `tmp/observability/failed_turn_incidents/*.md`
3. `tmp/observability/control_plane/incident_ledger/*.json`

### 2.8 Unified WS Smoke

```bash
python3.11 scripts/run_unified_ws_smoke.py \
  --api-base-url http://127.0.0.1:8001 \
  --message "请只回复ok。"
```

### 2.9 一键 Pre-release

```bash
python3.11 scripts/run_prerelease_observability.py \
  --api-base-url http://127.0.0.1:8001 \
  --ws-smoke-message "请只回复ok。" \
  --surface-smoke web
```

一键链路顺序固定为：

```text
OM -> ARR -> AAE -> ObserverSnapshot -> ChangeImpactRun -> OA -> ReleaseGate
```

### 2.10 一键 Daily Observability

Daily 链路用于每天或每次开发收口时快速回答：

1. 这次变更影响了哪些 domain
2. 第一个失败信号是什么
3. OA 的因果候选和 blind spots 是什么
4. Release Gate 当前建议是什么
5. 最近 run history 能否按 commit 过滤

```bash
python3.11 scripts/run_observability_daily.py
python3.11 scripts/run_observability_daily.py --changed-file deeptutor/services/session/turn_runtime.py
python3.11 scripts/run_observability_daily.py --output-dir tmp/observability/daily
```

固定链路为：

```text
ObserverSnapshot -> ChangeImpactRun -> OA(causal_oa_v1) -> ReleaseGate -> DailyTrend -> RunHistory
```

## 3. API 入口

当前已经开放最小控制面查询接口：

1. `POST /api/v1/observability/surface-events`
2. `GET /api/v1/observability/control-plane/{kind}/latest`
3. `GET /api/v1/observability/control-plane/{kind}/history?limit=10`
4. `GET /api/v1/observability/control-plane/run-history?limit=20&commit_sha=<sha-prefix>`

例如：

```bash
curl -fsS http://127.0.0.1:8001/api/v1/observability/control-plane/arr_runs/latest | jq
curl -fsS http://127.0.0.1:8001/api/v1/observability/control-plane/change_impact_runs/latest | jq
curl -fsS "http://127.0.0.1:8001/api/v1/observability/control-plane/release_gate_runs/history?limit=5" | jq
curl -fsS "http://127.0.0.1:8001/api/v1/observability/control-plane/run-history?limit=20&commit_sha=$(git rev-parse --short HEAD)" | jq
```

## 4. 当前语义边界

这套控制面是派生事实，不是业务 authority。

必须继续遵守：

1. turn/session truth 仍在 `unified_turn + session store`
2. trace/observation truth 仍在 `Langfuse`
3. runtime metrics truth 仍在 `/metrics` 与 `Prometheus`
4. `ObserverSnapshot` 只做 raw evidence bundle 与 blind spots 聚合，不写回业务状态
5. `ChangeImpactRun` 是变更影响的唯一控制面 authority；`OA` 和 `Release Gate` 只消费它，不重新发明 change impact 语义
6. `causal_oa_v1` 只排序和解释 canonical source runs，不负责重新判定 changed domains
7. failed turn promotion 只写 incident candidates，不直接改 benchmark registry 或 gate tier
8. control plane 只做 run history、摘要、gate、blind spots、RCA 候选

## 5. 当前已知限制

1. `OM` 的 live snapshot 仍依赖真实后端进程；若没有运行中的 `8001`，请用 `--metrics-json` 离线模式。
2. `AAE` 第一版仍以 proxy 为主，尤其是 `paid_student_satisfaction_score`。
3. `ObserverSnapshot` 若没有 turn event log，会明确暴露 `missing_turn_event_log`，而不是用 OM/ARR 代理事实伪装成真实 turn 观测。
4. `OA` 当前是规则化 observer，不是全自动高置信度根因系统。
5. `ChangeImpactRun` 第一版使用 deterministic file-domain mapping 与已有信号交叉判断，不做学习式因果模型。
6. `RunHistory` 当前读取 control-plane `history.jsonl`，不做长期归档压缩；如果需要跨月趋势，应接外部 warehouse。
7. failed turn promotion 第一版只生成 replay candidates；是否晋升为 regression tier 仍走 benchmark promotion 合同。
8. `Release Gate` 在 `AAE` 高比例 proxy、blind spot 偏大或 change impact 高风险时，默认只给 `WARN` 或 `FAIL`，不会伪装成强 PASS。
9. `Unified WS Smoke` 会触发一次真实 LLM turn；在本地验证或 pre-release 场景用它补强主链路证据，不建议高频定时触发。
