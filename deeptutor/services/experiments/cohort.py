from __future__ import annotations

import hashlib
import os

_STAGE_PERCENT = {
    "off": 0,
    "internal": 0,
    "cohort_10": 10,
    "cohort_50": 50,
    "cohort_100": 100,
    "sticky_100": 100,
    "on": 100,
}


def current_stage(flag: str) -> str:
    env_name = _stage_env_name(flag)
    raw = str(os.getenv(env_name) or "off").strip().lower()
    return raw if raw in _STAGE_PERCENT else "off"


def is_enabled(flag: str, user_id: str | None = None) -> bool:
    stage = current_stage(flag)
    if stage == "off":
        return False
    base_flag = _base_flag(flag)
    user = str(user_id or "").strip()
    if user and user in _internal_users(base_flag):
        return True
    if stage == "internal":
        return False
    percent = _STAGE_PERCENT.get(stage, 0)
    if percent >= 100:
        return True
    if not user:
        return False
    return _bucket(base_flag, user) < percent


def _stage_env_name(flag: str) -> str:
    base, subgate = _split_flag(flag)
    if not subgate:
        return f"{base}_STAGE"
    return f"{base}_{subgate.upper()}_STAGE"


def _split_flag(flag: str) -> tuple[str, str]:
    raw = str(flag or "").strip().upper().replace("-", "_")
    if "." not in raw:
        return raw, ""
    base, subgate = raw.split(".", 1)
    return base, subgate.replace(".", "_")


def _base_flag(flag: str) -> str:
    return _split_flag(flag)[0]


def _internal_users(base_flag: str) -> set[str]:
    raw = str(os.getenv(f"{base_flag}_INTERNAL_USERS") or "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _bucket(flag: str, user_id: str) -> int:
    digest = hashlib.sha256(f"{flag}:{user_id}".encode("utf-8")).digest()
    return digest[0] % 100


__all__ = ["current_stage", "is_enabled"]
