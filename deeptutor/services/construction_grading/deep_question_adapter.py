from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.compiled_context import (
    build_pack_from_question_context,
)
from deeptutor.services.construction_grading.mcq import grade_mcq_submission

_CHOICE_TYPES = {
    "choice",
    "single_choice",
    "single",
    "multi_choice",
    "multiple_choice",
    "multiple",
    "judge",
    "judgment",
    "true_false",
}

_CASE_TYPES = {
    "written",
    "case",
    "case_study",
    "short_answer",
    "open_ended",
    "essay",
}


def _stamp_compiled_context_and_authority(
    result: dict[str, Any],
    row: dict[str, Any],
    *,
    retrieval_sources: list[dict[str, Any]] | None = None,
) -> None:
    """Attach the unified compiled_context AND an honest answer-key authority stamp (M27 closure).

    Authority discipline (master plan §0.26.3): a ``correct_answer`` that is merely PRESENT in the
    inbound question context (e.g. client-supplied via the WS frame) is NOT a governed release-truth
    answer key. The deep_question runtime does not yet bind objective answer keys to the governed
    questions_bank / signed registry, so such a score is FORMATIVE only — it must never be laundered
    into an official release-truth score. We keep the formative score/is_correct unchanged (no UX or
    test breakage) but stamp the provenance so no downstream consumer (or red-team oracle) can treat
    a client-supplied answer key as governed truth.

    When the pack reports ``official_score_allowed`` (a signed release/published registry resolved
    the answer key server-side), the result is marked governed release-truth instead.
    """
    pack = build_pack_from_question_context(row, retrieval_sources=retrieval_sources)
    result["compiled_context"] = pack.to_dict()
    official = pack.official_score_allowed
    result["release_truth"] = bool(official)
    result["answer_key_authority"] = (
        "governed_signed_registry" if official else "context_supplied_unverified"
    )
    if not official:
        # No governed binding -> governance status is unresolved; score stays formative, not official.
        result.setdefault("registry_status", "unresolved")
        result["official_release_score"] = False
        result["not_production_grade"] = True
        result["official_score_laundering_guard"] = "client_or_context_answer_key_not_release_truth"


def build_deep_question_grading_result(
    question_context: dict[str, Any],
    *,
    user_answer: str,
) -> dict[str, Any] | None:
    """Build the single authoritative grading result for deep_question submissions."""

    if not isinstance(question_context, dict):
        return None
    answer = str(user_answer or "").strip()
    if not answer:
        return None

    row = _question_row_from_context(question_context)
    question_type = str(row.get("question_type") or "").strip().lower()
    if _is_choice_context(row):
        result = grade_mcq_submission(row, answer).to_dict()
        for key in (
            "question_stem",
            "stem",
            "question_text",
            "question",
            "options",
            "option_reasoning",
            "analysis",
            "testing_focus",
            "node_code",
        ):
            if key in row and row.get(key) not in (None, "", [], {}):
                result[key] = row.get(key)
        result["type"] = "mcq"
        result["authority"] = "construction_grading"
        _stamp_compiled_context_and_authority(result, row)
        return result
    if question_type in _CASE_TYPES:
        result = CaseGradingSkillKernel().grade(
            question_row=row,
            user_answer=answer,
            evidence_rows=_evidence_rows_from_context(row),
        ).to_dict()
        result["type"] = "case"
        result["authority"] = "construction_grading"
        result["question_type"] = question_type or "case"
        result["user_answer"] = answer
        _stamp_compiled_context_and_authority(
            result, row, retrieval_sources=_evidence_rows_from_context(row)
        )
        # v1 rubric-scored shadow (Nexus-like, non-authoritative): per-scoring-point LLM adjudication
        # over the compiled rubric -> GradingEvent + learning_evidence. Append-only; never replaces the
        # v0 result or grants official score. QA/test students only. Falls through silently on any issue.
        _attach_rubric_v1_shadow(result, row, answer)
        return result
    return None


def _attach_rubric_v1_shadow(result: dict[str, Any], row: dict[str, Any], answer: str) -> None:
    """Run the v1 rubric grader as a non-authoritative shadow and append it to the case result."""
    try:
        import os

        from deeptutor.services.construction_grading import rubric_grader_v1 as _G
        from deeptutor.services.construction_grading import runtime_shadow_adapter as _A

        qid = str(row.get("question_id") or row.get("id") or "").strip()
        student_id = str(row.get("student_id") or row.get("user_id") or "").strip()
        node_code = str(row.get("node_code") or "")
        if not qid or not _A._is_safe_shadow_student_id(student_id):
            return  # non-cohort / no qid -> no shadow (real students unaffected)
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            return
        from deeptutor.services.llm.factory import complete
        judge = _G.make_llm_judge(complete, key, model="deepseek-chat")
        shadow = _A.build_rubric_v1_shadow_result(
            question_id=qid, student_answer=answer, student_id=student_id,
            node_code=node_code, judge_fn=judge,
        )
        if shadow.get("status") == "ok":
            result["rubric_v1_shadow"] = shadow  # non-authoritative; official_score_allowed=False
    except Exception:  # noqa: BLE001 — shadow must never break the authoritative v0 result
        return


def _evidence_rows_from_context(question_context: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ref in list(question_context.get("evidence_refs") or []):
        if not isinstance(ref, dict):
            continue
        source = str(ref.get("source") or ref.get("source_type") or "").strip()
        field = str(ref.get("field") or ref.get("content_type") or "content").strip()
        content = ref.get("content")
        if content in (None, ""):
            content = ref.get("text")
        if content in (None, ""):
            content = ref.get("rag_content")
        if content in (None, ""):
            content = ref.get("value")
        if source and field and content not in (None, "", [], {}):
            rows.append({"source": source, "field": field, "content": content})
    return rows


def attach_deep_question_grading_result(
    question_context: dict[str, Any],
) -> dict[str, Any]:
    """Attach construction grading result without changing deep_question's ownership."""

    context = dict(question_context or {})
    items = context.get("items") or []
    if isinstance(items, list) and items:
        graded_items: list[dict[str, Any]] = []
        result_items: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                graded_items.append(item)
                continue
            graded_item = dict(item)
            item_result = build_deep_question_grading_result(
                graded_item,
                user_answer=str(graded_item.get("user_answer") or "").strip(),
            )
            if item_result:
                graded_item["construction_grading_result"] = item_result
                graded_item["is_correct"] = _result_is_full_score(item_result)
                graded_item["score"] = _result_percentage_score(item_result)
                result_items.append(item_result)
            graded_items.append(graded_item)
        if result_items:
            context["items"] = graded_items
            score_awarded = sum(float(item.get("score_awarded") or 0) for item in result_items)
            max_score = sum(float(item.get("max_score") or 0) for item in result_items)
            context["construction_grading_result"] = {
                "type": "batch",
                "authority": "construction_grading",
                "score_awarded": score_awarded,
                "max_score": max_score,
                "items": result_items,
            }
            context["is_correct"] = max_score > 0 and score_awarded >= max_score
            context["score"] = _percentage(score_awarded, max_score)
            context["diagnosis"] = (
                "CORRECT"
                if context["is_correct"]
                else "PARTIAL"
                if score_awarded > 0
                else "CONFUSION"
            )
        return context

    result = build_deep_question_grading_result(
        context,
        user_answer=str(context.get("user_answer") or "").strip(),
    )
    if not result:
        return context
    context["construction_grading_result"] = result
    context["is_correct"] = _result_is_full_score(result)
    context["score"] = _result_percentage_score(result)
    if context["is_correct"]:
        context["diagnosis"] = "CORRECT"
    elif result.get("type") == "case" and float(result.get("score_awarded") or 0) > 0:
        context["diagnosis"] = "PARTIAL"
    elif result.get("type") == "case":
        context["diagnosis"] = "采分点遗漏"
    elif not str(context.get("diagnosis") or "").strip():
        context["diagnosis"] = "CONFUSION"
    return context


def _question_row_from_context(question_context: dict[str, Any]) -> dict[str, Any]:
    row = dict(question_context)
    question = str(
        row.get("question_stem")
        or row.get("stem")
        or row.get("question")
        or row.get("question_text")
        or ""
    ).strip()
    row.setdefault("question_stem", question)
    row.setdefault("stem", question)
    row.setdefault("question_text", question)
    row.setdefault("testing_focus", row.get("concentration") or row.get("testing_focus") or "")
    if not row.get("id"):
        row["id"] = row.get("question_id") or row.get("original_id") or ""
    return row


def _is_choice_context(row: dict[str, Any]) -> bool:
    question_type = str(row.get("question_type") or "").strip().lower()
    if question_type in _CHOICE_TYPES:
        return True
    options = row.get("options")
    correct = str(row.get("correct_answer") or "").strip()
    return isinstance(options, dict) and bool(options) and bool(correct)


def _result_is_full_score(result: dict[str, Any]) -> bool:
    max_score = float(result.get("max_score") or 0)
    score_awarded = float(result.get("score_awarded") or 0)
    return max_score > 0 and score_awarded >= max_score


def _result_percentage_score(result: dict[str, Any]) -> int:
    return _percentage(float(result.get("score_awarded") or 0), float(result.get("max_score") or 0))


def _percentage(score_awarded: float, max_score: float) -> int:
    if max_score <= 0:
        return 0
    return int(round((score_awarded / max_score) * 100))
