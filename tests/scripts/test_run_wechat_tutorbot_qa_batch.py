from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_wechat_tutorbot_qa_batch.py"
SPEC = importlib.util.spec_from_file_location("run_wechat_tutorbot_qa_batch", SCRIPT_PATH)
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


def test_load_default_scenarios_are_complete() -> None:
    scenarios = MODULE._load_scenarios(None)

    assert len(scenarios) >= 10
    assert all(item.round_id for item in scenarios)
    assert all(item.query for item in scenarios)
    assert {item.conversation_key for item in scenarios}


@pytest.mark.asyncio
async def test_run_batch_sends_wechat_shaped_payload_and_writes_artifacts(tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    responses = {
        ("POST", "/api/v1/auth/login"): [
            _FakeResponse(200, {"token": "token-qa", "user_id": "user_qa"})
        ],
        ("GET", "/api/v1/auth/profile"): [
            _FakeResponse(200, {"user_id": "user_qa", "wallet": {"plan_id": "internal_qa"}})
        ],
        ("POST", "/api/v1/conversations"): [
            _FakeResponse(200, {"conversation": {"id": "conv_a"}}),
            _FakeResponse(200, {"conversation": {"id": "conv_b"}}),
        ],
        ("POST", "/api/v1/chat/start-turn"): [
            _FakeResponse(
                200,
                {
                    "conversation": {"id": "conv_a"},
                    "turn": {"id": "turn_a1"},
                    "stream": {
                        "transport": "websocket",
                        "subscribe": {"type": "subscribe_turn", "turn_id": "turn_a1", "after_seq": 0},
                    },
                },
            ),
            _FakeResponse(
                200,
                {
                    "conversation": {"id": "conv_a"},
                    "turn": {"id": "turn_a2"},
                    "stream": {
                        "transport": "websocket",
                        "subscribe": {"type": "subscribe_turn", "turn_id": "turn_a2", "after_seq": 0},
                    },
                },
            ),
            _FakeResponse(
                200,
                {
                    "conversation": {"id": "conv_b"},
                    "turn": {"id": "turn_b1"},
                    "stream": {
                        "transport": "websocket",
                        "subscribe": {"type": "subscribe_turn", "turn_id": "turn_b1", "after_seq": 0},
                    },
                },
            ),
        ],
    }

    def _client_factory(**kwargs):
        return _FakeAsyncClient(responses, captured, **kwargs)

    ws_batches = [
        [
            {"type": "content", "content": "答复一"},
            {"type": "result", "metadata": {"response": "答复一", "execution_path": "tutorbot_exact_fast_path"}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "result", "metadata": {"response": "答复二", "mode": "followup"}},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
        [
            {"type": "content", "content": "答复三"},
            {"type": "done", "metadata": {"status": "completed"}},
        ],
    ]

    def _connector_factory(url: str, *, additional_headers=None):
        captured.setdefault("ws_connections", []).append(
            {"url": url, "headers": dict(additional_headers or {})}
        )
        return _FakeWebSocket(ws_batches.pop(0), captured)

    scenarios = [
        MODULE.BatchTurn("R1", "a", "第一题", "exact", "答一"),
        MODULE.BatchTurn("R2", "a", "追问", "followup", "答二"),
        MODULE.BatchTurn("R3", "b", "第二题", "exact", "答三"),
    ]
    (tmp_path / "transcript.jsonl").write_text('{"stale": true}\n', encoding="utf-8")

    summary = await MODULE.run_batch(
        api_base_url="http://example.test",
        username="qa_user",
        password="QaTutorbot2026",
        phone="13900000001",
        scenarios=scenarios,
        output_dir=tmp_path,
        entry_surface="near_real_http_ws_wechat_payload",
        client_factory=_client_factory,
        connector_factory=_connector_factory,
    )

    assert summary["rounds"] == 3
    assert len((tmp_path / "transcript.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    assert summary["conversation_ids"] == {"a": "conv_a", "b": "conv_b"}
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "transcript.jsonl").exists()
    assert (tmp_path / "turn_ids.txt").read_text(encoding="utf-8").splitlines() == [
        "R1=turn_a1",
        "R2=turn_a2",
        "R3=turn_b1",
    ]

    start_turns = [
        request
        for request in captured["requests"]
        if request["method"] == "POST" and request["path"] == "/api/v1/chat/start-turn"
    ]
    assert [request["json"]["conversation_id"] for request in start_turns] == [
        "conv_a",
        "conv_a",
        "conv_b",
    ]
    assert start_turns[0]["json"]["config"] == {"bot_id": "construction-exam-coach"}
    assert start_turns[0]["json"]["interaction_profile"] == "tutorbot"
    assert start_turns[0]["json"]["interaction_hints"] == {
        "product_surface": "wechat_miniprogram",
        "entry_role": "tutorbot",
        "subject_domain": "construction_exam",
        "requested_response_mode": "smart",
    }
    assert "structuredSubmitContext" not in start_turns[0]["json"]

    assert captured["ws_connections"] == [
        {"url": "ws://example.test/api/v1/ws", "headers": {"Authorization": "Bearer token-qa"}},
        {"url": "ws://example.test/api/v1/ws", "headers": {"Authorization": "Bearer token-qa"}},
        {"url": "ws://example.test/api/v1/ws", "headers": {"Authorization": "Bearer token-qa"}},
    ]
    assert captured["ws_payloads"] == [
        {"type": "subscribe_turn", "turn_id": "turn_a1", "after_seq": 0},
        {"type": "subscribe_turn", "turn_id": "turn_a2", "after_seq": 0},
        {"type": "subscribe_turn", "turn_id": "turn_b1", "after_seq": 0},
    ]
