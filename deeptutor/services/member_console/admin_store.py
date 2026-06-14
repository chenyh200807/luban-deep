"""BI 管理员名单的运行时可编辑持久化存储（RBAC 角色 + 变更审计）。

Authority 收敛：BI 管理员 = env 引导名单 (DEEPTUTOR_ADMIN_USER_IDS, 恒 super_admin)
∪ 本文件（运行时增量，带角色）。
- env 名单是 bootstrap/保底，恒 super_admin，UI 不可移除/降级（防止超管锁死自己）。
- 本文件是运行时增量，super_admin 可在 UI 增删管理员、改角色，立即生效。
路径：data/user/bi_admins.json，bind-mount 持久化，容器重建不丢。

文件格式 v2：
  {"schema_version": 2,
   "admins": {"<user_id>": {"role","display_name","granted_by","granted_at"}},
   "audit": [...legacy...]}
向后兼容 v1：{"user_ids": [...]} 读取时迁移为 role=admin。

审计（防纵深 P2）：权限变更审计写入【独立 append-only 文件】 bi_admin_audit.jsonl
（与 bi_admins.json 同目录），每条一行 JSON，以 O_APPEND 原子追加、永不重写历史。
这杜绝了“恶意 super_admin 通过反复写操作把 bi_admins.json 内嵌 audit 数组截断刷掉
旧记录”的篡改路径。bi_admins.json 内已有的 legacy audit 仍被读取合并（不丢历史）。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_AUDIT_FILENAME = "bi_admin_audit.jsonl"


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
    """写回 admins/role_permissions。

    不再截断/重写 audit：新审计走独立 append-only 文件（见 _append_audit），
    bi_admins.json 内的 legacy audit 原样保留（只读，不增长），避免历史被覆写丢失。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data["audit"] = list(data.get("audit") or [])
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _audit_path(bi_admins_path: Path) -> Path:
    return bi_admins_path.parent / _AUDIT_FILENAME


def _append_audit(bi_admins_path: Path, entry: dict[str, Any]) -> None:
    """以 append-only 方式追加一条审计（O_APPEND 原子追加，绝不重写历史）。"""
    audit_path = _audit_path(bi_admins_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_admins(path: Path) -> dict[str, dict[str, Any]]:
    """运行时增量管理员（不含 env 引导名单）。返回 {user_id: {role, display_name, permission_overrides, ...}}。"""
    return dict(_read(path)["admins"])


def load_audit(path: Path) -> list[dict[str, Any]]:
    """合并 legacy 内嵌审计（旧）+ append-only 文件审计（新），按写入顺序（旧→新）返回。"""
    legacy = list(_read(path)["audit"])
    appended: list[dict[str, Any]] = []
    audit_path = _audit_path(path)
    try:
        text = audit_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    except OSError:
        logger.warning("bi_admin_audit.jsonl unreadable: %s", audit_path)
        text = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            appended.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("skipping corrupt audit line in %s", audit_path)
    return legacy + appended


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
        _write(path, data)
        _append_audit(
            path,
            {
                "ts": at,
                "actor": actor,
                "action": "set_role_permissions",
                "target": normalized,
                "from_role": "",
                "to_role": "",
                "detail": "role_matrix",
            },
        )
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
        _write(path, data)
        _append_audit(
            path,
            {
                "ts": at,
                "actor": actor,
                "action": "set_user_overrides",
                "target": normalized,
                "from_role": str(record.get("role") or ""),
                "to_role": "",
                "detail": ",".join(sorted(overrides.keys())) if overrides else "cleared",
            },
        )
        return dict(data["admins"])


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
        _write(path, data)
        _append_audit(
            path,
            {
                "ts": granted_at,
                "actor": actor,
                "action": "set_role" if prev else "add_admin",
                "target": normalized,
                "from_role": from_role,
                "to_role": role,
                "detail": display_name,
            },
        )
        return dict(data["admins"])


def remove_admin(
    path: Path, user_id: str, *, actor: str = "", removed_at: str = ""
) -> dict[str, dict[str, Any]]:
    normalized = str(user_id or "").strip()
    with _LOCK:
        data = _read(path)
        prev = data["admins"].pop(normalized, None)
        _write(path, data)
        if prev is not None:
            _append_audit(
                path,
                {
                    "ts": removed_at,
                    "actor": actor,
                    "action": "remove_admin",
                    "target": normalized,
                    "from_role": str(prev.get("role") or ""),
                    "to_role": "",
                    "detail": "",
                },
            )
        return dict(data["admins"])
