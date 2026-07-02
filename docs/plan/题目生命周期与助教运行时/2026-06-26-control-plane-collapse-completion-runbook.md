# 控制面收权 — 部署后完成 Runbook (Task 2-7)

> **状态**: Companion runbook to [2026-06-26 控制面收权 umbrella](2026-06-26-fast-mode-orchestrator-simplification-architecture-plan.md).
> **前提**: PR #261 (4 commit: Task0/1 baseline + live-shadow 度量 + Task2 generation prep + per-site 盲点补测) 已 merge 且部署到生产。
> **用途**: 把 umbrella 的 Task 2-7 从"卡在 7 天 live 窗口"变成部署后可逐步执行的确定性清单。每一步都标注:解锁条件 (gate proof) + 改动 + 验证。

## 0. 已落地基线 (PR #261, 不要重做)

| commit | 提供的能力 |
|---|---|
| `b382e23cd` | `control_plane_writers` allowlist (69 site) + `check_control_plane_writer_allowlist.py` static guard + hard corpus (`control_plane_hard_cases` / `reveal_terminal_hard_cases`) |
| `ce7184353` | live-shadow 度量: `control_plane_shadow_hits` 埋点 (deep_question canonical-missing guard / orchestrator `_select_legacy_capability` :508) + `turn_event_log` instrumentation marker + `scripts/report_control_plane_shadow_hits.py` (fail-closed `exit 2` on zero-coverage) + conftest 隔离 |
| `8957b3d46` | Task2 prep: orchestrator `_prepare_practice_request_context` 在所有 practice generation 路由供 canonical → S3/S4/S7 generation fabricate dormant (behavior-preserving) |
| `8d8417b28` | live-shadow per-scene/per-site + S5/S6 bare-build 盲点埋点 (`unconditional_fabricate`) |

**不变量** (任何后续 PR 必须保持): observe-only 埋点不改控制流; `TerminalResultAssembler`/`QuestionTurnPolicyKernel` 等新角色默认不新建; 每个删除 PR `authority_count_after < before`; 唯一观测 authority = `TurnEventLog` 单一终态 append; reveal last-mile redaction (`unified_ws._redact_*`) + turn-end merge guard (`turn_runtime.py:6339`) 是 §6 安全带不可删。

## 1. 部署后启动窗口

```bash
# 部署 PR#261 到 Aliyun (走 deeptutor-aliyun-release runbook, §3.7 写边界)
# 窗口开始后, 任意时刻查看进度 (生产服务器上, 读生产 turn_event_log):
python scripts/report_control_plane_shadow_hits.py --days 7
# 部署后立即跑应为 exit 2 (instrumented_turns 还在累积); 累计够后看 per_scene/per_site
```

**gate proof 判读**:
- `exit 2` = NOT-MEASURED (覆盖不足, 不得据此删除)。
- `per_scene.practice_generation` 的 fabricate hit == 0 (持续 7 天) → 解锁 **Task 2 删 S3/S4/S7**。
- `per_site.S5_review_render` / `S6_refused` 的 `unconditional_fabricate` 计数 → 量化 review/garbage 二权威活跃度。
- `legacy_production_decision_hits` (`_select_legacy_capability` :508 非 chat) == 0 → 解锁 **Task 3 legacy 降级**。

## 2. Task 2 删除 (解锁条件: per_scene.practice_generation fabricate == 0, ≥7 天)

generation 路径 fabricate (S3/S4/S7) 已被 8957b3d46 prep 变 dormant。窗口证 0 后:
- 改动: deep_question.py 删 S3/S4/S7 的 `turn_semantic_decision or build_turn_semantic_decision(...)` → 只 `= turn_semantic_decision` (canonical 恒在)。
- allowlist: 删对应 fabricate 条目 → `authority_count_after < before`。
- **陷阱 (slice-1 实证)**: 删前必须加"decision 非空"断言测试覆盖每条到达路径; 测试全过≠安全 (空 `{}` 不崩=假绿)。S5/S6 是 bare-build 不在此批 (见 §4)。
- 验证: hard corpus + `test_unified_ws_turn_runtime` same-SHA + 窗口 per-scene 持续 0 + reviewer + Claude 红队。

## 3. Task 3 ChatOrchestrator → CapabilityAdapter (解锁: legacy_production_decision_hits == 0)

- 改动: 降级 `_select_legacy_capability` (orchestrator.py ~789, 调用点 :460 shadow / :508 disabled)。窗口证 :508 production 0-hit 后, 删 production 调用, 只保留 shadow/emergency。
- Partner 只留 identity + skill stack, 移除任何 route/lifecycle/grading/current-object authority。
- 验证: `orchestrator_business_decision_count_after < before` (baseline=13, 见 artifacts) + same-SHA。

## 4. 延后 slice: S1/S2 grading + S5/S6 review (各自独立, HIGH RISK)

investigator 穷尽 path-map 明确这些**不是 orchestrator 单点供给可解**:
- **S1/S2** (MCQ/case full-submission grading, deep_question ~3715/3755): `allowed_patch` 依赖 deep_question 内 `*_context_from_full_submission` 的 item-count, orchestrator 路由时拿不到 → behavior-preserving 供给需把解析前移或在 deep_question 解析块内供 canonical。碰 §6 grading 安全带。**单独 slice + live 证。**
- **S5/S6** (review-render miss / refused, bare `build`): 无条件二权威 (canonical present 也 fabricate)。需 (a) orchestrator/lifecycle 为 review-render 路径供 canonical (值 = ask_about_active_object/route_to_followup_explainer/no_state_change) (b) deep_question S5/S6 改 `tsd or build`。**这是 slice-1 question_review CRITICAL 区, 必须穷尽 review 路径 + 每路径非空断言。**
- 每条: prep (供给, dormant) → 窗口证 per_site 0 → 删。

## 5. Task 4 TurnRuntime 收回 (scene pre-stamp)

- `_stamp_current_submission_scene_pre_capability` (turn_runtime.py ~1420) 是 `question_lifecycle_scene` 的第二 writer (canonical = `resolve_question_lifecycle_scene_decision`)。hard corpus 已证 canonical scene 对 12 case 全对。
- **难点**: pre-stamp 在 capability 选择**前**驱动 mode-selection + mcq_grading_bypass recovery → 不是纯 fallback, 删除需先把这些消费者改读 canonical scene (behavior change, 非纯 additive)。
- 路径: 先加 live-shadow scene 埋点确认 pre-stamp 与 canonical 一致率 → 改消费者读 canonical → 窗口证 pre-stamp 0 影响 → 删。**memory 多条 SEV-1 (题组塌缩/fail-closed 失忆) 警告, 最谨慎。**

## 6. Task 5 TerminalResultAssembler (reveal 双 sink + visible-output)

- 现状: tutorbot/deep_question 直接 `bus.result()` 构造 result_payload; reveal 碎成 4 处 (tutorbot `_reveal_reference_flags` / deep_question overrides / question_review 强制 / runtime trace 重建)。
- 目标: 单一 contentful visible-output writer; capability 只产 payload; ACK/PROGRESS 零领域 payload。这是**新角色**, 受 §3 creation gate: 必须证明引入它让 RESULT writer 3→1 + reveal writer 4→1 (authority 下降)。
- 保留 `unified_ws._redact_*` last-mile redaction (§6 安全带)。
- ACK / first_useful_content 当前不存在 (live-shadow guard 已 dormant 预留), 此 Task 才铸为 zero-domain transport frame。

## 7. Task 6 fast/deep latency (前置: contract-first)

- **前置**: `contracts/turn.md:100` fast 定义 (`kb_first + single_shot_with_prefetch` + 允许 web_search) 与目标 (fast 首 useful 前 tool_rounds=0 / 默认禁 web_search) 冲突, **contract 优先 → 必须先改 turn.md + 同步 `CONTRACT.md`/`contracts/capability.md`/`contracts/index.yaml`×2 + contract guard test, 且代码同 PR 改到匹配** (避免 contract-code gap)。
- 只能在 Task 1-5 authority baseline 后做。ack/progress/process-only text 不计入 first_useful_content。不得用 `run_eval_gate.py --list`/telemetry 冒充 latency closure。

## 8. Task 7 e2e/微信 true-entry closure

- same-SHA replay + hard corpus + 微信 true-entry (如触及微信面, 走 DevTools 真入口非 `/wechat-harness`) + observability 与 terminal consume 对齐。

## 完成判据 (umbrella §6.5 / §13)

每个 Task 2-7 PR 落地前: `authority_count_after < before` + `legacy_production_decision_hits == 0` + `compat_projection_production_reads == 0` (窗口测) + hard corpus pass + same-SHA replay + 微信 true-entry (如适用) + reviewer + Claude 异源红队 + 至少删/降/只读化一个 competing writer。**telemetry/progress/ack/wechat-harness/report-only 不得冒充 closure。**
