from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities import deep_question as deep_question_module
from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.agents.question.agents.submission_grader_agent import SubmissionGraderAgent
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus


def _install_module(monkeypatch: pytest.MonkeyPatch, fullname: str, **attrs: Any) -> None:
    parts = fullname.split(".")
    for idx in range(1, len(parts)):
        pkg_name = ".".join(parts[:idx])
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = []  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, pkg_name, pkg)
            if idx > 1:
                parent = sys.modules[".".join(parts[: idx - 1])]
                setattr(parent, parts[idx - 1], pkg)

    module = types.ModuleType(fullname)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, fullname, module)
    if len(parts) > 1:
        parent = sys.modules[".".join(parts[:-1])]
        monkeypatch.setattr(parent, parts[-1], module, raising=False)


async def _collect_events(run_coro) -> list[StreamEvent]:
    bus = StreamBus()
    events: list[StreamEvent] = []

    async def _consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0)
    await run_coro(bus)
    await asyncio.sleep(0)
    await bus.close()
    await consumer
    return events


@pytest.mark.asyncio
async def test_deep_question_uses_deterministic_feedback_for_choice_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("objective grading should not instantiate SubmissionGraderAgent")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚做完一道选择题。",
            "question_followup_context": {
                "question_id": "q_5",
                "question": "流水步距反映的是什么？",
                "question_type": "choice",
                "options": {"A": "工期", "B": "相邻专业队投入间隔"},
                "correct_answer": "B",
                "explanation": "步距看相邻专业队之间的时间间隔。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["user_answer"] == "B"
    assert result_event.metadata["is_correct"] is True
    assert result_event.metadata["question_followup_context"]["user_answer"] == "B"
    assert (
        result_event.metadata["question_followup_context"]["construction_grading_result"]["authority"]
        == "construction_grading"
    )
    assert result_event.metadata["construction_grading_result"]["authority"] == "construction_grading"
    assert "阅卷结论" in result_event.metadata["response"]
    assert "正确答案：** B" in result_event.metadata["response"]
    assert result_event.metadata["grading_kernel"] == "mcq"
    assert result_event.metadata["correct_answer_present"] is True
    assert result_event.metadata["question_authority_source"] == "active_object"

    # plan §Phase 5 / Batch E.2 Gap 5 — progressive_disclosure payload 必须进入 result.


@pytest.mark.asyncio
async def test_deep_question_mixed_submission_preserves_generation_next_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed while grading takes priority")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("objective grading should use deterministic feedback")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="我答 B 再出 3 题",
        language="zh",
        metadata={
            "raw_user_message": "我答 B 再出 3 题",
            "conversation_context_text": "用户刚做完一道选择题。",
            "question_followup_context": {
                "question_id": "q_5",
                "question": "小佑题库提供什么服务？",
                "question_type": "choice",
                "options": {"A": "免费听课", "B": "在线刷题", "C": "售后反馈", "D": "课程表"},
                "correct_answer": "B",
                "explanation": "小佑题库对应在线刷题。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["user_answer"] == "B"
    assert "阅卷结论" in response
    assert "### 下一步" in response
    assert "继续给你出 3 题" in response
    disclosure = result_event.metadata.get("progressive_disclosure")
    assert isinstance(disclosure, dict), "result must include progressive_disclosure payload"
    assert disclosure.get("verdict"), "progressive_disclosure must expose verdict"
    assert "primary_next_action" in disclosure
    primary = disclosure["primary_next_action"]
    assert primary.get("slug") and primary.get("label")
    # 答对场景：pacing 默认 hold，主行动 = 再练3题；首屏 verdict <= 120 字
    assert len(disclosure["verdict"]) <= 120
    # public payload 不应泄露 grading_key（虽 result_payload 本身在 turn_runtime 边界 redact，
    # 但 progressive_disclosure 内部不应携带 grading_key 子字段）
    import json as _json
    assert "grading_key" not in _json.dumps(disclosure, ensure_ascii=False)


@pytest.mark.asyncio
async def test_deep_question_deterministic_choice_feedback_explains_without_authored_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FailingSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("objective grading should not require LLM for basic explanation")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FailingSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="我选C",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚做完一道选择题。",
            "question_followup_context": {
                "question_id": "q_no_analysis",
                "question": "主体结构分部工程包含下列哪一项？",
                "question_type": "choice",
                "options": {"A": "地基基础", "B": "建筑屋面", "C": "装饰装修", "D": "钢结构"},
                "correct_answer": "D",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is False
    assert "阅卷结论" in response
    assert "解析" in response
    assert "你的答案：** C（装饰装修）" in response
    assert "正确答案：** D（钢结构）" in response
    assert "正确选项是 D（钢结构）" in response
    assert "逐项解析" in response
    assert "C. 装饰装修：误选项" in response
    assert "D. 钢结构：正确项" in response
    assert "你为什么会错" in response
    assert "采分点" in response
    assert "易错点" in response
    assert "记忆口诀" in response


@pytest.mark.asyncio
async def test_deep_question_deep_choice_grading_uses_rag_grounded_grader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_trace_callback(self, callback: Any) -> None:
            captured["trace_callback"] = callback

        async def process(self, **kwargs: Any) -> str:
            captured["grader_kwargs"] = kwargs
            response = (
                "## 📊 阅卷结论\n错误，正确答案 B。\n\n"
                "## 🧐 解析\n双扇防火门应按顺序关闭，不能理解成自动关闭。\n\n"
                "## ⚠️ 易错点\n| 易错理解 | 正确抓手 |\n| --- | --- |\n| 自动关闭 | 按顺序关闭 |\n\n"
                "## 🎯 核心要点\n✅ 命中：知道在考防火门关闭要求。\n❌ 遗漏：双扇门顺序器保证按顺序关闭。\n\n"
                "## 🚀 下一步建议\n现在把“双扇防火门按顺序关闭”抄 1 遍。\n\n"
                "📌 收尾提醒：双扇门不是同时、自动、手动，关键词是按顺序。"
            )
            callback = kwargs.get("on_content_chunk")
            if callback is not None:
                first = "## 📊 阅卷结论\n错误，正确答案 B。\n\n"
                second = response[len(first):]
                await callback(first)
                await callback(second)
            return response

    async def fake_rag_search(query: str, kb_name: str | None = None, **kwargs: Any) -> dict[str, Any]:
        captured["rag_query"] = query
        captured["rag_kb_name"] = kb_name
        captured["rag_kwargs"] = kwargs
        return {
            "content": "【规范依据】双扇防火门应具有按顺序自行关闭的功能，顺序器用于保证先后关闭。",
            "sources": [
                {
                    "title": "建筑防火门规范考点",
                    "content": "双扇防火门应按顺序关闭。",
                    "source_type": "standard",
                    "chunk_id": "std-fire-door-001",
                }
            ],
            "evidence_bundle": {
                "sources": [
                    {
                        "title": "建筑防火门规范考点",
                        "content": "双扇防火门应按顺序关闭。",
                        "source_type": "standard",
                        "chunk_id": "std-fire-door-001",
                    }
                ]
            },
        }

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )
    monkeypatch.setattr(deep_question_module, "rag_search", fake_rag_search, raising=False)

    context = UnifiedContext(
        user_message="我选C",
        language="zh",
        knowledge_bases=["construction-exam"],
        metadata={
            "selected_mode": "deep",
            "conversation_context_text": "上一轮题目问：双扇防火门关闭顺序。",
            "question_followup_context": {
                "question_id": "q_fire_door",
                "question": "关于双扇防火门关闭要求，下列说法正确的是？",
                "question_type": "choice",
                "options": {
                    "A": "同时关闭",
                    "B": "按顺序关闭",
                    "C": "自动关闭",
                    "D": "手动关闭",
                },
                "correct_answer": "B",
                "explanation": "双扇防火门应按顺序关闭。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    content_events = [event for event in events if event.type == StreamEventType.CONTENT]
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is False
    assert result_event.metadata["question_followup_context"]["correct_answer"] == "B"
    assert result_event.metadata["construction_grading_result"]["authority"] == "construction_grading"
    assert captured["rag_kb_name"] == "construction-exam"
    assert "双扇防火门关闭要求" in captured["rag_query"]
    assert captured["rag_kwargs"]["intent"] == "question_grading_explanation"
    assert captured["grader_kwargs"]["question_context"]["is_correct"] is False
    assert callable(captured["grader_kwargs"]["on_content_chunk"])
    assert "双扇防火门应具有按顺序自行关闭" in captured["grader_kwargs"]["grounding_context"]
    assert "双扇防火门应按顺序关闭" in result_event.metadata["response"]
    assert len(content_events) == 2
    assert "".join(event.content for event in content_events) == result_event.metadata["response"]
    assert result_event.metadata["grading_explanation_grounded"] is True
    assert result_event.metadata["grading_grounding_sources"][0]["chunk_id"] == "std-fire-door-001"


@pytest.mark.asyncio
async def test_deep_question_fast_wrong_choice_uses_rag_grounded_grader_when_kb_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_trace_callback(self, callback: Any) -> None:
            captured["trace_callback"] = callback

        async def process(self, **kwargs: Any) -> str:
            captured["grader_kwargs"] = kwargs
            return (
                "## 📊 阅卷结论\n错误，正确答案 B。\n\n"
                "## 🧐 解析\n室外临时消火栓应距路边不大于 2m，"
                "距拟建房屋不小于 5m 且不大于 25m；你选的 C 把房屋距离误记成 2m 到 15m。"
            )

    async def fake_rag_search(query: str, kb_name: str | None = None, **kwargs: Any) -> dict[str, Any]:
        captured["rag_query"] = query
        captured["rag_kb_name"] = kb_name
        captured["rag_kwargs"] = kwargs
        return {
            "content": "【规范依据】室外临时消火栓距路边不应大于2m，距拟建房屋不应小于5m且不应大于25m。",
            "sources": [
                {
                    "title": "施工现场临时消防设施",
                    "content": "临时消火栓距路边不大于2m，距拟建房屋5m至25m。",
                    "source_type": "questions_bank",
                    "chunk_id": "fire-hydrant-distance-001",
                }
            ],
        }

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )
    monkeypatch.setattr(deep_question_module, "rag_search", fake_rag_search, raising=False)

    context = UnifiedContext(
        user_message="我选C",
        language="zh",
        knowledge_bases=["construction-exam"],
        metadata={
            "selected_mode": "fast",
            "question_followup_context": {
                "question_id": "q_fire_hydrant",
                "question": "关于施工现场临时消火栓设置要求，下列说法正确的是？",
                "question_type": "choice",
                "options": {
                    "A": "距路边不应大于5m，距拟建房屋不小于5m且不大于25m",
                    "B": "距路边不应大于2m，距拟建房屋不小于5m且不大于25m",
                    "C": "距路边不应大于2m，距拟建房屋不小于2m且不大于15m",
                    "D": "距路边不应大于5m，距拟建房屋不小于2m且不大于15m",
                },
                "correct_answer": "B",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is False
    assert result_event.metadata["construction_grading_result"]["authority"] == "construction_grading"
    assert captured["rag_kb_name"] == "construction-exam"
    assert "施工现场临时消火栓设置要求" in captured["rag_query"]
    assert captured["rag_kwargs"]["intent"] == "question_grading_explanation"
    assert "室外临时消火栓应距路边不大于 2m" in result_event.metadata["response"]
    assert result_event.metadata["grading_explanation_grounded"] is True


@pytest.mark.asyncio
async def test_deep_question_reveals_objective_answer_without_followup_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for follow-up mode")

    class FailingFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("objective answer reveal should use question authority, not LLM")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.followup_agent",
        FollowupAgent=FailingFollowupAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="告诉我答案，并具体解析这道题",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚做完一道选择题。",
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
            },
            "question_followup_action": {
                "intent": "ask_followup",
            },
            "question_followup_context": {
                "question_id": "q_reveal",
                "question": "主体结构分部工程包含下列哪一项？",
                "question_type": "choice",
                "options": {"A": "地基基础", "B": "建筑屋面", "C": "装饰装修", "D": "钢结构"},
                "correct_answer": "D",
                "user_answer": "C",
                "is_correct": False,
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert result_event.metadata["mode"] == "followup"
    assert "答案与解析" in response
    assert "正确答案：** D（钢结构）" in response
    assert "正确选项是 D（钢结构）" in response
    assert "逐项解析" in response
    assert "采分点" in response
    assert "易错点" in response
    assert "记忆口诀" in response


@pytest.mark.asyncio
async def test_deep_question_revealed_objective_answer_honors_explicit_brevity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for follow-up mode")

    class FailingFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("brief objective answer reveal should use question authority, not LLM")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.followup_agent",
        FollowupAgent=FailingFollowupAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="是不是因为你按旧题库字母没看我这轮选项？一句话。",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚做完一道选择题，系统已展示过答案。",
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
            },
            "question_followup_action": {
                "intent": "ask_followup",
            },
            "question_followup_context": {
                "question_id": "q_brief_reveal",
                "question": "压型金属板采用轻型屋面时，屋面最小坡度宜为多少？",
                "question_type": "choice",
                "options": {"A": "5%", "B": "1%", "C": "2%", "D": "3%"},
                "correct_answer": "A",
                "user_answer": "A",
                "is_correct": True,
                "explanation": "屋面最小坡度：压型金属板：5%。",
                "reveal_answers": True,
                "reveal_explanations": True,
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert result_event.metadata["mode"] == "followup"
    assert "A（5%）" in response
    assert "按你这轮题面" in response
    assert "答案与解析" not in response
    assert "逐项解析" not in response
    assert "采分点" not in response
    assert "\n" not in response


@pytest.mark.asyncio
async def test_deep_question_option_hypothetical_followup_gives_targeted_scoring_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for follow-up mode")

    class FailingFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("answered objective option scoring should use question authority")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.followup_agent",
        FollowupAgent=FailingFollowupAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="C",
        language="zh",
        metadata={
            "raw_user_message": "这里的最高点是不是屋脊？如果我选B，你会怎么扣？",
            "conversation_context_text": "用户刚做完一道选择题。",
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
            },
            "question_followup_action": {
                "intent": "ask_followup",
            },
            "question_followup_context": {
                "question_id": "q_roof",
                "question": "压型金属板采用轻型屋面时，屋面最小坡度宜为多少？",
                "question_type": "choice",
                "options": {"A": "5%", "B": "屋脊", "C": "3%", "D": "最高点"},
                "correct_answer": "D",
                "user_answer": "C",
                "is_correct": False,
                "explanation": "题干问的是压型金属板屋面构造中的最高点。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert result_event.metadata["mode"] == "followup"
    assert "B（屋脊）" in response
    assert "不得分" in response
    assert "D（最高点）" in response
    assert "改写标准答案" in response


@pytest.mark.asyncio
async def test_deep_question_reveals_written_reference_without_followup_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for follow-up mode")

    class FailingFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("written answer reveal should use stored question authority")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.followup_agent",
        FollowupAgent=FailingFollowupAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="告诉我答案，并具体解析这道题",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚做完一道案例判断题。",
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
            },
            "question_followup_action": {
                "intent": "ask_followup",
            },
            "question_followup_context": {
                "question_id": "q_written_reveal",
                "question": "幕墙与主体结构的连接设计应符合哪些规定？",
                "question_type": "written",
                "correct_answer": (
                    "1. 应具有适应主体结构层间变形的能力；"
                    "2. 预埋件、锚固件应能承受幕墙传递的荷载和作用。"
                ),
                "user_answer": "连接要牢固。",
                "is_correct": False,
                "knowledge_context": "【GBT51231-2016 §6.4.3】幕墙与主体结构的连接设计应符合下列规定。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert result_event.metadata["mode"] == "followup"
    assert "答案与解析" in response
    assert "参考答案：** 1. 应具有适应主体结构层间变形的能力" in response
    assert "解析" in response
    assert "依据：【GBT51231-2016 §6.4.3】" in response
    assert "本题按参考答案的关键点给分" in response


@pytest.mark.asyncio
async def test_deep_question_blocks_unanswered_direct_answer_reveal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for follow-up mode")

    class FailingFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("unanswered reveal block should not call follow-up LLM")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.followup_agent",
        FollowupAgent=FailingFollowupAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="直接告诉我答案",
        language="zh",
        metadata={
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
            },
            "question_followup_action": {
                "intent": "ask_followup",
            },
            "question_followup_context": {
                "question_id": "q_unanswered_reveal",
                "question": "验槽通常主要采用什么方法？",
                "question_type": "choice",
                "options": {"A": "观察法", "B": "钎探法"},
                "correct_answer": "A",
                "explanation": "观察法为主，钎探法为辅。",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert result_event.metadata["mode"] == "followup"
    assert "练习阶段不公开答案" in response
    assert "观察法" not in response
    assert "正确答案" not in response


@pytest.mark.asyncio
async def test_deep_question_fail_closed_when_choice_answer_authority_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("missing MCQ authority must not fall back to LLM grading")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚做完一道选择题。",
            "question_followup_context": {
                "question_id": "tb_q_1",
                "question": "主体结构施工中，模板拆除应优先满足哪项要求？",
                "question_type": "choice",
                "options": {"A": "进度计划", "B": "混凝土强度", "C": "材料周转", "D": "现场人数"},
                "correct_answer": "",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["grading_blocked"] is True
    assert result_event.metadata["is_correct"] is None
    assert result_event.metadata["grading_kernel"] == "mcq"
    assert result_event.metadata["correct_answer_present"] is False
    assert result_event.metadata["question_authority_source"] == "missing"
    assert "缺少标准答案" in result_event.metadata["response"]
    assert "construction_grading_result" not in result_event.metadata


@pytest.mark.asyncio
async def test_deep_question_recovers_missing_choice_answer_from_questions_bank_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("recovered objective grading should not instantiate SubmissionGraderAgent")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        metadata={
            "exact_question": {
                "id": "tb_q_1",
                "answer_kind": "mcq",
                "stem": "主体结构施工中，模板拆除应优先满足哪项要求？",
                "options": [
                    {"key": "A", "value": "进度计划"},
                    {"key": "B", "value": "混凝土强度"},
                    {"key": "C", "value": "材料周转"},
                    {"key": "D", "value": "现场人数"},
                ],
                "correct_answer": "B",
                "analysis": "模板拆除必须满足混凝土强度及安全要求。",
            },
            "question_followup_context": {
                "question_id": "tb_q_1",
                "question": "主体结构施工中，模板拆除应优先满足哪项要求？",
                "question_type": "choice",
                "options": {"A": "进度计划", "B": "混凝土强度", "C": "材料周转", "D": "现场人数"},
                "correct_answer": "",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is True
    assert result_event.metadata["grading_kernel"] == "mcq"
    assert result_event.metadata["correct_answer_present"] is True
    assert result_event.metadata["question_authority_source"] == "questions_bank"
    assert result_event.metadata["question_followup_context"]["correct_answer"] == "B"


@pytest.mark.asyncio
async def test_deep_question_recovers_missing_choice_answer_from_grading_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """plan §Step 3.4 — lightweight_batch_llm 把答案写在 ``items[i].grading_key.correct_answer``;
    grader 必须把它当作 priority #1 authority，比 questions_bank 更优先。"""

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError(
                "recovered objective grading should not instantiate SubmissionGraderAgent"
            )

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        metadata={
            "question_followup_context": {
                "question_id": "lt_q_1",
                "question": "施工现场安全管理责任主体的第一责任人是？",
                "question_type": "choice",
                "options": {
                    "A": "项目经理",
                    "B": "建设单位负责人",
                    "C": "施工班组长",
                    "D": "安全员",
                },
                # plan §Step 3.4 — top-level slot intentionally empty;
                # lightweight_batch_llm only populates grading_key.
                "correct_answer": "",
                "grading_key": {
                    "correct_answer": "B",
                    "scoring_points": [],
                    "common_traps": [],
                    "minimal_rationale": "",
                    "source": "lightweight_batch_llm",
                },
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is True
    assert result_event.metadata["grading_kernel"] == "mcq"
    assert result_event.metadata["correct_answer_present"] is True
    assert result_event.metadata["question_authority_source"] == "grading_key"
    assert result_event.metadata["question_followup_context"]["correct_answer"] == "B"


@pytest.mark.asyncio
async def test_deep_question_recomputes_batch_after_recovering_missing_choice_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("recovered objective batch grading should not instantiate SubmissionGraderAgent")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="第1题：B；第2题：C",
        language="zh",
        metadata={
            "exact_question": [
                {
                    "id": "tb_q_1",
                    "answer_kind": "mcq",
                    "stem": "模板拆除应优先满足哪项要求？",
                    "options": [
                        {"key": "A", "value": "进度计划"},
                        {"key": "B", "value": "混凝土强度"},
                    ],
                    "correct_answer": "B",
                },
                {
                    "id": "tb_q_2",
                    "answer_kind": "mcq",
                    "stem": "钢筋进场复验应重点核查什么？",
                    "options": [
                        {"key": "A", "value": "颜色"},
                        {"key": "C", "value": "力学性能"},
                    ],
                    "correct_answer": "C",
                },
            ],
            "question_followup_context": {
                "question_id": "quiz_recover_batch",
                "question": "第1题...\n第2题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "tb_q_1",
                        "question": "模板拆除应优先满足哪项要求？",
                        "question_type": "choice",
                        "options": {"A": "进度计划", "B": "混凝土强度"},
                        "correct_answer": "",
                    },
                    {
                        "question_id": "tb_q_2",
                        "question": "钢筋进场复验应重点核查什么？",
                        "question_type": "choice",
                        "options": {"A": "颜色", "C": "力学性能"},
                        "correct_answer": "",
                    },
                ],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is True
    assert result_event.metadata["grading_kernel"] == "mcq"
    assert result_event.metadata["correct_answer_present"] is True
    assert result_event.metadata["question_authority_source"] == "questions_bank"
    assert result_event.metadata["construction_grading_result"]["score_awarded"] == 2.0
    assert [item["is_correct"] for item in result_event.metadata["question_followup_context"]["items"]] == [
        True,
        True,
    ]


@pytest.mark.asyncio
async def test_deep_question_clears_stale_item_flags_when_recovering_batch_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("recovered objective batch grading should not instantiate SubmissionGraderAgent")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="第1题：B；第2题：C",
        language="zh",
        metadata={
            "exact_question": [
                {
                    "id": "tb_q_1",
                    "answer_kind": "mcq",
                    "stem": "模板拆除应优先满足哪项要求？",
                    "options": [{"key": "B", "value": "混凝土强度"}],
                    "correct_answer": "B",
                },
                {
                    "id": "tb_q_2",
                    "answer_kind": "mcq",
                    "stem": "钢筋进场复验应重点核查什么？",
                    "options": [{"key": "C", "value": "力学性能"}],
                    "correct_answer": "C",
                },
            ],
            "question_followup_context": {
                "question_id": "quiz_stale_batch",
                "question": "第1题...\n第2题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "tb_q_1",
                        "question": "模板拆除应优先满足哪项要求？",
                        "question_type": "choice",
                        "options": {"A": "进度计划", "B": "混凝土强度"},
                        "correct_answer": "",
                        "user_answer": "B",
                        "is_correct": False,
                    },
                    {
                        "question_id": "tb_q_2",
                        "question": "钢筋进场复验应重点核查什么？",
                        "question_type": "choice",
                        "options": {"A": "颜色", "C": "力学性能"},
                        "correct_answer": "",
                        "user_answer": "C",
                        "is_correct": False,
                    },
                ],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["is_correct"] is True
    assert result_event.metadata["construction_grading_result"]["score_awarded"] == 2.0
    assert [item["is_correct"] for item in result_event.metadata["question_followup_context"]["items"]] == [
        True,
        True,
    ]


@pytest.mark.asyncio
async def test_deep_question_fail_closed_when_batch_choice_recovery_is_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("partial MCQ recovery must not fall back to LLM grading")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="第1题：B；第2题：C",
        language="zh",
        metadata={
            "exact_question": [
                {
                    "id": "tb_q_1",
                    "answer_kind": "mcq",
                    "stem": "模板拆除应优先满足哪项要求？",
                    "options": [{"key": "B", "value": "混凝土强度"}],
                    "correct_answer": "B",
                }
            ],
            "question_followup_context": {
                "question_id": "quiz_partial_recover",
                "question": "第1题...\n第2题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "tb_q_1",
                        "question": "模板拆除应优先满足哪项要求？",
                        "question_type": "choice",
                        "options": {"A": "进度计划", "B": "混凝土强度"},
                        "correct_answer": "",
                    },
                    {
                        "question_id": "tb_q_2",
                        "question": "钢筋进场复验应重点核查什么？",
                        "question_type": "choice",
                        "options": {"A": "颜色", "C": "力学性能"},
                        "correct_answer": "",
                    },
                ],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["grading_blocked"] is True
    assert result_event.metadata["is_correct"] is None
    assert result_event.metadata["correct_answer_present"] is False
    assert result_event.metadata["question_authority_source"] == "missing"
    assert "construction_grading_result" not in result_event.metadata
    assert [
        item.get("is_correct")
        for item in result_event.metadata["question_followup_context"]["items"]
    ] == [None, None]


@pytest.mark.asyncio
async def test_deep_question_uses_deterministic_feedback_for_batch_choice_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("objective batch grading should not instantiate SubmissionGraderAgent")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="第1题：C；第2题：A；第3题：B",
        language="zh",
        metadata={
            "conversation_context_text": "用户刚完成一组建筑构造选择题。",
            "question_followup_context": {
                "question_id": "quiz_batch",
                "question": "第1题...\n第2题...\n第3题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "choice",
                        "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                        "correct_answer": "C",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "choice",
                        "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                        "correct_answer": "A",
                    },
                    {
                        "question_id": "q_3",
                        "question": "题3",
                        "question_type": "choice",
                        "options": {"A": "A3", "B": "B3", "C": "C3", "D": "D3"},
                        "correct_answer": "D",
                    },
                ],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is False
    assert result_event.metadata["question_followup_context"]["items"][0]["user_answer"] == "C"
    assert result_event.metadata["question_followup_context"]["items"][2]["is_correct"] is False
    assert "得分：** 2/3题" in result_event.metadata["response"]
    assert "第3题：错误" in result_event.metadata["response"]


@pytest.mark.asyncio
async def test_deep_question_routes_subjective_case_submission_to_grading_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeSubmissionGraderAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs
            self._trace_callback = None

        def set_trace_callback(self, callback) -> None:
            self._trace_callback = callback

        async def process(self, **kwargs: Any) -> str:
            captured["process"] = kwargs
            grading_result = kwargs["question_context"]["construction_grading_result"]
            assert kwargs["user_message"] == raw_answer
            assert kwargs["question_context"]["user_answer"] == (
                "共用一个开关箱不妥，应采用专用开关箱"
            )
            assert grading_result["authority"] == "construction_grading"
            assert grading_result["type"] == "case"
            assert grading_result["score_awarded"] == 1.0
            assert grading_result["max_score"] == 3.0
            return "得分：1分（满分3分）。漏写临时用电施工组织设计和插座插头活动连接。"

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FakeSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    raw_answer = "我的答案：共用一个开关箱不妥，应采用专用开关箱。请按案例题阅卷标准批改。"
    context = UnifiedContext(
        user_message=f"[History Context]\nUser selected E earlier.\n\n[User Question]\n{raw_answer}",
        language="zh",
        metadata={
            "raw_user_message": raw_answer,
            "conversation_context_text": "用户刚做完一道建筑实务案例题。",
            "turn_semantic_decision": {
                "next_action": "route_to_grading",
            },
            "question_followup_action": {
                "intent": "answer_questions",
                "answers": [
                    {
                        "question_id": "case-9006",
                        "answer": "E",
                    }
                ],
            },
            "question_followup_context": {
                "question_id": "case-9006",
                "question": "指出事件二中临时用电管理的不妥之处。",
                "question_type": "case",
                "correct_answer": (
                    "不妥之处：1.未编制临时用电施工组织设计；2.共用一个开关箱；"
                    "3.插座插头活动连接。正确做法：1.应编制单项施工用电方案；"
                    "2.应采用专用开关箱；3.插头和插座应配套使用，不得活动连接。"
                ),
                "concentration": "临时用电",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["user_answer"] == "共用一个开关箱不妥，应采用专用开关箱"
    assert result_event.metadata["construction_grading_result"]["score_awarded"] == 1.0
    assert result_event.metadata["construction_grading_result"]["max_score"] == 3.0


@pytest.mark.asyncio
async def test_deep_question_fast_mode_uses_deterministic_grading_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FailingSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("fast deterministic grading should not instantiate SubmissionGraderAgent")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=FailingSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )

    context = UnifiedContext(
        user_message="第1题选B，第2题选C。你帮我批改，并且针对我错的地方解释一下。",
        language="zh",
        metadata={
            "selected_mode": "fast",
            "turn_semantic_decision": {
                "next_action": "route_to_grading",
            },
            "question_followup_action": {
                "intent": "answer_questions",
                "answers": [
                    {"question_id": "q_1", "answer": "B"},
                    {"question_id": "q_2", "answer": "C"},
                ],
            },
            "question_followup_context": {
                "question_id": "quiz_batch",
                "question": "第1题...\n第2题...",
                "question_type": "choice",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "题1",
                        "question_type": "choice",
                        "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                        "correct_answer": "B",
                        "explanation": "第1题考查流水步距定义。",
                    },
                    {
                        "question_id": "q_2",
                        "question": "题2",
                        "question_type": "choice",
                        "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                        "correct_answer": "B",
                        "explanation": "第2题关键在于先抓住同一施工段的起算点。",
                    },
                ],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["is_correct"] is False
    assert "得分" in result_event.metadata["response"]
    assert "第2题：错误" in result_event.metadata["response"]
    assert "第2题关键在于先抓住同一施工段的起算点。" in result_event.metadata["response"]


def test_build_submission_context_marks_oversight_for_negative_stem() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question": "下列关于流水施工的说法，错误的是哪一项？",
            "question_type": "choice",
            "correct_answer": "C",
            "explanation": "题干问的是错误项，关键在于先识别否定式设问。",
        },
        "A",
    )

    assert context["diagnosis"] == "OVERSIGHT"
    assert context["score"] == 0


def test_build_submission_context_marks_memory_decay_for_numeric_fact() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question": "防水混凝土养护时间至少应为多少天？",
            "question_type": "choice",
            "correct_answer": "B",
            "explanation": "规范要求连续养护不少于14天。",
        },
        "A",
    )

    assert context["diagnosis"] == "MEMORY_DECAY"


def test_extract_submission_answer_accepts_slip_style_submission() -> None:
    capability = DeepQuestionCapability()

    answer = capability._build_submission_context(
        {
            "question": "流水施工题",
            "question_type": "choice",
            "correct_answer": "B",
        },
        "B",
    )["user_answer"]

    assert answer == "B"


def test_build_submission_context_accepts_judgment_style_submission() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question": "判断：流水步距反映相邻专业队投入的时间间隔。",
            "question_type": "choice",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "B",
        },
        "B",
    )

    assert context["is_correct"] is True
    assert context["diagnosis"] == "CORRECT"


def test_build_submission_context_attaches_authoritative_mcq_grading_result() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question_id": "supabase-12233",
            "question": "某多选题",
            "question_type": "multi_choice",
            "options": {"A": "正确项", "B": "正确项", "C": "正确项", "D": "正确项", "E": "干扰项"},
            "correct_answer": "ABCD",
            "explanation": "E 不符合题意。",
            "concentration": "建筑实务",
        },
        "AE",
    )

    result = context["construction_grading_result"]
    assert result["type"] == "mcq"
    assert result["authority"] == "construction_grading"
    assert result["score_awarded"] == 0.0
    assert result["max_score"] == 1.0
    assert result["correct_answer"] == "ABCD"
    assert result["extra_options"] == ["E"]
    assert result["missed_options"] == ["B", "C", "D"]


def test_build_submission_context_attaches_authoritative_case_grading_result() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question_id": "case-9006",
            "question": "指出事件二中临时用电管理的不妥之处。",
            "question_type": "case",
            "correct_answer": (
                "不妥之处：1.未编制临时用电施工组织设计；2.共用一个开关箱；"
                "3.插座插头活动连接。正确做法：1.应编制单项施工用电方案；"
                "2.应采用专用开关箱；3.插头和插座应配套使用，不得活动连接。"
            ),
            "concentration": "临时用电",
        },
        "共用一个开关箱不妥，应采用专用开关箱。",
    )

    result = context["construction_grading_result"]
    assert result["type"] == "case"
    assert result["authority"] == "construction_grading"
    assert result["score_awarded"] == 1.0
    assert result["max_score"] == 3.0
    assert result["grading_mode"] == "projected_rubric"
    assert context["diagnosis"] == "PARTIAL"


def test_build_submission_context_does_not_attach_case_grading_to_coding_question() -> None:
    capability = DeepQuestionCapability()

    context = capability._build_submission_context(
        {
            "question_id": "coding-1",
            "question": "写一段 Python 代码输出 hello。",
            "question_type": "coding",
            "correct_answer": "print('hello')",
        },
        "print('hello')",
    )

    assert "construction_grading_result" not in context


def test_submission_grader_renders_authoritative_grading_result() -> None:
    rendered = SubmissionGraderAgent._render_question_context(
        {
            "question_id": "case-9006",
            "question": "指出事件二中的不妥之处。",
            "question_type": "case",
            "user_answer": "共用一个开关箱不妥。",
            "construction_grading_result": {
                "type": "case",
                "authority": "construction_grading",
                "score_awarded": 1.0,
                "max_score": 3.0,
                "grading_mode": "projected_rubric",
                "rubric_items": [
                    {
                        "criterion": "共用一个开关箱不妥；应采用专用开关箱",
                        "max_score": 1.0,
                        "awarded_score": 1.0,
                        "status": "full",
                        "keywords": ["共用一个开关箱"],
                        "evidence_text": "共用一个开关箱",
                        "source_fields": ["correct_answer"],
                    }
                ],
                "error_events": [],
                "rewrite_answer": "共用一个开关箱不妥；应采用专用开关箱。",
            },
        }
    )

    assert "Authoritative construction grading result" in rendered
    assert '"authority": "construction_grading"' in rendered
    assert '"score_awarded": 1.0' in rendered
    assert '"max_score": 3.0' in rendered
    assert "Score: 0" not in rendered
    assert "Score: 100" not in rendered


@pytest.mark.asyncio
async def test_deep_question_writes_grading_errors_to_learner_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FakeLearnerStateService:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def append_memory_event(self, user_id: str, **kwargs: Any) -> object:
            self.calls.append({"user_id": user_id, **kwargs})
            return object()

    fake_learner_state = FakeLearnerStateService()
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: fake_learner_state,
    )

    context = UnifiedContext(
        user_message="我选A，请按建筑实务选择题帮我批改，并告诉我下一题该练什么",
        language="zh",
        metadata={
            "turn_id": "turn-grading-1",
            "bot_id": "construction-exam-coach",
            "billing_context": {"user_id": "student-1"},
            "question_followup_context": {
                "question_id": "q-law",
                "question": "《建设工程安全生产管理条例》属于（ ）。",
                "question_type": "choice",
                "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
                "correct_answer": "B",
                "explanation": "条例由国务院制定，属于行政法规。",
                "concentration": "法规层级",
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "grading"
    assert result_event.metadata["construction_grading_result"]["authority"] == "construction_grading"
    assert len(fake_learner_state.calls) == 1
    call = fake_learner_state.calls[0]
    assert call["user_id"] == "student-1"
    assert call["source_feature"] == "construction_grading"
    assert call["source_bot_id"] == "construction-exam-coach"
    assert call["memory_kind"] == "learning_evidence"
    assert call["payload_json"]["event_type"] == "learning_evidence"
    assert call["payload_json"]["legacy_event_type"] == "construction_grading_error"
    assert call["payload_json"]["question_id"] == "q-law"
    assert call["payload_json"]["next_training_signal"]["focus"] == "法规层级"
    assert call["dedupe_key"]


def test_related_generation_anchor_uses_next_training_signal() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再给我相关题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "q-law",
            "question": "《建设工程安全生产管理条例》属于（ ）。",
            "question_type": "choice",
            "concentration": "法规层级",
            "construction_grading_result": {
                "type": "mcq",
                "authority": "construction_grading",
                "score_awarded": 0.0,
                "max_score": 1.0,
                "error_events": [{"error_code": "M02", "diagnosis": "层级混淆"}],
                "next_training_signal": {
                    "concept": "法规层级",
                    "focus": "行政法规与部门规章辨析",
                },
            },
        },
        conversation_context_text="",
    )

    assert "上一轮错因训练信号" in topic
    assert "行政法规与部门规章辨析" in topic
    assert "优先从现有题库" in topic


def test_related_generation_anchor_accepts_compiled_learning_truth_signal() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再给我相关题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "q-case",
            "question": "某危大工程专项方案应如何组织论证？",
            "question_type": "case",
            "concentration": "危大工程专项方案",
            "compiled_learning_truth": {
                "weak_points": [
                    {
                        "concept_id": "1A432000",
                        "error_code": "E02",
                        "evidence_level": "L1_repeated",
                        "recommended_training": {
                            "concept": "1A432000",
                            "focus": "专家论证程序",
                            "mode": "case_repair",
                        },
                    }
                ]
            },
        },
        conversation_context_text="",
    )

    assert "长期错因训练信号" in topic
    assert "1A432000" in topic
    assert "专家论证程序" in topic
    assert "E02" in topic
    assert "evidence_level=L1_repeated" in topic
    assert "policy_action=diagnostic_hint" in topic


def test_related_generation_anchor_accepts_personalization_context_without_writing_learner_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_calls: list[dict[str, Any]] = []

    def fake_record_memory_event(*args: Any, **kwargs: Any) -> None:
        record_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("deep_question must not write learner-state truth from context")

    monkeypatch.setattr(
        "deeptutor.services.learner_state.service.LearnerStateService.record_memory_event",
        fake_record_memory_event,
        raising=False,
    )

    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再给我相关题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "q-case",
            "question_type": "case",
            "personalization_context": {
                "authority": {"claims": "learning_synthesis", "prescription": "training_intent"},
                "top_claims": [{"concept_id": "1A432000", "evidence_refs": ["event:e1"]}],
                "active_training_intent": {
                    "training_intent_id": "lti_1",
                    "concept_id": "1A432000",
                    "concept_label": "危大工程专项方案",
                    "error_code": "E02",
                    "error_label": "专家论证程序漏项",
                    "evidence_refs": ["event:e1"],
                },
            },
        },
        conversation_context_text="",
    )

    assert "个性化训练意图" in topic
    assert "1A432000" in topic
    assert "危大工程专项方案" in topic
    assert "专家论证程序漏项" in topic
    assert record_calls == []


def test_related_generation_anchor_uses_l2_compiled_truth_for_stable_personalization() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再给我相关题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "q-case",
            "question": "某危大工程专项方案应如何组织论证？",
            "question_type": "case",
            "compiled_learning_truth": {
                "weak_points": [
                    {
                        "concept_id": "1A432000",
                        "error_code": "E02",
                        "evidence_level": "L2_confirmed",
                        "recommended_training": {
                            "focus": "专家论证程序",
                            "mode": "case_repair",
                        },
                    }
                ]
            },
        },
        conversation_context_text="",
    )

    assert "policy_action=stable_personalization" in topic
    assert "evidence_level=L2_confirmed" in topic


def test_related_generation_anchor_ignores_l0_compiled_truth_signal() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再给我相关题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "q-case",
            "question_type": "case",
            "compiled_learning_truth": {
                "weak_points": [
                    {
                        "concept_id": "1A432000",
                        "error_code": "E02",
                        "evidence_level": "L0_observed",
                        "recommended_training": {"focus": "专家论证程序"},
                    }
                ]
            },
        },
        conversation_context_text="",
    )

    assert "长期错因训练信号" not in topic


def test_related_generation_anchor_ignores_superseded_compiled_truth_signal() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再给我相关题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "q-case",
            "question_type": "case",
            "compiled_learning_truth": {
                "weak_points": [
                    {
                        "concept_id": "1A432000",
                        "error_code": "E02",
                        "evidence_level": "L1_repeated",
                        "decay_state": "superseded",
                        "superseded_by_event_ids": ["fix1"],
                        "recommended_training": {"focus": "专家论证程序"},
                    }
                ]
            },
        },
        conversation_context_text="",
    )

    assert "长期错因训练信号" not in topic


def test_related_generation_anchor_can_use_learner_memory_context_without_active_question() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="继续给我练刚才薄弱的点",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context=None,
        conversation_context_text=(
            "## 学员级长期状态\n"
            "### Recent Memory Events\n"
            "- 建筑实务批改错因；题目：q-law；题型：mcq；得分：0.0/1.0；"
            "错因：把行政法规与部门规章层级混淆。；下一题训练重点：行政法规与部门规章辨析"
        ),
    )

    assert "最近对话摘要" in topic
    assert "行政法规与部门规章辨析" in topic


def test_related_generation_anchor_prioritizes_batch_error_training_signal() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再给我相关题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "quiz_batch",
            "question": "批量题",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "choice",
                    "concentration": "考点1",
                    "knowledge_context": "普通知识锚点1",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "choice",
                    "concentration": "考点2",
                    "knowledge_context": "普通知识锚点2",
                },
                {
                    "question_id": "q_5",
                    "question": "题5",
                    "question_type": "choice",
                    "concentration": "法规层级",
                    "construction_grading_result": {
                        "type": "mcq",
                        "authority": "construction_grading",
                        "score_awarded": 0.0,
                        "max_score": 1.0,
                        "error_events": [{"error_code": "M02", "diagnosis": "层级混淆"}],
                        "next_training_signal": {
                            "concept": "法规层级",
                            "focus": "行政法规与部门规章辨析",
                        },
                    },
                },
            ],
        },
        conversation_context_text="",
    )

    assert "行政法规与部门规章辨析" in topic
    assert topic.index("上一轮错因训练信号") < topic.index("当前知识锚点")
