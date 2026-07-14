from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext
from deeptutor.services.session import SQLiteSessionStore, build_user_owner_key

ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")
secure_router_mod = importlib.import_module("deeptutor.api._secure_router")
router = ws_module.router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=is_admin,
    )


class _FakeRuntime:
    def __init__(self) -> None:
        self.started_payload: dict | None = None

    async def start_turn(self, payload: dict):
        self.started_payload = dict(payload)
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


class _BoomRuntime(_FakeRuntime):
    async def start_turn(self, payload: dict):
        raise RuntimeError("database exploded secret")


def test_ws_subscribe_session_rejects_foreign_owned_session(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SR1 PR-1b: authenticated user cannot subscribe another user's session.

    Note: original test used `resolve_auth_context: None` (anonymous); after PR-1b
    anon is rejected at handshake (4401), so this scenario is moved to
    `test_ws_anonymous_connection_rejected_with_4401`. Here we test the still-relevant
    case: user A trying to read user B's session must get "Session not found".
    """
    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="owned_session", owner_key=build_user_owner_key("student_other")))

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "subscribe_session", "session_id": "owned_session"})
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["content"] == "Session not found"


def test_ws_subscribe_session_rejects_ownerless_session_for_non_admin(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="legacy_public", owner_key=""))

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "subscribe_session", "session_id": "legacy_public"})
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["content"] == "Session not found"


def test_ws_anonymous_connection_rejected_with_4401(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SR1 PR-1b: anonymous WS connect must be rejected at handshake (was: A2 bypass).

    Replaces former `test_ws_subscribe_session_allows_anonymous_ownerless_session`
    which documented the A2 bug. The bug is now fixed; this test guards the fix.
    """
    from starlette.websockets import WebSocketDisconnect

    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: None)
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="legacy_public", owner_key=""))

    with TestClient(_build_app()) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/v1/ws") as websocket:
                websocket.receive_json()
    assert exc_info.value.code == 4401


def test_luban_card_stream_capability_only_subscribes_its_bound_turn(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The web-view has no bearer header, but cannot gain a general WS identity."""
    import asyncio

    store = SQLiteSessionStore(db_path=tmp_path / "ws-card-capability.db")
    fake_runtime = _FakeRuntime()
    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: None)
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    asyncio.run(
        store.create_session(
            session_id="card-session",
            owner_key=build_user_owner_key("student_real"),
        )
    )
    bound_turn = asyncio.run(store.create_turn("card-session", capability="chat"))
    asyncio.run(
        store.create_session(
            session_id="other-card-session",
            owner_key=build_user_owner_key("student_real"),
        )
    )
    other_turn = asyncio.run(store.create_turn("other-card-session", capability="chat"))
    ticket = asyncio.run(
        store.issue_luban_turn_stream_ticket(
            user_id="student_real",
            pack_id="F16",
            turn_id=str(bound_turn["id"]),
        )
    )

    with TestClient(_build_app()) as client:
        with client.websocket_connect(
            "/api/v1/ws",
            subprotocols=["luban-preview-v1", ticket],
        ) as websocket:
            websocket.send_json(
                {"type": "subscribe_turn", "turn_id": str(other_turn["id"]), "after_seq": 0}
            )
            rejected = websocket.receive_json()
            websocket.send_json(
                {"type": "subscribe_turn", "turn_id": str(bound_turn["id"]), "after_seq": 0}
            )
            completed = websocket.receive_json()
            websocket.send_json({"type": "start_turn", "content": "must not start"})
            forbidden = websocket.receive_json()

    assert rejected["type"] == "error"
    assert rejected["content"] == "Turn not found"
    assert completed["type"] == "done"
    assert completed["turn_id"] == str(bound_turn["id"])
    assert forbidden["type"] == "error"
    assert "only permits subscribing" in forbidden["content"]
    assert fake_runtime.started_payload is None


def test_luban_card_stream_rejects_invalid_capability_without_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: None)

    with TestClient(_build_app()) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/api/v1/ws",
                subprotocols=["luban-preview-v1", "not-a-real-capability"],
            ) as websocket:
                websocket.receive_json()
    assert exc_info.value.code == 4401


def test_ws_resume_from_rejects_foreign_owned_turn(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SR1 PR-1b regression: cross-session turn-regeneration is blocked.

    turn.md hard constraint #4 — `resume_from` only replays an existing turn and
    must authorize it through `_authorize_turn_access` (turn -> session -> owner).
    User A replaying user B's turn must get "Turn not found" and must never be
    subscribed to another user's stream. subscribe_session covers the session
    path; this locks the turn path independently so a future resume_from refactor
    that drops the authorize call is caught.
    """
    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="owned_by_other", owner_key=build_user_owner_key("student_other")))
    foreign_turn = asyncio.run(store.create_turn("owned_by_other", capability="chat"))
    foreign_turn_id = str(foreign_turn.get("id") or "")

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "resume_from", "turn_id": foreign_turn_id, "seq": 0})
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["content"] == "Turn not found"


def test_ws_subscribe_session_allows_owner(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="owned_session", owner_key=build_user_owner_key("student_demo")))

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "subscribe_session", "session_id": "owned_session"})
            message = websocket.receive_json()

    assert message["type"] == "done"
    assert message["session_id"] == "owned_session"


def test_ws_start_turn_binds_authenticated_user_into_billing_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "hello",
                    "config": {},
                }
            )
            message = websocket.receive_json()

    billing_context = fake_runtime.started_payload["config"]["billing_context"]
    assert billing_context["user_id"] == "student_demo"
    assert billing_context["source"] == "authenticated_ws"
    assert message["type"] == "done"


def test_ws_start_turn_normalizes_legacy_interaction_fields_into_interaction_hints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "hello",
                    "config": {
                        "product_surface": "prelaunch_audit",
                        "entry_role": "tutorbot",
                        "subject_domain": "construction_exam",
                        "teaching_mode": "smart",
                    },
                }
            )
            message = websocket.receive_json()

    config = fake_runtime.started_payload["config"]
    interaction_hints = config["interaction_hints"]
    assert "product_surface" not in config
    assert "entry_role" not in config
    assert interaction_hints["product_surface"] == "prelaunch_audit"
    assert interaction_hints["entry_role"] == "tutorbot"
    assert interaction_hints["subject_domain"] == "construction_exam"
    assert interaction_hints["requested_response_mode"] == "smart"
    assert "teaching_mode" not in interaction_hints
    assert config["billing_context"]["user_id"] == "student_demo"
    assert message["type"] == "done"


def test_ws_anonymous_start_turn_rejected_with_4401(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SR1 PR-1b: anonymous WS connect cannot reach start_turn (4401 at handshake).

    Replaces former `test_ws_start_turn_allows_anonymous_followup_for_ownerless_session`
    which documented the A2 bypass. Anonymous turn launches were the original
    LLM-burn risk vector — now hard-blocked.
    """
    from starlette.websockets import WebSocketDisconnect

    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: None)
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="legacy_public", owner_key=""))

    with TestClient(_build_app()) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/v1/ws") as websocket:
                websocket.receive_json()
    assert exc_info.value.code == 4401
    # fake_runtime must not have been touched — anon got rejected before reach handler.
    assert fake_runtime.started_payload is None


def test_ws_legacy_interaction_fields_normalization_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SR1 PR-1b: legacy interaction-field normalization still works for AUTH'd users.

    Replaces former `test_ws_start_turn_normalizes_legacy_interaction_fields_without_authentication`
    which tested the same normalization in anon mode. Anon WS is now hard-blocked;
    we re-test the normalization on an authenticated session.
    """
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "hello",
                    "config": {
                        "product_surface": "prelaunch_audit",
                        "priorities": ["stability", "compatibility"],
                    },
                }
            )
            message = websocket.receive_json()

    config = fake_runtime.started_payload["config"]
    interaction_hints = config["interaction_hints"]
    assert "product_surface" not in config
    assert "priorities" not in config
    assert interaction_hints["product_surface"] == "prelaunch_audit"
    assert interaction_hints["priorities"] == ["stability", "compatibility"]
    assert message["type"] == "done"


def test_ws_start_turn_runtime_error_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_runtime = _BoomRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "type": "start_turn",
                    "content": "hello",
                    "config": {},
                }
            )
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["content"] == "Unable to start turn. Please try again later."
    assert "database exploded secret" not in message["content"]


def test_ws_invalid_payload_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: _FakeRuntime())

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json({"type": "cancel_turn"})
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["content"] == "Invalid cancel_turn payload."


def test_ws_legacy_mobile_bootstrap_payload_subscribes_active_turn(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteSessionStore(db_path=tmp_path / "ws-auth.db")
    fake_runtime = _FakeRuntime()

    monkeypatch.setattr(secure_router_mod, "resolve_auth_context", lambda _authorization: _ctx("student_demo"))
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: fake_runtime)

    import asyncio

    asyncio.run(store.create_session(session_id="owned_session", owner_key=build_user_owner_key("student_demo")))
    asyncio.run(store.create_turn("owned_session", capability="chat"))

    with TestClient(_build_app()) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {
                    "content": "旧版小程序 bootstrap",
                    "chat_id": "owned_session",
                    "mode": "AUTO",
                }
            )
            message = websocket.receive_json()

    assert message["type"] == "done"
    assert message["session_id"] == "session_new"
