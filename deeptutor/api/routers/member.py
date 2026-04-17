from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.api.dependencies import AuthContext, require_admin
from deeptutor.services.member_console import get_member_console_service

router = APIRouter(dependencies=[Depends(require_admin)])
service = get_member_console_service()


class NoteCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    channel: str = Field(default="manual")
    pinned: bool = False


class NoteUpdateRequest(BaseModel):
    content: str | None = Field(default=None, max_length=2000)
    pinned: bool | None = None


class GrantRequest(BaseModel):
    user_id: str
    days: int = Field(..., gt=0, le=3650)
    tier: str = "vip"
    reason: str = ""


class UpdateRequest(BaseModel):
    user_id: str
    tier: str | None = None
    days: int | None = Field(default=None, ge=-3650, le=3650)
    expire_at: str | None = None
    auto_renew: bool | None = None
    reason: str = ""


class RevokeRequest(BaseModel):
    user_id: str
    reason: str = ""


class OverlayPatchRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)


class OverlayPromotionApplyRequest(BaseModel):
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    max_candidates: int = Field(default=10, ge=1, le=100)


class OverlayPromotionDecisionRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    reason: str = ""


@router.get("/health")
async def member_health() -> dict[str, Any]:
    return {"status": "ok", "module": "member"}


@router.get("/dashboard")
async def member_dashboard(days: int = 30) -> dict[str, Any]:
    return service.get_dashboard(days=days)


@router.get("/list")
async def member_list(
    page: int = 1,
    page_size: int = 20,
    sort: str = "expire_at",
    order: str = "asc",
    status: str | None = None,
    tier: str | None = None,
    search: str | None = None,
    segment: str | None = None,
    risk_level: str | None = None,
    auto_renew: bool | None = None,
) -> dict[str, Any]:
    return service.list_members(
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        status=status,
        tier=tier,
        search=search,
        segment=segment,
        risk_level=risk_level,
        auto_renew=auto_renew,
    )


@router.get("/{user_id}/360")
async def member_360(user_id: str) -> dict[str, Any]:
    try:
        return service.get_member_360(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/learner-state")
async def member_learner_state(user_id: str, limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    try:
        return service.get_member_learner_state_panel(user_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/heartbeat-jobs")
async def member_heartbeat_jobs(user_id: str) -> dict[str, Any]:
    try:
        return service.list_member_heartbeat_jobs(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/heartbeat-jobs/{job_id}/pause")
async def pause_member_heartbeat_job(
    user_id: str,
    job_id: str,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return service.pause_member_heartbeat_job(user_id, job_id, operator=current_user.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/heartbeat-jobs/{job_id}/resume")
async def resume_member_heartbeat_job(
    user_id: str,
    job_id: str,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return service.resume_member_heartbeat_job(user_id, job_id, operator=current_user.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/overlays/{bot_id}")
async def member_overlay(user_id: str, bot_id: str) -> dict[str, Any]:
    try:
        return service.get_member_overlay(user_id, bot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/overlays/{bot_id}/events")
async def member_overlay_events(
    user_id: str,
    bot_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    event_type: str | None = None,
) -> dict[str, Any]:
    try:
        return service.get_member_overlay_events(user_id, bot_id, limit=limit, event_type=event_type)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/overlays/{bot_id}/audit")
async def member_overlay_audit(
    user_id: str,
    bot_id: str,
    limit: int = Query(default=20, ge=1, le=200),
) -> dict[str, Any]:
    try:
        return service.get_member_overlay_audit(user_id, bot_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{user_id}/overlays/{bot_id}")
async def patch_member_overlay(
    user_id: str,
    bot_id: str,
    body: OverlayPatchRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    operations = list(body.operations or [])
    if not operations:
        raise HTTPException(status_code=400, detail="Overlay patch operations are required")
    try:
        return service.patch_member_overlay(
            user_id,
            bot_id,
            operations,
            operator=current_user.user_id,
        )
    except (KeyError, ValueError) as exc:
        status_code = 404 if isinstance(exc, KeyError) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/{user_id}/overlays/{bot_id}/promotions/apply")
async def apply_member_overlay_promotions(
    user_id: str,
    bot_id: str,
    body: OverlayPromotionApplyRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return service.apply_member_overlay_promotions(
            user_id,
            bot_id,
            operator=current_user.user_id,
            min_confidence=body.min_confidence,
            max_candidates=body.max_candidates,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/overlays/{bot_id}/promotions/ack")
async def ack_member_overlay_promotions(
    user_id: str,
    bot_id: str,
    body: OverlayPromotionDecisionRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    candidate_ids = [str(item or "").strip() for item in body.candidate_ids if str(item or "").strip()]
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids are required")
    try:
        return service.ack_member_overlay_promotions(
            user_id,
            bot_id,
            candidate_ids,
            operator=current_user.user_id,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/overlays/{bot_id}/promotions/drop")
async def drop_member_overlay_promotions(
    user_id: str,
    bot_id: str,
    body: OverlayPromotionDecisionRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    candidate_ids = [str(item or "").strip() for item in body.candidate_ids if str(item or "").strip()]
    if not candidate_ids:
        raise HTTPException(status_code=400, detail="candidate_ids are required")
    try:
        return service.drop_member_overlay_promotions(
            user_id,
            bot_id,
            candidate_ids,
            operator=current_user.user_id,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/notes")
async def member_notes(user_id: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    try:
        return service.get_notes(user_id, page=page, page_size=page_size)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/notes")
async def create_member_note(
    user_id: str,
    body: NoteCreateRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return service.add_note(
            user_id,
            body.content,
            channel=body.channel,
            pinned=body.pinned,
            operator=current_user.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/notes/{note_id}")
async def update_member_note(
    note_id: str,
    body: NoteUpdateRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return service.update_note(
            note_id,
            content=body.content,
            pinned=body.pinned,
            operator=current_user.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/notes/{note_id}")
async def delete_member_note(
    note_id: str,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    deleted = service.delete_note(note_id, operator=current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Unknown note")
    return {"deleted": True}


@router.get("/audit-log")
async def member_audit_log(
    page: int = 1,
    page_size: int = 50,
    target_user: str | None = None,
    operator: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    return service.get_audit_log(
        page=page,
        page_size=page_size,
        target_user=target_user,
        operator=operator,
        action=action,
    )


@router.post("/grant")
async def grant_membership(
    body: GrantRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    return service.grant_subscription(
        body.user_id,
        body.days,
        tier=body.tier,
        reason=body.reason,
        operator=current_user.user_id,
    )


@router.post("/update")
async def update_membership(
    body: UpdateRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    return service.update_subscription(
        body.user_id,
        tier=body.tier,
        days=body.days,
        expire_at=body.expire_at,
        auto_renew=body.auto_renew,
        reason=body.reason,
        operator=current_user.user_id,
    )


@router.post("/revoke")
async def revoke_membership(
    body: RevokeRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    return service.revoke_subscription(
        body.user_id,
        reason=body.reason,
        operator=current_user.user_id,
    )
