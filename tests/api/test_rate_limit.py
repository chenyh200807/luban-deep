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
