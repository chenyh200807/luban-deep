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
TABS: tuple[str, ...] = ("overview", "member_ops", "commerce", "feedback", "learning_pref", "ops")
ACTIONS: tuple[str, ...] = ("view", "export", "write", "high_risk")

TAB_LABELS = {
    "overview": "经营总览",
    "member_ops": "会员运营",
    "commerce": "商品账务",
    "feedback": "反馈中心",
    # 学习模块偏好驾驶舱（2026-07-21）：产品行为 read model 的聚合看板，非 PII，只读为主。
    "learning_pref": "学习模块偏好",
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
    ROLE_SUPER_ADMIN: "全部 tab + 全部操作 + 管理权限，系统引导超管不可降级/移除。",
    ROLE_ADMIN: "全部 tab + 全部操作（含高危）+ 管理权限，可增删管理员、改角色和编辑权限。",
    ROLE_OPERATOR: "会员运营全量操作（含套餐能力发放/删除等高危操作）+ 反馈中心常规写操作，看不到成本与系统运维。",
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
        "member_ops": set(_ALL_ACTIONS),
        "feedback": set(_NO_HIGH_RISK),
    },
    ROLE_ANALYST: {tab: set(_READ_ONLY) for tab in TABS},
}

# 只有这些角色能管理权限（增删管理员、改角色、编辑权限）。
_MANAGE_PERMISSION_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN}
# is_admin（兼容旧的布尔 admin 门）= 这些角色。
_FULL_ADMIN_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN}
# 恒全权、不可被编辑/覆盖的角色（防止超管把自己锁死）。
LOCKED_ROLES = {ROLE_SUPER_ADMIN}
# 代码默认权限矩阵（首次/未编辑时的初始值）。
DEFAULT_ROLE_PERMISSIONS = ROLE_PERMISSIONS


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
    """单个角色的【默认】权限矩阵（tab -> 有序 action 列表）。"""
    perms = ROLE_PERMISSIONS.get(role, {})
    return {tab: [a for a in ACTIONS if a in perms.get(tab, set())] for tab in TABS}


def is_role_editable(role: str | None) -> bool:
    """角色权限是否可被超管编辑。super_admin 恒全权,不可编辑(防锁死)。"""
    r = str(role or "")
    return r in ROLE_PERMISSIONS and r not in LOCKED_ROLES


def normalize_matrix(matrix: dict[str, Any] | None) -> dict[str, list[str]]:
    """把任意输入规范化成合法的 {tab: [有序合法 action]}（丢弃未知 tab/action）。"""
    matrix = matrix or {}
    out: dict[str, list[str]] = {}
    for tab in TABS:
        raw = matrix.get(tab) or []
        chosen = set(str(a) for a in raw) if isinstance(raw, (list, tuple, set)) else set()
        out[tab] = [a for a in ACTIONS if a in chosen]
    return out


def resolve_role_permissions(
    role: str | None, stored: dict[str, Any] | None = None
) -> dict[str, set[str]]:
    """角色的生效权限：locked 角色恒全权；否则 已编辑(stored) ?? 代码默认。"""
    r = str(role or "")
    if r in LOCKED_ROLES:
        return {tab: set(_ALL_ACTIONS) for tab in TABS}
    if stored and isinstance(stored.get(r), dict):
        norm = normalize_matrix(stored[r])
        return {tab: set(norm.get(tab, [])) for tab in TABS}
    base = ROLE_PERMISSIONS.get(r, {})
    return {tab: set(base.get(tab, set())) for tab in TABS}


def resolve_effective_permissions(
    role: str | None,
    stored_role_perms: dict[str, Any] | None = None,
    user_overrides: dict[str, Any] | None = None,
) -> dict[str, set[str]]:
    """某个管理员的最终生效权限 = 角色权限(可能被编辑) 叠加 per-user 覆盖。

    locked 角色(super_admin)忽略一切覆盖,恒全权。per-user override 按 tab 整列覆盖。
    """
    r = str(role or "")
    base = resolve_role_permissions(r, stored_role_perms)
    if r in LOCKED_ROLES or not user_overrides:
        return base
    norm = normalize_matrix(user_overrides)
    for tab in TABS:
        if tab in (user_overrides or {}):
            base[tab] = set(norm.get(tab, []))
    return base


def can_resolved(effective: dict[str, set[str]], tab: str, action: str) -> bool:
    return action in effective.get(tab, set())


def accessible_tabs_resolved(effective: dict[str, set[str]]) -> list[str]:
    return [tab for tab in TABS if "view" in effective.get(tab, set())]


def matrix_to_lists(effective: dict[str, set[str]]) -> dict[str, list[str]]:
    """{tab: set} → {tab: 有序 list}，给 JSON/前端。"""
    return {tab: [a for a in ACTIONS if a in effective.get(tab, set())] for tab in TABS}


def roles_payload(stored_role_perms: dict[str, Any] | None = None) -> dict[str, Any]:
    """全部角色定义 + 【生效】权限矩阵(含已编辑) + 维度标签 + 可编辑标记。"""
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
                "editable": is_role_editable(role),
                "matrix": matrix_to_lists(resolve_role_permissions(role, stored_role_perms)),
                "default_matrix": role_matrix(role),
            }
            for role in ROLE_ORDER
        ],
    }
