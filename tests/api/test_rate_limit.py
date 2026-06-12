from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
Depends = pytest.importorskip("fastapi").Depends
TestClient = pytest.importorskip("fastapi.testclient").TestClient

rate_limit_module = importlib.import_module("deeptutor.api.dependencies.rate_limit")


@pytest.fixture(autouse=True)
def _clear_rate_limit_state() -> None:
    rate_limit_module.clear_rate_limit_state()
    yield
    rate_limit_module.clear_rate_limit_state()


def test_rate_limit_falls_back_to_sqlite_when_redis_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _FakeRedisClient:
        def incr(self, *_args, **_kwargs):
            raise ConnectionError("redis unavailable")

        def pexpire(self, *_args, **_kwargs):
            return None

        def pttl(self, *_args, **_kwargs):
            return -1

    class _FakeRedisFactory:
        @staticmethod
        def from_url(*_args, **_kwargs):
            return _FakeRedisClient()

    fake_redis = types.ModuleType("redis")
    fake_redis.Redis = _FakeRedisFactory

    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_DB_PATH", str(tmp_path / "rate_limit.db"))
    monkeypatch.setitem(sys.modules, "redis", fake_redis)
    rate_limit_module.clear_rate_limit_state()

    app = FastAPI()

    @app.get(
        "/limited",
        dependencies=[
            Depends(
                rate_limit_module.route_rate_limit(
                    "redis_fallback",
                    default_max_requests=1,
                    default_window_seconds=60.0,
                )
            )
        ],
    )
    async def limited():
        return {"ok": True}

    with TestClient(app) as client:
        first = client.get("/limited")
        second = client.get("/limited")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "Too many requests"


def test_websocket_rate_limit_blocks_repeated_connections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "sqlite")
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_DB_PATH", str(tmp_path / "rate_limit.db"))
    rate_limit_module.clear_rate_limit_state()

    class _FakeWebSocket:
        def __init__(self) -> None:
            self.client = SimpleNamespace(host="127.0.0.1")
            self.headers: dict[str, str] = {}
            self.url = SimpleNamespace(path="/ws")
            self.scope = {"route": SimpleNamespace(path="/ws")}
            self.closed: tuple[int, str] | None = None

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.closed = (code, reason)

    async def _exercise() -> tuple[bool, bool, tuple[int, str] | None]:
        websocket = _FakeWebSocket()
        first = await rate_limit_module.enforce_websocket_rate_limit(
            websocket,
            "websocket_limit",
            default_max_requests=1,
            default_window_seconds=60.0,
        )
        second = await rate_limit_module.enforce_websocket_rate_limit(
            websocket,
            "websocket_limit",
            default_max_requests=1,
            default_window_seconds=60.0,
        )
        return first, second, websocket.closed

    first, second, closed = asyncio.run(_exercise())

    assert first is True
    assert second is False
    assert closed == (1013, "Too many requests")


def test_client_ip_prefers_unforgeable_x_real_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Behind the edge proxy, the rate-limit key must use the real client IP, not a
    forgeable header value — otherwise per-IP limits are trivially bypassed."""
    monkeypatch.setenv("DEEPTUTOR_TRUST_PROXY_HEADERS", "true")

    # X-Real-IP is set authoritatively by our nginx ($remote_addr) — use it as-is.
    ip = rate_limit_module._client_ip_from_parts(
        "172.20.0.1",
        {"x-real-ip": "203.0.113.9", "x-forwarded-for": "1.2.3.4, 203.0.113.9"},
    )
    assert ip == "203.0.113.9"


def test_client_ip_ignores_forged_leftmost_xff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_TRUST_PROXY_HEADERS", "true")
    # No X-Real-IP: fall back to the RIGHTMOST hop (appended by our nginx), never the
    # attacker-controlled leftmost "9.9.9.9".
    ip = rate_limit_module._client_ip_from_parts(
        "172.20.0.1",
        {"x-forwarded-for": "9.9.9.9, 203.0.113.9"},
    )
    assert ip == "203.0.113.9"


def test_client_ip_falls_back_to_socket_when_proxy_untrusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPTUTOR_TRUST_PROXY_HEADERS", raising=False)
    ip = rate_limit_module._client_ip_from_parts(
        "198.51.100.7", {"x-real-ip": "1.2.3.4", "x-forwarded-for": "1.2.3.4"}
    )
    assert ip == "198.51.100.7"  # headers ignored when proxy not trusted


def test_daily_turn_budget_blocks_sustained_burn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A 24h-window per-user budget caps sustained burn the 60s burst limit can't stop."""
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_BACKEND", "sqlite")
    monkeypatch.setenv("DEEPTUTOR_RATE_LIMIT_DB_PATH", str(tmp_path / "rl.db"))
    rate_limit_module.clear_rate_limit_state()

    class _FakeWebSocket:
        def __init__(self) -> None:
            self.client = SimpleNamespace(host="127.0.0.1")
            self.headers: dict[str, str] = {}
            self.url = SimpleNamespace(path="/ws")
            self.scope = {"route": SimpleNamespace(path="/ws")}
            self.closed: tuple[int, str] | None = None

        async def close(self, code: int = 1000, reason: str = "") -> None:
            self.closed = (code, reason)

    async def _exercise() -> list[bool]:
        ws = _FakeWebSocket()
        results = []
        for _ in range(3):
            results.append(
                await rate_limit_module.enforce_websocket_rate_limit(
                    ws, "ws_start_turn_daily",
                    default_max_requests=2, default_window_seconds=86400.0,
                )
            )
        return results

    results = asyncio.run(_exercise())
    assert results == [True, True, False]  # 3rd within the day window is blocked


def test_daily_turn_budget_is_wired_into_chat_entrypoints() -> None:
    """Both LLM chat entrypoints must reference the daily-budget scope (wiring guard)."""
    repo = Path(__file__).resolve().parents[2]
    ws_src = (repo / "deeptutor/api/routers/unified_ws.py").read_text(encoding="utf-8")
    mobile_src = (repo / "deeptutor/api/routers/mobile.py").read_text(encoding="utf-8")
    assert "ws_start_turn_daily" in ws_src
    assert "mobile_chat_start_turn_daily" in mobile_src


def test_fallback_in_memory_bucket_accumulates_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F9 regression: when the primary backend keeps throwing, the in-memory fallback
    must still rate-limit. The fallback ``_MemoryRateLimitBackend()`` is stateless —
    its buckets live in the module-level ``_RATE_LIMIT_STATE`` — so constructing a new
    instance per call does NOT reset counts; they accumulate and the limiter holds.
    (The audit's F9 "limiter bypassed" reading was a false positive; this pins the fact.)"""

    class _BoomBackend:
        def consume(self, *_args, **_kwargs):
            raise RuntimeError("primary backend down")

    monkeypatch.setattr(rate_limit_module, "_get_backend", lambda: _BoomBackend())

    policy = rate_limit_module.RateLimitPolicy(max_requests=3, window_seconds=60.0)
    results = [
        rate_limit_module._consume_rate_limit("probe_scope", "probe_key", policy)
        for _ in range(5)
    ]

    # First 3 allowed (None), then the accumulated count trips the limit (retry-after int).
    assert results[:3] == [None, None, None]
    assert all(isinstance(r, int) and r > 0 for r in results[3:])
