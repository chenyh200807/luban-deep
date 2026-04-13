from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from deeptutor.services.member_console import get_member_console_service

router = APIRouter()
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


@router.get("/{user_id}/notes")
async def member_notes(user_id: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    try:
        return service.get_notes(user_id, page=page, page_size=page_size)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{user_id}/notes")
async def create_member_note(user_id: str, body: NoteCreateRequest) -> dict[str, Any]:
    try:
        return service.add_note(user_id, body.content, channel=body.channel, pinned=body.pinned)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/notes/{note_id}")
async def update_member_note(note_id: str, body: NoteUpdateRequest) -> dict[str, Any]:
    try:
        return service.update_note(note_id, content=body.content, pinned=body.pinned)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/notes/{note_id}")
async def delete_member_note(note_id: str) -> dict[str, Any]:
    deleted = service.delete_note(note_id)
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
async def grant_membership(body: GrantRequest) -> dict[str, Any]:
    return service.grant_subscription(body.user_id, body.days, tier=body.tier, reason=body.reason)


@router.post("/update")
async def update_membership(body: UpdateRequest) -> dict[str, Any]:
    return service.update_subscription(
        body.user_id,
        tier=body.tier,
        days=body.days,
        expire_at=body.expire_at,
        auto_renew=body.auto_renew,
        reason=body.reason,
    )


@router.post("/revoke")
async def revoke_membership(body: RevokeRequest) -> dict[str, Any]:
    return service.revoke_subscription(body.user_id, reason=body.reason)

