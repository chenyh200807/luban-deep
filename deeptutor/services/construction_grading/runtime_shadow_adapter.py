"""Runtime shadow adapter for Luban construction grading.

This module adapts the real deep_question submission shape into the existing
Luban AI-Draft/Best-Quality shadow engines. It is deliberately non-authoritative:
no DB writes, no Learning Brain writes, no CaseGradingSkillKernel calls, no RAG.
"""
from __future__ import annotations

from typing import Any, Callable, Literal

from deeptutor.services.construction_grading.artifact_runtime_gate import (
    ARTIFACT_MISSING,
    ArtifactRuntimeGate,
    resolve_runtime_artifact_gate,
)
from deeptutor.services.construction_grading.best_quality_ai_draft import (
    CACHED_4MODEL,
    BestQualityUnavailable,
    best_quality_draft,
    load_cached_4model_predictions,
)
from deeptutor.services.construction_grading.question_grading_registry import (
    QuestionGradingRegistry,
    get_question_grading_artifact,
)

LEGACY_MODE = "legacy"
LUBAN_AI_DRAFT_SHADOW_MODE = "luban_ai_draft_shadow"
LUBAN_BEST_QUALITY_SHADOW_MODE = "luban_best_quality_shadow"

_SHADOW_MODES = {LUBAN_AI_DRAFT_SHADOW_MODE, LUBAN_BEST_QUALITY_SHADOW_MODE}

ShadowBuilder = Callable[..., dict[str, Any]]


class RuntimeShadowUnavailable(Exception):
    """Raised when a shadow engine cannot run without fabricating output."""


def attach_runtime_shadow_result(
    submission: dict[str, Any],
    *,
    legacy_grading_result: dict[str, Any] | None,
    grading_engine_mode: str = LEGACY_MODE,
    ai_draft_builder: ShadowBuilder | None = None,
    best_quality_builder: ShadowBuilder | None = None,
) -> dict[str, Any]:
    """Return legacy result plus optional shadow result without mutating legacy."""

    if grading_engine_mode == LEGACY_MODE:
        return {
            "grading_engine_mode": LEGACY_MODE,
            "legacy_grading_result": legacy_grading_result,
            "shadow_result": None,
        }
    return {
        "grading_engine_mode": grading_engine_mode,
        "legacy_grading_result": legacy_grading_result,
        "shadow_result": build_runtime_shadow_result(
            submission,
            grading_engine_mode=grading_engine_mode,
            ai_draft_builder=ai_draft_builder,
            best_quality_builder=best_quality_builder,
        ),
    }


def build_runtime_shadow_result(
    submission: dict[str, Any] | None = None,
    *,
    grading_engine_mode: str | None = None,
    question_id: str | None = None,
    student_id: str | None = None,
    student_answer: str | None = None,
    engine: Literal["deepseek_fast", "best_quality_4model"] | str | None = None,
    qa_shadow: bool = True,
    registry: QuestionGradingRegistry | None = None,
    ai_draft_builder: ShadowBuilder | None = None,
    best_quality_builder: ShadowBuilder | None = None,
    prediction_student_id: str | None = None,
) -> dict[str, Any]:
    """Build a non-production Luban shadow result for one real submission shape."""

    if submission is None:
        submission = {
            "student_id": student_id,
            "question_followup_context": {
                "question_id": question_id,
                "question_type": "case",
                "user_answer": student_answer,
            },
        }
    if grading_engine_mode is None:
        grading_engine_mode = _mode_from_engine(engine)
    if grading_engine_mode == LEGACY_MODE:
        return {}
    if grading_engine_mode not in _SHADOW_MODES:
        return _fail_closed_result(
            engine=_engine_name(grading_engine_mode),
            question_id=_question_id_from_submission(submission),
            student_id=_student_id_from_submission(submission),
            gate=None,
            error="unsupported_grading_engine_mode",
            message=grading_engine_mode,
        )

    question_id = _question_id_from_submission(submission)
    student_id = _student_id_from_submission(submission)
    student_answer = _student_answer_from_submission(submission)
    if qa_shadow and not _is_safe_shadow_student_id(student_id):
        return _fail_closed_result(
            engine=_engine_name(grading_engine_mode),
            question_id=question_id,
            student_id=student_id,
            gate=None,
            error="qa_student_required",
            message="runtime shadow only accepts QA/test/fixture student ids",
        )
    gate = resolve_runtime_artifact_gate(question_id, registry=registry)
    if gate.artifact_status == ARTIFACT_MISSING:
        return _fail_closed_result(
            engine=_engine_name(grading_engine_mode),
            question_id=question_id,
            student_id=student_id,
            gate=gate,
            error=ARTIFACT_MISSING,
            message="QuestionGradingArtifact missing; shadow grading did not run.",
        )

    artifact = _artifact_for_question(question_id, registry=registry)
    question = _question_from_submission(submission, artifact=artifact)
    try:
        if grading_engine_mode == LUBAN_BEST_QUALITY_SHADOW_MODE:
            builder = best_quality_builder or _build_best_quality_draft
            draft = builder(
                question=question,
                student_answer=student_answer,
                student_id=student_id,
                artifact_gate=gate,
                prediction_student_id=prediction_student_id,
            )
        else:
            builder = ai_draft_builder or _build_deepseek_fast_draft
            draft = builder(
                question=question,
                student_answer=student_answer,
                student_id=student_id,
                artifact_gate=gate,
            )
    except BestQualityUnavailable as exc:
        return _fail_closed_result(
            engine=_engine_name(grading_engine_mode),
            question_id=question_id,
            student_id=student_id,
            gate=gate,
            error="best_quality_unavailable",
            message=str(exc),
        )
    except RuntimeShadowUnavailable as exc:
        return _fail_closed_result(
            engine=_engine_name(grading_engine_mode),
            question_id=question_id,
            student_id=student_id,
            gate=gate,
            error="shadow_engine_unavailable",
            message=str(exc),
        )
    return _shadow_result_from_draft(
        draft,
        engine=_engine_name(grading_engine_mode),
        question_id=question_id,
        student_id=student_id,
        gate=gate,
    )


def _default_best_quality_builder(
    *,
    question: dict[str, Any],
    student_answer: str,
    student_id: str | None,
    artifact_gate: ArtifactRuntimeGate,
    prediction_student_id: str | None = None,
) -> dict[str, Any]:
    lookup_student_id = str(prediction_student_id or student_id or "").strip()
    if not lookup_student_id:
        raise BestQualityUnavailable("student_id required for cached 4-model lookup")
    case_id = str(question.get("case_id") or question.get("id") or "").strip()
    model_outputs = load_cached_4model_predictions(case_id, lookup_student_id)
    draft = best_quality_draft(
        question,
        student_answer,
        model_outputs,
        points=question.get("scoring_points") or [],
        student_id=student_id,
        artifact_gate=artifact_gate,
    )
    draft["prediction_source"] = "model_cache"
    draft["prediction_cache"] = {
        "cache_hit": True,
        "cache_student_id": lookup_student_id,
        "cache_case_id": case_id,
        "cache_file": str(CACHED_4MODEL),
        "cache_slice_id": "luban-full-485",
    }
    draft["provider"] = "cached_4model_jury"
    draft["model"] = "gpt55+opus48+deepseek_v4+qwen37"
    draft["fixture_used"] = False
    return draft


def _build_best_quality_draft(
    *,
    question: dict[str, Any],
    student_answer: str,
    student_id: str | None,
    artifact_gate: ArtifactRuntimeGate,
    prediction_student_id: str | None = None,
) -> dict[str, Any]:
    return _default_best_quality_builder(
        question=question,
        student_answer=student_answer,
        student_id=student_id,
        artifact_gate=artifact_gate,
        prediction_student_id=prediction_student_id,
    )


def _default_ai_draft_builder(
    *,
    question: dict[str, Any],
    student_answer: str,
    student_id: str | None,
    artifact_gate: ArtifactRuntimeGate,
) -> dict[str, Any]:
    predictions = question.get("ai_draft_predictions")
    if not isinstance(predictions, list) or not predictions:
        raise RuntimeShadowUnavailable("ai_draft_predictions missing; no provider call in runtime shadow adapter")
    from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft

    return build_ai_draft(
        question,
        student_answer,
        predictions,
        points=question.get("scoring_points") or [],
        student_id=student_id,
        artifact_gate=artifact_gate,
    )


def _build_deepseek_fast_draft(
    *,
    question: dict[str, Any],
    student_answer: str,
    student_id: str | None,
    artifact_gate: ArtifactRuntimeGate,
) -> dict[str, Any]:
    return _default_ai_draft_builder(
        question=question,
        student_answer=student_answer,
        student_id=student_id,
        artifact_gate=artifact_gate,
    )


def _shadow_result_from_draft(
    draft: dict[str, Any],
    *,
    engine: str,
    question_id: str,
    student_id: str | None,
    gate: ArtifactRuntimeGate,
) -> dict[str, Any]:
    point_results = list(draft.get("point_results") or [])
    return {
        "authority": "luban_grading_engine_shadow",
        "engine": engine,
        "question_id": question_id,
        "student_id": student_id,
        "artifact_gate": dict(draft.get("artifact_gate") or gate.to_dict()),
        "scores": {
            "model_draft_score": float(draft.get("model_draft_score") or 0),
            "auto_certified_score": float(draft.get("auto_certified_score") or 0),
            "pending_review_score": float(draft.get("pending_review_score") or 0),
        },
        "point_results": point_results,
        "teacher_review_required": True,
        "learning_evidence_payload_preview": draft.get("learning_evidence_payload_preview") or {},
        "writeback_performed": False,
        "not_production_grade": True,
        "source_authority": draft.get("authority"),
        "prediction_source": draft.get("prediction_source") or "",
        "provider": draft.get("provider") or "",
        "model": draft.get("model") or "",
        "cache_hit": bool((draft.get("prediction_cache") or {}).get("cache_hit")),
        "prediction_cache": draft.get("prediction_cache") or {},
        "fixture_used": bool(draft.get("fixture_used")),
        "shadow_status": "ok",
    }


def _fail_closed_result(
    *,
    engine: str,
    question_id: str,
    student_id: str | None,
    gate: ArtifactRuntimeGate | None,
    error: str,
    message: str = "",
) -> dict[str, Any]:
    return {
        "authority": "luban_grading_engine_shadow",
        "engine": engine,
        "question_id": question_id,
        "student_id": student_id,
        "artifact_gate": gate.to_dict()
        if gate is not None
        else {
            "artifact_found": False,
            "artifact_status": ARTIFACT_MISSING,
            "artifact_version_id": None,
            "auto_certification_allowed": False,
            "blocked_reason": ARTIFACT_MISSING,
            "point_auto_certification": {},
        },
        "scores": {
            "model_draft_score": 0.0,
            "auto_certified_score": 0.0,
            "pending_review_score": 0.0,
        },
        "point_results": [],
        "teacher_review_required": True,
        "learning_evidence_payload_preview": {},
        "writeback_performed": False,
        "not_production_grade": True,
        "error": error,
        "error_message": message[:300],
        "shadow_status": _shadow_status_for_error(error),
        "unavailable_reason": message[:300] if error in {"best_quality_unavailable", "shadow_engine_unavailable"} else "",
    }


def _question_from_submission(
    submission: dict[str, Any],
    *,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    context = _context_from_submission(submission)
    question_id = _question_id_from_submission(submission)
    question = dict(context)
    question["case_id"] = question_id
    question["id"] = question_id
    question.setdefault("question_id", question_id)
    question.setdefault("question_type", "case")
    question["scoring_points"] = _points_from_artifact(artifact)
    question["max_score"] = sum(float(point.get("max_score") or 0) for point in question["scoring_points"])
    answer = _student_answer_from_submission(submission)
    question["user_answer"] = answer
    if isinstance(submission.get("ai_draft_predictions"), list):
        question["ai_draft_predictions"] = list(submission["ai_draft_predictions"])
    return question


def _points_from_artifact(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for sp in artifact.get("scoring_points") or []:
        points.append(
            {
                "point_id": sp.get("point_id"),
                "label": sp.get("label"),
                "max_score": sp.get("max_score"),
                "typed_policy": {
                    "policy_type": sp.get("policy_type"),
                    "required_terms": list(sp.get("required_terms") or []),
                    "list_spec": {"rule_text": sp.get("list_rule")}
                    if sp.get("list_rule")
                    else None,
                    "numeric_spec": sp.get("calculation_spec"),
                    "penalty_spec": {"rule_text": sp.get("penalty_rule")}
                    if sp.get("penalty_rule")
                    else None,
                },
            }
        )
    return points


def _artifact_for_question(
    question_id: str,
    *,
    registry: QuestionGradingRegistry | None = None,
) -> dict[str, Any]:
    if registry is not None:
        art = registry.get_artifact(question_id)
        if art is not None:
            return art
        return {"artifact_missing": True, "question_id": question_id, "scoring_points": []}
    return get_question_grading_artifact(question_id)


def _context_from_submission(submission: dict[str, Any]) -> dict[str, Any]:
    for key in ("question_followup_context", "question_context", "context"):
        value = submission.get(key)
        if isinstance(value, dict):
            return value
    return submission


def _question_id_from_submission(submission: dict[str, Any]) -> str:
    context = _context_from_submission(submission)
    return str(
        submission.get("case_id")
        or submission.get("question_id")
        or context.get("case_id")
        or context.get("question_id")
        or context.get("id")
        or ""
    ).strip()


def _student_id_from_submission(submission: dict[str, Any]) -> str | None:
    value = submission.get("student_id") or submission.get("user_id")
    return str(value).strip() if value not in (None, "") else None


def _student_answer_from_submission(submission: dict[str, Any]) -> str:
    context = _context_from_submission(submission)
    return str(
        submission.get("student_answer")
        or submission.get("answer")
        or context.get("student_answer")
        or context.get("user_answer")
        or context.get("answer")
        or ""
    ).strip()


def _engine_name(mode: str) -> str:
    if mode == LUBAN_BEST_QUALITY_SHADOW_MODE:
        return "best_quality_4model"
    if mode == LUBAN_AI_DRAFT_SHADOW_MODE:
        return "deepseek_fast"
    return mode or "unknown"


def _mode_from_engine(engine: str | None) -> str:
    raw = str(engine or "").strip()
    if raw == "best_quality_4model":
        return LUBAN_BEST_QUALITY_SHADOW_MODE
    if raw in {"deepseek_fast", "ai_draft", "deepseek"}:
        return LUBAN_AI_DRAFT_SHADOW_MODE
    return raw or LEGACY_MODE


def _is_safe_shadow_student_id(student_id: str | None) -> bool:
    raw = str(student_id or "").strip()
    if not raw:
        return False
    return raw.startswith(("qa_", "test_"))


def _shadow_status_for_error(error: str) -> str:
    if error == ARTIFACT_MISSING:
        return ARTIFACT_MISSING
    if error == "qa_student_required":
        return "qa_student_required"
    if error in {"best_quality_unavailable", "shadow_engine_unavailable"}:
        return "engine_unavailable"
    return "fail_closed"


LUBAN_RUBRIC_V1_SHADOW_MODE = "luban_rubric_v1_shadow"


def build_rubric_v1_shadow_result(
    *,
    question_id: str,
    student_answer: str,
    student_id: str,
    node_code: str = "",
    rubric_points: list[dict[str, Any]] | None = None,
    judge_fn: Callable[..., dict[str, Any]] | None = None,
    qa_shadow: bool = True,
) -> dict[str, Any]:
    """Non-authoritative v1 rubric grading shadow: load the compiled scored rubric (or use the passed
    open-world rubric), LLM-adjudicate each scoring point, deterministically sum, and emit a
    GradingEvent + learning_evidence projection. QA/test student ids only when qa_shadow. Never writes
    DB / Learning Brain / official score (candidate evidence; teacher/governed gate promotes)."""
    from deeptutor.services.construction_grading import rubric_grader_v1 as _G

    if qa_shadow and not _is_safe_shadow_student_id(student_id):
        return {"engine": "rubric_v1", "status": "fail_closed", "error": "qa_student_required",
                "question_id": question_id, "shadow_result": None}
    points = rubric_points if rubric_points is not None else _G.load_rubric(question_id)
    if not points:
        # open-world: no in-bank rubric and none supplied -> signal caller to extract on the fly
        return {"engine": "rubric_v1", "status": "no_rubric_open_world", "question_id": question_id,
                "shadow_result": None}
    if judge_fn is None:
        return {"engine": "rubric_v1", "status": "fail_closed", "error": "judge_unavailable",
                "question_id": question_id, "shadow_result": None}
    event = _G.grade_with_rubric(qid=question_id, student_answer=student_answer,
                                 rubric_points=points, judge_fn=judge_fn, student_id=student_id)
    evidence = _G.to_learning_evidence(event, node_code=node_code)
    return {"engine": "rubric_v1", "status": "ok", "question_id": question_id,
            "grading_event": event, "learning_evidence": evidence,
            "official_score_allowed": False}


__all__ = [
    "LEGACY_MODE",
    "LUBAN_AI_DRAFT_SHADOW_MODE",
    "LUBAN_BEST_QUALITY_SHADOW_MODE",
    "LUBAN_RUBRIC_V1_SHADOW_MODE",
    "RuntimeShadowUnavailable",
    "attach_runtime_shadow_result",
    "build_runtime_shadow_result",
    "build_rubric_v1_shadow_result",
]
