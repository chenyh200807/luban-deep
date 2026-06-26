from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.agents.question.agents.submission_grader_agent import SubmissionGraderAgent
from deeptutor.capabilities import deep_question as deep_question_module
from deeptutor.capabilities.deep_question import DeepQuestionCapability
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


def test_deep_question_builds_case_context_from_full_submission() -> None:
    raw_case_submission = (
        "建设单位编制了投资兴建某工程的招标文件。\n"
        "【问题】1. 工程量清单的强制性内容还有哪些？\n"
        "回答\n"
        "作答：项目编码、项目名称、项目特征、计量单位和工程量。"
    )

    context = DeepQuestionCapability._case_grading_context_from_full_submission(
        raw_case_submission
    )

    assert context is not None
    assert context["question_type"] == "case"
    assert context["construction_grading_result"]["type"] == "case"
    assert "工程量清单的强制性内容" in context["question_stem"]
    assert context["user_answer"] == "项目编码、项目名称、项目特征、计量单位和工程量。"
    assert "建设单位编制了投资兴建某工程" not in context["user_answer"]


@pytest.mark.asyncio
async def test_deep_question_case_grading_scene_without_context_uses_grading_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("case grading should not generate questions")

    async def fake_emit_grading_result(self, **kwargs: Any) -> None:
        captured.update(kwargs)
        await kwargs["stream"].result({"response": "graded"}, source=self.name)

    captured: dict[str, Any] = {}
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    monkeypatch.setattr(
        "deeptutor.services.llm.config.get_llm_config",
        lambda: SimpleNamespace(api_key="test", base_url="", api_version=""),
    )
    monkeypatch.setattr(
        DeepQuestionCapability,
        "_emit_grading_result",
        fake_emit_grading_result,
    )
    raw_case_submission = (
        "案例背景：某工程地下室混凝土拆模后发现孔洞。\n"
        "问题：补充孔洞治理流程。\n"
        "作答：凿毛、涂刷界面剂、支模、浇筑、养护。"
    )
    capability = DeepQuestionCapability()
    context = UnifiedContext(
        session_id="s-case-deep-question",
        user_message=raw_case_submission,
        config_overrides={},
        metadata={"question_lifecycle_scene": "case_grading"},
        language="zh",
    )

    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["authority_source"] == "case_grading_full_submission"
    assert captured["correct_answer_present"] is False
    assert captured["graded_context"]["construction_grading_result"]["type"] == "case"
    assert captured["graded_context"]["user_answer"] == "凿毛、涂刷界面剂、支模、浇筑、养护。"
    assert context.metadata["question_followup_context"]["question_type"] == "case"
    assert any(event.type == StreamEventType.RESULT for event in events)


@pytest.mark.asyncio
async def test_deep_question_full_case_submission_marks_current_reference_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("case grading should not generate questions")

    async def fake_emit_grading_result(self, **kwargs: Any) -> None:
        captured.update(kwargs)
        await kwargs["stream"].result({"response": "graded"}, source=self.name)

    captured: dict[str, Any] = {}
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    monkeypatch.setattr(
        "deeptutor.services.llm.config.get_llm_config",
        lambda: SimpleNamespace(api_key="test", base_url="", api_version=""),
    )
    monkeypatch.setattr(
        DeepQuestionCapability,
        "_emit_grading_result",
        fake_emit_grading_result,
    )
    raw_case_submission = (
        "案例题：某工程底模拆除时混凝土强度检查。\n"
        "问题：跨度为8m的现浇梁底模拆除时，混凝土强度应达到设计强度的多少？"
        "我的答案：75%。标准答案：100%。请判分。"
    )
    capability = DeepQuestionCapability()
    context = UnifiedContext(
        session_id="s-case-deep-question-reference",
        user_message=raw_case_submission,
        config_overrides={},
        metadata={"question_lifecycle_scene": "case_grading"},
        language="zh",
    )

    await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["authority_source"] == "case_grading_full_submission"
    assert captured["correct_answer_present"] is True
    assert captured["graded_context"]["correct_answer"] == "100%"
    assert captured["graded_context"]["reference_answer"] == "100%"
    assert captured["graded_context"]["user_answer"] == "75%"


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
    # #21(2026-06-23):反篡改薄答罐头("我不会因追问改写标准答案")已删,改给详细
    # 答案与解析(确定性,不调 FollowupAgent),不再只甩单选项防御句。
    assert "改写标准答案" not in response
    assert "D（最高点）" in response
    assert "解析" in response


@pytest.mark.asyncio
async def test_deep_question_invalid_option_followup_uses_current_options_not_fabrication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for follow-up mode")

    class FailingFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("invalid option check should use current option authority")

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
        user_message="E",
        language="zh",
        metadata={
            "raw_user_message": "如果我选E，对不对？一句话。",
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
            },
            "question_followup_action": {
                "intent": "ask_followup",
            },
            "question_followup_context": {
                "question_id": "q_joint",
                "question": "下列关于施工缝留置位置的说法，错误的是（ ）。",
                "question_type": "choice",
                "options": {
                    "A": "施工缝可留在剪力较小处",
                    "B": "楼梯梯段施工缝可留在梯段板跨中1/3范围内",
                    "C": "梁板施工缝可留在次梁跨中1/3范围内",
                    "D": "单向板施工缝可留在平行于短边的位置",
                },
                "correct_answer": "B",
                "user_answer": "D",
                "is_correct": False,
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    response = result_event.metadata["response"]
    assert result_event.metadata["mode"] == "followup"
    assert "E" in response
    assert "不是这道题的选项" in response
    assert "A、B、C、D" in response
    assert "E（" not in response


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
    # #21(2026-06-23):删 _render_targeted_option_reference_feedback 后,书面题参考揭示
    # 走 verbose 答案与解析分支(参考答案要点+按关键点给分),确定性、不调 FollowupAgent;
    # 不再经 targeted 渲染器输出 §条号(参考内容仍揭示,§条号非必需)。无反篡改薄答罐头。
    assert "改写标准答案" not in response
    assert "本题按参考答案的关键点给分" in response


@pytest.mark.asyncio
async def test_deep_question_blocks_unanswered_direct_answer_reveal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for follow-up mode")

    # A1-①(2026-06-22):未作答 followup 不再硬 block"练习阶段不公开答案",改走 FollowupAgent
    # 在答案隐藏下作答(should_reveal_reference_material=False → 渲染不含答案 + 安全指令)。
    # 关键不变量仍是:绝不泄露答案。FollowupAgent 被调用但拿不到答案,故不会吐出 观察法/正确答案。
    class StubFollowupAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_trace_callback(self, _cb: Any) -> None:
            pass

        async def process(self, **_kwargs: Any) -> str:
            return "这道题你还没作答,我先帮你理解题意,先不直接公布答案,你可以试着选一个。"

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.followup_agent",
        FollowupAgent=StubFollowupAgent,
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
    # A1-①:不再硬 block,但答案仍绝不泄露(FollowupAgent 拿不到答案)
    assert "观察法" not in response
    assert "正确答案" not in response


@pytest.mark.asyncio
async def test_deep_question_open_world_grading_when_choice_answer_authority_missing(
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
                "## 📊 阅卷结论\n依据教材判定：正确答案应为 B（混凝土强度），你选 B，判定正确。\n\n"
                "## 🧐 解析\n模板拆除以混凝土强度达到规范要求为先决条件。"
            )

    async def fake_rag_search(query: str, kb_name: str | None = None, **kwargs: Any) -> dict[str, Any]:
        captured["rag_query"] = query
        captured["rag_kb_name"] = kb_name
        captured["rag_kwargs"] = kwargs
        return {
            "content": "【教材依据】模板拆除时混凝土强度必须满足规范要求。",
            "sources": [],
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
        user_message="我选B",
        language="zh",
        knowledge_bases=["construction-exam"],
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
    # 开放世界判分：不再以"缺少标准答案"拒答（grading_blocked 字段随死代码一并移除）。
    assert "grading_blocked" not in result_event.metadata
    assert result_event.metadata["is_correct"] is None
    assert result_event.metadata["grading_kernel"] == "mcq"
    assert result_event.metadata["correct_answer_present"] is False
    assert result_event.metadata["question_authority_source"] == "open_world"
    assert "缺少标准答案" not in result_event.metadata["response"]
    assert "依据教材判定" in result_event.metadata["response"]
    # llm_judge 占位结果不得冒充确定性判分 authority。
    assert "construction_grading_result" not in result_event.metadata
    # 开放世界裁决必须带 RAG grounding（kb 可用时）。
    assert captured["rag_kb_name"] == "construction-exam"
    assert captured["rag_kwargs"]["routing_metadata"]["answer_authority"] == "open_world"
    grader_question_context = captured["grader_kwargs"]["question_context"]
    assert grader_question_context["is_correct"] is None
    assert not str(grader_question_context.get("correct_answer") or "").strip()


@pytest.mark.asyncio
async def test_deep_question_open_world_grading_stays_non_empty_when_grader_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """绝不空输出 / 绝不拒答 backstop（硬约束40,2026-06-17）。

    即使无标准答案、且 open-world ``SubmissionGraderAgent`` 自身失败,用户也必须
    拿到一条非空的判分回复(降级到确定性 grounded 解析),绝不能是空输出或
    "缺少标准答案"拒答 —— 这是 "做完题没给答案" 体验事故的最后一道安全网。
    """

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class FailingSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_trace_callback(self, callback: Any) -> None:
            pass

        async def process(self, **_kwargs: Any) -> str:
            raise RuntimeError("open-world grader unavailable")

    async def fake_rag_search(query: str, kb_name: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return {"content": "【教材依据】模板拆除时混凝土强度必须满足规范要求。", "sources": []}

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
    monkeypatch.setattr(deep_question_module, "rag_search", fake_rag_search, raising=False)

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        knowledge_bases=["construction-exam"],
        metadata={
            "conversation_context_text": "用户刚做完一道选择题。",
            "question_followup_context": {
                "question_id": "tb_q_2",
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
    # 安全网：response 必须非空，绝不拒答、绝不空输出。
    response = str(result_event.metadata.get("response") or "").strip()
    assert response, "grader 失败也必须给出非空判分回复（绝不空输出）"
    assert "缺少标准答案" not in response
    assert "grading_blocked" not in result_event.metadata


@pytest.mark.asyncio
async def test_deep_question_open_world_fallback_is_honest_when_setup_and_rag_both_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex review 加固（2026-06-17）：兜底必须覆盖 grader **构造期** 失败(不止 process),
    且在检索证据也缺失时**不得虚称"依据教材/规范给你要点"**(否则冒充了不存在的依据)。
    """

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("Coordinator should not be constructed for grading mode")

    class ConstructorFailingSubmissionGraderAgent:
        def __init__(self, **_kwargs: Any) -> None:
            # 构造期就失败：验证 try 已包住 import/构造/set_trace,而不仅是 process。
            raise RuntimeError("open-world grader construction failed")

    async def failing_rag_search(query: str, kb_name: str | None = None, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("rag unavailable")

    _install_module(
        monkeypatch,
        "deeptutor.agents.question.coordinator",
        AgentCoordinator=FakeCoordinator,
    )
    _install_module(
        monkeypatch,
        "deeptutor.agents.question.agents.submission_grader_agent",
        SubmissionGraderAgent=ConstructorFailingSubmissionGraderAgent,
    )
    _install_module(
        monkeypatch,
        "deeptutor.services.llm.config",
        get_llm_config=lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )
    monkeypatch.setattr(deep_question_module, "rag_search", failing_rag_search, raising=False)

    context = UnifiedContext(
        user_message="我选B",
        language="zh",
        knowledge_bases=["construction-exam"],
        metadata={
            "conversation_context_text": "用户刚做完一道选择题。",
            "question_followup_context": {
                "question_id": "tb_q_3",
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
    response = str(result_event.metadata.get("response") or "").strip()
    # 构造期失败也被兜住：非空、不拒答、不崩。
    assert response, "构造期失败也必须给出非空判分回复"
    assert "缺少标准答案" not in response
    assert "grading_blocked" not in result_event.metadata
    # 检索证据缺失时不得虚称已"依据教材/规范给你要点"。
    assert "依据教材/规范给你要点" not in response


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
async def test_deep_question_open_world_grading_when_batch_choice_recovery_is_partial(
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
                "## 📊 阅卷结论\n第1题按题库标准答案判定正确；"
                "第2题无题库标准答案，依据教材判定你选 C（力学性能）正确。"
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
    assert "grading_blocked" not in result_event.metadata
    assert result_event.metadata["is_correct"] is None
    assert result_event.metadata["correct_answer_present"] is False
    assert result_event.metadata["question_authority_source"] == "open_world"
    assert "缺少标准答案" not in result_event.metadata["response"]
    assert "依据教材判定" in result_event.metadata["response"]
    # 顶层聚合的 llm_judge 占位结果不得冒充确定性判分 authority。
    assert "construction_grading_result" not in result_event.metadata
    # 已恢复 authority 的第 1 题保留确定性判定；缺 authority 的第 2 题交开放世界裁决。
    assert [
        item.get("is_correct")
        for item in result_event.metadata["question_followup_context"]["items"]
    ] == [True, None]


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


def test_plain_count_generation_request_requires_authoritative_anchor() -> None:
    for user_topic in ("出三道题", "出3道题", "来两道题", "给我三道题"):
        assert deep_question_module._topic_needs_authoritative_anchor(user_topic) is True


def test_plain_count_generation_request_uses_open_chat_topic_anchor() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="出三道题",
        active_object={
            "object_type": "open_chat_topic",
            "object_id": "topic-deformation-joint",
            "state_snapshot": {
                "title": "变形缝",
                "compressed_summary": "用户刚学习了建筑实务变形缝的设置与构造处理。",
            },
        },
        suspended_object_stack=[],
        followup_question_context=None,
        conversation_context_text="",
    )

    assert topic.startswith("出三道题")
    assert "当前学习锚点" in topic
    assert "变形缝" in topic


def test_plain_count_generation_request_uses_conversation_context_anchor() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="出三道题",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context=None,
        conversation_context_text="用户上一轮在讨论建筑实务变形缝，重点是沉降缝、伸缩缝、防震缝的适用场景。",
    )

    assert topic.startswith("出三道题")
    assert "最近对话摘要" in topic
    assert "变形缝" in topic


def test_different_topic_generation_request_excludes_active_question_anchor() -> None:
    topic = deep_question_module._resolve_generation_topic(
        raw_topic="再出一道不同考点的单选题，不要答案。",
        active_object=None,
        suspended_object_stack=[],
        followup_question_context={
            "question_id": "q_joint",
            "question": "下列关于施工缝留置位置的说法，错误的是（ ）。",
            "question_type": "choice",
            "options": {
                "A": "施工缝宜留在结构受剪力较小处",
                "B": "梁板施工缝可留在受剪力较大处",
                "C": "次梁跨度中间1/3范围可留设施工缝",
                "D": "单向板可平行于短边留设施工缝",
            },
            "correct_answer": "B",
        },
        conversation_context_text="",
    )

    assert topic.startswith("再出一道不同考点的单选题")
    assert "建筑实务/建造师考试高频考点" in topic
    assert "当前学习锚点" not in topic
    assert "排除当前题" in topic
    assert "不得作为新题考点" in topic
    assert "施工缝" in topic


def test_explicit_generation_topic_does_not_require_context_anchor() -> None:
    assert deep_question_module._topic_needs_authoritative_anchor("出三道变形缝的题") is False
    for user_topic in (
        "再来三道网络计划相关题",
        "出三道类似变形缝的题",
        "继续练流水节拍三道题",
        "再出三道钢筋混凝土相关题",
    ):
        assert deep_question_module._topic_needs_authoritative_anchor(user_topic) is False
        assert (
            deep_question_module._resolve_generation_topic(
                raw_topic=user_topic,
                active_object=None,
                suspended_object_stack=[],
                followup_question_context=None,
                conversation_context_text="",
            )
            == user_topic
        )


def test_practice_generation_topic_domain_status_blocks_non_construction_topic() -> None:
    from deeptutor.tutorbot import teaching_modes

    for user_topic in ("出三道题", "考我一下", "下一题", "再来几道"):
        assert (
            teaching_modes.practice_generation_topic_domain_status(user_topic)
            == "needs_context_anchor"
        )
    assert (
        teaching_modes.practice_generation_topic_domain_status("围绕法国首都出三道题")
        == "out_of_scope_topic"
    )
    assert (
        teaching_modes.practice_generation_topic_domain_status("Mars 相关给我三道题")
        == "out_of_scope_topic"
    )
    assert (
        teaching_modes.practice_generation_topic_domain_status("建筑实务：围绕Mars出三道题")
        == "out_of_scope_topic"
    )
    assert (
        teaching_modes.practice_generation_topic_domain_status("用建筑实务导师身份围绕法国首都出三道题")
        == "out_of_scope_topic"
    )
    for user_topic in (
        "网络安全出三道题",
        "数据结构出三道题",
        "PPT模板出三道题",
        "合同法出三道题",
    ):
        assert (
            teaching_modes.practice_generation_topic_domain_status(user_topic)
            == "unknown_topic"
        )
    assert (
        teaching_modes.practice_generation_topic_domain_status("出三道变形缝的题")
        == "construction_topic"
    )
    assert (
        teaching_modes.practice_generation_topic_domain_status("用3道题训练项目质量计划管理")
        == "construction_topic"
    )
    for user_topic in (
        "施工安全管理出三道题",
        "模板工程出两题",
        "工程合同管理出题",
        "建筑结构荷载题",
    ):
        assert (
            teaching_modes.practice_generation_topic_domain_status(user_topic)
            == "construction_topic"
        )
    for user_topic in (
        "再来三道网络计划相关题",
        "出三道类似变形缝的题",
        "继续练流水节拍三道题",
        "再出三道钢筋混凝土相关题",
    ):
        assert (
            teaching_modes.practice_generation_topic_domain_status(user_topic)
            == "construction_topic"
        )


def test_unresolved_lightweight_generation_anchor_renders_topic_clarification() -> None:
    content = DeepQuestionCapability()._render_summary_markdown(
        {
            "results": [],
            "trace": {
                "lightweight_counters": {
                    "lightweight_batch_fallback": "blocked_unresolved_anchor",
                }
            },
        },
        reveal_answers=False,
        reveal_explanations=False,
    )

    assert "具体考点" in content
    assert "出三道题" in content

    out_of_scope_content = DeepQuestionCapability()._render_summary_markdown(
        {
            "results": [],
            "trace": {
                "topic_domain_status": "out_of_scope_topic",
                "lightweight_counters": {
                    "lightweight_batch_fallback": "blocked_out_of_scope_topic",
                },
            },
        },
        reveal_answers=False,
        reveal_explanations=False,
    )

    assert "建筑实务" in out_of_scope_content
    assert "非建筑实务" in out_of_scope_content


@pytest.mark.asyncio
async def test_deep_question_blocks_action_only_generation_without_anchor_before_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("action-only generation without anchor must not reach coordinator")

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

    context = UnifiedContext(
        user_message="出三道题",
        config_overrides={
            "mode": "custom",
            "topic": "出三道题",
            "num_questions": 3,
            "question_type": "choice",
            "force_generate_questions": True,
            "lightweight_generation": False,
        },
        language="zh",
        metadata={
            "question_lifecycle_scene": "practice_generation",
            "selected_mode": "deep",
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "具体考点" in result_event.metadata["response"]
    assert result_event.metadata["question_followup_context"] == {}
    assert result_event.metadata["practice_generation_blocked_reason"] == "missing_topic_anchor"


@pytest.mark.asyncio
async def test_deep_question_blocks_non_construction_generation_before_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            raise AssertionError("out-of-domain generation must not reach coordinator")

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

    context = UnifiedContext(
        user_message="围绕法国首都出三道题",
        config_overrides={
            "mode": "custom",
            "topic": "围绕法国首都出三道题",
            "num_questions": 3,
            "question_type": "choice",
            "force_generate_questions": True,
            "lightweight_generation": False,
        },
        language="zh",
        metadata={
            "question_lifecycle_scene": "practice_generation",
            "selected_mode": "deep",
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "建筑实务" in result_event.metadata["response"]
    assert result_event.metadata["question_followup_context"] == {}
    assert (
        result_event.metadata["practice_generation_blocked_reason"]
        == "out_of_scope_topic"
    )


@pytest.mark.asyncio
async def test_deep_question_allows_explicit_construction_generation_topic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_ws_callback(self, callback: Any) -> None:
            captured["ws_callback"] = callback

        def set_trace_callback(self, callback: Any) -> None:
            captured["trace_callback"] = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["generate_from_topic"] = kwargs
            return {
                "source": "topic",
                "requested": kwargs.get("num_questions", 0),
                "completed": 0,
                "failed": 0,
                "results": [],
                "trace": {
                    "lightweight_generation": kwargs.get("lightweight_generation", False),
                    "lightweight_counters": {
                        "llm_calls": 0,
                        "retriever_calls": 0,
                        "bank_hits": 0,
                        "lightweight_batch_fallback": "none",
                        "generated_explanation": False,
                    },
                },
            }

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

    context = UnifiedContext(
        user_message="出三道变形缝的题",
        config_overrides={
            "mode": "custom",
            "topic": "出三道变形缝的题",
            "num_questions": 3,
            "question_type": "choice",
            "force_generate_questions": True,
            "lightweight_generation": False,
        },
        language="zh",
        metadata={
            "question_lifecycle_scene": "practice_generation",
            "selected_mode": "deep",
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert captured["generate_from_topic"]["num_questions"] == 3
    assert "变形缝" in captured["generate_from_topic"]["user_topic"]
    assert "practice_generation_blocked_reason" not in result_event.metadata


@pytest.mark.asyncio
async def test_deep_question_different_topic_request_does_not_inherit_question_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_ws_callback(self, callback: Any) -> None:
            captured["ws_callback"] = callback

        def set_trace_callback(self, callback: Any) -> None:
            captured["trace_callback"] = callback

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            captured["generate_from_topic"] = kwargs
            return {
                "source": "topic",
                "requested": kwargs.get("num_questions", 0),
                "completed": 0,
                "failed": 0,
                "results": [],
                "trace": {
                    "lightweight_generation": kwargs.get("lightweight_generation", False),
                    "lightweight_counters": {
                        "llm_calls": 0,
                        "retriever_calls": 0,
                        "bank_hits": 0,
                        "lightweight_batch_fallback": "none",
                        "generated_explanation": False,
                    },
                },
            }

        async def generate_from_followup_context(self, **_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("different-topic requests must not use current question anchor")

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

    context = UnifiedContext(
        user_message="再出一道不同考点的单选题，不要答案。",
        config_overrides={
            "mode": "custom",
            "topic": "再出一道不同考点的单选题，不要答案。",
            "num_questions": 1,
            "question_type": "choice",
            "force_generate_questions": True,
            "lightweight_generation": False,
            "reveal_answers": False,
            "reveal_explanations": False,
        },
        language="zh",
        metadata={
            "question_lifecycle_scene": "practice_generation",
            "selected_mode": "fast",
            "active_object": {
                "object_type": "single_question",
                "object_id": "q_hot_work",
                "state_snapshot": {
                    "question_id": "q_hot_work",
                    "question": "施工现场负责审查批准一级动火作业的（ ）。",
                    "question_type": "choice",
                    "options": {
                        "A": "项目负责人",
                        "B": "项目生产负责人",
                        "C": "项目安全管理部门",
                        "D": "企业安全管理部门",
                    },
                    "correct_answer": "A",
                    "construction_grading_result": {
                        "next_training_signal": {
                            "concept": "一级建造师项目管理",
                            "focus": "动火审批责任主体",
                        }
                    },
                },
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    user_topic = captured["generate_from_topic"]["user_topic"]
    assert captured["generate_from_topic"]["avoid_current_question"] is True
    assert "当前学习锚点" not in user_topic
    assert "排除当前题" in user_topic
    assert "一级动火作业" in user_topic
    assert "上一轮薄弱点" not in user_topic
    assert "next_training_signal" not in user_topic
    assert "practice_generation_blocked_reason" not in result_event.metadata
    assert "非建筑实务" not in result_event.metadata["response"]


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
