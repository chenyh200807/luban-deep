from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.api.dependencies import AuthContext, require_admin, require_self_or_admin
from deeptutor.services.learner_state import get_bot_learner_overlay_service, get_learner_state_service
from deeptutor.services.tutor_state import get_user_tutor_state_service

router = APIRouter()


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    return {
        "user_id": snapshot.user_id,
        "profile": snapshot.profile,
        "persona": snapshot.persona,
        "memory": snapshot.memory,
        "profile_updated_at": snapshot.profile_updated_at,
        "persona_updated_at": snapshot.persona_updated_at,
        "memory_updated_at": snapshot.memory_updated_at,
    }


class OverlayPatchRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


class OverlayPromotionApplyRequest(BaseModel):
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    max_candidates: int = Field(default=10, ge=1, le=100)


class OverlayPromotionDecisionRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    reason: str = ""


@router.get("/{user_id}")
async def get_tutor_state(
    user_id: str,
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    snapshot = get_user_tutor_state_service().read_snapshot(user_id)
    return _snapshot_dict(snapshot)


@router.get("/{user_id}/context")
async def get_tutor_state_context(
    user_id: str,
    language: str = Query(default="zh"),
    max_chars: int = Query(default=5000, ge=500, le=20000),
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    service = get_user_tutor_state_service()
    return {
        "user_id": user_id,
        "language": language,
        "max_chars": max_chars,
        "context": service.build_context(user_id, language=language, max_chars=max_chars),
    }


@router.get("/{user_id}/heartbeat-history")
async def get_tutor_state_heartbeat_history(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    include_arbitration: bool = Query(default=True),
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    service = get_learner_state_service()
    return {
        "user_id": user_id,
        "limit": limit,
        "include_arbitration": include_arbitration,
        "items": service.list_heartbeat_history(
            user_id,
            limit=limit,
            include_arbitration=include_arbitration,
        ),
    }


@router.get("/{user_id}/heartbeat-arbitration")
async def get_tutor_state_heartbeat_arbitration_history(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    service = get_learner_state_service()
    return {
        "user_id": user_id,
        "limit": limit,
        "items": service.list_heartbeat_arbitration_history(user_id, limit=limit),
    }


@router.get("/{user_id}/overlays")
async def get_tutor_state_overlays(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    overlay_service = get_bot_learner_overlay_service()
    items = overlay_service.list_user_overlays(user_id, limit=limit)
    return {
        "user_id": user_id,
        "limit": limit,
        "total": len(items),
        "items": items,
    }


@router.get("/{user_id}/overlay/{bot_id}")
async def get_tutor_state_overlay(
    user_id: str,
    bot_id: str,
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    return get_bot_learner_overlay_service().read_overlay(bot_id, user_id)


@router.get("/{user_id}/overlay/{bot_id}/events")
async def get_tutor_state_overlay_events(
    user_id: str,
    bot_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    event_type: str | None = Query(default=None),
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    overlay_service = get_bot_learner_overlay_service()
    items = overlay_service.list_overlay_events(
        bot_id,
        user_id,
        limit=limit,
        event_type=event_type,
    )
    return {
        "user_id": user_id,
        "bot_id": bot_id,
        "limit": limit,
        "event_type": event_type,
        "items": items,
    }


@router.get("/{user_id}/overlay/{bot_id}/audit")
async def get_tutor_state_overlay_audit(
    user_id: str,
    bot_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    current_user: AuthContext = Depends(require_self_or_admin),
) -> dict[str, Any]:
    overlay_service = get_bot_learner_overlay_service()
    items = overlay_service.list_overlay_audit(bot_id, user_id, limit=limit)
    return {
        "user_id": user_id,
        "bot_id": bot_id,
        "limit": limit,
        "items": items,
    }


@router.patch("/{user_id}/overlay/{bot_id}")
async def patch_tutor_state_overlay(
    user_id: str,
    bot_id: str,
    body: OverlayPatchRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    operations = list(body.operations or [])
    if not operations:
        raise HTTPException(status_code=400, detail="Overlay patch operations are required")
    try:
        return get_bot_learner_overlay_service().patch_overlay(
            bot_id,
            user_id,
            {"operations": operations},
            source_feature="admin_overlay",
            source_id=current_user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{user_id}/overlay/{bot_id}/promotions/apply")
async def apply_tutor_state_overlay_promotions(
    user_id: str,
    bot_id: str,
    body: OverlayPromotionApplyRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    overlay_service = get_bot_learner_overlay_service()
    return overlay_service.apply_promotions(
        bot_id,
        user_id,
        learner_state_service=get_learner_state_service(),
        min_confidence=body.min_confidence,
        max_candidates=body.max_candidates,
    )


@router.post("/{user_id}/overlay/{bot_id}/promotions/ack")
async def ack_tutor_state_overlay_promotions(
    user_id: str,
    bot_id: str,
    body: OverlayPromotionDecisionRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    candidate_ids = [str(item or "").strip() for item in body.candidate_ids if str(item or "").strip()]
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids are required")
    return get_bot_learner_overlay_service().ack_promotions(
        bot_id,
        user_id,
        candidate_ids,
        reason=body.reason or f"acked_by:{current_user.user_id}",
    )


@router.post("/{user_id}/overlay/{bot_id}/promotions/drop")
async def drop_tutor_state_overlay_promotions(
    user_id: str,
    bot_id: str,
    body: OverlayPromotionDecisionRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    candidate_ids = [str(item or "").strip() for item in body.candidate_ids if str(item or "").strip()]
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids are required")
    return get_bot_learner_overlay_service().drop_promotions(
        bot_id,
        user_id,
        candidate_ids,
        reason=body.reason or f"dropped_by:{current_user.user_id}",
    )
