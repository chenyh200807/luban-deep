# DeepTutor OA / OM / Observability 日报

- report_date：2026-07-15（Asia/Shanghai）
- frozen window：1784044800..1784131199
- run_at：2026-07-16 13:23-13:33 +08:00
- Observability verdict：**BLOCKED**
- release verdict：**RELEASE-P0 / HOLD**

## 一句话结论

今天没有 current-candidate release truth。live http://127.0.0.1:8001/metrics 拒绝连接，无法证明 runtime 的 git_sha、ff_snapshot_hash、deploy_manifest_hash 与 candidate 8ca6a804dde2 一致；当前 checkout 的 daily runner 还存在“先 WS smoke、后 metrics”的执行顺序，且本地无 token 时会尝试铸造 student_demo token，违反本任务的 authority 硬规则，因此 runner 未被调用，WS/online ARR/online benchmark 全部保持 DEFERRED。历史 control plane 已整体 stale：daily/OA/observer/change-impact/OM 均超过 36h，最新 release gate 仍 FAIL/hold 且不在当前 candidate 的祖先链上。

## Tier 0 authority

| 检查 | 结果 | 证据 |
|---|---|---|
| pwd -L / pwd -P | PASS | 均为 /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts |
| git toplevel | PASS | /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor |
| core.worktree | PASS | 空 |
| 配置 authority | PASS | 父仓 .env 可读；artifacts/.env 不存在 |
| branch / HEAD | WARN | main / 8ca6a804dde2c8a4d9ccfd96a061945adf359c7a |
| origin/main | WARN | 93fe95895c7c407d7c57107b3e6e3f023ab266c1；HEAD...origin/main = 3 left / 5 right |
| candidate identity | BLOCKED | git_sha=8ca6a804dde2，ff_snapshot_hash=a638f39bf909，deploy_manifest_hash=local-24a4e1fe350c，git_dirty=true |
| CODEX_HOME | INFO | 空；automation memory 使用 /Users/yehongchen/.codex/automations |

## Runtime authority 与 runner

- strict preflight：GET http://127.0.0.1:8001/metrics → httpx.ConnectError: [Errno 61] Connection refused。
- provenance：source=live_metrics_endpoint，fallback_used=false；未使用 TestClient、metrics_json 或字段覆盖。
- runtime identity：未取得，status=BLOCKED。
- runner_invoked=false，runner_exit_code=NOT_RUN。
- 原因：当前 runner 的 _ensure_om_payload 先调用 unified_ws_smoke，随后才读取 metrics；其 local token resolver 仍可铸造 student_demo token。本任务明确要求先过 live identity 且只允许显式合规 eval token，因此不能冒险执行。
- online boundary：unified_ws_smoke=DEFERRED；online ARR=DEFERRED；online benchmark=DEFERRED；current OA/release/readiness assembly=STOPPED。
- 没有启动/停止任何进程，没有浏览器、Computer Use、部署、SSH 或生产写入。

## Freshness 与 lineage

审计时刻约 2026-07-16 13:29 +08:00。

| store | latest run | age | lineage | 判定 |
|---|---|---:|---|---|
| daily_trends | observability-daily-1783905684 | 76.13h | 87599ea5a0cc；窗口仍为 2026-07-12 | **OBS-P1 / stale** |
| oa_runs | oa-daily-1783905684 | 76.13h | 87599ea5a0cc | **OBS-P1 / stale** |
| observer_snapshots | observer-snapshot-1783905682 | 76.14h | 87599ea5a0cc | **OBS-P1 / stale** |
| change_impact_runs | change-impact-1783905684 | 76.13h | 87599ea5a0cc | **OBS-P1 / stale** |
| om_runs | om-1783992205 | 52.10h | foreign dirty runtime 954c830c7bc5 | **OBS-P1 / foreign-lineage** |
| readiness_checks | contract/playwright/wechat rows | 76.13h | 87599ea5a0cc | stale by age/lineage；不覆盖当前 Web/微信改动 |
| release_gate_runs | release-gate-1783905684 | 76.13h | 87599ea5a0cc，且不是 HEAD 祖先 | 未超 7d，但 release 相关提交后未更新，**RELEASE-P0** |
| benchmark_runs | benchmark-1783905682 | 76.14h | 87599ea5a0cc | 未超 7d；仅旧 artifact 证据，不是 candidate truth |

## 昨日 commit / diff

2026-07-15 自然日共有 9 个 commit：5 个实质提交、4 个 merge。

| commit | 影响 |
|---|---|
| 4501cb3d | 教学卡 conversation history 保留；触及 preview router 与 compiled practice |
| f839da6d | 将 Luban card conversation 收回 canonical history；触及 turn contract / sqlite store |
| 80818cff | 失效 stale teaching-card runtime；批量改变 compiled practice authority |
| fd8bee26 | C route 成为 canonical lesson entry；直接触及 yousenwebview 真入口路由 |
| 5c9f83a8 | 安全解锁 practice pools；触及 schema registry、lesson router、40-pack compiled supply |

这五个实质变更都没有 current-lineage release gate/readiness 证据。最新 gate SHA 87599ea5a0cc 不是当前 HEAD 的祖先，不能用“距 gate 的线性 commit 数”伪造可比较性。

### 当前 dirty state

- 169 个状态条目：160 modified + 9 untracked。
- tracked diff：159 files，18778 insertions / 1905 deletions。
- 分组：
  - Web/真实微信 surface：95。
  - Luban 内容/runtime assets：51。
  - tests：12。
  - learner-state/contract/DB：6。
  - contract governance：2。
  - other：3。
- Web/微信 dirty 包括 43 个 web 与 52 个 yousenwebview 条目；当前没有资格复用旧 Playwright/DevTools 结论。
- 本次没有 reset、stash、checkout、stage、commit 或覆盖任何用户改动。

## OA / OM / benchmark / release gate 真相

### OA

- 没有 report_date=2026-07-15、candidate=8ca6a804dde2 的 OA。
- latest OA 已 76.13h，verdict=STALE，stale_inputs=[om]，blocker=artifact_release_stale_vs_head。
- root_causes=[] 不能解释为“没有根因”；同一 payload 有 5 个盲区，证据不足才是正确解释。
- 旧 OA 中 unified_ws_smoke_ok=true 属于更早旧 lineage，不得跨 SHA 继承到今日。

### OM

- latest OM 已 52.10h，绑定 foreign dirty runtime 954c830c7bc5；不是当前 candidate。
- 旧 OM 的 unified WS 已正确 DEFERRED（当时 candidate de5c000816c4 与 runtime 不一致），没有 session_id / turn_id。
- 旧 runtime 84 个 HTTP 请求中 16 个为 401，errors_total=0；只能保留 auth-surface 信号，不能宣布 incident。
- GET /api/v1/mobile/learning-report 旧样本 avg_latency_ms=4904.57，POST /api/v1/first-run/complete=1479.5；lineage/窗口均过期，只能作为待同 SHA 复测的线索。
- 旧 OM 有 7 个 accepted wechat_yousenwebview events，但 coverage=[]、event release_id 为空，且发生在本冻结窗口之前。
- usage_summary/provider_summary 均为空，成本与 provider 负载仍未知。

### Benchmark

- 旧 benchmark 26/26 PASS：pr_gate_core 19/19、regression_watch 6/6、real_exam_quality_spine 1/1。
- 它绑定 87599ea5a0cc、git_dirty=true，且没有覆盖昨日五个实质提交或当前 dirty surface；只能证明旧离线 artifact。

### Release gate / readiness

- latest gate：STALE，final_status=FAIL，recommendation=hold。
- blockers：runtime_release_dirty、playwright_evidence_missing、wechat_devtools_true_entry_pending、artifact_release_stale_vs_head。
- readiness：旧 contract_guard=PASS；旧 Playwright=FAIL；旧 wechat_devtools=FAIL。
- 昨日 fd8bee26 和当前 95 个 Web/微信 dirty 条目都晚于 readiness 证据，因此按规则为 RELEASE-P1；Web harness、Playwright、DevTools project-open、real_wechat_package/auth-chain 必须分层。

## 2026-07-15 冻结窗口原始审计

| 原始面 | 结果 | 正确解释 |
|---|---|---|
| turn event log | turn_events_2026-07-15.jsonl 无事件/文件缺失 | writer/ingestion 证据缺失，不是 0 failure |
| chat history | sessions=0，messages=0，turns=0 | 无法建立 OA chat/trace linkage |
| product behavior | events=0，所有 P0 path count=0 | 无法证明真实使用、行动或退出路径 |
| surface ACK | coverage 缺失 | 旧 accepted sidecar 计数不能替代 coverage |
| backend logs | 49 行；3 warning，0 error | 有日志但无业务闭环 |
| warning 1 | Langfuse auth check false | Langfuse linkage不可用 |
| warning 2-3 | stu_2 dream cycle synthesis boom | test-shaped 且无 trace/runner identity；不得提升为生产 incident |
| Langfuse | enabled=false，trace_id_count=0 | 无端到端 trace truth |
| live metrics | Connection refused | runtime identity 与实时 SLO 均不可证明 |

## Persistence continuity

稳定 key 不含 SHA/release_id/run_id，以 report_date 自然日计数。

| stable gap | first_seen | last_seen | consecutive_count | 升级 |
|---|---|---|---:|---|
| live_runtime_authority_unverified | 2026-07-12 | 2026-07-15 | 4 | **AUTOMATION-P1** |
| missing_true_entry_evidence | 2026-07-12 | 2026-07-15 | 4 | **RELEASE-P1 / AUTOMATION-P1** |
| observer_five_layer_blindspots | 2026-07-12 | 2026-07-15 | 4 | **OBS-P1 / AUTOMATION-P1** |
| daily_payload_missing_for_report_date | 2026-07-13 | 2026-07-15 | 3 | **AUTOMATION-P1** |
| foreign_om_latest_lineage | 2026-07-13 | 2026-07-15 | 3 | **OBS-P1 / AUTOMATION-P1** |
| live_metrics_endpoint_unavailable | 2026-07-14 | 2026-07-15 | 2 | WATCH；不与 earlier SHA mismatch 混写 |
| daily_oa_observer_change_over_36h | 2026-07-14 | 2026-07-15 | 2 | 已因阈值直接为 **OBS-P1** |
| om_over_36h | 2026-07-15 | 2026-07-15 | 1 | **OBS-P1**（阈值触发） |
| observer_dailytrend_repair_evidence | UNKNOWN | 2026-07-15 | UNKNOWN | 无 same-SHA rerun，不能声称修复 |

## P0 / P1 / P2

### P0

1. **RELEASE-P0：live runtime authority 不存在。** metrics endpoint 不可达，candidate dirty，current payload 未生成。
2. **RELEASE-P0：release gate 与 candidate 不可比。** latest gate 已 FAIL，且其 SHA 不是当前 HEAD 祖先；昨日仍有多项 release/surface 变更。
3. **AUTOMATION-P0：current checkout runner 执行顺序违反本次硬规则。** 未过 metrics identity 就会进入 WS token/smoke 路径，不能直接运行。

### P1

1. **OBS-P1：daily/OA/observer/change-impact/OM 超过 36h。**
2. **AUTOMATION-P1：live authority 连续 4 个 report_date 未通过。**
3. **OBS-P1/AUTOMATION-P1：五层 blind spots 连续 4 天。**
4. **AUTOMATION-P1：连续 3 个 report_date 没有对应 daily payload。**
5. **OBS-P1/AUTOMATION-P1：foreign OM latest 连续 3 天未被 current lineage 替换。**
6. **RELEASE-P1：Web/真实微信变更后 Playwright 与 real_wechat_package readiness 缺失。**

### P2

1. 旧 OM 的 401 与慢 learning-report 只保留为复测线索，same-SHA 前不可比较。
2. OM 缺 usage/token/provider summary，成本与 provider load 未知。
3. backend log 出现 test-shaped warning 但没有 actor_type/run_id/trace linkage，日志污染与真实 incident 不能分离。

## 建议动作

1. **Automation owner：**先将 strict live metrics authority preflight 前置到 daily runner，并删除本地 student_demo token fallback；验收要求 endpoint unavailable/mismatch 时零 WS side effect 且仍写 preflight。
2. **Runtime owner：**建立一个 clean candidate，并让受管 127.0.0.1:8001 显式运行它；git_sha、ff_snapshot_hash、deploy_manifest_hash、git_dirty 与 provenance 六项同时 PASS。
3. **Release owner：**先裁决 main 相对 origin/main 的 3/5 分叉和 169 项 dirty state；不要在当前 battlefield 宣称 release-ready。
4. **Observability owner：**same-SHA 恢复后重跑 current report_date，直接核内层 payload；再逐层打通 turn event、chat、product behavior、surface coverage、Langfuse linkage。
5. **Web/WeChat owner：**在独立、受管验证面分别补 Playwright 与 real_wechat_package/auth-chain 证据；不能用 harness、截图或 project-open 互相替代。

## 下一步最小 prompt

> 从 artifacts cwd 开始，只修 observability daily authority 顺序：先读取 live /metrics provenance 并严格比对 candidate git_sha、ff_snapshot_hash、deploy_manifest_hash；PASS 后才允许显式 qa_eval/eval/qa token 的 unified WS。删除 student_demo token fallback，endpoint unavailable/mismatch 时零 WS side effect并保全 runtime_authority_preflight。不要触碰现有 169 项 dirty files，不部署；用 targeted observability tests + full observability suite 验证后再请求 owner 决定是否窄提交。

