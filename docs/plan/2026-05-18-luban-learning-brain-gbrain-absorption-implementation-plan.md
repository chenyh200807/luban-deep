# Luban Learning Brain GBrain Absorption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the P0/P1 execution loop for 鲁班智考学习事实编译层: grading evidence -> learner memory event -> compiled truth projection -> typed graph projection -> nightly synthesis -> next training signal.

**Architecture:** Do not import or embed GBrain. Reuse existing DeepTutor authorities: `construction_grading_result` owns scoring facts, `LearnerStateService` owns learner memory events and summaries, `RAGService.evidence_bundle` owns retrieval evidence, and `deep_question` owns practice continuity. Add focused helpers under existing modules; wrappers only adapt payloads, while synthesis and graph projection live in learner-state service code.

**Tech Stack:** Python dataclasses/functions, existing `deeptutor/services/construction_grading`, existing `deeptutor/services/learner_state`, existing outbox/Supabase writer, pytest, optional `/wechat-harness` smoke after code lands.

---

## Execution Status (2026-05-18)

Current implementation status: **all PRD phases implemented locally with `/wechat-harness` live visible-chain verified**.

Clarification: this PRD uses Phase 0-5 plus v0.2 strengthening items, not separate `P2/P3` labels. The implemented scope now covers Phase 0-5 and the v0.2 strengthening bar.

Completed locally:

1. `learning_evidence` canonical payload and dedupe helper are implemented under `construction_grading`.
2. Grading writeback now writes `memory_kind="learning_evidence"` through `LearnerStateService`.
3. Learner-state synthesis produces `compiled_objects`, timeline refs, typed graph projection, weak-point convenience views, evidence gates, conflict/decay/manual-correction handling, and `synthesis_run` audit metadata.
4. Summary refresh outbox and Supabase writer preserve `summary_structured_json`.
5. `scripts/run_learning_synthesis.py` supports dry-run JSON output with claim counts and projection hash.
6. `deep_question` can consume high-confidence compiled training signals without adding a new router.
7. Graph projection exposes query helpers for question context, concept evidence, training traceability, and readiness gaps.
8. Manual confirmation can upgrade supported claims to `L2_confirmed`; manual correction can supersede automatic claims.
9. Trace references can be preserved in `learning_evidence.evidence_refs`.
10. Teaching Policy consumption records evidence level and selected policy action in the generated training anchor.
11. The plan index points to this PRD and implementation plan.

Verification completed locally:

```bash
pytest -q
# 1752 passed, 2 skipped, 5 warnings

pytest \
  tests/api/test_unified_ws_turn_runtime.py \
  tests/core/test_deep_question_submission_grading.py \
  tests/services/construction_grading/test_audit_and_writeback.py \
  tests/services/learner_state/test_learning_synthesis.py \
  -q
# 127 passed, 5 warnings

npm --prefix web run test:wechat-harness
# data tests: 2 passed
# Playwright wechat-harness: 3 passed

python scripts/check_contract_guard.py
# contract-guard: passed
```

Code review fixes completed:

1. `weak_points` now represents only active Teaching Policy-consumable claims;
   manual correction and later improvement remove stale weak points from the
   active view while preserving superseded/decayed facts in `compiled_objects`
   and timeline/audit metadata.
2. The Learning Brain QA route is mounted only when
   `DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA=1` and runtime environment is exactly
   `local`; production/staging cannot enable the write-capable harness route.
3. `learning_evidence` now removes full provider reasoning blocks, including
   attributed and unclosed `<think>` / `<thinking>` blocks.
4. Synthesis expands all `error_events` in a grading event instead of only the
   first error.
5. Typed graph projection now fail-closes invalid edges with an allowlist,
   non-empty node ids, and confidence range validation.
6. Ordinary `summary_refresh` no longer writes fallback
   `summary_structured_json`, so normal chat summaries do not overwrite the
   Learning Brain projection column.
7. Learning synthesis summary refresh dedupe includes the output projection
   hash, so a changed structured projection is not swallowed when the rendered
   Markdown summary is unchanged.
8. Concept-level compiled truth now summarizes all active error codes under
   the concept instead of being overwritten by the last error object.

Fresh real-scenario verification completed after starting real local services:

1. Backend started with `DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA=1` and isolated
   `DEEPTUTOR_USER_DATA_DIR`.
2. Web started with `NEXT_API_PROXY_TARGET` pointing to the live backend.
3. A scenario matrix passed against real product functions and the live
   `/api/v1/learning-brain/harness-case-grading` route:
   - live API status, repeated `learning_evidence` writes, compiled truth
     projection, L1 weak point promotion, typed graph edge count, visible
     grading card payload
   - canonical `learning_evidence` shape, dedupe key, reasoning-tag stripping,
     full graph edge chain pieces
   - L0 single observation gate, L1 repeated evidence, question-to-training
     graph query, concept evidence query, training recommendation trace, next
     training target query, missing concept readiness gap
   - improvement decay, manual confirmation to `L2_confirmed`, manual
     correction supersede, conflict audit, chat-only memory blocked
   - Teaching Policy L1 diagnostic action, L2 stable personalization, L0 ignored
   - manual correction removes active weak point while preserving superseded
     compiled object
4. Real Web UI verification passed at `/wechat-harness`:
   - API `200`
   - `projectionSubject=construction_exam_learning_truth`
   - `eventCount=2`
   - `createdClaimCount>=1`
   - `typedGraphEdgeCount=14`
   - UI showed score, missed point, rewrite, next training, and compiled truth
     subject
   - `consoleErrors=[]`
5. Release-gate automation rerun after stopping the manual Web server:
   - focused review suite: `89 passed`
   - `pytest -q`: `1752 passed, 2 skipped, 5 warnings`
   - `npm --prefix web run test:wechat-harness`: data tests `2 passed`,
     Playwright `3 passed`
   - `python scripts/check_contract_guard.py`: passed

Deferred to deployment / release gate:

1. Production deployment.
2. Online Langfuse trace inspection for grading -> memory event -> synthesis
   projection correlation.
3. 微信小程序真入口 smoke, only required if this change is packaged into the
   mini-program surface or mini-program files change in the release.

Additional isolated backend QA completed with `DEEPTUTOR_USER_DATA_DIR=/tmp/...`:

1. `CaseGradingSkillKernel` graded two construction case answers that missed rubric points.
2. `write_grading_error_events(...)` wrote two canonical `learning_evidence` events for the same learner.
3. `python scripts/run_learning_synthesis.py --user-id learning_brain_qa_student --dry-run` returned `subject="construction_exam_learning_truth"`, `event_count=2`, `created_claim_count=1`, `compiled_objects`, typed graph edges, and an `L1_repeated` weak point for concept `1A432000` / error `E02`.

Live Web QA completed:

`/wechat-harness` now includes a local QA panel that calls the dev-only backend wrapper `/api/v1/learning-brain/harness-case-grading`. The wrapper owns no grading or memory truth; it only connects the Web QA surface to existing `CaseGradingSkillKernel`, `write_grading_error_events(...)`, and `LearnerStateService.synthesize_learning_truth(...)` authorities.

Manual live verification completed with backend `127.0.0.1:8019` and Web `localhost:3791`:

```text
UI: score visible, missed point visible, rewrite visible, next training visible, construction_exam_learning_truth visible
API: status=200, event_count=2, created_claim_count=1, typed_graph_edge_count=18, consoleErrors=[]
```

Remaining note: this does not replace a real 微信小程序入口 smoke if mini-program files are changed later.

Phase coverage:

| PRD phase | Local status |
| --- | --- |
| Phase 0 - Contract alignment | Done |
| Phase 1 - Learning evidence event | Done |
| Phase 2 - Compiled truth + timeline | Done |
| Phase 3 - Typed graph projection | Done |
| Phase 4 - Teaching Policy consumption | Done |
| Phase 5 - Web QA and release gate | Done locally through `/wechat-harness`; mini-program smoke remains conditional on mini-program file changes |

v0.2 strengthening coverage:

| Strengthening item | Local status |
| --- | --- |
| Object-level compiled truth | Done |
| Full typed graph chain and query helpers | Done |
| Evidence source gates and trace refs | Done |
| Synthesis run audit, conflict, decay, manual correction | Done |
| Manual confirmation to `L2_confirmed` | Done |

## 0. Scope And Authority Rules

This plan implements the PRD:

- [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md)

The implementation must preserve these authority boundaries:

| Business fact | Existing authority | Implementation rule |
| --- | --- | --- |
| Score, rubric hits, error events | `construction_grading_result` | Do not recompute score in learner-state or TutorBot text. |
| Long-term learner event ledger | `LearnerStateService.append_memory_event` / `learner_memory_events` | All durable learning evidence writes go through this service. |
| Compiled learning truth | `learner_summaries.summary_structured_json.learning_brain` projection | P0 writes projection through summary refresh/outbox, not a new table. |
| Retrieval evidence | `RAGService.evidence_bundle` | Store evidence refs only; do not add a second retrieval path. |
| Next practice continuity | `deep_question` / active question object | Use compiled signals as an anchor, not as a new practice router. |

Do not create:

- a `gbrain` dependency
- a graph database
- a new chat route
- a parallel learner profile/progress/memory table
- a new `deeptutor/services/case_grading/` package
- a second Teaching Policy engine

## 1. File Structure

Create:

- `deeptutor/services/construction_grading/learning_evidence.py`
  - Canonical builder for `learning_evidence` payloads and dedupe keys from grading results.
- `deeptutor/services/learner_state/learning_synthesis.py`
  - Pure functions for compiled truth, typed edge projection, and summary rendering from learner events.
- `scripts/run_learning_synthesis.py`
  - Dry-run capable local/nightly entrypoint.
- `tests/services/construction_grading/test_learning_evidence.py`
  - Unit tests for canonical evidence payload and writeback shape.
- `tests/services/learner_state/test_learning_synthesis.py`
  - Unit tests for repeated evidence, single-observation gating, improvement signal, and typed graph projection.
- `tests/scripts/test_run_learning_synthesis.py`
  - CLI smoke test with dry-run.

Modify:

- `deeptutor/services/construction_grading/writeback.py`
  - Write canonical `memory_kind="learning_evidence"` while keeping legacy reader compatibility.
- `deeptutor/services/learner_state/service.py`
  - Render `learning_evidence` in memory context.
  - Add a small service method to run synthesis for one learner.
  - Allow summary refresh to carry `summary_structured_json`.
- `deeptutor/services/learner_state/supabase_writer.py`
  - Preserve `summary_structured_json` when writing `learner_summaries`.
- `deeptutor/capabilities/deep_question.py`
  - Read compiled training signal only when evidence level is high enough.
- `tests/services/construction_grading/test_audit_and_writeback.py`
  - Update expectations from legacy `case_error_event` / `mcq_error_event` to canonical `learning_evidence`.
- `tests/services/learner_state/test_service.py`
  - Add rendering and synthesis integration tests.
- `tests/core/test_deep_question_submission_grading.py`
  - Add/adjust next-training anchor tests.
- `docs/plan/INDEX.md`
  - Register this implementation plan.

## 2. Baseline Verification

Run before coding:

```bash
pytest \
  tests/services/construction_grading/test_audit_and_writeback.py \
  tests/services/construction_grading/test_case_grading_kernel.py \
  tests/services/learner_state/test_service.py::test_learner_state_context_renders_construction_grading_error_events \
  tests/core/test_deep_question_submission_grading.py::test_related_generation_anchor_uses_next_training_signal \
  -q
```

Expected:

```text
all selected tests pass
```

If this baseline fails, stop and fix the existing failing authority path first. Do not start the Learning Brain work on a broken grading/writeback baseline.

## 3. Task 1: Canonical Learning Evidence Payload

**Files:**

- Create: `deeptutor/services/construction_grading/learning_evidence.py`
- Modify: `deeptutor/services/construction_grading/writeback.py`
- Test: `tests/services/construction_grading/test_learning_evidence.py`
- Test: `tests/services/construction_grading/test_audit_and_writeback.py`

- [ ] **Step 1.1: Write failing tests for canonical `learning_evidence`**

Add `tests/services/construction_grading/test_learning_evidence.py`:

```python
from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_dedupe_key,
    build_learning_evidence_payload,
)


def test_build_learning_evidence_payload_preserves_grading_authority() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={
            "id": "case-1",
            "question_type": "case_study",
            "correct_answer": "应组织专家论证。",
            "grading_keywords": ["专家论证"],
            "node_code": "1A432000",
        },
        user_answer="应加强管理。",
    )

    payload = build_learning_evidence_payload(
        grading_result=result,
        turn_id="turn-1",
        session_id="session-1",
    )

    assert payload["schema_version"] == 1
    assert payload["event_type"] == "learning_evidence"
    assert payload["source"] == "construction_grading"
    assert payload["question_id"] == "case-1"
    assert payload["question_type"] == "case"
    assert payload["quality"]["evidence_level"] == "L0_observed"
    assert payload["quality"]["writeback_eligible"] is True
    assert payload["error_events"][0]["error_code"] in {"E02", "E03", "E04"}
    assert payload["typed_edges"]
    assert any(edge["edge_type"] == "submission_missed_rubric_item" for edge in payload["typed_edges"])


def test_learning_evidence_dedupe_key_is_stable() -> None:
    payload = {
        "question_id": "q-1",
        "question_type": "case",
        "user_answer": "应组织专家论证。",
        "error_events": [{"error_code": "E02"}],
        "score_awarded": 0.0,
        "max_score": 1.0,
    }

    first = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=payload,
    )
    second = build_learning_evidence_dedupe_key(
        user_id="student-1",
        payload_json=dict(reversed(list(payload.items()))),
    )

    assert first == second
    assert len(first) == 40
```

- [ ] **Step 1.2: Run tests and verify they fail**

Run:

```bash
pytest tests/services/construction_grading/test_learning_evidence.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.construction_grading.learning_evidence'
```

- [ ] **Step 1.3: Implement canonical payload helper**

Create `deeptutor/services/construction_grading/learning_evidence.py`:

```python
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from deeptutor.services.construction_grading.schema import CaseGradingResult, MCQGradingResult

_REASONING_TAG_RE = re.compile(r"</?(?:think|thinking)>", re.IGNORECASE)


def build_learning_evidence_payload(
    *,
    grading_result: CaseGradingResult | MCQGradingResult | dict[str, Any],
    turn_id: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    payload = _grading_result_payload(grading_result)
    question_type = str(payload.get("type") or payload.get("question_type") or "").strip()
    errors = [_clean_dict(error) for error in list(payload.get("error_events") or [])]
    evidence_refs = [_clean_dict(ref) for ref in list(payload.get("evidence_refs") or [])]
    typed_edges = _typed_edges_from_payload(payload, errors)
    next_training_signal = dict(payload.get("next_training_signal") or {})
    score_awarded = payload.get("score_awarded")
    max_score = payload.get("max_score")
    score_ratio = _score_ratio(score_awarded, max_score)

    return {
        "schema_version": 1,
        "event_type": "learning_evidence",
        "legacy_event_type": "construction_grading_error",
        "source": "construction_grading",
        "turn_id": str(turn_id or "").strip(),
        "session_id": str(session_id or "").strip(),
        "question_id": str(payload.get("question_id") or "").strip(),
        "question_type": question_type or "unknown",
        "user_answer": _clean_text(payload.get("user_answer")),
        "score_awarded": score_awarded,
        "max_score": max_score,
        "score_ratio": score_ratio,
        "grading_mode": payload.get("grading_mode"),
        "rubric_items": [_clean_dict(item) for item in list(payload.get("rubric_items") or [])],
        "evidence_refs": evidence_refs,
        "rag_evidence_refs": [
            ref for ref in evidence_refs if str(ref.get("source") or "").lower() in {"rag", "kb", "kb_chunk"}
        ],
        "error_events": errors,
        "errors": errors,
        "next_training_signal": next_training_signal,
        "typed_edges": typed_edges,
        "quality": {
            "evidence_level": "L0_observed",
            "writeback_eligible": bool(errors),
        },
    }


def build_learning_evidence_dedupe_key(*, user_id: str, payload_json: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "user_id": str(user_id or "").strip(),
            "memory_kind": "learning_evidence",
            "question_type": payload_json.get("question_type"),
            "question_id": payload_json.get("question_id"),
            "user_answer": payload_json.get("user_answer"),
            "error_events": payload_json.get("error_events") or [],
            "score_awarded": payload_json.get("score_awarded"),
            "max_score": payload_json.get("max_score"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _grading_result_payload(grading_result: CaseGradingResult | MCQGradingResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(grading_result, dict):
        payload = dict(grading_result)
    else:
        payload = grading_result.to_dict()
        if isinstance(grading_result, CaseGradingResult):
            payload["type"] = "case"
        elif isinstance(grading_result, MCQGradingResult):
            payload["type"] = "mcq"
    payload["error_events"] = [_error_event_payload(error) for error in payload.get("error_events") or []]
    return payload


def _error_event_payload(error: Any) -> dict[str, Any]:
    if hasattr(error, "to_dict"):
        return _clean_dict(error.to_dict())
    if isinstance(error, dict):
        return _clean_dict(error)
    return {"diagnosis": _clean_text(error)}


def _typed_edges_from_payload(payload: dict[str, Any], errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    question_id = str(payload.get("question_id") or "").strip()
    edges: list[dict[str, Any]] = []
    for error in errors:
        error_code = str(error.get("error_code") or "").strip()
        concept_tag = str(error.get("concept_tag") or "").strip()
        if question_id and concept_tag:
            edges.append({
                "edge_type": "question_tests_concept",
                "from": {"type": "question", "id": question_id},
                "to": {"type": "concept", "id": concept_tag},
            })
        if question_id and error_code:
            edges.append({
                "edge_type": "submission_missed_rubric_item",
                "from": {"type": "submission", "id": question_id},
                "to": {"type": "error_tag", "id": error_code},
            })
            edges.append({
                "edge_type": "error_points_to_training",
                "from": {"type": "error_tag", "id": error_code},
                "to": {"type": "training_signal", "id": question_id},
            })
    return edges


def _score_ratio(score_awarded: Any, max_score: Any) -> float | None:
    try:
        max_score_float = float(max_score or 0)
        if max_score_float <= 0:
            return None
        return float(score_awarded or 0) / max_score_float
    except (TypeError, ValueError):
        return None


def _clean_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): _clean_value(value) for key, value in payload.items()}


def _clean_value(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        return _clean_dict(value)
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    return value


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return _REASONING_TAG_RE.sub("", text).strip()
```

- [ ] **Step 1.4: Switch writeback to canonical memory kind**

Modify `deeptutor/services/construction_grading/writeback.py`:

```python
from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_dedupe_key,
    build_learning_evidence_payload,
)
```

Replace the current payload/dedupe block in `write_grading_error_events(...)` with:

```python
    payload_json = build_learning_evidence_payload(grading_result=grading_result)
    if not payload_json["quality"]["writeback_eligible"]:
        return 0
    dedupe_key = build_learning_evidence_dedupe_key(
        user_id=normalized_user_id,
        payload_json=payload_json,
    )
    learner_state_service.append_memory_event(
        normalized_user_id,
        source_feature="construction_grading",
        source_id=source_id,
        source_bot_id=source_bot_id,
        memory_kind="learning_evidence",
        payload_json=payload_json,
        dedupe_key=dedupe_key,
    )
    return 1
```

Keep `_grading_result_payload(...)`, `_error_event_payload(...)`, and `_grading_error_dedupe_key(...)` only if other code still imports them. If not imported, delete them in this task.

- [ ] **Step 1.5: Update existing writeback expectations**

In `tests/services/construction_grading/test_audit_and_writeback.py`, update the first writeback test assertions:

```python
    assert call["source_feature"] == "construction_grading"
    assert call["memory_kind"] == "learning_evidence"
    assert call["source_bot_id"] == "construction-exam"
    assert call["dedupe_key"]
    assert call["payload_json"]["event_type"] == "learning_evidence"
    assert call["payload_json"]["legacy_event_type"] == "construction_grading_error"
    assert call["payload_json"]["question_id"] == "case-1"
    assert call["payload_json"]["error_events"][0]["error_code"] in {"E02", "E03", "E04"}
    assert call["payload_json"]["quality"]["evidence_level"] == "L0_observed"
```

Update the batch test:

```python
    assert call["source_id"] == "turn-1:q-1"
    assert call["memory_kind"] == "learning_evidence"
    assert call["payload_json"]["question_id"] == "q-1"
    assert call["payload_json"]["next_training_signal"]["focus"] == "行政法规与部门规章辨析"
```

- [ ] **Step 1.6: Run focused tests**

Run:

```bash
pytest \
  tests/services/construction_grading/test_learning_evidence.py \
  tests/services/construction_grading/test_audit_and_writeback.py \
  -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 1.7: Checkpoint diff**

Run:

```bash
git diff -- deeptutor/services/construction_grading/learning_evidence.py deeptutor/services/construction_grading/writeback.py tests/services/construction_grading/test_learning_evidence.py tests/services/construction_grading/test_audit_and_writeback.py
```

Expected:

```text
Only learning evidence payload/writeback related changes are present.
```

Do not commit unless the user explicitly asks for a commit.

## 4. Task 2: Learner State Rendering Compatibility

**Files:**

- Modify: `deeptutor/services/learner_state/service.py`
- Test: `tests/services/learner_state/test_service.py`

- [ ] **Step 2.1: Add failing test for `learning_evidence` context rendering**

Append to `tests/services/learner_state/test_service.py` near the existing grading memory test:

```python
def test_learner_state_context_renders_learning_evidence_events(tmp_path) -> None:
    service = _make_service(tmp_path)
    service.append_memory_event(
        "student_demo",
        source_feature="construction_grading",
        source_id="turn-1:q-law",
        source_bot_id="construction-exam-coach",
        memory_kind="learning_evidence",
        payload_json={
            "event_type": "learning_evidence",
            "question_type": "mcq",
            "question_id": "q-law",
            "score_awarded": 0.0,
            "max_score": 1.0,
            "error_events": [
                {
                    "error_code": "M02",
                    "diagnosis": "把行政法规与部门规章层级混淆。",
                }
            ],
            "next_training_signal": {
                "concept": "法规层级",
                "focus": "行政法规与部门规章辨析",
            },
        },
    )

    context = service.build_context("student_demo", language="zh")
    candidates = service.build_context_candidates(
        user_id="student_demo",
        query="继续练刚才薄弱的点",
        route="recall",
        language="zh",
    )

    assert "建筑实务批改错因" in context
    assert "把行政法规与部门规章层级混淆" in context
    assert "行政法规与部门规章辨析" in context
    assert any(
        "行政法规与部门规章辨析" in str(candidate.get("content") or "")
        for candidate in candidates.get("candidates", [])
    )
```

- [ ] **Step 2.2: Run test and verify failure**

Run:

```bash
pytest tests/services/learner_state/test_service.py::test_learner_state_context_renders_learning_evidence_events -q
```

Expected before implementation:

```text
FAIL because learning_evidence is not rendered by _grading_memory_event_text
```

- [ ] **Step 2.3: Update learner-state grading event renderer**

Modify `_grading_memory_event_text(...)` in `deeptutor/services/learner_state/service.py`.

Replace the opening guard with:

```python
        if event.source_feature != "construction_grading" and event.memory_kind not in {
            "case_error_event",
            "mcq_error_event",
            "learning_evidence",
        }:
            return ""
```

Keep the existing payload parsing. It already reads `question_id`, `question_type`, `score_awarded`, `max_score`, `next_training_signal`, and `error_events`, which are present in the canonical payload.

- [ ] **Step 2.4: Run compatibility tests**

Run:

```bash
pytest \
  tests/services/learner_state/test_service.py::test_learner_state_context_renders_construction_grading_error_events \
  tests/services/learner_state/test_service.py::test_learner_state_context_renders_learning_evidence_events \
  -q
```

Expected:

```text
2 passed
```

## 5. Task 3: Pure Synthesis And Typed Graph Projection

**Files:**

- Create: `deeptutor/services/learner_state/learning_synthesis.py`
- Test: `tests/services/learner_state/test_learning_synthesis.py`

- [ ] **Step 3.1: Write failing tests for synthesis gates**

Create `tests/services/learner_state/test_learning_synthesis.py`:

```python
from deeptutor.services.learner_state.service import LearnerStateEvent
from deeptutor.services.learner_state.learning_synthesis import (
    project_learning_graph,
    render_learning_truth_summary_md,
    synthesize_learning_truth,
)


def _event(event_id: str, *, concept: str, error_code: str, improved: bool = False) -> LearnerStateEvent:
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student_demo",
        source_feature="construction_grading",
        source_id=f"turn:{event_id}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=f"2026-05-18T0{len(event_id)}:00:00+08:00",
        payload_json={
            "event_type": "learning_evidence",
            "question_id": f"q-{event_id}",
            "question_type": "case",
            "score_awarded": 0.0 if not improved else 1.0,
            "max_score": 1.0,
            "error_events": [] if improved else [
                {
                    "error_code": error_code,
                    "concept_tag": concept,
                    "diagnosis": "漏写专家论证程序。",
                }
            ],
            "next_training_signal": {
                "concept": concept,
                "focus": "专家论证程序",
                "mode": "case_repair",
            },
            "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
            "typed_edges": [
                {
                    "edge_type": "submission_missed_rubric_item",
                    "from": {"type": "submission", "id": f"q-{event_id}"},
                    "to": {"type": "error_tag", "id": error_code},
                }
            ],
        },
    )


def test_synthesis_keeps_single_observation_out_of_stable_truth() -> None:
    projection = synthesize_learning_truth([_event("evt1", concept="1A432000", error_code="E02")])

    assert projection["weak_points"] == []
    assert projection["observed_candidates"][0]["evidence_level"] == "L0_observed"


def test_synthesis_promotes_repeated_error_to_l1() -> None:
    projection = synthesize_learning_truth([
        _event("evt1", concept="1A432000", error_code="E02"),
        _event("evt2", concept="1A432000", error_code="E02"),
    ])

    weak = projection["weak_points"][0]
    assert weak["concept_id"] == "1A432000"
    assert weak["error_code"] == "E02"
    assert weak["evidence_level"] == "L1_repeated"
    assert weak["supporting_event_ids"] == ["evt1", "evt2"]


def test_synthesis_marks_improvement_signal() -> None:
    projection = synthesize_learning_truth([
        _event("evt1", concept="1A432000", error_code="E02"),
        _event("evt2", concept="1A432000", error_code="E02"),
        _event("evt3", concept="1A432000", error_code="E02", improved=True),
    ])

    assert projection["improvement_signals"][0]["concept_id"] == "1A432000"
    assert projection["stale_claims"][0]["reason"] == "later_training_improved"


def test_project_learning_graph_reuses_typed_edges() -> None:
    graph = project_learning_graph([
        _event("evt1", concept="1A432000", error_code="E02"),
    ])

    assert graph["schema_version"] == 1
    assert graph["edges"][0]["evidence_event_id"] == "evt1"
    assert graph["edges"][0]["edge_type"] == "submission_missed_rubric_item"


def test_render_learning_truth_summary_md_is_teacher_readable() -> None:
    projection = synthesize_learning_truth([
        _event("evt1", concept="1A432000", error_code="E02"),
        _event("evt2", concept="1A432000", error_code="E02"),
    ])

    summary = render_learning_truth_summary_md(projection)

    assert "学习事实编译" in summary
    assert "1A432000" in summary
    assert "E02" in summary
```

- [ ] **Step 3.2: Run tests and verify failure**

Run:

```bash
pytest tests/services/learner_state/test_learning_synthesis.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.learner_state.learning_synthesis'
```

- [ ] **Step 3.3: Implement synthesis helper**

Create `deeptutor/services/learner_state/learning_synthesis.py`:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from deeptutor.services.learner_state.service import LearnerStateEvent


def synthesize_learning_truth(events: Iterable[LearnerStateEvent]) -> dict[str, Any]:
    relevant = [_event_payload(event) for event in events if _is_learning_evidence(event)]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    improvements: list[dict[str, Any]] = []

    for item in relevant:
        errors = item["payload"].get("error_events") or []
        signal = item["payload"].get("next_training_signal") if isinstance(item["payload"].get("next_training_signal"), dict) else {}
        if not errors and _is_improvement(item["payload"]):
            concept = str(signal.get("concept") or "").strip()
            if concept:
                improvements.append({
                    "concept_id": concept,
                    "event_id": item["event_id"],
                    "observed_at": item["created_at"],
                })
            continue
        for error in errors:
            if not isinstance(error, dict):
                continue
            concept = str(error.get("concept_tag") or signal.get("concept") or "unknown_concept").strip()
            error_code = str(error.get("error_code") or "unknown_error").strip()
            grouped[(concept, error_code)].append(item)

    weak_points: list[dict[str, Any]] = []
    observed_candidates: list[dict[str, Any]] = []
    stale_claims: list[dict[str, Any]] = []

    for (concept, error_code), items in sorted(grouped.items()):
        event_ids = [item["event_id"] for item in items]
        candidate = {
            "concept_id": concept,
            "error_code": error_code,
            "claim": f"{concept} 上反复出现 {error_code} 错因",
            "supporting_event_ids": event_ids,
            "last_observed_at": items[-1]["created_at"],
            "recommended_training": _first_training_signal(items),
        }
        if len(items) >= 2:
            weak_points.append({**candidate, "evidence_level": "L1_repeated"})
        else:
            observed_candidates.append({**candidate, "evidence_level": "L0_observed"})

    improved_concepts = {item["concept_id"] for item in improvements}
    for weak in weak_points:
        if weak["concept_id"] in improved_concepts:
            stale_claims.append({
                "concept_id": weak["concept_id"],
                "error_code": weak["error_code"],
                "reason": "later_training_improved",
                "supporting_event_ids": weak["supporting_event_ids"],
            })

    return {
        "schema_version": 1,
        "generated_by": "nightly_synthesis",
        "subject": "construction_exam_learning_truth",
        "weak_points": weak_points,
        "observed_candidates": observed_candidates,
        "improvement_signals": improvements,
        "stale_claims": stale_claims,
    }


def project_learning_graph(events: Iterable[LearnerStateEvent]) -> dict[str, Any]:
    edges: list[dict[str, Any]] = []
    for event in events:
        if not _is_learning_evidence(event):
            continue
        payload = dict(event.payload_json or {})
        for edge in list(payload.get("typed_edges") or []):
            if not isinstance(edge, dict):
                continue
            edges.append({**edge, "evidence_event_id": event.event_id, "observed_at": event.created_at})
    return {"schema_version": 1, "edges": edges}


def render_learning_truth_summary_md(projection: dict[str, Any]) -> str:
    lines = ["## 学习事实编译", ""]
    weak_points = list(projection.get("weak_points") or [])
    if not weak_points:
        lines.append("- 暂无达到长期画像阈值的稳定薄弱点。")
        return "\n".join(lines).strip()
    for item in weak_points:
        lines.append(
            "- "
            + f"{item.get('concept_id')}: {item.get('error_code')} "
            + f"({item.get('evidence_level')}, evidence={','.join(item.get('supporting_event_ids') or [])})"
        )
    return "\n".join(lines).strip()


def _is_learning_evidence(event: LearnerStateEvent) -> bool:
    return event.source_feature == "construction_grading" and event.memory_kind == "learning_evidence"


def _event_payload(event: LearnerStateEvent) -> dict[str, Any]:
    return {"event_id": event.event_id, "created_at": event.created_at, "payload": dict(event.payload_json or {})}


def _is_improvement(payload: dict[str, Any]) -> bool:
    try:
        max_score = float(payload.get("max_score") or 0)
        score = float(payload.get("score_awarded") or 0)
        return max_score > 0 and score >= max_score and not payload.get("error_events")
    except (TypeError, ValueError):
        return False


def _first_training_signal(items: list[dict[str, Any]]) -> dict[str, Any]:
    for item in items:
        signal = item["payload"].get("next_training_signal")
        if isinstance(signal, dict) and signal:
            return dict(signal)
    return {}
```

- [ ] **Step 3.4: Run synthesis tests**

Run:

```bash
pytest tests/services/learner_state/test_learning_synthesis.py -q
```

Expected:

```text
5 passed
```

## 6. Task 4: LearnerStateService Synthesis Integration

**Files:**

- Modify: `deeptutor/services/learner_state/service.py`
- Modify: `deeptutor/services/learner_state/supabase_writer.py`
- Test: `tests/services/learner_state/test_service.py`
- Test: `tests/services/learner_state/test_supabase_writer.py`

- [ ] **Step 4.1: Add failing service-level synthesis test**

Append to `tests/services/learner_state/test_service.py`:

```python
def test_learner_state_synthesize_learning_truth_dry_run_does_not_enqueue(tmp_path) -> None:
    service = _make_service(tmp_path)
    for index in range(2):
        service.append_memory_event(
            "student_demo",
            source_feature="construction_grading",
            source_id=f"turn-{index}",
            source_bot_id="construction-exam",
            memory_kind="learning_evidence",
            payload_json={
                "event_type": "learning_evidence",
                "question_id": f"q-{index}",
                "question_type": "case",
                "score_awarded": 0,
                "max_score": 1,
                "error_events": [
                    {"error_code": "E02", "concept_tag": "1A432000", "diagnosis": "漏专家论证。"}
                ],
                "next_training_signal": {"concept": "1A432000", "focus": "专家论证程序"},
                "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
            },
        )

    result = service.synthesize_learning_truth("student_demo", dry_run=True)

    assert result["projection"]["weak_points"][0]["evidence_level"] == "L1_repeated"
    assert result["outbox_item"] is None
    assert not service.outbox_service.list_pending("student_demo")
```

Add non-dry run test:

```python
def test_learner_state_synthesize_learning_truth_enqueues_summary_refresh(tmp_path) -> None:
    service = _make_service(tmp_path)
    for index in range(2):
        service.append_memory_event(
            "student_demo",
            source_feature="construction_grading",
            source_id=f"turn-{index}",
            source_bot_id="construction-exam",
            memory_kind="learning_evidence",
            payload_json={
                "event_type": "learning_evidence",
                "question_id": f"q-{index}",
                "question_type": "case",
                "score_awarded": 0,
                "max_score": 1,
                "error_events": [
                    {"error_code": "E02", "concept_tag": "1A432000", "diagnosis": "漏专家论证。"}
                ],
                "next_training_signal": {"concept": "1A432000", "focus": "专家论证程序"},
                "quality": {"evidence_level": "L0_observed", "writeback_eligible": True},
            },
        )

    result = service.synthesize_learning_truth("student_demo", dry_run=False)

    pending = service.outbox_service.list_pending("student_demo")
    assert result["outbox_item"] is not None
    assert pending[0].event_type == "summary_refresh"
    assert (
        pending[0].payload_json["summary_structured_json"]["learning_brain"]["subject"]
        == "construction_exam_learning_truth"
    )
```

- [ ] **Step 4.2: Run tests and verify failure**

Run:

```bash
pytest \
  tests/services/learner_state/test_service.py::test_learner_state_synthesize_learning_truth_dry_run_does_not_enqueue \
  tests/services/learner_state/test_service.py::test_learner_state_synthesize_learning_truth_enqueues_summary_refresh \
  -q
```

Expected:

```text
AttributeError: 'LearnerStateService' object has no attribute 'synthesize_learning_truth'
```

- [ ] **Step 4.3: Extend summary refresh to carry structured projection**

In `deeptutor/services/learner_state/service.py`, change `_enqueue_summary_refresh(...)` signature:

```python
    def _enqueue_summary_refresh(
        self,
        *,
        user_id: str,
        summary_md: str,
        source_feature: str,
        source_id: str,
        source_bot_id: str | None = None,
        summary_structured_json: dict[str, Any] | None = None,
    ) -> LearnerStateOutboxItem:
```

Inside the method, set:

```python
        structured = dict(summary_structured_json or {})
```

Add this key to the outbox payload:

```python
                "summary_structured_json": structured,
```

- [ ] **Step 4.4: Add service synthesis method**

Add to `LearnerStateService`:

```python
    def synthesize_learning_truth(
        self,
        user_id: str,
        *,
        dry_run: bool = True,
        event_limit: int | None = None,
    ) -> dict[str, Any]:
        from deeptutor.services.learner_state.learning_synthesis import (
            project_learning_graph,
            render_learning_truth_summary_md,
            synthesize_learning_truth,
        )

        normalized = _normalize_user_id(user_id)
        events = self.list_memory_events(normalized, limit=event_limit)
        projection = synthesize_learning_truth(events)
        graph = project_learning_graph(events)
        projection["typed_graph"] = graph
        summary_md = render_learning_truth_summary_md(projection)
        if dry_run:
            return {"projection": projection, "summary_md": summary_md, "outbox_item": None}
        outbox_item = self._enqueue_summary_refresh(
            user_id=normalized,
            summary_md=summary_md,
            source_feature="learning_synthesis",
            source_id="nightly_synthesis",
            source_bot_id=None,
            summary_structured_json=projection,
        )
        return {"projection": projection, "summary_md": summary_md, "outbox_item": outbox_item}
```

- [ ] **Step 4.5: Preserve structured summary in Supabase writer**

In `deeptutor/services/learner_state/supabase_writer.py`, update `_build_summary_refresh_row(...)`.

Replace the `summary_structured_json` value with:

```python
            "summary_structured_json": dict(payload.get("summary_structured_json") or {
                "source_feature": str(payload.get("source_feature") or "").strip(),
                "source_id": str(payload.get("source_id") or "").strip(),
                "source_bot_id": self._null_if_blank(payload.get("source_bot_id")),
            }),
```

- [ ] **Step 4.6: Add Supabase writer test**

In `tests/services/learner_state/test_supabase_writer.py`, add a test next to existing summary refresh coverage:

```python
def test_write_item_summary_refresh_preserves_structured_learning_truth() -> None:
    writer = _make_writer()
    item = _item(
        event_type="summary_refresh",
        dedupe_key="summary:learning-synthesis",
        payload={
            "user_id": "student_demo",
            "summary_md": "## 学习事实编译",
            "source_feature": "learning_synthesis",
            "source_id": "nightly_synthesis",
            "summary_structured_json": {
                "subject": "construction_exam_learning_truth",
                "weak_points": [{"concept_id": "1A432000"}],
            },
        },
    )

    writer.write_item(item)

    request = writer.client.requests[-1]
    assert request["path"] == "/rest/v1/learner_summaries"
    learning_brain = request["json"][0]["summary_structured_json"]["learning_brain"]
    assert learning_brain["subject"] == "construction_exam_learning_truth"
    assert learning_brain["weak_points"][0]["concept_id"] == "1A432000"
```

If the test helper names differ in this file, adapt only to the existing helper names. Keep the assertions exactly about preserving `summary_structured_json`.

- [ ] **Step 4.7: Run learner-state tests**

Run:

```bash
pytest \
  tests/services/learner_state/test_learning_synthesis.py \
  tests/services/learner_state/test_service.py::test_learner_state_synthesize_learning_truth_dry_run_does_not_enqueue \
  tests/services/learner_state/test_service.py::test_learner_state_synthesize_learning_truth_enqueues_summary_refresh \
  tests/services/learner_state/test_supabase_writer.py::test_write_item_summary_refresh_preserves_structured_learning_truth \
  -q
```

Expected:

```text
all selected tests pass
```

## 7. Task 5: Dry-run Nightly Synthesis Script

**Files:**

- Create: `scripts/run_learning_synthesis.py`
- Test: `tests/scripts/test_run_learning_synthesis.py`

- [ ] **Step 5.1: Write failing CLI dry-run test**

Create `tests/scripts/test_run_learning_synthesis.py`:

```python
import json
import subprocess
import sys
from pathlib import Path


def test_run_learning_synthesis_dry_run_outputs_projection(tmp_path: Path) -> None:
    env_root = tmp_path / "repo"
    env_root.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_learning_synthesis.py",
            "--user-id",
            "student_demo",
            "--dry-run",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] in {"ok", "no_events"}
    assert payload["user_id"] == "student_demo"
    assert payload["dry_run"] is True
```

- [ ] **Step 5.2: Run test and verify failure**

Run:

```bash
pytest tests/scripts/test_run_learning_synthesis.py -q
```

Expected:

```text
FAIL because scripts/run_learning_synthesis.py does not exist
```

- [ ] **Step 5.3: Implement script**

Create `scripts/run_learning_synthesis.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from deeptutor.services.learner_state import get_learner_state_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Run learner learning-truth synthesis for one user.")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--event-limit", type=int, default=None)
    args = parser.parse_args()

    service = get_learner_state_service()
    events = service.list_memory_events(args.user_id, limit=args.event_limit)
    result = service.synthesize_learning_truth(
        args.user_id,
        dry_run=bool(args.dry_run),
        event_limit=args.event_limit,
    )
    payload: dict[str, Any] = {
        "status": "ok" if events else "no_events",
        "user_id": args.user_id,
        "dry_run": bool(args.dry_run),
        "event_count": len(events),
        "projection": result["projection"],
        "outbox_item_id": getattr(result.get("outbox_item"), "id", None),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5.4: Run CLI tests**

Run:

```bash
pytest tests/scripts/test_run_learning_synthesis.py -q
python scripts/run_learning_synthesis.py --user-id student_demo --dry-run
```

Expected:

```text
pytest passes
script prints valid JSON with status ok or no_events
```

## 8. Task 6: Deep Question Consumption Of Compiled Signals

**Files:**

- Modify: `deeptutor/capabilities/deep_question.py`
- Test: `tests/core/test_deep_question_submission_grading.py`

- [ ] **Step 6.1: Add failing helper test for compiled training signal**

Add to `tests/core/test_deep_question_submission_grading.py`:

```python
def test_related_generation_anchor_accepts_compiled_learning_truth_signal() -> None:
    context = {
        "compiled_learning_truth": {
            "weak_points": [
                {
                    "concept_id": "1A432000",
                    "error_code": "E02",
                    "evidence_level": "L1_repeated",
                    "recommended_training": {
                        "concept": "1A432000",
                        "focus": "专家论证程序",
                        "mode": "case_repair",
                    },
                }
            ]
        }
    }

    anchor = _question_context_generation_anchor(context)

    assert "1A432000" in anchor
    assert "专家论证程序" in anchor
    assert "E02" in anchor
```

If `_question_context_generation_anchor` is not imported in this test file, import it from `deeptutor.capabilities.deep_question`.

- [ ] **Step 6.2: Run test and verify failure**

Run:

```bash
pytest tests/core/test_deep_question_submission_grading.py::test_related_generation_anchor_accepts_compiled_learning_truth_signal -q
```

Expected before implementation:

```text
FAIL because compiled_learning_truth is ignored by _question_context_generation_anchor
```

- [ ] **Step 6.3: Add helper in `deep_question.py`**

Add near `_training_signal_text_from_context(...)`:

```python
def _compiled_training_signal_text_from_context(question_context: dict[str, Any]) -> str:
    truth = question_context.get("compiled_learning_truth")
    if not isinstance(truth, dict):
        return ""
    weak_points = list(truth.get("weak_points") or [])
    parts: list[str] = []
    for item in weak_points[:3]:
        if not isinstance(item, dict):
            continue
        evidence_level = str(item.get("evidence_level") or "").strip()
        if evidence_level not in {"L1_repeated", "L2_confirmed", "L3_mastery_signal"}:
            continue
        concept = _compact_text(item.get("concept_id"))
        error_code = _compact_text(item.get("error_code"))
        training = item.get("recommended_training") if isinstance(item.get("recommended_training"), dict) else {}
        focus = _compact_text(training.get("focus"))
        mode = _compact_text(training.get("mode"))
        signal_parts = []
        if concept:
            signal_parts.append(f"concept={concept}")
        if focus:
            signal_parts.append(f"focus={focus}")
        if mode:
            signal_parts.append(f"mode={mode}")
        if error_code:
            signal_parts.append(f"error_codes={error_code}")
        if signal_parts:
            parts.append("；".join(signal_parts))
    return " | ".join(parts)
```

In `_question_context_generation_anchor(...)`, after appending normal training signal text for each item, add:

```python
        _append_unique(training_parts, _compiled_training_signal_text_from_context(item))
```

- [ ] **Step 6.4: Run focused tests**

Run:

```bash
pytest \
  tests/core/test_deep_question_submission_grading.py::test_related_generation_anchor_uses_next_training_signal \
  tests/core/test_deep_question_submission_grading.py::test_related_generation_anchor_accepts_compiled_learning_truth_signal \
  -q
```

Expected:

```text
2 passed
```

## 9. Task 7: Index And Contract Guard Check

**Files:**

- Modify: `docs/plan/INDEX.md`

- [ ] **Step 7.1: Register implementation plan**

Update these places in `docs/plan/INDEX.md`:

1. Main overview row for `学习事实编译 / Evidence-first Memory`.
2. `Learner State / Memory / Overlay` table.
3. `鲁班智考 / 因材施教` table.
4. `Implementation Plan` list.

Use this status:

```text
Implementation Plan | Proposed P0/P1
```

- [ ] **Step 7.2: Run path check**

Run:

```bash
rg -n 'deeptutor/d[o]c/plan|`/d[o]c/plan|d[o]c/plan/[0-9]|d[o]cs/d[o]cs/plan' docs/plan contracts/index.yaml AGENTS.md
```

Expected:

```text
no output
```

- [ ] **Step 7.3: Run final focused test set**

Run:

```bash
pytest \
  tests/services/construction_grading/test_learning_evidence.py \
  tests/services/construction_grading/test_audit_and_writeback.py \
  tests/services/learner_state/test_learning_synthesis.py \
  tests/services/learner_state/test_service.py::test_learner_state_context_renders_learning_evidence_events \
  tests/services/learner_state/test_service.py::test_learner_state_synthesize_learning_truth_dry_run_does_not_enqueue \
  tests/services/learner_state/test_service.py::test_learner_state_synthesize_learning_truth_enqueues_summary_refresh \
  tests/services/learner_state/test_supabase_writer.py::test_write_item_summary_refresh_preserves_structured_learning_truth \
  tests/scripts/test_run_learning_synthesis.py \
  tests/core/test_deep_question_submission_grading.py::test_related_generation_anchor_accepts_compiled_learning_truth_signal \
  -q
```

Expected:

```text
all selected tests pass
```

## 10. Task 8: Web QA Handoff

This task is not required before code review, but it is required before claiming product behavior is done.

**Files:**

- Read: [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md)
- Read: [2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md](2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md)
- Use: `/wechat-harness` local QA entry

- [ ] **Step 8.1: Run backend focused tests**

Run:

```bash
pytest \
  tests/api/test_unified_ws_turn_runtime.py \
  tests/core/test_deep_question_submission_grading.py \
  tests/services/construction_grading/test_audit_and_writeback.py \
  tests/services/learner_state/test_learning_synthesis.py \
  -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 8.2: Run Web quick QA**

Start the local dev stack according to the current repo runbook, then open `/wechat-harness`.

Exercise this flow:

1. Submit or select one construction case question.
2. Provide an answer that misses a known rubric point.
3. Verify visible grading output shows score, missed point, rewrite, and next training suggestion.
4. Run `python scripts/run_learning_synthesis.py --user-id <same-user-id> --dry-run`.
5. Verify JSON output contains `construction_exam_learning_truth`.

Expected:

```text
Web QA proves user-visible grading still works and synthesis can read the resulting evidence events.
```

This Web check does not replace 微信小程序真入口 smoke if mini-program files are changed later.

## 11. Stop Rules During Execution

Stop and report instead of patching around the issue when any of these happen:

1. `construction_grading_result` is missing from the grading flow.
2. Evidence must be inferred from final Markdown rather than structured grading metadata.
3. A proposed fix requires a new learner-state table before P0 proves the projection shape.
4. A proposed fix wants to query RAG outside `RAGService`.
5. The only way to make a test pass is to let `L0_observed` enter stable weak points.
6. Supabase writer cannot preserve `summary_structured_json`; fix writer shape before adding a new storage path.

## 12. Done Definition

P0 is done only when all are true:

1. `write_grading_error_events(...)` writes canonical `learning_evidence` through `LearnerStateService`.
2. Existing learner context can render both legacy grading events and canonical learning evidence.
3. `synthesize_learning_truth(...)` keeps single observations out of stable truth and promotes repeated errors to `L1_repeated`.
4. Typed edge projection can be produced from evidence events.
5. Summary refresh outbox preserves `summary_structured_json`.
6. Dry-run CLI returns valid JSON and never writes.
7. Deep question can consume compiled training signals without creating a new router.
8. `docs/plan/INDEX.md` points to this implementation plan.
9. Focused pytest suite passes.
10. Product completion is not claimed until `/wechat-harness` or mini-program smoke validates the visible chain.

## 13. v0.2 Strengthening Addendum

The first version is safe, but it can still degrade into a shallow weak-point list. Before implementation starts, fold the following tasks into the execution queue. They keep the scope P0/P1, but make the GBrain absorption real enough for 建筑实务教培.

### 13.1 Task 9: Object-Level Compiled Truth

**Purpose:** Make compiled truth object-level, not only learner-level.

**Files:**

- Modify: `deeptutor/services/learner_state/learning_synthesis.py`
- Test: `tests/services/learner_state/test_learning_synthesis.py`

- [ ] **Step 9.1: Add failing test for `compiled_objects`**

Add a test that feeds two repeated learning evidence events for the same concept/rubric/error and asserts:

```python
def test_synthesis_builds_object_level_compiled_truth() -> None:
    projection = synthesize_learning_truth([
        _learning_event(
            "evt1",
            concept_id="1A432000",
            question_id="case_001",
            rubric_item_id="r1",
            error_code="E02",
            observed_at="2026-05-18T10:00:00Z",
        ),
        _learning_event(
            "evt2",
            concept_id="1A432000",
            question_id="case_002",
            rubric_item_id="r9",
            error_code="E02",
            observed_at="2026-05-18T12:00:00Z",
        ),
    ])

    concept = projection["compiled_objects"]["concept:1A432000"]
    assert concept["object_type"] == "concept"
    assert concept["evidence_level"] == "L1_repeated"
    assert concept["supporting_event_ids"] == ["evt1", "evt2"]
    assert concept["timeline_refs"][0]["event_id"] == "evt1"

    error = projection["compiled_objects"]["error:1A432000:E02"]
    assert error["supporting_event_ids"] == ["evt1", "evt2"]
```

- [ ] **Step 9.2: Implement `compiled_objects` in synthesis**

Implementation rule:

1. Build stable object keys: `concept:<id>`, `question:<id>`, `rubric_item:<question_id>:<id>`, `error:<concept_id>:<error_code>`, `submission:<turn_id>`.
2. Each object stores `current_truth`, `evidence_level`, `confidence`, `supporting_event_ids`, `conflicting_event_ids`, `superseded_by_event_ids`, `valid_since`, `last_observed_at`, `decay_state`, `timeline_refs`.
3. `weak_points` can remain as a convenience view, but the authoritative projection for Teaching Policy must be `compiled_objects`.

- [ ] **Step 9.3: Add fail-closed behavior**

If an event lacks `question_id`, do not create question/rubric truth. If it lacks `concept_id`, do not create concept truth. Preserve the raw event in observed candidates.

Run:

```bash
pytest tests/services/learner_state/test_learning_synthesis.py::test_synthesis_builds_object_level_compiled_truth -q
```

### 13.2 Task 10: Full Typed Graph Chain

**Purpose:** Ensure graph projection supports `题目 -> 知识点 -> 采分点 -> 常见错因 -> 学生作答 -> 下一步训练`.

**Files:**

- Modify: `deeptutor/services/construction_grading/learning_evidence.py`
- Modify: `deeptutor/services/learner_state/learning_synthesis.py`
- Test: `tests/services/construction_grading/test_learning_evidence.py`
- Test: `tests/services/learner_state/test_learning_synthesis.py`

- [ ] **Step 10.1: Add failing evidence payload test**

Expected edge types from a complete grading result:

```python
expected_edge_types = {
    "question_tests_concept",
    "question_has_rubric_item",
    "rubric_item_maps_to_error",
    "submission_answered_question",
    "submission_missed_rubric_item",
    "submission_triggered_error",
}
assert expected_edge_types.issubset({edge["edge_type"] for edge in payload["typed_edges"]})
```

- [ ] **Step 10.2: Add graph query helper test**

Add a small pure helper:

```python
def find_next_training_targets(projection: dict[str, Any], *, concept_id: str, error_code: str) -> list[dict[str, Any]]:
    ...
```

Test:

```python
def test_graph_can_trace_error_to_next_training() -> None:
    projection = synthesize_learning_truth([...])
    targets = find_next_training_targets(projection, concept_id="1A432000", error_code="E02")
    assert targets[0]["concept_id"] == "1A432000"
    assert targets[0]["error_code"] == "E02"
    assert targets[0]["reason_event_ids"] == ["evt1", "evt2"]
```

- [ ] **Step 10.3: Enforce edge metadata**

Every edge must contain:

```text
edge_type, from, to, evidence_event_id, source_feature, observed_at, confidence
```

Reject or drop malformed edges during projection; do not repair them with guessed IDs.

Run:

```bash
pytest \
  tests/services/construction_grading/test_learning_evidence.py \
  tests/services/learner_state/test_learning_synthesis.py::test_graph_can_trace_error_to_next_training \
  -q
```

### 13.3 Task 11: Evidence Source Gates

**Purpose:** Prevent student profiles from being written from chat impressions or incomplete evidence.

**Files:**

- Modify: `deeptutor/services/construction_grading/learning_evidence.py`
- Modify: `deeptutor/services/learner_state/learning_synthesis.py`
- Test: `tests/services/construction_grading/test_learning_evidence.py`
- Test: `tests/services/learner_state/test_learning_synthesis.py`

- [ ] **Step 11.1: Add evidence refs to payload**

`learning_evidence` must include `evidence_refs` with typed entries:

```json
[
  {"source_type": "grading_result", "source_id": "grading_turn_abc"},
  {"source_type": "active_question", "source_id": "question_case_001"},
  {"source_type": "rag_evidence", "source_id": "rag_chunk_789"},
  {"source_type": "answer_history", "source_id": "turn_abc"},
  {"source_type": "trace", "source_id": "langfuse_trace_xyz"}
]
```

- [ ] **Step 11.2: Add evidence cap tests**

Required tests:

```python
def test_missing_question_id_caps_evidence_at_l0() -> None: ...
def test_rag_degraded_caps_evidence_at_l0() -> None: ...
def test_chat_only_event_is_not_learning_evidence() -> None: ...
def test_manual_correction_supersedes_automatic_claim() -> None: ...
```

Rules:

1. Missing question identity: max `L0_observed`.
2. Missing grading result: not eligible for stable learning truth.
3. RAG degraded or citation missing: max `L0_observed`.
4. Open-skill grading without manual confirmation: max `L1_repeated`.
5. Manual correction supersedes automatic claim and becomes timeline evidence.

- [ ] **Step 11.3: Add stop condition to writeback**

If the system can only infer evidence from final Markdown text, stop and do not write `learning_evidence`. Fix structured grading metadata first.

Run:

```bash
pytest \
  tests/services/construction_grading/test_learning_evidence.py \
  tests/services/learner_state/test_learning_synthesis.py \
  -q
```

### 13.4 Task 12: Synthesis Run Audit, Conflict, And Decay

**Purpose:** Make nightly synthesis idempotent, auditable, and reversible.

**Files:**

- Modify: `deeptutor/services/learner_state/learning_synthesis.py`
- Modify: `scripts/run_learning_synthesis.py`
- Test: `tests/services/learner_state/test_learning_synthesis.py`
- Test: `tests/scripts/test_run_learning_synthesis.py`

- [ ] **Step 12.1: Add synthesis audit object**

`synthesize_learning_truth(...)` should return:

```json
{
  "synthesis_run": {
    "synthesis_run_id": "syn_test",
    "input_event_count": 2,
    "input_event_ids_hash": "sha256:...",
    "previous_projection_hash": "sha256:...",
    "output_projection_hash": "sha256:...",
    "created_claim_count": 1,
    "updated_claim_count": 0,
    "decayed_claim_count": 0,
    "conflict_count": 0,
    "manual_override_count": 0,
    "status": "dry_run_ok"
  }
}
```

- [ ] **Step 12.2: Add idempotency tests**

Required tests:

```python
def test_synthesis_is_idempotent_for_same_inputs() -> None: ...
def test_synthesis_marks_conflicting_evidence_without_overwriting_claim() -> None: ...
def test_synthesis_decays_weak_point_after_improvement() -> None: ...
def test_synthesis_records_manual_override_count() -> None: ...
```

- [ ] **Step 12.3: CLI dry-run diff**

`python scripts/run_learning_synthesis.py --user-id <id> --dry-run` must print:

1. `created_claim_count`
2. `updated_claim_count`
3. `decayed_claim_count`
4. `conflict_count`
5. `manual_override_count`
6. `output_projection_hash`

Dry-run must never enqueue summary refresh.

Run:

```bash
pytest \
  tests/services/learner_state/test_learning_synthesis.py \
  tests/scripts/test_run_learning_synthesis.py \
  -q
```

### 13.5 Updated P0 Acceptance Bar

After this addendum, P0 is not accepted unless:

1. `compiled_objects` exists and has at least concept, question, rubric, error object projections where source data permits.
2. The graph projection can trace from error to next training without vector search.
3. All stable claims have `supporting_event_ids`.
4. Incomplete evidence fails closed into `L0_observed` or no write.
5. Synthesis is idempotent for identical inputs.
6. Manual correction can supersede an automatic claim.
7. Improvements decay old weak points instead of deleting evidence.
8. `/wechat-harness` proves the visible chain: answer -> grading -> evidence event -> dry-run synthesis -> next training signal.
