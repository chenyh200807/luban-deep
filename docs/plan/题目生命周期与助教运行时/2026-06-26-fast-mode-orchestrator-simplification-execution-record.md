# Fast / Deep Latency And Orchestrator Simplification Execution Record

> Status: Thin-slice implemented / Phase 2-3 gated  
> Date: 2026-06-26  
> Branch: `codex/fast-deep-latency-authority`  
> Worktree: `/Users/yehongchen/.codex/worktrees/deeptutor-fast-deep-latency-authority`  
> Source plan: `2026-06-26-fast-mode-orchestrator-simplification-architecture-plan.md` v0.3

## Commander Decision

The commander lane accepted the v0.3 plan's thin-slice constraint: do not rewrite `ChatOrchestrator`, do not add `TurnRoutingDecision` / `FastTurnExecutionPolicy`, and do not delete production safety guards before real fast/deep slow-turn evidence exists.

Executed safe thin-slice scope is:

- make `TurnRuntimeManager` the runtime-owned first useful content latency observer;
- derive a per-turn latency timeline and max-stall summary from existing telemetry;
- add internal authority-probe telemetry for competing semantic decision writers;
- keep provider / latency telemetry out of public WS payloads;
- document the contract boundary so telemetry cannot become a new routing, scoring, billing, or learner-state authority;
- replace the preselected practice-generation half-schema `turn_semantic_decision` writer with the canonical semantic decision builder;
- remove one deep-mode pre-content duplicate: after successful RAG prefetch, the first agent-loop LLM call no longer re-advertises `rag`.

## Implemented

### 1. First Useful Content Runtime Observation

Implemented in `deeptutor/services/session/turn_runtime.py`.

`TurnRuntimeManager` now records:

- `server_turn_start_to_first_useful_content_ms`
- `capability_stream_to_first_useful_content_ms`
- `first_useful_content_event_type`
- `first_useful_content_source`
- `first_useful_content_content_source`
- selected mode / execution path / lifecycle scene when present

Rules:

- `progress`, ack/status-only events, internal events, empty content, and tool argument deltas do not count.
- public `content` from the final assistant channel and public `result.metadata.response` count.
- the observation is written only after the event has passed runtime persistence/publication boundary.
- these fields are terminal observability projection only.

### 2. Latency Timeline And Max Stall

Implemented in `deeptutor/services/session/turn_runtime.py` and `deeptutor/services/observability/observer_snapshot.py`.

Terminal turn observation metadata now includes:

- `latency_timeline`
- `latency_max_stall`
- `latency_timeline_truncated`
- `latency_timeline_total_count`

The timeline is derived from existing fields:

- `start_turn_setup_stage_timings_ms`
- `latency_stages_ms`
- `context_build_stage_timings_ms`
- `capability_stream_stage_timings_ms`
- `llm_stream_telemetry.calls[].stage_timings_ms`
- first useful content timing

`latency_max_stall` is computed from the full untruncated timeline, then the display timeline is capped. This prevents the largest stall from disappearing because of the timeline display cap.

`observer_snapshot` now exposes `slow_turn_samples` with sanitized fields only: turn id, status, capability, latency, first useful content timing, selected mode / execution path, and max-stall summary.

### 3. Semantic Authority Probe

Implemented in `deeptutor/services/semantic_router_telemetry.py`.

Internal `semantic_router_telemetry` now includes:

- `authority_probe_schema_version`
- `decision_writer_chain`
- `decision_writer_chain_source`: `recorded`, `inferred`, or `none`
- `final_decision_writer`
- `decision_authority_count`
- `decision_overwrite_count`
- `decision_schema_valid`
- `legacy_selector_used`
- `preselected_bypass_used`
- `deep_question_canonical_decision_missing`
- `fallback_decision_reason_prefix`

This is observation only. It does not drive capability routing or repair decisions.

### 4. Public WS Redaction For Internal Telemetry

Implemented in `deeptutor/api/routers/unified_ws.py`.

Outbound public WS copies now drop internal observability keys such as:

- `llm_stream_telemetry`
- provider timing keys
- first useful content timing keys
- `latency_timeline`
- `latency_max_stall`
- stage timing maps

Persisted turn events and terminal observer truth remain unchanged. This prevents provider/debug telemetry from becoming a public client contract.

### 5. Contract Updates

Updated:

- `contracts/turn.md`
- `contracts/capability.md`

The contracts now state that first-useful-content timing, latency timeline, max stall, and provider telemetry are internal terminal observability projections only.

### 6. Orchestrator Canonical Decision Reduction

Implemented in `deeptutor/runtime/orchestrator.py`.

`_prepare_practice_request_context` no longer writes a partial `turn_semantic_decision` containing only:

- `next_action`
- `confidence`
- `reason`

That partial dict looked like canonical semantic truth but failed the canonical schema expected by `normalize_turn_semantic_decision`, which could push the decision back into downstream compatibility/fallback behavior.

The branch now uses `build_turn_semantic_decision(...)` for this preselected practice-generation path:

- `relation_to_active_object`: `continue_same_learning_flow` when an active question object exists, otherwise `switch_to_new_object`
- `next_action`: `route_to_generation`
- `allowed_patch`: `set_active_object`
- `target_object_ref`: derived from the canonical active object
- `turn_semantic_decision_writer_chain`: `["orchestrator_practice_context"]` for internal authority telemetry

This is still a compatibility writer, not the final desired architecture. The improvement is that it now emits canonical schema and explicit provenance instead of a malformed mirror truth.

### 7. Deep Mode RAG First-Loop Deduplication

Implemented in `deeptutor/tutorbot/agent/loop.py`.

Before this change, deep/full-agent turns could successfully run grounded RAG prefetch, inject the RAG tool result into the initial messages, and still advertise `rag` again on the first agent-loop provider call. That made it easy for the model to spend the first loop on duplicate RAG instead of producing the first useful answer.

The branch now marks successful, non-degraded RAG prefetch as:

- `prefetched_rag_satisfied=True`

Then `_run_agent_loop` suppresses only `rag` on the first provider call:

- `web_search` and other tools remain available;
- degraded RAG prefetch does not set the marker and keeps `rag` available;
- later loop behavior is unchanged after the first call;
- RAG authority remains the existing RAG tool/service/evidence bundle path.

This is a reversible deep-mode latency reduction. It does not turn deep into fast mode and does not change answer-generation quality policy.

## Not Implemented Yet

These are intentionally not implemented because the plan's gates are not met:

- deleting `_select_legacy_capability` production paths;
- adding `TurnRoutingDecision`, `FastTurnExecutionPolicy`, `PublicRevealDecision`, or `UserVisibleEventBoundary` schema objects;
- moving reveal authority;
- deleting the remaining preselected/legacy routing paths;
- parallelizing deep RAG/web/tool execution;
- computing `provider_to_public_content_gate_ms`.

Reason: provider stage timings currently use provider-call-relative timing, while first useful content uses server-turn-relative timing. Without a shared absolute provider request timestamp, subtracting them would create false precision.

Newly observed but not changed in this branch:

- `process_direct` still calls `memory_consolidator.maybe_consolidate_by_tokens(session)` before building the prompt. This can be first-content-path work when a session exceeds the context window, but it is also the current safety valve that advances `last_consolidated` before `get_history(max_messages=0)` reads unconsolidated history. It needs its own RED test and overflow-safe design before deferral.

## Immediate Next Gates

To prove user-visible latency improvement beyond this branch, collect at least:

- 1-2 real slow fast turns;
- 1 real slow deep turn;
- `turn_id`, surface, provider/model, selected mode, execution path;
- terminal observer metadata containing `server_turn_start_to_first_useful_content_ms`, `latency_timeline`, and `latency_max_stall`;
- public WS payload scan proving no internal telemetry leaks;
- same-SHA replay for any proposed deletion or optimization.

Allowed next actions after evidence:

- if max stall is provider-bound: move to provider/model/concurrency owner, not Orchestrator cleanup;
- if max stall is context/source/tool pre-work: make exactly one reversible reduction;
- if max stall is repeated tool planning after successful prefetch: the deep RAG first-loop deduplication here is the candidate to A/B;
- if max stall is public gate/runtime persist/frontend consume: optimize that boundary;
- if authority probe shows recorded multi-writer chain: demote/delete one competing writer only after hard-case replay coverage.

## Verification

Passed:

```bash
python -m pytest tests/api/test_unified_ws_public_redaction.py tests/capabilities/test_request_contracts.py tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_observer_breaks_down_start_setup_and_capability_stream tests/api/test_unified_ws_turn_runtime.py::test_turn_completion_writes_internal_semantic_router_telemetry_event tests/services/observability/test_turn_runtime_observer_event.py tests/services/test_semantic_router_telemetry.py tests/services/observability/test_observer_snapshot.py tests/runtime/test_orchestrator_autoroute.py tests/tutorbot/test_agent_loop_question_lifecycle.py tests/tutorbot/test_agent_loop_case_rubric_v1.py::test_prefetched_rag_satisfied_suppresses_first_loop_rag_but_keeps_web_search tests/core/test_capabilities_runtime.py::test_tutorbot_process_direct_prefetches_grounded_rag_for_current_info_query tests/core/test_capabilities_runtime.py::test_tutorbot_agent_loop_only_suppresses_rag_after_successful_prefetch tests/core/test_capabilities_runtime.py::test_tutorbot_full_process_direct_suppresses_stream_when_degraded_answer_guard_applies tests/core/test_capabilities_runtime.py::test_tutorbot_agent_loop_honors_mode_policy_max_tool_rounds tests/core/test_capabilities_runtime.py::test_tutorbot_agent_loop_disables_further_rag_after_high_overlap_saturation tests/core/test_capabilities_runtime.py::test_tutorbot_process_direct_prefetches_web_search_when_user_enabled_tool -q
```

Result: `169 passed, 5 warnings`.

```bash
python -m ruff check deeptutor/tutorbot/agent/loop.py tests/core/test_capabilities_runtime.py tests/tutorbot/test_agent_loop_case_rubric_v1.py deeptutor/runtime/orchestrator.py tests/runtime/test_orchestrator_autoroute.py
```

Result: `All checks passed`.

```bash
python scripts/check_contract_guard.py deeptutor/services/session/turn_runtime.py deeptutor/api/routers/unified_ws.py deeptutor/services/semantic_router_telemetry.py deeptutor/services/observability/observer_snapshot.py deeptutor/runtime/orchestrator.py deeptutor/tutorbot/agent/loop.py contracts/turn.md contracts/capability.md tests/services/observability/test_turn_runtime_observer_event.py tests/services/test_semantic_router_telemetry.py tests/services/observability/test_observer_snapshot.py tests/api/test_unified_ws_turn_runtime.py tests/api/test_unified_ws_public_redaction.py tests/runtime/test_orchestrator_autoroute.py tests/core/test_capabilities_runtime.py tests/tutorbot/test_agent_loop_case_rubric_v1.py
```

Result: `contract-guard: passed`; turn, capability, and luban_grading_engine domains passed.

## Remaining Risk

This branch now includes one concrete deep-mode latency reduction and one concrete orchestrator authority reduction, but it still does not prove production p95 improvement. The next evidence step is to run real fast/deep slow turns on the same SHA, classify `latency_max_stall`, and compare:

- deep successful RAG prefetch turns before/after first-loop `rag` suppression;
- preselected practice-generation turns before/after canonical decision schema;
- any slow turns where pre-turn memory consolidation is the max stall.
