from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from deeptutor.api.dependencies.auth import AuthContext, resolve_auth_context
from deeptutor.services.config import get_env_store
from deeptutor.services.bi_service import get_bi_service


def _bi_public_enabled() -> bool:
    value = get_env_store().get("DEEPTUTOR_BI_PUBLIC_ENABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def require_bi_access(authorization: str | None = Header(default=None)) -> AuthContext | None:
    current_user = resolve_auth_context(authorization)
    if _bi_public_enabled():
        return current_user
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if current_user.is_admin:
        return current_user
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
):
    return await get_bi_service().get_feedback(days=days, limit=limit)
