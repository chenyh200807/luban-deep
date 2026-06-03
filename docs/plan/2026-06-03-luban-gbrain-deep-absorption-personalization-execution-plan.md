# GBrain Deep Absorption Personalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Learning Brain from "compiled learning facts" into a production personalization engine that can decide, explain, and verify each learner's next best action.

**Architecture:** Do not import `garrytan/gbrain` as a runtime dependency. Translate GBrain's brain-first lookup, compiled truth + timeline, typed graph, dream cycle, operational disciplines, system-of-record discipline, and eval gates into DeepTutor's existing authorities: `LearnerStateService`, `learning_synthesis`, `RAGService`, `training_intent`, `learning-report-read-model`, and `/api/v1/ws`. Wrappers stay thin; the fat authority is the learner-state / learning-brain service layer.

**Tech Stack:** Python dataclasses and pure functions, existing learner-state JSON projection, existing Supabase learner summaries, existing RAG compiled truth source group, pytest, existing mobile learning-report route, existing `/wechat-harness` / yosen mini-program QA path, Langfuse / ClickHouse trace sampling for production observation.

---

## 0. Source Audit

This plan is grounded in `garrytan/gbrain` at commit `f09f9177a965122ab8e8f7ba8478c0c9756c6237`.

Primary source concepts absorbed:

| GBrain concept | Source | DeepTutor translation |
| --- | --- | --- |
| Search returns pages; brain returns synthesized answer with citations and gap analysis | `README.md` | Learning report and TutorBot must answer "what should this learner do next, why, and what is missing." |
| Brain-first lookup before external APIs | `docs/guides/brain-first-lookup.md` | Read compiled learner truth before generic RAG, topic generation, or study advice. |
| Compiled truth + immutable timeline | `docs/guides/compiled-truth.md` | Rewrite current learner claim projection; append evidence events only. |
| Operational disciplines | `docs/guides/operational-disciplines.md` | Capture learning signals every turn, run heartbeat, run nightly dream cycle. |
| System of record | `docs/architecture/system-of-record.md` | `learner_memory_events.learning_evidence` is the event ledger; derived projections must be rebuildable. |
| Eval gate | `docs/eval-bench.md` | Personalization changes need regression and correctness gates, not screenshots only. |

## 1. Current Status

We have learned the first half of GBrain:

1. `learner_memory_events` can hold learning evidence.
2. `deeptutor/services/learner_state/learning_synthesis.py` can create `learning_brain` compiled projection.
3. Compiled truth can enter RAG as `compiled_learning_truth` source group.
4. `learning-report-read-model` exposes learning brain evidence and next training.
5. `deep_question` can consume `learning_training_intent`.

We have not fully learned the second half:

1. No single `PersonalizationContextPack` is used before every personalized answer.
2. Claim lifecycle exists in pieces, but it is not yet a hard cross-surface contract.
3. Typed graph is still mostly projection, not a next-best-action query engine.
4. Nightly dream cycle is not a production operational discipline.
5. Eval gates measure retrieval and grading better than personalization quality.
6. User-facing workspace does not yet make the learning brain visible as a trustworthy "why this now" system.

## 2. Karpathy Gate

### assumptions

- The goal is not "install GBrain" or "copy GBrain's generic personal brain."
- The goal is to make DeepTutor dramatically better at personalization for construction exam learners.
- Current production flag work for compiled truth is necessary but insufficient; this plan is the next architecture step.
- The plan must stay inside existing DeepTutor authorities and avoid a second memory, second RAG, second homepage reader, or second chat route.

### simplest path

The shortest path is:

1. Harden learner claim lifecycle inside `deeptutor/services/learner_state/learning_synthesis.py`.
2. Add a pure `PersonalizationContextPack` builder that reads compiled truth, evidence timeline, active training intent, and graph hints.
3. Use that pack in learning report, TutorBot, `deep_question`, and RAG metadata.
4. Add a next-best-action helper over existing typed graph and `training_intent`.
5. Add dream-cycle lint and eval gates before expanding UI.

### change boundary

Allowed in implementation:

- `deeptutor/services/learner_state/*`
- `deeptutor/services/rag/*`
- `deeptutor/api/routers/mobile.py`
- `deeptutor/capabilities/deep_question.py`
- `deeptutor/tutorbot/agent/loop.py`
- `deeptutor/tutorbot/skills/construction-study-assistant/SKILL.md`
- focused tests under `tests/services/learner_state`, `tests/services/rag`, `tests/api`, `tests/core`
- docs / scripts directly tied to Learning Brain dream-cycle and eval gates

Not allowed in this plan:

- New `/api/v1/mobile/tutorbot/ws/...` or any second chat route.
- A standalone `gbrain` runtime service.
- A second vector DB or second RAG provider.
- A new learner profile table unless a later scale gate proves JSON projection cannot serve.
- Notebook cards directly mutating mastery, weak points, or compiled truth.
- Frontend sorting becoming recommendation authority.

### verification target

For a sampled learner, the system must answer:

1. What do we believe about this learner?
2. Which evidence proves it?
3. What changed recently?
4. What should they do next?
5. Why this action now?
6. How will we know it worked?

If any answer is missing, the GBrain absorption is incomplete.

## 3. Authority Map

| Business fact | One authority | Readers | Must not happen |
| --- | --- | --- | --- |
| Raw learning evidence | `learner_memory_events.memory_kind=learning_evidence` | `learning_synthesis`, attempt detail, learning report | Free-form chat summary writes stable truth. |
| Current learner claim | `learning_synthesis.py` projection under `summary_structured_json.learning_brain` | RAG, report, TutorBot, next action | Mobile / TutorBot re-computes claim status. |
| Next training prescription | `training_intent.py` | learning report, deep_question, workspace | Study plan or frontend computes competing prescription. |
| Personalized context | new `personalization_context.py` pure builder | report, TutorBot, deep_question, RAG metadata | Each caller hand-rolls its own learner context. |
| Retrieval grounding | `RAGService` / `SupabasePipeline` | TutorBot, chat, deep_question | Direct `kb_chunks` or learner-state lookup in wrappers. |
| User notes | Notebook card service | workspace, recall as low-weight subjective signal | Notebook card becomes mastery or weak-point truth. |

## 4. File Structure

Create:

- `deeptutor/services/learner_state/personalization_context.py`
  - Pure builder for `PersonalizationContextPack`.
  - No storage reads; accepts projections and intents passed by caller.
- `deeptutor/services/learner_state/next_best_action.py`
  - Pure ranking over claim lifecycle, typed graph, evidence recency, and `training_intent`.
- `deeptutor/services/learner_state/learning_brain_lint.py`
  - Dream-cycle checks: unsupported claim, stale claim, contradiction, missing retest, graph gap.
- `scripts/run_learning_brain_dream_cycle.py`
  - Dry-run first; later production cron wrapper.
- `tests/services/learner_state/test_personalization_context.py`
- `tests/services/learner_state/test_next_best_action.py`
- `tests/services/learner_state/test_learning_brain_lint.py`
- `tests/scripts/test_run_learning_brain_dream_cycle.py`
- `tests/fixtures/learning_brain_personalization_cases.json`

Modify:

- `deeptutor/services/learner_state/learning_synthesis.py`
  - Make claim lifecycle explicit and stable.
- `deeptutor/services/learner_state/learning_report_read_model.py`
  - Surface `personalization_context` and evidence-backed `next_best_actions`.
- `deeptutor/services/learner_state/training_intent.py`
  - Preserve current authority; add optional evidence-chain fields only if missing.
- `deeptutor/services/rag/retrieval_plan.py`
  - Add `personalization_context_available` to intent planning.
- `deeptutor/services/rag/compiled_truth_source.py`
  - Include lifecycle status and evidence refs in materialized docs.
- `deeptutor/services/rag/maintenance.py`
  - Add learning-brain personalization audit checks.
- `contracts/learner-state.md`
  - Define claim lifecycle and `PersonalizationContextPack` as learner-state projections.
- `contracts/learning-report.md`
  - Define `personalization_context`, `next_best_actions`, and `today_prescription` as learning-report v2 fields.
- `contracts/rag.md`
  - Define how personalization context may influence compiled truth retrieval without becoming RAG authority.
- `contracts/index.yaml`
  - Register the contract surfaces and tests for this plan.
- `deeptutor/api/routers/mobile.py`
  - Preserve `/mobile/learning-report`; do not add a second homepage reader.
- `deeptutor/capabilities/deep_question.py`
  - Consume `PersonalizationContextPack` only as context; do not compute learner truth.
- `deeptutor/tutorbot/agent/loop.py`
  - Pass personalization context into RAG preview args and session metadata.
- `deeptutor/tutorbot/skills/construction-study-assistant/SKILL.md`
  - Require evidence-backed advice and no local learner-state writes.
- `docs/plan/INDEX.md`
  - Register this plan under Learning Brain.

## 5. Implementation Tasks

### Task 0: Baseline and Mapping Gate

**Files:**

- Modify: `docs/plan/2026-05-18-luban-learning-brain-gbrain-absorption-prd.md`
- Modify: `docs/plan/2026-05-26-luban-learner-workspace-notebook-calendar-prd.md`
- Modify: `docs/plan/INDEX.md`
- Modify: `contracts/learner-state.md`
- Modify: `contracts/learning-report.md`
- Modify: `contracts/rag.md`
- Modify: `contracts/index.yaml`

- [ ] **Step 0.1: Record the source mapping**

Add a short appendix to the existing PRD with this table:

```markdown
| GBrain discipline | DeepTutor current state | Gap | Target task |
| --- | --- | --- | --- |
| Brain-first lookup | Compiled truth can enter RAG | Not shared across report/TutorBot/deep_question | Task 2 |
| Claim lifecycle | L0/L1/L2/stale exists in synthesis tests | Not a cross-surface contract | Task 1 |
| Typed graph | Projection exists | Not used for next-best-action ranking | Task 3 |
| Dream cycle | Maintenance helpers exist for RAG | No learner-brain nightly lint | Task 5 |
| Eval gate | Retrieval/grading gates exist | No personalization correctness gate | Task 6 |
```

- [ ] **Step 0.2: Run doc index check**

Run:

```bash
rg -n "gbrain-deep-absorption|GBrain Deep Absorption|PersonalizationContextPack" docs/plan
```

Expected:

```text
docs/plan/INDEX.md contains this plan
docs/plan/2026-06-03-luban-gbrain-deep-absorption-personalization-execution-plan.md contains the execution plan
```

- [ ] **Step 0.3: Verify contract documents exist**

Run:

```bash
test -f contracts/learner-state.md
test -f contracts/learning-report.md
test -f contracts/rag.md
test -f contracts/index.yaml
```

Expected:

```text
all commands exit 0
```

### Task 0.5: Contract-First Schema Gate

**Files:**

- Modify: `contracts/learner-state.md`
- Modify: `contracts/learning-report.md`
- Modify: `contracts/rag.md`
- Modify: `contracts/index.yaml`
- Test: `tests/services/learner_state/test_learning_synthesis.py`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`
- Test: `tests/services/rag/test_retrieval_plan.py`
- Test: `tests/api/test_mobile_router.py`

- [ ] **Step 0.5.1: Add learner-state contract text before implementation**

Add this contract language to `contracts/learner-state.md` under the Learning Brain section:

```markdown
### Claim lifecycle and personalization context

`summary_structured_json.learning_brain` may expose stable claim lifecycle
fields only when they are produced by `learning_synthesis.py`.

Allowed claim statuses:

- `observed`: single eligible learning evidence, not stable truth.
- `repeated`: repeated eligible evidence for the same `(concept_id, error_code)`.
- `confirmed`: teacher/manual confirmation or equivalent trusted review.
- `stale`: later evidence indicates the claim needs retest or decay.
- `superseded`: a later correction replaces the old claim.
- `rejected`: a teacher/manual correction rejects the claim.
- `contradicted`: evidence conflicts and synthesis must not silently resolve it.

Every stable claim exposed to product surfaces must carry non-empty
`evidence_refs` or `supporting_event_ids`. Online wrappers, mobile routers,
TutorBot runtime, RAG, notebook services, and frontend surfaces must not
compute claim lifecycle status.

`PersonalizationContextPack` is a read-only projection over existing
learner-state truth, `training_intent`, and recent evidence. It is not a
writer, not a learner profile table, and not a recommendation authority.
```

- [ ] **Step 0.5.2: Add learning-report v2 contract text**

Add this contract language to `contracts/learning-report.md` under schema v2:

```markdown
### Personalization fields

`personalization_context` is optional in v1 and allowed in v2. When present,
it must be copied from learner-state read-model helpers and must include:

- `schema_version`
- `source`
- `top_claims`
- `recent_evidence_refs`
- `active_training_intent`
- `next_best_action_candidates`
- `gaps`
- `authority`

`next_best_actions` and `today_prescription` may only be derived from
`training_intent`, `learning_synthesis` claim lifecycle, and typed graph
evidence. They must expose `why_this_now` and `evidence_refs` for any
non-starter action. A learner with no evidence must receive a starter action,
not fake personalization.
```

- [ ] **Step 0.5.3: Add RAG contract text**

Add this contract language to `contracts/rag.md`:

```markdown
`PersonalizationContextPack` may be passed to `RAGService.search(...)` as
read-only request metadata. RAG may use it to enable or explain the existing
`compiled_learning_truth` source group, but RAG must not write learner-state,
compute claim lifecycle, or let compiled truth override exact question,
standard, textbook, or hidden grading authority.
```

- [ ] **Step 0.5.4: Register contract files in index**

Update `contracts/index.yaml` so the Learning Brain / learning-report / RAG surfaces list:

```yaml
contracts:
  - contracts/learner-state.md
  - contracts/learning-report.md
  - contracts/rag.md
tests:
  - tests/services/learner_state/test_learning_synthesis.py
  - tests/services/learner_state/test_learning_report_read_model.py
  - tests/services/rag/test_retrieval_plan.py
  - tests/api/test_mobile_router.py
```

- [ ] **Step 0.5.5: Verify contract terms are discoverable**

Run:

```bash
rg -n "Claim lifecycle|PersonalizationContextPack|today_prescription|compiled truth override" \
  contracts/learner-state.md contracts/learning-report.md contracts/rag.md contracts/index.yaml
```

Expected:

```text
all four contract files mention the new stable boundary
```

### Task 1: Claim Lifecycle Contract

**Files:**

- Modify: `deeptutor/services/learner_state/learning_synthesis.py`
- Modify: `deeptutor/services/learner_state/learning_brain_read_model.py`
- Test: `tests/services/learner_state/test_learning_synthesis.py`
- Test: `tests/services/learner_state/test_learning_brain_read_model.py`

- [ ] **Step 1.1: Add failing lifecycle tests**

Add tests covering these exact states:

```python
def test_claim_lifecycle_statuses_are_stable_and_evidence_backed() -> None:
    projection = synthesize_learning_truth([
        _learning_event("evt_observed", concept_id="1A432000", error_code="E02"),
        _learning_event("evt_repeated", concept_id="1A432000", error_code="E02"),
        _manual_confirmation(concept_id="1A432000", error_code="E02"),
        _learning_event("evt_improved", concept_id="1A432000", error_code="E02", improved=True),
    ])

    claim = projection["compiled_objects"]["concept:1A432000"]
    assert claim["claim_status"] in {"confirmed", "stale"}
    assert claim["evidence_refs"]
    assert claim["lifecycle"]["last_event_id"] == "evt_improved"
    assert claim["lifecycle"]["status_reason"] in {"manual_confirmed", "later_training_improved"}
```

- [ ] **Step 1.2: Run test to verify it fails before implementation**

Run:

```bash
pytest tests/services/learner_state/test_learning_synthesis.py::test_claim_lifecycle_statuses_are_stable_and_evidence_backed -q
```

Expected:

```text
FAIL because claim_status or lifecycle is missing
```

- [ ] **Step 1.3: Implement lifecycle fields**

Add stable fields to every compiled object and weak point:

```python
{
    "claim_status": "observed" | "repeated" | "confirmed" | "stale" | "superseded" | "rejected" | "contradicted",
    "evidence_level": "L0_observed" | "L1_repeated" | "L2_confirmed" | "L3_mastery_signal",
    "evidence_refs": ["event:..."],
    "lifecycle": {
        "created_event_id": "...",
        "last_event_id": "...",
        "status_reason": "...",
        "needs_retest": true,
        "superseded_by": "",
    },
}
```

- [ ] **Step 1.4: Verify read model preserves lifecycle**

Run:

```bash
pytest \
  tests/services/learner_state/test_learning_synthesis.py \
  tests/services/learner_state/test_learning_brain_read_model.py \
  -q
```

Expected:

```text
all selected tests pass
```

### Task 2: PersonalizationContextPack

**Files:**

- Create: `deeptutor/services/learner_state/personalization_context.py`
- Test: `tests/services/learner_state/test_personalization_context.py`
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`

- [ ] **Step 2.1: Write failing context builder tests**

Create `tests/services/learner_state/test_personalization_context.py`:

```python
from deeptutor.services.learner_state.personalization_context import build_personalization_context_pack


def test_context_pack_prioritizes_confirmed_and_recent_claims() -> None:
    pack = build_personalization_context_pack(
        user_id="u1",
        learning_brain={
            "weak_points": [
                {
                    "concept_id": "1A432000",
                    "concept_label": "危大工程专项方案",
                    "error_code": "E02",
                    "claim_status": "confirmed",
                    "evidence_level": "L2_confirmed",
                    "evidence_refs": ["event:e1", "event:e2"],
                }
            ],
            "stale_claims": [
                {"concept_id": "1A412000", "claim_status": "stale", "evidence_refs": ["event:old"]}
            ],
        },
        active_training_intent={
            "training_intent_id": "lti_1",
            "concept_id": "1A432000",
            "error_code": "E02",
            "evidence_refs": ["event:e2"],
        },
        recent_events=[{"event_id": "e2", "created_at": "2026-06-03T08:00:00Z"}],
    )

    assert pack["schema_version"] == 1
    assert pack["user_id"] == "u1"
    assert pack["top_claims"][0]["concept_id"] == "1A432000"
    assert pack["top_claims"][0]["why_now"] == "confirmed_active_training_intent"
    assert pack["gaps"][0]["code"] == "stale_claim_needs_retest"
```

- [ ] **Step 2.2: Run test to verify it fails**

Run:

```bash
pytest tests/services/learner_state/test_personalization_context.py -q
```

Expected:

```text
ModuleNotFoundError for personalization_context
```

- [ ] **Step 2.3: Implement the pure builder**

The builder must:

1. Accept already-loaded projections and events.
2. Never read storage.
3. Never call LLM.
4. Return deterministic JSON.
5. Rank by claim status, evidence level, recency, and active training intent match.

Required output shape:

```python
{
    "schema_version": 1,
    "user_id": "u1",
    "source": "learning_brain",
    "top_claims": [],
    "recent_evidence_refs": [],
    "active_training_intent": {},
    "next_best_action_candidates": [],
    "gaps": [],
    "authority": {
        "claims": "learning_synthesis",
        "next_training": "training_intent",
        "retrieval": "RAGService",
    },
}
```

- [ ] **Step 2.4: Surface context in learning report**

Add `personalization_context` to the existing `/mobile/learning-report` read model. Do not add a new endpoint.

Run:

```bash
pytest \
  tests/services/learner_state/test_personalization_context.py \
  tests/services/learner_state/test_learning_report_read_model.py \
  tests/api/test_mobile_router.py::test_mobile_learning_report_dual_emits_v2_without_breaking_v1_fields \
  -q
```

Expected:

```text
all selected tests pass and v1 fields remain present
```

### Task 3: Next Best Action Over Typed Graph

**Files:**

- Create: `deeptutor/services/learner_state/next_best_action.py`
- Test: `tests/services/learner_state/test_next_best_action.py`
- Modify: `deeptutor/services/learner_state/training_intent.py`
- Modify: `deeptutor/services/learner_state/scoring_point_map_read_model.py`

- [ ] **Step 3.1: Write failing next-action tests**

Create `tests/services/learner_state/test_next_best_action.py`:

```python
from deeptutor.services.learner_state.next_best_action import get_next_best_actions


def test_next_best_action_requires_evidence_chain() -> None:
    actions = get_next_best_actions(
        personalization_context={
            "top_claims": [
                {
                    "concept_id": "1A432000",
                    "concept_label": "危大工程专项方案",
                    "error_code": "E02",
                    "claim_status": "confirmed",
                    "evidence_refs": ["event:e1", "attempt:a1"],
                }
            ],
            "active_training_intent": {"training_intent_id": "lti_1"},
        },
        typed_graph={
            "edges": [
                {"edge_type": "evidence_for", "from": "attempt:a1", "to": "claim:1A432000:E02"},
                {"edge_type": "recommended_next", "from": "claim:1A432000:E02", "to": "training:retest"},
            ]
        },
        max_actions=2,
    )

    assert actions[0]["action_type"] == "retest_training"
    assert actions[0]["evidence_refs"] == ["event:e1", "attempt:a1"]
    assert actions[0]["explain"]["why_this_now"]
```

- [ ] **Step 3.2: Implement deterministic ranking**

Ranking order:

1. `confirmed` or `repeated` claim with active `training_intent`.
2. Stale claim that needs retest.
3. Repeated weak point without active training.
4. User subjective focus with supporting evidence.
5. Starter action only when no evidence exists.

- [ ] **Step 3.3: Verify no competing prescription authority**

Run:

```bash
pytest \
  tests/services/learner_state/test_next_best_action.py \
  tests/services/learner_state/test_training_intent.py \
  tests/services/learner_state/test_study_plan_reads_training_intent.py \
  -q
```

Expected:

```text
all selected tests pass; study_plan still reads training_intent as prescription authority
```

### Task 4: Runtime Consumption Without Wrapper Drift

**Files:**

- Modify: `deeptutor/capabilities/deep_question.py`
- Modify: `deeptutor/tutorbot/agent/loop.py`
- Modify: `deeptutor/services/rag/retrieval_plan.py`
- Modify: `deeptutor/services/rag/compiled_truth_source.py`
- Modify: `deeptutor/tutorbot/skills/construction-study-assistant/SKILL.md`
- Test: `tests/core/test_deep_question_submission_grading.py`
- Test: `tests/core/test_capabilities_runtime.py`
- Test: `tests/services/rag/test_retrieval_plan.py`
- Test: `tests/services/rag/test_compiled_truth_source.py`

- [ ] **Step 4.1: Add tests that runtime only consumes context**

Add runtime spy tests that patch learner-state writers and prove wrappers only forward context:

```python
from typing import Any

import pytest


def test_rag_prefetch_preview_args_forward_personalization_context_without_writing_learner_state(monkeypatch) -> None:
    from deeptutor.tutorbot.agent.loop import AgentLoop

    record_calls: list[dict] = []
    synthesize_calls: list[dict] = []

    def fake_record_memory_event(*args, **kwargs):
        record_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("RAG preview must not write learner-state truth")

    def fake_synthesize_learning_truth(*args, **kwargs):
        synthesize_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("RAG preview must not compute claim lifecycle")

    monkeypatch.setattr(
        "deeptutor.services.learner_state.service.LearnerStateService.record_memory_event",
        fake_record_memory_event,
        raising=False,
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.service.LearnerStateService.synthesize_learning_truth",
        fake_synthesize_learning_truth,
        raising=False,
    )

    personalization_context = {
        "authority": {"claims": "learning_synthesis", "next_training": "training_intent"},
        "top_claims": [{"concept_id": "1A432000", "evidence_refs": ["event:e1"]}],
    }
    preview = AgentLoop._build_rag_preview_args(
        "我老是案例题丢分怎么办",
        {
            "default_kb": "construction-exam",
            "personalization_context": personalization_context,
        },
    )

    assert preview["personalization_context"]["authority"]["claims"] == "learning_synthesis"
    assert preview["routing_metadata"]["personalization_context_available"] is True
    assert record_calls == []
    assert synthesize_calls == []


@pytest.mark.asyncio
async def test_rag_adapter_tool_forwards_personalization_context_without_writing_learner_state(monkeypatch) -> None:
    import importlib

    from deeptutor.tutorbot.agent.tools.deeptutor_tools import RAGAdapterTool

    captured: dict[str, Any] = {}
    record_calls: list[dict] = []

    def fake_record_memory_event(*args, **kwargs):
        record_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("RAG adapter must not write learner-state truth")

    monkeypatch.setattr(
        "deeptutor.services.learner_state.service.LearnerStateService.record_memory_event",
        fake_record_memory_event,
        raising=False,
    )

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"answer": "ok"}

    rag_tool = importlib.import_module("deeptutor.tools.rag_tool")
    monkeypatch.setattr(rag_tool, "rag_search", _fake_rag_search)

    personalization_context = {
        "authority": {"claims": "learning_synthesis", "next_training": "training_intent"},
        "top_claims": [{"concept_id": "1A432000", "evidence_refs": ["event:e1"]}],
    }
    tool = RAGAdapterTool()
    tool.set_runtime_context(
        metadata={
            "default_kb": "construction-exam",
            "personalization_context": personalization_context,
        }
    )

    result = await tool.execute(query="我老是案例题丢分怎么办")

    assert result == "ok"
    assert captured["personalization_context"] == personalization_context
    assert captured["routing_metadata"]["personalization_context_available"] is True
    assert record_calls == []


def test_deep_question_uses_personalization_context_without_writing_learner_state(monkeypatch) -> None:
    from deeptutor.capabilities import deep_question as deep_question_module

    record_calls: list[dict] = []

    def fake_record_memory_event(*args, **kwargs):
        record_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("deep_question must not write learner-state truth from context")

    monkeypatch.setattr(
        "deeptutor.services.learner_state.service.LearnerStateService.record_memory_event",
        fake_record_memory_event,
        raising=False,
    )

    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再给我相关题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "q-case",
            "question_type": "case",
            "personalization_context": {
                "authority": {"claims": "learning_synthesis", "next_training": "training_intent"},
                "top_claims": [{"concept_id": "1A432000", "evidence_refs": ["event:e1"]}],
            },
        },
        conversation_context_text="",
    )

    assert "1A432000" in topic
    assert record_calls == []
```

These tests deliberately use the existing adjacent entry points:

```text
AgentLoop._build_rag_preview_args
RAGAdapterTool.execute
deep_question._resolve_generation_topic
```

Do not create production-only test helpers for this task.

- [ ] **Step 4.2: Pass context through existing routes**

Rules:

1. `deep_question` may use context to bias topic wording and question count.
2. TutorBot may pass context to RAG preview args and prompt metadata.
3. RAG may use context to select `compiled_learning_truth` source group.
4. None of these callers may write learner truth or decide claim lifecycle.

- [ ] **Step 4.3: Run runtime propagation tests**

Run:

```bash
pytest \
  tests/core/test_capabilities_runtime.py::test_rag_adapter_tool_forwards_compiled_learning_truth \
  tests/core/test_deep_question_submission_grading.py::test_related_generation_anchor_accepts_compiled_learning_truth_signal \
  tests/services/rag/test_retrieval_plan.py \
  tests/services/rag/test_compiled_truth_source.py \
  -q
```

Expected:

```text
all selected tests pass; exact question authority still outranks compiled truth
```

### Task 5: Nightly Dream Cycle and Doctor

**Files:**

- Create: `deeptutor/services/learner_state/learning_brain_lint.py`
- Create: `scripts/run_learning_brain_dream_cycle.py`
- Test: `tests/services/learner_state/test_learning_brain_lint.py`
- Test: `tests/scripts/test_run_learning_brain_dream_cycle.py`
- Modify: `deeptutor/services/rag/maintenance.py`

- [ ] **Step 5.1: Write lint tests**

Required issue codes:

```python
UNSUPPORTED_CLAIM = "unsupported_claim"
STALE_CLAIM_NEEDS_RETEST = "stale_claim_needs_retest"
CONTRADICTED_CLAIM = "contradicted_claim"
MISSING_NEXT_ACTION = "missing_next_action"
GRAPH_GAP = "graph_gap"
GENERIC_PERSONALIZATION = "generic_personalization"
```

Test:

```python
def test_learning_brain_lint_flags_unsupported_claim() -> None:
    issues = lint_learning_brain_projection({
        "weak_points": [{"concept_id": "1A432000", "claim": "掌握不稳", "evidence_refs": []}],
    })
    assert issues[0]["code"] == "unsupported_claim"
```

- [ ] **Step 5.2: Implement dry-run dream cycle**

Command:

```bash
python scripts/run_learning_brain_dream_cycle.py --user-id student_demo --dry-run --json
```

Expected JSON:

```json
{
  "status": "dry_run_ok",
  "users_scanned": 1,
  "issues": [],
  "would_refresh_compiled_truth": false
}
```

- [ ] **Step 5.3: Verify no writes in dry-run**

Run:

```bash
pytest \
  tests/services/learner_state/test_learning_brain_lint.py \
  tests/scripts/test_run_learning_brain_dream_cycle.py \
  tests/services/rag/test_maintenance.py \
  -q
```

Expected:

```text
all selected tests pass
```

### Task 6: Personalization Eval Gate

**Files:**

- Create: `tests/fixtures/learning_brain_personalization_cases.json`
- Create: `deeptutor/services/benchmark/learning_brain_personalization_eval.py`
- Test: `tests/services/benchmark/test_learning_brain_personalization_eval.py`
- Modify: `docs/plan/2026-05-18-luban-learning-brain-gbrain-absorption-prd.md`

- [ ] **Step 6.1: Add hermetic fixture**

Create `tests/fixtures/learning_brain_personalization_cases.json` with at least 10 cases.
The first two cases must establish the evidence/no-evidence split:

```json
{
  "schema_version": 1,
  "cases": [
    {
      "case_id": "lbp_001_confirmed_retest",
      "learner_id": "fixture_student_001",
      "learning_brain": {
        "weak_points": [
          {
            "concept_id": "1A432000",
            "concept_label": "危大工程专项方案",
            "error_code": "E02",
            "claim_status": "confirmed",
            "evidence_level": "L2_confirmed",
            "evidence_refs": ["event:e1", "attempt:a1"]
          }
        ],
        "typed_graph": {
          "edges": [
            {"edge_type": "evidence_for", "from": "attempt:a1", "to": "claim:1A432000:E02"},
            {"edge_type": "recommended_next", "from": "claim:1A432000:E02", "to": "training:retest"}
          ]
        }
      },
      "active_training_intent": {
        "training_intent_id": "lti_confirmed_001",
        "concept_id": "1A432000",
        "error_code": "E02",
        "evidence_refs": ["event:e1", "attempt:a1"]
      },
      "expected": {
        "must_reference_evidence": true,
        "forbidden_action_types": ["generic_encouragement"],
        "expected_action_type": "retest_training"
      }
    },
    {
      "case_id": "lbp_002_no_evidence_starter",
      "learner_id": "fixture_student_002",
      "learning_brain": {
        "weak_points": [],
        "typed_graph": {"edges": []}
      },
      "active_training_intent": {},
      "expected": {
        "must_reference_evidence": false,
        "forbidden_action_types": ["retest_training", "fake_personalized_review"],
        "expected_action_type": "starter_action"
      }
    }
  ]
}
```

Then add eight more cases using the same shape:

| Case id | Scenario | Required expected behavior |
| --- | --- | --- |
| `lbp_003_repeated_weak_point` | `claim_status=repeated`, L1 evidence, no active intent | recommend `targeted_practice`, include evidence refs |
| `lbp_004_stale_needs_retest` | stale claim with `needs_retest=true` | recommend `retest_training`, include stale reason |
| `lbp_005_contradicted_claim` | contradicted claim with conflicting evidence refs | do not recommend based on the contradicted claim; emit `review_needed` |
| `lbp_006_exact_question_conflict` | exact question authority conflicts with compiled truth | choose exact question / hidden grading authority, not compiled truth |
| `lbp_007_standard_authority_conflict` | standard/textbook authority conflicts with learner memory wording | choose standard/textbook authority, preserve learner evidence as context only |
| `lbp_008_notebook_subjective_focus` | notebook card says learner cares about a topic, with no learning evidence | allow low-priority `review_saved_note`, not mastery or weak-point action |
| `lbp_009_training_intent_absent` | repeated weak point exists but no active training intent | recommend `create_training_intent_candidate`, not frontend-only action |
| `lbp_010_improved_after_training` | previous weak point has later improvement signal | suppress weak-point action; recommend `maintenance_review` or no action |

Add a fixture test:

```python
import json
from pathlib import Path


def test_personalization_fixture_covers_required_case_matrix() -> None:
    fixture = json.loads(Path("tests/fixtures/learning_brain_personalization_cases.json").read_text())
    case_ids = {case["case_id"] for case in fixture["cases"]}

    assert {
        "lbp_001_confirmed_retest",
        "lbp_002_no_evidence_starter",
        "lbp_003_repeated_weak_point",
        "lbp_004_stale_needs_retest",
        "lbp_005_contradicted_claim",
        "lbp_006_exact_question_conflict",
        "lbp_007_standard_authority_conflict",
        "lbp_008_notebook_subjective_focus",
        "lbp_009_training_intent_absent",
        "lbp_010_improved_after_training",
    }.issubset(case_ids)


def test_no_evidence_case_does_not_require_evidence_backed_retest() -> None:
    fixture = json.loads(Path("tests/fixtures/learning_brain_personalization_cases.json").read_text())
    no_evidence = next(case for case in fixture["cases"] if case["case_id"] == "lbp_002_no_evidence_starter")

    assert no_evidence["learning_brain"]["weak_points"] == []
    assert no_evidence["expected"]["must_reference_evidence"] is False
    assert no_evidence["expected"]["expected_action_type"] == "starter_action"
    assert "retest_training" in no_evidence["expected"]["forbidden_action_types"]
```

- [ ] **Step 6.2: Implement deterministic evaluator**

Metrics:

```python
{
    "personalization_hit_rate": 0.0,
    "evidence_coverage": 0.0,
    "generic_fallback_rate": 0.0,
    "unsupported_claim_rate": 0.0,
    "stale_claim_rate": 0.0,
}
```

- [ ] **Step 6.3: Run eval gate**

Run:

```bash
python -m deeptutor.services.benchmark.learning_brain_personalization_eval \
  --fixture tests/fixtures/learning_brain_personalization_cases.json \
  --min-evidence-coverage 0.95 \
  --max-generic-fallback-rate 0.05
```

Expected:

```text
verdict=pass
```

### Task 7: Product Surface Slice

**Files:**

- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Modify: `deeptutor/api/routers/mobile.py`
- Modify: `wx_miniprogram/pages/report/report.js`
- Modify: `yousenwebview/packageDeeptutor/pages/report/report.js`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`
- Test: `tests/api/test_mobile_router.py`

- [ ] **Step 7.1: Add read model contract for "why this now"**

Learning report v2 must expose:

```json
{
  "today_prescription": {
    "title": "今天先复测危大工程专项方案",
    "why_this_now": "最近 2 次案例题都漏写专家论证程序，且已有复测队列。",
    "evidence_refs": ["event:e1", "attempt:a1"],
    "primary_action": {"type": "retest_training", "intent_id": "lti_1"}
  }
}
```

- [ ] **Step 7.2: Add mobile tests**

Run:

```bash
pytest \
  tests/services/learner_state/test_learning_report_read_model.py::test_learning_report_exposes_weak_points_learning_brain_evidence_and_next_training \
  tests/api/test_mobile_router.py::test_mobile_learning_report_dual_emits_v2_without_breaking_v1_fields \
  -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 7.3: Manual QA gates**

Required before production:

1. `/wechat-harness` visible-chain screenshot shows `why_this_now`.
2. WeChat DevTools simulator confirms text does not overflow.
3. `yousenwebview/packageDeeptutor` page renders same action and evidence label.
4. A learner with no evidence sees starter action, not fake personalization.

## 6. Final Verification Command

Run before merge:

```bash
rg -n "Claim lifecycle|PersonalizationContextPack|today_prescription|compiled truth override" \
  contracts/learner-state.md contracts/learning-report.md contracts/rag.md contracts/index.yaml
```

Expected:

```text
all four contract files mention the new stable boundary
```

Then run:

```bash
pytest \
  tests/services/learner_state/test_learning_synthesis.py \
  tests/services/learner_state/test_learning_brain_read_model.py \
  tests/services/learner_state/test_personalization_context.py \
  tests/services/learner_state/test_next_best_action.py \
  tests/services/learner_state/test_learning_brain_lint.py \
  tests/services/learner_state/test_training_intent.py \
  tests/services/learner_state/test_study_plan_reads_training_intent.py \
  tests/services/rag/test_retrieval_plan.py \
  tests/services/rag/test_compiled_truth_source.py \
  tests/services/rag/test_maintenance.py \
  tests/services/benchmark/test_learning_brain_personalization_eval.py \
  tests/api/test_mobile_router.py \
  tests/core/test_capabilities_runtime.py \
  tests/core/test_deep_question_submission_grading.py \
  -q
```

Expected:

```text
all selected tests pass
```

## 7. Release Gates

Do not promote beyond internal cohort until all gates pass:

1. `unsupported_claim_rate = 0` in eval fixture.
2. `evidence_coverage >= 95%` for next-best-action recommendations.
3. `generic_fallback_rate <= 5%` for learners with evidence.
4. `exact_question` and standard authority still outrank compiled truth in RAG.
5. Learning report p95 remains within current budget.
6. `/wechat-harness`, WeChat DevTools, and `yousenwebview/packageDeeptutor` all show the same evidence-backed prescription.
7. Langfuse / ClickHouse sample contains `personalization_context_available=true`, `claim_status`, `evidence_ref_count`, and `next_action_id`.

## 8. Anti-Patterns

Reject these during implementation review:

1. "Add a new learner brain DB for now."
2. "Let the frontend decide the top recommendation."
3. "Notebook says mastered, so update mastery."
4. "RAG found compiled truth, so it can override exact answer."
5. "TutorBot wrapper checks weak point status with regex."
6. "Nightly job silently rewrites evidence events."
7. "Eval passes because UI screenshot looks right."
8. "Generic advice is acceptable when evidence exists."

## 9. Scope Split

P0 for the next implementation branch:

1. Task 0.5: contract-first schema gate.
2. Task 1: claim lifecycle contract.
3. Task 2: `PersonalizationContextPack`.
4. Task 3: `next_best_action`.
5. Task 5 dry-run lint only.
6. Task 6 hermetic eval fixture with at least 10 cases.

P1:

1. Runtime propagation into TutorBot / deep_question / RAG.
2. Learning report `today_prescription`.
3. Dream-cycle scheduled run.

P2:

1. Full learner workspace surface.
2. BI personalization quality dashboard.
3. Production cohort rollout and 14-day observation.

## 10. Eng-Review Hardening Amendments (2026-06-03)

> 本节是 `/gstack-plan-eng-review` 评审产出。每条修订都用 codegraph 对真实代码核实过，
> 解决的是"eval 绿/线上空跑"、"首读崩溃"、"第二套权威"这类会对结果负责的真实缺口。
> 实现时本节优先级高于上文对应任务的原始描述。

### 修订 A — Task 3 / Task 6：消费真实 typed-graph 边，删除发明的词汇 (P0 BLOCKER, confidence 9/10)

**问题：** 计划全程用 `evidence_for` / `recommended_next` 两种边，但
`learning_synthesis.py::project_learning_graph` 的 `_ALLOWED_EDGE_TYPES` 白名单
从不产出这两种。真实边词汇是：

```
question_tests_concept / question_has_rubric_item / rubric_item_maps_to_error
error_points_to_training / training_improved_error / submission_missed_rubric_item
```

`error_points_to_training`（错因→训练）本质就是计划想要的 "recommended_next training"，
`training_improved_error` 就是 "improved signal"。计划等于重新发明了已存在的图词汇，
违反 Concept Discipline，且让 fixture（手写假边）100% 通过 release gate，生产却拿真边
匹配不上 → 返回空 → 静默退化为 generic（踩中 §8 反模式 #8）。

**修订：**
- Task 3 `next_best_action.py` 排序输入改为真实边 `error_points_to_training` /
  `training_improved_error` + `training_intent`，**禁止**引入 `recommended_next` / `evidence_for`。
- Task 3 测试 `test_next_best_action_requires_evidence_chain` 的 `typed_graph` 改用真实边类型。
- Task 6 fixture（lbp_001、lbp_004、lbp_010 等带图的用例）`typed_graph.edges` 全部改用真实边类型。
- 新增 guard 测试：断言 `next_best_action` 引用的所有 `edge_type` ∈ `learning_synthesis._ALLOWED_EDGE_TYPES`，
  防止未来再漂出第二套词汇。

**Codex 外部声音纠正（2026-06-03，confidence 9/10，行号实证）：**
- ⚠️ `training_improved_error` **不是** synthesis 的 raw projection 边。`project_learning_graph`
  （`learning_synthesis.py:134`）只复制 payload 的 `typed_edges`；construction grading 只产
  `error_points_to_training`（`construction_grading/learning_evidence.py:264`），`training_improved_error`
  是 `learning_brain_read_model.py:215` 从 `improvement_signals` **派生**的。→ next_best_action 读
  `projection.typed_graph` 拿不到它。修订：next_best_action 的"已改善"信号改读 `improvement_signals`
  或 read_model 的 `graph_chain`，而非假设它在 raw projection 边里。
- ⚠️ `error_points_to_training` 生产覆盖率被假设：仅当 errors 存在且能生成 training_id 才产
  （`construction_grading/learning_evidence.py:295`），assessment evidence batch 无 `typed_edges`
  （`assessment/learning_evidence.py:35`），且 `_valid_edge`（`learning_synthesis.py:710`）硬要求
  source/evidence/observed/confidence。**新增 P0 上线门 `actionable_edge_coverage`**：按 `source_feature`
  分桶统计真实学员图里可行动边占比，覆盖率低于阈值则 next_best_action 必须回退 training_intent 直选，
  不得静默空跑。

### 修订 B — `PersonalizationContextPack` 下沉为唯一个性化事实源，`home_personalization` 改表达层 (P0, confidence 8/10)

**问题：** `learner_state/home_personalization.py::build_home_dashboard_learning_projection`
已经在读 `projection + training_intent` 产出首页 6 类个性化行动 prompt——它本身已是一个
"个性化上下文"权威。计划 §3 Authority Map 却把"Personalized context"唯一权威写成新建
`personalization_context.py`，全程未提 home_personalization → 两个个性化事实源并存。

**修订（按决策 7 收口）：**
- **处方权威收口（最重要）：** `training_intent`（含 `prioritize_training_intents`）继续是
  **唯一决定"做什么"**的权威。`next_best_action` 降为它之上的 **view/explain 层**：只把已排序的
  intent 翻译成带 `why_this_now` / `evidence_refs` 的可解释视图，**不自决处方**。
- §3 Authority Map "Personalized context" 行补注：`home_personalization` = 首页表达层，
  `next_best_action` = intent 的解释视图，二者都不是处方事实源。
- **Codex finding #5 收编（重大漏网）：** `learning_report._next_action_card`
  （`learning_report_read_model.py:1556`）当前**自决标题/CTA/training intent**，比 home 更直接竞争
  `today_prescription`。必须改为读 `training_intent` 排序结果，与 `next_best_action` 同源。
- 加回归测试：home 首页行动、learning-report `today_prescription`、`_next_action_card` 三者在同一学员上
  **指向同一个 training_intent_id**（同一事实源 → 不漂移）。

### 修订 C — Task 1：旧 projection 读侧 default-handling + 回填验证测试 (P0 BLOCKER, confidence 9/10)

**问题：** Task 1 给每个 compiled object 新增 `claim_status` / `evidence_level` / `lifecycle`。
但生产现有 `learner_summaries.summary_structured_json.learning_brain` 是旧 synthesis 产出的，
没有这些字段。`learning_brain_read_model` / `personalization_context` / `next_best_action`
读取时会缺字段 → 学情页首读 5xx。

**修订（含 Codex finding #1 关键纠正）：**
- ⚠️ **Codex 纠正：真实 synthesis 字段是 `supporting_event_ids`，不是 `evidence_refs`**
  （`learning_synthesis.py:489/502/663`）。若按原 §10-C 写"`evidence_refs` 缺→`[]`"，会把**所有现有真实
  projection 全部降成"无证据"**，反而制造静默退化。**必须先做 canonical alias**：读侧把
  `supporting_event_ids` 映射为 `evidence_refs`（或 next_best_action/context_pack 同时认两个键），
  alias 落地后再谈降级。
- 读侧对缺失 lifecycle 字段退化：`claim_status` 缺→`observed`，`evidence_refs`/`supporting_event_ids`
  双缺→`[]`，`lifecycle` 缺→`{}`，绝不 KeyError。
- 新增 CRITICAL 回归测试：用一份**真实形态**旧格式 projection（带 `supporting_event_ids`、不含 lifecycle）喂
  `build_learning_brain_read_model` / `build_personalization_context_pack` / `get_next_best_actions`，
  断言三者均不抛错，**且带 `supporting_event_ids` 的 claim 仍被识别为有证据**（不被误降为无证据）。

### 修订 D — Task 6 / §7：golden projection 进 P0 门 + 生产 shadow 进 P2 观测 (P0, confidence 8/10)

**问题：** Task 6 与 §7 release gate 全部跑在手写 fixture 上。手写 fixture 必然带
`evidence_refs`，`unsupported_claim_rate` 天然=0——只验证了 evaluator 逻辑，没验证生产
synthesis 真的产出合法 claim。Karpathy 验收目标说 "for a sampled learner" 却无任务采真实学员。

**修订：**
- P0 新增 `tests/fixtures/learning_brain_golden_projection.json`：用真实/脱敏学员事件跑
  `synthesize_learning_truth` 一次，把**输出 projection** 冻结为 golden，再对其跑
  lifecycle/evidence 断言（验证"评估器✕真实产出"，不是只验证评估器）。
- P0 eval 增一条：golden projection 经 `next_best_action` 后 `unsupported_claim_rate==0`、
  `evidence_coverage>=0.95`。
- P2 新增生产 shadow：采样真实学员跑 next_best_action，把 `unsupported_rate` /
  `generic_fallback_rate` 打到 Langfuse/ClickHouse，卡真实分布漂移（接入现有 trace 采样，不另起观测）。

### 修订 E — Task 1：claim_status × evidence_level 状态机 ASCII 图 + invariant + 退出边 (P1, confidence 7/10)

**问题：** 7 个 `claim_status` 与 4 个 `evidence_level` 的关系（正交/耦合）未定义。
能否 `confirmed`+`L0_observed`？`contradicted` 一旦进入无退出路径 → 永久死 claim，
压制该 concept 所有行动 → 运营死角。

**修订：** 在 `contracts/learner-state.md` 补下图与 invariant 表，Task 1 加 invariant 断言测试。

```
                      claim lifecycle 状态机 (status × evidence_level)
  ┌─────────┐ repeated evidence  ┌─────────┐ teacher/manual    ┌───────────┐
  │observed │───────────────────▶│repeated │──────────────────▶│ confirmed │
  │  (L0)   │                    │  (L1)   │   confirm          │ (L2/L3)   │
  └────┬────┘                    └────┬────┘                    └─────┬─────┘
       │ later correction            │ decay / no retest             │ later improvement
       │ rejects claim               ▼                               ▼
       │                        ┌─────────┐ retest passes      ┌───────────┐
       └───────────────────────▶│  stale  │◀───────────────────│ (mastery) │
                                │needs_retest│ decay            └───────────┘
                                └────┬────┘
            conflicting evidence     │            teacher review / retest resolves
       ┌─────────────┐◀──────────────┘──────────────────────────────────┐
       │contradicted │  EXIT: 仅 manual_review 或 retest 事件可脱困        │
       │ (frozen)    │───────────────────────────────────────────────────┘
       └─────────────┘   superseded ← 更新 correction 替换旧 claim（带 superseded_by）

  INVARIANT (Task 1 断言):
   - confirmed ⇒ evidence_level ∈ {L2_confirmed, L3_mastery_signal} 且 evidence_refs 非空
   - observed  ⇒ evidence_level == L0_observed
   - contradicted / superseded / rejected ⇒ next_best_action 不得基于该 claim 出处方动作
   - contradicted 的唯一退出事件 = manual_review | retest（synthesis 不得静默 resolve）
```

**Codex finding #4 纠正（confidence 8/10）：** 上述 contradicted 状态机当前**没有事件管道**。
现状：`learning_synthesis.py:343` 只读 `conflicting_event_ids`，但 `weak_points` 不携带 conflict、
`_active_weak_points`（`:410`）不看 conflict；manual correction（`:468`）只有 confirm/supersede 语义，
**没有 `manual_review` 事件类型**。→ 处置：**P0 只实现 `observed/repeated/confirmed/stale/superseded`
五态**（这些有现成 decay/confirm/supersede 管道）；`contradicted` + `rejected` + `manual_review` 退出边
作为 **P1 单独任务**，先在 synthesis 加 conflict 透传 + 新事件类型，再点亮状态。P0 的 next_best_action
遇到 `conflicting_event_ids` 非空的 claim 直接**保守跳过**（不出处方），不依赖未落地的 contradicted 态。

### 修订 F — Task 4 / §7：复用 home_personalization projection 缓存 + chat turn p95 gate (P1, confidence 7/10)

**问题：** Task 4 每轮 `/api/v1/ws` 都注入 Pack。builder 纯函数不读库，但调用方必须先加载
projection。§7 gate 只卡 learning-report p95，没卡 chat turn p95 → 热路径减速只能事后发现。

**修订（含 Codex finding #9 纠正）：**
- ⚠️ **Codex 纠正缓存对象：** `home_personalization` 的 6h projection 是**表达层缓存**（会 seed
  fallback、从 recent events 恢复、自拼 6 类 prompt，见 `home_personalization.py:31/70`）。直接复用它当
  Pack 加载缓存，会把**表达缓存升格为学习事实缓存**，制造 authority 漂移。**正确做法：缓存
  `compiled_learning_truth` projection / `PersonalizationContextPack` 本身**（事实层），不缓存 home prompts；
  home 与 Pack 各自从这层事实缓存读，但 home 的 prompt 拼装结果不进事实缓存。
- §7 Release Gate 增一条：注入 context 后 **chat turn p95 不退化**（基线对比，fail-closed）。
- 运行时 fail-open：projection 加载超时则跳过 context（不阻断聊天），但记 trace 标记
  `personalization_context_available=false` 以便观测命中率。

### 修订 H — Codex 外部声音新增缺口（运行时接线 + fallback 标记）(confidence 8/10)

**Codex finding #7 + #8（Task 4 是"加接线"不是"加转发测试"）：**
- `build_retrieval_plan`（`retrieval_plan.py:135`）当前只读 `compiled_learning_truth_available`，**不读**
  `personalization_context_available`；`AgentLoop._build_rag_preview_args`（`loop.py:1309`）只传 compiled truth；
  `RAGAdapterTool.preview_args`（`deeptutor_tools.py:209`）**连 routing_metadata 都不补**。
- `_resolve_generation_topic`（`deep_question.py:377`）**不读 personalization_context**，题数只吃
  `learning_training_intent` override（`:1731`）。→ 计划 Task 4 的 `assert "1A432000" in topic` 在现状下**会失败**。
- **处置：** Task 4 必须显式定义 mapping 并真接线，二选一（推荐前者，符合决策 7 单一权威）：
  **(a) pack → training_intent**：personalization 通过把 top_claim 转成/匹配 `learning_training_intent`
  进入 deep_question（沿用既有 anchor + 题数 override 路径），RAG 侧仅用 `personalization_context_available`
  开关解释既有 `compiled_learning_truth` source group；
  (b) 在 `_resolve_generation_topic` / `build_retrieval_plan` 真新增 pack 解析分支（更大 diff、更多新面）。
- 测试随真实接线路径写，不写"假设已接线"的转发桩。

**Codex finding #10（report dry-run fallback 退化为最近窗口，须标 degraded）：**
- compiled truth 缺失时，`learning_report_read_model.py:821` 用 `event_limit` 做 dry-run synthesis，与计划的
  immutable-timeline / `learner_summaries` authority 不一致。
- **处置：** next_best_action / today_prescription 若基于该 dry-run fallback projection，必须带
  `degraded=true` 标记并**禁止产生强个性化处方**（降级为 starter / 复习类安全动作），trace 记 `source=dry_run_fallback`。

### 修订 G — 补充测试缺口（IRON RULE：覆盖/回归测试直接纳入，不另行决策）

1. **正向贯通集成测试**：真实形态 projection → build pack → 断言非空 `top_claims` 经
   `_build_rag_preview_args` 落到 `routing_metadata.personalization_context_available=true`
   且 `error_points_to_training` 真边产生非空 action（关闭"静默退化"失败模式）。
2. **tie-break 确定性测试**：构造 status/level/recency 全等的多个候选，断言 `next_best_action`
   输出顺序稳定（计划自称 deterministic 但无 tie 测试）。
3. **synthesis 性能门**：Task 1 后复跑性能门，证据见
   `docs/qa/2026-06-03-gbrain-learning-synthesis-performance-baseline.md`；
   p95≤200ms@2000-event 不回归（lifecycle 扫描勿引入 O(events×claims)）。
4. **旧客户端 v2 缺失渲染**：Task 7 manual gate 增一条——wx/yousen 旧版页面在
   `today_prescription` / `personalization_context` 字段缺失时优雅降级（不白屏、回退 v1）。

### 修订对 §9 Scope Split 的增量（含 codex 整合）

**P0 新增：**
- 修订 C 的 `supporting_event_ids→evidence_refs` canonical alias（**最先做**，否则迁移清零证据）。
- 修订 A 真边收口（与 Task 3/6 同批）+ `actionable_edge_coverage` 上线门（codex #3）。
- 修订 B 决策 7：`next_best_action` 降为 view/explain over `training_intent`；收编
  `learning_report._next_action_card`（codex #5）。
- 修订 E 收窄：P0 只实现五态生命周期；`contradicted/rejected/manual_review` 退出边 → P1（codex #4）。
- 修订 D 的 golden projection 门 + 修订 H 的 dry-run fallback `degraded` 标记（codex #10）。

**P1 新增：**
- 修订 B 的 home 下沉、修订 E 的完整状态机契约 + contradicted 事件管道、修订 F（事实层缓存 + chat p95 门）。
- 修订 H 的 Task 4 真接线 mapping（pack→intent 优先，codex #7/#8）、修订 G.1/G.2/G.3。

**P2 新增：** 修订 D 的生产 shadow 观测、修订 G.4。

### 实施顺序硬约束（codex 整合后）

```
0. supporting_event_ids→evidence_refs alias        ← 不先做，Task 1 迁移会清零所有现有证据
1. Task 1 五态 lifecycle + invariant（跳过 contradicted）
2. 真边盘点 actionable_edge_coverage（先量真实图是否为空，再决定 Task 3 形态）
3. Task 3 next_best_action = view/explain over training_intent（不新建处方权威）
4. 收编 _next_action_card + home 同读 intent
5. Task 4 真接线（pack→intent 优先），测试随真实路径
6. golden projection 门 + dry-run fallback degraded 标记
```

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | not run (optional) |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | 10 code-grounded findings; 3 corrected my amendments, 5 new gaps |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 7 architecture decisions + 4 coverage gaps + codex integration |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | not run (backend/contract change) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | not run |

- **CODEX:** 10 findings, all valid. #1/#2/#9 corrected eng-review amendments (evidence_refs vs supporting_event_ids; derived vs raw edge; cache target). #5/#6/#7/#8/#10 surfaced gaps both plan and eng-review missed (prescription-authority sprawl, missing runtime wiring, dry-run fallback authority drift).
- **CROSS-MODEL:** No tension — codex deepened the same direction. Core synthesis: the real risk is **prescription-authority sprawl** (training_intent + _next_action_card + home_personalization + proposed next_best_action = 4 authorities), resolved by decision 7 (next_best_action → view/explain over training_intent).
- **UNRESOLVED:** 0 — all 7 decisions answered; codex findings #1-#10 folded into §10 (修订 A/B/C/E/F corrected, 修订 H added, implementation-order hard constraint added).
- **CRITICAL GAPS:** 3 closed — silent-degradation (修订 A + G.1 + actionable_edge_coverage gate), first-read crash + evidence-zeroing (修订 C alias-first), prescription-authority sprawl (决策 7).
- **VERDICT:** ENG REVIEW + CODEX issues addressed in §10. Plan is fully grounded (every symbol codegraph-verified, every codex finding line-cited). Now closes eval-green/prod-empty, migration-crash, second-authority sprawl, hot-path-latency, and missing-wiring gaps. **Must implement in the §10 hard-constraint order** (alias FIRST). Ready for P0.
