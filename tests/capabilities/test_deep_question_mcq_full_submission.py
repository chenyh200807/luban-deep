from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.semantic_router import build_active_object_from_question_context

_parse = DeepQuestionCapability._mcq_grading_context_from_full_submission


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


def test_pasted_single_choice_parsed_on_learner_surface() -> None:
    ctx = _parse("某工程屋面坡度最小值（）。A.5% B.2% C.3% D.1%。我选A")
    assert ctx is not None
    assert ctx["question_type"] == "choice"
    assert ctx["options"] == {"A": "5%", "B": "2%", "C": "3%", "D": "1%"}  # learner surface
    assert ctx["user_answer"] == "A"
    assert ctx["correct_answer"] == ""  # open-world adjudication, no bank letter leaked


def test_pasted_single_choice_accepts_learner_answer_label_after_option_surface() -> None:
    ctx = _parse(
        "问题：建筑工程最低保修期限说法正确的是（ ）。\n"
        "A. 电气管线、给排水管道、设备安装为2年\n"
        "B. 电气管线、给排水管道、设备安装为5年\n"
        "C. 屋面防水为2年\n"
        "D. 供热与供冷系统为1个采暖期\n"
        "我的答案：A，请批改"
    )

    assert ctx is not None
    assert ctx["question_type"] == "choice"
    assert ctx["options"]["A"] == "电气管线、给排水管道、设备安装为2年"
    assert ctx["user_answer"] == "A"
    assert ctx["correct_answer"] == ""


def test_pasted_single_choice_carries_marked_standard_answer() -> None:
    ctx = _parse(
        "题目：建设工程竣工验收应由谁组织？\n"
        "A. 施工单位项目经理\n"
        "B. 监理工程师\n"
        "C. 建设单位项目负责人\n"
        "D. 总监理工程师。我的答案 B。标准答案：C。"
    )

    assert ctx is not None
    assert ctx["options"]["D"] == "总监理工程师"
    assert ctx["user_answer"] == "B"
    assert ctx["correct_answer"] == "C"


def test_pasted_multi_choice_extracts_all_selected() -> None:
    ctx = _parse("正确的有：A.导管法 B.槽段8到10m C.导墙 D.墙底注浆。我选ACD")
    assert ctx is not None
    assert ctx["user_answer"] == "ACD"


def test_value_only_answer_maps_to_learner_letter() -> None:
    # "我选5%" (value, not letter) -> deterministically mapped to the learner's A.
    ctx = _parse("坡度最小值（）。A.5% B.2% C.3% D.1%。我选5%")
    assert ctx is not None
    assert ctx["user_answer"] == "A"


def test_non_mcq_and_chat_return_none() -> None:
    assert _parse("介绍一下流水施工") is None
    assert _parse("今天好热啊") is None
    assert _parse("") is None


def test_canonical_turn_decision_missing_predicate() -> None:
    # Context-Continuity task #12 step 2: observation predicate for "deep_question reached
    # without the orchestrator's canonical turn_semantic_decision" (the fabricated-fallback
    # path the migration removes). Zero behavior change — observation only.
    missing = DeepQuestionCapability._canonical_turn_decision_missing
    assert missing({}) is True  # no key
    assert missing({"turn_semantic_decision": {}}) is True  # empty / falsy
    assert missing(None) is False  # non-dict → not applicable
    assert (
        missing(
            {
                "turn_semantic_decision": {
                    "relation_to_active_object": "answer_active_object",
                    "next_action": "route_to_grading",
                }
            }
        )
        is False  # canonical decision present
    )


def test_fabrication_observation_fields_extracts_identifying_context() -> None:
    # task #12 step 2: the fabrication-fallback observation log must carry enough context
    # to pin the upstream path. loguru uses {key} formatting; these are the bound fields.
    fields = DeepQuestionCapability._fabrication_observation_fields(
        {
            "question_lifecycle_scene": "practice_generation",
            "active_object": {"object_type": "question_set"},
            "suspended_object_stack": [{"object_type": "open_chat_topic"}],
            "turn_id": "turn_abc",
            "client_turn_id": "c_xyz",
        }
    )
    assert fields == {
        "scene": "practice_generation",
        "active_object": True,
        "suspended": 1,
        "turn_id": "turn_abc",
        "client_turn_id": "c_xyz",
    }
    # non-dict / empty → safe defaults
    assert DeepQuestionCapability._fabrication_observation_fields(None) == {
        "scene": None, "active_object": False, "suspended": 0,
        "turn_id": None, "client_turn_id": None,
    }


@pytest.mark.asyncio
async def test_deep_question_honors_clarification_decision_before_full_mcq_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.llm.config.get_llm_config",
        lambda: SimpleNamespace(api_key="test", base_url="", api_version=""),
    )

    async def fail_grading(self, **_kwargs: Any) -> None:
        raise AssertionError("ask_clarifying_question must not enter grading")

    monkeypatch.setattr(DeepQuestionCapability, "_emit_grading_result", fail_grading)

    context = UnifiedContext(
        session_id="s-clarify-before-mcq-fallback",
        user_message="题干：倒置式屋面构造做法正确的是（ ）。A.保护层在防水层下 B.保温层在防水层上。我选B",
        config_overrides={},
        metadata={
            "turn_id": "turn-clarify-before-mcq-fallback",
            "turn_semantic_decision": {
                "relation_to_active_object": "uncertain",
                "next_action": "ask_clarifying_question",
                "target_object_ref": {"object_type": "single_question", "object_id": "q_roof"},
                "allowed_patch": ["no_state_change"],
                "confidence": 0.31,
                "reason": "当前输入可同时命中多个题目对象，不能硬猜。",
            },
        },
        language="zh",
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "clarification"
    assert result_event.metadata["turn_semantic_decision"]["next_action"] == "ask_clarifying_question"
    assert result_event.metadata["question_authority_source"] == "turn_semantic_decision"
    assert result_event.metadata["reveal_answers"] is False


@pytest.mark.asyncio
async def test_deep_question_prefers_self_contained_mcq_over_case_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.llm.config.get_llm_config",
        lambda: SimpleNamespace(api_key="test", base_url="", api_version=""),
    )
    captured: dict[str, Any] = {}

    async def capture_grading(self, **kwargs: Any) -> None:
        captured.update(kwargs)
        await kwargs["stream"].result(
            {"response": "graded"},
            source="deep_question",
            metadata={
                "mode": "grading",
                "authority_source": kwargs.get("authority_source"),
            },
        )

    monkeypatch.setattr(DeepQuestionCapability, "_emit_grading_result", capture_grading)

    message = (
        "问题：建筑工程最低保修期限说法正确的是（ ）。\n"
        "A. 电气管线、给排水管道、设备安装为2年\n"
        "B. 电气管线、给排水管道、设备安装为5年\n"
        "C. 屋面防水为2年\n"
        "D. 供热与供冷系统为1个采暖期\n"
        "我的答案：A，请批改"
    )
    context = UnifiedContext(
        session_id="s-self-contained-mcq-over-case",
        user_message=message,
        config_overrides={},
        metadata={
            "turn_id": "turn-self-contained-mcq-over-case",
            "raw_user_message": message,
            "question_lifecycle_scene": "case_grading",
        },
        language="zh",
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["authority_source"] == "mcq_grading_full_submission"
    assert captured["graded_context"]["question_type"] == "choice"
    assert captured["graded_context"]["user_answer"] == "A"
    assert context.metadata["question_followup_context"]["question_type"] == "choice"
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["authority_source"] == "mcq_grading_full_submission"


@pytest.mark.asyncio
async def test_deep_question_self_contained_mcq_overrides_stale_active_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deeptutor.services.llm.config.get_llm_config",
        lambda: SimpleNamespace(api_key="test", base_url="", api_version=""),
    )
    captured: dict[str, Any] = {}

    async def capture_grading(self, **kwargs: Any) -> None:
        captured.update(kwargs)
        await kwargs["stream"].result(
            {"response": "graded"},
            source="deep_question",
            metadata={
                "mode": "grading",
                "authority_source": kwargs.get("authority_source"),
                "question_followup_context": kwargs.get("graded_context"),
                "active_object": kwargs.get("active_object"),
            },
        )

    monkeypatch.setattr(DeepQuestionCapability, "_emit_grading_result", capture_grading)

    stale_context = {
        "question_id": "q_old",
        "question": "以下关于施工缝留置位置的说法，错误的是（ ）。",
        "question_type": "choice",
        "options": {
            "A": "柱的施工缝宜留置在基础、楼板、梁的顶面",
            "B": "楼梯梯段施工缝留设在梯段板跨度中部1/3范围内",
            "C": "单向板施工缝留设在跨度方向平行的任何位置",
            "D": "墙的施工缝宜留置在门洞口过梁跨中1/3范围内",
        },
        "correct_answer": "B",
        "user_answer": "A",
        "is_correct": False,
    }
    stale_active_object = build_active_object_from_question_context(stale_context)
    message = (
        "请判这道我粘贴的单选题：题目：关于混凝土施工缝留置，下列说法正确的是？"
        "A. 施工缝可随意留置 "
        "B. 施工缝宜留在结构受剪力较大处 "
        "C. 施工缝处理时无需清除浮浆 "
        "D. 施工缝位置应按设计要求和施工技术方案确定。"
        "我的答案：D。标准答案：D。"
    )
    context = UnifiedContext(
        session_id="s-self-contained-mcq-stale-active",
        user_message=message,
        config_overrides={},
        metadata={
            "turn_id": "turn-self-contained-mcq-stale-active",
            "raw_user_message": message,
            "question_lifecycle_scene": "mcq_grading",
            "active_object": stale_active_object,
            "question_followup_context": stale_context,
            "turn_semantic_decision": {
                "relation_to_active_object": "answer_active_object",
                "next_action": "route_to_grading",
                "allowed_patch": ["update_answer_slot"],
                "confidence": 0.95,
                "target_object_ref": {
                    "object_type": "single_question",
                    "object_id": "q_old",
                },
            },
        },
        language="zh",
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    assert captured["authority_source"] == "mcq_grading_full_submission"
    assert captured["graded_context"]["question"] == message
    assert captured["graded_context"]["options"]["B"] == "施工缝宜留在结构受剪力较大处"
    assert captured["graded_context"]["correct_answer"] == "D"
    assert captured["active_object"]["state_snapshot"]["question"] == message
    assert captured["active_object"]["state_snapshot"]["correct_answer"] == "D"
    assert context.metadata["question_followup_context"]["question"] == message
    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["active_object"]["state_snapshot"]["question"] == message
