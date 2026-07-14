"""WS boundary error handling: single-turn execution errors must NOT disconnect.

Root cause (thin-wrapper-fat-skill): `/api/v1/ws` is the only chat WS entry. Its
main loop must keep the receive loop alive when a *single turn operation* fails —
it should emit a turn-level `error` event and `continue`. Only transport/protocol
errors (WebSocketDisconnect) should tear down the connection.

These tests pin the boundary contract:
- a non-Permission/Runtime/Validation exception from `runtime.start_turn` →
  error event + loop stays alive + next message still processed.
- the same for `runtime.cancel_turn`.
- `asyncio.CancelledError` is NEVER swallowed into an error event (control flow).
- the public error message never leaks internal exception detail.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext

ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")
secure_router_mod = importlib.import_module("deeptutor.api._secure_router")
router = ws_module.router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _ctx(user_id: str = "student_demo") -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=False,
    )


class _BaseFakeRuntime:
    def __init__(self) -> None:
        self.start_calls = 0

    async def start_turn(self, payload: dict):
        self.start_calls += 1
        return {"id": str(payload.get("session_id") or "session_new")}, {"id": "turn_new"}

    async def subscribe_turn(self, turn_id: str, after_seq: int = 0):
        yield {
            "type": "done",
            "source": "test",
            "stage": "",
            "content": "",
            "metadata": {"status": "completed", "after_seq": after_seq},
            "session_id": "session_new",
            "turn_id": turn_id,
            "seq": 1,
            "timestamp": 0,
        }

    async def subscribe_session(self, session_id: str, after_seq: int = 0):
        yield {
            "type": "done",
            "source": "test",
            "stage": "",
            "content": "",
            "metadata": {"status": "completed", "after_seq": after_seq},
            "session_id": session_id,
            "turn_id": "",
            "seq": 1,
            "timestamp": 0,
        }

    async def cancel_turn(self, _turn_id: str) -> bool:
        return True


class _StartTurnExplodesOnceRuntime(_BaseFakeRuntime):
    """First start_turn raises a *non-handled* exception; later ones succeed.

    Uses KeyError (not Permission/Runtime/Validation) to exercise the fallback
    boundary. The message embeds a secret to prove the public reply is sanitized.
    """

    async def start_turn(self, payload: dict):
        self.start_calls += 1
        if self.start_calls == 1:
            raise KeyError("internal_kv_secret_xyz")
        return {"id": str(payload.get("session_id") or "session_new")}, {"id": "turn_new"}


class _CancelTurnExplodesRuntime(_BaseFakeRuntime):
    async def cancel_turn(self, _turn_id: str) -> bool:
        raise KeyError("cancel_internal_secret_abc")


class _StartTurnCancelledRuntime(_BaseFakeRuntime):
    async def start_turn(self, payload: dict):
        self.start_calls += 1
        raise asyncio.CancelledError()


def test_ws_start_turn_unhandled_error_keeps_loop_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A KeyError from start_turn must NOT kill the connection.

    Contract: emit a turn-level error event + keep receiving. The second
    start_turn (which succeeds) must still flow through the same connection.
    """
    fake_runtime = _StartTurnExplodesOnceRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx())
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)
    # Isolate from the process-global ws_start_turn rate-limit store (other suite
    # tests share the same identity|path key); this test sends 2 start_turns and
    # must not trip the limit.
    monkeypatch.setattr(ws_module, "enforce_websocket_rate_limit", _allow_rate_limit)

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "start_turn", "content": "boom", "config": {}})
            first = websocket.receive_json()

            # Loop must still be alive: send a second message that succeeds.
            websocket.send_json({"type": "start_turn", "content": "ok", "config": {}})
            second = websocket.receive_json()

    assert first["type"] == "error"
    assert first["content"] == "Unable to start turn. Please try again later."
    assert "internal_kv_secret_xyz" not in first["content"]
    # Proof the receive loop survived and processed the next turn.
    assert second["type"] == "done"
    assert fake_runtime.start_calls == 2


def test_ws_cancel_turn_unhandled_error_keeps_loop_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A KeyError from cancel_turn must NOT kill the connection either."""
    fake_runtime = _CancelTurnExplodesRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx())
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)
    # Bypass turn ownership lookup so we reach the runtime.cancel_turn call.
    monkeypatch.setattr(ws_module, "_authorize_turn_access", _noop_authorize)
    # Isolate from the process-global ws_start_turn rate-limit store (the follow-up
    # start_turn below shares the same identity|path key as other suite tests).
    monkeypatch.setattr(ws_module, "enforce_websocket_rate_limit", _allow_rate_limit)

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "cancel_turn", "turn_id": "turn_x"})
            first = websocket.receive_json()

            # Loop must still be alive: a start_turn after the failed cancel works.
            websocket.send_json({"type": "start_turn", "content": "ok", "config": {}})
            second = websocket.receive_json()

    assert first["type"] == "error"
    assert "cancel_internal_secret_abc" not in first["content"]
    assert second["type"] == "done"


async def _noop_authorize(_turn_id: str, _current_user) -> None:
    return None


def test_ws_start_turn_cancelled_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """asyncio.CancelledError from start_turn must propagate, NOT become an error event.

    We assert directly on the endpoint coroutine: drive one start_turn frame, then
    confirm CancelledError escapes the loop instead of being converted to a
    sanitized error event. This guards the `except asyncio.CancelledError: raise`
    placed before the bare-Exception fallback.
    """
    fake_runtime = _StartTurnCancelledRuntime()
    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx())
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    sent: list[dict] = []
    frames = iter([{"type": "start_turn", "content": "boom", "config": {}}])

    class _FakeWS:
        scope = {"subprotocols": []}

        async def receive_text(self):
            import json as _json

            try:
                return _json.dumps(next(frames))
            except StopIteration:
                from starlette.websockets import WebSocketDisconnect

                raise WebSocketDisconnect(code=1000)

        async def send_json(self, data: dict) -> None:
            sent.append(data)

        async def accept(self, *args, **kwargs) -> None:
            return None

        async def close(self, *args, **kwargs) -> None:
            return None

    # Make handshake auth a pass-through that yields our context.
    monkeypatch.setattr(ws_module, "secure_ws_endpoint", _passthrough_secure_ws)
    monkeypatch.setattr(ws_module, "enforce_websocket_rate_limit", _allow_rate_limit)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ws_module.unified_websocket(_FakeWS()))

    # CancelledError must NOT have been turned into a public error event.
    assert all(
        not (isinstance(item, dict) and item.get("type") == "error") for item in sent
    ), f"CancelledError leaked into an error event: {sent}"


async def _passthrough_secure_ws(ws, **_kwargs):
    await ws.accept()
    return _ctx()


async def _allow_rate_limit(*_args, **_kwargs) -> bool:
    return True
