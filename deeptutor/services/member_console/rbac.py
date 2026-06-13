"""BI 管理员 RBAC（基于角色的访问控制）权限模型。

世界顶尖 BI 管理后台的权限地基（用户 2026-06-13 拍板：预定义角色 + tab/操作权限矩阵）。

设计：
- 5 个 BI tab × 4 类操作 构成权限矩阵。
- 4 个预定义角色，每个角色对每个 tab 有一组允许的操作。
- 只有 super_admin 能管理权限（分配角色、增删管理员）。
- env 引导管理员（DEEPTUTOR_ADMIN_USER_IDS）恒为 super_admin 且不可降级/移除（防锁死）。

单一 authority：本模块是 BI 权限的唯一定义来源；端点与前端都从这里派生，
不得各自硬编码权限判断。
"""
from __future__ import annotations

from typing import Any

# ---- 权限维度 ----
TABS: tuple[str, ...] = ("overview", "member_ops", "commerce", "feedback", "ops")
ACTIONS: tuple[str, ...] = ("view", "export", "write", "high_risk")

TAB_LABELS = {
    "overview": "经营总览",
    "member_ops": "会员运营",
    "commerce": "商品账务",
    "feedback": "反馈中心",
    "ops": "系统运维",
}
ACTION_LABELS = {
    "view": "查看",
    "export": "导出",
    "write": "写操作",
    "high_risk": "高危操作",
}

# ---- 角色 ----
ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_ANALYST = "analyst"

ROLE_ORDER: tuple[str, ...] = (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_OPERATOR, ROLE_ANALYST)

ROLE_LABELS = {
    ROLE_SUPER_ADMIN: "超级管理员",
    ROLE_ADMIN: "管理员",
    ROLE_OPERATOR: "运营",
    ROLE_ANALYST: "分析师",
}
ROLE_DESCRIPTIONS = {
    ROLE_SUPER_ADMIN: "全部 tab + 全部操作 + 管理权限（唯一能增删管理员、改角色）。",
    ROLE_ADMIN: "全部 tab + 全部操作（含高危），但不能管理权限。",
    ROLE_OPERATOR: "会员运营 + 反馈中心，可查看/导出/写操作，不能高危操作，看不到成本与系统运维。",
    ROLE_ANALYST: "全部 tab 只读（查看 + 导出），不能任何写操作。",
}

_ALL_ACTIONS = set(ACTIONS)
_READ_ONLY = {"view", "export"}
_NO_HIGH_RISK = {"view", "export", "write"}

# 权限矩阵：role -> {tab -> set(actions)}。缺省 tab = 无任何权限。
ROLE_PERMISSIONS: dict[str, dict[str, set[str]]] = {
    ROLE_SUPER_ADMIN: {tab: set(_ALL_ACTIONS) for tab in TABS},
    ROLE_ADMIN: {tab: set(_ALL_ACTIONS) for tab in TABS},
    ROLE_OPERATOR: {
        "member_ops": set(_NO_HIGH_RISK),
        "feedback": set(_NO_HIGH_RISK),
    },
    ROLE_ANALYST: {tab: set(_READ_ONLY) for tab in TABS},
}

# 只有这些角色能管理权限（增删管理员、改角色）。
_MANAGE_PERMISSION_ROLES = {ROLE_SUPER_ADMIN}
# is_admin（兼容旧的布尔 admin 门）= 这些角色。
_FULL_ADMIN_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN}


def is_valid_role(role: str | None) -> bool:
    return str(role or "") in ROLE_PERMISSIONS


def normalize_role(role: str | None, default: str = ROLE_ADMIN) -> str:
    candidate = str(role or "").strip()
    return candidate if candidate in ROLE_PERMISSIONS else default


def can(role: str | None, tab: str, action: str) -> bool:
    """该角色在某 tab 是否允许某操作。"""
    perms = ROLE_PERMISSIONS.get(str(role or ""))
    if not perms:
        return False
    return action in perms.get(tab, set())


def can_manage_permissions(role: str | None) -> bool:
    return str(role or "") in _MANAGE_PERMISSION_ROLES


def is_full_admin(role: str | None) -> bool:
    """兼容旧 require_bi_admin 布尔门：super_admin / admin 视为完整管理员。"""
    return str(role or "") in _FULL_ADMIN_ROLES


def accessible_tabs(role: str | None) -> list[str]:
    """该角色至少能 view 的 tab（前端导航门控用），保持 TABS 顺序。"""
    return [tab for tab in TABS if can(role, tab, "view")]


def role_matrix(role: str) -> dict[str, list[str]]:
    """单个角色的权限矩阵（tab -> 有序 action 列表），给 UI 渲染。"""
    perms = ROLE_PERMISSIONS.get(role, {})
    return {tab: [a for a in ACTIONS if a in perms.get(tab, set())] for tab in TABS}


def roles_payload() -> dict[str, Any]:
    """全部角色定义 + 权限矩阵 + 维度标签，供前端一次性渲染权限管理界面。"""
    return {
        "tabs": [{"key": t, "label": TAB_LABELS[t]} for t in TABS],
        "actions": [{"key": a, "label": ACTION_LABELS[a]} for a in ACTIONS],
        "roles": [
            {
                "key": role,
                "label": ROLE_LABELS[role],
                "description": ROLE_DESCRIPTIONS[role],
                "can_manage_permissions": can_manage_permissions(role),
                "is_full_admin": is_full_admin(role),
                "matrix": role_matrix(role),
            }
            for role in ROLE_ORDER
        ],
    }
