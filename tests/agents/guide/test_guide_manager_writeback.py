from __future__ import annotations

import asyncio
import importlib

guide_manager_module = importlib.import_module("deeptutor.agents.guide.guide_manager")
guide_router_module = importlib.import_module("deeptutor.api.routers.guide")
GuideManager = guide_manager_module.GuideManager


class _FakeBaseAgent:
    def __init__(self, *args, **kwargs):
        pass


class _FakeDesignAgent(_FakeBaseAgent):
    async def process(self, user_input: str):
        return {
            "success": True,
            "knowledge_points": [
                {
                    "knowledge_title": "地基基础承载力",
                    "knowledge_summary": "核心概念梳理",
                    "user_difficulty": "medium",
                }
            ],
        }


class _FakeSummaryAgent(_FakeBaseAgent):
    async def process(self, *args, **kwargs):
        return {
            "success": True,
            "summary": "# Guided Learning Summary\n- 已完成地基基础承载力的结构化整理。",
        }


class _FakeInteractiveAgent(_FakeBaseAgent):
    async def process(self, **kwargs):
        return {
            "success": True,
            "html": "<div class='page'>学习页面</div>",
            "error": "",
            "knowledge": kwargs.get("knowledge", {}),
        }


class _FakeLearnerStateService:
    def __init__(self, calls):
        self._calls = calls

    async def record_guide_completion(self, **kwargs):
        self._calls.append({"kind": "event", **kwargs})

    async def refresh_from_turn(self, **kwargs):
        self._calls.append({"kind": "refresh", **kwargs})
        return None


class _FakeRouterManager:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def create_session(self, **kwargs):
        self.calls.append(("create_session", kwargs))
        return {"success": True, "session_id": "session_demo", "knowledge_points": []}

    async def complete_learning(self, session_id: str, **kwargs):
        payload = {"session_id": session_id, **kwargs}
        self.calls.append(("complete_learning", payload))
        return {"success": True, "status": "completed", "summary": "ok", "progress": 100}


def test_guide_manager_preserves_identifiers_and_writes_back_on_complete(monkeypatch, tmp_path) -> None:
    calls: list[dict] = []

    monkeypatch.setattr(guide_manager_module, "DesignAgent", _FakeDesignAgent)
    monkeypatch.setattr(guide_manager_module, "InteractiveAgent", _FakeInteractiveAgent)
    monkeypatch.setattr(guide_manager_module, "ChatAgent", _FakeBaseAgent)
    monkeypatch.setattr(guide_manager_module, "SummaryAgent", _FakeSummaryAgent)
    monkeypatch.setattr(
        guide_manager_module,
        "UserTutorStateService",
        lambda: _FakeLearnerStateService(calls),
    )

    manager = GuideManager(
        api_key="test-key",
        base_url="https://example.invalid",
        config_path=str(tmp_path / "missing.yaml"),
        output_dir=str(tmp_path / "guide"),
        language="zh",
    )

    created = asyncio.run(
        manager.create_session(
            user_input="请帮我设计一个地基基础承载力的 guided learning 计划。",
            display_title="地基基础承载力学习",
            notebook_context="Notebook context for guided learning.",
            user_id="student_demo",
            source_bot_id="bot_alpha",
        )
    )

    assert created["success"] is True
    session = manager._load_session(created["session_id"])
    assert session is not None
    assert session.user_id == "student_demo"
    assert session.source_bot_id == "bot_alpha"

    asyncio.run(manager._generate_single_page(created["session_id"], 0))
    completed = asyncio.run(manager.complete_learning(created["session_id"]))
    assert completed["success"] is True
    assert calls
    events = [call for call in calls if call["kind"] == "event"]
    refreshes = [call for call in calls if call["kind"] == "refresh"]

    plan_path = tmp_path / "guide" / "learning_plans" / f"{created['session_id']}.json"
    pages_path = tmp_path / "guide" / "learning_plan_pages" / f"{created['session_id']}.json"
    assert plan_path.exists()
    assert pages_path.exists()

    plan_payload = guide_manager_module.json.loads(plan_path.read_text(encoding="utf-8"))
    pages_payload = guide_manager_module.json.loads(pages_path.read_text(encoding="utf-8"))

    assert plan_payload["user_id"] == "student_demo"
    assert plan_payload["session_id"] == created["session_id"]
    assert plan_payload["source_material_refs_json"][0]["kind"] == "user_input"
    assert plan_payload["status"] == "completed"
    assert "Guided Learning Summary" in plan_payload["summary"]
    assert pages_payload[0]["page_index"] == 0
    assert pages_payload[0]["page_status"] == "ready"
    assert "学习页面" in pages_payload[0]["html"]
    assert events[0]["user_id"] == "student_demo"
    assert events[0]["guide_id"] == created["session_id"]
    assert events[0]["source_bot_id"] == "bot_alpha"
    assert refreshes[0]["session_id"] == created["session_id"]
    assert refreshes[0]["capability"] == "guide:bot_alpha"
    assert "Notebook context for guided learning." in refreshes[0]["user_message"]


def test_guide_router_forwards_optional_identity_fields(monkeypatch) -> None:
    manager = _FakeRouterManager()
    monkeypatch.setattr(guide_router_module, "get_guide_manager", lambda: manager)

    created = asyncio.run(
        guide_router_module.create_session(
            guide_router_module.CreateSessionRequest(
                user_input="请帮我梳理知识点。",
                user_id="student_demo",
                source_bot_id="bot_alpha",
            )
        )
    )
    completed = asyncio.run(
        guide_router_module.complete_learning(
            guide_router_module.SessionActionRequest(
                session_id=created["session_id"],
                user_id="student_demo",
                source_bot_id="bot_alpha",
            )
        )
    )

    assert created["success"] is True
    assert completed["success"] is True
    assert manager.calls[0][0] == "create_session"
    assert manager.calls[0][1]["user_id"] == "student_demo"
    assert manager.calls[0][1]["source_bot_id"] == "bot_alpha"
    assert manager.calls[1][0] == "complete_learning"
    assert manager.calls[1][1]["user_id"] == "student_demo"
    assert manager.calls[1][1]["source_bot_id"] == "bot_alpha"
