from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.schema import CaseGradingResult
from deeptutor.services.construction_grading.writeback import write_grading_error_events
from deeptutor.services.learner_state import get_learner_state_service
from deeptutor.services.learner_state.learning_brain_read_model import build_learning_brain_read_model
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
    return build_learning_brain_read_model(user_id=normalized_user_id, projection=projection, surface="qa")


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
    read_model = build_learning_brain_read_model(user_id=user_id, projection=projection, surface="qa")
    graph_chain = dict(read_model.get("graph_chain") or {})
    return {
        **read_model,
        "grading_results": visible_results,
        "manual_confirmation": manual_confirmation,
        "training_uses_question": graph_chain["has_training_uses_question"],
        "training_improved_error": graph_chain["has_training_improved_error"],
        "training_not_improved_error": graph_chain["has_training_not_improved_error"],
    }
