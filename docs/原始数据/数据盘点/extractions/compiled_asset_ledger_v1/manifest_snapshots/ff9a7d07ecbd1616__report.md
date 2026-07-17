# DeepTutor Observability OA/OM 日报

- report_date: `2026-07-06`
- generated_at: `2026-07-07 09:25:14 CST`
- verdict: `DEGRADED`
- authority: `PASS with caveat`
  - `pwd -L` = `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
  - `pwd -P` = `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
  - `git toplevel` = `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
  - `core.worktree` = empty
  - `artifacts/.env` = missing
  - `repo-root .env` = readable

## Execution Summary

本次只认 `artifacts` cwd 的 compliant run：

- command: `python ../scripts/run_observability_daily.py --output-dir tmp/observability/control_plane`
- daily_trends: `observability-daily-1783387344`
- oa_runs: `oa-daily-1783387344`
- om_runs: `om-1783387342`
- observer_snapshots: `observer-snapshot-1783387342`
- change_impact_runs: `change-impact-1783387344`
- release_gate_runs: `release-gate-1783387344`
- benchmark_runs: `benchmark-1783387323`
- readiness_checks: `readiness-matrix-1783387344`

日报窗口已按 `Asia/Shanghai` 冻结到昨天自然日：

- `report_date=2026-07-06`
- `start_ts=1783267200`
- `end_ts=1783353599`

结论先行：

1. control-plane 新鲜，`OM` 直接命中 `http://127.0.0.1:8001/metrics`，`fallback_used=false`
2. release gate 继续 `FAIL` 且 `hold`，说明 fail-closed 仍在工作
3. 真正失真的不是 release gate，而是 wrapper 语义层：`daily_trends.payload.verdict=TRUSTED` 但同轮 `release_gate.final_status=FAIL`

## Tier 0 / Battlefield 状态

- branch: `release/card-fit`
- `HEAD=c5fa4fc0ebfe37ffedf241c1c7fdb261c3108753`
- `origin/main=64e23513024852e81719e9ee127ff97cf5a7d47a`
- relative to `origin/main`: `ahead 2 / behind 133`
- dirty summary: `modified=59` + `added=21` + `deleted=1` + `untracked=15` = `96`
- dirty clustering:
  - `yousenwebview`: `71`
  - `docs*`: `9`
  - `deeptutor`: `5`
  - `scripts`: `4`
  - `tests`: `3`
  - `contracts`: `2`

这不是“少量后端热修”场景，而是表面层大面积未收口场景。所以 `change_impact.required_readiness_checks=['contract_guard', 'playwright', 'wechat_devtools']` 是合理升档，不是噪声。

## Freshness 表

| surface | latest run | age_hours | threshold | status |
| --- | --- | ---: | --- | --- |
| `daily_trends` | `observability-daily-1783387344` | `0.05h` | `36h` | `fresh` |
| `oa_runs` | `oa-daily-1783387344` | `0.05h` | `36h` | `fresh` |
| `om_runs` | `om-1783387342` | `0.05h` | `36h` | `fresh` |
| `observer_snapshots` | `observer-snapshot-1783387342` | `0.05h` | `36h` | `fresh` |
| `change_impact_runs` | `change-impact-1783387344` | `0.05h` | `36h` | `fresh` |
| `release_gate_runs` | `release-gate-1783387344` | `0.05h` | `7d` | `fresh` |
| `benchmark_runs` | `benchmark-1783387323` | `0.05h` | `7d` | `fresh` |
| `readiness_checks` | `readiness-matrix-1783387344` | `0.05h` | `36h` | `fresh` |
| `playwright readiness` | `playwright-1783387326` | `0.05h` | current-release reference | `fresh but FAIL` |
| `wechat_devtools readiness` | `wechat_devtools-1783387326` | `0.05h` | current-release reference | `fresh but FAIL` |
| `launch_readiness` | `launch-readiness-1783354722` | `9.12h` | current-release reference | `fresh and PASS` |

结论：今天不是 freshness gap。任何红灯都应按真实红灯处理。

## 昨日发生了什么

`2026-07-06`（Asia/Shanghai）只有一个正式 commit：

- `c5fa4fc0e` `fix(daily-health): restore turn authority gates`

其 diff 重点：

- `deeptutor/capabilities/deep_question.py`
- `deeptutor/services/session/turn_runtime.py`
- `contracts/turn.md`
- 多个 turn/capability/learner-state 测试
- `wx_miniprogram/utils/learning-report-view-model.js`

这条 commit 和今天控制面的正向变化是对得上的：

1. `OM` 的 `unified_ws_smoke_ok=True`
2. `turn_event_log` 已恢复，不再是 blind spot
3. `release_gate` 仍然 fail，说明“turn authority 恢复”并没有自动等于“surface readiness 闭环”

这是今天最容易被误判的点：昨天的修复确实改善了观测链，但它没有清掉发布门里最贵的两个 blocker。

## OA / OM / Observer / Release Gate

### OA

- `oa.verdict=TRUSTED`
- `turns_started=2`
- `turns_completed=2`
- `turns_failed=0`
- `provider_error_ratio=0.0`
- `unified_ws_smoke_ok=True`

但 OA 明确保留 3 个 canonical blind spots：

- `missing_surface_coverage`
- `missing_product_behavior_evidence`
- `missing_langfuse_trace_linkage`

### OM

- metrics provenance = `live_metrics_endpoint`
- endpoint = `http://127.0.0.1:8001/metrics`
- `status_code=200`
- `fallback_used=False`
- `turn_avg_latency_ms=4264.22`
- `turn_success_ratio=1.0`
- `unified_ws_smoke_ok=True`

SLO 分层：

- `turn_success_ratio` `PASS`
- `readyz_success_ratio` `PASS`
- `turn_p95_latency_seconds_proxy` `PASS`
- `provider_error_ratio` `PASS`
- `turn_first_render_ratio=None` `WARN`

结论：本地 runtime 活着，且 metrics provenance 没有 fallback 污染；但这仍只是一条本地工程证据，不是 release closure。

### Observer

- `coverage_ratio=0.7273`，即 `8/11`
- 已有数据：`turn_event_log`、`om_snapshot`、`quality_run`、`aae_composite`、`recent_conversations`、`backend_logs`、`daily_trend`、`live_metrics`
- 缺口仍是：
  - `surface_ack`
  - `product_behavior`
  - `langfuse_trace_linkage`
- `langfuse_enabled=false`

这里最关键的不是“还有 3 个盲区”，而是这 3 个盲区已经连续跨多轮存在：

- 最近 5 个 `OA` run 都保留同样 3 个 blind spots
- 最近 5 个 `release_gate` run 也保留同样 3 个 blind spots

所以这不该再被写成“今日新发现”，而应视为持久观测债。

### Release Gate

- `release_gate.verdict=TRUSTED`
- `final_status=FAIL`
- `recommendation=hold`
- blockers:
  - `runtime_release_dirty`
  - `playwright_evidence_missing`
  - `wechat_devtools_true_entry_pending`

gate 分层：

- `P0 Runtime = FAIL`
- `P1 Trace Completeness = WARN`
- `P2 Benchmark Regression = PASS`
- `P3 AAE = PASS`
- `P4 Blind Spot Budget = WARN`
- `P5 Change Impact = WARN`
- `P6 Plan Completion = WARN`

这里反而有一个好消息：release gate 仍然 fail-closed，没有被 `OA/OM` 的局部绿灯误导去放行。真正失真的是 daily wrapper narration，而不是 final gate。

### Benchmark

- `26/26` 通过
- `pass_rate=1.0`
- suites:
  - `pr_gate_core=19/19`
  - `regression_watch=6/6`
  - `real_exam_quality_spine=1/1`

Benchmark 绿灯只能说明回归脊梁没炸，不能替代 surface 的 `Playwright + WeChat true-entry` readiness。

## Change Impact / Readiness

`change_impact.risk_level=medium`，`risk_score=0.55`，但受影响域并不轻：

- `turn=high`
- `capability=high`
- `surface=medium`
- `bi=medium`
- `learner_state=medium`

required gates：

- `turn`: `contract_guard` + `observer_snapshot` + `unified_ws_smoke`
- `capability`: `arr_lite` + `contract_guard` + `observer_snapshot` + `unified_ws_smoke`
- `surface`: `aae_snapshot` + `observer_snapshot` + `surface_smoke`

required readiness checks：

- `contract_guard`
- `playwright`
- `wechat_devtools`

当前 readiness matrix：

- `contract_guard=PASS`
- `launch_readiness=PASS`
- `playwright=FAIL`
- `wechat_devtools=FAIL`

plan completion 不是 blocker，但也没闭环：

- `scoped=2`
- `done=1`
- `partial=1`

## Control-Plane 语义风险

今天至少有两个 automation 级 authority 漂移，且都不是一次性噪声：

1. 最近 6 个 `daily_trends` run 都是 `verdict=TRUSTED`，同时 `metrics.release_gate_status=FAIL`
2. 当前 `observer_snapshot` 里的 `daily_trend` source 仍指向 prior wrapper `observability-daily-1783387326`，不是本轮 compliant run `observability-daily-1783387344`

第二点尤其值得注意：这次 prior-wrapper 引用和前几天不一样，它已经不是跨天旧 SHA，而是“同一早晨、同一 SHA、前一轮 wrapper”。这说明问题不只是历史残留，更像是 `observer_snapshot` 读 `latest daily_trend` 的绑定时机/来源设计本身有漂移。

因此 automation 仍然不能消费 `daily_trends.verdict` 作为最终结论，必须 direct-read：

- `release_gate_runs/latest.json`
- `observer_snapshots/latest.json`
- `readiness_checks/latest.json`

## P0 / P1 / P2

- `RELEASE-P0`: `release_gate.final_status=FAIL`，blockers 继续是 `runtime_release_dirty + playwright_evidence_missing + wechat_devtools_true_entry_pending`
- `AUTOMATION-P1`: `daily_trends.verdict=TRUSTED` 与 `release_gate.final_status=FAIL` 已连续至少 6 个 run，不能再当成偶发 wrapper 语义偏差
- `OBS-P1`: 3 个 canonical blind spots 已连续跨 5 个 OA/release run 持续存在
- `OBS-P2`: `langfuse_enabled=false`，所以 trace linkage 缺口不是单日流量问题，而是链路本身没打开
- `AUTOMATION-P2`: `artifacts/.env` 仍缺，当前 automation 依赖父仓 `.env`

## Blind Spots

- `surface_ack` 缺失，`P1 Trace Completeness` 只能停在 `WARN`
- `product_behavior` 窗口内无数据，无法证明真实产品行为被持久化
- `langfuse_trace_linkage` 缺失且 `langfuse_enabled=false`
- `daily wrapper verdict` 仍不是 final release truth

## 建议动作

1. 继续把总体 verdict 保持为 `DEGRADED`，不要接受 `daily_trends.verdict=TRUSTED` 的表层叙事。
2. 对外汇报时把“release gate fail-closed 仍正常工作”单列出来，避免团队误以为整个控制面已经失真到无法判断。
3. 把 `daily_trends -> release_gate` 语义对齐和 `observer_snapshot -> daily_trend` prior-wrapper 绑定，合并成一个 authority 修复项，而不是两个零碎补丁。
4. 不要再把 3 个 blind spots 写成“今天又发现”；直接标成 persistent debt，并按 `surface_ack / product_behavior / langfuse` 三条 owner 拆解。
5. 只有当 `playwright` 和 `wechat_devtools` 对当前 SHA 给出真入口证据后，benchmark 绿灯才有资格参与 release-ready 结论。

## 下一步最小 Prompt

`请只读审计 run_observability_daily / observer_snapshot / daily_trends / release_gate 的 authority 绑定，解释为什么同一窗口里 release_gate.final_status=FAIL 时 top-level daily_trends.verdict 仍是 TRUSTED，且 observer 仍引用 prior daily wrapper，并给出不改业务逻辑的最小 fail-closed 修复方案。`

## Run Artifacts

- log: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/automation-runs/deeptutor-observability-oa-om-report/20260707T092514+0800/run_observability_daily.log`
- report: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/automation-runs/deeptutor-observability-oa-om-report/20260707T092514+0800/report.md`
- runner output dir: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/tmp/observability/control_plane`
