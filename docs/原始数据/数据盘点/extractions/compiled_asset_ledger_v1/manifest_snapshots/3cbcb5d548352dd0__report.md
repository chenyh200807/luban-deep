# DeepTutor Observability OA/OM 日报

- report_date: `2026-07-05`
- generated_at: `2026-07-06 09:25:15 CST`
- verdict: `DEGRADED`
- authority: `PASS with caveat`
  - `pwd -L` = `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
  - `pwd -P` = `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
  - `git toplevel` = `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
  - `core.worktree` = empty
  - `artifacts/.env` = missing
  - `repo-root .env` = readable

## Execution Summary

从 `artifacts` cwd 执行父仓库脚本：

- command: `python3 /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/scripts/run_observability_daily.py --output-dir /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/tmp/observability/control_plane`
- runner warning: `Using the public default auth secret — set DEEPTUTOR_AUTH_SECRET`

日报窗口已按 `Asia/Shanghai` 冻结到昨天自然日：

- `report_date=2026-07-05`
- `start_ts=1783180800`
- `end_ts=1783267199`

同轮 control-plane run ids：

- `daily_trends=observability-daily-1783300992`
- `oa_runs=oa-daily-1783300992`
- `om_runs=om-1783300990`
- `observer_snapshots=observer-snapshot-1783300990`
- `change_impact_runs=change-impact-1783300992`
- `release_gate_runs=release-gate-1783300992`
- `benchmark_runs=benchmark-1783300990`
- `readiness_checks=readiness-matrix-1783300992`

本轮不是 freshness 问题，而是 authority 分层问题：

1. `daily_trends.payload.verdict=TRUSTED`
2. `oa.payload.verdict=TRUSTED`
3. `release_gate.payload.final_status=FAIL`

因此 automation 不能消费 top-level daily verdict 作为最终结论，整体 verdict 必须维持 `DEGRADED`。

## Tier 0 / Battlefield 状态

- branch: `release/card-fit`
- `HEAD=99a1d4111218b5b36f2b340d333014018d6803ad`
- `origin/main=1d0026a05dbded7591b0faf7415bef2f2a5a18da`
- 相对 `origin/main`: `ahead 1 / behind 122`
- dirty summary: `42 modified` + `1 deleted` + `14 untracked` = `57` 项
- dirty 主体仍是 `yousenwebview/packageDeeptutor/...` 与相关测试，加上 `.codegraph/.gitignore`、`docs/plan/...` 等非发布噪声

这意味着今天 release gate 的 FAIL 不是“环境没跑起来”，而是当前 battlefield 本身仍未达到 release-ready 边界。

## Freshness 表

| surface | latest run | age_hours | threshold | status |
| --- | --- | ---: | --- | --- |
| `daily_trends` | `observability-daily-1783300992` | `0.03h` | `36h` | `fresh` |
| `oa_runs` | `oa-daily-1783300992` | `0.03h` | `36h` | `fresh` |
| `om_runs` | `om-1783300990` | `0.03h` | `36h` | `fresh` |
| `observer_snapshots` | `observer-snapshot-1783300990` | `0.03h` | `36h` | `fresh` |
| `change_impact_runs` | `change-impact-1783300992` | `0.03h` | `36h` | `fresh` |
| `release_gate_runs` | `release-gate-1783300992` | `0.03h` | `7d` | `fresh` |
| `benchmark_runs` | `benchmark-1783300990` | `0.03h` | `7d` | `fresh` |
| `playwright readiness` | `playwright-1783298289` | `0.79h` | current-release reference | `fresh but FAIL` |
| `wechat_devtools readiness` | `wechat_devtools-1783298289` | `0.79h` | current-release reference | `fresh but FAIL` |
| `launch_readiness` | `launch-readiness-1783298643` | `0.69h` | current-release reference | `fresh and PASS` |

结论：今天所有关键 payload 都是新鲜的，所以任何红灯都应按真实红灯处理，不能归因给 store 老化。

## 昨日 Commit / Diff

`2026-07-05` 的提交面主要分三类：

1. capability/runtime：`99a1d4111 fix(deep-question): respect explicit practice count`
2. 课程/预览托管：`c4a775a41` 到 `1cda8b4d9` 一组 `luban-preview` 发布、重发布、字体与打包链路提交
3. 微信/学习前端：`e370a4ae4` 与 `bed5e8120` 到 `9289ac113` 一组 `learn/styles/stations` UI 行为提交

而当前未提交 diff 仍覆盖：

- `capability` 高风险域：`contracts/capability.md`、`deeptutor/capabilities/deep_question.py`、`deeptutor/runtime/orchestrator.py`
- `surface` 中风险域：大批 `yousenwebview/packageDeeptutor/...`
- `other` 低风险域：`deeptutor/services/question_followup.py`、tests、docs plan

所以这轮 `change_impact` 合理地把 `required_readiness_checks` 提升为：

- `contract_guard`
- `playwright`
- `wechat_devtools`

这点和上一轮只要求 `contract_guard` 的结论已经不同，不能沿用昨天的 scope。

## OA / OM / Observer / Release Gate

### OA

- `oa.verdict=TRUSTED`
- `turns_started=1`
- `turns_completed=1`
- `turns_failed=0`
- `provider_error_ratio=0.0`
- `unified_ws_smoke_ok=True`

但 OA 仍明确写出盲区：

- `missing_surface_coverage`
- `missing_product_behavior_evidence`
- `missing_langfuse_trace_linkage`

### OM

- `/metrics` provenance = `live_metrics_endpoint`
- endpoint = `http://127.0.0.1:8001/metrics`
- `status_code=200`
- `fallback_used=False`
- SLO:
  - `turn_success_ratio=1.0` `PASS`
  - `readyz_success_ratio=1.0` `PASS`
  - `turn_p95_latency_seconds_proxy=5.3038` `PASS`
  - `provider_error_ratio=0.0` `PASS`
  - `turn_first_render_ratio=None` `WARN`

结论：OM 证明本地运行面通，但它只证明 `127.0.0.1:8001` 当前可服务，不等于 release closure。

### Observer / Raw Evidence Layer

- `coverage_ratio=0.7273`，即 `8/11` 层有数据
- 已恢复：
  - `turn_event_log` `sample_count=3`
  - `recent_conversations` `sample_count=3`
  - `backend_logs` `sample_count=1000`
- 仍缺：
  - `surface_ack=0`
  - `product_behavior=0`
  - `langfuse_trace_linkage=0`

这是今天最重要的正向变化：observer 盲区已从上一轮 `4` 个降到 `3` 个，`turn_event_log` 不再缺失；但发布判断仍不能升格为 `TRUSTED`。

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

其中 `P0 Runtime` 的 evidence 已明确写入：

- `git_dirty=true`
- `required_readiness_checks=['contract_guard', 'playwright', 'wechat_devtools']`
- `readiness_required_failures=2`

所以今天 release gate 的真实失败原因已经从“只剩 dirty”升级为“dirty + 当前 scope 缺少 Playwright/微信真入口 readiness”。

### Benchmark

- `26/26` 通过
- `pass_rate=1.0`
- suites:
  - `pr_gate_core=19/19`
  - `regression_watch=6/6`
  - `real_exam_quality_spine=1/1`

质量门没有新增 regression，但它也不能抵消 P0 runtime 和 true-entry readiness 的缺口。

## Control-Plane 语义风险

今天有两个 automation 级 authority 漂移，必须继续上报：

1. `daily_trends.payload.verdict=TRUSTED`，但 `metrics.release_gate_status=FAIL`
2. `observer_snapshot.source_runs.daily_trend_run_id=observability-daily-1783298289`，仍指向前一轮 daily wrapper，而不是当前 `observability-daily-1783300992`

这说明：

- top-level daily verdict 仍不是 release-authoritative truth
- observer 和 daily 的 source binding 仍存在 prior-wrapper 漂移
- automation 必须继续 direct-read `release_gate_runs` 与 `observer_snapshots`，不能信 wrapper narration

## P0 / P1 / P2

- `RELEASE-P0` `final_status=FAIL`，blockers 已是 `runtime_release_dirty + playwright_evidence_missing + wechat_devtools_true_entry_pending`
- `OBS-P1` observer 仍有 3 个 canonical blind spots：`surface_ack`、`product_behavior`、`langfuse_trace_linkage`
- `AUTOMATION-P1` `daily_trends` 顶层 verdict 语义仍漂移，且 observer 继续引用 prior daily wrapper
- `SEC-P1` local env 仍在使用默认 `DEEPTUTOR_AUTH_SECRET`
- `AUTOMATION-P2` `artifacts/.env` 缺失；虽然父仓 `.env` 可读，当前 automation cwd 级环境契约仍不整齐

## Blind Spots

- `surface_ack` 缺失，P1 trace completeness 只能停在 `WARN`
- `product_behavior_events` 在窗口内无数据，控制面看不到真实产品行为
- `langfuse_trace_linkage` 缺失且 `langfuse_enabled=False`
- `daily_trends` 顶层 verdict 仍不是 final authority

## 建议动作

1. 继续把整体 verdict 维持为 `DEGRADED`，不要被 `daily_trends.verdict=TRUSTED` 误导。
2. 把当前 release blocker 按真实顺序写清：先是 battlefield dirty，再是 `playwright/wechat_devtools` true-entry readiness 缺失。
3. 不要把 observer blind spot 进展写成“已收敛完成”；今天只是 `4 -> 3`，不是闭环。
4. 优先审计 `daily_trends` 与 `observer_snapshot.source_runs.daily_trend_run_id` 的 authority 绑定，避免自动化继续读到 prior wrapper。
5. 在本地设置非默认 `DEEPTUTOR_AUTH_SECRET`，否则所有本地 release truth 都只能算工程侧弱证据。

## 下一步最小 Prompt

`请只读审计 daily_trends / observer_snapshot / release_gate 的 payload contract，解释为什么 release_gate.final_status=FAIL 时 top-level daily_trends.verdict 仍是 TRUSTED，且 observer 还在引用 prior daily wrapper，并给出不改业务逻辑的最小 authority 修复方案。`

## Run Artifacts

- log: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/automation-runs/deeptutor-observability-oa-om-report/20260706T092515+0800/run_observability_daily.log`
- report: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/automation-runs/deeptutor-observability-oa-om-report/20260706T092515+0800/report.md`
- runner output dir: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/tmp/observability/control_plane`
