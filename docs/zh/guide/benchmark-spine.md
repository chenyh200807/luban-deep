# DeepTutor Benchmark 单一主脊梁

这份说明定义仓库内 benchmark 的 canonical 用法。目标是让发布门禁、日常趋势、事故归因都读取同一份 benchmark truth，而不是各自维护一套脚本和口径。

## 1. 单一 authority

benchmark 的一等事实来自：

1. registry：`tests/fixtures/benchmark_phase1_registry.json`
2. runner：`deeptutor/services/benchmark/runner.py`
3. artifact：`run_manifest / release_spine / suite_summaries / case_results / failure_taxonomy / baseline_diff / runtime_evidence_links / blind_spots`

消费者只能读取 artifact，不允许重新定义 case 身份、failure taxonomy 或成功标准。

## 2. Canonical suites

当前只承认 4 个 suite：

1. `pr_gate_core`：发布门禁核心集
2. `regression_watch`：日常趋势集
3. `incident_replay`：事故回放与 RCA seed
4. `exploration_lab`：研究和扩样，不参与 blocking gate

运行示例：

```bash
python3 scripts/run_benchmark.py pr_gate_core --output-dir tmp/benchmark/pr-gate
python3 scripts/run_benchmark.py --suite regression_watch --output-dir tmp/benchmark/regression
python3 scripts/run_benchmark.py incident_replay --output-dir tmp/benchmark/incident
python3 scripts/run_benchmark.py exploration_lab --output-dir tmp/benchmark/exploration
```

## 3. 三个消费视图

### 3.1 Pre-release Gate

发布门禁仍可通过一键观测链运行：

```bash
python3 scripts/run_prerelease_observability.py \
  --api-base-url http://127.0.0.1:8001 \
  --ws-smoke-message "请只回复ok。" \
  --surface-smoke web
```

`run_arr()` 现在是 canonical benchmark runner 的兼容 wrapper。`Release Gate` 的 `P2 Benchmark Regression` 优先读取 `benchmark_run_manifest / benchmark_case_results / baseline_diff`，`P4 Blind Spot Budget` 优先读取 benchmark blind spots。

### 3.2 Daily Trend

日常趋势只读 `regression_watch` 产物，并固定输出 6 个指标：

1. `pass_rate`
2. `new_regression_count`
3. `continuity_floor`
4. `groundedness_floor`
5. `surface_delivery_coverage`
6. `blind_spot_count`

运行：

```bash
python3 scripts/run_daily_benchmark.py --output-dir tmp/benchmark/daily
```

输出会写入：

1. `tmp/benchmark/daily/runs`
2. `tmp/benchmark/daily/trend`
3. control plane `benchmark_runs`
4. control plane `daily_trends`

### 3.3 Incident / RCA

事故回放只跑 `incident_replay` suite，并输出：

1. 已知 regression 数
2. 新 failure 数
3. 当前 failure 数
4. blind spot 数
5. replay candidates

运行：

```bash
python3 scripts/run_incident_replay.py \
  --incident-id INC-001 \
  --output-dir tmp/benchmark/incident
```

输出会写入：

1. `tmp/benchmark/incident/runs`
2. `tmp/benchmark/incident/incident`
3. control plane `benchmark_runs`
4. control plane `incident_ledger`

## 4. Surface contract

`surface.wx.renderer.parity` 不是口头检查。它会执行：

```bash
node wx_miniprogram/tests/test_renderer_parity.js
```

`surface.yousenwebview.telemetry.smoke` 是 `yousenwebview` 在 Phase 1 的 targeted smoke。它不做重自动化，只验证仓内可执行的表面埋点合同：

```bash
node yousenwebview/tests/test_chat_send_surface_telemetry.js
```

结果规则：

1. Node parity 通过：case `PASS`
2. Node 缺失：case `SKIP`，进入 `blind_spots`
3. parity 失败：case `FAIL`，failure type 为 `FAIL_SURFACE_DELIVERY`
4. 执行超时：case `FAIL`，failure type 为 `FAIL_TIMEOUT`

真实微信开发者工具或真机验证仍然是上线前 surface 验收的一部分；Node parity 只解决仓内自动化的最低合同。

## 5. Incident Promotion

incident 反哺 benchmark 必须走 registry proposal，不能口头把 case 挪进 gate。晋升链路固定为：

1. `incident_replay` -> `regression_tier`
2. `regression_tier` -> `gate_stable`

直接从 `incident_replay` 晋升 `gate_stable` 会被拒绝。

生成 registry proposal：

```bash
python3 scripts/promote_benchmark_case.py \
  --case-id surface.web.ack.smoke \
  --target-tier regression_tier \
  --output-registry-path tmp/benchmark/promoted_registry.json \
  --reason "INC-001 stable replay"
```

registry 中的 `origin_type / origin_ref / promotion_status / promoted_from_case_id` 是 case 来源与晋升状态的 canonical 字段。它们用于回答“这个 case 是否由 incident replay 晋升而来”，而不是靠 incident 文档或人工记忆。

## 6. Phase 1 验收查询

PRD §16 的 6 个问题必须能从 registry、suite projection、runner artifact 直接回答：

1. case 登记位置：`tests/fixtures/benchmark_phase1_registry.json`
2. 合同域：registry `contract_domain`
3. 所属 suite：registry `suites[*].case_ids`
4. 失败 taxonomy：registry `failure_taxonomy_scope` 与 artifact `failure_taxonomy`
5. 是否影响 pre-release gate：是否属于 `pr_gate_core`，或是否被晋升到 `gate_stable`
6. 是否由 incident replay 晋升：registry `origin_type == incident_replay`；`promoted_from_case_id` 只说明来源 case，不单独证明 incident 来源

代码内的 `build_case_acceptance_snapshot()` 是这 6 个问题的最小可测试入口。

## 7. 禁止事项

1. 不新增第二套 benchmark registry
2. 不新增第二套 failure taxonomy
3. 不让 daily / incident / gate 自己拼 case summary
4. 不把 `exploration_lab` 结果升级成发布门禁真相
5. 不绕过统一聊天入口 `/api/v1/ws`
