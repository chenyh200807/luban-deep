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


# ---- 可编辑角色权限 + per-user 覆盖 ----

def test_locked_super_admin_not_editable():
    assert not rbac.is_role_editable(rbac.ROLE_SUPER_ADMIN)
    assert rbac.is_role_editable(rbac.ROLE_OPERATOR)
    assert rbac.is_role_editable(rbac.ROLE_ANALYST)


def test_resolve_role_permissions_uses_stored_over_default():
    # 超管把 operator 改成能看成本(commerce view)
    stored = {"operator": {"member_ops": ["view", "write"], "commerce": ["view"]}}
    perms = rbac.resolve_role_permissions("operator", stored)
    assert "view" in perms["commerce"]
    assert perms["member_ops"] == {"view", "write"}
    # feedback 不在 stored → 空(整列覆盖)
    assert perms["feedback"] == set()


def test_resolve_role_falls_back_to_default_when_no_stored():
    perms = rbac.resolve_role_permissions("operator", None)
    assert perms["member_ops"] == {"view", "export", "write"}
    assert perms["commerce"] == set()


def test_locked_role_ignores_stored():
    stored = {"super_admin": {"overview": []}}  # 试图阉割超管
    perms = rbac.resolve_role_permissions("super_admin", stored)
    assert perms["overview"] == set(rbac.ACTIONS)  # 仍全权


def test_per_user_override_overrides_role():
    # operator 默认看不到 commerce；给某人单独开 commerce view
    eff = rbac.resolve_effective_permissions(
        "operator", None, {"commerce": ["view", "export"]}
    )
    assert eff["commerce"] == {"view", "export"}
    # 未覆盖的 tab 保持角色默认
    assert eff["member_ops"] == {"view", "export", "write"}


def test_per_user_override_can_revoke():
    # 给 analyst 某人收掉 ops 的 export(只剩 view)
    eff = rbac.resolve_effective_permissions("analyst", None, {"ops": ["view"]})
    assert eff["ops"] == {"view"}
    assert eff["overview"] == {"view", "export"}  # 其他 tab 角色默认


def test_locked_super_admin_ignores_user_override():
    eff = rbac.resolve_effective_permissions("super_admin", None, {"commerce": []})
    assert eff["commerce"] == set(rbac.ACTIONS)


def test_effective_stacks_role_edit_and_user_override():
    stored = {"operator": {"commerce": ["view"]}}  # 角色级:operator 加 commerce view
    eff = rbac.resolve_effective_permissions(
        "operator", stored, {"commerce": ["view", "export"]}  # 个人级:再加 export
    )
    assert eff["commerce"] == {"view", "export"}


def test_normalize_matrix_drops_unknown():
    norm = rbac.normalize_matrix(
        {"commerce": ["view", "hack"], "ghost_tab": ["view"], "ops": ["high_risk"]}
    )
    assert norm["commerce"] == ["view"]
    assert "ghost_tab" not in norm
    assert norm["ops"] == ["high_risk"]


def test_roles_payload_reflects_stored_edits():
    stored = {"operator": {"commerce": ["view"]}}
    p = rbac.roles_payload(stored)
    operator = next(r for r in p["roles"] if r["key"] == "operator")
    assert operator["editable"] is True
    assert operator["matrix"]["commerce"] == ["view"]
    assert operator["default_matrix"]["commerce"] == []  # 默认仍空
    super_role = next(r for r in p["roles"] if r["key"] == "super_admin")
    assert super_role["editable"] is False
