# Learner State / Bot-Learner Overlay 复审证据

## 1. 文档信息

- 文档名称：Learner State / Bot-Learner Overlay 复审证据
- 文档路径：`/docs/plan/2026-04-24-learner-state-overlay-completion-evidence.md`
- 创建日期：2026-04-24
- 状态：Gap Review v1
- 关联主文档：
  - [2026-04-15-learner-state-memory-guided-learning-prd.md](2026-04-15-learner-state-memory-guided-learning-prd.md)
  - [2026-04-15-learner-state-service-design.md](2026-04-15-learner-state-service-design.md)
  - [2026-04-15-learner-state-supabase-schema-appendix.md](2026-04-15-learner-state-supabase-schema-appendix.md)
  - [2026-04-15-bot-learner-overlay-prd.md](2026-04-15-bot-learner-overlay-prd.md)
  - [2026-04-15-bot-learner-overlay-service-design.md](2026-04-15-bot-learner-overlay-service-design.md)

## 2. 结论

Learner State / Memory / Heartbeat 与 Bot-Learner Overlay 没有达到产品级完成。

当前仓库已经有 repo foundation：contract、代码、migration、运营面入口、聚焦测试都存在，并且部分主链路已接入。但这些只能证明“基础设施可工作”，不能证明 PRD 背后的产品目的已经达成。

真正的产品目的有三条：

1. 学员长期状态要成为所有学习功能共同使用的记忆与画像，而不是旁路数据。
2. Heartbeat 要基于真实 learner state 主动触达，并且在多 Bot 下只产生一个受控触达。
3. Overlay 要支持局部差异，但不能污染全局 learner truth，并且 promotion 要可治理、可审计、可回滚。

这三条目前仍是部分达成。2026-04-24 已先收口四个 repo hard gate：

1. Guide completion 会确定性进入 learner summary，并在下一轮统一聊天主路径中被读取。
2. 多 Bot heartbeat due jobs 会经过全局仲裁，只执行 winner，suppressed job 与 winner 都写入 learner memory，运营面可读 delivery 与 arbitration history。
3. Overlay promotion 不再只凭 `candidate_kind` 写回全局 learner core；候选必须同时满足置信度与晋升依据 gate，未达标候选会返回 skipped reason，供运营治理和质量抽检。
4. Member Console 使用真实 `BotLearnerOverlayService + LearnerStateService` 执行 promotion apply 时，会把成功晋升与 skipped reason 同时写入运营 audit。

2026-04-24 生产侧复验更新：

- Learner State / Memory / Heartbeat 的生产 outbox 调度、FK 身份、heartbeat upsert 三个 blocker 已修复并在阿里云容器验证。
- 生产 outbox 从 `sent=41` 推进到 `sent=1284`；`processing` stuck 已恢复；外键 409 已清零；heartbeat `(user_id, bot_id, channel)` 唯一键冲突已清零。
- Bot-Learner Overlay 的 repo-side contract / migration / service / tests 已完成，但生产 Supabase 仍缺 `bot_learner_overlays`、`bot_learner_overlay_events`、`bot_learner_overlay_audit` 三张表。当前阿里云环境只有 Supabase REST service key，没有 DB_URL / SQL RPC，因此 overlay 生产写入仍被 PGRST205 阻塞，不能宣布生产级全关。

## 3. 单一 authority

| 业务事实 | 唯一 authority | 证据入口 |
| --- | --- | --- |
| 学员长期 profile/progress/goals/summary | `LearnerStateService` | `deeptutor/services/learner_state/service.py` |
| Supabase core table 读写 | `LearnerStateSupabaseSyncCoreStore` 与 outbox writer | `deeptutor/services/learner_state/supabase_store.py`, `deeptutor/services/learner_state/supabase_writer.py` |
| Guided Learning completion 写回 | `LearnerStateService.record_guide_completion` | `deeptutor/services/learner_state/service.py` |
| Heartbeat 调度主语 | `user_id` | `deeptutor/services/learner_state/heartbeat/` |
| 多 Bot heartbeat 触达裁决 | `LearnerHeartbeatArbitrator` | `deeptutor/services/learner_state/heartbeat/arbitration.py` |
| Bot 局部差异 | `BotLearnerOverlayService` | `deeptutor/services/learner_state/overlay_service.py` |
| Overlay 晋升为全局事实 | `BotLearnerOverlayService.apply_promotions` 调用 `LearnerStateService` | `deeptutor/services/learner_state/overlay_service.py` |
| 运营治理面 | `MemberConsoleService` | `deeptutor/services/member_console/service.py` |

## 4. 已完成范围

### 4.1 Learner State / Memory / Heartbeat

- `user_profiles / user_stats / user_goals` 通过 Supabase core store 读写，缺配置时走本地 durable fallback。
- `learner_summaries / learner_memory_events / learning_plans / learning_plan_pages / heartbeat_jobs` 通过 outbox writer 同步。
- `LearnerStateRuntime` 承接 outbox flusher 与 heartbeat scheduler。
- Guide completion summary 会确定性写入 learner summary 顶部，不再只依赖后续 LLM summary rewrite。
- Heartbeat job 状态词表收敛为 `active / paused / disabled / failed`，旧 `stopped` 只作为兼容输入并归一化为 `disabled`。
- 默认 `LearnerStateService + LearnerHeartbeatScheduler` 组合支持多 Bot arbitration，suppressed job 不再绕过 learner memory 历史。
- Member Console 已能展示 learner state、heartbeat jobs、heartbeat history、arbitration history，并支持 pause/resume。

### 4.2 Bot-Learner Overlay

- Overlay 只允许承载局部字段：`local_focus / active_plan_binding / teaching_policy_override / heartbeat_override / working_memory_projection / channel_presence_override / local_notebook_scope_refs / engagement_state / promotion_candidates`。
- Overlay 显式拒绝 profile、summary、progress、goals、weak points、subscription 等全局 learner truth 字段。
- Promotion candidate 只能通过统一 promotion pipeline 晋升到 learner core。
- Promotion pipeline 会检查置信度与晋升依据，只有结构化结果、用户确认、稳定复现或明确 `explicit_*` 候选才允许进入全局 writeback；无证据候选留在 overlay 队列并返回 skipped reason。
- 多 Bot heartbeat 使用 active plan、goal urgency、recent interaction、overlay override、cooldown 等信号仲裁，只允许一个 winner。
- Member Console 已覆盖 overlay list/read/patch、events/audit、promotion apply/ack/drop；promotion apply 的 audit 会记录 `acked_ids / dropped_ids / skipped_ids / skipped`。

## 5. Migration 证据

- `supabase/migrations/20260415000100_learner_state_core.sql`
- `supabase/migrations/20260415000200_bot_learner_overlay.sql`
- `supabase/migrations/20260419000100_learner_state_rls.sql`

这些 migration 已在仓库中提供 schema 和 RLS 规则。生产实例是否已执行，需要部署 gate 用真实 Supabase 环境单独验收。

## 6. 测试入口

聚焦回归命令：

```bash
python3 -m pytest \
  tests/services/learner_state/test_service.py \
  tests/services/learner_state/test_overlay_service.py \
  tests/services/learner_state/test_supabase_store.py \
  tests/services/learner_state/test_supabase_writer.py \
  tests/services/learner_state/test_outbox.py \
  tests/services/learner_state/test_flusher.py \
  tests/services/learner_state/test_runtime.py \
  tests/services/learner_state/test_heartbeat_service.py \
  tests/services/learner_state/heartbeat/test_service.py \
  tests/services/learner_state/heartbeat/test_scheduler.py \
  tests/services/learner_state/heartbeat/test_arbitration.py \
  tests/services/member_console/test_service.py \
  tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_end_to_end_applies_overlay_promotion_and_reads_next_turn \
  tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_uses_guide_completion_summary_from_real_learner_state \
  tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_context_orchestration_loads_bot_overlay_into_context_pack \
  tests/web/test_bi_member_admin_surface.py \
  tests/supabase/test_learner_state_rls_migration.py \
  -q
```

本轮验证结果（2026-04-24）：

- `151 passed in 50.00s`

新增 hard gate 验证（2026-04-24）：

- `python3 -m pytest tests/services/learner_state/test_service.py tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_uses_guide_completion_summary_from_real_learner_state tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_uses_user_scoped_learner_state_when_user_id_is_available -q`
- `16 passed in 1.64s`

Heartbeat hard gate 验证（2026-04-24）：

- `python3 -m pytest tests/services/learner_state/heartbeat/test_scheduler.py tests/services/learner_state/test_heartbeat_service.py tests/services/learner_state/test_runtime.py tests/services/member_console/test_service.py::test_member_console_learner_state_panel_and_controls -q`
- `13 passed in 0.70s`

Overlay promotion hard gate 验证（2026-04-24）：

- `python3 -m pytest tests/services/learner_state/test_overlay_service.py -q`
- `13 passed in 0.91s`

端到端打通验证（2026-04-24）：

- `python3 -m pytest tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_end_to_end_applies_overlay_promotion_and_reads_next_turn -q`
- 覆盖链路：`BotLearnerOverlayService.promote_candidate` -> `TurnRuntimeManager` post-turn refresh -> `BotLearnerOverlayService.apply_promotions` -> `LearnerStateService.merge_progress / append_memory_event` -> 下一轮 unified turn 读取 `learner_progress` 与 `overlay_promotion` memory hit。
- 结果已纳入本轮聚焦回归：`151 passed in 50.00s`

运营入口验收（2026-04-24）：

- `python3 -m pytest tests/services/member_console/test_service.py::test_member_console_overlay_promotion_apply_uses_real_services_and_audits_skips tests/api/test_tutor_state_router.py tests/api/test_member_router_auth.py tests/services/learner_state/test_overlay_service.py tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_end_to_end_applies_overlay_promotion_and_reads_next_turn -q`
- 覆盖链路：Member Console promotion apply -> 真实 overlay service -> 真实 learner state service -> progress writeback -> overlay skipped candidate retention -> audit `skipped_ids/skipped`。
- `29 passed in 3.24s`

生产 outbox / Supabase 写回验收（2026-04-24）：

- 本地 focused 回归：`python3 -m pytest tests/services/learner_state/test_outbox.py tests/services/learner_state/test_flusher.py tests/services/learner_state/test_supabase_writer.py tests/supabase/test_learner_state_rls_migration.py tests/services/learner_state/test_service.py tests/services/learner_state/test_overlay_service.py tests/services/learner_state/heartbeat/test_scheduler.py tests/services/learner_state/test_heartbeat_service.py tests/services/member_console/test_service.py::test_member_console_overlay_promotion_apply_uses_real_services_and_audits_skips tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_uses_guide_completion_summary_from_real_learner_state tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_end_to_end_applies_overlay_promotion_and_reads_next_turn -q`
- 结果：`58 passed in 3.65s`
- 阿里云热修文件：`deeptutor/services/learner_state/outbox.py`, `deeptutor/services/learner_state/supabase_writer.py`
- 阿里云 `readyz`：`status=ok`, `learner_state_runtime_ready=true`
- 生产 outbox 修复证据：
  - 修复前：`pending=5878`，poison FK retry 约 `3414`，`processing=20` stuck。
  - 修复后：`sent=1284`，`pending_fk_errors=0`，`pending_unique_heartbeat_errors=0`，`processing` 由 lease 管理，不再永久 stuck。
- 生产身份修复证据：
  - 已补 canonical UUID users / aliases。
  - 已把历史 outbox 与 heartbeat jobs 中可证明属于同一人的 legacy user id 迁到 canonical UUID。
- 仍未通过的生产证据：
  - `pending_overlay_schema_errors=41`
  - Supabase REST 返回 `PGRST205`，缺 `public.bot_learner_overlays` 等 overlay 表。
  - 当前环境无 DB_URL，且 `exec_sql / execute_sql / run_sql / pg_execute` RPC 均不存在，无法通过当前凭据执行 DDL。

## 7. 未完成目标

### 7.1 Learner State / Memory / Heartbeat

| 目标 | 当前状态 | 缺口 |
| --- | --- | --- |
| 跨 Chat / Guide / Notebook / TutorBot 的长期记忆共享 | repo hard gate 部分收口 | 已有自动化回归证明 Guide completion summary 会进入下一轮统一聊天上下文；仍缺真实模型回放与线上满意度验收。 |
| Supabase 作为生产级主存储 | 部分达成 | 有 core store、writer、migration、RLS 测试，但当前本地验证主要是 mocked PostgREST；真实生产实例 migration apply、权限、回滚、数据一致性未验收。 |
| Guided Learning completion 更新 summary/profile/progress | repo hard gate 部分收口 | `record_guide_completion` 会更新 profile/progress/summary，并有 turn runtime 回归证明下一轮读取；仍缺真实模型效果验收。 |
| Heartbeat 主动学习触达 | repo + production writeback blocker 已收口 | 已有自动化回归证明 due job -> arbitration -> executor -> delivery/arbitration history；生产 outbox/FK/upsert blocker 已修复；仍缺真实 channel delivery、用户频控、退订/负反馈闭环、5 万规模调度验证。 |
| 运营面治理 | repo hard gate 部分收口 | Member Console service/API 有入口，promotion apply 已用真实服务组合验收并审计 skipped reason；仍缺运营权限矩阵、误操作恢复、线上审计 SOP。 |

### 7.2 Bot-Learner Overlay

| 目标 | 当前状态 | 缺口 |
| --- | --- | --- |
| 多 Bot 局部差异 | repo 达成，生产 schema 未达成 | overlay 字段和上下文注入存在；生产 Supabase overlay 表仍未创建，overlay writeback 仍会 404；缺多 Bot 真实使用流量下的稳定性和污染检测。 |
| promotion 仲裁与晋升治理 | repo hard gate 部分收口 | `apply_promotions` 已增加置信度 + 晋升依据 gate，并返回 skipped reason；Member Console audit 已记录 skipped；仍缺真实候选质量抽检、冲突处理、人工审核 SOP、误操作回滚。 |
| heartbeat 全局仲裁 | repo hard gate 部分收口 | `LearnerHeartbeatArbitrator` 已实现 winner/suppress，且默认 `LearnerStateService + Scheduler` 组合会把 winner/suppression 写入运营历史；仍缺生产级多 Bot due jobs 回放和触达频控验证。 |
| 后台治理 | 部分达成 | API/service 有操作入口，但缺 UI 级完整验收、权限分层、审计导出、回滚机制。 |

## 8. 仍需外部 gate

这些项目不能只靠本地仓库宣布完成：

1. 真实生产 Supabase migration apply 与回滚演练。
2. 线上 service role / RLS / admin 权限配置验收。
3. 5 万会员 heartbeat job 调度、outbox flush、arbitration 的压测报告。
4. 运营 SOP：promotion apply/ack/drop 的权限、审计、误操作恢复流程。
5. 真实多 Bot 线上流量下的 promotion 质量抽检与触达频控调参。
