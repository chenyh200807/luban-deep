"""BI 管理员名单的运行时可编辑持久化存储（RBAC 角色 + 变更审计）。

Authority 收敛：BI 管理员 = env 引导名单 (DEEPTUTOR_ADMIN_USER_IDS, 恒 super_admin)
∪ 本文件（运行时增量，带角色）。
- env 名单是 bootstrap/保底，恒 super_admin，UI 不可移除/降级（防止超管锁死自己）。
- 本文件是运行时增量，super_admin 可在 UI 增删管理员、改角色，立即生效。
路径：data/user/bi_admins.json，bind-mount 持久化，容器重建不丢。

文件格式 v2：
  {"schema_version": 2,
   "admins": {"<user_id>": {"role","display_name","granted_by","granted_at"}},
   "audit": [{"ts","actor","action","target","from_role","to_role","detail"}]}
向后兼容 v1：{"user_ids": [...]} 读取时迁移为 role=admin。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_AUDIT_MAX = 1000


def _empty() -> dict[str, Any]:
    return {"schema_version": 2, "admins": {}, "audit": [], "role_permissions": {}}


def _read(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty()
    except (json.JSONDecodeError, OSError):
        logger.warning("bi_admins.json unreadable, treating as empty: %s", path)
        return _empty()
    if not isinstance(raw, dict):
        return _empty()
    # v1 兼容：{"user_ids": [...]} → admins{uid: role=admin}
    if "admins" not in raw and isinstance(raw.get("user_ids"), list):
        admins = {
            str(uid).strip(): {
                "role": "admin",
                "display_name": "",
                "granted_by": "migrated_from_v1",
                "granted_at": "",
            }
            for uid in raw["user_ids"]
            if str(uid).strip()
        }
        return {"schema_version": 2, "admins": admins, "audit": [], "role_permissions": {}}
    admins = raw.get("admins")
    if not isinstance(admins, dict):
        admins = {}
    audit = raw.get("audit")
    if not isinstance(audit, list):
        audit = []
    role_permissions = raw.get("role_permissions")
    if not isinstance(role_permissions, dict):
        role_permissions = {}
    return {
        "schema_version": 2,
        "admins": admins,
        "audit": audit,
        "role_permissions": role_permissions,
    }


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["audit"] = list(data.get("audit") or [])[-_AUDIT_MAX:]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_admins(path: Path) -> dict[str, dict[str, Any]]:
    """运行时增量管理员（不含 env 引导名单）。返回 {user_id: {role, display_name, permission_overrides, ...}}。"""
    return dict(_read(path)["admins"])


def load_audit(path: Path) -> list[dict[str, Any]]:
    return list(_read(path)["audit"])


def load_role_permissions(path: Path) -> dict[str, Any]:
    """超管编辑过的角色权限矩阵 {role: {tab: [actions]}}（未编辑的角色不在此）。"""
    return dict(_read(path)["role_permissions"])


def set_role_permissions(
    path: Path,
    role: str,
    matrix: dict[str, list[str]],
    *,
    actor: str = "",
    at: str = "",
) -> dict[str, Any]:
    """超管编辑某角色的权限矩阵（整体覆盖该角色），并写审计。"""
    normalized = str(role or "").strip()
    if not normalized:
        raise ValueError("role is required")
    with _LOCK:
        data = _read(path)
        data["role_permissions"][normalized] = matrix
        data["audit"].append(
            {
                "ts": at,
                "actor": actor,
                "action": "set_role_permissions",
                "target": normalized,
                "from_role": "",
                "to_role": "",
                "detail": "role_matrix",
            }
        )
        _write(path, data)
        return dict(data["role_permissions"])


def set_user_overrides(
    path: Path,
    user_id: str,
    overrides: dict[str, list[str]],
    *,
    actor: str = "",
    at: str = "",
) -> dict[str, dict[str, Any]]:
    """给某个已存在的运行时管理员设置 per-user 权限覆盖（精确到人），并写审计。"""
    normalized = str(user_id or "").strip()
    if not normalized:
        raise ValueError("user_id is required")
    with _LOCK:
        data = _read(path)
        record = data["admins"].get(normalized)
        if record is None:
            raise ValueError("该用户不是运行时管理员，无法设置个人权限覆盖")
        record["permission_overrides"] = overrides
        data["audit"].append(
            {
                "ts": at,
                "actor": actor,
                "action": "set_user_overrides",
                "target": normalized,
                "from_role": str(record.get("role") or ""),
                "to_role": "",
                "detail": ",".join(sorted(overrides.keys())) if overrides else "cleared",
            }
        )
        _write(path, data)
        return dict(data["admins"])


def set_admin(
    path: Path,
    user_id: str,
    *,
    role: str,
    display_name: str = "",
    actor: str = "",
    granted_at: str = "",
) -> dict[str, dict[str, Any]]:
    """新增或改角色（运行时增量），并写一条审计。"""
    normalized = str(user_id or "").strip()
    if not normalized:
        raise ValueError("user_id is required")
    with _LOCK:
        data = _read(path)
        prev = data["admins"].get(normalized) or {}
        from_role = str(prev.get("role") or "")
        data["admins"][normalized] = {
            "role": role,
            "display_name": display_name or prev.get("display_name") or "",
            "granted_by": actor or prev.get("granted_by") or "",
            "granted_at": granted_at or prev.get("granted_at") or "",
            "permission_overrides": prev.get("permission_overrides") or {},
        }
        data["audit"].append(
            {
                "ts": granted_at,
                "actor": actor,
                "action": "set_role" if prev else "add_admin",
                "target": normalized,
                "from_role": from_role,
                "to_role": role,
                "detail": display_name,
            }
        )
        _write(path, data)
        return dict(data["admins"])


def remove_admin(
    path: Path, user_id: str, *, actor: str = "", removed_at: str = ""
) -> dict[str, dict[str, Any]]:
    normalized = str(user_id or "").strip()
    with _LOCK:
        data = _read(path)
        prev = data["admins"].pop(normalized, None)
        if prev is not None:
            data["audit"].append(
                {
                    "ts": removed_at,
                    "actor": actor,
                    "action": "remove_admin",
                    "target": normalized,
                    "from_role": str(prev.get("role") or ""),
                    "to_role": "",
                    "detail": "",
                }
            )
        _write(path, data)
        return dict(data["admins"])
