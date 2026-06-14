from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status

from deeptutor.api.dependencies.auth import AuthContext, _has_metrics_token_access, resolve_auth_context
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
    payload: dict[str, Any] | None = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    auth: AuthContext = Depends(require_bi_permission("member_ops", "write")),
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
