# DeepTutor Learning Fact Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade DeepTutor retrieval from "find relevant chunks" to source-aware learning fact retrieval with explicit query plans, provenance features, compiled truth sources, typed graph expansion, and maintenance workflows while preserving `RAGService` as the only retrieval entry.

**Architecture:** Keep `/api/v1/ws`, `rag`, and `RAGService` as the only online grounding path. Add pure, testable helpers under `deeptutor/services/rag/` for retrieval planning, compiled truth materialization, provenance scoring, and maintenance audits; wire them into `SupabasePipeline` as additional source groups, not as a new provider or mode. `LearnerStateService` remains the authority for compiled learning truth; `SupabasePipeline` may consume a projection passed in request context but must not become a learner-state writer.

**Tech Stack:** Python dataclasses and pure functions, existing `SupabasePipeline`, existing `LearnerStateService.synthesize_learning_truth`, existing `evidence_bundle`, pytest, optional live `/api/v1/ws`, Langfuse/ClickHouse trace verification, `/wechat-harness` only for visible QA.

---

## 0. Current Baseline

This plan is a child plan of:

- [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md)
- [2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md](2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md)
- [contracts/rag.md](../../contracts/rag.md)

Existing useful pieces:

| Existing piece | Current role | Keep / change |
| --- | --- | --- |
| `deeptutor/services/rag/service.py` | Single RAG entry | Keep as entry; only normalize richer `evidence_bundle`. |
| `deeptutor/services/rag/pipelines/supabase.py` | Read-only Supabase hybrid retrieval pipeline | Add source-aware compiled truth group and provenance features here. |
| `deeptutor/services/rag/pipelines/supabase_strategy.py` | Query rewrite, source selection, second pass, rerank helpers | Keep as stable helper module; `retrieval_plan.py` may import its existing helpers, but this file must not import `retrieval_plan.py` to avoid a circular dependency. |
| `deeptutor/services/learner_state/learning_synthesis.py` | Compiled truth, typed graph, weak point projection | Treat as the only compiled learning truth authority. |
| `deeptutor/capabilities/deep_question.py` | Consumes compiled training signal | Keep as practice continuity owner; do not turn it into a retrieval router. |
| `tests/services/rag/test_rag_pipelines.py` | Supabase RAG behavior tests | Extend for compiled truth and provenance. |
| `tests/services/rag/test_supabase_strategy.py` | Query strategy tests | Extend for explicit retrieval intent and source plan trace. |
| `tests/services/learner_state/test_learning_synthesis.py` | Learning graph and compiled truth tests | Extend only for graph helpers needed by retrieval. |

## 1. Design Gate

Do not start coding unless this gate is answered in the implementation PR description.

| Gate | Decision |
| --- | --- |
| Thin wrapper / fat skill split | API, TutorBot tools, and `/api/v1/ws` remain thin wrappers. RAG planning/ranking lives in `deeptutor/services/rag/*`; compiled truth remains in `LearnerStateService` / `learning_synthesis.py`. |
| One business fact | A retrieval result must expose why each source was selected, which authority it came from, which evidence supports it, and whether it is fresh enough for teaching. |
| One authority | `RAGService` is the only online retrieval entry; `SupabasePipeline` owns retrieval fusion; `LearnerStateService` owns compiled truth; `questions_bank` owns exact answer facts. |
| Competing authorities to demote | Prompt-only source selection, ad hoc regex in wrappers, free-form chat summary as learner truth, and any direct `kb_chunks` or learner-state lookup outside `RAGService`. |
| Canonical path | caller context -> `RAGService.search(...)` -> `SupabasePipeline.search(...)` -> retrieval plan -> source-group fanout including optional compiled truth docs -> provenance-aware fusion -> `evidence_bundle` -> responding layer. |
| Additive proof | New dataclasses and helpers are allowed only because current `source_plan` is not rich enough to express retrieval intent, provenance features, and compiled truth source groups in a replayable form. |
| LLM vs deterministic | Query plan and source weighting are deterministic. LLM remains only in responding/rerank provider where already present. No LLM classifier is added. |

## 2. Non-Goals

This plan does not:

1. Import or run `gbrain`.
2. Create a second vector store, graph database, or RAG provider.
3. Add `learning brain mode`, `grounded mode`, or a new WebSocket route.
4. Let compiled truth outrank a full `exact_question` hit.
5. Let `SupabasePipeline` write learner memory.
6. Run nightly synthesis inline during an online turn.
7. Replace `questions_bank`, `standard`, `textbook`, or existing `kb_chunks` source authority.

## 3. Target Retrieval Contract

Every successful retrieval should make these facts visible in `evidence_bundle`:

```json
{
  "retrieval_plan": {
    "schema_version": 1,
    "intent": "weak_point_review",
    "query_shape": "concept_like",
    "primary_query": "我老是案例题采分点漏写怎么办",
    "source_groups": [
      {"name": "compiled_learning_truth", "enabled": true, "reason": "weak_point_review"},
      {"name": "questions_bank", "enabled": true, "reason": "training_question_needed"},
      {"name": "standard", "enabled": true, "reason": "authority_grounding"}
    ],
    "expanded_queries": ["案例题 采分点 漏写 训练", "弱点 采分点 错因"],
    "plan_id": "stable-short-hash"
  },
  "ranking_trace": {
    "fusion": "weighted_rrf_with_provenance",
    "authority_order": ["exact_question", "standard", "questions_bank", "compiled_learning_truth", "textbook", "exam"],
    "provenance_features": [
      {"chunk_id": "compiled-truth:weak:1A432000:E02", "evidence_level": "L1_repeated", "freshness": "recent", "manual_confirmed": false}
    ]
  }
}
```

Authority order:

1. Full coverage `exact_question`.
2. Exact standard clause / standard precision.
3. `questions_bank` and active question object.
4. Compiled learning truth and learner weak point projection.
5. Textbook / exam / ordinary semantic chunks.

Compiled truth can boost personalization and training relevance; it cannot rewrite canonical answers.

## 4. File Structure

Create:

- `deeptutor/services/rag/retrieval_plan.py`
  - Dataclasses and deterministic `build_retrieval_plan(...)`.
  - Maps existing `query_shape`, `source_plan`, upstream `intent/question_type/routing_metadata`, and optional learner context into a replayable plan.
- `deeptutor/services/rag/compiled_truth_source.py`
  - Pure materializer from `summary_structured_json.learning_brain` / compiled projection to retrieval documents.
  - No storage reads and no writes.
- `deeptutor/services/rag/provenance.py`
  - Provenance feature extraction and source-aware boost/penalty functions.
- `deeptutor/services/rag/maintenance.py`
  - Offline audit helpers for retrieval miss, citation, stale weak point, rubric coverage, and eval case generation.
- `scripts/run_learning_retrieval_maintenance.py`
  - Dry-run capable command wrapper around `maintenance.py`.
- `tests/services/rag/test_retrieval_plan.py`
- `tests/services/rag/test_compiled_truth_source.py`
- `tests/services/rag/test_provenance.py`
- `tests/services/rag/test_learning_fact_retrieval_pipeline.py`
- `tests/scripts/test_run_learning_retrieval_maintenance.py`
- `tests/fixtures/learning_fact_retrieval_cases.json`
- `deeptutor/tutorbot/skills/retrieval-maintenance/SKILL.md`

Modify:

- `deeptutor/services/rag/pipelines/supabase.py`
  - Build `retrieval_plan`.
  - Add compiled truth source group to fusion input when caller passes compiled truth context.
  - Add provenance-aware ranking metadata to `evidence_bundle`.
  - Preserve exact-question authority.
- `deeptutor/services/rag/pipelines/supabase_strategy.py`
  - Keep compatibility functions stable. Do not import `retrieval_plan.py` from this module.
- `deeptutor/services/rag/service.py`
  - Preserve `retrieval_plan` and `ranking_trace` in fallback `evidence_bundle`.
- `deeptutor/tutorbot/agent/loop.py`
  - If compiled truth is already present in runtime learner context, pass it to `rag` calls as context metadata.
  - Do not query learner state directly from tool wrapper.
- `tests/services/rag/test_rag_pipelines.py`
  - Add regression cases for exact authority vs compiled truth boost.
- `docs/plan/INDEX.md`
  - Register this child plan under Learning Brain and 鲁班智考.

## 5. Baseline Verification

- [ ] **Step 5.1: Run current RAG and Learning Brain tests**

Run:

```bash
pytest \
  tests/services/rag/test_supabase_strategy.py \
  tests/services/rag/test_rag_pipelines.py \
  tests/services/learner_state/test_learning_synthesis.py \
  tests/core/test_deep_question_submission_grading.py \
  -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5.2: If baseline fails, stop**

If any baseline fails, fix the existing authority path first. Do not start this plan on a broken RAG or compiled-truth baseline.

## 6. Task 1: Explicit Retrieval Plan

**Purpose:** Turn current query understanding into a durable, replayable plan.

**Files:**

- Create: `deeptutor/services/rag/retrieval_plan.py`
- Test: `tests/services/rag/test_retrieval_plan.py`
- Test: `tests/services/rag/test_supabase_strategy.py`

- [ ] **Step 1.1: Write tests for retrieval intent and source groups**

Create `tests/services/rag/test_retrieval_plan.py`:

```python
from deeptutor.services.rag.retrieval_plan import build_retrieval_plan


def test_build_retrieval_plan_for_standard_clause() -> None:
    plan = build_retrieval_plan(
        query="GB 50345-2015 第3.0.1条对屋面防水等级怎么规定",
        include_questions_default=True,
    )

    assert plan.intent == "standard_clause"
    assert plan.query_shape == "standard_like"
    assert plan.source_groups["standard"].enabled is True
    assert plan.source_groups["standard_code_exact"].enabled is True
    assert plan.source_groups["questions_bank"].enabled is False
    assert "standard_code" in plan.reasons


def test_build_retrieval_plan_for_weak_point_review() -> None:
    plan = build_retrieval_plan(
        query="我老是案例题采分点漏写怎么办",
        include_questions_default=True,
        routing_metadata={"compiled_learning_truth_available": True},
    )

    assert plan.intent == "weak_point_review"
    assert plan.source_groups["compiled_learning_truth"].enabled is True
    assert plan.source_groups["questions_bank"].enabled is True
    assert plan.source_groups["standard"].enabled is True
    assert "weak_point_terms" in plan.reasons


def test_build_retrieval_plan_for_exact_question_keeps_exact_first() -> None:
    plan = build_retrieval_plan(
        query="单选题：确定屋面防水工程的防水等级应根据什么 A 建筑物类别 B 建筑物用途",
        include_questions_default=True,
        question_type="single_choice",
    )

    assert plan.intent == "exact_question"
    assert plan.exact_question_first is True
    assert plan.source_groups["question_exact_text"].enabled is True
    assert plan.authority_order[0] == "exact_question"
```

- [ ] **Step 1.2: Run tests and verify they fail**

Run:

```bash
pytest tests/services/rag/test_retrieval_plan.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.rag.retrieval_plan'
```

- [ ] **Step 1.3: Implement retrieval plan dataclasses and builder**

Create `deeptutor/services/rag/retrieval_plan.py`:

```python
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from deeptutor.services.rag.pipelines.supabase_strategy import (
    classify_query_shape,
    extract_standard_codes,
    is_question_like_query,
    select_sources,
)


_WEAK_POINT_TERMS = ("老是", "总是", "反复", "薄弱", "错因", "漏写", "丢分", "采分点", "怎么练")
_TRAINING_TERMS = ("下一题", "再练", "变式", "训练", "刷题", "巩固")


@dataclass(slots=True)
class RetrievalSourceGroup:
    name: str
    enabled: bool
    reason: str = ""
    weight_hint: float = 1.0

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "reason": self.reason,
            "weight_hint": self.weight_hint,
        }


@dataclass(slots=True)
class RetrievalPlan:
    query: str
    intent: str
    query_shape: str
    source_groups: dict[str, RetrievalSourceGroup]
    authority_order: list[str]
    expanded_queries: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    exact_question_first: bool = False

    @property
    def plan_id(self) -> str:
        basis = "|".join([
            self.intent,
            self.query_shape,
            self.query,
            ",".join(name for name, group in sorted(self.source_groups.items()) if group.enabled),
        ])
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "plan_id": self.plan_id,
            "query": self.query,
            "intent": self.intent,
            "query_shape": self.query_shape,
            "source_groups": [group.to_trace_dict() for group in self.source_groups.values()],
            "authority_order": list(self.authority_order),
            "expanded_queries": list(self.expanded_queries),
            "reasons": list(self.reasons),
            "exact_question_first": self.exact_question_first,
        }


def build_retrieval_plan(
    query: str,
    *,
    include_questions_default: bool,
    intent: str = "",
    question_type: str = "",
    routing_metadata: dict[str, Any] | None = None,
) -> RetrievalPlan:
    text = str(query or "").strip()
    routing = routing_metadata if isinstance(routing_metadata, dict) else {}
    shape = classify_query_shape(text)
    source_plan = select_sources(
        text,
        include_questions_default=include_questions_default,
        intent=intent,
        question_type=question_type,
        routing_metadata=routing,
    )
    reasons = list(source_plan.selection_reasons or [])
    explicit_intent = _classify_retrieval_intent(
        text,
        query_shape=shape,
        question_type=question_type,
        upstream_intent=intent,
        routing_metadata=routing,
    )
    if explicit_intent == "weak_point_review":
        reasons.append("weak_point_terms")
    if extract_standard_codes(text):
        reasons.append("standard_code")

    compiled_available = bool(routing.get("compiled_learning_truth_available"))
    compiled_enabled = compiled_available and explicit_intent in {
        "weak_point_review",
        "next_training",
        "rubric_lookup",
        "concept_explanation",
    }
    question_enabled = source_plan.search_questions_bank or explicit_intent in {"exact_question", "next_training"}

    source_groups = {
        "question_exact_text": RetrievalSourceGroup("question_exact_text", explicit_intent == "exact_question", "exact_probe", 4.2),
        "question_exact_vector": RetrievalSourceGroup("question_exact_vector", explicit_intent == "exact_question", "exact_probe", 3.4),
        "standard_code_exact": RetrievalSourceGroup("standard_code_exact", bool(extract_standard_codes(text)), "standard_code", 3.0),
        "standard_precision": RetrievalSourceGroup("standard_precision", source_plan.search_standard_chunks, "standard_grounding", 2.2),
        "standard": RetrievalSourceGroup("standard", source_plan.search_standard_chunks, "authority_grounding", 1.4),
        "questions_bank": RetrievalSourceGroup("questions_bank", question_enabled, "question_or_training", 1.5 if explicit_intent in {"exact_question", "next_training"} else 0.4),
        "compiled_learning_truth": RetrievalSourceGroup("compiled_learning_truth", compiled_enabled, explicit_intent, 1.15),
        "learner_weak_point": RetrievalSourceGroup("learner_weak_point", compiled_enabled and explicit_intent in {"weak_point_review", "next_training"}, explicit_intent, 1.25),
        "textbook": RetrievalSourceGroup("textbook", source_plan.search_textbook_chunks, "explanation", 1.0),
        "exam": RetrievalSourceGroup("exam", source_plan.search_exam_chunks, "exam_context", 0.7),
    }
    expanded_queries = _plan_expansions(text, explicit_intent)
    return RetrievalPlan(
        query=text,
        intent=explicit_intent,
        query_shape=shape,
        source_groups=source_groups,
        authority_order=[
            "exact_question",
            "standard_code_exact",
            "standard_precision",
            "standard",
            "questions_bank",
            "compiled_learning_truth",
            "learner_weak_point",
            "textbook",
            "exam",
        ],
        expanded_queries=expanded_queries,
        reasons=reasons,
        exact_question_first=explicit_intent == "exact_question",
    )


def _classify_retrieval_intent(
    query: str,
    *,
    query_shape: str,
    question_type: str,
    upstream_intent: str,
    routing_metadata: dict[str, Any],
) -> str:
    text = str(query or "").strip()
    if query_shape == "standard_like" or extract_standard_codes(text):
        return "standard_clause"
    if any(term in text for term in _TRAINING_TERMS):
        return "next_training"
    if any(term in text for term in _WEAK_POINT_TERMS):
        return "weak_point_review"
    if query_shape == "case_like":
        return "case_grading_context"
    if question_type or upstream_intent == "answer_questions" or is_question_like_query(text):
        return "exact_question"
    if "采分点" in text or "rubric" in text.lower():
        return "rubric_lookup"
    if routing_metadata.get("preferred_intent"):
        return str(routing_metadata["preferred_intent"])
    return "concept_explanation"


def _plan_expansions(query: str, intent: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(query or "").strip())
    if not text:
        return []
    if intent == "weak_point_review":
        return [f"{text} 错因 采分点", f"{text} 训练 复盘"]
    if intent == "next_training":
        return [f"{text} 变式训练", f"{text} 相似题"]
    if intent == "rubric_lookup":
        return [f"{text} 采分点 扣分红线", f"{text} 标准表达"]
    return [text]
```

- [ ] **Step 1.4: Keep existing strategy tests green**

Run:

```bash
pytest tests/services/rag/test_retrieval_plan.py tests/services/rag/test_supabase_strategy.py -q
```

Expected:

```text
all selected tests pass
```

## 7. Task 2: Compiled Truth Retrieval Source

**Purpose:** Turn Learning Brain projection into retrieval documents without creating another memory authority.

**Files:**

- Create: `deeptutor/services/rag/compiled_truth_source.py`
- Test: `tests/services/rag/test_compiled_truth_source.py`
- Read: `deeptutor/services/learner_state/learning_synthesis.py`

- [ ] **Step 2.1: Write tests for materialized compiled truth docs**

Create `tests/services/rag/test_compiled_truth_source.py`:

```python
from deeptutor.services.rag.compiled_truth_source import materialize_compiled_truth_sources
from deeptutor.services.rag.retrieval_plan import build_retrieval_plan


def _projection() -> dict:
    return {
        "subject": "construction_exam_learning_truth",
        "weak_points": [
            {
                "concept_id": "1A432000",
                "error_code": "E02",
                "evidence_level": "L1_repeated",
                "supporting_event_ids": ["evt1", "evt2"],
                "recommended_training": {"focus": "补全专家论证采分表达", "mode": "case_rewrite"},
                "timeline_refs": [{"event_id": "evt1"}, {"event_id": "evt2"}],
            }
        ],
        "compiled_objects": {
            "concept:1A432000": {
                "object_type": "concept",
                "object_id": "1A432000",
                "current_truth": "危大工程专项方案流程掌握不稳，专家论证程序反复漏写。",
                "evidence_level": "L1_repeated",
                "supporting_event_ids": ["evt1", "evt2"],
            },
            "rubric_item:case_001:r1": {
                "object_type": "rubric_item",
                "object_id": "r1",
                "current_truth": "应写明组织专家论证和施工单位技术负责人审批。",
                "evidence_level": "L1_repeated",
                "supporting_event_ids": ["evt1"],
            },
        },
    }


def test_materialize_compiled_truth_sources_for_weak_point_review() -> None:
    plan = build_retrieval_plan(
        "我老是案例题采分点漏写怎么办",
        include_questions_default=True,
        routing_metadata={"compiled_learning_truth_available": True},
    )

    docs = materialize_compiled_truth_sources(
        query="我老是案例题采分点漏写怎么办",
        projection=_projection(),
        retrieval_plan=plan,
    )

    assert [doc["_source_group"] for doc in docs] == ["learner_weak_point", "compiled_learning_truth", "compiled_learning_truth"]
    assert docs[0]["chunk_id"] == "compiled-truth:weak-point:1A432000:E02"
    assert "evt1" in docs[0]["rag_content"]
    assert docs[0]["metadata"]["provenance"]["evidence_level"] == "L1_repeated"
    assert docs[0]["metadata"]["provenance"]["source_authority"] == "compiled_learning_truth"


def test_materialize_compiled_truth_sources_returns_empty_without_projection() -> None:
    plan = build_retrieval_plan("屋面防水等级", include_questions_default=True)

    assert materialize_compiled_truth_sources(
        query="屋面防水等级",
        projection=None,
        retrieval_plan=plan,
    ) == []
```

- [ ] **Step 2.2: Run tests and verify they fail**

Run:

```bash
pytest tests/services/rag/test_compiled_truth_source.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.rag.compiled_truth_source'
```

- [ ] **Step 2.3: Implement materializer**

Create `deeptutor/services/rag/compiled_truth_source.py`:

```python
from __future__ import annotations

import re
from typing import Any

from deeptutor.services.rag.retrieval_plan import RetrievalPlan


def materialize_compiled_truth_sources(
    *,
    query: str,
    projection: dict[str, Any] | None,
    retrieval_plan: RetrievalPlan,
) -> list[dict[str, Any]]:
    if not isinstance(projection, dict):
        return []
    if not _group_enabled(retrieval_plan, "compiled_learning_truth"):
        return []

    docs: list[dict[str, Any]] = []
    if _group_enabled(retrieval_plan, "learner_weak_point"):
        for weak in list(projection.get("weak_points") or [])[:4]:
            if isinstance(weak, dict):
                docs.append(_weak_point_doc(weak))

    compiled = projection.get("compiled_objects") if isinstance(projection.get("compiled_objects"), dict) else {}
    for key, item in list(compiled.items())[:12]:
        if isinstance(item, dict) and _object_matches_plan(item, retrieval_plan=retrieval_plan, query=query):
            docs.append(_compiled_object_doc(str(key), item))

    return [doc for doc in docs if str(doc.get("rag_content") or "").strip()]


def _group_enabled(plan: RetrievalPlan, name: str) -> bool:
    group = plan.source_groups.get(name)
    return bool(group and group.enabled)


def _weak_point_doc(weak: dict[str, Any]) -> dict[str, Any]:
    concept = _clean(weak.get("concept_id"))
    error = _clean(weak.get("error_code"))
    training = weak.get("recommended_training") if isinstance(weak.get("recommended_training"), dict) else {}
    evidence_ids = [_clean(item) for item in list(weak.get("supporting_event_ids") or []) if _clean(item)]
    content = "\n".join([
        f"学习事实：学员在知识点 {concept} 上反复出现错因 {error}。",
        f"证据等级：{_clean(weak.get('evidence_level')) or 'L0_observed'}。",
        f"训练建议：{_clean(training.get('focus')) or '回到对应采分点做变式训练'}。",
        f"证据事件：{', '.join(evidence_ids)}。",
    ])
    return {
        "id": f"compiled-truth:weak-point:{concept}:{error}",
        "chunk_id": f"compiled-truth:weak-point:{concept}:{error}",
        "card_title": f"学员薄弱点 {concept} {error}",
        "rag_content": content,
        "source_type": "compiled_learning_truth",
        "_source_group": "learner_weak_point",
        "_source_table": "learner_summaries.summary_structured_json.learning_brain",
        "score": 1.0,
        "metadata": {
            "provenance": {
                "source_authority": "compiled_learning_truth",
                "evidence_level": _clean(weak.get("evidence_level")),
                "supporting_event_ids": evidence_ids,
                "manual_confirmed": _clean(weak.get("evidence_level")) in {"L2_confirmed", "L3_mastery_signal"},
                "stale": bool(weak.get("stale") or weak.get("superseded_by_event_ids")),
            },
            "compiled_truth_object": "weak_point",
            "concept_id": concept,
            "error_code": error,
        },
    }


def _compiled_object_doc(key: str, item: dict[str, Any]) -> dict[str, Any]:
    object_type = _clean(item.get("object_type")) or key.split(":", 1)[0]
    object_id = _clean(item.get("object_id")) or key
    evidence_ids = [_clean(event_id) for event_id in list(item.get("supporting_event_ids") or []) if _clean(event_id)]
    content = "\n".join([
        f"编译对象：{object_type} {object_id}。",
        f"当前可信判断：{_clean(item.get('current_truth'))}",
        f"证据等级：{_clean(item.get('evidence_level')) or 'L0_observed'}。",
        f"证据事件：{', '.join(evidence_ids)}。",
    ])
    return {
        "id": f"compiled-truth:{key}",
        "chunk_id": f"compiled-truth:{key}",
        "card_title": f"编译学习事实 {object_type} {object_id}",
        "rag_content": content,
        "source_type": "compiled_learning_truth",
        "_source_group": "compiled_learning_truth",
        "_source_table": "learner_summaries.summary_structured_json.learning_brain",
        "score": 0.88,
        "metadata": {
            "provenance": {
                "source_authority": "compiled_learning_truth",
                "evidence_level": _clean(item.get("evidence_level")),
                "supporting_event_ids": evidence_ids,
                "manual_confirmed": _clean(item.get("evidence_level")) in {"L2_confirmed", "L3_mastery_signal"},
                "stale": bool(item.get("stale") or item.get("superseded_by_event_ids")),
            },
            "compiled_truth_object": object_type,
            "compiled_truth_key": key,
        },
    }


def _object_matches_plan(item: dict[str, Any], *, retrieval_plan: RetrievalPlan, query: str) -> bool:
    object_type = _clean(item.get("object_type"))
    if retrieval_plan.intent == "rubric_lookup":
        return object_type == "rubric_item"
    if retrieval_plan.intent in {"weak_point_review", "next_training"}:
        return object_type in {"concept", "rubric_item", "error"}
    text = _clean(item.get("current_truth"))
    tokens = [token for token in re.findall(r"[A-Za-z0-9_-]+|[\u4e00-\u9fff]{2,8}", query) if token]
    return any(token in text for token in tokens[:6])


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())
```

- [ ] **Step 2.4: Run compiled truth source tests**

Run:

```bash
pytest tests/services/rag/test_compiled_truth_source.py -q
```

Expected:

```text
2 passed
```

## 8. Task 3: Provenance-Aware Ranking

**Purpose:** Make authority, evidence level, freshness, and manual confirmation part of ranking without violating exact answer authority.

**Files:**

- Create: `deeptutor/services/rag/provenance.py`
- Test: `tests/services/rag/test_provenance.py`

- [ ] **Step 3.1: Write tests for provenance features and authority order**

Create `tests/services/rag/test_provenance.py`:

```python
from deeptutor.services.rag.provenance import apply_provenance_boost, provenance_features


def test_provenance_features_for_standard_and_compiled_truth() -> None:
    standard = provenance_features({"_source_group": "standard_code_exact", "standard_code": "GB50345-2015"})
    compiled = provenance_features({
        "_source_group": "compiled_learning_truth",
        "metadata": {"provenance": {"evidence_level": "L2_confirmed", "manual_confirmed": True}},
    })

    assert standard["source_authority"] == "standard"
    assert standard["authority_rank"] < compiled["authority_rank"]
    assert compiled["manual_confirmed"] is True
    assert compiled["evidence_level"] == "L2_confirmed"


def test_apply_provenance_boost_never_puts_compiled_truth_above_exact_question() -> None:
    docs = [
        {"chunk_id": "compiled", "_source_group": "compiled_learning_truth", "weighted_rrf_score": 0.20, "metadata": {"provenance": {"evidence_level": "L2_confirmed"}}},
        {"chunk_id": "exact", "_source_group": "question_exact_text", "weighted_rrf_score": 0.10},
        {"chunk_id": "standard", "_source_group": "standard", "weighted_rrf_score": 0.15},
    ]

    ranked = apply_provenance_boost(docs)

    assert [doc["chunk_id"] for doc in ranked][:2] == ["exact", "standard"]
    assert ranked[2]["chunk_id"] == "compiled"
    assert ranked[2]["_provenance_features"]["evidence_level"] == "L2_confirmed"


def test_apply_provenance_boost_penalizes_stale_compiled_truth() -> None:
    docs = [
        {"chunk_id": "fresh", "_source_group": "compiled_learning_truth", "weighted_rrf_score": 0.2, "metadata": {"provenance": {"evidence_level": "L1_repeated"}}},
        {"chunk_id": "stale", "_source_group": "compiled_learning_truth", "weighted_rrf_score": 0.2, "metadata": {"provenance": {"evidence_level": "L2_confirmed", "stale": True}}},
    ]

    ranked = apply_provenance_boost(docs)

    assert [doc["chunk_id"] for doc in ranked] == ["fresh", "stale"]
```

- [ ] **Step 3.2: Implement provenance helper**

Create `deeptutor/services/rag/provenance.py`:

```python
from __future__ import annotations

from typing import Any


_GROUP_AUTHORITY_RANK = {
    "question_exact_text": 0,
    "question_exact_vector": 1,
    "standard_code_exact": 2,
    "standard_precision": 3,
    "standard": 4,
    "questions_bank": 5,
    "learner_weak_point": 6,
    "compiled_learning_truth": 7,
    "textbook": 8,
    "exam": 9,
}

_GROUP_AUTHORITY_NAME = {
    "question_exact_text": "exact_question",
    "question_exact_vector": "exact_question",
    "standard_code_exact": "standard",
    "standard_precision": "standard",
    "standard": "standard",
    "questions_bank": "questions_bank",
    "learner_weak_point": "compiled_learning_truth",
    "compiled_learning_truth": "compiled_learning_truth",
    "textbook": "textbook",
    "exam": "exam",
}

_EVIDENCE_BONUS = {
    "L0_observed": 0.0,
    "L1_repeated": 0.015,
    "L2_confirmed": 0.025,
    "L3_mastery_signal": 0.02,
}


def provenance_features(doc: dict[str, Any]) -> dict[str, Any]:
    group = str(doc.get("_source_group") or "").strip()
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    provenance = metadata.get("provenance") if isinstance(metadata.get("provenance"), dict) else {}
    evidence_level = str(provenance.get("evidence_level") or "").strip()
    return {
        "source_group": group,
        "source_authority": _GROUP_AUTHORITY_NAME.get(group, group or "unknown"),
        "authority_rank": _GROUP_AUTHORITY_RANK.get(group, 50),
        "evidence_level": evidence_level,
        "manual_confirmed": bool(provenance.get("manual_confirmed")),
        "stale": bool(provenance.get("stale")),
        "supporting_event_ids": list(provenance.get("supporting_event_ids") or []),
    }


def apply_provenance_boost(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boosted: list[dict[str, Any]] = []
    for item in results:
        doc = dict(item)
        features = provenance_features(doc)
        score = float(doc.get("weighted_rrf_score") or doc.get("score") or 0.0)
        score += _authority_bonus(features["authority_rank"])
        score += _EVIDENCE_BONUS.get(str(features["evidence_level"]), 0.0)
        if features["manual_confirmed"]:
            score += 0.01
        if features["stale"]:
            score -= 0.05
        doc["_provenance_features"] = features
        doc["_provenance_score"] = score
        boosted.append(doc)
    return sorted(
        boosted,
        key=lambda doc: (
            int(doc.get("_provenance_features", {}).get("authority_rank", 50)),
            -float(doc.get("_provenance_score") or 0.0),
        ),
    )


def ranking_trace(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "fusion": "weighted_rrf_with_provenance",
        "authority_order": [
            "exact_question",
            "standard",
            "questions_bank",
            "compiled_learning_truth",
            "textbook",
            "exam",
        ],
        "provenance_features": [
            {
                "chunk_id": str(item.get("chunk_id") or item.get("id") or ""),
                **dict(item.get("_provenance_features") or provenance_features(item)),
            }
            for item in results
        ],
    }


def _authority_bonus(authority_rank: int) -> float:
    if authority_rank <= 1:
        return 0.10
    if authority_rank <= 4:
        return 0.05
    if authority_rank <= 5:
        return 0.025
    if authority_rank <= 7:
        return 0.01
    return 0.0
```

- [ ] **Step 3.3: Run provenance tests**

Run:

```bash
pytest tests/services/rag/test_provenance.py -q
```

Expected:

```text
3 passed
```

## 9. Task 4: Wire Query Plan, Compiled Sources, and Provenance into SupabasePipeline

**Purpose:** Make the new retrieval behavior available through the existing `RAGService` path.

**Files:**

- Modify: `deeptutor/services/rag/pipelines/supabase.py`
- Modify: `deeptutor/services/rag/service.py`
- Test: `tests/services/rag/test_learning_fact_retrieval_pipeline.py`
- Test: `tests/services/rag/test_rag_pipelines.py`

- [ ] **Step 4.1: Write pipeline test for compiled truth source group**

Create `tests/services/rag/test_learning_fact_retrieval_pipeline.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_supabase_search_adds_compiled_truth_source_group(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")
    monkeypatch.setenv("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", "true")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())
    pipeline = supabase_module.SupabasePipeline()

    async def _skip_availability_gate(**kwargs):
        return None

    monkeypatch.setattr(pipeline, "_assert_data_api_available", _skip_availability_gate)

    async def _fake_client(timeout_s: float):
        return object()

    async def _fake_embed(query: str):
        return [0.1, 0.2, 0.3]

    async def _fake_run_query_plan(**kwargs):
        return [{
            "phase": "primary",
            "group_name": "standard",
            "query": kwargs["queries"][0],
            "query_index": 0,
            "query_weight": 1.0,
            "results": [{
                "chunk_id": "std-1",
                "card_title": "标准条文",
                "rag_content": "专家论证应按危大工程程序组织。",
                "_source_group": "standard",
                "_source_table": "kb_chunks",
                "score": 0.82,
            }],
        }]

    async def _identity(results, **kwargs):
        return results

    monkeypatch.setattr(pipeline, "_get_client", _fake_client)
    monkeypatch.setattr(pipeline, "_embed_query", _fake_embed)
    monkeypatch.setattr(pipeline, "_run_query_plan", _fake_run_query_plan)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    projection = {
        "subject": "construction_exam_learning_truth",
        "weak_points": [{
            "concept_id": "1A432000",
            "error_code": "E02",
            "evidence_level": "L1_repeated",
            "supporting_event_ids": ["evt1", "evt2"],
            "recommended_training": {"focus": "补全专家论证采分表达"},
        }],
        "compiled_objects": {},
    }

    result = await pipeline.search(
        query="我老是案例题采分点漏写怎么办",
        kb_name="construction-exam",
        compiled_learning_truth=projection,
        routing_metadata={"compiled_learning_truth_available": True},
    )

    source_groups = [source["source_type"] for source in result["sources"]]
    assert "compiled_learning_truth" in source_groups
    assert result["evidence_bundle"]["retrieval_plan"]["intent"] == "weak_point_review"
    assert result["evidence_bundle"]["ranking_trace"]["fusion"] == "weighted_rrf_with_provenance"


@pytest.mark.asyncio
async def test_compiled_truth_does_not_override_exact_question(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.rag.pipelines import supabase as supabase_module

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_RAG_ENABLE_RERANK", "false")
    monkeypatch.setenv("SUPABASE_RAG_SECOND_PASS", "false")
    monkeypatch.setenv("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", "true")

    class _FakeKbConfigService:
        def get_kb_config(self, kb_name: str) -> dict[str, object]:
            return {}

    monkeypatch.setattr(supabase_module, "get_kb_config_service", lambda: _FakeKbConfigService())
    pipeline = supabase_module.SupabasePipeline()

    async def _skip_availability_gate(**kwargs):
        return None

    monkeypatch.setattr(pipeline, "_assert_data_api_available", _skip_availability_gate)

    async def _fake_client(timeout_s: float):
        return object()

    async def _empty_plan(**kwargs):
        return []

    async def _exact_text_batch(**kwargs):
        return [{
            "query": kwargs["probe_queries"][0],
            "results": [{
                "id": "q1",
                "chunk_id": "question-q1",
                "card_title": "题目",
                "rag_content": "【答案】ABE",
                "stem": "确定屋面防水等级应根据什么",
                "correct_answer": "ABE",
                "question_type": "multi_choice",
                "_source_group": "question_exact_text",
                "_source_table": "questions_bank",
                "score": 1.0,
            }],
        }]

    async def _identity(results, **kwargs):
        return results

    monkeypatch.setattr(pipeline, "_get_client", _fake_client)
    monkeypatch.setattr(pipeline, "_run_query_plan", _empty_plan)
    monkeypatch.setattr(pipeline, "_search_exact_question_text_batch", _exact_text_batch)
    monkeypatch.setattr(pipeline, "_hydrate_sources", _identity)
    monkeypatch.setattr(pipeline, "_rerank_results", _identity)

    result = await pipeline.search(
        query="单选题：确定屋面防水工程的防水等级应根据什么 A 建筑物类别 B 建筑物用途",
        kb_name="construction-exam",
        compiled_learning_truth={"weak_points": [{"concept_id": "1A432000", "error_code": "E02", "evidence_level": "L2_confirmed"}]},
        routing_metadata={"compiled_learning_truth_available": True},
    )

    assert result["exact_question"]["chunk_id"] == "question-q1"
    assert result["evidence_bundle"]["exact_question"]["chunk_id"] == "question-q1"
    assert result["evidence_bundle"]["retrieval_plan"]["authority_order"][0] == "exact_question"
```

- [ ] **Step 4.2: Modify `SupabasePipeline.search` imports**

In `deeptutor/services/rag/pipelines/supabase.py`, add imports:

```python
from deeptutor.services.rag.compiled_truth_source import materialize_compiled_truth_sources
from deeptutor.services.rag.provenance import apply_provenance_boost, ranking_trace
from deeptutor.services.rag.retrieval_plan import build_retrieval_plan
```

- [ ] **Step 4.3: Build retrieval plan near existing source plan**

In `SupabasePipeline.search`, after `source_plan = select_sources(...)`, add:

```python
            compiled_learning_truth = (
                kwargs.get("compiled_learning_truth")
                if isinstance(kwargs.get("compiled_learning_truth"), dict)
                else None
            )
            retrieval_plan = build_retrieval_plan(
                query,
                include_questions_default=config.include_questions,
                intent=intent,
                question_type=question_type,
                routing_metadata={
                    **(routing_metadata if isinstance(routing_metadata, dict) else {}),
                    "compiled_learning_truth_available": bool(compiled_learning_truth),
                },
            )
```

- [ ] **Step 4.4: Add compiled truth source weights**

In `_load_search_config(...)`, extend `source_weights`:

```python
            "compiled_learning_truth": float(os.getenv("SUPABASE_RAG_WEIGHT_COMPILED_TRUTH", "1.15")),
            "learner_weak_point": float(os.getenv("SUPABASE_RAG_WEIGHT_LEARNER_WEAK_POINT", "1.25")),
```

Extend `question_weights` with the same keys:

```python
            "compiled_learning_truth": float(os.getenv("SUPABASE_RAG_QUESTION_WEIGHT_COMPILED_TRUTH", "1.05")),
            "learner_weak_point": float(os.getenv("SUPABASE_RAG_QUESTION_WEIGHT_LEARNER_WEAK_POINT", "1.10")),
```

- [ ] **Step 4.5: Add compiled truth as a source group before fusion**

Before the retrieval `try:` block, initialize:

```python
            compiled_truth_plan: list[dict[str, Any]] = []
```

After `primary_plan` / `exact_text_plans` are built and before first `_fuse_plan_results(...)`, add:

```python
                compiled_truth_docs = materialize_compiled_truth_sources(
                    query=query,
                    projection=compiled_learning_truth if _env_flag("SUPABASE_RAG_COMPILED_TRUTH_ENABLED", False) else None,
                    retrieval_plan=retrieval_plan,
                )
                compiled_truth_plan = []
                if compiled_truth_docs:
                    compiled_truth_plan.append({
                        "phase": "primary",
                        "group_name": "compiled_learning_truth",
                        "query": query,
                        "query_index": 0,
                        "query_weight": 0.92,
                        "results": compiled_truth_docs,
                    })
```

Then include `compiled_truth_plan` in every plan list:

```python
        fused = self._fuse_plan_results(
            [*exact_text_plans, *primary_plan, *compiled_truth_plan],
            query=query,
            question_like=question_like,
            config=config,
        )
```

And after second pass:

```python
        all_plans = [*exact_text_plans, *primary_plan, *second_pass_plan, *compiled_truth_plan]
```

- [ ] **Step 4.6: Apply provenance before final dedupe**

After rerank and partial-case filtering:

```python
        reranked = self._filter_partial_case_results(reranked, exact_question=exact_question)
        reranked = apply_provenance_boost(reranked)
        final_results = dedupe_ranked_results(reranked, max_items=config.top_k)
```

- [ ] **Step 4.7: Add plan and ranking trace to `evidence_bundle`**

After `_build_evidence_bundle(...)`, add:

```python
        evidence_bundle["retrieval_plan"] = retrieval_plan.to_trace_dict()
        evidence_bundle["ranking_trace"] = ranking_trace(final_results)
```

Also extend Langfuse metadata:

```python
                "retrieval_plan": retrieval_plan.to_trace_dict(),
                "ranking_trace": ranking_trace(final_results),
```

- [ ] **Step 4.8: Preserve richer evidence bundle in `RAGService` fallback**

In `deeptutor/services/rag/service.py`, when constructing fallback `evidence_bundle`, include empty stable keys:

```python
                    "retrieval_plan": {},
                    "ranking_trace": {},
```

- [ ] **Step 4.9: Run pipeline tests**

Run:

```bash
pytest \
  tests/services/rag/test_learning_fact_retrieval_pipeline.py \
  tests/services/rag/test_rag_pipelines.py \
  tests/services/rag/test_supabase_strategy.py \
  -q
```

Expected:

```text
all selected tests pass
```

## 10. Task 5: Pass Compiled Truth Context from TutorBot Runtime to RAG

**Purpose:** Make compiled truth available to retrieval without making RAG read learner state directly.

**Files:**

- Modify: `deeptutor/tutorbot/agent/loop.py`
- Test: `tests/tutorbot/test_tutorbot_rag_compiled_truth_context.py`
- Read: `deeptutor/capabilities/deep_question.py`

- [ ] **Step 5.1: Write test for context propagation**

Create `tests/tutorbot/test_tutorbot_rag_compiled_truth_context.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_rag_tool_receives_compiled_learning_truth_from_runtime_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.tutorbot.agent import loop as loop_module

    captured_kwargs = {}

    class _FakeRAGService:
        async def search(self, query, kb_name, event_sink=None, **kwargs):
            captured_kwargs.update(kwargs)
            return {
                "query": query,
                "answer": "grounded answer",
                "content": "grounded answer",
                "sources": [],
                "provider": "supabase",
                "evidence_bundle": {"retrieval_empty": True},
            }

    monkeypatch.setattr(loop_module, "RAGService", lambda *args, **kwargs: _FakeRAGService())

    runtime_context = {
        "compiled_learning_truth": {
            "subject": "construction_exam_learning_truth",
            "weak_points": [{"concept_id": "1A432000", "error_code": "E02"}],
        }
    }

    tool = loop_module._build_rag_tool(runtime_context=runtime_context)
    await tool.invoke({"query": "我老是案例题丢分怎么办", "kb_name": "construction-exam"})

    assert captured_kwargs["compiled_learning_truth"]["subject"] == "construction_exam_learning_truth"
    assert captured_kwargs["routing_metadata"]["compiled_learning_truth_available"] is True
```

If `_build_rag_tool` does not exist, create the smallest extraction around current RAG tool construction so this behavior is testable. The extraction must not change tool semantics.

- [ ] **Step 5.2: Implement context propagation**

In `deeptutor/tutorbot/agent/loop.py`, pass existing runtime compiled truth into RAG tool kwargs:

```python
compiled_learning_truth = (
    runtime_context.get("compiled_learning_truth")
    if isinstance(runtime_context, dict) and isinstance(runtime_context.get("compiled_learning_truth"), dict)
    else None
)
routing_metadata = dict(args.get("routing_metadata") or {})
if compiled_learning_truth:
    routing_metadata["compiled_learning_truth_available"] = True
result = await RAGService().search(
    query=query,
    kb_name=kb_name,
    event_sink=event_sink,
    compiled_learning_truth=compiled_learning_truth,
    routing_metadata=routing_metadata,
)
```

- [ ] **Step 5.3: Run TutorBot context test**

Run:

```bash
pytest tests/tutorbot/test_tutorbot_rag_compiled_truth_context.py -q
```

Expected:

```text
1 passed
```

## 11. Task 6: Graph-Aware Retrieval Expansion

**Purpose:** Use existing typed graph projection to expand weak-point and training queries along teaching relationships.

**Files:**

- Modify: `deeptutor/services/rag/compiled_truth_source.py`
- Test: `tests/services/rag/test_compiled_truth_source.py`
- Read: `deeptutor/services/learner_state/learning_synthesis.py`

- [ ] **Step 6.1: Add graph expansion test**

Append to `tests/services/rag/test_compiled_truth_source.py`:

```python
def test_materialize_compiled_truth_sources_uses_graph_training_trace() -> None:
    plan = build_retrieval_plan(
        "下一题给我练专家论证",
        include_questions_default=True,
        routing_metadata={"compiled_learning_truth_available": True},
    )
    projection = {
        "weak_points": [{
            "concept_id": "1A432000",
            "error_code": "E02",
            "evidence_level": "L1_repeated",
            "supporting_event_ids": ["evt1"],
            "recommended_training": {"focus": "专家论证程序", "mode": "case_rewrite"},
        }],
        "compiled_objects": {},
        "typed_graph": {
            "edges": [{
                "edge_type": "error_points_to_training",
                "from": {"type": "error", "id": "E02"},
                "to": {"type": "training", "id": "case_rewrite:expert_review"},
                "evidence_event_id": "evt1",
            }]
        },
    }

    docs = materialize_compiled_truth_sources(
        query="下一题给我练专家论证",
        projection=projection,
        retrieval_plan=plan,
    )

    assert any("case_rewrite:expert_review" in doc["rag_content"] for doc in docs)
```

- [ ] **Step 6.2: Append graph trace to weak-point docs**

In `_weak_point_doc(...)`, accept optional `training_trace` and include:

```python
        f"图谱训练链路：{', '.join(training_trace)}。" if training_trace else "",
```

Change `materialize_compiled_truth_sources(...)` to compute training ids from `projection["typed_graph"]["edges"]` where `edge_type == "error_points_to_training"` and the weak point's `error_code` matches the edge `from.id`.

- [ ] **Step 6.3: Run graph source test**

Run:

```bash
pytest tests/services/rag/test_compiled_truth_source.py -q
```

Expected:

```text
all selected tests pass
```

## 12. Task 7: Evidence Bundle and Trace Regression Matrix

**Purpose:** Lock the contract so future changes do not silently remove provenance or plan trace.

**Files:**

- Modify: `tests/fixtures/learning_fact_retrieval_cases.json`
- Create: `tests/services/rag/test_learning_fact_retrieval_contract.py`

- [ ] **Step 7.1: Add contract fixture**

Create `tests/fixtures/learning_fact_retrieval_cases.json`:

```json
[
  {
    "case_id": "standard_clause",
    "query": "GB 50345-2015 第3.0.1条对屋面防水等级怎么规定",
    "expected_intent": "standard_clause",
    "required_source_groups": ["standard", "standard_code_exact"],
    "forbidden_source_groups": ["learner_weak_point"]
  },
  {
    "case_id": "weak_point_review",
    "query": "我老是案例题采分点漏写怎么办",
    "expected_intent": "weak_point_review",
    "required_source_groups": ["compiled_learning_truth", "learner_weak_point", "standard"],
    "forbidden_source_groups": []
  },
  {
    "case_id": "next_training",
    "query": "下一题给我练专家论证",
    "expected_intent": "next_training",
    "required_source_groups": ["compiled_learning_truth", "questions_bank"],
    "forbidden_source_groups": []
  }
]
```

- [ ] **Step 7.2: Add fixture-driven contract test**

Create `tests/services/rag/test_learning_fact_retrieval_contract.py`:

```python
import json
from pathlib import Path

from deeptutor.services.rag.retrieval_plan import build_retrieval_plan


def test_learning_fact_retrieval_plan_contract_cases() -> None:
    cases = json.loads(Path("tests/fixtures/learning_fact_retrieval_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        plan = build_retrieval_plan(
            case["query"],
            include_questions_default=True,
            routing_metadata={"compiled_learning_truth_available": True},
        )
        enabled = {name for name, group in plan.source_groups.items() if group.enabled}
        assert plan.intent == case["expected_intent"], case["case_id"]
        for source_group in case["required_source_groups"]:
            assert source_group in enabled, case["case_id"]
        for source_group in case["forbidden_source_groups"]:
            assert source_group not in enabled, case["case_id"]
```

- [ ] **Step 7.3: Run contract tests**

Run:

```bash
pytest tests/services/rag/test_learning_fact_retrieval_contract.py -q
```

Expected:

```text
1 passed
```

## 13. Task 8: Offline Dream Cycle Maintenance Workflows

**Purpose:** Make knowledge maintenance executable instead of relying on model improvisation.

**Files:**

- Create: `deeptutor/services/rag/maintenance.py`
- Create: `scripts/run_learning_retrieval_maintenance.py`
- Create: `tests/scripts/test_run_learning_retrieval_maintenance.py`
- Create: `deeptutor/tutorbot/skills/retrieval-maintenance/SKILL.md`

- [ ] **Step 8.1: Write maintenance dry-run tests**

Create `tests/scripts/test_run_learning_retrieval_maintenance.py`:

```python
import json
import subprocess
import sys


def test_learning_retrieval_maintenance_dry_run_outputs_audit_sections() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_learning_retrieval_maintenance.py",
            "--dry-run",
            "--user-id",
            "student-1",
            "--projection-json",
            json.dumps({
                "weak_points": [{"concept_id": "1A432000", "error_code": "E02", "supporting_event_ids": ["evt1"]}],
                "typed_graph": {"readiness_gaps": [{"code": "missing_training_edge"}]},
            }, ensure_ascii=False),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["audits"]["retrieval_miss_audit"]["status"] in {"ok", "warn"}
    assert payload["audits"]["citation_audit"]["status"] in {"ok", "warn"}
    assert payload["audits"]["stale_weak_point_cleanup"]["status"] in {"ok", "warn"}
    assert payload["audits"]["rubric_coverage_audit"]["status"] in {"ok", "warn"}
    assert payload["audits"]["rag_eval_case_generation"]["status"] in {"ok", "warn"}
```

- [ ] **Step 8.2: Implement maintenance helpers**

Create `deeptutor/services/rag/maintenance.py`:

```python
from __future__ import annotations

from typing import Any


def build_learning_retrieval_maintenance_report(
    *,
    user_id: str,
    projection: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    weak_points = [item for item in list(projection.get("weak_points") or []) if isinstance(item, dict)]
    graph = projection.get("typed_graph") if isinstance(projection.get("typed_graph"), dict) else {}
    readiness_gaps = [item for item in list(graph.get("readiness_gaps") or []) if isinstance(item, dict)]
    return {
        "user_id": user_id,
        "dry_run": dry_run,
        "audits": {
            "retrieval_miss_audit": _audit_retrieval_miss(readiness_gaps),
            "citation_audit": _audit_citations(weak_points),
            "stale_weak_point_cleanup": _audit_stale_weak_points(weak_points),
            "rubric_coverage_audit": _audit_rubric_coverage(readiness_gaps),
            "rag_eval_case_generation": _audit_eval_case_generation(weak_points),
        },
    }


def _audit_retrieval_miss(readiness_gaps: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [gap for gap in readiness_gaps if str(gap.get("code") or "").startswith("missing_")]
    return {"status": "warn" if missing else "ok", "missing_count": len(missing)}


def _audit_citations(weak_points: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [item for item in weak_points if not list(item.get("supporting_event_ids") or [])]
    return {"status": "warn" if missing else "ok", "missing_support_count": len(missing)}


def _audit_stale_weak_points(weak_points: list[dict[str, Any]]) -> dict[str, Any]:
    stale = [item for item in weak_points if item.get("stale") or item.get("superseded_by_event_ids")]
    return {"status": "warn" if stale else "ok", "stale_count": len(stale)}


def _audit_rubric_coverage(readiness_gaps: list[dict[str, Any]]) -> dict[str, Any]:
    rubric_gaps = [gap for gap in readiness_gaps if "rubric" in str(gap.get("code") or "")]
    return {"status": "warn" if rubric_gaps else "ok", "gap_count": len(rubric_gaps)}


def _audit_eval_case_generation(weak_points: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        {
            "concept_id": str(item.get("concept_id") or ""),
            "error_code": str(item.get("error_code") or ""),
        }
        for item in weak_points[:10]
    ]
    return {"status": "ok" if candidates else "warn", "candidate_count": len(candidates), "candidates": candidates}
```

- [ ] **Step 8.3: Implement dry-run script**

Create `scripts/run_learning_retrieval_maintenance.py`:

```python
#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys

from deeptutor.services.rag.maintenance import build_learning_retrieval_maintenance_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Learning Fact Retrieval maintenance audits.")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--projection-json", default="{}")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        projection = json.loads(args.projection_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid --projection-json: {exc}") from exc
    if not isinstance(projection, dict):
        raise SystemExit("--projection-json must decode to an object")

    report = build_learning_retrieval_maintenance_report(
        user_id=args.user_id,
        projection=projection,
        dry_run=bool(args.dry_run),
    )
    sys.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8.4: Add maintenance skill**

Create `deeptutor/tutorbot/skills/retrieval-maintenance/SKILL.md`:

```markdown
# Retrieval Maintenance

Use this skill when auditing Learning Fact Retrieval quality, including retrieval misses, missing citations, stale weak points, rubric coverage gaps, or RAG eval case generation.

## Workflow

1. Read `contracts/rag.md` and confirm `RAGService` remains the only online retrieval entry.
2. Produce or fetch the learner compiled truth projection from `LearnerStateService`.
3. Run:

   ```bash
   python scripts/run_learning_retrieval_maintenance.py --dry-run --user-id <user_id> --projection-json '<projection-json>'
   ```

4. Treat `warn` sections as action items:
   - `retrieval_miss_audit`: add eval case or inspect source plan.
   - `citation_audit`: do not promote the claim above `L0_observed`.
   - `stale_weak_point_cleanup`: verify improvement or manual correction.
   - `rubric_coverage_audit`: inspect `questions_bank` / projected rubric coverage.
   - `rag_eval_case_generation`: add fixture cases before changing ranking.

## Boundaries

- Do not write learner memory from this skill.
- Do not call RAG outside `RAGService`.
- Do not create a new chat route or mode.
```

- [ ] **Step 8.5: Run maintenance tests**

Run:

```bash
pytest tests/scripts/test_run_learning_retrieval_maintenance.py -q
```

Expected:

```text
1 passed
```

## 14. Task 9: Evaluation and Release Gate

**Purpose:** Verify retrieval quality with both deterministic tests and live product behavior.

**Files:**

- Modify: `tests/fixtures/learning_fact_retrieval_cases.json`
- Create: `scripts/eval_learning_fact_retrieval.py`
- Test: `tests/scripts/test_eval_learning_fact_retrieval.py`

- [ ] **Step 9.1: Add eval CLI test**

Create `tests/scripts/test_eval_learning_fact_retrieval.py`:

```python
import json
import subprocess
import sys
from pathlib import Path


def test_eval_learning_fact_retrieval_reads_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "cases.json"
    fixture.write_text(json.dumps([{
        "case_id": "weak_point_review",
        "query": "我老是案例题采分点漏写怎么办",
        "expected_intent": "weak_point_review",
        "required_source_groups": ["compiled_learning_truth"]
    }], ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/eval_learning_fact_retrieval.py", "--fixture", str(fixture)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["total"] == 1
    assert payload["passed"] == 1
    assert payload["failed"] == 0
```

- [ ] **Step 9.2: Implement eval CLI**

Create `scripts/eval_learning_fact_retrieval.py`:

```python
#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from deeptutor.services.rag.retrieval_plan import build_retrieval_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Learning Fact Retrieval query plans.")
    parser.add_argument("--fixture", default="tests/fixtures/learning_fact_retrieval_cases.json")
    args = parser.parse_args()
    cases = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    passed = 0
    failures = []
    for case in cases:
        plan = build_retrieval_plan(
            case["query"],
            include_questions_default=True,
            routing_metadata={"compiled_learning_truth_available": True},
        )
        enabled = {name for name, group in plan.source_groups.items() if group.enabled}
        required = set(case.get("required_source_groups") or [])
        ok = plan.intent == case.get("expected_intent") and required.issubset(enabled)
        if ok:
            passed += 1
        else:
            failures.append({
                "case_id": case.get("case_id"),
                "expected_intent": case.get("expected_intent"),
                "actual_intent": plan.intent,
                "missing_source_groups": sorted(required - enabled),
            })
    result = {"total": len(cases), "passed": passed, "failed": len(failures), "failures": failures}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9.3: Run full focused gate**

Run:

```bash
pytest \
  tests/services/rag/test_retrieval_plan.py \
  tests/services/rag/test_compiled_truth_source.py \
  tests/services/rag/test_provenance.py \
  tests/services/rag/test_learning_fact_retrieval_pipeline.py \
  tests/services/rag/test_learning_fact_retrieval_contract.py \
  tests/services/rag/test_rag_pipelines.py \
  tests/services/rag/test_supabase_strategy.py \
  tests/services/learner_state/test_learning_synthesis.py \
  tests/scripts/test_run_learning_retrieval_maintenance.py \
  tests/scripts/test_eval_learning_fact_retrieval.py \
  -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 9.4: Run contract guard**

Run:

```bash
python scripts/check_contract_guard.py
```

Expected:

```text
contract-guard: passed
```

## 15. Task 10: Live Verification

**Purpose:** Prove the feature works in real product chains, not only unit tests.

- [ ] **Step 10.1: Local direct RAG smoke**

Run a local Python smoke that calls `RAGService.search(...)` with `compiled_learning_truth`:

```bash
python - <<'PY'
import asyncio
from deeptutor.services.rag.service import RAGService

projection = {
    "subject": "construction_exam_learning_truth",
    "weak_points": [{
        "concept_id": "1A432000",
        "error_code": "E02",
        "evidence_level": "L1_repeated",
        "supporting_event_ids": ["evt1", "evt2"],
        "recommended_training": {"focus": "补全专家论证采分表达"},
    }],
    "compiled_objects": {},
}

async def main():
    result = await RAGService(provider="supabase").search(
        query="我老是案例题采分点漏写怎么办",
        kb_name="construction-exam",
        compiled_learning_truth=projection,
        routing_metadata={"compiled_learning_truth_available": True},
    )
    bundle = result["evidence_bundle"]
    print(bundle.get("retrieval_plan", {}).get("intent"))
    print(bundle.get("ranking_trace", {}).get("fusion"))
    print([source.get("source_type") for source in result.get("sources", [])])

asyncio.run(main())
PY
```

Expected:

```text
weak_point_review
weighted_rrf_with_provenance
```

The source list should include `compiled_learning_truth` when Supabase is available.

- [ ] **Step 10.2: Local `/api/v1/ws` smoke**

Run one `fast` and one `deep` turn against local `/api/v1/ws` with a learner that has compiled truth. Confirm:

1. Trace contains `rag.supabase.search`.
2. `evidence_bundle.retrieval_plan.intent == "weak_point_review"` for weak-point query.
3. `ranking_trace.provenance_features` includes compiled truth docs.
4. Final answer explains weak point using evidence language, not a generic study suggestion.

- [ ] **Step 10.3: Langfuse / ClickHouse verification after deploy**

After deployment, query one real trace and confirm:

1. `rag.supabase.search` metadata includes `retrieval_plan`.
2. `ranking_trace.fusion == "weighted_rrf_with_provenance"`.
3. `exact_question` hit still appears above compiled truth for exact exam query.
4. For weak-point query, compiled truth appears as source but does not replace standard or question authority.

- [ ] **Step 10.4: Mini-program verification rule**

If no mini-program files changed, Web `/wechat-harness` visible smoke is enough for this plan. If any `wx_miniprogram` or `yousenwebview/packageDeeptutor` files change, run WeChat DevTools smoke before release.

## 16. Commit Strategy

Use narrow commits. Suggested order:

1. `feat(rag): add explicit learning fact retrieval plan`
2. `feat(rag): materialize compiled truth retrieval sources`
3. `feat(rag): add provenance-aware source ranking`
4. `feat(rag): wire learning fact sources into supabase pipeline`
5. `feat(tutorbot): pass compiled truth into rag context`
6. `feat(rag): add retrieval maintenance workflow`
7. `test(rag): add learning fact retrieval eval gate`
8. `docs(plan): register learning fact retrieval plan`

Only stage files changed by each commit. Do not stage existing unrelated dirty files in this workspace.

## 17. Rollout and Guardrails

Recommended rollout flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `SUPABASE_RAG_QUERY_PLAN_TRACE_ENABLED` | `true` | Emits retrieval plan in trace without changing ranking. |
| `SUPABASE_RAG_COMPILED_TRUTH_SHADOW_ENABLED` | `true` for first deploy | Materializes compiled truth docs into trace only, not final sources. |
| `SUPABASE_RAG_COMPILED_TRUTH_ENABLED` | `false` for first deploy | Enables compiled truth source group in final retrieval results. |
| `SUPABASE_RAG_PROVENANCE_BOOST_ENABLED` | `false` for first deploy | Enables provenance sort after RRF/rerank. Keep false until exact/standard regression and live trace checks pass. |
| `SUPABASE_RAG_COMPILED_TRUTH_MAX_DOCS` | `6` | Caps compiled truth docs per retrieval. |
| `SUPABASE_RAG_MAINTENANCE_WRITE_ENABLED` | `false` | Keeps maintenance audit dry-run by default. |

Fail-closed behavior:

1. Missing compiled truth projection: run ordinary RAG.
2. Malformed projection: skip compiled source group and add warning to `evidence_bundle`.
3. Supabase 402 / quota: existing `RAGSearchError(provider="supabase")` remains authoritative.
4. Rerank unavailable: provenance boost still works on fused results.
5. Exact full coverage hit: compiled truth source group may appear in trace but cannot override exact authority.

## 18. Acceptance Criteria

This plan is complete when:

1. `RAGService.search` still remains the only online retrieval entry.
2. `evidence_bundle.retrieval_plan` exists for Supabase results.
3. Query examples map correctly:
   - exact exam question -> `exact_question`
   - case question -> `case_grading_context`
   - standard clause -> `standard_clause`
   - weak point review -> `weak_point_review`
   - next training -> `next_training`
4. Compiled truth is included as source group only when caller passes compiled truth context.
5. `ranking_trace` exposes source group, authority rank, evidence level, manual confirmation, stale flag, and supporting event ids.
6. Full exact question answer still outranks compiled truth.
7. Weak-point queries can retrieve learner weak point docs and supporting event ids.
8. Maintenance dry-run produces retrieval miss, citation, stale weak point, rubric coverage, and eval case sections.
9. Focused pytest gate and contract guard pass.
10. One live `/api/v1/ws` trace proves the retrieval plan and provenance trace are visible.

## 19. Self-Review Checklist

Before execution:

1. Confirm no task adds a new chat route, provider, vector DB, graph DB, or RAG entry.
2. Confirm `compiled_learning_truth` is passed as context and not read/written by `SupabasePipeline`.
3. Confirm exact-question ranking tests fail before implementation and pass after.
4. Confirm no plan step relies on vague implementation wording; every new behavior has a test.
5. Confirm `docs/plan/INDEX.md` points to this file under the existing Learning Brain主线.

## 20. Expert Review Addendum: Strengthened Delivery Plan

This section supersedes any conflicting execution order above. The original plan has the right direction, but its first implementation slice is still too broad for a production learning product. The safest current path is **selective scope reduction for first release, with full traceability preserved for the larger vision**.

### 20.1 Product Thesis

The product outcome is not "more retrieval features." The outcome is:

> When a construction-exam learner asks a question, DeepTutor can retrieve the right authoritative fact, explain why that fact is relevant to this learner, and prove the answer's evidence chain in trace.

Therefore the deliverable must optimize for three measurable user outcomes:

1. **Correct authority:** exact exam answers and standard clauses remain correct.
2. **Personalized relevance:** weak-point / next-training questions use the learner's compiled truth when it is safe.
3. **Auditability:** every retrieval decision can be replayed from `evidence_bundle.retrieval_plan`, `ranking_trace`, source ids, and Langfuse trace.

### 20.2 Use-Case Matrix

These are the scenarios the implementation must handle before production enablement.

| Scenario | Example query | Expected intent | Required sources | Authority behavior | Verification |
| --- | --- | --- | --- | --- | --- |
| Exact MCQ lookup | "确定屋面防水等级应根据什么 A...B..." | `exact_question` | `question_exact_text`, `questions_bank` | Full exact answer pins above everything. | Unit + live `/api/v1/ws`; check `exact_question.chunk_id`. |
| Exact case full coverage | Full case background + all subquestions | `case_grading_context` | `question_exact_text`, `questions_bank`, standards | Full case exact may lead, but final answer still assembled by responding layer. | Existing case coverage tests + Langfuse. |
| Exact case partial coverage | Case contains 3 subquestions, only 1 exact hit | `case_grading_context` | exact + standards/textbook supplement | Mark `coverage_state=partial`; do not suppress supplement retrieval. | Unit test for missing subquestions. |
| Standard clause | "GB 50345 第3.0.1条..." | `standard_clause` | `standard_code_exact`, `standard_precision`, `standard` | Standard outranks compiled truth. | Fixture eval + direct RAG. |
| Concept explanation | "防水等级和设防层数区别" | `concept_explanation` | standard, textbook, exam | Compiled truth only personalizes if available; not factual authority. | Source diversity + final answer sampling. |
| Case rubric lookup | "这类案例题采分点怎么写" | `rubric_lookup` | projected rubric, questions_bank, standard, compiled truth | Rubric/standard explain scoring; compiled truth says learner often misses which item. | Unit + QA harness. |
| Weak-point review | "我老是案例题采分点漏写怎么办" | `weak_point_review` | learner weak point, compiled truth, standard, questions_bank | Compiled truth can lead personalization but must cite support event ids. | `/wechat-harness` visible chain + Langfuse. |
| Next training | "下一题给我练专家论证" | `next_training` | learner weak point, questions_bank, typed graph | Training target uses graph; selected question still from question authority. | `deep_question` regression. |
| Cold-start learner | No compiled truth | fallback intent | standard/textbook/questions | Ordinary RAG; no empty personalization text. | Unit: no compiled context. |
| Stale weak point | Weak point superseded by improvement | weak-point query | compiled truth excluded or marked stale | Stale claims do not become active recommendation. | Learning synthesis + retrieval tests. |
| Manual correction | Teacher corrected a learner claim | weak-point query | corrected compiled truth | Manual `L2_confirmed` can boost, but source ids remain visible. | Manual correction fixture. |
| Retrieval degraded | Supabase 402 / timeout / rerank failure | any | fail closed | No raw provider error; no L1/L2 promotion from degraded evidence. | Existing failure contract tests. |
| Malicious context | Compiled truth contains prompt-like text | any personalized query | sanitized compiled docs | Treat compiled truth as untrusted retrieval content; no tool/prompt instruction leakage. | Security regression. |
| Mixed mode fast/deep | Same weak-point query in fast and deep | weak_point_review | same `RAGService` trace | Same source authority; modes differ only execution depth. | Fast/deep public WS trace pair. |
| Frontend visible QA | User reads report or harness | weak-point review | same backend evidence | Web harness may screen; mini-program smoke required only if mini files change. | Playwright + DevTools conditional. |

### 20.3 Revised Delivery Sequence

The first release should not enable every ranking change. Ship in layers:

| Phase | Ship | Ranking impact | Why this order |
| --- | --- | --- | --- |
| Phase A: Trace-only query plan | `retrieval_plan` emitted in `evidence_bundle` and Langfuse | None | Lowest risk; makes future failures debuggable. |
| Phase B: Compiled truth materializer in shadow mode | Materialized docs appear in `ranking_trace.shadow_sources` only | None | Validates projection shape, size, privacy, and token budget before affecting answers. |
| Phase C: Provenance feature extraction | `ranking_trace.provenance_features` emitted for all sources | None by default | Proves metadata quality without rank perturbation. |
| Phase D: Weak-point-only enablement | Compiled truth enters final sources only for `weak_point_review` and `next_training` | Limited | Highest product value, lowest risk to factual QA. |
| Phase E: Graph expansion | Typed graph expands training target and related question lookup | Limited | Only after weak-point source quality is verified. |
| Phase F: Maintenance workflows | Audit scripts and retrieval-maintenance skill | Offline only | Keeps knowledge quality durable without online complexity. |

Do not enable provenance rank changes globally until Phase D has passed live traces. If a release window is tight, Phase A + Phase B is still valuable and safe.

### 20.4 Ranking Policy Revision

The implementation must not use a simple global sort of `(authority_rank, score)` for every source. That is too blunt and can hide relevant supporting evidence. Use this safer policy:

1. **Pin only validated full exact authority.**
   - Pin `question_exact_text` only when existing exact validation says full coverage / option overlap / answer kind is valid.
   - Partial case exact is a high-authority source, not a final-answer shortcut.

2. **Use tier caps, not blind sorting.**
   - Tier 0: validated exact question.
   - Tier 1: standards and standard precision.
   - Tier 2: questions bank / rubric.
   - Tier 3: compiled learning truth.
   - Tier 4: textbook/exam semantic chunks.

3. **Compiled truth may personalize, not factualize.**
   - It can answer "why this learner should train X."
   - It cannot answer "what is the correct standard answer" without standard/question support.

4. **Provenance boost is bounded.**
   - Manual confirmation and `L2_confirmed` may boost inside the compiled-truth tier.
   - Stale, superseded, degraded, or unsupported claims are either excluded or capped at trace-only.

5. **Rerank input should include authority labels.**
   - Rerank candidates should include a compact prefix such as `[source_authority=standard]`, `[source_authority=compiled_learning_truth]`.
   - The prefix is for ranking context only and must not leak to final user text.

### 20.5 Security and Privacy Hardening

Compiled truth is durable learner-specific content. Treat it as untrusted and scoped:

1. Only pass compiled truth for the authenticated current user.
2. Never include wallet, phone, membership, account id aliases, or raw private profile fields.
3. Do not include full raw submissions by default; include short evidence event ids and compact rubric/error summaries.
4. Strip prompt-like blocks, XML-ish thinking blocks, tool instructions, and markdown that looks like system/developer instructions.
5. Cap materialized compiled docs by count, characters, and total token estimate:
   - max docs: `6`
   - max chars per doc: `700`
   - max compiled truth chars per retrieval: `2400`
6. Add `metadata.security.sanitized=true` and `metadata.security.redaction_count` to compiled docs.
7. If sanitization modifies a doc heavily, keep it in shadow trace only and add `retrieval_warning=compiled_truth_sanitized_heavily`.

### 20.6 Performance Budget

Online turn budget must stay predictable:

| Item | Budget |
| --- | --- |
| Query plan build | < 3 ms local CPU |
| Compiled truth materialization | < 10 ms local CPU, no I/O |
| Additional candidates into RRF | <= 6 docs |
| Additional rerank docs | <= 4 compiled docs, only when enabled |
| Added p95 latency target | <= 150 ms before external rerank variance |
| Langfuse metadata size | Keep `retrieval_plan` and `ranking_trace` compact; no full compiled projection in trace. |

If p95 overhead exceeds budget, keep Phase B shadow mode and postpone final-source enablement.

### 20.7 Data and Runtime Uncertainties

| Uncertainty | Risk | Verification | Alternative |
| --- | --- | --- | --- |
| TutorBot runtime may not currently carry `compiled_learning_truth` into tool context. | Task 5 could require larger runtime context work. | Inspect real `question_context` / runtime context and write a failing propagation test before editing. | First release supports only explicit caller-passed `compiled_learning_truth`; TutorBot propagation becomes a separate follow-up. |
| `summary_structured_json.learning_brain` projection may be too large or stale. | Token bloat or wrong personalization. | Measure projection size and `synthesis_run.generated_at` in local and Supabase rows. | Use only `weak_points[:3]` and `compiled_objects` by key lookup; ignore stale projections. |
| Langfuse metadata may truncate large ranking traces. | Observability appears incomplete. | Check ClickHouse `observations.metadata` size on a fresh local/live trace. | Store compact ids in metadata; write full debug payload only to local logs in dev. |
| Query intent heuristics may misclassify ambiguous Chinese queries. | Wrong source plan. | Fixture matrix + real logs from recent weak-point/standard/exact prompts. | Keep source plan broad and trace-only until enough eval cases pass. |
| Provenance boost may reduce recall for ordinary concept explanation. | Factual answer quality regresses. | A/B compare top sources on fixture suite before enabling. | Enable provenance boost only for weak-point and next-training intents. |
| Supabase quota / 402 can block live validation. | False diagnosis of ranking issue. | Run availability gate first and check project-level restriction. | Use local mocked pipeline + postpone live validation until service restriction clears. |
| WeChat mini-program may not surface new evidence fields. | Backend works, user cannot see value. | `/wechat-harness` first, DevTools only if mini files change. | Keep UI unchanged and validate answer text + trace first. |

### 20.8 Additional Tests Required Before Coding Completes

Add these tests beyond the original list:

1. `test_query_plan_trace_only_does_not_change_sources`
   - With `SUPABASE_RAG_QUERY_PLAN_TRACE_ENABLED=1` and all other new flags off, top sources must match baseline.

2. `test_compiled_truth_shadow_not_returned_in_sources`
   - With shadow enabled and final enablement off, compiled truth appears only in `ranking_trace.shadow_sources`.

3. `test_compiled_truth_sanitizes_prompt_injection`
   - Input compiled truth containing "ignore previous instructions" does not appear verbatim in `rag_content`.

4. `test_stale_compiled_truth_excluded_from_final_sources`
   - `stale=true` or `superseded_by_event_ids` excludes the doc from final sources unless explicitly in debug trace.

5. `test_partial_case_exact_still_runs_supplement`
   - Existing partial exact contract remains intact after query plan and provenance changes.

6. `test_standard_clause_not_personalized_as_truth`
   - Standard clause query may include learner context in trace, but final standard answer is not rewritten by compiled truth.

7. `test_fast_and_deep_share_retrieval_plan_shape`
   - For the same user/query/context, fast and deep emit the same retrieval plan core fields.

8. `test_langfuse_metadata_compact`
   - Serialized `retrieval_plan + ranking_trace` stays below a fixed size threshold.

### 20.9 Release Gates

Minimum release gates by phase:

| Phase | Required tests | Required live evidence |
| --- | --- | --- |
| A | RAG strategy + plan fixture tests | One local direct RAG trace with `retrieval_plan`. |
| B | Compiled truth source + sanitization tests | One `/api/v1/ws` trace with shadow compiled docs, no final source impact. |
| C | Provenance feature tests | One Langfuse/ClickHouse observation with compact `ranking_trace`. |
| D | Weak-point final-source tests + exact regression | One weak-point public WS trace and one exact-question public WS trace after restart. |
| E | Graph expansion tests + deep_question regression | One next-training visible run in `/wechat-harness`. |
| F | Maintenance script tests | Dry-run report from one real learner projection; no writes. |

Production enablement requires Phase D gates at minimum. Phase A-C may be deployed as observability-only.

### 20.10 Strong Recommendation

Implement the first production slice as:

1. Task 1: explicit retrieval plan.
2. Add `SUPABASE_RAG_QUERY_PLAN_TRACE_ENABLED=true`.
3. Task 2: compiled truth materializer, but only in shadow mode.
4. Task 3: provenance features, but no ranking change.
5. Add sanitization and compact trace tests.
6. Run local direct RAG + `/api/v1/ws` smoke.

Only after that should we wire final compiled truth sources into answers for `weak_point_review` and `next_training`.

The original larger plan remains valuable, but this revised slice is the current best route to a robust, shippable result under existing constraints.

## GSTACK REVIEW REPORT

> 由 `/gstack-plan-ceo-review` (2026-05-19 04:06, mode=HOLD SCOPE) + `/gstack-plan-eng-review` (2026-05-19 05:06, mode=FULL_REVIEW) 联合产出。用户决策 Approach A (Phase D 直接全量启用)。本节始终保持在 plan 文件最末。

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/gstack-plan-ceo-review` | Scope & strategy（HOLD SCOPE） | 1 | issues_open | 5 critical gaps、2 deferred TODO、0 unresolved |
| Outside Voice (CEO) | claude-subagent-fallback | Independent 2nd opinion at plan layer | 1 | issues_found | 新增 G5-G8 + 多处代码层 finding；强烈反对 Approach A |
| Eng Review | `/gstack-plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 22 issues, 9 critical gaps; A1/A2/Q1-Q7/P1-P5 + 验证 CEO 的 F1-F4/G5-G8 |
| Outside Voice (Eng) | claude-subagent-fallback-eng | Independent 2nd opinion at code layer | 1 | issues_found | N1-N7：N1+N2 (HIGH) session metadata stick + tool singleton 跨 user 残留；N5+N7 fast-path 静默禁用 rerank + capsule replace |
| Codex Review | `/codex review` | Diff 独立审查 | 0 | — | Codex CLI vendor binary ENOENT；fallback 走 Claude subagent |
| Design Review | `/gstack-plan-design-review` | UI/UX | 0 | — | n/a 本次启用 UX 无变化（A2 修正：capsule 是 LLM-context 注入，非 UI 框架变化） |

**CODEX**: Codex CLI 不可用 (`/Users/.../codex` ENOENT)，两轮 Outside Voice 都走 Claude subagent fallback。

**CROSS-MODEL**: Eng review + Outside Voice (Eng) 在 N1 / N2 / N5 / N7 上一致同意 — 新发现 4 个 CEO + 我自己第一遍 eng-review 都漏掉的 finding。Outside Voice 在 N4 (plan_id determinism) 假阳性，经验证 `expand_query_variants` 顺序稳定。用户对 Outside Voice 推 Approach B 灰度的建议未采纳，保持 A。

**UNRESOLVED**: 0（10 个 AskUserQuestion 全部应答；D9+D10 决策记录如下）。

**VERDICT**: **CEO + ENG HOLD_SCOPE CLEARED — pre-enable gates required**。Phase D 全量启用前必须完成 **9 项 P1 gate**（F1 + F2 + F3 + G5 + G6 + G7 + Q3 + P1 + P2）+ **4 项 P1 新增 gate**（N1 + N2 + N5 + N7）+ **1 项 P0**（A1 拆分支）= **共 14 项前置工作**。其后才能翻 `SUPABASE_RAG_COMPILED_TRUTH_ENABLED` / `SUPABASE_RAG_PROVENANCE_BOOST_ENABLED` 两个 flag。

### P0 — 必须先做（违反 AGENTS 硬约束）

- [ ] **A1 — branch discipline**: 把 `deeptutor/services/invite_test_applications.py` (727 行) + `web/app/invite-test/` (652 行) + 关联 tests/api 改动从 `codex/gbrain-learning-brain` 抽到独立分支独立 PR；当前分支只保留 Learning Brain 主线。AGENTS §3.6 narrow scope。

### P1 — Phase D 全量启用前置 Gate

- [ ] **F1 — pipeline** (Section 2+4+9 / Outside Voice CEO): `supabase.py:858 compiled_only_fast_path` 加 sparse-projection fallback：compiled truth 文档数 <2 或 `typed_graph.edges` 空时不触发 fast-path
- [ ] **F2 — observability** (Section 8+9): 接 launch_readiness_dashboard 五个指标：(a) exact_question chunk_id 命中率 by intent (b) compiled_truth_final_enabled=true 占比 by intent (c) p95 latency by intent (d) sanitize 错误占比 (e) capsule 实际生成占比 + LLM 引用 chunk_id 占比 (A2)
- [ ] **F3 — ops**: 新建 `docs/ops/phase-d-enablement-runbook.md`：trigger 阈值、env flag flip 顺序、`/root/deeptutor` 写边界校验、验证 SQL、回退步骤；挂 `docs/plan/INDEX.md`
- [ ] **G5 — security** (Outside Voice CEO): `RAGService.search` / `SupabasePipeline.search` 加 `compiled_learning_truth['user_id'] == 当前调用 user_id` 断言 + cross-tenant leak 回归测试
- [ ] **G6 — observability** (Outside Voice CEO): `retrieval_plan_json + ranking_trace_json` size-bound 单测（6-doc + 20-feature projection 下 < 4000 chars）+ 超限 compact fallback
- [ ] **G7 — test** (Outside Voice CEO): `test_rag_pipelines.py` 加 rerank+compiled+exact 三者同存集成测试；`provenance.py:102` pin 改用 `chunk_id` 而非 `id()`
- [ ] **A2 — observability** (Section 1 — eng review 新发现): F2 dashboard 包含 capsule 监控两个指标（F2 task 内 e 子项已写）
- [ ] **Q3 — observability** (Section 2): `compiled_truth_source.py` heavily_sanitized 时 emit `retrieval_warning=compiled_truth_silently_demoted` + F2 加被静默降级学员占比 metric
- [ ] **P1 — performance** (Section 4): `compiled_truth_source.py:245` 前置 `weak_points = weak_points[:50]` cap；O(weak × edges) 防爆
- [ ] **P2 — test** (Section 4): `test_compiled_only_fast_path_sparse.py` 加 perf assertion (fast-path total < 80ms / 通用 < 200ms)
- [ ] **N1 — security** (Outside Voice Eng, **HIGH**): `manager.py:802` session metadata merge 改为 ephemeral key strip — 每次 update 前从 `session.metadata` 删除 `compiled_learning_truth` / `retrieval_runtime_context` 等 ephemeral key；避免旧 projection 永久 stick
- [ ] **N2 — security** (Outside Voice Eng, **HIGH**): `loop.py:_set_tool_context` 加 try/finally 保证每 turn entry 必走 + tool 加显式 `reset_runtime_context()` 接口；异常路径 prior user runtime_context 不残留；写跨 user 隔离回归测试
- [ ] **N5 — observability** (Outside Voice Eng): `supabase.py:864 compiled_only_fast_path` 进入时 `retrieval_warnings.append(fast_path_no_rerank)`；F2 dashboard 加该 warning 占比 metric
- [ ] **N7 — capability** (Outside Voice Eng): `deeptutor_tools.py:189-191` `_build_learning_fact_capsule` 改 augment：`return capsule + "\n\n" + original_answer` 而非完全 replace；flag 翻动时答案形状不突变

### P2 — 启用后 Followups（挂 `docs/plan/INDEX.md` Backlog）

- [ ] **F4 — capability**: `deep_question` 消费 `compiled_learning_truth.weak_points` / `typed_graph.edges` 选题；解锁 retrieval upgrade 完整 ROI；H+72 质量信号确认后立项
- [ ] **G8 — policy**: stale weak point 时间策略；决定 writer-side decay marker only 还是 RAG-side cutoff days
- [ ] **Q1 — refactor**: 合并 `_compiled_truth_plan` / `_final_compiled_truth_plan` / `_ensure_final_compiled_truth_presence` 三方法为单一 `_compiled_truth_pipeline()` 状态机
- [ ] **N3 — concurrency**: `_last_trace_metadata` 改按 call_id 隔离；agentic_pipeline 并发不互相覆盖
- [ ] **N4 — test**: `test_retrieval_plan.py` 加 plan_id stability assertion（跨进程同 query+context 必须产同 plan_id）
- [ ] **N6 — errors**: `service.read_compiled_learning_truth` 区分 has_no_projection vs read_failed；emit metric

### NOT in scope

- 新增 RAG provider / vector store / 图数据库（plan §2 Non-Goals + AGENTS Single Authority）
- 新增 `/api/v1/...` 聊天 WS（AGENTS 流式入口唯一硬约束）
- 让 compiled truth outrank full `exact_question`（plan §2 + §20.4 Ranking Policy）
- Approach B 灰度 cohort（用户已选 A，两轮 Outside Voice 反对意见已留痕）
- invite_test 主线后续开发（P0 拆分支后归独立 plan）

### Critical Gaps Registry（Phase D 启用后新增 / 暴露的失败模式）

| Codepath | Failure | Rescued | Tested | User Sees | Logged | Gap → Fix |
| --- | --- | --- | --- | --- | --- | --- |
| `manager.py:802 session.metadata.update` | 旧 compiled_truth 永久 stick 跨 turn | N | N | A 学员旧 projection 影响新 turn | N | **N1 HIGH** |
| `loop.py:310 _set_tool_context happy-path-only` | 异常路径 prior user runtime_context 残留 | N | N | cross-user compiled_truth 泄漏 | N | **N2 HIGH** |
| RAG 边界无 `user_id` 断言 | compiled_truth 错配 | N | N | A 看到 B 训练 | N | **G5** |
| `supabase.py:858 compiled_only_fast_path` | sparse projection → 近空推荐 | N | N | 题极少 | partial | **F1** |
| `supabase.py:864 fast-path 静默禁用 rerank+second_pass` | next_training 失去质量校准 | N | N | 答案波动 | N | **N5** |
| `supabase.py:874 _assert_data_api_available 仅 else` | Supabase 402 在 next_training 假 OK | N | N | RAG 死看不见 | partial | **F2 metric** |
| `langfuse_adapter.py text_limit=4000` | ranking_trace_json > 4KB → 截断 | N | N | dashboard 失效 | partial | **G6** |
| `supabase.py:1053 rerank w/o exact-awareness` | rerank demote 已 pin exact | partial | N | exact 被覆盖 | Y | **G7** |
| `provenance.py:672 _pin via id()` | dict 重建断 pin | partial | N | exact 漂移 | N | **G7 测试** |
| `deeptutor_tools.py:287 capsule replaces answer` | flag 翻动答案形状突变 | N | partial | weak/next intent 答案被替换 | partial | **N7** |
| `compiled_truth_source.py:301 heavily_sanitized 静默 shadow` | 大量 PII 学员被静默降级 | partial | N | 该学员 Phase D 无效 | N | **Q3** |
| `compiled_truth_source.py:182 O(weak × edges) 无 cap` | 异常 projection 拖慢 turn | N | N | latency 漂移 | partial | **P1** |
| `compiled_truth_source.py:72 stale 字段-only` | 写入侧不打 decay → 永远新鲜 | partial | partial | 老 weak point 进训练 | N | **G8 TODO** |
| `_compiled_truth_plan / _final / _ensure 三方法` | 改一个忘另一个 | N | partial | 回归概率高 | N | **Q1 TODO** |
| `_last_trace_metadata 并发覆盖` | 并发 tool 调用 trace 错位 | N | N | trace 归属错乱 | N | **N3 TODO** |
| `service.read_compiled_learning_truth except 静默` | 读失败 vs 无投影无法区分 | N | partial | F4 无法决策 | N | **N6 TODO** |
| cold-start（无 compiled truth） | fail-closed 走通用 RAG | Y | Y | 通用回答 | Y | **OK** |
| exact_question 全覆盖命中 | compiled truth 排出 final | Y | Y (line 443) | exact 优先 | Y | **OK** |
| sanitize prompt injection | "ignore previous instructions" 不入 rag_content | Y | Y (test 90) | LLM 不被劫持 | Y | **OK** |

### Implementation Tasks (synthesized from this review)

挂在 `~/.gstack/projects/chenyh200807-luban-deep/`:

- CEO tasks: `tasks-ceo-review-20260519-120641.jsonl` (8 项)
- Eng tasks: `tasks-eng-review-20260519-130611.jsonl` (14 项)
- Test plan: `yehongchen-codex-gbrain-learning-brain-eng-review-test-plan-20260519-122414.md`

### Worktree parallelization

| Lane | Tasks | Modules | 依赖 |
|---|---|---|---|
| A | A1 拆分支 | invite_test 文件群 | — (先做，独立) |
| B | F1 + N5 + P1 | services/rag/pipelines/supabase.py + compiled_truth_source.py | A 完成后 |
| C | G5 + N1 + N2 + N7 | rag/service.py + tutorbot/agent/loop.py + tools/deeptutor_tools.py + services/tutorbot/manager.py | A 完成后；与 B 共享 supabase.py，**有冲突，串行** |
| D | F2 + A2 + Q3 + N5-metric | docs/plan/launch_readiness + supabase observability | 与 B/C 并行 OK |
| E | F3 | docs/ops/phase-d-runbook | 独立 |
| F | G6 | observability/langfuse_adapter.py + supabase.py | 与 B/C 共享 supabase.py，**串行** |
| G | G7 + P2 | tests/services/rag/ | C/B 完成后 |

**执行顺序**: A (拆分支) → 并行 (D + E) → B → C → F → G。

### Decisions log（本次 review 的 10 个 AskUserQuestion）

| ID | 问题 | 用户决策 |
|---|---|---|
| D1 (CEO) | Phase D 启用方式 | A) 直接全量启用 |
| D2 (CEO) | 审查模式 | HOLD SCOPE |
| F1-F4 (CEO) | 4 个 critical 处理 | F1/F2/F3 → A 前置 gate；F4 → A TODO |
| T1-T3 (CEO) | Outside Voice 4 个 gate | reviewer 默认推荐合成：G5+G6 → 前置；G7 → 前置；G8 → TODO |
| D1 (Eng) | eng-review 范围 | B) 全诊 17126 行 diff |
| D2 (Eng) | A1 invite_test 同分支 | A) 拆分支 |
| D3 (Eng) | A2 capsule 监控 | A) F2 加两指标 |
| D4 (Eng) | Q1 三方法重叠 | A) 推后 P2 |
| D5 (Eng) | Q3 sanitize 静默降级 | A) 前置 emit warning |
| D6 (Eng) | P1 cap 缺失 | A) 启用前加 cap |
| D7 (Eng) | P2 fast-path latency 断言 | A) 加 perf fixture |
| D8 (Eng) | 跑第二次 Outside Voice | A) 跑 |
| D9 (Eng) | N1+N2 跨 user 泄漏 | A) 启用前双补 |
| D10 (Eng) | N5+N7 capsule + rerank | A) N5 告警 + N7 augment |
