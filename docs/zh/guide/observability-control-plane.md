# DeepTutor 观测控制面

这份说明覆盖 `OM / ARR / AAE / OA / Release Gate` 的仓库内最小控制面。

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

### 2.4 OA

```bash
python3.11 scripts/run_oa.py --mode daily
python3.11 scripts/run_oa.py --mode pre-release
python3.11 scripts/run_oa.py --mode incident
```

### 2.5 Release Gate

```bash
python3.11 scripts/run_release_gate.py
```

### 2.5.1 Benchmark 单一主脊梁

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

### 2.6 Unified WS Smoke

```bash
python3.11 scripts/run_unified_ws_smoke.py \
  --api-base-url http://127.0.0.1:8001 \
  --message "请只回复ok。"
```

### 2.7 一键 Pre-release

```bash
python3.11 scripts/run_prerelease_observability.py \
  --api-base-url http://127.0.0.1:8001 \
  --ws-smoke-message "请只回复ok。" \
  --surface-smoke web
```

## 3. API 入口

当前已经开放最小控制面查询接口：

1. `POST /api/v1/observability/surface-events`
2. `GET /api/v1/observability/control-plane/{kind}/latest`
3. `GET /api/v1/observability/control-plane/{kind}/history?limit=10`

例如：

```bash
curl -fsS http://127.0.0.1:8001/api/v1/observability/control-plane/arr_runs/latest | jq
curl -fsS "http://127.0.0.1:8001/api/v1/observability/control-plane/release_gate_runs/history?limit=5" | jq
```

## 4. 当前语义边界

这套控制面是派生事实，不是业务 authority。

必须继续遵守：

1. turn/session truth 仍在 `unified_turn + session store`
2. trace/observation truth 仍在 `Langfuse`
3. runtime metrics truth 仍在 `/metrics` 与 `Prometheus`
4. control plane 只做 run history、摘要、gate、blind spots、RCA 候选

## 5. 当前已知限制

1. `OM` 的 live snapshot 仍依赖真实后端进程；若没有运行中的 `8001`，请用 `--metrics-json` 离线模式。
2. `AAE` 第一版仍以 proxy 为主，尤其是 `paid_student_satisfaction_score`。
3. `OA` 当前是规则化 observer，不是全自动高置信度根因系统。
4. `Release Gate` 在 `AAE` 高比例 proxy 或 blind spot 偏大时，默认只给 `WARN` 或 `FAIL`，不会伪装成强 PASS。
5. `Unified WS Smoke` 会触发一次真实 LLM turn；在本地验证或 pre-release 场景用它补强主链路证据，不建议高频定时触发。
