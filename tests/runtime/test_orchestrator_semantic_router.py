from __future__ import annotations

from typing import Any

import pytest

from deeptutor.core.context import UnifiedContext
from deeptutor.runtime.orchestrator import ChatOrchestrator
from deeptutor.services.semantic_router import build_active_object_from_question_context


class _FakeCapability:
    async def run(self, context: UnifiedContext, bus) -> None:
        await bus.result(
            {
                "capability": context.active_capability or "auto",
                "turn_semantic_decision": context.metadata.get("turn_semantic_decision", {}),
            },
            source="fake",
        )


class _FakeRegistry:
    def __init__(self) -> None:
        self.captured: list[str] = []

    def get(self, name: str) -> Any:
        self.captured.append(name)
        return _FakeCapability()

    def list_capabilities(self) -> list[str]:
        return ["chat", "deep_question"]

    def get_manifests(self) -> list[dict[str, Any]]:
        return []


def _active_object() -> dict[str, Any]:
    active_object = build_active_object_from_question_context(
        {
            "question_id": "q_1",
            "question": "流水步距反映的是什么？",
            "question_type": "choice",
            "options": {"A": "工期", "B": "相邻专业队投入间隔"},
            "correct_answer": "B",
        },
        source_turn_id="turn-1",
    )
    assert active_object is not None
    return active_object


def _guide_active_object() -> dict[str, Any]:
    return {
        "object_type": "guide_page",
        "object_id": "plan_demo:page:1",
        "scope": {"domain": "guided_plan", "plan_id": "plan_demo", "page_index": 1},
        "state_snapshot": {
            "plan_id": "plan_demo",
            "status": "in_progress",
            "current_index": 1,
            "summary": "当前正在学习网络计划。",
            "current_page": {
                "page_index": 1,
                "knowledge_title": "网络计划关键线路",
                "knowledge_summary": "继续聚焦关键线路、总时差和自由时差。",
            },
        },
        "version": 1,
        "entered_at": "",
        "last_touched_at": "",
        "source_turn_id": "turn-guide-1",
    }


@pytest.mark.asyncio
async def test_orchestrator_routes_cached_turn_semantic_decision_to_deep_question() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="semantic-router-grading",
        user_message="我选B",
        config_overrides={},
        metadata={
            "active_object": _active_object(),
            "turn_semantic_decision": {
                "relation_to_active_object": "answer_active_object",
                "next_action": "route_to_grading",
                "target_object_ref": {"object_type": "single_question", "object_id": "q_1"},
                "allowed_patch": ["update_answer_slot"],
                "confidence": 0.9,
                "reason": "用户正在回答当前题目。",
            },
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"


@pytest.mark.asyncio
async def test_orchestrator_routes_temporary_detour_to_chat_even_with_active_question() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="semantic-router-detour",
        user_message="我还有多少点数",
        config_overrides={},
        metadata={
            "active_object": _active_object(),
            "turn_semantic_decision": {
                "relation_to_active_object": "temporary_detour",
                "next_action": "route_to_general_chat",
                "target_object_ref": {"object_type": "single_question", "object_id": "q_1"},
                "allowed_patch": ["no_state_change"],
                "confidence": 0.85,
                "reason": "用户临时切去问账户问题。",
            },
        },
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "chat"


@pytest.mark.asyncio
async def test_orchestrator_routes_active_guide_page_continuation_to_chat() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="semantic-router-guide",
        user_message="继续刚才这个学习页面",
        config_overrides={},
        metadata={"active_object": _guide_active_object()},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "chat"
    assert context.metadata["semantic_router_mode"] == "primary"
    assert context.metadata["semantic_router_selected_capability"] == "chat"
    assert context.metadata["turn_semantic_decision"]["next_action"] == "route_to_guide"
    assert context.metadata["active_object"]["object_type"] == "guide_page"


@pytest.mark.asyncio
async def test_orchestrator_shadow_mode_keeps_legacy_route_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    async def _fake_preview(_context, _message):
        return {
            "relation_to_active_object": "answer_active_object",
            "next_action": "route_to_grading",
            "target_object_ref": {"object_type": "single_question", "object_id": "q_1"},
            "allowed_patch": ["update_answer_slot"],
            "confidence": 0.91,
            "reason": "shadow compare",
        }

    monkeypatch.setattr(orchestrator, "_preview_turn_semantic_decision", _fake_preview)

    context = UnifiedContext(
        session_id="semantic-router-shadow",
        user_message="随便聊聊",
        config_overrides={
            "semantic_router_enabled": True,
            "semantic_router_shadow_mode": True,
        },
        metadata={"active_object": _active_object()},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "chat"
    assert context.metadata["semantic_router_mode"] == "shadow"
    assert context.metadata["semantic_router_shadow_route"] == "deep_question"
    assert context.metadata["semantic_router_selected_capability"] == "chat"
    assert "turn_semantic_decision" not in context.metadata


@pytest.mark.asyncio
async def test_orchestrator_disabled_mode_skips_semantic_router() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="semantic-router-disabled",
        user_message="继续刚才这个学习页面",
        config_overrides={"semantic_router_enabled": False},
        metadata={"active_object": _guide_active_object()},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "chat"
    assert context.metadata["semantic_router_mode"] == "disabled"
    assert context.metadata["semantic_router_selected_capability"] == "chat"
    assert "turn_semantic_decision" not in context.metadata


@pytest.mark.asyncio
async def test_orchestrator_scope_excludes_guide_from_question_only_rollout() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="semantic-router-scope-guide",
        user_message="继续刚才这个学习页面",
        config_overrides={
            "semantic_router_enabled": True,
            "semantic_router_scope": "question_only",
        },
        metadata={"active_object": _guide_active_object()},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "chat"
    assert context.metadata["semantic_router_mode"] == "disabled"
    assert context.metadata["semantic_router_mode_reason"] == "scope_excluded"
    assert context.metadata["semantic_router_scope"] == "question_only"
    assert context.metadata["semantic_router_scope_match"] is False


@pytest.mark.asyncio
async def test_orchestrator_scope_keeps_question_in_question_only_rollout() -> None:
    orchestrator = ChatOrchestrator()
    registry = _FakeRegistry()
    orchestrator._cap_registry = registry  # type: ignore[attr-defined]

    context = UnifiedContext(
        session_id="semantic-router-scope-question",
        user_message="我选B",
        config_overrides={
            "semantic_router_enabled": True,
            "semantic_router_scope": "question_only",
        },
        metadata={"active_object": _active_object()},
        language="zh",
    )

    _ = [event async for event in orchestrator.handle(context)]

    assert registry.captured[0] == "deep_question"
    assert context.metadata["semantic_router_mode"] == "primary"
    assert context.metadata["semantic_router_scope_match"] is True
