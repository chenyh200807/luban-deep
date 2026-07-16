# DeepTutor OA/OM/Observability 日报

- 生成时间：2026-07-11 09:25 +08
- 冻结窗口：2026-07-10 00:00:00 至 2026-07-10 23:59:59（Asia/Shanghai）
- Verdict：`STALE`

## 1. Tier 0 与执行面

- `pwd -L` / `pwd -P`：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- `git toplevel`：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- `core.worktree`：空，符合 artifacts-cwd guardrail
- `branch`：`codex/old-blue-workspace-snapshot-20260710`
- `HEAD`：`0887f1b172d724dda29529731242e113851cd3a8`
- `origin/main`：`918cf4aa0ad4cdeb42fea747407733d0dcbfb423`
- `origin/main...HEAD`：左 176 / 右 59，说明当前分支与 `origin/main` 明显分叉
- `artifacts/.env`：`missing`

当前工作区 dirty：

- 已修改：`docs/plan/INDEX.md`、`yousenwebview/project.private.config.json`
- 未跟踪：3 份 `docs/plan/知识编译与检索/*`、`docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/`、`docs/原始数据/数据盘点/scripts/run_learning_graph_pilot_ab.py`、`tests/scripts/test_learning_graph_pilot_ab.py`

结论：Tier 0 通过，但运行面本身仍是 dirty local release，不能当发布真相。

## 2. 总结论

今天的控制面工件是新鲜的，但结论仍然是 `STALE`，不是因为“没跑”，而是因为“跑出来的 lineage 仍不可信”：

1. `daily / OA / benchmark / release_gate / readiness` 都绑定到当前工作区 `HEAD=0887f1b172d7`，但 `OM/live metrics` 仍绑定到另一份本地 runtime `8ee9f38a0b92`，所以 release gate 继续报 `artifact_release_stale_vs_head`。
2. release gate 仍然 fail-closed：`runtime_release_dirty`、`playwright_evidence_missing`、`wechat_devtools_true_entry_pending` 没有关闭。
3. observer 只有 `6/11` 层有数据；`turn_event_log`、`surface_ack`、`recent_conversations`、`product_behavior`、`langfuse_trace_linkage` 五层继续缺失。也就是说，入口层有活动，不代表观测链真正闭环。

## 3. Freshness 表

| 面 | run_id | 生成时间 | 新鲜度 | 结论 |
| --- | --- | --- | --- | --- |
| daily_trends | `observability-daily-1783732971` | 2026-07-11 09:22:51 | 新鲜 | 时间新鲜，但 verdict=`STALE` |
| oa_runs | `oa-daily-1783732971` | 2026-07-11 09:22:51 | 新鲜 | 只把 `om` 标成 stale input |
| om_runs | `om-1783732969` | 2026-07-11 09:22:49 | 新鲜 | 但 runtime SHA=`8ee9f38a0b92`，不是当前 HEAD |
| observer_snapshots | `observer-snapshot-1783732969` | 2026-07-11 09:22:49 | 新鲜 | 但 `daily_trend_run_id` 仍回绑上一轮 `observability-daily-1783731374` |
| change_impact_runs | `change-impact-1783732971` | 2026-07-11 09:22:51 | 新鲜 | `risk_level=medium`，要求 surface 验证 |
| release_gate_runs | `release-gate-1783732971` | 2026-07-11 09:22:51 | 新鲜 | `final_status=FAIL`，推荐 `hold` |
| benchmark_runs | `benchmark-1783732969` | 2026-07-11 09:22:49 | 新鲜 | `26/26` 通过，但不抵消 release blocker |
| readiness_checks | `readiness-matrix-1783732971` | 2026-07-11 09:22:51 | 新鲜 | 3 个 required checks 中 2 个失败 |

结论：这不是 freshness gap，而是 release lineage 与 true-entry evidence gap。

## 4. 昨日 commit impact

2026-07-10 的提交主线明确集中在微信真入口和首体验：

- `0887f1b1`：first-run review 修复 + Polyv 服务端签名接口
- `6e84a2c2`：freeCourse 播放签名策略回调
- `16e80174`：`yousenwebview/packageDeeptutor` 真入口 first-run 接线
- `dcc78bf6` / `41bbded2` / `42206f11`：老蓝版与首体验脚本/视觉/埋点连续迭代

`change_impact` 也给出同样判断：

- `changed_domains.surface` = `medium`
- 受影响文件 21 个，其中 10 个直接落在 `wx_miniprogram` / `yousenwebview/packageDeeptutor`
- required readiness checks 仍是 `contract_guard`、`playwright`、`wechat_devtools`

因此今天缺失 Playwright / 微信 DevTools 不是“文档不全”，而是与昨天改动面直接相关的 release blocker。

## 5. OA / OM / Observer / Release Gate 证据

### OA / OM

- OA verdict=`STALE`
- OA health summary 只有 3 个 turn，`turn_success_ratio=1.0`，`unified_ws_smoke_ok=true`
- OA 唯一 blocker：`artifact_release_stale_vs_head`
- OM 也只看到 3 个 turn，且 smoke 是打到 `http://127.0.0.1:8001`
- OM SLO 只有 `0.6` 合规：`turn_first_render_ratio=null`，`turn_p95_latency_seconds_proxy=7.1776 > 6.0`

关键不是 turn 成功，而是 OM 绑定的 release 仍是：

- OM/live metrics SHA：`8ee9f38a0b92`
- 当前 daily/OA/release/benchmark SHA：`0887f1b172d7`

这说明本地 `127.0.0.1:8001` 跑的不是当前工作区这份 runtime。

### Surface split

OM 的 live metrics 明确看到了微信入口事件：

- `wechat_yousenwebview` accepted events 共 9 个
- `retest_item_answered=6`
- `learning_action_started=1`
- `learning_action_completed=1`
- `module_viewed=1`

但这些事件没有进入后续权威层：

- `surface_ack`：0
- `product_behavior.event_count`：0
- `recent_conversations.session_count`：0
- `turn_event_log.file_exists`：`false`
- recent surface event metadata 里的 `release_id` / `app_version` 仍为空字符串

结论：入口层有 activity，不等于 observer 真正收到了 canonical closure。

### Observer

- coverage：`6 / 11 = 0.5455`
- 缺失层：
  - `turn_event_log`
  - `surface_ack`
  - `recent_conversations`
  - `product_behavior`
  - `langfuse_trace_linkage`

额外值得单列的是 source binding：

- `observer.source_runs.om_run_id = om-1783732969`：当前轮
- `observer.source_runs.daily_trend_run_id = observability-daily-1783731374`：上一轮 wrapper，不是本轮 `1783732971`

这说明 observer 仍然存在“本轮 rerun 了，但 source_runs 没全跟上”的 authority smell。

### Benchmark / Release Gate / Readiness

- benchmark：`26/26 PASS`，`pr_gate_core / regression_watch / real_exam_quality_spine` 全绿
- release gate：`verdict=STALE`、`final_status=FAIL`、`recommendation=hold`
- gate 结果：
  - `P0 Runtime = FAIL`
  - `P1 Trace Completeness = WARN`
  - `P2 Benchmark Regression = PASS`
  - `P3 AAE = PASS`
  - `P4 Blind Spot Budget = WARN`
  - `P5 Change Impact = WARN`
  - `P6 Plan Completion = WARN`

readiness matrix：

- `contract_guard = PASS`
- `playwright = FAIL`
- `wechat_devtools = FAIL`

也就是：质量脊梁没坏，但 true-entry readiness 仍没闭环，所以发布判断不能放行。

## 6. P0 / P1 / P2

### P0

- `runtime_release_dirty`
- `artifact_release_stale_vs_head`
- `playwright_evidence_missing`
- `wechat_devtools_true_entry_pending`

### P1

- `turn_event_log` 缺失，昨天窗口没有 canonical turn event 文件
- `surface_ack` 缺失，accepted surface events 没进入 observer ack 层
- `recent_conversations` 缺失，chat history 对冻结窗口给出 0
- `product_behavior` 缺失，行为库对冻结窗口给出 0
- `langfuse_trace_linkage` 缺失，`trace_id_count=0` 且 Langfuse disabled
- observer `daily_trend_run_id` 仍绑定上一轮 wrapper

### P2

- `turn_p95_latency_seconds_proxy=7.1776s`
- `turn_first_render_ratio=null`
- `artifacts/.env` 缺失，虽然本轮仍跑通，但 automation env contract 仍不干净

## 7. 盲区与不能下的结论

今天不能下的结论：

- 不能说“release ready”，因为 Playwright / 微信 DevTools 都没给当前 release 的真入口证据
- 不能说“OM 代表当前 HEAD”，因为 live metrics 仍绑旧 runtime SHA
- 不能说“微信入口 telemetry 已闭环”，因为 accepted events 没落到 `surface_ack/product_behavior/recent_conversations/turn_event_log`
- 不能把本轮本地 `127.0.0.1:8001` metrics 当公网/容器 truth；今天没有新的 public endpoint 或 DevTools true-entry evidence

## 8. 建议动作（最小且有用）

1. 先处理 `127.0.0.1:8001` runtime lineage：要么把本地 runtime 对齐到 `0887f1b172d7`，要么停止把这份 metrics 当 release truth。
2. 对当前 `first-run / yousenwebview` 改动面补当天 `Playwright` 与 `微信 DevTools CLI` readiness evidence，否则 release gate 没法从 `FAIL` 变成可讨论状态。
3. 排查 observer 为什么仍把 `daily_trend_run_id` 绑到上一轮 wrapper，而不是当前 `observability-daily-1783732971`。
4. 排查 `turn_event_log`、`recent_conversations`、`surface_ack`、`product_behavior` 四层为什么同时空洞，尤其是已有 9 个 accepted surface events 的前提下。
5. 明确 `artifacts/.env` 缺失是不是允许的长期 contract；如果允许，要把“父仓 `.env` fallback”写成显式规则，不要继续靠隐式成功。

## 9. 下一步最小 prompt

`请先只做 read-only root-cause audit：为什么 observer 仍复用上一轮 daily_trend wrapper，且 accepted wechat_yousenwebview events 没进入 surface_ack / product_behavior / recent_conversations / turn_event_log。不要修代码，先给 single-authority 断点图。`
