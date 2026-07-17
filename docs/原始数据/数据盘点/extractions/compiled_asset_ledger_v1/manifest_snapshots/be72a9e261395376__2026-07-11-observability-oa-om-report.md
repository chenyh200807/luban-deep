# DeepTutor OA / OM / Observability 日报（2026-07-11）

- 生成时间：2026-07-12 09:22-09:25 Asia/Shanghai
- 冻结窗口：2026-07-11 00:00:00-23:59:59 Asia/Shanghai（`start_ts=1783699200`, `end_ts=1783785599`）
- 总 verdict：**BLOCKED**
- control-plane payload verdict：**STALE**
- release gate：**FAIL / hold**

## 1. 结论先行

本轮不是“观测数据过期”，而是“启动硬门失败 + 新鲜证据仍指向错误 lineage”。所有核心 control-plane payload 都在 2026-07-12 09:22 新生成，但 artifacts cwd 下 `.env` 不可读，按 automation Tier 0 总 verdict 必须为 `BLOCKED`。即使暂时忽略该硬门，日报、OA 与 release gate 仍明确给出 `STALE`：当前源码 HEAD 为 `e24f00842105`，OM/live metrics 却来自 `7297c9081755`，不能作为 same-SHA release truth。

Release gate 正确 fail-closed：`final_status=FAIL`，blockers 为 `runtime_release_dirty`、`playwright_evidence_missing`、`wechat_devtools_true_entry_pending`、`artifact_release_stale_vs_head`。Benchmark 26/26 PASS 与 unified `/api/v1/ws` synthetic smoke PASS 只证明对应窄面，不清除发布阻塞。

## 2. Tier 0 / authority

| 项目 | 证据 | 判定 |
|---|---|---|
| `pwd -L` / `pwd -P` | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts` | PASS |
| git toplevel | `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor` | PASS |
| `core.worktree` | 空 | PASS |
| branch | `codex/old-blue-workspace-snapshot-20260710` | 风险信号 |
| HEAD | `e24f008421055e95c5c2d9a2c695316d24665f8e` | 当前执行 authority |
| `origin/main` | `245cbd98cf880b26835cb3c6777308b48ba1dce5` | 与当前分支分叉 |
| divergence | HEAD 独有 61，`origin/main` 独有 221 | release truth 不可外推到 main |
| `.env` | artifacts cwd 下不可读 | **Tier 0 BLOCKED** |
| dirty state | 4 modified + 14 untracked | `runtime_release_dirty` |

Dirty files 分组：治理/计划文档（`AGENTS.md`、`docs/plan/INDEX.md`、implementation notes 与新增计划）、真实入口本地配置（`yousenwebview/project.private.config.json`）、brainstorm 临时目录、知识图谱 pilot 脚本/抽取物/测试。全部视为用户/并行工作，本轮未 reset、stash、checkout 或覆盖。

## 3. Freshness

| 控制面 | 本轮 run | 生成时间 | 年龄 | 阈值 | 判定 |
|---|---|---:|---:|---:|---|
| daily_trends | `observability-daily-1783819366` | 09:22:46 | <1m | 36h | FRESH |
| oa_runs | `oa-daily-1783819366` | 09:22:46 | <1m | 36h | FRESH |
| om_runs | `om-1783819363` | 09:22:43 | <1m | 36h | FRESH-BY-AGE / STALE-BY-LINEAGE |
| observer_snapshots | `observer-snapshot-1783819363` | 09:22:43 | <1m | 36h | FRESH-BY-AGE / coverage 6/11 |
| change_impact_runs | `change-impact-1783819366` | 09:22:46 | <1m | 36h | FRESH |
| release_gate_runs | `release-gate-1783819366` | 09:22:46 | <1m | 7d | FRESH-BY-AGE / FAIL |
| benchmark_runs | `benchmark-1783819363` | 09:22:43 | <1m | 7d | FRESH / 26 of 26 PASS |
| readiness_checks | `contract_guard/playwright/wechat_devtools-1783819366` | 09:22:46 | <1m | current release | 1 PASS / 2 FAIL |

Freshness 年龄全部合格；因此本轮不能把 `STALE` 归因为“没重跑”。真正问题是 same-SHA lineage、缺失 true-entry readiness 与持久观测断点。

## 4. 昨日 commit / diff

当前分支在冻结日仅 1 个 commit：`a600236051e6`（`fix(billing): unify direct payment contract`），修改 contract 双拷贝与 `yousenwebview` billing tests。`origin/main` 在同一自然日有 33 个 commit，包含 first-run/微信 surface、session/route/runtime、LLM tier、观测埋点、security baseline 等发布相关变化。当前分支落后 `origin/main` 221 个 commit，因此当前本地日报不能替代 main 或线上 same-SHA 验收。

当前未提交 diff 为 4 个 tracked 文件，`28 insertions / 5 deletions`，另有 14 个 untracked 路径；change impact 因 `yousenwebview/project.private.config.json` 判定 `surface` medium risk，并要求 `contract_guard`、`playwright`、`wechat_devtools`。

## 5. OA / OM / benchmark / release gate

### OA

- `oa-daily-1783819366` verdict=`STALE`，`stale_inputs=[om]`，blocker=`artifact_release_stale_vs_head`。
- OA 能链接 observer、change impact、OM、ARR、AAE、benchmark 的 run id，但 `root_causes=[]`，只有 1 个 pending causal candidate；当前只够形成“blind spot 候选”，不能下业务根因结论。
- raw evidence 有 run-id linkage；但 chat history 0 session/0 turn、turn event file 不存在、Langfuse disabled 且 trace_id=0，所以 raw logs/chat_history/trace linkage 不完整。

### OM

- live metrics provenance：`http://127.0.0.1:8001/metrics`，HTTP 200，`fallback_used=false`。
- runtime release=`7297c9081755`，与 HEAD=`e24f00842105` 不同；这是 live endpoint 成功但 release authority 失败。
- 2 turns started/completed、0 failed/cancelled、synthetic unified WS smoke terminal=`done`。
- 平均 turn latency `6057.63ms`，超过 `6000ms` proxy target，SLO 为 WARN；主要阶段为 context build `4581.81ms` 与 capability stream `1377.63ms`。SLO compliance=`0.6`，first-render ratio 缺失。
- provider error ratio=0，但 providers usage/error 细目为空；不能据此推导真实生产 usage 健康。

### Surface split

- OM/live metrics 看到 14 条 accepted `wechat_yousenwebview` 事件：8 `first_run_started`、5 `retest_item_answered`、1 `learning_action_completed`。
- 这些 recent events 的 `release_id` 与 `app_version` 全为空；observer 的 `surface_ack` 仍为 0，product behavior 仍为 0。
- 这证明 sidecar 接收计数存在，但未形成可按 release lineage 归属的 readiness / observer evidence；不能当作真实微信闭环。

### Benchmark

- `pr_gate_core` 19/19、`regression_watch` 6/6、`real_exam_quality_spine` 1/1，总计 26/26 PASS。
- P2 benchmark gate PASS；但 baseline diff 为 null，且这套 evidence 不覆盖 live runtime SHA、Playwright、微信 DevTools、Langfuse 或真实用户行为。

### Release gate / readiness

- `final_status=FAIL`，recommendation=`hold`，payload 直接读取而非只看 `latest.json` wrapper。
- P0 FAIL：dirty runtime + Playwright missing + WeChat DevTools true entry pending。
- P1 WARN：surface ack coverage=0。
- P2/P3 PASS：benchmark 与 AAE proxy 通过。
- P4/P5/P6 WARN：5 个 blind spots、medium change impact、计划 scope partial。
- readiness：contract guard PASS；Playwright FAIL；WeChat DevTools FAIL。两项 FAIL 都是“current-release evidence missing”，不是已执行真实入口后发现产品失败。

## 6. P0 / P1 / P2

### P0

- `TIER0-P0 artifacts_env_unreadable`：本轮 automation contract 要求 `.env` 可读，实际未满足，总 verdict=`BLOCKED`。
- `RELEASE-P0 same_sha_release_truth_missing`：HEAD `e24f00842105` 与 live OM `7297c9081755` 不一致；该 failure signature 已连续远超 3 次。
- `RELEASE-P0 fail_closed_dirty_true_entry`：release gate FAIL，dirty + Playwright/DevTools evidence 缺失 + artifact lineage stale。

### P1

- `AUTOMATION-P1 observer_dailytrend_prior_wrapper_persists`：observer 本轮仍绑定前一轮 `observability-daily-1783816923`，而非当前 `1783819366`；连续多次出现，说明 persistence/source binding 仍有 authority debt。
- `OBS-P1 observer_blind_spots_5_layers`：连续多轮 coverage 6/11；缺 turn event log、surface ack、recent conversations、product behavior、Langfuse linkage。
- `AUTOMATION-P1 surface_metrics_vs_observer_split`：14 条 accepted surface events 未进入 observer/product behavior，且 release metadata 为空。
- `OBS-P1 turn_latency_proxy_warn`：平均 `6057.63ms` 略高于 6s 阈值，当前样本仅 2 个且是 synthetic smoke，需避免过度外推。

### P2

- `AUTOMATION-P2 runner_capture_wrapper_error`：runner 成功生成 artifacts 后，外层 zsh 采集命令因使用只读变量名 `status` 报错；不影响本轮 payload，但应修 automation shell wrapper，避免未来把成功误记为失败。
- `OBS-P2 usage_detail_missing`：OM provider usage/error 明细为空，无法回答成本/模型用量变化。

## 7. 观测盲区与不能下的结论

1. turn event 文件 `turn_events_2026-07-11.jsonl` 不存在，append success/failure 均为 0；无法计算 canonical turn error ratio。
2. chat history 冻结窗内 0 sessions/turns；无法判断真实对话质量与失败分布。
3. product behavior 0 events，但 metrics sidecar 有 14 条 surface events；写入/读取 authority 未对齐。
4. Langfuse disabled、trace_id=0；OA 无法闭合 log → chat → trace。
5. observer daily trend 持续读取前一轮 wrapper，`consecutive_count`/persistence continuity 的 lineage 仍不可信。
6. Web harness、synthetic unified WS、Playwright、微信 DevTools、真实微信包、Aliyun public endpoint 是不同证据层；本轮仅执行 synthetic unified WS，不能声称 Web/微信/公网上线通过。

## 8. 建议动作（按最小闭环排序）

1. Owner=automation/runtime：恢复 artifacts `.env` 可读性或把父级 env fallback 明确升级为受治理 contract；pass criteria=Tier 0 可机械 PASS，且不泄露 secret。
2. Owner=runtime/release：停掉或明确标记 `127.0.0.1:8001` 的旧 SHA runtime，在同一 HEAD/deploy manifest 上重跑 daily；pass criteria=HEAD、OM、OA、release gate、benchmark 的 `git_sha/deploy_manifest_hash` 一致。
3. Owner=observability：修复 observer 对 prior daily wrapper 的回读和持久计数 lineage；pass criteria=observer `daily_trend_run_id` 指向本轮 authority，连续计数跨 run 延续且不被 SHA 切换误清零。
4. Owner=surface telemetry：让 accepted surface event 写入 canonical product behavior/surface ack，并强制携带 release_id/app_version；pass criteria=同一事件可从 metrics → observer → release lineage join。
5. Owner=release QA：仅在 same-SHA 与 Tier 0 恢复后，按 `required_readiness_checks` 补 Playwright 和 `real_wechat_package` DevTools evidence；pass criteria=两项 readiness current-release PASS，且不把 harness 当真入口。

## 9. 下一步最小 prompt

> 只读定位 `observer-snapshot` 为何总绑定上一轮 `daily_trend_run_id`，以及 accepted `wechat_yousenwebview` surface events 为何未进入 canonical `surface_ack/product_behavior`。请给出唯一 writer/store/reader、跨 run lineage 断点、连续计数 persistence 断点与最小修复方案；不要改代码、不要启动浏览器、不要部署。

## 10. Run artifacts

- runner log：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts/automation-runs/deeptutor-observability-oa-om-report/2026-07-11/runner.log`
- daily payload：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/data/runtime/observability/control_plane/daily_trends/observability-daily-1783819366.json`
- OA payload：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/data/runtime/observability/control_plane/oa_runs/oa-daily-1783819366.json`
- OM payload：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/data/runtime/observability/control_plane/om_runs/om-1783819363.json`
- observer payload：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/data/runtime/observability/control_plane/observer_snapshots/observer-snapshot-1783819363.json`
- release gate payload：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/data/runtime/observability/control_plane/release_gate_runs/release-gate-1783819366.json`
