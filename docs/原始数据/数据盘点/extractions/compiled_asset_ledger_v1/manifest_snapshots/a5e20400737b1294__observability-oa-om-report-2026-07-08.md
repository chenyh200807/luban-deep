# DeepTutor OA / OM / Observability 日报

- report_date: `2026-07-08`
- generated_at: `2026-07-09 09:24:07 Asia/Shanghai`
- automation_id: `deeptutor-observability-oa-om-report`
- verdict: `STALE`

## 1. 结论

今天不是 freshness 失效，而是 **release truth 继续失真**：

1. `daily_trends`、`OA`、`change_impact`、`release_gate`、`benchmark` 都是刚跑出来的，年龄上是新的。
2. 但 `OM` 仍绑定本地 live runtime `1.0.0+4d8d12aaa876+local`，而当前 battlefield HEAD / daily spine 绑定 `1.0.0+571a793a0f78+local`，所以这是 **fresh by age, stale by lineage**。
3. `release_gate.final_status=FAIL`，而且继续 fail-closed：`runtime_release_dirty`、`contract_guard_failed`、`playwright_evidence_missing`、`wechat_devtools_true_entry_pending` 都还在。
4. observer blind spots 从昨天的 3 个扩大到今天 5 个，新增 `missing_turn_event_log` 和 `missing_recent_conversation_evidence`，说明 control-plane 证据面正在变窄，不是单纯重复昨天。

## 2. Authority / 环境快照

- `pwd -L`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- `pwd -P`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts`
- `git toplevel`: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor`
- `core.worktree`: 空
- branch: `release/old-blue-frontend`
- HEAD: `571a793a0f7855bd4b4341d354bc1a8b879ab65c`
- `origin/main`: `06aedc6466d1b32b1f4e975ab79327a05ea3e5f7`
- git status: `ahead 3, behind 3`
- `.env`: `artifacts/.env` 缺失；父级 `../.env` 可读，今天仍靠父级 fallback

主仓 dirty 是一等信号，不是背景噪音。当前脏面同时命中：

- `turn/capability`: `deeptutor/api/routers/mobile.py`
- `surface`: `wx_miniprogram/`、`yousenwebview/`、`web/app/(workspace)/bi/...`
- `member/billing`: `deeptutor/services/member_console/*`、`wallet/service.py`、`wechat_pay.py`
- `plan/docs/assets`: `docs/plan/INDEX.md`、多份 plan、`artifacts/luban_case_family_assets/F16/*`

## 3. Freshness 表

| Surface | Run ID | Release | Freshness | 备注 |
| --- | --- | --- | --- | --- |
| daily_trends | `observability-daily-1783560247` | `571a793a0f78` | Fresh | verdict=`STALE` |
| OA | `oa-daily-1783560247` | `571a793a0f78` | Fresh | root_causes=0 |
| change_impact | `change-impact-1783560247` | `571a793a0f78` | Fresh | risk=`medium` |
| release_gate | `release-gate-1783560247` | `571a793a0f78` | Fresh | final_status=`FAIL` |
| benchmark | `benchmark-1783560245` | `571a793a0f78` | Fresh | 26/26 PASS |
| observer_snapshot | `observer-snapshot-1783560245` | `571a793a0f78` | Fresh | 但回读了旧 `daily_trend_run_id` |
| OM | `om-1783560245` | `4d8d12aaa876` | Fresh but stale lineage | 与 HEAD 不同 SHA |
| readiness latest | `readiness-matrix-1783560247` | `571a793a0f78` | Fresh | 3/3 required checks FAIL |

结论：SLA 意义上的 freshness 没过期；**authority lineage 过期**。

## 4. 昨日发生了什么

昨天唯一新的 commit 是：

- `87ad68c91 fix(tutorbot): preserve mnemonic study aid flow`

影响面：

- `contracts/turn.md`
- `deeptutor/capabilities/tutorbot.py`
- `deeptutor/services/question_followup.py`
- `deeptutor/services/session/turn_runtime.py`
- 3 个相关测试文件

这笔 commit 本身命中 `turn / TutorBot / followup`，属于高敏感面。但今天 `change_impact` 的 release 判断主要不是由它单独驱动，而是由 **当前未提交 dirty scope** 一起驱动，尤其是 `mobile.py + wx_miniprogram + yousenwebview + member_console` 这批未提交改动。

## 5. OA / OM / Benchmark / Release Gate 证据

### 5.1 OM

- live metrics 来源：`http://127.0.0.1:8001/metrics`
- provenance: `source=live_metrics_endpoint`、`fallback_used=false`、`status_code=200`
- 但 live runtime release 是 `1.0.0+4d8d12aaa876+local`
- 当前 daily/release/OA/change-impact release 是 `1.0.0+571a793a0f78+local`
- `unified_ws_smoke=PASS`
- `turn_success_ratio=1.0`
- `turn_p95_latency_seconds_proxy=10.528`，高于 6s target，SLO 为 `WARN`

关键点：OM 不是坏掉，而是 **读到了别的 runtime**。

### 5.2 Release Gate

- `verdict=STALE`
- `final_status=FAIL`
- `stale_inputs=["om"]`
- blockers:
  - `runtime_release_dirty`
  - `contract_guard_failed`
  - `playwright_evidence_missing`
  - `wechat_devtools_true_entry_pending`
  - `artifact_release_stale_vs_head`

gate 解释：

- `P0 Runtime=FAIL`
- `P1 Trace Completeness=WARN`
- `P2 Benchmark Regression=PASS`
- `P3 AAE=PASS`
- `P4 Blind Spot Budget=WARN`
- `P5 Change Impact=WARN`
- `P6 Plan Completion=WARN`

### 5.3 Benchmark

- run: `benchmark-1783560245`
- requested suites:
  - `pr_gate_core`
  - `regression_watch`
  - `real_exam_quality_spine`
- summary: `26 executed / 26 passed / 0 failed / 0 skipped`

结论：benchmark 继续提供 P2 质量证据，但**完全不能冲销 release truth 和 observer blind spots**。

### 5.4 OA

- `root_causes=[]`
- `causal_candidates=1`
- first failing signal: `observer_blind_spots`
- repair_playbook 仍指向 observer / contract_guard / ws smoke / surface smoke 这条观测链，而不是业务逻辑修复

结论：OA 目前不是在给出新根因，而是在提醒“证据面先塌了”。

## 6. Readiness 缺口

`change_impact.required_readiness_checks` 仍是：

- `contract_guard`
- `playwright`
- `wechat_devtools`

三项今天全部 FAIL，而且都是 required，不是 advisory。

### contract_guard

- 失败原因不是 guard 本身，而是 `deeptutor/api/routers/mobile.py` 命中 `turn` 和 `capability` 敏感面，但没有同步更新 contract surfaces。
- stderr 明确点名：
  - `contracts/turn.md`
  - `contracts/capability.md`
  - `contracts/index.yaml`
  - `deeptutor/contracts/unified_turn.py`
  - `deeptutor/capabilities/request_contracts.py`

### Playwright

- 不是今天跑挂了。
- 是 **current release 没有 Playwright readiness row**，因此被 daily fallback 判成 `playwright_evidence_missing`。

### WeChat DevTools

- 不是 CLI 报错。
- 是 **current release 没有真入口 `real_wechat_package` 证据**，因此被 daily fallback 判成 `wechat_devtools_true_entry_pending`。
- payload 已把边界写得很清楚：`islogin/open` 只算 preflight，不算 page scenario PASS。

## 7. 观测盲区

今天 observer blind spots 是 5 个：

1. `missing_turn_event_log` `high`
2. `missing_surface_coverage` `medium`
3. `missing_recent_conversation_evidence` `medium`
4. `missing_product_behavior_evidence` `medium`
5. `missing_langfuse_trace_linkage` `medium`

其中最值得警惕的是 split evidence：

- OM live metrics 明确看到 `wechat_yousenwebview` accepted surface events 13 条
- 但 observer `surface_ack.coverage=[]`
- 同时 `product_behavior.event_count=0`
- 这些 surface events 的 metadata 里 `release_id=""`、`app_version=""`

这更像 **surface event 被接收了，但没进入可 join 的 release/product authority**，而不是用户昨天完全没动页面。

另外两个新增退化：

- `turn_event_log` 对应文件 `turn_events_2026-07-08.jsonl` 根本不存在
- `recent_conversations` 在冻结窗口内 `session_count=0`

## 8. P0 / P1 / P2

### P0

- `artifact_release_stale_vs_head`: live OM runtime 仍停在 `4d8d12aaa876`，daily/release 在 `571a793a0f78`
- `runtime_release_dirty`: 当前 release spine 仍是 dirty workspace
- `contract_guard_failed`: `mobile.py` 触碰 contract-sensitive 面但 contract surface 未同步

### P1

- `playwright_evidence_missing`
- `wechat_devtools_true_entry_pending`
- observer blind spots 扩大到 5 个，且 `surface_events accepted` 与 `observer/product_behavior=0` 继续分裂
- `artifacts/.env` 仍缺失，自动化 contract 继续依赖父级 `.env` fallback

### P2

- benchmark 26/26 PASS，但只能算质量脊梁健康
- OM SLO 仍有 latency warning：`turn_p95_latency_seconds_proxy=10.528`

## 9. 建议动作

1. 先把 `127.0.0.1:8001` 对应 runtime 的 release lineage 对齐到当前 HEAD，再重跑 OM/release gate；在此之前，任何 `status_code=200` 都不是 release truth。
2. 按 contract_guard 点名的 `turn/capability` surfaces 补 contract surface，而不是只补测试；`mobile.py` 现在是显式 fail-closed blocker。
3. 把 surface event metadata 里的 `release_id` / `app_version` 补成真实 authority，再查为什么 accepted event 进不了 `surface_ack` 和 `product_behavior`。
4. 单独查 `turn_event_log` 为什么 2026-07-08 没落文件；这是今天 blind spot 从 3 扩到 5 的关键新增项。
5. 如果当前 scope 要求 release readiness，就必须补 current-release 的 Playwright 和 WeChat DevTools 真入口证据；没有 row 不能继续拿 fallback 当“已知待补”轻描淡写。

## 10. 最小下一步 Prompt

```text
从 /Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/artifacts 开始，只读定位为什么当前 OM 仍绑定 4d8d12aaa876 而 daily/release 绑定 571a793a0f78；同时查 surface_events accepted 13 条为何没有进入 observer surface_ack / product_behavior，并给出 file:line 级 root-cause。
```
