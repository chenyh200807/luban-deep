from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status

from deeptutor.api.dependencies.auth import AuthContext, _has_metrics_token_access, resolve_auth_context
from deeptutor.services.config import get_env_store
from deeptutor.services.bi_service import get_bi_service


def _bi_public_enabled() -> bool:
    value = get_env_store().get("DEEPTUTOR_BI_PUBLIC_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_idempotency_key(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Idempotency-Key header is required",
        )
    if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Idempotency-Key must be 1-128 chars of A-Z, a-z, 0-9, _ or -",
        )
    return normalized


def require_bi_access(
    authorization: str | None = Header(default=None),
    metrics_token: str | None = Header(default=None, alias="X-Metrics-Token"),
) -> AuthContext | None:
    current_user = resolve_auth_context(authorization)
    if current_user is not None and current_user.is_admin:
        return current_user
    if _bi_public_enabled():
        return current_user
    if _has_metrics_token_access(authorization, metrics_token):
        return None
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


def require_bi_admin(auth: AuthContext | None = Depends(require_bi_access)) -> AuthContext:
    if auth is not None and auth.is_admin:
        return auth
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


router = APIRouter(dependencies=[Depends(require_bi_access)])


@router.get("/overview")
async def bi_overview(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_overview(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/active-trend")
async def bi_active_trend(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_active_trend(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/retention")
async def bi_retention(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_retention(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/capabilities")
async def bi_capabilities(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_capability_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/tools")
async def bi_tools(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_tool_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/knowledge")
async def bi_knowledge(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_knowledge_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/members")
async def bi_members(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_member_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/tutorbots")
async def bi_tutorbots(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_tutorbot_stats(
        days=days,
        capability=capability,
        entrypoint=entrypoint,
        tier=tier,
    )


@router.get("/learner/{user_id}")
async def bi_learner_detail(user_id: str, days: int = Query(30, ge=1, le=365)):
    return await get_bi_service().get_learner_detail(user_id=user_id, days=days)


@router.get("/cost")
async def bi_cost(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_cost_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/cost/reconciliation")
async def bi_cost_reconciliation(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    workspace_id: str | None = Query(None),
    apikey_id: str | None = Query(None),
    model: str | None = Query(None),
    billing_cycle: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
):
    return await get_bi_service().get_cost_reconciliation(
        days=days,
        capability=capability,
        entrypoint=entrypoint,
        tier=tier,
        workspace_id=workspace_id,
        apikey_id=apikey_id,
        model=model,
        billing_cycle=billing_cycle,
    )


@router.get("/commerce")
async def bi_commerce(
    limit: int = Query(100, ge=1, le=500),
    _auth: AuthContext = Depends(require_bi_admin),
):
    return await get_bi_service().get_commerce(limit=limit)


@router.get("/anomalies")
async def bi_anomalies(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
):
    return await get_bi_service().get_anomalies(
        days=days,
        limit=limit,
        capability=capability,
        entrypoint=entrypoint,
        tier=tier,
    )


@router.get("/feedback")
async def bi_feedback(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    _auth: AuthContext = Depends(require_bi_admin),
):
    return await get_bi_service().get_feedback(days=days, limit=limit)


@router.post("/feedback/{feedback_id}/triage")
async def bi_feedback_triage(
    feedback_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_admin),
):
    key = _validate_idempotency_key(idempotency_key)
    body = payload or {}
    try:
        return await get_bi_service().triage_feedback(
            feedback_id=feedback_id,
            status=str(body.get("status") or ""),
            operator=auth.user_id,
            note=str(body.get("note") or ""),
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/member/{user_id}/ops-action")
async def bi_member_ops_action(
    user_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_admin),
):
    key = _validate_idempotency_key(idempotency_key)
    body = payload or {}
    try:
        return await get_bi_service().record_member_ops_action(
            user_id=user_id,
            status=str(body.get("status") or ""),
            result=str(body.get("result") or ""),
            action_title=str(body.get("action_title") or ""),
            next_follow_up_at=str(body.get("next_follow_up_at") or ""),
            operator=auth.user_id,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/export-jobs")
async def bi_export_request(
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_admin),
):
    key = _validate_idempotency_key(idempotency_key)
    body = payload or {}
    try:
        return await get_bi_service().request_export_job(
            dataset=str(body.get("dataset") or ""),
            export_format=str(body.get("format") or "csv"),
            filters=body.get("filters") if isinstance(body.get("filters"), dict) else {},
            operator=auth.user_id,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/invite-test/applications")
async def bi_invite_test_applications(
    days: int = Query(365, ge=1, le=3650),
    limit: int = Query(100, ge=1, le=500),
    status_filter: str | None = Query(None, alias="status"),
    source_page: str | None = Query(None),
    q: str | None = Query(None, max_length=120),
    auth: AuthContext = Depends(require_bi_admin),
):
    return await get_bi_service().get_invite_test_applications(
        days=days,
        limit=limit,
        status=status_filter,
        source_page=source_page,
        q=q,
        reveal_contact=auth.is_admin,
    )


@router.get("/invite-test/stats")
async def bi_invite_test_stats(
    days: int = Query(365, ge=1, le=3650),
    _auth: AuthContext = Depends(require_bi_admin),
):
    return await get_bi_service().get_invite_test_stats(days=days)
