from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_CURRENT_INFO_KEYWORDS = (
    "最新",
    "现行",
    "当前",
    "今年",
    "最近",
    "政策",
    "通知",
    "公告",
    "新规",
    "发文",
    "变化",
)

_TEXTBOOK_DELTA_MARKERS = (
    "变化",
    "变动",
    "更新",
    "改版",
    "调整",
    "新增",
    "删除",
    "对比",
    "不一样",
)

_GROUNDED_CONSTRUCTION_EXAM_KB_ALIASES = {
    "construction-exam",
    "construction-exam-coach",
    "construction-exam-tutor",
    "construction_exam_tutor",
}


@dataclass(slots=True)
class GroundingDecision:
    grounded_construction_exam_runtime: bool = False
    current_info_required: bool = False
    textbook_delta_query: bool = False
    exact_question_candidate: bool = False
    practice_generation_request: bool = False
    rag_enabled: bool = False
    tutorbot_context: bool = False
    followup_question: bool = False
    answer_type: str = ""
    should_force_retrieval_first: bool = False
    should_prefetch_grounded_rag: bool = False
    should_try_exact_fast_path: bool = False
    reasons: list[str] = field(default_factory=list)


def normalize_query_text(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def query_requires_current_info(query: str) -> bool:
    text = normalize_query_text(query)
    return any(keyword in text for keyword in _CURRENT_INFO_KEYWORDS)


def looks_like_textbook_delta_query(query: str) -> bool:
    text = normalize_query_text(query)
    return "教材" in text and any(marker in text for marker in _TEXTBOOK_DELTA_MARKERS)


def has_grounded_construction_exam_kb(
    *,
    default_kb: str = "",
    knowledge_bases: list[str] | tuple[str, ...] | None = None,
    kb_aliases: list[str] | tuple[str, ...] | None = None,
) -> bool:
    direct = str(default_kb or "").strip().lower()
    if direct in _GROUNDED_CONSTRUCTION_EXAM_KB_ALIASES:
        return True

    for values in (knowledge_bases, kb_aliases):
        if not isinstance(values, (list, tuple)):
            continue
        for item in values:
            normalized = str(item or "").strip().lower()
            if normalized in _GROUNDED_CONSTRUCTION_EXAM_KB_ALIASES:
                return True
    return False


def build_grounding_decision(
    *,
    query: str,
    default_kb: str = "",
    knowledge_bases: list[str] | tuple[str, ...] | None = None,
    kb_aliases: list[str] | tuple[str, ...] | None = None,
    rag_enabled: bool = False,
    tutorbot_context: bool = False,
    followup_question: bool = False,
    answer_type: str = "",
    current_info_required_hint: bool = False,
    exact_question_candidate: bool = False,
    practice_generation_request: bool = False,
) -> GroundingDecision:
    normalized_answer_type = str(answer_type or "").strip().lower()
    reasons: list[str] = []
    grounded_runtime = has_grounded_construction_exam_kb(
        default_kb=default_kb,
        knowledge_bases=knowledge_bases,
        kb_aliases=kb_aliases,
    )
    if grounded_runtime:
        reasons.append("grounded_construction_exam_runtime")

    current_info_required = bool(current_info_required_hint) or query_requires_current_info(query)
    textbook_delta = looks_like_textbook_delta_query(query)
    if current_info_required:
        reasons.append("current_info_required")
    if textbook_delta:
        reasons.append("textbook_delta_query")
    if exact_question_candidate:
        reasons.append("exact_question_candidate")
    if practice_generation_request:
        reasons.append("practice_generation_request")
    if followup_question:
        reasons.append("followup_question")
    if tutorbot_context:
        reasons.append("tutorbot_context")
    if rag_enabled:
        reasons.append("rag_enabled")

    should_force_retrieval_first = False
    if grounded_runtime and rag_enabled:
        if followup_question:
            should_force_retrieval_first = True
        elif normalized_answer_type in {"knowledge_explainer", "problem_solving"}:
            should_force_retrieval_first = True
        elif tutorbot_context and len(str(query or "").strip()) >= 40:
            should_force_retrieval_first = True
    if should_force_retrieval_first:
        reasons.append("force_retrieval_first")

    should_prefetch_grounded_rag = (
        grounded_runtime
        and not exact_question_candidate
        and not practice_generation_request
        and (current_info_required or textbook_delta)
    )
    if should_prefetch_grounded_rag:
        reasons.append("prefetch_grounded_rag")

    should_try_exact_fast_path = (
        grounded_runtime
        and exact_question_candidate
        and not (practice_generation_request and tutorbot_context)
    )
    if should_try_exact_fast_path:
        reasons.append("exact_fast_path")

    return GroundingDecision(
        grounded_construction_exam_runtime=grounded_runtime,
        current_info_required=current_info_required,
        textbook_delta_query=textbook_delta,
        exact_question_candidate=exact_question_candidate,
        practice_generation_request=practice_generation_request,
        rag_enabled=rag_enabled,
        tutorbot_context=tutorbot_context,
        followup_question=followup_question,
        answer_type=normalized_answer_type,
        should_force_retrieval_first=should_force_retrieval_first,
        should_prefetch_grounded_rag=should_prefetch_grounded_rag,
        should_try_exact_fast_path=should_try_exact_fast_path,
        reasons=reasons,
    )


def build_grounding_decision_from_metadata(
    *,
    query: str,
    runtime_metadata: dict[str, Any] | None,
    rag_enabled: bool = False,
    tutorbot_context: bool = False,
    followup_question: bool = False,
    answer_type: str = "",
    exact_question_candidate: bool = False,
    practice_generation_request: bool = False,
) -> GroundingDecision:
    metadata = runtime_metadata if isinstance(runtime_metadata, dict) else {}
    knowledge_bases = metadata.get("knowledge_bases")
    kb_aliases = metadata.get("kb_aliases")
    return build_grounding_decision(
        query=query,
        default_kb=str(metadata.get("default_kb") or "").strip(),
        knowledge_bases=knowledge_bases if isinstance(knowledge_bases, (list, tuple)) else None,
        kb_aliases=kb_aliases if isinstance(kb_aliases, (list, tuple)) else None,
        rag_enabled=rag_enabled,
        tutorbot_context=tutorbot_context,
        followup_question=followup_question,
        answer_type=answer_type,
        current_info_required_hint=bool(metadata.get("current_info_required")),
        exact_question_candidate=exact_question_candidate,
        practice_generation_request=practice_generation_request,
    )
