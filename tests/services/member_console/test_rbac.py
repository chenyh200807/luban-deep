from __future__ import annotations

from deeptutor.services.member_console import rbac


def test_super_admin_can_everything_and_manage():
    for tab in rbac.TABS:
        for action in rbac.ACTIONS:
            assert rbac.can(rbac.ROLE_SUPER_ADMIN, tab, action)
    assert rbac.can_manage_permissions(rbac.ROLE_SUPER_ADMIN)
    assert rbac.is_full_admin(rbac.ROLE_SUPER_ADMIN)


def test_admin_full_but_cannot_manage_permissions():
    for tab in rbac.TABS:
        for action in rbac.ACTIONS:
            assert rbac.can(rbac.ROLE_ADMIN, tab, action)
    assert not rbac.can_manage_permissions(rbac.ROLE_ADMIN)
    assert rbac.is_full_admin(rbac.ROLE_ADMIN)


def test_operator_scoped_no_high_risk_no_cost():
    # 能在会员运营/反馈写，但不能高危
    assert rbac.can(rbac.ROLE_OPERATOR, "member_ops", "write")
    assert rbac.can(rbac.ROLE_OPERATOR, "feedback", "write")
    assert not rbac.can(rbac.ROLE_OPERATOR, "member_ops", "high_risk")
    # 看不到成本/系统运维/总览
    assert not rbac.can(rbac.ROLE_OPERATOR, "commerce", "view")
    assert not rbac.can(rbac.ROLE_OPERATOR, "ops", "view")
    assert not rbac.can(rbac.ROLE_OPERATOR, "overview", "view")
    assert not rbac.is_full_admin(rbac.ROLE_OPERATOR)
    assert rbac.accessible_tabs(rbac.ROLE_OPERATOR) == ["member_ops", "feedback"]


def test_analyst_read_only_all_tabs():
    for tab in rbac.TABS:
        assert rbac.can(rbac.ROLE_ANALYST, tab, "view")
        assert rbac.can(rbac.ROLE_ANALYST, tab, "export")
        assert not rbac.can(rbac.ROLE_ANALYST, tab, "write")
        assert not rbac.can(rbac.ROLE_ANALYST, tab, "high_risk")
    assert rbac.accessible_tabs(rbac.ROLE_ANALYST) == list(rbac.TABS)


def test_unknown_role_denied():
    assert not rbac.can("ghost", "overview", "view")
    assert not rbac.can(None, "overview", "view")
    assert not rbac.is_full_admin("ghost")
    assert not rbac.can_manage_permissions("ghost")


def test_normalize_and_validate():
    assert rbac.is_valid_role("admin")
    assert not rbac.is_valid_role("nope")
    assert rbac.normalize_role("nope") == rbac.ROLE_ADMIN
    assert rbac.normalize_role("operator") == rbac.ROLE_OPERATOR


def test_roles_payload_shape():
    p = rbac.roles_payload()
    assert [t["key"] for t in p["tabs"]] == list(rbac.TABS)
    assert [a["key"] for a in p["actions"]] == list(rbac.ACTIONS)
    keys = [r["key"] for r in p["roles"]]
    assert keys == list(rbac.ROLE_ORDER)
    super_role = next(r for r in p["roles"] if r["key"] == "super_admin")
    assert super_role["can_manage_permissions"] is True
    assert super_role["matrix"]["commerce"] == list(rbac.ACTIONS)
    operator = next(r for r in p["roles"] if r["key"] == "operator")
    assert operator["matrix"]["member_ops"] == ["view", "export", "write"]
    assert operator["matrix"]["commerce"] == []
