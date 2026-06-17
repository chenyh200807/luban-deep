"""M34 integration: general knowledge dividend over the real /api/v1/ws entrypoint."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import deeptutor.api._secure_router as secure_router_mod
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "wsh_m34",
    REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py",
)
wsh = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(wsh)


class FakeAgentCoordinator:
    calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def set_ws_callback(self, _callback: Any) -> None:
        return None

    def set_trace_callback(self, _callback: Any) -> None:
        return None

    async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return {
            "results": [
                {
                    "qa_pair": {
                        "question_id": "m34_general_knowledge_fixture",
                        "question": "高层住宅的建筑高度是怎么界定的？",
                        "question_type": "written",
                        "explanation": "M34 fake coordinator response.",
                    }
                }
            ]
        }

    async def generate_from_followup_context(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return await self.generate_from_topic(**kwargs)


def _client(tmp: str, *, user: str = "qa_m34_ws") -> TestClient:
    runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m34.db"))
    wsh._install_fakes(runtime, user_id=user, write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _authorization: wsh._auth_ctx(user)

    import deeptutor.agents.question.coordinator as coordinator_mod

    coordinator_mod.AgentCoordinator = FakeAgentCoordinator
    FakeAgentCoordinator.calls.clear()
    return TestClient(wsh._build_ws_app())


def _frame(content: str, *, include_config: bool = True) -> dict[str, Any]:
    frame = {
        "type": "start_turn",
        "content": content,
        "capability": "deep_question",
        "language": "zh",
    }
    if include_config:
        frame["config"] = {
            "general_knowledge_context": True,
        }
    return frame


def test_general_knowledge_question_ws_attaches_teaching_context() -> None:
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as client:
        result = wsh._receive_result(client, _frame("高层住宅的建筑高度是怎么界定的？"))

    metadata = result.get("metadata") or {}
    block = metadata.get("luban_general_knowledge_context")
    assert block, "general knowledge WS turn must attach compiled teaching context"
    assert block["official_score_allowed"] is False
    assert block["tier"] == "teaching_context_not_answer_key"
    assert "construction_grading_result" not in metadata
    preview = metadata.get("learning_evidence_preview")
    if preview is not None:
        assert preview.get("canonical_truth_written") is False
    assert FakeAgentCoordinator.calls
    assert "编译教学上下文" in str(FakeAgentCoordinator.calls[-1].get("history_context") or "")


def test_general_knowledge_question_ws_defaults_shadow_off_for_real_user_without_config() -> None:
    with tempfile.TemporaryDirectory() as tmp, _client(tmp, user="real_student_42") as client:
        result = wsh._receive_result(
            client,
            _frame("高层住宅的建筑高度是怎么界定的？", include_config=False),
        )

    metadata = result.get("metadata") or {}
    assert "luban_general_knowledge_context" not in metadata
    assert "construction_grading_result" not in metadata


def test_off_syllabus_ws_falls_open_no_teaching_block() -> None:
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as client:
        result = wsh._receive_result(client, _frame("今天天气怎么样随便聊聊"))

    metadata = result.get("metadata") or {}
    assert "luban_general_knowledge_context" not in metadata
    assert "construction_grading_result" not in metadata
