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
        svc.set_admin_role(actor="x", user_id="env-super", role=rbac.ROLE_ANALYST)
    with pytest.raises(ValueError):
        svc.remove_admin_user("env-super", actor="x")
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
