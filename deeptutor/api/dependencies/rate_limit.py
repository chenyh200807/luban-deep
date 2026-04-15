from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable

from fastapi import HTTPException, Request, WebSocket, status

from deeptutor.services.path_service import PathService

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    max_requests: int
    window_seconds: float


@dataclass(slots=True)
class _RateLimitBucket:
    window_start: float
    request_count: int
    window_seconds: float


_RATE_LIMIT_POLICY_OVERRIDES: dict[str, RateLimitPolicy] = {}
_RATE_LIMIT_STATE: dict[str, _RateLimitBucket] = {}
_RATE_LIMIT_LOCK = threading.RLock()
_SQLITE_SCHEMA_LOCK = threading.RLock()
_BACKEND_LOCK = threading.RLock()
_BACKEND_CACHE: tuple[tuple[str, ...], "_BaseRateLimitBackend"] | None = None


class _BaseRateLimitBackend:
    def clear(self) -> None:
        raise NotImplementedError

    def consume(self, scope_name: str, key: str, policy: RateLimitPolicy, now: float) -> int | None:
        raise NotImplementedError


class _MemoryRateLimitBackend(_BaseRateLimitBackend):
    def clear(self) -> None:
        with _RATE_LIMIT_LOCK:
            _RATE_LIMIT_STATE.clear()

    def consume(self, scope_name: str, key: str, policy: RateLimitPolicy, now: float) -> int | None:
        del scope_name
        with _RATE_LIMIT_LOCK:
            bucket = _RATE_LIMIT_STATE.get(key)
            if bucket is None or now - bucket.window_start >= bucket.window_seconds:
                _RATE_LIMIT_STATE[key] = _RateLimitBucket(
                    window_start=now,
                    request_count=1,
                    window_seconds=policy.window_seconds,
                )
                self._prune_expired_entries(now)
                return None

            if bucket.request_count >= policy.max_requests:
                return max(1, math.ceil(bucket.window_seconds - (now - bucket.window_start)))

            bucket.request_count += 1
            return None

    def _prune_expired_entries(self, now: float) -> None:
        if len(_RATE_LIMIT_STATE) <= 1024:
            return

        expired_keys = [
            key
            for key, bucket in _RATE_LIMIT_STATE.items()
            if now - bucket.window_start >= bucket.window_seconds
        ]
        for key in expired_keys:
            _RATE_LIMIT_STATE.pop(key, None)


class _SQLiteRateLimitBackend(_BaseRateLimitBackend):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path.resolve()
        self._ensure_schema()

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM rate_limit_buckets")

    def consume(self, scope_name: str, key: str, policy: RateLimitPolicy, now: float) -> int | None:
        expires_at = now + policy.window_seconds
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT window_start, request_count, window_seconds
                FROM rate_limit_buckets
                WHERE scope_name = ? AND bucket_key = ?
                """,
                (scope_name, key),
            ).fetchone()

            if row is None:
                conn.execute(
                    """
                    INSERT INTO rate_limit_buckets (
                        scope_name, bucket_key, window_start, request_count, window_seconds, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (scope_name, key, now, 1, policy.window_seconds, expires_at),
                )
                self._prune(conn, now)
                conn.commit()
                return None

            window_start = float(row["window_start"])
            request_count = int(row["request_count"])
            bucket_window = float(row["window_seconds"])
            expired = now - window_start >= bucket_window
            policy_changed = not math.isclose(bucket_window, policy.window_seconds, rel_tol=0.0, abs_tol=1e-6)

            if expired or policy_changed:
                conn.execute(
                    """
                    UPDATE rate_limit_buckets
                    SET window_start = ?, request_count = ?, window_seconds = ?, expires_at = ?
                    WHERE scope_name = ? AND bucket_key = ?
                    """,
                    (now, 1, policy.window_seconds, expires_at, scope_name, key),
                )
                self._prune(conn, now)
                conn.commit()
                return None

            if request_count >= policy.max_requests:
                conn.commit()
                return max(1, math.ceil(bucket_window - (now - window_start)))

            conn.execute(
                """
                UPDATE rate_limit_buckets
                SET request_count = request_count + 1, expires_at = ?
                WHERE scope_name = ? AND bucket_key = ?
                """,
                (expires_at, scope_name, key),
            )
            conn.commit()
            return None

    def _ensure_schema(self) -> None:
        with _SQLITE_SCHEMA_LOCK:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rate_limit_buckets (
                        scope_name TEXT NOT NULL,
                        bucket_key TEXT NOT NULL,
                        window_start REAL NOT NULL,
                        request_count INTEGER NOT NULL,
                        window_seconds REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (scope_name, bucket_key)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_rate_limit_buckets_expires_at
                    ON rate_limit_buckets (expires_at)
                    """
                )
                conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _prune(self, conn: sqlite3.Connection, now: float) -> None:
        conn.execute("DELETE FROM rate_limit_buckets WHERE expires_at <= ?", (now,))


class _RedisRateLimitBackend(_BaseRateLimitBackend):
    def __init__(self, redis_url: str, namespace: str) -> None:
        try:
            import redis
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "DEEPTUTOR_RATE_LIMIT_BACKEND=redis requires the 'redis' package"
            ) from exc

        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._namespace = namespace.strip() or "deeptutor:rate-limit"
        self._fallback = _SQLiteRateLimitBackend(_sqlite_backend_path())
        self._degraded = False

    def clear(self) -> None:
        self._fallback.clear()

    def consume(self, scope_name: str, key: str, policy: RateLimitPolicy, now: float) -> int | None:
        del now
        if policy.max_requests <= 0 or policy.window_seconds <= 0:
            return None
        if self._degraded:
            return self._fallback.consume(scope_name, key, policy, time.time())

        namespaced_key = f"{self._namespace}:{scope_name}:{key}"
        ttl_ms = max(1, int(math.ceil(policy.window_seconds * 1000.0)))
        try:
            current = int(self._redis.incr(namespaced_key))
            if current == 1:
                self._redis.pexpire(namespaced_key, ttl_ms)
            if current > policy.max_requests:
                ttl = int(self._redis.pttl(namespaced_key))
                if ttl < 0:
                    return max(1, math.ceil(policy.window_seconds))
                return max(1, math.ceil(ttl / 1000.0))
            return None
        except Exception:
            self._degraded = True
            logger.warning(
                "Redis rate limit backend failed, falling back to SQLite backend",
                exc_info=True,
            )
            return self._fallback.consume(scope_name, key, policy, time.time())


def clear_rate_limit_state() -> None:
    _MemoryRateLimitBackend().clear()
    try:
        _get_backend().clear()
    except Exception:
        logger.debug("Failed to clear shared rate limit backend", exc_info=True)


def set_rate_limit_policy(scope_name: str, max_requests: int, window_seconds: float) -> None:
    _RATE_LIMIT_POLICY_OVERRIDES[str(scope_name)] = RateLimitPolicy(
        max_requests=max(0, int(max_requests)),
        window_seconds=max(0.0, float(window_seconds)),
    )


def _resolve_policy(
    scope_name: str,
    *,
    default_max_requests: int,
    default_window_seconds: float,
) -> RateLimitPolicy:
    return _RATE_LIMIT_POLICY_OVERRIDES.get(
        str(scope_name),
        RateLimitPolicy(
            max_requests=max(0, int(default_max_requests)),
            window_seconds=max(0.0, float(default_window_seconds)),
        ),
    )


def _env_flag(value: str | None) -> bool:
    return str(value or "").strip().lower() in _TRUTHY


def _rate_limit_backend_name() -> str:
    backend = str(os.getenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "sqlite")).strip().lower()
    if backend in {"memory", "sqlite", "redis", "auto"}:
        return backend
    logger.warning("Unknown DEEPTUTOR_RATE_LIMIT_BACKEND=%s, falling back to sqlite", backend)
    return "sqlite"


def _rate_limit_redis_url() -> str:
    return str(os.getenv("DEEPTUTOR_RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()


def _rate_limit_redis_namespace() -> str:
    return str(os.getenv("DEEPTUTOR_RATE_LIMIT_NAMESPACE") or "deeptutor:rate-limit").strip()


def _trust_proxy_headers() -> bool:
    return _env_flag(os.getenv("DEEPTUTOR_TRUST_PROXY_HEADERS"))


def _sqlite_backend_path() -> Path:
    configured = str(os.getenv("DEEPTUTOR_RATE_LIMIT_DB_PATH", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (PathService.get_instance().get_user_root() / "rate_limit.db").resolve()


def _get_backend() -> _BaseRateLimitBackend:
    global _BACKEND_CACHE

    backend_name = _rate_limit_backend_name()
    if backend_name == "redis":
        backend_key = (backend_name, _rate_limit_redis_url(), _rate_limit_redis_namespace())
    else:
        backend_key = (backend_name, str(_sqlite_backend_path()))

    with _BACKEND_LOCK:
        if _BACKEND_CACHE is not None and _BACKEND_CACHE[0] == backend_key:
            return _BACKEND_CACHE[1]

        if backend_name == "memory":
            backend = _MemoryRateLimitBackend()
        elif backend_name == "redis":
            redis_url = _rate_limit_redis_url()
            if not redis_url:
                raise RuntimeError(
                    "DEEPTUTOR_RATE_LIMIT_BACKEND=redis requires DEEPTUTOR_RATE_LIMIT_REDIS_URL"
                )
            backend = _RedisRateLimitBackend(redis_url, _rate_limit_redis_namespace())
        elif backend_name == "auto":
            redis_url = _rate_limit_redis_url()
            if redis_url:
                try:
                    backend = _RedisRateLimitBackend(redis_url, _rate_limit_redis_namespace())
                except Exception:
                    logger.warning(
                        "Redis rate limit backend unavailable, falling back to SQLite backend",
                        exc_info=True,
                    )
                    backend = _SQLiteRateLimitBackend(_sqlite_backend_path())
            else:
                backend = _SQLiteRateLimitBackend(_sqlite_backend_path())
        else:
            backend = _SQLiteRateLimitBackend(_sqlite_backend_path())

        _BACKEND_CACHE = (backend_key, backend)
        return backend


def _client_ip_from_parts(client_host: str, headers: dict[str, str]) -> str:
    if _trust_proxy_headers():
        forwarded_for = str(headers.get("x-forwarded-for") or headers.get("x-real-ip") or "").strip()
        if forwarded_for:
            first_hop = forwarded_for.split(",", 1)[0].strip()
            if first_hop:
                return first_hop
    return client_host or "unknown"


def _identity_from_headers(headers: dict[str, str]) -> str | None:
    authorization = str(headers.get("authorization") or "").strip()
    if not authorization:
        return None

    try:
        from deeptutor.api.dependencies.auth import resolve_auth_context

        auth_context = resolve_auth_context(authorization)
    except Exception:
        return None

    if auth_context is None:
        return None

    user_id = str(auth_context.user_id or "").strip()
    if not user_id:
        return None
    return f"user:{user_id}"


def _client_ip(request: Request) -> str:
    client = request.client
    client_host = str(client.host or "").strip() if client else ""
    headers = {str(key).lower(): str(value) for key, value in request.headers.items()}
    return _client_ip_from_parts(client_host, headers)


def _websocket_client_ip(ws: WebSocket) -> str:
    client = ws.client
    client_host = str(client.host or "").strip() if client else ""
    headers = {str(key).lower(): str(value) for key, value in ws.headers.items()}
    return _client_ip_from_parts(client_host, headers)


def _route_path(request: Request, scope_name: str) -> str:
    route = request.scope.get("route")
    path = str(getattr(route, "path", "") or "").strip()
    if path:
        return path
    return str(request.url.path or scope_name).strip() or scope_name


def _websocket_path(ws: WebSocket, scope_name: str) -> str:
    path = str(ws.url.path or "").strip()
    return path or scope_name


def _build_rate_limit_key(request: Request, scope_name: str) -> str:
    headers = {str(key).lower(): str(value) for key, value in request.headers.items()}
    identity = _identity_from_headers(headers) or f"ip:{_client_ip(request)}"
    return f"{identity}|{_route_path(request, scope_name)}"


def _build_websocket_rate_limit_key(ws: WebSocket, scope_name: str) -> str:
    headers = {str(key).lower(): str(value) for key, value in ws.headers.items()}
    identity = _identity_from_headers(headers) or f"ip:{_websocket_client_ip(ws)}"
    return f"{identity}|{_websocket_path(ws, scope_name)}"


def _consume_rate_limit(scope_name: str, key: str, policy: RateLimitPolicy) -> int | None:
    if policy.max_requests <= 0 or policy.window_seconds <= 0:
        return None

    now = time.time()
    backend = _get_backend()
    try:
        return backend.consume(scope_name, key, policy, now)
    except Exception:
        logger.warning("Rate limit backend failed, falling back to in-memory bucket", exc_info=True)
        return _MemoryRateLimitBackend().consume(scope_name, key, policy, now)


def route_rate_limit(
    scope_name: str,
    *,
    default_max_requests: int,
    default_window_seconds: float,
) -> Callable[[Request], object]:
    async def _rate_limit_dependency(request: Request) -> None:
        policy = _resolve_policy(
            scope_name,
            default_max_requests=default_max_requests,
            default_window_seconds=default_window_seconds,
        )
        retry_after = _consume_rate_limit(scope_name, _build_rate_limit_key(request, scope_name), policy)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": str(retry_after)},
            )

    return _rate_limit_dependency


async def enforce_websocket_rate_limit(
    ws: WebSocket,
    scope_name: str,
    *,
    default_max_requests: int,
    default_window_seconds: float,
) -> bool:
    policy = _resolve_policy(
        scope_name,
        default_max_requests=default_max_requests,
        default_window_seconds=default_window_seconds,
    )
    retry_after = _consume_rate_limit(scope_name, _build_websocket_rate_limit_key(ws, scope_name), policy)
    if retry_after is None:
        return True
    await ws.close(code=1013, reason="Too many requests")
    return False
