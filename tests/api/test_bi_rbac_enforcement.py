"""端点级 RBAC enforcement 回归（P1-1 收口）。

验证 BI 数据端点真正按【生效权限矩阵】can_access 裁决，而不是旧的 is_admin 布尔旁路：
- operator/analyst 等非 full-admin 角色按各自矩阵被精确放行/拦截；
- 超管编辑角色矩阵（收权 admin）立即在端点生效；
- per-user 覆盖精确到人，不影响同角色其他人；
- env 引导 super_admin 恒全权、免一切编辑/覆盖。

这是 Codex 对抗审查 P1-1 的修复证据：此前矩阵只用于展示/service 方法，端点从不调用，
导致 operator/analyst 被 router 直接 403、admin 收权不生效。
"""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
fastapi_module = pytest.importorskip("fastapi")
FastAPI = fastapi_module.FastAPI
HTTPException = fastapi_module.HTTPException
TestClient = pytest.importorskip("fastapi.testclient").TestClient

bi = importlib.import_module("deeptutor.api.routers.bi")


class _StubBI:
    """只为通过权限门后的 200 端点提供最简返回；403 在权限门即返回，不触达此处。"""

    async def get_overview(self, **_kwargs):
        return {"ok": True}

    async def get_commerce(self, **_kwargs):
        return {"ok": True}

    async def get_invite_test_stats(self, **_kwargs):
        return {"ok": True}


@pytest.fixture
def rbac_env(tmp_path, monkeypatch):
    from deeptutor.services.member_console.service import get_member_console_service

    svc = get_member_console_service()
    monkeypatch.setattr(svc, "_bi_admins_path", lambda: tmp_path / "bi_admins.json")
    monkeypatch.setattr(svc, "_env_admin_user_ids", lambda: {"env-super"})
    monkeypatch.setattr(svc, "_safe_member_display_name", lambda uid: f"name-{uid}")
    monkeypatch.setattr("deeptutor.api.routers.bi.get_member_console_service", lambda: svc)
    monkeypatch.setattr("deeptutor.api.routers.bi.get_bi_service", lambda: _StubBI())

    app = FastAPI()
    app.include_router(bi.router, prefix="/api/v1/bi")
    return app, svc


def _login_as(app: FastAPI, user_id: str, *, is_admin: bool = False) -> None:
    """注入身份（仅替代 token 解析层）；授权裁决仍由真实 require_bi_permission/can_access 完成。"""
    app.dependency_overrides[bi.require_bi_access] = lambda: SimpleNamespace(
        user_id=user_id, is_admin=is_admin
    )


# ---- require_bi_access 放宽闸：非 full-admin 的 BI 成员也能进 router ----

def test_require_bi_access_admits_non_full_admin_member(monkeypatch):
    monkeypatch.setattr(
        bi, "resolve_auth_context", lambda _a: SimpleNamespace(user_id="u-op", is_admin=False)
    )

    class _M:
        def get_admin_role(self, uid):
            return "operator" if uid == "u-op" else None

    monkeypatch.setattr(bi, "get_member_console_service", lambda: _M())
    auth = bi.require_bi_access(authorization="Bearer x", metrics_token=None)
    assert auth is not None and auth.user_id == "u-op"


def test_require_bi_access_rejects_non_member(monkeypatch):
    monkeypatch.setattr(
        bi, "resolve_auth_context", lambda _a: SimpleNamespace(user_id="rando", is_admin=False)
    )

    class _M:
        def get_admin_role(self, _uid):
            return None

    monkeypatch.setattr(bi, "get_member_console_service", lambda: _M())
    monkeypatch.setattr(bi, "_bi_public_enabled", lambda: False)
    monkeypatch.setattr(bi, "_has_metrics_token_access", lambda *_a, **_k: False)
    with pytest.raises(HTTPException) as exc:
        bi.require_bi_access(authorization="Bearer x", metrics_token=None)
    assert exc.value.status_code == 403


# ---- 端点级矩阵裁决 ----

def test_operator_scoped_to_member_ops_blocked_elsewhere(rbac_env):
    app, svc = rbac_env
    svc.set_admin_role(actor="env-super", user_id="u-op", role="operator", at="t1")
    _login_as(app, "u-op")
    with TestClient(app) as client:
        assert client.get("/api/v1/bi/overview?days=7").status_code == 403  # 无 overview
        assert client.get("/api/v1/bi/commerce?limit=10").status_code == 403  # 无 commerce
        assert client.get("/api/v1/bi/invite-test/stats?days=365").status_code == 200  # member_ops/view


def test_analyst_read_all_tabs_but_no_write(rbac_env):
    app, svc = rbac_env
    svc.set_admin_role(actor="env-super", user_id="u-an", role="analyst", at="t1")
    _login_as(app, "u-an")
    with TestClient(app) as client:
        assert client.get("/api/v1/bi/overview?days=7").status_code == 200
        assert client.get("/api/v1/bi/commerce?limit=10").status_code == 200
        # 无 write：triage 在权限门即 403（不到 idempotency 校验）
        resp = client.post("/api/v1/bi/feedback/fb1/triage", json={"status": "triaged"})
        assert resp.status_code == 403


def test_admin_full_access_then_revoked_commerce_takes_effect(rbac_env):
    """Codex P1-1 安全面：超管收权 admin 的 commerce 后，端点立即拒绝。"""
    app, svc = rbac_env
    svc.set_admin_role(actor="env-super", user_id="u-ad", role="admin", at="t1")
    _login_as(app, "u-ad", is_admin=True)
    with TestClient(app) as client:
        assert client.get("/api/v1/bi/commerce?limit=10").status_code == 200
        # 超管把 admin 的 commerce 收掉（矩阵不含 commerce → 整列空）
        svc.set_role_permissions(
            actor="env-super",
            role="admin",
            matrix={
                "overview": ["view", "export", "write", "high_risk"],
                "member_ops": ["view", "export", "write", "high_risk"],
                "feedback": ["view", "export", "write", "high_risk"],
                "ops": ["view", "export", "write", "high_risk"],
            },
            at="t2",
        )
        assert client.get("/api/v1/bi/commerce?limit=10").status_code == 403


def test_env_super_admin_immune_to_edits(rbac_env):
    app, svc = rbac_env
    # 即便试图收权 super_admin（locked，应被 service 拒绝）
    with pytest.raises(ValueError):
        svc.set_role_permissions(actor="env-super", role="super_admin", matrix={}, at="t1")
    _login_as(app, "env-super", is_admin=True)
    with TestClient(app) as client:
        assert client.get("/api/v1/bi/commerce?limit=10").status_code == 200


def test_per_user_override_precise_to_person(rbac_env):
    app, svc = rbac_env
    svc.set_admin_role(actor="env-super", user_id="u-op1", role="operator", at="t1")
    svc.set_admin_role(actor="env-super", user_id="u-op2", role="operator", at="t1")
    svc.set_user_permission_overrides(
        actor="env-super", user_id="u-op1", overrides={"commerce": ["view"]}, at="t2"
    )
    _login_as(app, "u-op1")
    with TestClient(app) as client:
        assert client.get("/api/v1/bi/commerce?limit=10").status_code == 200  # 这个人开了
    _login_as(app, "u-op2")
    with TestClient(app) as client:
        assert client.get("/api/v1/bi/commerce?limit=10").status_code == 403  # 同角色他人不受影响
