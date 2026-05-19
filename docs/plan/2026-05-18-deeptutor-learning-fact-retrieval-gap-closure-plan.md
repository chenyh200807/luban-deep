# DeepTutor Learning Fact Retrieval Gap Closure Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining delivery gaps for the learning-fact retrieval PRD without creating a second RAG, chat route, memory writer, or graph database.

**Architecture:** Keep `RAGService` and `SupabasePipeline` as the only online retrieval path. Add graph-aware compiled truth materialization, runtime context propagation, offline maintenance reporting, and live-gate scripts around the existing path; keep Phase D final-source enablement behind explicit flags until public WS and Langfuse evidence prove exact authority is unaffected.

**Tech Stack:** Python, FastAPI/TutorBot runtime, Supabase RAG, learner-state compiled projection, Langfuse/ClickHouse observability, pytest, Aliyun `/root/deeptutor` deploy scripts.

---

## 1. Scope And Authority

This plan closes gaps in [2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md).

Hard boundaries:

1. Do not add a new RAG provider, vector store, graph DB, or chat WebSocket.
2. `LearnerStateService` / synthesis remains the only writer of compiled learning truth.
3. `SupabasePipeline` may only consume caller-passed `compiled_learning_truth`.
4. `compiled_learning_truth` remains shadow-only by default.
5. Production enablement of final compiled truth sources requires live public WS and Langfuse evidence.

## 2. Current Gap Ledger

| Gap | Status before this plan | Closure target |
| --- | --- | --- |
| Live gate | Missing direct RAG, public `/api/v1/ws`, Langfuse/ClickHouse evidence | Add repeatable local/remote commands and run when deployable. |
| Phase D production validation | Code flag exists, live proof missing | Add focused tests and live script for weak-point vs exact authority pair. |
| Graph expansion | Learner-state graph exists, RAG does not use it | Materialize weak-point graph context into compiled truth retrieval docs. |
| TutorBot runtime propagation | `deep_question` consumes compiled truth, RAG tool propagation uncertain | Pass runtime `compiled_learning_truth` into `rag` tool calls and prefetch/fast paths. |
| Maintenance workflow | Basic audit helper only | Add dry-run report CLI covering retrieval miss, citation, stale weak point, rubric coverage, eval case generation. |
| Contract guard | RAG green, mobile turn/capability guard red due dirty `mobile.py` | Update relevant contract surfaces only if the changed mobile API surface is intentional. |
| Plan status | Child plan still `Proposed / Expert reviewed` | Update to partial/active closure status only after local gates; do not mark Done until live gates pass. |

## 3. Tasks

### Task 1: Graph-Aware Compiled Truth Materialization

**Files:**
- Modify: `deeptutor/services/rag/compiled_truth_source.py`
- Test: `tests/services/rag/test_compiled_truth_source.py`
- Test: `tests/services/rag/test_learning_fact_retrieval_pipeline.py`

- [x] Add weak-point retrieval docs from `projection.weak_points`.
- [x] Include compact graph context from `projection.typed_graph.edges`: `question -> concept -> rubric_item -> error -> next_training`.
- [x] Exclude stale/superseded/low-evidence weak points.
- [x] Verify compiled truth still cannot outrank exact-question authority.

### Task 2: Runtime Propagation Into RAG Tool Calls

**Files:**
- Modify: `deeptutor/services/learner_state/service.py`
- Modify: `deeptutor/services/session/turn_runtime.py`
- Modify: `deeptutor/tutorbot/agent/tools/deeptutor_tools.py`
- Modify: `deeptutor/tutorbot/agent/loop.py`
- Test: `tests/agents/chat/test_agentic_parallel_tools.py` or focused TutorBot tool tests.

- [x] Persist offline `COMPILED_TRUTH.json` as local/dev cache from learner-state synthesis when `dry_run=False`; production durable truth is `learner_summaries.summary_structured_json.learning_brain`.
- [x] Have turn runtime read this compiled projection and attach it to `UnifiedContext.metadata`.
- [x] Pass `runtime_context.compiled_learning_truth` to `rag_search(...)`.
- [x] Attach compact `routing_metadata.compiled_learning_truth_available` marker for trace compatibility.
- [x] Ensure prefetch/exact-fast-path preview args carry the same projection.
- [x] Do not let wrapper code synthesize or mutate learner truth.

### Task 3: Maintenance Dry-Run Workflow

**Files:**
- Modify: `deeptutor/services/rag/maintenance.py`
- Create: `scripts/run_learning_fact_retrieval_maintenance.py`
- Test: `tests/services/rag/test_maintenance.py`
- Test: `tests/scripts/test_run_learning_retrieval_maintenance.py`

- [x] Produce dry-run report sections: retrieval misses, citation gaps, stale weak points, rubric coverage gaps, eval cases.
- [x] Accept JSON input from a file or stdin.
- [x] Never write learner-state or Supabase rows.

### Task 4: Contract And Plan State

**Files:**
- Modify: `contracts/rag.md`
- Modify only if needed: `contracts/turn.md`, `contracts/capability.md`
- Modify: `docs/plan/INDEX.md`

- [x] Keep RAG contract aligned with graph context and runtime propagation.
- [x] If mobile learning-brain projection API remains in this branch, document the intentional turn/capability surface so contract guard is not red.
- [x] Mark the child plan as local Phase A-D implementation in progress, not Done.

### Task 5: Local Verification Gate

**Commands:**

```bash
pytest tests/services/rag/test_retrieval_plan.py tests/services/rag/test_compiled_truth_source.py tests/services/rag/test_provenance.py tests/services/rag/test_learning_fact_retrieval_pipeline.py tests/services/rag/test_rag_pipelines.py tests/services/rag/test_maintenance.py -q
pytest tests/agents/chat/test_agentic_parallel_tools.py -q
pytest tests/scripts/test_run_learning_fact_retrieval_maintenance.py -q
python scripts/check_contract_guard.py
```

Expected:

- RAG and maintenance tests pass.
- Contract guard has no RAG failure. Full guard may pass only after intentional mobile surface is documented.

Status:

- [x] Local targeted gate passed: `tests/agents/chat/test_chat_agent_retrieval.py`, fast chat propagation, RAG final-source tests, `scripts/check_contract_guard.py`, `git diff --check`.
- [x] Broader local slice passed: 364 relevant RAG / learner-state / mobile / WS runtime / TutorBot propagation / maintenance tests.

### Task 6: Live Gate

**Files / Commands:**
- Use existing Aliyun scripts only with remote write root `/root/deeptutor`.
- Add or use a script that can run:
  - direct RAG smoke
  - public `/api/v1/ws` weak-point smoke
  - public `/api/v1/ws` exact-question smoke
  - ClickHouse query for `retrieval_plan` and `ranking_trace`

- [x] Run direct RAG against deployed code.
- [x] Run public weak-point WS with Phase D flag enabled only in controlled deploy.
- [x] Run public exact-question WS and confirm exact authority remains first.
- [x] Query Langfuse/ClickHouse fresh trace metadata.
- [x] Record trace ids and exact source behavior before marking Done.

Live evidence recorded on 2026-05-18:

- Direct RAG weak-point query: `intent=weak_point_review`, `compiled_truth_final_enabled=true`, final source included `compiled-truth:weak-point:1A432000:E02`.
- Direct RAG exact query: `intent=exact_question`, `exact_chunk_id=question-15165`, `compiled_truth_final_enabled=false`.
- Public WS weak-point query: session `live-gate-weak-5554f3f0`, Langfuse / ClickHouse trace `d6b4770d012b65592cfdfc5087a5d7bf`, observation `f64153139de84e88`, `compiled_learning_truth` source group enabled with reason `weak_point_review`, `compiled_truth_final_enabled=true`.
- Public WS exact query: session `live-gate-exact-5554f3f0`, Langfuse / ClickHouse trace `c82f85015ffa8c112273438459a0ae9c`, observation `00fab4801d7dcf77`, `intent=exact_question`, `compiled_learning_truth` source group disabled, `compiled_truth_final_enabled=false`.
- The Phase D production flag was enabled only during the controlled live-gate window and restored afterward; public `/healthz` and `/readyz` passed after restoration.

## 4. Acceptance Criteria

This gap closure is complete only when:

1. Local tests prove graph-aware compiled truth docs, shadow behavior, and exact authority.
2. RAG tool calls receive caller-passed compiled truth from runtime context.
3. Maintenance dry-run produces all required sections without writes.
4. Contract guard is green or any remaining red domain is explicitly unrelated and documented.
5. Direct RAG, public `/api/v1/ws`, and Langfuse/ClickHouse evidence are recorded.
6. `docs/plan/INDEX.md` status reflects the real state: partial/local complete until live gates pass.
