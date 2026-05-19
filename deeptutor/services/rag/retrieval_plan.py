"""Deterministic retrieval planning for source-aware RAG."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from deeptutor.services.rag.pipelines.supabase_strategy import (
    classify_query_shape,
    expand_query_variants,
    extract_standard_codes,
    select_sources,
)


@dataclass(frozen=True, slots=True)
class RetrievalSourceGroup:
    name: str
    enabled: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    schema_version: int
    plan_id: str
    intent: str
    query_shape: str
    primary_query: str
    source_groups: dict[str, RetrievalSourceGroup] = field(default_factory=dict)
    expanded_queries: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    authority_order: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "intent": self.intent,
            "query_shape": self.query_shape,
            "primary_query": self.primary_query,
            "source_groups": [group.to_dict() for group in self.source_groups.values()],
            "expanded_queries": list(self.expanded_queries),
            "reasons": list(self.reasons),
            "authority_order": list(self.authority_order),
        }


_AUTHORITY_ORDER = [
    "exact_question",
    "standard_code_exact",
    "standard_precision",
    "standard",
    "questions_bank",
    "compiled_learning_truth",
    "textbook",
    "exam",
]


def _truthy(value: Any) -> bool:
    if value in (None, False, "", [], {}):
        return False
    return True


def _infer_intent(
    query: str,
    *,
    query_shape: str,
    intent: str,
    question_type: str,
    routing_metadata: dict[str, Any],
) -> tuple[str, list[str]]:
    if intent:
        return intent, ["upstream_intent"]
    if question_type:
        return "training_question_needed", ["upstream_question_type"]
    text = str(query or "").lower()
    next_training_terms = ("下一题", "下道题", "继续练", "练一题", "训练", "专项练")
    if any(term in text for term in next_training_terms):
        return "next_training", ["next_training_terms"]
    weak_terms = ("薄弱", "错因", "丢分", "漏写", "漏答", "弱点", "不会", "老是", "反复")
    if any(term in text for term in weak_terms):
        return "weak_point_review", ["weak_point_terms"]
    rubric_terms = ("采分点", "扣分", "评分标准", "标准表达", "答题模板")
    if any(term in text for term in rubric_terms):
        return "rubric_lookup", ["rubric_terms"]
    if query_shape == "standard_like":
        return "standard_clause", ["standard_like_query"]
    if query_shape in {"mcq_like", "case_like"}:
        return "exact_question", ["question_like_query"]
    return "concept_explain", ["default_concept_query"]


def _source_group(name: str, enabled: bool, reason: str) -> RetrievalSourceGroup:
    return RetrievalSourceGroup(name=name, enabled=enabled, reason=reason if enabled else "not_selected")


def build_retrieval_plan(
    query: str,
    *,
    include_questions_default: bool = True,
    intent: str = "",
    question_type: str = "",
    routing_metadata: dict[str, Any] | None = None,
    max_expanded_queries: int = 5,
) -> RetrievalPlan:
    metadata = routing_metadata if isinstance(routing_metadata, dict) else {}
    text = str(query or "").strip()
    source_plan = select_sources(
        text,
        include_questions_default=include_questions_default,
        intent=intent,
        question_type=question_type,
        routing_metadata=metadata,
    )
    query_shape = str(source_plan.query_shape or classify_query_shape(text))
    inferred_intent, reasons = _infer_intent(
        text,
        query_shape=query_shape,
        intent=str(intent or "").strip(),
        question_type=str(question_type or "").strip(),
        routing_metadata=metadata,
    )
    standard_codes = extract_standard_codes(text)
    compiled_truth_available = _truthy(metadata.get("compiled_learning_truth_available"))
    wants_compiled_truth = inferred_intent in {"weak_point_review", "next_training"}
    expanded = expand_query_variants(text, max_variants=max_expanded_queries)
    if not expanded:
        expanded = [text]

    groups = {
        "compiled_learning_truth": _source_group(
            "compiled_learning_truth",
            bool(compiled_truth_available and wants_compiled_truth),
            inferred_intent or "compiled_truth_context",
        ),
        "questions_bank": _source_group(
            "questions_bank",
            bool(source_plan.search_questions_bank),
            "training_question_needed" if source_plan.search_questions_bank else "",
        ),
        "standard": _source_group(
            "standard",
            bool(source_plan.search_standard_chunks),
            "authority_grounding" if source_plan.search_standard_chunks else "",
        ),
        "standard_code_exact": _source_group(
            "standard_code_exact",
            bool(standard_codes and source_plan.search_standard_chunks),
            "standard_code",
        ),
        "textbook": _source_group(
            "textbook",
            bool(source_plan.search_textbook_chunks),
            "concept_grounding" if source_plan.search_textbook_chunks else "",
        ),
        "exam": _source_group(
            "exam",
            bool(source_plan.search_exam_chunks),
            "exam_pattern" if source_plan.search_exam_chunks else "",
        ),
    }
    reasons.extend(list(getattr(source_plan, "selection_reasons", []) or []))
    if compiled_truth_available:
        reasons.append("compiled_learning_truth_available")
    if standard_codes:
        reasons.append("standard_code")
    plan_seed = {
        "query": text,
        "intent": inferred_intent,
        "query_shape": query_shape,
        "groups": [(name, group.enabled) for name, group in groups.items()],
        "expanded": expanded,
    }
    plan_id = hashlib.sha256(repr(plan_seed).encode("utf-8")).hexdigest()[:12]
    return RetrievalPlan(
        schema_version=1,
        plan_id=plan_id,
        intent=inferred_intent,
        query_shape=query_shape,
        primary_query=expanded[0] if expanded else text,
        source_groups=groups,
        expanded_queries=expanded[:max_expanded_queries],
        reasons=list(dict.fromkeys(reason for reason in reasons if reason)),
        authority_order=list(_AUTHORITY_ORDER),
    )
