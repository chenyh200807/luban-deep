from __future__ import annotations

import asyncio
from datetime import date
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status

from deeptutor.api.dependencies.auth import AuthContext, _has_metrics_token_access, resolve_auth_context
from deeptutor.api.routers.member import (
    AccountMergeRequest,
    BatchActionRequest,
    DeleteMemberAccountRequest,
    ManualPurchaseRequest,
    ManualPurchaseReversalRequest,
    MembershipPackageRequest,
    NoteCreateRequest,
    NoteUpdateRequest,
    OpsActionResultRequest,
    RevokeRequest,
    UpdateRequest,
)
from deeptutor.services.config import get_env_store
from deeptutor.services.bi_service import get_bi_service
from deeptutor.services.member_console.service import get_member_console_service


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
    # router 级闸：任何 BI 角色成员（super_admin/admin/operator/analyst）都放行进入
    # router；细粒度 tab/action 由端点级 require_bi_permission 按权限矩阵裁决。
    # 收权到这一层只用 get_admin_role(成员判定)，不用 is_admin(full-admin 布尔)，
    # 否则 operator/analyst 会被 router 直接挡在外面，端点矩阵永远没机会生效。
    if (
        current_user is not None
        and get_member_console_service().get_admin_role(current_user.user_id) is not None
    ):
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


def require_bi_permission(tab: str, action: str, *, public_ok: bool = False):
    """端点级 RBAC 强制门：按【生效权限矩阵】can_access 裁决某 (tab, action)。

    单一 authority：授权唯一依据是 member_console.can_access(= 角色矩阵[可被超管编辑]
    叠加 per-user 覆盖)，不再用 is_admin 布尔旁路。super_admin/admin 默认全权矩阵，
    被超管收权后 can_access 立即生效；operator/analyst 按各自矩阵细分。

    public_ok=True 的聚合非 PII 端点沿用历史 public/metrics-token 放行语义
    (require_bi_access 返回 None 即匿名只读放行)；public_ok=False 的 PII/写端点
    必须有真实 BI 身份。
    """

    def _dep(auth: AuthContext | None = Depends(require_bi_access)) -> AuthContext | None:
        if auth is None:
            # require_bi_access 已放行（metrics-token 校验通过，或 public 模式无身份）。
            # 聚合非 PII 端点允许匿名只读；PII/写端点要求真实身份。
            if public_ok:
                return None
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        if get_member_console_service().can_access(auth.user_id, tab, action):
            return auth
        from deeptutor.services.member_console import rbac

        label = f"{rbac.TAB_LABELS.get(tab, tab)}/{rbac.ACTION_LABELS.get(action, action)}"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"需要「{label}」权限",
        )

    return _dep


router = APIRouter(dependencies=[Depends(require_bi_access)])


@router.get("/overview")
async def bi_overview(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
):
    return await get_bi_service().get_overview(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/active-trend")
async def bi_active_trend(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
):
    return await get_bi_service().get_active_trend(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/retention")
async def bi_retention(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
):
    return await get_bi_service().get_retention(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/capabilities")
async def bi_capabilities(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
):
    return await get_bi_service().get_capability_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/tools")
async def bi_tools(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
):
    return await get_bi_service().get_tool_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/knowledge")
async def bi_knowledge(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
):
    return await get_bi_service().get_knowledge_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/members")
async def bi_members(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
):
    return await get_bi_service().get_member_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/tutorbots")
async def bi_tutorbots(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
):
    return await get_bi_service().get_tutorbot_stats(
        days=days,
        capability=capability,
        entrypoint=entrypoint,
        tier=tier,
    )


@router.get("/learner/{user_id}")
async def bi_learner_detail(
    user_id: str,
    days: int = Query(30, ge=1, le=365),
    # Admin-only, like the other learner-data endpoints. Without this, when
    # DEEPTUTOR_BI_PUBLIC_ENABLED is on, any authenticated student could read ANY
    # other user's learner detail by substituting user_id (horizontal IDOR).
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
):
    return await get_bi_service().get_learner_detail(user_id=user_id, days=days)


@router.get("/cost")
async def bi_cost(
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("commerce", "view", public_ok=True)),
):
    return await get_bi_service().get_cost_stats(days=days, capability=capability, entrypoint=entrypoint, tier=tier)


@router.get("/cost/reconciliation")
async def bi_cost_reconciliation(
    _auth: AuthContext = Depends(require_bi_permission("commerce", "view")),
    provider: str = Query("dashscope"),
    days: int = Query(30, ge=1, le=365),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    environment: str | None = Query(None),
    cost_center: str = Query("all"),
    billable_only: bool = Query(False),
    cost_basis: str = Query("list_price_cost"),
    workspace_id: str | None = Query(None),
    apikey_id: str | None = Query(None),
    api_key_fingerprint: str | None = Query(None),
    model: str | None = Query(None),
    billing_cycle: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
):
    return await get_bi_service().get_cost_reconciliation(
        provider=provider,
        days=days,
        capability=capability,
        entrypoint=entrypoint,
        tier=tier,
        environment=environment,
        cost_center=cost_center,
        billable_only=billable_only,
        cost_basis=cost_basis,
        workspace_id=workspace_id,
        apikey_id=apikey_id,
        api_key_fingerprint=api_key_fingerprint,
        model=model,
        billing_cycle=billing_cycle,
    )


@router.get("/member-ops/packages")
async def bi_member_ops_packages(
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
):
    """套餐品类列表（operator 可访问）：会员运营开通套餐下拉用，不含账务明细。"""
    return await get_bi_service().get_available_packages()


@router.get("/commerce")
async def bi_commerce(
    limit: int = Query(100, ge=1, le=500),
    _auth: AuthContext = Depends(require_bi_permission("commerce", "view")),
):
    return await get_bi_service().get_commerce(limit=limit)


@router.get("/anomalies")
async def bi_anomalies(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
    capability: str | None = Query(None),
    entrypoint: str | None = Query(None),
    tier: str | None = Query(None),
    _auth: AuthContext | None = Depends(require_bi_permission("overview", "view", public_ok=True)),
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
    _auth: AuthContext = Depends(require_bi_permission("feedback", "view")),
):
    return await get_bi_service().get_feedback(days=days, limit=limit)


@router.post("/feedback/{feedback_id}/triage")
async def bi_feedback_triage(
    feedback_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("feedback", "write")),
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
    body: OpsActionResultRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    return _record_bi_member_ops_action(
        user_id=user_id,
        body=body,
        idempotency_key=idempotency_key,
        auth=auth,
    )


@router.post("/member/{user_id}/ops-actions")
async def bi_member_ops_actions(
    user_id: str,
    body: OpsActionResultRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    return _record_bi_member_ops_action(
        user_id=user_id,
        body=body,
        idempotency_key=idempotency_key,
        auth=auth,
    )


def _record_bi_member_ops_action(
    *,
    user_id: str,
    body: OpsActionResultRequest,
    idempotency_key: str | None,
    auth: AuthContext,
) -> dict[str, Any]:
    key = _validate_idempotency_key(idempotency_key)
    try:
        return get_member_console_service().record_ops_action_result(
            user_id,
            status=body.status,
            result=body.result,
            action_title=body.action_title,
            next_follow_up_at=body.next_follow_up_at,
            operator=auth.user_id,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/member/dashboard")
async def bi_member_dashboard(
    days: int = Query(30, ge=1, le=3650),
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    return get_member_console_service().get_dashboard(days=days)


@router.get("/member/list")
async def bi_member_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = Query("expire_at"),
    order: str = Query("asc"),
    status_filter: str | None = Query(None, alias="status"),
    tier: str | None = Query(None),
    search: str | None = Query(None),
    segment: str | None = Query(None),
    risk_level: str | None = Query(None),
    risk_min: float | None = Query(default=None, ge=0, le=1),
    auto_renew: bool | None = Query(None),
    expire_within_days: int | None = Query(default=None, ge=0, le=3650),
    active_within_days: int | None = Query(default=None, ge=0, le=3650),
    registered_from: date | None = Query(default=None),
    registered_to: date | None = Query(default=None),
    review_due_min: int | None = Query(default=None, ge=0, le=3650),
    not_paid: bool | None = Query(default=None),
    channel: str | None = Query(default=None, max_length=64),
    behavior_cohort: str | None = Query(default=None, max_length=64),
    has_heartbeat_job: bool | None = None,
    has_overlay_candidates: bool | None = None,
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    return get_member_console_service().list_members(
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        status=status_filter,
        tier=tier,
        search=search,
        segment=segment,
        risk_level=risk_level,
        risk_min=risk_min,
        auto_renew=auto_renew,
        expire_within_days=expire_within_days,
        active_within_days=active_within_days,
        registered_from=registered_from,
        registered_to=registered_to,
        review_due_min=review_due_min,
        not_paid=not_paid,
        channel=channel,
        behavior_cohort=behavior_cohort,
        has_heartbeat_job=has_heartbeat_job,
        has_overlay_candidates=has_overlay_candidates,
    )


@router.get("/member/overview")
async def bi_member_ops_overview(
    days: int = Query(30, ge=1, le=3650),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: str = Query("expire_at"),
    order: str = Query("asc"),
    status_filter: str | None = Query(None, alias="status"),
    tier: str | None = Query(None),
    search: str | None = Query(None),
    segment: str | None = Query(None),
    risk_level: str | None = Query(None),
    risk_min: float | None = Query(default=None, ge=0, le=1),
    auto_renew: bool | None = Query(None),
    expire_within_days: int | None = Query(default=None, ge=0, le=3650),
    active_within_days: int | None = Query(default=None, ge=0, le=3650),
    registered_from: date | None = Query(default=None),
    registered_to: date | None = Query(default=None),
    review_due_min: int | None = Query(default=None, ge=0, le=3650),
    not_paid: bool | None = Query(default=None),
    channel: str | None = Query(default=None, max_length=64),
    behavior_cohort: str | None = Query(default=None, max_length=64),
    has_heartbeat_job: bool | None = None,
    has_overlay_candidates: bool | None = None,
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    return get_member_console_service().get_member_ops_overview(
        days=days,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        status=status_filter,
        tier=tier,
        search=search,
        segment=segment,
        risk_level=risk_level,
        risk_min=risk_min,
        auto_renew=auto_renew,
        expire_within_days=expire_within_days,
        active_within_days=active_within_days,
        registered_from=registered_from,
        registered_to=registered_to,
        review_due_min=review_due_min,
        not_paid=not_paid,
        channel=channel,
        behavior_cohort=behavior_cohort,
        has_heartbeat_job=has_heartbeat_job,
        has_overlay_candidates=has_overlay_candidates,
    )


@router.get("/member/packages")
async def bi_list_membership_packages(
    auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    return {
        "items": get_member_console_service().list_membership_packages(),
        "operator": auth.user_id,
    }


@router.put("/member/packages/{package_id}")
async def bi_upsert_membership_package(
    package_id: str,
    body: MembershipPackageRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    key = _validate_idempotency_key(idempotency_key)
    try:
        return get_member_console_service().upsert_membership_package(
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
            operator=auth.user_id,
            reason=body.reason,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/member/packages/{package_id}")
async def bi_delete_membership_package(
    package_id: str,
    reason: str = Query(default="", max_length=200),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "high_risk")),
) -> dict[str, Any]:
    key = _validate_idempotency_key(idempotency_key)
    try:
        return get_member_console_service().remove_membership_package(
            package_id,
            operator=auth.user_id,
            reason=reason,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/member/{user_id}/360")
async def bi_member_360(
    user_id: str,
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().get_member_360(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/member/{user_id}/conversations")
async def bi_member_conversations(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    message_limit: int = Query(default=12, ge=1, le=50),
    q: str = Query(default=""),
    source: str = Query(default=""),
    capability: str = Query(default=""),
    sort: str = Query(default="updated_at"),
    order: str = Query(default="desc"),
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().list_member_conversations(
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/member/{user_id}/conversations/{session_id}/view-audit")
async def bi_member_conversation_view_audit(
    user_id: str,
    session_id: str,
    reason: str | None = Query(default=None),
    body: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    key = _validate_idempotency_key(idempotency_key)
    body_reason = body.get("reason") if isinstance(body, dict) else None
    effective_reason = reason if reason else body_reason
    if isinstance(effective_reason, str):
        effective_reason = effective_reason.replace("\n", " ").replace("\r", " ")
    try:
        return get_member_console_service().record_conversation_view(
            user_id,
            session_id,
            operator=auth.user_id,
            reason=effective_reason,
            idempotency_key=key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/member/{user_id}/learner-state")
async def bi_member_learner_state(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().get_member_learner_state_panel(user_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/member/{user_id}/heartbeat-jobs")
async def bi_member_heartbeat_jobs(
    user_id: str,
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().list_member_heartbeat_jobs(user_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/member/{user_id}/heartbeat-jobs/{job_id}/pause")
async def bi_pause_member_heartbeat_job(
    user_id: str,
    job_id: str,
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().pause_member_heartbeat_job(
            user_id, job_id, operator=auth.user_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/member/{user_id}/heartbeat-jobs/{job_id}/resume")
async def bi_resume_member_heartbeat_job(
    user_id: str,
    job_id: str,
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().resume_member_heartbeat_job(
            user_id, job_id, operator=auth.user_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/member/{user_id}/overlays/{bot_id}")
async def bi_member_overlay(
    user_id: str,
    bot_id: str,
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().get_member_overlay(user_id, bot_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/member/{user_id}/overlays/{bot_id}/events")
async def bi_member_overlay_events(
    user_id: str,
    bot_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    event_type: str | None = None,
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().get_member_overlay_events(
            user_id, bot_id, limit=limit, event_type=event_type
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/member/{user_id}/overlays/{bot_id}/audit")
async def bi_member_overlay_audit(
    user_id: str,
    bot_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().get_member_overlay_audit(user_id, bot_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/member/{user_id}/overlays/{bot_id}")
async def bi_patch_member_overlay(
    user_id: str,
    bot_id: str,
    body: Any = Body(...),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().patch_member_overlay(
            user_id,
            bot_id,
            list(getattr(body, "operations", None) or body.get("operations") or []),
            operator=auth.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/member/{user_id}/overlays/{bot_id}/promotions/apply")
async def bi_apply_member_overlay_promotions(
    user_id: str,
    bot_id: str,
    body: dict[str, Any] | None = Body(default=None),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    payload = body or {}
    try:
        return get_member_console_service().apply_member_overlay_promotions(
            user_id,
            bot_id,
            operator=auth.user_id,
            min_confidence=payload.get("min_confidence"),
            max_candidates=payload.get("max_candidates"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/member/{user_id}/notes")
async def bi_create_member_note(
    user_id: str,
    body: NoteCreateRequest,
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().add_note(
            user_id,
            body.content,
            channel=body.channel,
            pinned=body.pinned,
            operator=auth.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/member/notes/{note_id}")
async def bi_update_member_note(
    note_id: str,
    body: NoteUpdateRequest,
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    try:
        return get_member_console_service().update_note(
            note_id,
            content=body.content,
            pinned=body.pinned,
            operator=auth.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/member/notes/{note_id}")
async def bi_delete_member_note(
    note_id: str,
    auth: AuthContext = Depends(require_bi_permission("member_ops", "high_risk")),
) -> dict[str, Any]:
    deleted = get_member_console_service().delete_note(note_id, operator=auth.user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown note")
    return {"deleted": True}


@router.get("/member/audit-log")
async def bi_member_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    target_user: str | None = None,
    operator: str | None = None,
    action: str | None = None,
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
) -> dict[str, Any]:
    return get_member_console_service().get_audit_log(
        page=page,
        page_size=page_size,
        target_user=target_user,
        operator=operator,
        action=action,
    )


@router.get("/member/export")
async def bi_member_export(
    status_filter: str | None = Query(None, alias="status"),
    tier: str | None = None,
    search: str | None = None,
    segment: str | None = None,
    risk_level: str | None = None,
    risk_min: float | None = Query(default=None, ge=0, le=1),
    auto_renew: bool | None = None,
    expire_within_days: int | None = Query(default=None, ge=0, le=3650),
    active_within_days: int | None = Query(default=None, ge=0, le=3650),
    registered_from: date | None = Query(default=None),
    registered_to: date | None = Query(default=None),
    review_due_min: int | None = Query(default=None, ge=0, le=3650),
    not_paid: bool | None = Query(default=None),
    channel: str | None = Query(default=None, max_length=64),
    behavior_cohort: str | None = Query(default=None, max_length=64),
    has_heartbeat_job: bool | None = None,
    has_overlay_candidates: bool | None = None,
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "export")),
):
    from fastapi import Response

    export = get_member_console_service().export_members_csv(
        status=status_filter,
        tier=tier,
        search=search,
        segment=segment,
        risk_level=risk_level,
        risk_min=risk_min,
        auto_renew=auto_renew,
        expire_within_days=expire_within_days,
        active_within_days=active_within_days,
        registered_from=registered_from,
        registered_to=registered_to,
        review_due_min=review_due_min,
        not_paid=not_paid,
        channel=channel,
        behavior_cohort=behavior_cohort,
        has_heartbeat_job=has_heartbeat_job,
        has_overlay_candidates=has_overlay_candidates,
    )
    return Response(
        content=export["content"],
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export["filename"]}"'},
    )


@router.post("/member/batch")
async def bi_member_batch_action(
    body: BatchActionRequest,
    auth: AuthContext = Depends(require_bi_permission("member_ops", "high_risk")),
) -> dict[str, Any]:
    if body.action == "grant":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch tier grant is no longer supported; use package-based manual purchase.",
        )
    return get_member_console_service().batch_update_members(
        user_ids=body.user_ids,
        action=body.action,
        days=body.days,
        tier=body.tier,
        expire_at=body.expire_at,
        auto_renew=body.auto_renew,
        reason=body.reason,
        operator=auth.user_id,
    )


@router.post("/member/manual-purchase")
async def bi_manual_purchase_membership(
    body: ManualPurchaseRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    key = _validate_idempotency_key(idempotency_key)
    try:
        return get_member_console_service().manual_membership_purchase(
            user_id=body.user_id,
            package_id=body.package_id,
            days=body.days,
            operator=auth.user_id,
            reason=body.reason,
            idempotency_key=key,
            phone=body.phone,
            display_name=body.display_name,
            amount_cny=body.amount_cny,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/member/manual-purchase/reverse")
async def bi_reverse_manual_purchase_membership(
    body: ManualPurchaseReversalRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "high_risk")),
) -> dict[str, Any]:
    key = _validate_idempotency_key(idempotency_key)
    if not body.purchase_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="purchase_id is required for BI membership reversal",
        )
    try:
        return get_member_console_service().reverse_manual_membership_purchase(
            user_id=body.user_id,
            purchase_id=body.purchase_id,
            amount_cny=None,
            operator=auth.user_id,
            reason=body.reason,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/member/merge-accounts")
async def bi_merge_member_accounts(
    body: AccountMergeRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "high_risk")),
) -> dict[str, Any]:
    key = _validate_idempotency_key(idempotency_key)
    try:
        return get_member_console_service().merge_member_accounts(
            target_user_id=body.target_user_id,
            source_user_ids=body.source_user_ids,
            operator=auth.user_id,
            reason=body.reason,
            idempotency_key=key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/member/{user_id}/account")
async def bi_delete_member_account(
    user_id: str,
    body: DeleteMemberAccountRequest | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "high_risk")),
) -> dict[str, Any]:
    key = _validate_idempotency_key(idempotency_key)
    reason = str((body.reason if body else "") or "").strip()
    try:
        return get_member_console_service().delete_member_account(
            user_id,
            operator=auth.user_id,
            reason=reason,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/member/update")
async def bi_update_membership(
    body: UpdateRequest,
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
) -> dict[str, Any]:
    return get_member_console_service().update_subscription(
        body.user_id,
        tier=body.tier,
        days=body.days,
        expire_at=body.expire_at,
        auto_renew=body.auto_renew,
        reason=body.reason,
        operator=auth.user_id,
    )


@router.post("/member/revoke")
async def bi_revoke_membership(
    body: RevokeRequest,
    auth: AuthContext = Depends(require_bi_permission("member_ops", "high_risk")),
) -> dict[str, Any]:
    return get_member_console_service().revoke_subscription(
        body.user_id,
        reason=body.reason,
        operator=auth.user_id,
    )


@router.post("/export-jobs")
async def bi_export_request(
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "export")),
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
    auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
):
    return await get_bi_service().get_invite_test_applications(
        days=days,
        limit=limit,
        status=status_filter,
        source_page=source_page,
        q=q,
        reveal_contact=auth.is_admin,
    )


@router.patch("/invite-test/applications/{application_id}")
async def bi_invite_test_application_update(
    application_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
):
    key = _validate_idempotency_key(idempotency_key)
    try:
        return await get_bi_service().update_invite_test_application(
            application_id=application_id,
            payload=payload or {},
            operator=auth.user_id,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite-test application not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.delete("/invite-test/applications/{application_id}")
async def bi_invite_test_application_delete(
    application_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "high_risk")),
):
    key = _validate_idempotency_key(idempotency_key)
    try:
        return await get_bi_service().delete_invite_test_application(
            application_id=application_id,
            payload=payload or {},
            operator=auth.user_id,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite-test application not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/invite-test/stats")
async def bi_invite_test_stats(
    days: int = Query(365, ge=1, le=3650),
    _auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
):
    return await get_bi_service().get_invite_test_stats(days=days)


@router.get("/luban-feedback/responses")
async def bi_luban_feedback_responses(
    days: int = Query(365, ge=1, le=3650),
    limit: int = Query(100, ge=1, le=500),
    status_filter: str | None = Query(None, alias="status"),
    source_page: str | None = Query(None),
    q: str | None = Query(None, max_length=120),
    auth: AuthContext = Depends(require_bi_permission("feedback", "view")),
):
    return await get_bi_service().get_luban_feedback_responses(
        days=days,
        limit=limit,
        status=status_filter,
        source_page=source_page,
        q=q,
        reveal_contact=auth.is_admin,
    )


@router.get("/luban-feedback/stats")
async def bi_luban_feedback_stats(
    days: int = Query(365, ge=1, le=3650),
    _auth: AuthContext = Depends(require_bi_permission("feedback", "view")),
):
    return await get_bi_service().get_luban_feedback_stats(days=days)


@router.patch("/luban-feedback/responses/{response_id}")
async def bi_luban_feedback_response_update(
    response_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("feedback", "write")),
):
    key = _validate_idempotency_key(idempotency_key)
    try:
        return await get_bi_service().update_luban_feedback_response(
            response_id=response_id,
            payload=payload or {},
            operator=auth.user_id,
            idempotency_key=key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Luban feedback response not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def require_bi_permission_manager(
    auth: AuthContext | None = Depends(require_bi_access),
) -> AuthContext:
    """权限管理端点专用门：允许 can_manage_permissions 的管理员变更权限。"""
    if auth is None or not get_member_console_service().can_manage_permissions(auth.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限才能管理 BI 权限",
        )
    return auth


require_bi_super_admin = require_bi_permission_manager


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@router.get("/rbac/roles")
async def bi_rbac_roles(_auth: AuthContext = Depends(require_bi_admin)):
    """角色定义 + 【生效】权限矩阵(含管理员已编辑) + tab/操作维度 + 可编辑标记。"""
    return get_member_console_service().roles_payload()


@router.put("/rbac/roles/{role}/permissions")
async def bi_set_role_permissions(
    role: str,
    payload: dict[str, Any] | None = Body(default=None),
    auth: AuthContext = Depends(require_bi_permission_manager),
):
    """编辑某角色的权限矩阵(角色级,影响所有该角色管理员)。body: {matrix:{tab:[actions]}}。"""
    body = payload or {}
    matrix = body.get("matrix") if isinstance(body.get("matrix"), dict) else body
    try:
        return get_member_console_service().set_role_permissions(
            actor=auth.user_id, role=role, matrix=matrix, at=_now_iso()
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/admins/{user_id}/permissions")
async def bi_set_user_permissions(
    user_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    auth: AuthContext = Depends(require_bi_permission_manager),
):
    """精确到人:给某管理员设个人权限覆盖。body: {overrides:{tab:[actions]}}(只提交的 tab 覆盖)。"""
    body = payload or {}
    overrides = body.get("overrides") if isinstance(body.get("overrides"), dict) else {}
    try:
        admins = get_member_console_service().set_user_permission_overrides(
            actor=auth.user_id, user_id=user_id, overrides=overrides, at=_now_iso()
        )
        return {"admins": admins, "user_id": user_id}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/admins/{user_id}/effective-permissions")
async def bi_user_effective_permissions(
    user_id: str, _auth: AuthContext = Depends(require_bi_admin)
):
    """某管理员的最终生效权限矩阵(角色权限叠加个人覆盖)。"""
    svc = get_member_console_service()
    return {
        "user_id": user_id,
        "role": svc.get_admin_role(user_id),
        "effective_matrix": svc.get_effective_permissions(user_id),
    }


@router.get("/rbac/me")
async def bi_rbac_me(auth: AuthContext | None = Depends(require_bi_access)):
    """当前登录者的角色与生效权限(前端导航门控用)。"""
    from deeptutor.services.member_console import rbac

    uid = auth.user_id if auth else ""
    svc = get_member_console_service()
    role = svc.get_admin_role(uid)
    effective = svc.get_effective_permissions(uid) if role else {}
    return {
        "user_id": uid,
        "role": role,
        "role_label": rbac.ROLE_LABELS.get(role or "", ""),
        "can_manage_permissions": svc.can_manage_permissions(uid),
        "is_full_admin": rbac.is_full_admin(role),
        "accessible_tabs": [t for t in rbac.TABS if "view" in (effective.get(t) or [])],
        "matrix": effective,
    }


@router.get("/admins")
async def bi_list_admins(_auth: AuthContext = Depends(require_bi_admin)):
    """列出 BI 管理员（含角色、可访问 tab、来源）。"""
    return {"admins": get_member_console_service().list_admin_user_ids()}


@router.get("/admins/audit")
async def bi_admins_audit(
    limit: int = Query(200, ge=1, le=1000),
    _auth: AuthContext = Depends(require_bi_permission_manager),
):
    """权限变更审计（谁在何时把谁设成什么角色）。"""
    return {"audit": get_member_console_service().list_admin_audit(limit=limit)}


@router.get("/admins/search-members")
async def bi_admins_search_members(
    q: str = Query("", min_length=0, max_length=64),
    limit: int = Query(10, ge=1, le=50),
    _auth: AuthContext = Depends(require_bi_permission_manager),
):
    """按手机号/姓名/user_id 搜会员，供添加管理员选人（带回 user_id）。"""
    return {"members": get_member_console_service().search_members_for_admin(q=q, limit=limit)}


@router.post("/admins")
async def bi_add_admin(
    payload: dict[str, Any] | None = Body(default=None),
    auth: AuthContext = Depends(require_bi_permission_manager),
):
    """添加管理员并指定角色，立即生效。body: {user_id, role, display_name?}。"""
    from deeptutor.services.member_console import rbac

    body = payload or {}
    raw = str(body.get("user_id") or "").strip()
    role = str(body.get("role") or rbac.ROLE_ADMIN).strip()
    display_name = str(body.get("display_name") or "").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id 必填")
    try:
        admins = get_member_console_service().set_admin_role(
            actor=auth.user_id, user_id=raw, role=role, display_name=display_name, at=_now_iso()
        )
        return {"admins": admins, "added": raw, "role": role}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/admins/{user_id}")
async def bi_set_admin_role(
    user_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    auth: AuthContext = Depends(require_bi_permission_manager),
):
    """修改管理员角色。body: {role}。"""
    body = payload or {}
    role = str(body.get("role") or "").strip()
    if not role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role 必填")
    try:
        admins = get_member_console_service().set_admin_role(
            actor=auth.user_id, user_id=user_id, role=role, at=_now_iso()
        )
        return {"admins": admins, "user_id": user_id, "role": role}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/admins/{user_id}")
async def bi_remove_admin(
    user_id: str,
    auth: AuthContext = Depends(require_bi_permission_manager),
):
    """移除管理员。系统引导管理员不可移除（防止锁死超管）。"""
    try:
        admins = get_member_console_service().remove_admin_user(
            user_id, actor=auth.user_id, at=_now_iso()
        )
        return {"admins": admins}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/cost-calibration")
async def bi_cost_calibration_status(_auth: AuthContext = Depends(require_bi_permission("commerce", "view"))):
    """读当前自校准状态（系数 + 全局健康度 + 上次刷新时间）。"""
    from pathlib import Path

    from deeptutor.services.observability.cost_calibration import load_calibration

    service = get_bi_service()
    path: Path = service._cost_calibration_path()
    return load_calibration(path)


@router.post("/cost-calibration/refresh")
async def bi_cost_calibration_refresh(
    payload: dict[str, Any] | None = Body(default=None),
    _auth: AuthContext = Depends(require_bi_permission("commerce", "write")),
):
    """用官方账单反推真实单价，刷新自校准系数。billing_cycle 默认当月。"""
    from datetime import datetime, timezone

    body = payload or {}
    now = datetime.now(timezone.utc)
    billing_cycle = str(body.get("billing_cycle") or now.strftime("%Y-%m")).strip()
    return await get_bi_service().refresh_cost_calibration(
        billing_cycle=billing_cycle, generated_at=now.isoformat()
    )


@router.get("/member-ops/internal-accounts")
async def bi_internal_accounts(
    limit: int = Query(200, ge=1, le=1000),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "view")),
):
    """内部账号列表 + 完整审计流水（仅 member_ops view 及以上可访问）。"""
    states, audit = await asyncio.gather(
        get_bi_service().get_internal_account_states(),
        get_bi_service().get_internal_account_audit_log(limit=limit),
    )
    internal_users = [v for v in states.values() if v.get("is_internal")]
    return {"states": states, "internal_accounts": internal_users, "audit": audit, "total_internal": len(internal_users)}


@router.post("/member/{user_id}/internal-account")
async def bi_mark_internal_account(
    user_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
):
    """标记 / 取消标记内部账号。操作人和原因强制记录，不可删改。"""
    body = payload or {}
    is_internal_flag = body.get("is_internal")
    if is_internal_flag is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="is_internal (bool) is required")
    reason = str(body.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason must be at least 5 characters")
    try:
        result = await get_bi_service().mark_internal_account(
            user_id=user_id,
            is_internal=bool(is_internal_flag),
            operator_id=auth.user_id,
            reason=reason,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
