from __future__ import annotations

import pytest

from deeptutor.services.member_console import rbac
from deeptutor.services.member_console.service import get_member_console_service


@pytest.fixture
def svc(tmp_path, monkeypatch):
    service = get_member_console_service()
    monkeypatch.setattr(service, "_bi_admins_path", lambda: tmp_path / "bi_admins.json")
    monkeypatch.setattr(service, "_env_admin_user_ids", lambda: {"env-super"})
    monkeypatch.setattr(service, "_safe_member_display_name", lambda uid: f"name-{uid}")
    return service


def test_env_admin_is_super_admin_not_editable(svc):
    assert svc.get_admin_role("env-super") == rbac.ROLE_SUPER_ADMIN
    assert svc.is_admin_user("env-super") is True
    assert svc.can_manage_permissions("env-super") is True
    entry = next(e for e in svc.list_admin_user_ids() if e["user_id"] == "env-super")
    assert entry["role"] == "super_admin"
    assert entry["removable"] is False
    assert entry["editable"] is False


def test_add_admin_with_role_takes_effect(svc):
    assert svc.get_admin_role("u-new") is None
    svc.set_admin_role(actor="env-super", user_id="u-new", role=rbac.ROLE_OPERATOR, at="t1")
    assert svc.get_admin_role("u-new") == rbac.ROLE_OPERATOR
    # operator 不是 full admin
    assert svc.is_admin_user("u-new") is False
    # operator 能写会员运营，不能高危，看不到成本
    assert svc.can_access("u-new", "member_ops", "write") is True
    assert svc.can_access("u-new", "member_ops", "high_risk") is False
    assert svc.can_access("u-new", "commerce", "view") is False


def test_change_role(svc):
    svc.set_admin_role(actor="env-super", user_id="u-x", role=rbac.ROLE_ANALYST, at="t1")
    svc.set_admin_role(actor="env-super", user_id="u-x", role=rbac.ROLE_ADMIN, at="t2")
    assert svc.get_admin_role("u-x") == rbac.ROLE_ADMIN
    assert svc.is_admin_user("u-x") is True


def test_analyst_read_only(svc):
    svc.set_admin_role(actor="env-super", user_id="u-a", role=rbac.ROLE_ANALYST, at="t1")
    assert svc.can_access("u-a", "overview", "view") is True
    assert svc.can_access("u-a", "overview", "write") is False
    assert svc.can_manage_permissions("u-a") is False


def test_cannot_change_or_remove_env_admin(svc):
    with pytest.raises(ValueError):
        svc.set_admin_role(actor="env-super", user_id="env-super", role=rbac.ROLE_ANALYST)
    with pytest.raises(ValueError):
        svc.remove_admin_user("env-super", actor="env-super")
    assert svc.get_admin_role("env-super") == rbac.ROLE_SUPER_ADMIN


def test_remove_runtime_admin(svc):
    svc.set_admin_role(actor="env-super", user_id="u-temp", role=rbac.ROLE_ADMIN, at="t1")
    svc.remove_admin_user("u-temp", actor="env-super", at="t2")
    assert svc.get_admin_role("u-temp") is None


def test_invalid_role_rejected(svc):
    with pytest.raises(ValueError):
        svc.set_admin_role(actor="env-super", user_id="u-bad", role="ghost")


def test_audit_trail(svc):
    svc.set_admin_role(actor="env-super", user_id="u-1", role=rbac.ROLE_ADMIN, at="t1")
    svc.set_admin_role(actor="env-super", user_id="u-1", role=rbac.ROLE_OPERATOR, at="t2")
    svc.remove_admin_user("u-1", actor="env-super", at="t3")
    audit = svc.list_admin_audit()
    # 最新在前
    assert audit[0]["action"] == "remove_admin"
    actions = [a["action"] for a in audit]
    assert "add_admin" in actions and "set_role" in actions


# ---- 角色权限编辑 + per-user 覆盖（精确到人）----

def test_edit_role_permissions_takes_effect(svc):
    """超管把 operator 改成能看成本(commerce view)，所有 operator 生效。"""
    svc.set_admin_role(actor="env-super", user_id="u-op", role=rbac.ROLE_OPERATOR, at="t1")
    assert svc.can_access("u-op", "commerce", "view") is False  # 默认看不到
    svc.set_role_permissions(
        actor="env-super",
        role=rbac.ROLE_OPERATOR,
        matrix={"member_ops": ["view", "export", "write"], "feedback": ["view"], "commerce": ["view"]},
        at="t2",
    )
    assert svc.can_access("u-op", "commerce", "view") is True
    assert svc.can_access("u-op", "commerce", "write") is False


def test_cannot_edit_super_admin_role(svc):
    with pytest.raises(ValueError):
        svc.set_role_permissions(actor="env-super", role=rbac.ROLE_SUPER_ADMIN, matrix={})


def test_per_user_override_precise_to_person(svc):
    """精确到人:给某个 analyst 单独开 commerce 写权限,不影响其他 analyst。"""
    svc.set_admin_role(actor="env-super", user_id="u-a1", role=rbac.ROLE_ANALYST, at="t1")
    svc.set_admin_role(actor="env-super", user_id="u-a2", role=rbac.ROLE_ANALYST, at="t1")
    assert svc.can_access("u-a1", "commerce", "write") is False
    svc.set_user_permission_overrides(
        actor="env-super", user_id="u-a1", overrides={"commerce": ["view", "export", "write"]}, at="t2"
    )
    assert svc.can_access("u-a1", "commerce", "write") is True   # 这个人开了
    assert svc.can_access("u-a2", "commerce", "write") is False  # 另一个人不受影响


def test_effective_permissions_payload(svc):
    svc.set_admin_role(actor="env-super", user_id="u-op", role=rbac.ROLE_OPERATOR, at="t1")
    svc.set_user_permission_overrides(
        actor="env-super", user_id="u-op", overrides={"ops": ["view"]}, at="t2"
    )
    eff = svc.get_effective_permissions("u-op")
    assert eff["ops"] == ["view"]              # 个人覆盖加了 ops view
    assert eff["member_ops"] == ["view", "export", "write"]  # 角色默认保留


def test_cannot_override_env_super_admin(svc):
    with pytest.raises(ValueError):
        svc.set_user_permission_overrides(
            actor="env-super", user_id="env-super", overrides={"commerce": []}
        )


def test_role_edit_persists_in_list_and_payload(svc):
    svc.set_admin_role(actor="env-super", user_id="u-op", role=rbac.ROLE_OPERATOR, at="t1")
    svc.set_role_permissions(
        actor="env-super", role=rbac.ROLE_OPERATOR,
        matrix={"member_ops": ["view"], "commerce": ["view"]}, at="t2"
    )
    payload = svc.roles_payload()
    op = next(r for r in payload["roles"] if r["key"] == "operator")
    assert op["matrix"]["commerce"] == ["view"]
    # 列表里该 operator 的可访问 tab 含 commerce
    entry = next(e for e in svc.list_admin_user_ids() if e["user_id"] == "u-op")
    assert "commerce" in entry["accessible_tabs"]


# ---- P2 防御纵深 ----

def test_non_super_admin_actor_cannot_mutate(svc):
    """service 层自校验 actor：operator/admin 都不能管理权限（纵深，独立于 HTTP gate）。"""
    svc.set_admin_role(actor="env-super", user_id="u-op", role=rbac.ROLE_OPERATOR, at="t1")
    svc.set_admin_role(actor="env-super", user_id="u-ad", role=rbac.ROLE_ADMIN, at="t1")
    with pytest.raises(PermissionError):
        svc.set_admin_role(actor="u-op", user_id="u-new", role=rbac.ROLE_ANALYST)
    with pytest.raises(PermissionError):
        svc.set_role_permissions(actor="u-ad", role=rbac.ROLE_OPERATOR, matrix={})
    with pytest.raises(PermissionError):
        svc.set_user_permission_overrides(actor="u-op", user_id="u-op", overrides={"commerce": ["view"]})
    with pytest.raises(PermissionError):
        svc.remove_admin_user("u-op", actor="u-ad")


def test_blank_actor_rejected(svc):
    with pytest.raises(PermissionError):
        svc.set_admin_role(actor="", user_id="u-x", role=rbac.ROLE_ADMIN)


def test_corrupt_persisted_role_fails_closed(svc, tmp_path):
    """持久化中出现非法 role 时 fail-closed：视为非管理员、不回落 admin、列表跳过。"""
    import json

    (tmp_path / "bi_admins.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "admins": {"u-bad": {"role": "ghost"}},
                "audit": [],
                "role_permissions": {},
            }
        ),
        encoding="utf-8",
    )
    assert svc.get_admin_role("u-bad") is None
    assert svc.is_admin_user("u-bad") is False
    assert svc.can_access("u-bad", "overview", "view") is False
    assert all(e["user_id"] != "u-bad" for e in svc.list_admin_user_ids())
