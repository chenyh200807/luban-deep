"""学员主动信号写入端点：subjective_focus / user_dispute。

走 ``secure_router``（默认 ``Depends(get_current_user)`` 鉴权，过 CI route inventory
gate，非裸 APIRouter）。事件经 ``record_learner_signal`` 写
``learner_memory_events``（``memory_kind="learning_evidence"`` 白名单已含 +
``source_feature="learner_signal"`` → 被 ``_is_learning_evidence`` 排除，不进证据
编译器），点亮关注线/订正读侧。

owner-scope：``user_id`` 取自鉴权上下文 ``current_user.user_id``，**不接受**客户端
传 ``user_id``。
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from deeptutor.api._secure_router import secure_router
from deeptutor.api.dependencies import AuthContext, get_current_user
from deeptutor.services.learner_state.learner_signal import record_learner_signal
from deeptutor.services.learner_state.service import get_learner_state_service

router = secure_router(tags=["learner_signal"])


class LearnerSignalRequest(BaseModel):
    signal_type: str            # "subjective_focus" | "user_dispute" | "station_completed"(复习模块旗标后)
    concept_id: str
    concept_label: str = ""
    error_code: str = ""
    ability_dimension: str = ""
    user_says: str = ""         # user_dispute: "mastered" | "not_mastered"
    completion_id: str = ""
    practice_mode: str = ""
    training_intent_id: str = ""
    probe_id: str = ""


@router.post("/signal")
async def post_learner_signal(
    body: LearnerSignalRequest,
    current_user: AuthContext = Depends(get_current_user),
) -> dict:
    try:
        event = record_learner_signal(
            get_learner_state_service(),
            user_id=current_user.user_id,
            signal_type=body.signal_type,
            concept_id=body.concept_id,
            concept_label=body.concept_label,
            error_code=body.error_code,
            ability_dimension=body.ability_dimension,
            user_says=body.user_says,
            completion_id=body.completion_id,
            practice_mode=body.practice_mode,
            training_intent_id=body.training_intent_id,
            probe_id=body.probe_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "event_id": str(getattr(event, "event_id", "") or "")}
