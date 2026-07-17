# DeepTutor OA / OM / Observability 日报

- report_date: `2026-07-07`
- generated_at: `2026-07-08 09:23:49 Asia/Shanghai`
- automation_id: `deeptutor-observability-oa-om-report`
- overall_verdict: `STALE`
- daily_run_id: `observability-daily-1783473829`
- release_gate_run_id: `release-gate-1783473829`
- observer_run_id: `observer-snapshot-1783473826`
- oa_run_id: `oa-daily-1783473829`
- om_run_id: `om-1783473826`
- benchmark_run_id: `benchmark-1783473826`
- readiness_run_id: `readiness-matrix-1783473829`

## 0. Tier 0 authority

- `pwd -L` / `pwd -P`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- `git toplevel`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- `core.worktree`: empty
- branch: `release/old-blue-frontend`
- HEAD: `5373b518a7944a9efdbb6f834ce45e44d8145e07`
- `origin/main`: `c7f57b74bbd4afdae413809e773551db2933e34f`
- `origin/main...HEAD`: `142 8`
- `origin/release/old-blue-frontend...HEAD`: `3 0`
- `.env`: `artifacts/.env` missing, repo-root `.env` readable

结论：automation cwd 合规，不是 BLOCKED；但 battlefield branch 既脏又显著落后 `origin/main`，且当前 daily spine 读到的 live runtime 不是 HEAD 同 SHA，导致 verdict 只能是 `STALE`。

## 1. 昨天发生了什么

2026-07-07 的提交主题集中在两条线：

1. `billing / wechat pay / old-blue frontend`
   `26440c8d9`、`5c5cadf8a`、`5373b518a`、`fde0928b6`、`f0b370ade`、`587ce87f1`
2. `学习双轮 / retest / login / free course details`
   `4d8d12aaa`、`88ff35fbb`、`f1ecb6a25`、`42681ace6`、`fc0b17cf3`

当前工作区不是“只有这些已提交改动”。`git status` 仍有 `29 modified / 1 deleted / 17 untracked`，覆盖：

- `turn/capability`：`deeptutor/api/routers/mobile.py`
- `member/wallet/auth`：`deeptutor/services/member_console/*`、`wallet/service.py`、`wechat_pay.py`
- `wx/yousen surface`：billing / login / profile 多文件
- `docs/plan/assets/scripts/tests`：母题资产、计划文档、脚本和测试一起在动

这意味着 release gate 失败不是“观测太保守”，而是当前 scope 本身就没有收口。

## 2. Freshness 表

| 面向 | run_id | 状态 | 结论 |
| --- | --- | --- | --- |
| daily_trends | `observability-daily-1783473829` | fresh wrapper / `verdict=STALE` | 顶层语义已不再伪装 `TRUSTED`，但整体因 stale input 降级 |
| release_gate | `release-gate-1783473829` | fresh wrapper / `final_status=FAIL` | blocker 新增 `artifact_release_stale_vs_head` |
| observer_snapshot | `observer-snapshot-1783473826` | fresh wrapper / stale dependency | 仍绑定前一日 `daily_trend_run_id=observability-daily-1783387344` |
| change_impact | `change-impact-1783473829` | fresh | 仍要求 `contract_guard + playwright + wechat_devtools` |
| OA | `oa-daily-1783473829` | fresh wrapper / `verdict=STALE` | 业务健康表面正常，但依赖 stale OM lineage |
| OM | `om-1783473826` | fresh wrapper / stale release lineage | live `/metrics` 读到的 release 是 `4d8d12aaa876`，不是 HEAD `5373b518a794` |
| benchmark | `benchmark-1783473826` | fresh | `26/26` pass，不能覆盖 release lineage/true-entry 缺口 |
| readiness | `readiness-matrix-1783473829` | fresh / `FAIL` | 4 个 required checks 里 3 个非 PASS |

## 3. OA / OM / release 证据

### OA

- `ready=True`
- `unified_ws_smoke_ok=True`
- `turns_started_total=1`
- `turns_completed_total=1`
- `orphaned_turns=0`
- 唯一顶层 blocker 不是业务报错，而是 `artifact_release_stale_vs_head`

解释：OA 没有看到 turn runtime 崩坏；它失败在“这份 OA 是否还能代表当前 battlefield HEAD”。

### OM

- metrics provenance: `live_metrics_endpoint`, `http://127.0.0.1:8001/metrics`, `status_code=200`, `fallback_used=false`
- 但 metrics release: `1.0.0+4d8d12aaa876+local`
- battlefield HEAD release: `1.0.0+5373b518a794+local`
- `turn_avg_latency_ms=15151.27`
- `turn_p95_latency_seconds_proxy=15.1513` vs target `6.0` => `WARN`
- `om_slo_compliance=0.6`

关键真相：control plane 现在能稳定读到 live `/metrics`，但读到的是另一条本地 runtime lineage。按 `git log`，`4d8d12aaa` 对应 `spike/main-base-v2`，不是本次 branch HEAD。这不是“数据老一点”，而是“authority 指错进程”。

### Release Gate

`final_status=FAIL`，blockers 为：

1. `runtime_release_dirty`
2. `contract_guard_failed`
3. `playwright_evidence_missing`
4. `wechat_devtools_true_entry_pending`
5. `artifact_release_stale_vs_head`

其中第 5 条是今天最值得重视的新硬伤：即便 benchmark、WS smoke、launch readiness 都过了，release truth 仍然指向别的 SHA，本日报不能给出可信 GO。

## 4. Observer / blind spots

observer coverage 仍是 `8 / 11 = 0.7273`，三个 canonical blind spots 没变：

1. `missing_surface_coverage`
2. `missing_product_behavior_evidence`
3. `missing_langfuse_trace_linkage`

但今天有一个容易忽略的裂缝：

- OM live metrics 里 `surface_events.event_counts` 明明已有 `13` 条 `wechat_yousenwebview accepted` 事件
- observer `product_behavior.db` 在同一 frozen window 里仍是 `event_count=0`
- `surface_events.coverage=[]`
- recent events metadata 里的 `release_id/app_version/platform` 仍为空

这说明不是“昨天没人用”。更可能是 surface telemetry 进了 metrics 侧计数，但没有形成 observer 想要的 surface_ack / product_behavior authority 证据，所以 blind spot 不是单纯静默，而是链路分叉。

另一个 persistence debt 仍在：

- `observer.source_runs.daily_trend_run_id=observability-daily-1783387344`
- 当前 daily run 是 `observability-daily-1783473829`

也就是 observer 仍然吃到 prior-wrapper daily trend，而不是本次 run-local daily payload。

## 5. Readiness 与 contract

`change_impact.required_readiness_checks` 仍是：

- `contract_guard`
- `playwright`
- `wechat_devtools`

对应 `readiness-matrix` 的 3 个 required failures：

1. `contract_guard_failed`
   `deeptutor/api/routers/mobile.py` 改动触发 `turn` 与 `capability` contract-sensitive guard，但没有同步更新对应 contract surface
2. `playwright_evidence_missing`
3. `wechat_devtools_true_entry_pending`

这里不要被 fallback wording 误导。当前 dirty scope 明确包含 `mobile.py`、`wx_miniprogram/*`、`yousenwebview/*`，所以 Playwright / WeChat DevTools 不是可选加分项，而是 change-impact authority 要求的必需项。

## 6. P0 / P1 / P2

### P0

- `artifact_release_stale_vs_head`: live runtime SHA=`4d8d12aaa876` 与 battlefield HEAD=`5373b518a794` 不一致
- `contract_guard_failed`: `mobile.py` 触碰 turn/capability sensitive boundary 但 contract surface 未更新

### P1

- `playwright_evidence_missing`
- `wechat_devtools_true_entry_pending`
- observer 仍绑定 prior-wrapper `daily_trend_run_id`

### P2

- blind spots 仍为 `surface_ack / product_behavior / langfuse_trace_linkage`
- `artifacts/.env` 仍缺失，当前依赖 repo-root `.env` fallback
- OM latency 代理项偏高：`15.15s`，SLO compliance 仅 `0.6`

## 7. 建议动作

1. 先核对并收口 `127.0.0.1:8001` 这条 live runtime 的启动目录、git SHA、deploy manifest；在同 SHA 下重跑 `OM -> OA -> observer -> release gate`，否则任何“今天 fresh”都只是 fresh to the wrong process。
2. 处理 `mobile.py` 的 contract-sensitive 改动：要么补 `contracts/turn.md` / `contracts/capability.md` 等 surface，要么把实际语义改动从 protected boundary 收回；否则 release gate 会持续 fail-closed。
3. 补当前 release 的 Playwright readiness；不要拿旧 run 或 web shadow 代替。
4. 补当前 release 的 WeChat DevTools true-entry 证据，明确 `devtools_project_root=yousenwebview`、`target_subpackage=packageDeeptutor`、`target_page`、`auth_state`。
5. 单独排查 surface telemetry 双轨：为什么 OM metrics 已有 accepted events，但 observer `surface_ack/product_behavior` 仍为 0，尤其检查 metadata 里的 `release_id/app_version/platform` 为空是否让 observer 无法归窗/归版。

## 8. 最小下一步 prompt

```text
先只做 observability authority 收口：核对 127.0.0.1:8001 当前 runtime 的 git SHA / 启动目录 / deploy manifest，确保它与 battlefield HEAD 5373b518a794 一致；一致后重跑 OM、observer、OA、release gate，并解释为什么 surface_events 已有 accepted 事件但 observer 的 product_behavior 和 surface_ack 仍为 0。不要部署，不要 SSH，不要改生产数据。
```
