from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from fastapi import HTTPException, Request, status


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


def clear_rate_limit_state() -> None:
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_STATE.clear()


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


def _client_ip(request: Request) -> str:
    client = request.client
    if client and str(client.host or "").strip():
        return str(client.host).strip()
    return "unknown"


def _route_path(request: Request, scope_name: str) -> str:
    route = request.scope.get("route")
    path = str(getattr(route, "path", "") or "").strip()
    if path:
        return path
    return str(request.url.path or scope_name).strip() or scope_name


def _build_rate_limit_key(request: Request, scope_name: str) -> str:
    return f"{_client_ip(request)}|{_route_path(request, scope_name)}"


def _prune_expired_entries(now: float) -> None:
    if len(_RATE_LIMIT_STATE) <= 1024:
        return

    expired_keys = [
        key
        for key, bucket in _RATE_LIMIT_STATE.items()
        if now - bucket.window_start >= bucket.window_seconds
    ]
    for key in expired_keys:
        _RATE_LIMIT_STATE.pop(key, None)


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
        if policy.max_requests <= 0 or policy.window_seconds <= 0:
            return

        now = time.monotonic()
        key = _build_rate_limit_key(request, scope_name)

        with _RATE_LIMIT_LOCK:
            bucket = _RATE_LIMIT_STATE.get(key)
            if bucket is None or now - bucket.window_start >= bucket.window_seconds:
                _RATE_LIMIT_STATE[key] = _RateLimitBucket(
                    window_start=now,
                    request_count=1,
                    window_seconds=policy.window_seconds,
                )
                _prune_expired_entries(now)
                return

            if bucket.request_count >= policy.max_requests:
                retry_after = max(1, int(bucket.window_seconds - (now - bucket.window_start)))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests",
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.request_count += 1

    return _rate_limit_dependency
