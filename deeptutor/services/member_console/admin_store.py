"""BI 管理员名单的运行时可编辑持久化存储。

Authority 收敛：is_admin = env 引导名单 (DEEPTUTOR_ADMIN_USER_IDS) ∪ 本文件。
- env 名单是 bootstrap/保底，UI 不可移除（防止超管把自己锁死）。
- 本文件是运行时增量，UI 可增删，立即生效，无需重启。
路径：data/user/bi_admins.json，bind-mount 持久化，容器重建不丢。
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()


def _read(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"user_ids": []}
    except (json.JSONDecodeError, OSError):
        logger.warning("bi_admins.json unreadable, treating as empty: %s", path)
        return {"user_ids": []}
    if not isinstance(raw, dict):
        return {"user_ids": []}
    ids = raw.get("user_ids")
    if not isinstance(ids, list):
        return {"user_ids": []}
    return {"user_ids": [str(x).strip() for x in ids if str(x).strip()]}


def load_persisted_admins(path: Path) -> set[str]:
    """运行时增量管理员名单（不含 env 引导名单）。"""
    return set(_read(path)["user_ids"])


def add_persisted_admin(path: Path, user_id: str) -> set[str]:
    normalized = str(user_id or "").strip()
    if not normalized:
        raise ValueError("user_id is required")
    with _LOCK:
        current = _read(path)["user_ids"]
        if normalized not in current:
            current.append(normalized)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"user_ids": current}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return set(current)


def remove_persisted_admin(path: Path, user_id: str) -> set[str]:
    """移除运行时增量管理员。env 引导名单不在此文件，天然无法被移除（防锁死）。"""
    normalized = str(user_id or "").strip()
    with _LOCK:
        current = _read(path)["user_ids"]
        remaining = [x for x in current if x != normalized]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"user_ids": remaining}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return set(remaining)
