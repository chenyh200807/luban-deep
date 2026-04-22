from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_mobile_login_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_mobile_login_smoke", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, object]:
        return dict(self._payload)


class _FakeAsyncClient:
    def __init__(self, responses: dict[tuple[str, str], list[_FakeResponse]], captured: dict[str, object], **_kwargs) -> None:
        self._responses = responses
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method: str, path: str, *, headers=None, json=None):
        key = (method.upper(), path)
        self._captured.setdefault("requests", []).append(
            {
                "method": method.upper(),
                "path": path,
                "headers": dict(headers or {}),
                "json": dict(json or {}) if isinstance(json, dict) else json,
            }
        )
        queue = self._responses.get(key) or []
        if not queue:
            raise AssertionError(f"unexpected request: {key}")
        return queue.pop(0)


class _FakeWebSocket:
    def __init__(self, events: list[dict[str, object]], captured: dict[str, object]) -> None:
        self._events = [json.dumps(item, ensure_ascii=False) for item in events]
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, raw: str) -> None:
        self._captured.setdefault("ws_payloads", []).append(json.loads(raw))

    async def recv(self) -> str:
        if not self._events:
            raise AssertionError("unexpected ws recv")
        return self._events.pop(0)


def test_generated_credentials_meet_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE.time, "time", lambda: 1_776_857_000)

    username, password, phone = MODULE._generated_credentials("smoke")

    assert username == "smoke_1776857000"
    assert password.startswith("SmokeA")
    assert any(ch.islower() for ch in password)
    assert any(ch.isupper() for ch in password)
    assert any(ch.isdigit() for ch in password)
    assert len(phone) == 11
    assert phone.startswith("139")


@pytest.mark.asyncio
async def test_run_mobile_login_smoke_registers_two_turns_and_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    responses = {
        ("POST", "/api/v1/auth/register"): [
            _FakeResponse(
                200,
                {
                    "token": "token-1",
                    "user_id": "user_smoke",
                    "user": {"user_id": "user_smoke"},
                },
            )
        ],
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(
                200,
                {
                    "user_id": "user_smoke",
                    "id": "user_smoke",
                    "display_name": "smoke",
                },
            )
        ],
        ("POST", "/api/v1/conversations"): [
            _FakeResponse(
                200,
                {
                    "conversation": {
                        "id": "tb_smoke_1",
                        "title": "新对话",
                    }
                },
            )
        ],
        ("POST", "/api/v1/chat/start-turn"): [
            _FakeResponse(
                200,
                {
                    "conversation": {"id": "tb_smoke_1"},
                    "turn": {"id": "turn_1"},
                    "stream": {
                        "transport": "websocket",
                        "url": "/api/v1/ws",
                        "subscribe": {"type": "subscribe_turn", "turn_id": "turn_1", "after_seq": 0},
                    },
                },
            ),
            _FakeResponse(
                200,
                {
                    "conversation": {"id": "tb_smoke_1"},
                    "turn": {"id": "turn_2"},
                    "stream": {
                        "transport": "websocket",
                        "url": "/api/v1/ws",
                        "subscribe": {"type": "subscribe_turn", "turn_id": "turn_2", "after_seq": 0},
                    },
                },
            ),
        ],
        ("GET", "/api/v1/conversations/tb_smoke_1/messages"): [
            _FakeResponse(
                200,
                {
                    "messages": [
                        {"id": "m1", "role": "user"},
                        {"id": "m2", "role": "assistant"},
                    ]
                },
            ),
            _FakeResponse(
                200,
                {
                    "messages": [
                        {"id": "m1", "role": "user"},
                        {"id": "m2", "role": "assistant"},
                        {"id": "m3", "role": "user"},
                        {"id": "m4", "role": "assistant"},
                    ]
                },
            ),
        ],
        ("DELETE", "/api/v1/conversations/tb_smoke_1"): [
            _FakeResponse(200, {"deleted": True})
        ],
    }

    def _client_factory(**kwargs):
        return _FakeAsyncClient(responses, captured, **kwargs)

    ws_batches = [
        [
            {"type": "session", "session_id": "tb_smoke_1", "turn_id": "turn_1"},
            {"type": "content", "content": "第一轮回答"},
            {"type": "result", "turn_id": "turn_1", "metadata": {"response": "第一轮回答"}},
            {"type": "done", "turn_id": "turn_1", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "session", "session_id": "tb_smoke_1", "turn_id": "turn_2"},
            {"type": "content", "content": "第二轮回答"},
            {"type": "result", "turn_id": "turn_2", "metadata": {"response": "第二轮回答"}},
            {"type": "done", "turn_id": "turn_2", "metadata": {"status": "completed"}},
        ],
    ]

    def _connector_factory(url: str, *, additional_headers=None):
        captured.setdefault("ws_connections", []).append(
            {"url": url, "headers": dict(additional_headers or {})}
        )
        if not ws_batches:
            raise AssertionError("unexpected ws connection")
        return _FakeWebSocket(ws_batches.pop(0), captured)

    payload = await MODULE.run_mobile_login_smoke(
        api_base_url="https://example.com",
        username="smoke_user",
        password="SmokeA123456",
        phone="13900001234",
        register=True,
        client_factory=_client_factory,
        connector_factory=_connector_factory,
    )

    assert payload["passed"] is True
    assert payload["created_user"] is True
    assert payload["conversation_id"] == "tb_smoke_1"
    assert payload["conversation_deleted"] is True
    assert payload["messages_after_first_count"] == 2
    assert payload["messages_after_second_count"] == 4
    assert payload["first_turn"]["turn_id"] == "turn_1"
    assert payload["second_turn"]["turn_id"] == "turn_2"
    assert payload["first_turn"]["assistant_response"] == "第一轮回答"
    assert payload["second_turn"]["assistant_response"] == "第二轮回答"
    assert captured["ws_connections"] == [
        {
            "url": "wss://example.com/api/v1/ws",
            "headers": {"Authorization": "Bearer token-1"},
        },
        {
            "url": "wss://example.com/api/v1/ws",
            "headers": {"Authorization": "Bearer token-1"},
        },
    ]
    assert captured["ws_payloads"] == [
        {"type": "subscribe_turn", "turn_id": "turn_1", "after_seq": 0},
        {"type": "subscribe_turn", "turn_id": "turn_2", "after_seq": 0},
    ]


@pytest.mark.asyncio
async def test_run_mobile_login_smoke_falls_back_to_login_when_register_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {
        ("POST", "/api/v1/auth/register"): [
            _FakeResponse(400, {"detail": "用户名已存在"})
        ],
        ("POST", "/api/v1/auth/login"): [
            _FakeResponse(
                200,
                {
                    "token": "token-existing",
                    "user_id": "user_existing",
                    "user": {"user_id": "user_existing"},
                },
            )
        ],
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "user_existing", "id": "user_existing"})
        ],
        ("POST", "/api/v1/conversations"): [
            _FakeResponse(200, {"conversation": {"id": "tb_existing"}})
        ],
        ("POST", "/api/v1/chat/start-turn"): [
            _FakeResponse(
                200,
                {
                    "conversation": {"id": "tb_existing"},
                    "turn": {"id": "turn_existing_1"},
                    "stream": {
                        "transport": "websocket",
                        "url": "/api/v1/ws",
                        "subscribe": {"type": "subscribe_turn", "turn_id": "turn_existing_1", "after_seq": 0},
                    },
                },
            ),
            _FakeResponse(
                200,
                {
                    "conversation": {"id": "tb_existing"},
                    "turn": {"id": "turn_existing_2"},
                    "stream": {
                        "transport": "websocket",
                        "url": "/api/v1/ws",
                        "subscribe": {"type": "subscribe_turn", "turn_id": "turn_existing_2", "after_seq": 0},
                    },
                },
            ),
        ],
        ("GET", "/api/v1/conversations/tb_existing/messages"): [
            _FakeResponse(200, {"messages": [{"id": "m1"}, {"id": "m2"}]}),
            _FakeResponse(200, {"messages": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]}),
        ],
        ("DELETE", "/api/v1/conversations/tb_existing"): [
            _FakeResponse(200, {"deleted": True})
        ],
    }

    def _client_factory(**kwargs):
        return _FakeAsyncClient(responses, {}, **kwargs)

    ws_batches = [
        [
            {"type": "session", "session_id": "tb_existing", "turn_id": "turn_existing_1"},
            {"type": "result", "turn_id": "turn_existing_1", "metadata": {"response": "答复一"}},
            {"type": "done", "turn_id": "turn_existing_1", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "session", "session_id": "tb_existing", "turn_id": "turn_existing_2"},
            {"type": "result", "turn_id": "turn_existing_2", "metadata": {"response": "答复二"}},
            {"type": "done", "turn_id": "turn_existing_2", "metadata": {"status": "completed"}},
        ],
    ]

    def _connector_factory(_url: str, *, additional_headers=None):
        return _FakeWebSocket(ws_batches.pop(0), {})

    payload = await MODULE.run_mobile_login_smoke(
        api_base_url="https://example.com",
        username="existing",
        password="SmokeA123456",
        phone="13900001234",
        register=True,
        client_factory=_client_factory,
        connector_factory=_connector_factory,
    )

    assert payload["passed"] is True
    assert payload["created_user"] is False
