from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response

# Round 5 M1: tight format gate for X-Idempotency-Key. UUID hyphens + URL-safe
# base64 alphabet covers all reasonable client-generated keys; anything else
# (e.g. separator injection ':', whitespace, multi-MB JSON) is rejected.
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
from pydantic import BaseModel, Field

from deeptutor.api.dependencies import AuthContext, require_admin
from deeptutor.api.routers.tutor_state import (
    OverlayPatchRequest,
    OverlayPromotionApplyRequest,
    OverlayPromotionDecisionRequest,
)
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


class OpsActionResultRequest(BaseModel):
    status: str = Field(..., pattern=r"^(open|in_progress|done|follow_up)$")
    result: str = Field(..., min_length=1, max_length=2000)
    action_title: str = Field(default="", max_length=200)
    next_follow_up_at: str = Field(default="", max_length=80)


class GrantRequest(BaseModel):
    user_id: str
    days: int = Field(..., gt=0, le=3650)
    tier: str = "vip"
    reason: str = ""


class ManualPurchaseRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=200)
    package_id: str = Field(..., min_length=1, max_length=80)
    days: int = Field(..., gt=0, le=3650)
    reason: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    display_name: str = Field(default="", max_length=100)
    amount_cny: float | None = Field(default=None, ge=0)


class ManualPurchaseReversalRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=200)
    purchase_id: str = Field(default="", max_length=120)
    amount_cny: float | None = Field(default=None, ge=0)
    reason: str = Field(default="", max_length=200)


class AccountMergeRequest(BaseModel):
    target_user_id: str = Field(..., min_length=1, max_length=200)
    source_user_ids: list[str] = Field(..., min_length=1, max_length=10)
    reason: str = Field(default="", max_length=200)


class MembershipPackageRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    tier: str = Field(..., min_length=1, max_length=40)
    points: int = Field(..., gt=0, le=10_000_000)
    turns: int = Field(..., gt=0, le=1_000_000)
    price: str = Field(..., min_length=1, max_length=40)
    original_price: str = Field(default="", max_length=40)
    badge: str = Field(default="", max_length=40)
    per: str = Field(default="", max_length=80)
    desc: str = Field(default="", max_length=400)
    status: str = Field(default="active", pattern=r"^(active|draft|archived)$")
    reason: str = Field(default="", max_length=200)


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


class BatchActionRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list, min_length=1, max_length=100)
    action: str = Field(..., pattern=r"^(grant|update|revoke)$")
    days: int | None = Field(default=None, ge=-3650, le=3650)
    tier: str | None = None
    expire_at: str | None = None
    auto_renew: bool | None = None
    reason: str = ""


# Overlay request models are owned by the tutor_state router (single authority); imported
# above so member-console overlay endpoints share one definition instead of a copy-paste
# duplicate (schema-governance P3#10: no same-name route model defined in two routers).


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
    expire_within_days: int | None = Query(default=None, ge=0, le=3650),
    active_within_days: int | None = Query(default=None, ge=0, le=3650),
    has_heartbeat_job: bool | None = None,
    has_overlay_candidates: bool | None = None,
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
        expire_within_days=expire_within_days,
        active_within_days=active_within_days,
        has_heartbeat_job=has_heartbeat_job,
        has_overlay_candidates=has_overlay_candidates,
    )


def _require_idempotency_key(value: str | None) -> str:
    normalized_key = str(value or "").strip()
    if not normalized_key:
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key header is required for audited writes",
        )
    if len(normalized_key) > 128 or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized_key):
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key must be ≤ 128 chars of [a-zA-Z0-9_-]",
        )
    return normalized_key


@router.get("/packages")
async def list_membership_packages(
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    return {"items": service.list_membership_packages(), "operator": current_user.user_id}


@router.put("/packages/{package_id}")
async def upsert_membership_package(
    package_id: str,
    body: MembershipPackageRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return service.upsert_membership_package(
            package_id=package_id,
            label=body.label,
            tier=body.tier,
            points=body.points,
            turns=body.turns,
            price=body.price,
            original_price=body.original_price,
            badge=body.badge,
            per=body.per,
            desc=body.desc,
            status=body.status,
            operator=current_user.user_id,
            reason=body.reason,
            idempotency_key=_require_idempotency_key(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/packages/{package_id}")
async def delete_membership_package(
    package_id: str,
    reason: str = Query(default="", max_length=200),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return service.remove_membership_package(
            package_id,
            operator=current_user.user_id,
            reason=reason,
            idempotency_key=_require_idempotency_key(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{user_id}/360")
async def member_360(user_id: str) -> dict[str, Any]:
    try:
        return service.get_member_360(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{user_id}/conversations")
async def member_conversations(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    message_limit: int = Query(default=12, ge=1, le=50),
    q: str = Query(default=""),
    source: str = Query(default=""),
    capability: str = Query(default=""),
    sort: str = Query(default="updated_at"),
    order: str = Query(default="desc"),
) -> dict[str, Any]:
    try:
        return service.list_member_conversations(
            user_id,
            limit=limit,
            message_limit=message_limit,
            q=q,
            source=source,
            capability=capability,
            sort=sort,
            order=order,
        )
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


@router.post("/{user_id}/ops-actions")
async def record_member_ops_action(
    user_id: str,
    body: OpsActionResultRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key header is required for audited writes",
        )
    if len(normalized_key) > 128 or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized_key):
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key must be ≤ 128 chars of [a-zA-Z0-9_-]",
        )
    try:
        return service.record_ops_action_result(
            user_id,
            status=body.status,
            result=body.result,
            action_title=body.action_title,
            next_follow_up_at=body.next_follow_up_at,
            operator=current_user.user_id,
            idempotency_key=normalized_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{user_id}/conversations/{session_id}/view-audit")
async def record_member_conversation_view(
    user_id: str,
    session_id: str,
    # Round 3 G: accept reason via query (forward-compat for clients already
    # sending it that way) or JSON body { "reason": "complaint" | ... }.
    # The service-side whitelist is the authoritative gate.
    reason: str | None = Query(default=None),
    body: dict[str, Any] | None = Body(default=None),
    # Round 4 S1: X-Idempotency-Key is mandatory on every audited write. The
    # frontend useAuditedAction hook always injects it; missing/empty here
    # means either a misconfigured client or a manual replay attempt. Both must
    # be rejected at the edge so dedup is enforced (not advised).
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    normalized_key = (idempotency_key or "").strip()
    if not normalized_key:
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key header is required for audited writes",
        )
    # Round 5 M1: cap key length + character set so the audit_idempotency_keys
    # index cannot be inflated with multi-MB blobs and so callers cannot inject
    # the composite-key separator (':') to collide with another action's
    # dedup entry. UUID-ish characters only.
    if len(normalized_key) > 128 or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized_key):
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key must be ≤ 128 chars of [a-zA-Z0-9_-]",
        )
    body_reason = None
    if isinstance(body, dict):
        candidate = body.get("reason")
        if isinstance(candidate, str):
            body_reason = candidate
    effective_reason = reason if reason else body_reason
    # Round 5 M2: strip newline / CR so a reason containing log-injection
    # characters (e.g. '%0a' through the query param) cannot break audit_log
    # JSON parsers or downstream log aggregators.
    if effective_reason is not None:
        effective_reason = effective_reason.replace("\n", " ").replace("\r", " ")
    try:
        return service.record_conversation_view(
            user_id,
            session_id,
            operator=current_user.user_id,
            reason=effective_reason,
            idempotency_key=normalized_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.post("/batch")
async def member_batch_action(
    body: BatchActionRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    if body.action == "grant":
        raise HTTPException(
            status_code=400,
            detail="Batch tier grant is no longer supported; use manual membership purchase by package.",
        )
    return service.batch_update_members(
        user_ids=body.user_ids,
        action=body.action,
        days=body.days,
        tier=body.tier,
        expire_at=body.expire_at,
        auto_renew=body.auto_renew,
        reason=body.reason,
        operator=current_user.user_id,
    )


@router.get("/export")
async def member_export(
    status: str | None = None,
    tier: str | None = None,
    search: str | None = None,
    segment: str | None = None,
    risk_level: str | None = None,
    auto_renew: bool | None = None,
    expire_within_days: int | None = Query(default=None, ge=0, le=3650),
    active_within_days: int | None = Query(default=None, ge=0, le=3650),
    has_heartbeat_job: bool | None = None,
    has_overlay_candidates: bool | None = None,
) -> Response:
    export = service.export_members_csv(
        status=status,
        tier=tier,
        search=search,
        segment=segment,
        risk_level=risk_level,
        auto_renew=auto_renew,
        expire_within_days=expire_within_days,
        active_within_days=active_within_days,
        has_heartbeat_job=has_heartbeat_job,
        has_overlay_candidates=has_overlay_candidates,
    )
    return Response(
        content=export["content"],
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export["filename"]}"'},
    )


@router.post("/grant")
async def grant_membership(
    body: GrantRequest,
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    raise HTTPException(
        status_code=400,
        detail="Tier-only grant is no longer supported; use /api/v1/member/manual-purchase with a package.",
    )


@router.post("/manual-purchase")
async def manual_purchase_membership(
    body: ManualPurchaseRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key header is required for audited writes",
        )
    if len(normalized_key) > 128 or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized_key):
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key must be ≤ 128 chars of [a-zA-Z0-9_-]",
        )
    try:
        return service.manual_membership_purchase(
            user_id=body.user_id,
            package_id=body.package_id,
            days=body.days,
            operator=current_user.user_id,
            reason=body.reason,
            idempotency_key=normalized_key,
            phone=body.phone,
            display_name=body.display_name,
            amount_cny=body.amount_cny,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/manual-purchase/reverse")
async def reverse_manual_purchase_membership(
    body: ManualPurchaseReversalRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key header is required for audited writes",
        )
    if len(normalized_key) > 128 or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized_key):
        raise HTTPException(
            status_code=400,
            detail="X-Idempotency-Key must be ≤ 128 chars of [a-zA-Z0-9_-]",
        )
    if not body.purchase_id.strip():
        raise HTTPException(
            status_code=400,
            detail="purchase_id is required for manual membership reversal",
        )
    try:
        return service.reverse_manual_membership_purchase(
            user_id=body.user_id,
            purchase_id=body.purchase_id,
            amount_cny=None,
            operator=current_user.user_id,
            reason=body.reason,
            idempotency_key=normalized_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
