from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
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
        )
        visible_results.append(_visible_grading_result(result, write_count=write_count))

    synthesis = learner_state_service.synthesize_learning_truth(
        user_id,
        dry_run=True,
        event_limit=50,
    )
    projection = dict(synthesis.get("projection") or {})
    run = dict(projection.get("synthesis_run") or {})
    return {
        "ok": True,
        "user_id": user_id,
        "grading_results": visible_results,
        "event_count": int(run.get("input_event_count") or 0),
        "created_claim_count": int(run.get("created_claim_count") or 0),
        "output_projection_hash": str(run.get("output_projection_hash") or ""),
        "projection_subject": str(projection.get("subject") or ""),
        "weak_points": list(projection.get("weak_points") or []),
        "compiled_objects": dict(projection.get("compiled_objects") or {}),
        "typed_graph_edge_count": len(dict(projection.get("typed_graph") or {}).get("edges") or []),
    }
