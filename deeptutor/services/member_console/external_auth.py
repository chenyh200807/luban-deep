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

try:  # pragma: no cover - 平台差异
    import fcntl
except ImportError:  # Windows 无 fcntl:降级为纯进程内互斥
    fcntl = None  # type: ignore[assignment]

import bcrypt
from deeptutor.services.runtime_env import env_flag, is_production_environment

logger = logging.getLogger(__name__)

_PASSWORD_MAX_LENGTH = 128
_CN_MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")
_EVAL_RUNNER_ACCOUNT_KIND = "eval_runner"
_EVAL_RUNNER_ACTOR_TYPE = "machine"
_EVAL_RUNNER_CREATED_BY = "eval_runner"
_EVAL_RUNNER_IDENTITY_METADATA = {
    "account_kind": _EVAL_RUNNER_ACCOUNT_KIND,
    "actor_type": _EVAL_RUNNER_ACTOR_TYPE,
    "created_by": _EVAL_RUNNER_CREATED_BY,
    "is_internal_test": True,
}
_EVAL_RUNNER_USERNAME_MARKERS = (
    "eval",
    "qa_",
    "qa-",
    "qa.",
    "casefix",
    "codex",
    "probe",
    "audit",
    "prelaunch",
    "preflight",
    "release",
    "smoke",
    "soak",
    "debug",
    "mock",
    "dummy",
    "fake",
    "compiled_shadow",
    "practiceanchor",
    "practice_anchor",
    "army_",
    "synthetic",
    "test_",
    "_test",
    "test-",
    "-test",
    "测试",
)
# 身份 metadata 的**唯一字段权威**:写侧(`normalize_identity_metadata`)与读侧
# (`service._EXPLICIT_IDENTITY_METADATA_FIELDS`)都从这张表派生。
#
# 为什么必须是一张表:2026-07-24 `a7ebaab38` 往写侧加了 reg_channel/reg_scene,
# 2026-07-26 `0a0387983`(跨 worker 锁重构)把相邻的那段又删掉了,而读侧的字段表
# 毫不知情——注册渠道归因从此静默落 None,BI 侧 `(item.get("identity_metadata")
# or {}).get("reg_channel")` 是 fail-open 的,空桶不报错,UI 全绿。两张表分裂
# 就是那次静默丢失的结构性成因;合成一张表让"读侧认得、写侧不认"不再可能发生。
#
# 三种归一化模式:
#   "marker" — 机器身份标记,做 lower + 连字符→下划线 的规整(便于跨源比对)。
#   "bool"   — 真值标记。
#   "token"  — **归因键,原样保真**:只做安全字符白名单过滤,绝不改大小写/连字符。
#              这类值是与外部投放系统对账的键,静默规整会把"丢失病"换成"改名病"
#              (`Campaign-7` → `campaign_7` 在 BI 里就对不上投放侧配置)。
#   "digits" — 只保留数字(微信场景值)。
_IDENTITY_METADATA_FIELD_MODES: tuple[tuple[str, str], ...] = (
    ("account_kind", "marker"),
    ("member_account_kind", "marker"),
    ("actor_type", "marker"),
    ("created_by", "marker"),
    ("runner", "marker"),
    ("agent_tool", "marker"),
    ("eval_run_id", "marker"),
    ("phone_binding_method", "marker"),
    ("is_internal_test", "bool"),
    ("is_test_account", "bool"),
    ("reg_channel", "token"),
    ("reg_scene", "digits"),
)
IDENTITY_METADATA_FIELDS: tuple[str, ...] = tuple(
    field for field, _mode in _IDENTITY_METADATA_FIELD_MODES
)
_IDENTITY_METADATA_TOKEN_RE = re.compile(r"[^0-9A-Za-z_\-]")
_IDENTITY_METADATA_MARKER_MAX = 64
_IDENTITY_METADATA_TOKEN_MAX = 64
_IDENTITY_METADATA_DIGITS_MAX = 8
_PRIMARY_USERS_FILE = Path("/app/data/user/external_auth/users.json")
_LEGACY_USERS_FILE = Path("/root/luban/.storage/users.json")
_PRIMARY_SESSIONS_FILE = Path("/app/data/user/external_auth/sessions.json")
_LEGACY_SESSIONS_FILE = Path("/root/luban/.storage/sessions.json")


def _allow_legacy_external_auth_default() -> bool:
    if not is_production_environment():
        return True
    return env_flag("DEEPTUTOR_EXTERNAL_AUTH_ALLOW_LEGACY_DEFAULT", default=False)


def _store_lock_path() -> Path:
    """external_auth 存储的跨进程锁文件路径。

    路径必须复用 writer 的有效 users store 决策：显式 env → 已存在且允许的
    primary/legacy default → 首次创建的 primary。否则 writer 落 legacy、锁却落
    primary 时，锁目录权限会让本可写的 legacy store 整体不可用。

    ``_resolve_users_file_for_write`` 在文件尚不存在时仍确定性返回 primary，因此
    首次创建不依赖 exists；所有 worker 走同一个 resolver，不另造路径 authority。
    """
    return _resolve_users_file_for_write().with_name(".external_auth.lock")


class _CrossProcessStoreLock:
    """进程内 + 跨进程复合互斥,替代原来的裸 `threading.Lock()`。

    **为什么必须改**:生产 `UVICORN_WORKERS=2`(2026-07-26 实测容器 env),
    `threading.Lock` 只在单进程内互斥。users.json / sessions.json 的
    read-modify-write 在两个 worker 间**结构上无保护**,交错如下会静默丢绑定:

        P1 load {A}          P2 load {A}
        P1 write {A,B}       P2 write {A,C}   ← B 丢失,且无任何错误

    单次 `_write_json_mapping` 是原子的(tempfile + replace),但原子写救不了
    跨进程的 RMW 序列——这是"看起来有锁其实没锁"的典型 dormant authority。

    **两层锁各司其职**:
      · `threading.Lock` — 同进程多线程(FastAPI anyio 池)互斥。**必须先拿**:
        flock 对同进程不同 fd 不可重入,先串行化同进程可避免自锁。
      · `flock(LOCK_EX)` — 跨 worker 进程互斥。这是本次修复的实质。

    **非重入是刻意的**:8 个持锁函数经 AST 核验互不在锁内调用
    (5 处 `delete_external_auth_sessions` 调用全在 `with` 块之外),
    所以不需要 RLock 语义。若将来新增嵌套调用会立即死锁 —— 这是**期望行为**,
    比静默丢更新好,且 `tests/services/member_console/test_external_auth_cross_process_lock.py`
    会钉住这个不变量。
    """

    def __init__(self) -> None:
        self._thread_lock = Lock()
        self._handle: Any = None

    def __enter__(self) -> "_CrossProcessStoreLock":
        self._thread_lock.acquire()
        try:
            path = _store_lock_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a+", encoding="utf-8")
            try:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except BaseException:
                handle.close()
                raise
            self._handle = handle
        except BaseException:
            self._thread_lock.release()
            raise
        return self

    def __exit__(self, *_exc: Any) -> bool:
        handle, self._handle = self._handle, None
        try:
            if handle is not None:
                try:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()
        finally:
            self._thread_lock.release()
        return False


_STORE_LOCK = _CrossProcessStoreLock()


def _default_users_file() -> Path | None:
    candidates = [_PRIMARY_USERS_FILE]
    if _allow_legacy_external_auth_default():
        candidates.append(_LEGACY_USERS_FILE)
    for path in candidates:
        if path.exists():
            return path
    return None


def _default_sessions_file() -> Path | None:
    candidates = [_PRIMARY_SESSIONS_FILE]
    if _allow_legacy_external_auth_default():
        candidates.append(_LEGACY_SESSIONS_FILE)
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
    path = _env_path("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", None)
    if path is None:
        path = _default_users_file()
    if path is None:
        path = _PRIMARY_USERS_FILE
    _ensure_parent(path)
    return path


def _resolve_sessions_file_for_write() -> Path | None:
    path = _env_path("DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE", None)
    if path is None:
        path = _default_sessions_file()
    if path is None:
        return None
    _ensure_parent(path)
    return path


def get_external_auth_users_file() -> Path | None:
    path = _env_path("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", None)
    if path is None:
        path = _default_users_file()
    if path is not None and path.exists():
        return path
    return None


def get_external_auth_sessions_file() -> Path | None:
    path = _env_path("DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE", None)
    if path is None:
        path = _default_sessions_file()
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


def _normalize_optional_user_id(user_id: str | None) -> str:
    value = str(user_id or "").strip()
    if not value:
        return ""
    try:
        uuid.UUID(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("用户身份格式不正确") from exc
    return value


def normalize_identity_metadata(identity_metadata: dict[str, Any] | None) -> dict[str, Any]:
    """身份 metadata 的唯一归一化入口,由 `_IDENTITY_METADATA_FIELD_MODES` 驱动。

    调用方(external_auth 的写路径、member_console 的渠道归因构造)共用这一个实现,
    因此不存在"某一侧认得某字段而另一侧把它过滤掉"的可能。
    """
    if not isinstance(identity_metadata, dict):
        return {}
    normalized: dict[str, Any] = {}
    for field, mode in _IDENTITY_METADATA_FIELD_MODES:
        raw = identity_metadata.get(field)
        if mode == "bool":
            if isinstance(raw, bool):
                normalized[field] = raw
            elif str(raw or "").strip().lower() in {"1", "true", "yes", "y"}:
                normalized[field] = True
            continue
        text = str(raw or "").strip()
        if mode == "marker":
            value = text.lower().replace("-", "_")[:_IDENTITY_METADATA_MARKER_MAX]
        elif mode == "token":
            # 大小写与连字符原样保真——归因键要跟外部投放系统对账。
            value = _IDENTITY_METADATA_TOKEN_RE.sub("", text)[:_IDENTITY_METADATA_TOKEN_MAX]
        else:
            value = "".join(ch for ch in text if ch.isdigit())[:_IDENTITY_METADATA_DIGITS_MAX]
        if value:
            normalized[field] = value
    return normalized


def _eval_runner_identity_from_username(username: str) -> dict[str, Any]:
    normalized = str(username or "").strip().lower()
    if not normalized:
        return {}
    if not any(marker in normalized for marker in _EVAL_RUNNER_USERNAME_MARKERS):
        return {}
    metadata = dict(_EVAL_RUNNER_IDENTITY_METADATA)
    if "claude" in normalized:
        metadata.update({"runner": "claude_code", "agent_tool": "claude_code"})
    elif "codex" in normalized:
        metadata.update({"runner": "codex", "agent_tool": "codex"})
    return metadata


def _identity_metadata_for_user(
    username: str,
    identity_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit = normalize_identity_metadata(identity_metadata)
    detected = _eval_runner_identity_from_username(username)
    merged = {**explicit, **detected}
    is_eval_runner = bool(detected) or any(
        (
            merged.get("account_kind") == _EVAL_RUNNER_ACCOUNT_KIND,
            merged.get("actor_type") == _EVAL_RUNNER_ACTOR_TYPE,
            merged.get("created_by") == _EVAL_RUNNER_CREATED_BY,
            merged.get("is_internal_test") is True,
            merged.get("is_test_account") is True,
        )
    )
    if is_eval_runner:
        merged.update(_EVAL_RUNNER_IDENTITY_METADATA)
    return merged


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


def validate_external_auth_password(password: str) -> None:
    _validate_password(str(password or ""))


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


def get_external_auth_identity_metadata(user_id: str) -> dict[str, Any]:
    """Return canonical BI identity metadata for an external-auth user id."""

    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return {}
    for username, user_data in load_external_auth_users().items():
        if str(user_data.get("id") or "").strip() != normalized_user_id:
            continue
        return _identity_metadata_for_user(username, user_data)
    return {}


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
    identity_metadata: dict[str, Any] | None = None,
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
        payload.update(_identity_metadata_for_user(normalized_username, identity_metadata))
        if normalized_phone:
            payload["phone"] = normalized_phone
        if security_question:
            payload["security_question"] = str(security_question).strip()[:64]
        if security_answer_hash:
            payload["security_answer_hash"] = str(security_answer_hash).strip()
        users[normalized_username] = payload
        _write_json_mapping(users_file, users)

    return _merge_user(normalized_username, payload)


def ensure_external_auth_user(
    username: str,
    password: str,
    *,
    phone: str | None = None,
    identity_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or refresh a deterministic local QA auth user."""

    normalized_username = _normalize_username(username)
    _validate_password(password)
    normalized_phone = normalize_external_phone(phone) if phone else ""
    users_file = _resolve_users_file_for_write()

    with _STORE_LOCK:
        users = _load_json_mapping(users_file)
        for existing_username, existing_user in users.items():
            if existing_username == normalized_username or not isinstance(existing_user, dict):
                continue
            if normalized_phone and _normalize_existing_phone(str(existing_user.get("phone") or "")) == normalized_phone:
                raise ValueError("该手机号已被注册，请更换手机号或直接登录。")

        now = datetime.now(timezone.utc).isoformat()
        existing = users.get(normalized_username)
        payload = dict(existing) if isinstance(existing, dict) else {}
        payload["id"] = str(payload.get("id") or uuid.uuid4())
        payload["username"] = normalized_username
        payload["password_hash"] = _hash_password(password)
        payload.setdefault("created_at", now)
        payload["updated_at"] = now
        payload.update(_identity_metadata_for_user(normalized_username, identity_metadata))
        if normalized_phone:
            payload["phone"] = normalized_phone
        users[normalized_username] = payload
        _write_json_mapping(users_file, users)

    return _merge_user(normalized_username, payload)


def _generate_auto_password() -> str:
    return "Aa" + secrets.token_hex(8) + "9"


def ensure_external_auth_user_for_phone(
    phone: str,
    *,
    user_id: str | None = None,
    identity_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_phone = normalize_external_phone(phone)
    desired_user_id = _normalize_optional_user_id(user_id)
    users_file = _resolve_users_file_for_write()
    invalidate_user_id = ""
    result: dict[str, Any] | None = None

    with _STORE_LOCK:
        users = _load_json_mapping(users_file)
        if desired_user_id:
            for username, user_data in users.items():
                if not isinstance(user_data, dict):
                    continue
                if str(user_data.get("id") or "").strip() != desired_user_id:
                    continue
                if _normalize_existing_phone(str(user_data.get("phone") or "")) != normalized_phone:
                    raise ValueError("该手机号已被注册，请更换手机号或直接登录。")

        for username, user_data in users.items():
            if not isinstance(user_data, dict):
                continue
            if _normalize_existing_phone(str(user_data.get("phone") or "")) == normalized_phone:
                existing_id = str(user_data.get("id") or "").strip()
                if desired_user_id and existing_id != desired_user_id:
                    if existing_id:
                        invalidate_user_id = existing_id
                    user_data = dict(user_data)
                    user_data["id"] = desired_user_id
                    user_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                    users[username] = user_data
                    _write_json_mapping(users_file, users)
                metadata = _identity_metadata_for_user(str(username), identity_metadata)
                if metadata:
                    user_data = dict(user_data)
                    changed = False
                    for field, value in metadata.items():
                        if user_data.get(field) != value:
                            user_data[field] = value
                            changed = True
                    if changed:
                        user_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                        users[username] = user_data
                        _write_json_mapping(users_file, users)
                result = _merge_user(username, user_data)
                break

        if result is None:
            base_username = f"user_{normalized_phone[-4:]}"
            candidate = base_username
            while candidate in users:
                candidate = f"{base_username}_{secrets.token_hex(2)}"
            payload = {
                "id": desired_user_id or str(uuid.uuid4()),
                "username": candidate,
                "password_hash": _hash_password(_generate_auto_password()),
                "phone": normalized_phone,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            payload.update(_identity_metadata_for_user(candidate, identity_metadata))
            users[candidate] = payload
            _write_json_mapping(users_file, users)
            result = _merge_user(candidate, payload)

    if invalidate_user_id:
        delete_external_auth_sessions(invalidate_user_id)
    if result is None:
        raise RuntimeError("phone-backed external auth bootstrap failed")
    return result


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


def reset_external_auth_password(username: str, new_password: str) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    _validate_password(new_password)
    users_file = _resolve_users_file_for_write()

    with _STORE_LOCK:
        users = _load_json_mapping(users_file)
        user = users.get(normalized_username)
        if not isinstance(user, dict):
            raise ValueError("账号或手机号不匹配")
        user["password_hash"] = _hash_password(new_password)
        user["updated_at"] = datetime.now(timezone.utc).isoformat()
        users[normalized_username] = user
        _write_json_mapping(users_file, users)
    deleted = delete_external_auth_sessions(str(user.get("id") or ""))
    return {"success": True, "sessions_invalidated": deleted}


def delete_external_auth_user(username: str, password: str | None = None) -> dict[str, Any]:
    normalized_username = _normalize_username(username)
    if password is not None and verify_external_auth_user(normalized_username, password) is None:
        raise ValueError("用户名或密码错误")
    users_file = _resolve_users_file_for_write()

    with _STORE_LOCK:
        users = _load_json_mapping(users_file)
        user = users.get(normalized_username)
        if not isinstance(user, dict):
            return {"success": True, "deleted": False, "sessions_invalidated": 0}
        users.pop(normalized_username, None)
        _write_json_mapping(users_file, users)
    deleted = delete_external_auth_sessions(str(user.get("id") or ""))
    return {"success": True, "deleted": True, "sessions_invalidated": deleted}


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
