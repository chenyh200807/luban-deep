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

- [ ] Add weak-point retrieval docs from `projection.weak_points`.
- [ ] Include compact graph context from `projection.typed_graph.edges`: `question -> concept -> rubric_item -> error -> next_training`.
- [ ] Exclude stale/superseded/low-evidence weak points.
- [ ] Verify compiled truth still cannot outrank exact-question authority.

### Task 2: Runtime Propagation Into RAG Tool Calls

**Files:**
- Modify: `deeptutor/tutorbot/agent/tools/deeptutor_tools.py`
- Modify: `deeptutor/tutorbot/agent/loop.py`
- Test: `tests/agents/chat/test_agentic_parallel_tools.py` or focused TutorBot tool tests.

- [ ] Pass `runtime_context.compiled_learning_truth` to `rag_search(...)`.
- [ ] Also attach it to `routing_metadata.compiled_learning_truth` for fallback compatibility.
- [ ] Ensure prefetch/exact-fast-path preview args carry the same projection.
- [ ] Do not let wrapper code synthesize or mutate learner truth.

### Task 3: Maintenance Dry-Run Workflow

**Files:**
- Modify: `deeptutor/services/rag/maintenance.py`
- Create: `scripts/run_learning_retrieval_maintenance.py`
- Test: `tests/services/rag/test_maintenance.py`
- Test: `tests/scripts/test_run_learning_retrieval_maintenance.py`

- [ ] Produce dry-run report sections: retrieval misses, citation gaps, stale weak points, rubric coverage gaps, eval cases.
- [ ] Accept JSON input from a file or stdin.
- [ ] Never write learner-state or Supabase rows.

### Task 4: Contract And Plan State

**Files:**
- Modify: `contracts/rag.md`
- Modify only if needed: `contracts/turn.md`, `contracts/capability.md`
- Modify: `docs/plan/INDEX.md`

- [ ] Keep RAG contract aligned with graph context and runtime propagation.
- [ ] If mobile learning-brain projection API remains in this branch, document the intentional turn/capability surface so contract guard is not red.
- [ ] Mark the child plan as local Phase A-D implementation in progress, not Done.

### Task 5: Local Verification Gate

**Commands:**

```bash
pytest tests/services/rag/test_retrieval_plan.py tests/services/rag/test_compiled_truth_source.py tests/services/rag/test_provenance.py tests/services/rag/test_learning_fact_retrieval_pipeline.py tests/services/rag/test_rag_pipelines.py tests/services/rag/test_maintenance.py -q
pytest tests/agents/chat/test_agentic_parallel_tools.py -q
pytest tests/scripts/test_run_learning_retrieval_maintenance.py -q
python scripts/check_contract_guard.py
```

Expected:

- RAG and maintenance tests pass.
- Contract guard has no RAG failure. Full guard may pass only after intentional mobile surface is documented.

### Task 6: Live Gate

**Files / Commands:**
- Use existing Aliyun scripts only with remote write root `/root/deeptutor`.
- Add or use a script that can run:
  - direct RAG smoke
  - public `/api/v1/ws` weak-point smoke
  - public `/api/v1/ws` exact-question smoke
  - ClickHouse query for `retrieval_plan` and `ranking_trace`

- [ ] Run direct RAG against deployed code.
- [ ] Run public weak-point WS with Phase D flag enabled only in controlled deploy.
- [ ] Run public exact-question WS and confirm exact authority remains first.
- [ ] Query Langfuse/ClickHouse fresh trace metadata.
- [ ] Record trace ids and exact source behavior before marking Done.

## 4. Acceptance Criteria

This gap closure is complete only when:

1. Local tests prove graph-aware compiled truth docs, shadow behavior, and exact authority.
2. RAG tool calls receive caller-passed compiled truth from runtime context.
3. Maintenance dry-run produces all required sections without writes.
4. Contract guard is green or any remaining red domain is explicitly unrelated and documented.
5. Direct RAG, public `/api/v1/ws`, and Langfuse/ClickHouse evidence are recorded.
6. `docs/plan/INDEX.md` status reflects the real state: partial/local complete until live gates pass.
