from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import bcrypt

logger = logging.getLogger(__name__)

_PASSWORD_MAX_LENGTH = 128
_CN_MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")
_STORE_LOCK = Lock()


def _default_users_file() -> Path | None:
    candidates = [
        Path("/app/data/user/external_auth/users.json"),
        Path("/root/luban/.storage/users.json"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _default_sessions_file() -> Path | None:
    candidates = [
        Path("/app/data/user/external_auth/sessions.json"),
        Path("/root/luban/.storage/sessions.json"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _env_path(name: str, default: Path | None) -> Path | None:
    raw = str(os.getenv(name) or "").strip()
    if raw:
        return Path(raw)
    return default


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _resolve_users_file_for_write() -> Path:
    path = _env_path("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", _default_users_file())
    if path is None:
        path = Path("/app/data/user/external_auth/users.json")
    _ensure_parent(path)
    return path


def _resolve_sessions_file_for_write() -> Path | None:
    path = _env_path("DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE", _default_sessions_file())
    if path is None:
        return None
    _ensure_parent(path)
    return path


def get_external_auth_users_file() -> Path | None:
    path = _env_path("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", _default_users_file())
    if path is not None and path.exists():
        return path
    return None


def get_external_auth_sessions_file() -> Path | None:
    path = _env_path("DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE", _default_sessions_file())
    if path is not None and path.exists():
        return path
    return None


def _load_json_mapping(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load external auth store from %s: %s", path, exc)
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_json_mapping(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent(path)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def load_external_auth_users() -> dict[str, dict[str, Any]]:
    payload = _load_json_mapping(get_external_auth_users_file())
    return {
        str(username): user_data
        for username, user_data in payload.items()
        if isinstance(user_data, dict)
    }


def load_external_auth_sessions() -> dict[str, dict[str, Any]]:
    payload = _load_json_mapping(get_external_auth_sessions_file())
    return {
        str(token): session_data
        for token, session_data in payload.items()
        if isinstance(session_data, dict)
    }


def normalize_external_phone(phone: str) -> str:
    raw = (phone or "").strip()
    if not raw:
        raise ValueError("手机号不能为空")
    normalized = re.sub(r"[\s\-()]", "", raw)
    if normalized.startswith("+86"):
        local = normalized[3:]
    elif normalized.startswith("86") and len(normalized) == 13:
        local = normalized[2:]
    else:
        local = normalized
    if not _CN_MOBILE_RE.fullmatch(local):
        raise ValueError("手机号格式错误，请输入中国大陆 11 位手机号")
    return f"+86{local}"


def _normalize_username(username: str) -> str:
    value = str(username or "").strip()
    if len(value) < 2:
        raise ValueError("用户名至少需要 2 个字符")
    if len(value) > 50:
        raise ValueError("用户名不能超过 50 个字符")
    return value


def _validate_password(password: str) -> None:
    if len(password) > _PASSWORD_MAX_LENGTH:
        raise ValueError(f"密码不能超过 {_PASSWORD_MAX_LENGTH} 个字符")
    if len(password) < 6:
        raise ValueError("密码至少需要 6 个字符")
    if not any(ch.isdigit() for ch in password):
        raise ValueError("密码必须包含至少一个数字")
    if not any(ch.islower() for ch in password):
        raise ValueError("密码必须包含至少一个小写字母")
    if not any(ch.isupper() for ch in password):
        raise ValueError("密码必须包含至少一个大写字母")


def _pre_hash(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(_pre_hash(password), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    start_time = time.time()
    min_verify_time = 0.1
    result = False
    try:
        result = bcrypt.checkpw(_pre_hash(plain_password), hashed_password.encode("utf-8"))
    except Exception:
        result = False
    elapsed = time.time() - start_time
    if elapsed < min_verify_time:
        time.sleep(min_verify_time - elapsed)
    return result


def _merge_user(username: str, user_data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(user_data)
    merged["username"] = username
    return merged


def get_external_auth_user(username: str) -> dict[str, Any] | None:
    normalized = str(username or "").strip()
    if not normalized:
        return None
    user = load_external_auth_users().get(normalized)
    if not isinstance(user, dict):
        return None
    return _merge_user(normalized, user)


def get_external_auth_user_by_phone(phone: str) -> dict[str, Any] | None:
    normalized_phone = normalize_external_phone(phone)
    for username, user_data in load_external_auth_users().items():
        if normalize_external_phone(str(user_data.get("phone") or "")) == normalized_phone:
            return _merge_user(username, user_data)
    return None


def _normalize_existing_phone(value: str) -> str:
    try:
        return normalize_external_phone(value)
    except ValueError:
        return ""


def verify_external_auth_user(username: str, password: str) -> dict[str, Any] | None:
    normalized_username = str(username or "").strip()
    if not normalized_username:
        return None
    if len(str(password or "")) > _PASSWORD_MAX_LENGTH:
        return None
    user = get_external_auth_user(normalized_username)
    if not user:
        return None
    password_hash = str(user.get("password_hash") or "").strip()
    if not password_hash:
        return None
    if not _verify_password(str(password or ""), password_hash):
        return None
    return user


def create_external_auth_user(
    username: str,
    password: str,
    *,
    phone: str | None = None,
    security_question: str | None = None,
    security_answer_hash: str | None = None,
) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    _validate_password(password)
    normalized_phone = normalize_external_phone(phone) if phone else ""
    users_file = _resolve_users_file_for_write()

    with _STORE_LOCK:
        users = _load_json_mapping(users_file)
        if normalized_username in users:
            raise ValueError("用户名已存在")
        if normalized_phone:
            for existing_username, existing_user in users.items():
                if not isinstance(existing_user, dict):
                    continue
                if _normalize_existing_phone(str(existing_user.get("phone") or "")) == normalized_phone:
                    raise ValueError("该手机号已被注册，请更换手机号或直接登录。")
        payload: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "username": normalized_username,
            "password_hash": _hash_password(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if normalized_phone:
            payload["phone"] = normalized_phone
        if security_question:
            payload["security_question"] = str(security_question).strip()[:64]
        if security_answer_hash:
            payload["security_answer_hash"] = str(security_answer_hash).strip()
        users[normalized_username] = payload
        _write_json_mapping(users_file, users)

    return _merge_user(normalized_username, payload)


def _generate_auto_password() -> str:
    return "Aa" + secrets.token_hex(8) + "9"


def ensure_external_auth_user_for_phone(phone: str) -> dict[str, Any]:
    normalized_phone = normalize_external_phone(phone)
    users_file = _resolve_users_file_for_write()

    with _STORE_LOCK:
        users = _load_json_mapping(users_file)
        for username, user_data in users.items():
            if not isinstance(user_data, dict):
                continue
            if _normalize_existing_phone(str(user_data.get("phone") or "")) == normalized_phone:
                return _merge_user(username, user_data)

        base_username = f"user_{normalized_phone[-4:]}"
        candidate = base_username
        while candidate in users:
            candidate = f"{base_username}_{secrets.token_hex(2)}"
        payload = {
            "id": str(uuid.uuid4()),
            "username": candidate,
            "password_hash": _hash_password(_generate_auto_password()),
            "phone": normalized_phone,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        users[candidate] = payload
        _write_json_mapping(users_file, users)

    return _merge_user(candidate, payload)


def change_external_auth_password(username: str, old_password: str, new_password: str) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    _validate_password(new_password)
    users_file = _resolve_users_file_for_write()

    with _STORE_LOCK:
        users = _load_json_mapping(users_file)
        user = users.get(normalized_username)
        if not isinstance(user, dict):
            raise ValueError("用户名或密码错误")
        password_hash = str(user.get("password_hash") or "").strip()
        if not password_hash or not _verify_password(old_password, password_hash):
            raise ValueError("用户名或密码错误")
        user["password_hash"] = _hash_password(new_password)
        user["updated_at"] = datetime.now(timezone.utc).isoformat()
        users[normalized_username] = user
        _write_json_mapping(users_file, users)
    deleted = delete_external_auth_sessions(str(user.get("id") or ""))
    return {"success": True, "sessions_invalidated": deleted}


def reset_external_auth_password_by_phone(username: str, phone: str, new_password: str) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    normalized_phone = normalize_external_phone(phone)
    _validate_password(new_password)
    users_file = _resolve_users_file_for_write()

    with _STORE_LOCK:
        users = _load_json_mapping(users_file)
        user = users.get(normalized_username)
        if not isinstance(user, dict):
            raise ValueError("账号或手机号不匹配")
        if _normalize_existing_phone(str(user.get("phone") or "")) != normalized_phone:
            raise ValueError("账号或手机号不匹配")
        user["password_hash"] = _hash_password(new_password)
        user["updated_at"] = datetime.now(timezone.utc).isoformat()
        users[normalized_username] = user
        _write_json_mapping(users_file, users)
    deleted = delete_external_auth_sessions(str(user.get("id") or ""))
    return {"success": True, "sessions_invalidated": deleted}


def delete_external_auth_sessions(user_id: str) -> int:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return 0
    sessions_file = _resolve_sessions_file_for_write()
    if sessions_file is None:
        return 0

    with _STORE_LOCK:
        sessions = _load_json_mapping(sessions_file)
        if not isinstance(sessions, dict):
            return 0
        retained = {}
        deleted = 0
        for token, session in sessions.items():
            if isinstance(session, dict) and str(session.get("id") or "").strip() == normalized_user_id:
                deleted += 1
                continue
            retained[str(token)] = session
        if deleted:
            _write_json_mapping(sessions_file, retained)
        return deleted
