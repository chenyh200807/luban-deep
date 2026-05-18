from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.schema import CaseGradingResult
from deeptutor.services.construction_grading.writeback import write_grading_error_events
from deeptutor.services.learner_state import get_learner_state_service
from deeptutor.services.runtime_env import env_flag, runtime_environment

router = APIRouter()


class LearningBrainHarnessRequest(BaseModel):
    user_id: str = Field(default="wechat_harness_learning_brain", min_length=1, max_length=120)
    user_answer: str = Field(
        default="应加强现场管理，落实责任，严格检查。",
        min_length=1,
        max_length=1000,
    )
    manual_confirm: bool = False


def _qa_enabled() -> bool:
    return runtime_environment() == "local" and env_flag("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", default=False)


def _demo_case_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "wechat-harness-case-001",
            "question_type": "case_study",
            "correct_answer": "应组织专家论证，并编制专项施工方案后按规定审批。",
            "grading_keywords": ["专家论证", "专项施工方案", "审批"],
            "node_code": "1A432000",
            "testing_focus": "危险性较大工程专项方案程序",
        },
        {
            "id": "wechat-harness-case-002",
            "question_type": "case_study",
            "correct_answer": "应组织专家论证，并按专项施工方案实施，验收合格后方可进入下道工序。",
            "grading_keywords": ["专家论证", "专项施工方案", "验收合格"],
            "node_code": "1A432000",
            "testing_focus": "专项方案与验收程序",
        },
    ]


def _visible_grading_result(result: CaseGradingResult, *, write_count: int) -> dict[str, Any]:
    missed_points = [item.criterion for item in result.rubric_items if item.status == "miss"]
    return {
        "question_id": result.question_id,
        "score_awarded": result.score_awarded,
        "max_score": result.max_score,
        "score_label": f"{result.score_awarded:g}/{result.max_score:g}",
        "missed_points": missed_points,
        "rewrite": result.rewrite_answer,
        "next_training_signal": dict(result.next_training_signal or {}),
        "write_count": write_count,
    }


def _projection_read_model(*, user_id: str, projection: dict[str, Any]) -> dict[str, Any]:
    run = dict(projection.get("synthesis_run") or {})
    typed_graph = dict(projection.get("typed_graph") or {})
    typed_graph_edges = list(typed_graph.get("edges") or [])
    weak_points = list(projection.get("weak_points") or [])
    improvement_signals = list(projection.get("improvement_signals") or [])
    stale_claims = list(projection.get("stale_claims") or [])
    compiled_objects = dict(projection.get("compiled_objects") or {})
    visible_sections = [
        {
            "id": "weak_points",
            "visible": bool(weak_points),
            "item_count": len(weak_points),
            "items": weak_points[:8],
        },
        {
            "id": "compiled_objects",
            "visible": bool(compiled_objects),
            "item_count": len(compiled_objects),
            "object_keys": sorted(compiled_objects)[:24],
        },
        {
            "id": "typed_graph",
            "visible": bool(typed_graph_edges),
            "item_count": len(typed_graph_edges),
            "readiness_gaps": list(typed_graph.get("readiness_gaps") or []),
        },
    ]
    return {
        "ok": True,
        "user_id": user_id,
        "projection_subject": str(projection.get("subject") or ""),
        "compiled_objects": compiled_objects,
        "weak_points": weak_points,
        "improvement_signals": improvement_signals,
        "stale_claims": stale_claims,
        "visible_sections": visible_sections,
        "typed_graph_edges": typed_graph_edges,
        "typed_graph_readiness_gaps": list(typed_graph.get("readiness_gaps") or []),
        "typed_graph_edge_count": len(typed_graph_edges),
        "event_count": int(run.get("input_event_count") or 0),
        "created_claim_count": int(run.get("created_claim_count") or 0),
        "output_projection_hash": str(run.get("output_projection_hash") or ""),
        "synthesis_run": run,
    }


def _node_id(edge: dict[str, Any], side: str) -> str:
    node = edge.get(side) if isinstance(edge.get(side), dict) else {}
    return str(node.get("id") or "").strip()


def _concept_from_error_id(error_id: str) -> str:
    return error_id.split(":", 1)[0].strip() if ":" in error_id else ""


def _question_edges_by_concept(edges: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_concept: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        if edge.get("edge_type") != "question_tests_concept":
            continue
        concept_id = _node_id(edge, "to")
        if not concept_id:
            continue
        by_concept.setdefault(concept_id, []).append(edge)
    return by_concept


def _visible_training_graph_chain(
    *,
    projection: dict[str, Any],
    grading_results: list[dict[str, Any]],
) -> dict[str, Any]:
    edges = list((dict(projection.get("typed_graph") or {})).get("edges") or [])
    question_edges_by_concept = _question_edges_by_concept(edges)
    grading_by_question = {str(item.get("question_id") or ""): item for item in grading_results}
    error_to_training = [edge for edge in edges if edge.get("edge_type") == "error_points_to_training"]
    training_uses_question_edges: list[dict[str, Any]] = []
    training_improved_error_edges: list[dict[str, Any]] = []
    training_not_improved_error_edges: list[dict[str, Any]] = []

    for edge in error_to_training:
        error_id = _node_id(edge, "from")
        training_id = _node_id(edge, "to")
        concept_id = _concept_from_error_id(error_id)
        candidate_questions = question_edges_by_concept.get(concept_id, [])
        selected_question = next(
            (candidate for candidate in candidate_questions if candidate.get("evidence_event_id") != edge.get("evidence_event_id")),
            candidate_questions[0] if candidate_questions else None,
        )
        if not selected_question or not training_id:
            continue
        question_id = _node_id(selected_question, "from")
        training_uses_question_edges.append({
            "edge_type": "training_uses_question",
            "from": {"type": "next_training", "id": training_id},
            "to": {"type": "question", "id": question_id},
            "source_feature": "learning_brain_harness_read_model",
            "reason_edge_event_id": edge.get("evidence_event_id"),
            "selected_question_event_id": selected_question.get("evidence_event_id"),
            "confidence": edge.get("confidence", 0.8),
        })
        grading = grading_by_question.get(question_id, {})
        try:
            score_awarded = float(grading.get("score_awarded") or 0)
            max_score = float(grading.get("max_score") or 0)
        except (TypeError, ValueError):
            score_awarded = 0
            max_score = 0
        outcome_edge = {
            "from": {"type": "next_training", "id": training_id},
            "to": {"type": "error", "id": error_id},
            "source_feature": "learning_brain_harness_read_model",
            "question_id": question_id,
            "score_label": grading.get("score_label", ""),
            "confidence": edge.get("confidence", 0.8),
        }
        if max_score > 0 and score_awarded >= max_score and not grading.get("missed_points"):
            training_improved_error_edges.append({"edge_type": "training_improved_error", **outcome_edge})
        else:
            training_not_improved_error_edges.append({
                "edge_type": "training_not_improved_error",
                "reason": "selected_question_still_has_missed_points",
                **outcome_edge,
            })

    return {
        "error_points_to_training": error_to_training,
        "training_uses_question": training_uses_question_edges,
        "training_improved_error": training_improved_error_edges,
        "training_not_improved_error": training_not_improved_error_edges,
        "has_training_uses_question": bool(training_uses_question_edges),
        "has_training_improved_error": bool(training_improved_error_edges),
        "has_training_not_improved_error": bool(training_not_improved_error_edges),
    }


@router.get("/harness-projection")
async def get_learning_brain_projection(
    user_id: str = Query(..., min_length=1, max_length=120),
) -> dict[str, Any]:
    if not _qa_enabled():
        raise HTTPException(status_code=404, detail="Learning Brain QA projection is disabled")

    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    synthesis = get_learner_state_service().synthesize_learning_truth(
        normalized_user_id,
        dry_run=True,
        event_limit=50,
    )
    projection = dict(synthesis.get("projection") or {})
    return _projection_read_model(user_id=normalized_user_id, projection=projection)


@router.post("/harness-case-grading")
async def run_learning_brain_harness_case_grading(
    payload: LearningBrainHarnessRequest,
) -> dict[str, Any]:
    """Dev harness for the visible Learning Brain chain.

    This wrapper owns no grading or memory truth. It only connects the Web QA
    surface to the existing grading, learner-state writeback, and synthesis
    authorities.
    """

    if not _qa_enabled():
        raise HTTPException(status_code=404, detail="Learning Brain QA harness is disabled")

    user_id = payload.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    kernel = CaseGradingSkillKernel()
    learner_state_service = get_learner_state_service()
    run_id = uuid4().hex[:10]
    visible_results: list[dict[str, Any]] = []
    for index, row in enumerate(_demo_case_rows(), 1):
        result = kernel.grade(question_row=row, user_answer=payload.user_answer)
        source_id = f"wechat-harness-learning-brain-{run_id}-{index}"
        write_count = write_grading_error_events(
            learner_state_service=learner_state_service,
            user_id=user_id,
            grading_result=result,
            source_id=source_id,
            source_bot_id="construction-exam",
            include_success_events=True,
        )
        visible_results.append(_visible_grading_result(result, write_count=write_count))

    manual_confirmation: dict[str, Any] | None = None
    if payload.manual_confirm:
        event = learner_state_service.append_memory_event(
            user_id,
            source_feature="manual_correction",
            source_id=f"wechat-harness-learning-brain-confirm-{run_id}",
            memory_kind="learning_correction",
            payload_json={
                "event_type": "manual_correction",
                "action": "confirm",
                "concept_id": "1A432000",
                "error_code": "E02",
                "correction": "老师确认该学生反复漏写危险性较大工程专项方案程序。",
            },
            dedupe_key=f"{user_id}:wechat-harness-learning-brain-confirm:{run_id}",
        )
        manual_confirmation = {
            "event_id": event.event_id,
            "source_feature": event.source_feature,
            "memory_kind": event.memory_kind,
        }

    synthesis = learner_state_service.synthesize_learning_truth(
        user_id,
        dry_run=True,
        event_limit=50,
    )
    projection = dict(synthesis.get("projection") or {})
    read_model = _projection_read_model(user_id=user_id, projection=projection)
    graph_chain = _visible_training_graph_chain(
        projection=projection,
        grading_results=visible_results,
    )
    return {
        **read_model,
        "grading_results": visible_results,
        "manual_confirmation": manual_confirmation,
        "graph_chain": graph_chain,
        "training_uses_question": graph_chain["has_training_uses_question"],
        "training_improved_error": graph_chain["has_training_improved_error"],
        "training_not_improved_error": graph_chain["has_training_not_improved_error"],
    }
