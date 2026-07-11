"""Battle1 W3-T1 — 路由决策每轮至多执行一次（消双跑收权）.

旧病灶：turn_runtime 先用 getattr 调私有 ``_select_capability`` 选一次能力，
``orch.handle(context)`` 内部又无条件再跑一次——scene=None 带 hint 轮重跑
LLM 场景分类、review/practice 轮经 semantic_router Stage C 重调 followup
解释器（生产活体数据：followup 判定器占首答前阻塞分类器 ~79%）。

收权后：turn_runtime 经公共 ``select_capability`` 只选一次，把原值经
``handle(preselected_capability=...)`` 传入；handle 收到预选值时**不得**
再触发选择管线。本文件是"路由 LLM 每轮至多一次"的构造性 spy 证明
（按指挥官裁决：不加 metadata 计数字段，纯测试断言）。
"""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.core.context import UnifiedContext
from deeptutor.runtime.orchestrator import ChatOrchestrator


class _FakeBusCapability:
    manifest = None

    async def run(self, context: UnifiedContext, bus: Any) -> None:
        await bus.result({"response": "ok"}, source="fake")


class _FakeRegistry:
    def get(self, name: str) -> Any:
        return _FakeBusCapability()

    def list_capabilities(self) -> list[str]:
        return ["chat", "deep_question", "tutorbot"]

    def get_manifests(self) -> list[dict[str, Any]]:
        return []


async def _drain(agen) -> list[Any]:
    events = []
    async for event in agen:
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_handle_with_preselected_capability_skips_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """handle 收到预选能力时，选择管线（含其中的路由 LLM）零调用。"""
    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _FakeRegistry()  # type: ignore[attr-defined]

    calls = {"select": 0}

    async def _spy_select(context: UnifiedContext) -> str:
        calls["select"] += 1
        return "chat"

    monkeypatch.setattr(orchestrator, "_select_capability", _spy_select)

    context = UnifiedContext(
        session_id="s-single-selection-1",
        user_message="帮我出几道题练练",  # 含 hint 词，旧第二跑会重进 lifecycle
        language="zh",
    )
    await _drain(orchestrator.handle(context, preselected_capability="chat"))
    assert calls["select"] == 0, "handle 收到预选能力后不得重跑选择管线（双跑复发）"


@pytest.mark.asyncio
async def test_handle_without_preselection_selects_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """无预选（CLI/SDK 路径）时，handle 自选恰好一次——不多不少。"""
    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _FakeRegistry()  # type: ignore[attr-defined]

    calls = {"select": 0}

    async def _spy_select(context: UnifiedContext) -> str:
        calls["select"] += 1
        return "chat"

    monkeypatch.setattr(orchestrator, "_select_capability", _spy_select)

    context = UnifiedContext(
        session_id="s-single-selection-2",
        user_message="解析一下这道真题",
        language="zh",
    )
    await _drain(orchestrator.handle(context))
    assert calls["select"] == 1


@pytest.mark.asyncio
async def test_select_capability_public_api_delegates_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """公共 select_capability 是私有选择器的唯一薄封装（消灭 getattr 私有依赖）。"""
    orchestrator = ChatOrchestrator()

    calls = {"select": 0}

    async def _spy_select(context: UnifiedContext) -> str:
        calls["select"] += 1
        return "tutorbot"

    monkeypatch.setattr(orchestrator, "_select_capability", _spy_select)

    context = UnifiedContext(session_id="s-single-selection-3", user_message="你好", language="zh")
    result = await orchestrator.select_capability(context)
    assert result == "tutorbot"
    assert calls["select"] == 1


@pytest.mark.asyncio
async def test_routing_llm_at_most_once_per_turn_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端 spy：select_capability 一次 + handle(preselected) 全程，
    lifecycle 场景 LLM 与 followup 解释 LLM 的调用次数合计 ≤1。

    覆盖 scene=None 带 hint 轮（旧双跑下场景分类 LLM 会跑 2 次）。"""
    import deeptutor.services.question_lifecycle_skills as qls
    import deeptutor.services.question_followup as qf

    orchestrator = ChatOrchestrator()
    orchestrator._cap_registry = _FakeRegistry()  # type: ignore[attr-defined]

    llm_calls = {"scene": 0, "followup": 0}

    async def _spy_scene_proposal(*args: Any, **kwargs: Any):
        llm_calls["scene"] += 1
        return None

    async def _spy_followup(*args: Any, **kwargs: Any):
        llm_calls["followup"] += 1
        return None

    monkeypatch.setattr(qls, "_llm_question_lifecycle_scene_proposal", _spy_scene_proposal, raising=True)
    monkeypatch.setattr(qf, "interpret_question_followup_action", _spy_followup, raising=False)

    context = UnifiedContext(
        session_id="s-single-selection-4",
        user_message="帮我测一测消防设施这块掌握得怎么样",  # 含"测"hint、无 active_object → 旧路径必进场景 LLM
        config_overrides={"bot_id": "construction-exam-coach"},
        language="zh",
    )

    selected = await orchestrator.select_capability(context)
    await _drain(orchestrator.handle(context, preselected_capability=selected))

    total = llm_calls["scene"] + llm_calls["followup"]
    assert total <= 1, (
        f"路由 LLM 每轮至多一次被击穿: scene={llm_calls['scene']} followup={llm_calls['followup']}"
    )


def _active_single_question(session_id: str) -> dict:
    return {
        "object_type": "single_question",
        "object_id": "q1",
        "scope": {"domain": "session", "session_id": session_id},
        "state_snapshot": {
            "question_id": "q1",
            "question": "某工程屋面坡度最小值是（ ）。",
            "question_type": "choice",
            "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
            "correct_answer": "C",
        },
        "version": 1,
    }


@pytest.mark.asyncio
async def test_single_run_preserves_deep_question_demote_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Battle1 对抗审查 MAJOR-1: 旧双跑意外把 deep_question preselect demote
    守卫套在了服务端选择上(run2 读到 run1 写的 active_capability)——净生产
    行为=非题目续轮 demote 回默认聊天能力。单跑收权后该守卫必须确定性保留。"""
    orchestrator = ChatOrchestrator()
    sid = "s-demote-parity"

    async def _routed_deep_question(context: UnifiedContext) -> str:
        # 模拟语义路由(LLM 权威)选出 deep_question 且 scene=None 的第一跑产出
        context.metadata.setdefault("question_lifecycle_scene", None)
        return "deep_question"

    monkeypatch.setattr(orchestrator, "_select_capability", _routed_deep_question)

    context = UnifiedContext(
        session_id=sid,
        user_message="帮我把这段话润色一下发朋友圈",  # 非题目措辞: 全部 _looks_like_* 启发式为负
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={"active_object": _active_single_question(sid)},
        language="zh",
    )
    selected = await orchestrator.select_capability(context)
    assert selected != "deep_question", "非题目续轮的服务端 deep_question 选择必须被 demote(旧净行为)"
    assert (
        context.metadata.get("semantic_router_mode_reason")
        == "deep_question_preselect_demoted_non_question_turn"
    )


@pytest.mark.asyncio
async def test_single_run_demote_guard_spares_submission_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """提交作答轮(启发式命中)不 demote——判分入口必达(硬约束40)。"""
    orchestrator = ChatOrchestrator()
    sid = "s-demote-spare-submission"

    async def _routed_deep_question(context: UnifiedContext) -> str:
        context.metadata.setdefault("question_lifecycle_scene", None)
        return "deep_question"

    monkeypatch.setattr(orchestrator, "_select_capability", _routed_deep_question)

    context = UnifiedContext(
        session_id=sid,
        user_message="我选C",
        config_overrides={"bot_id": "construction-exam-coach"},
        metadata={"active_object": _active_single_question(sid)},
        language="zh",
    )
    selected = await orchestrator.select_capability(context)
    assert selected == "deep_question"
