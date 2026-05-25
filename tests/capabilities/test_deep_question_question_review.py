from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus


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


def _review_context() -> UnifiedContext:
    return UnifiedContext(
        session_id="s-question-review",
        user_message="分析一道钢筋保护层的真题",
        config_overrides={
            "question_review_mode": True,
            "mode": "custom",
            "topic": "分析一道钢筋保护层的真题",
            "num_questions": 1,
            "question_type": "choice",
        },
        metadata={
            "question_lifecycle_scene": "question_review",
            "question_lifecycle_skill_names": [
                "construction-exam-tutor",
                "construction-question-review",
            ],
        },
        knowledge_bases=["construction-exam"],
        language="zh",
    )


def _patch_llm_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.services.llm.config.get_llm_config",
        lambda: SimpleNamespace(api_key="k", base_url="u", api_version="v1"),
    )


@pytest.mark.asyncio
async def test_question_review_bank_hit_renders_non_interactive_review_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_ws_callback(self, _callback) -> None:
            pass

        def set_trace_callback(self, _callback) -> None:
            pass

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(dict(kwargs))
            return {
                "results": [
                    {
                        "success": True,
                        "qa_pair": {
                            "question_id": "q_review",
                            "question": "关于混凝土保护层厚度，下列哪个说法是正确的？",
                            "question_type": "choice",
                            "options": {
                                "A": "I-A环境中，设计使用年限50年的C30板，其最小保护层厚度为15mm。",
                                "B": "直接接触土体浇筑的构件，其混凝土保护层厚度不应小于65mm。",
                            },
                            "correct_answer": "",
                            "explanation": "",
                            "grading_key": {
                                "correct_answer": "B",
                                "source": "questions_bank",
                                "minimal_rationale": "题库命中，B 为标准答案。",
                            },
                            "metadata": {
                                "source": "questions_bank",
                                "knowledge_context": "题库解析要点：直接接触土体浇筑的构件，保护层厚度不应小于65mm。",
                            },
                        },
                    }
                ],
                "trace": {
                    "lightweight_counters": {
                        "bank_hits": 1,
                        "llm_calls": 0,
                        "retriever_calls": 1,
                    }
                },
            }

    monkeypatch.setattr("deeptutor.agents.question.coordinator.AgentCoordinator", FakeCoordinator)
    _patch_llm_config(monkeypatch)

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(_review_context(), bus))

    assert calls
    assert calls[0]["lightweight_generation"] is True
    assert calls[0]["allow_lightweight_fallback"] is False
    result = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result.metadata["active_object"] == {}
    assert result.metadata["question_followup_context"] == {}
    block = result.metadata["presentation"]["blocks"][0]
    assert block["review_mode"] is True
    assert block["submit_hint"] == "题目讲评，已展示解析，不需要提交答案。"
    assert block["questions"][0]["followup_context"]["correct_answer"] == "B"
    assert "题库命中" in result.metadata["response"] or "保护层厚度" in result.metadata["response"]


@pytest.mark.asyncio
async def test_question_review_bank_miss_does_not_fallback_to_generated_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_ws_callback(self, _callback) -> None:
            pass

        def set_trace_callback(self, _callback) -> None:
            pass

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(dict(kwargs))
            return {
                "results": [],
                "trace": {
                    "lightweight_counters": {
                        "bank_hits": 0,
                        "llm_calls": 0,
                        "retriever_calls": 1,
                        "lightweight_batch_fallback": "disabled",
                    }
                },
            }

    monkeypatch.setattr("deeptutor.agents.question.coordinator.AgentCoordinator", FakeCoordinator)
    _patch_llm_config(monkeypatch)

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(_review_context(), bus))

    assert calls
    assert calls[0]["allow_lightweight_fallback"] is False
    result = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "还没有定位到" in result.metadata["response"]
    assert "请把完整题干" in result.metadata["response"]
    assert result.metadata["active_object"] == {}
    assert result.metadata["question_followup_context"] == {}
    assert "presentation" not in result.metadata


@pytest.mark.asyncio
async def test_question_review_evidence_bundle_renders_when_bank_hit_has_no_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production trace 85363: retriever hit templates but results stayed empty."""

    calls: list[dict[str, Any]] = []

    class FakeCoordinator:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def set_ws_callback(self, _callback) -> None:
            pass

        def set_trace_callback(self, _callback) -> None:
            pass

        async def generate_from_topic(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(dict(kwargs))
            return {
                "success": False,
                "requested": 1,
                "completed": 0,
                "templates": [
                    {
                        "question_id": "q_1",
                        "concentration": "分析一道钢筋保护层的真题",
                        "question_type": "choice",
                        "reference_question": "不利于提高框架结构抗震性能的措施是（　　）。",
                        "reference_answer": "B",
                        "metadata": {
                            "evidence_refs": [
                                {
                                    "source": "evidence_bundle",
                                    "field": "TEXTBOOK",
                                    "content": {
                                        "source_group": "TEXTBOOK",
                                        "source_id": "question-14576",
                                        "content": (
                                            "【题目】一般环境中，直接接触土体浇筑的构件，"
                                            "其钢筋的混凝土保护层厚度不应小于（ ）mm。\n"
                                            "【选项】[\"A. 55\", \"B. 60\", \"C. 65\", \"D. 70\"]\n"
                                            "【答案】D\n"
                                            "【解析】直接接触土体浇筑的构件，其混凝土保护层厚度不应小于70mm。"
                                        ),
                                    },
                                }
                            ]
                        },
                    }
                ],
                "results": [],
                "trace": {
                    "lightweight_counters": {
                        "bank_hits": 1,
                        "llm_calls": 0,
                        "retriever_calls": 1,
                        "lightweight_batch_fallback": "disabled",
                    }
                },
            }

    monkeypatch.setattr("deeptutor.agents.question.coordinator.AgentCoordinator", FakeCoordinator)
    _patch_llm_config(monkeypatch)

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(_review_context(), bus))

    assert calls
    assert calls[0]["allow_lightweight_fallback"] is False
    result = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result.metadata["response"] != "No questions generated."
    assert "直接接触土体" in result.metadata["response"]
    assert result.metadata["active_object"] == {}
    assert result.metadata["question_followup_context"] == {}
    block = result.metadata["presentation"]["blocks"][0]
    assert block["review_mode"] is True
    question = block["questions"][0]
    assert "混凝土保护层厚度" in question["stem"]
    assert question["followup_context"]["correct_answer"] == "D"
    assert question["followup_context"]["options"]["D"] == "70"
