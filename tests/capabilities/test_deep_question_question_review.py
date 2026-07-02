from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus


ROOT = Path(__file__).resolve().parents[2]


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


def _review_context_with_canonical() -> UnifiedContext:
    """A question_review context carrying the canonical turn_semantic_decision the
    orchestrator supplies for this scene (turn.md §硬约束 24). Control-plane 治本
    Action 2: deep_question is a READER of the orchestrator's canonical decision; the
    main review-render path fail-fasts (no second-authority fabrication) if it is
    absent, so unit tests that drive the render path directly must supply it just like
    every production entry route (question_review-no-active inject / canonical resolve /
    preselect inject) does."""
    ctx = _review_context()
    ctx.metadata["turn_semantic_decision"] = {
        "relation_to_active_object": "ask_about_active_object",
        "next_action": "route_to_followup_explainer",
        "allowed_patch": "no_state_change",
        "confidence": 1.0,
        "reason": "orchestrator question_review canonical decision",
    }
    return ctx


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
    events = await _collect_events(lambda bus: capability.run(_review_context_with_canonical(), bus))

    assert calls
    assert calls[0]["lightweight_generation"] is True
    assert calls[0]["allow_lightweight_fallback"] is False
    assert calls[0]["allow_similar_source_variant"] is True
    result = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "### 第 1 题" in result.metadata["response"]
    assert "关于混凝土保护层厚度" in result.metadata["response"]
    assert "A. I-A环境中" in result.metadata["response"]
    assert "B. 直接接触土体" in result.metadata["response"]
    assert "正确答案" in result.metadata["response"]
    assert "解析要点" in result.metadata["response"]
    assert "采分点" in result.metadata["response"]
    assert "易错点" in result.metadata["response"]
    assert "记忆口诀" in result.metadata["response"]
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
    assert calls[0]["allow_similar_source_variant"] is True
    result = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "还没有定位到" in result.metadata["response"]
    assert "请把完整题干" in result.metadata["response"]
    assert result.metadata["active_object"] == {}
    assert result.metadata["question_followup_context"] == {}
    assert "presentation" not in result.metadata


@pytest.mark.asyncio
async def test_question_review_variant_marks_generated_card_as_variant(
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
                            "question_id": "q_variant",
                            "question": "关于混凝土保护层厚度，下列说法正确的是（ ）。",
                            "question_type": "choice",
                            "options": {
                                "A": "直接接触土体浇筑的构件不应小于50mm",
                                "B": "直接接触土体浇筑的构件不应小于70mm",
                            },
                            "correct_answer": "",
                            "explanation": "",
                            "grading_key": {
                                "correct_answer": "B",
                                "source": "similar_question_variant",
                                "minimal_rationale": "基于相似来源变式：直接接触土体浇筑的构件不应小于70mm。",
                            },
                            "metadata": {
                                "source": "similar_question_variant",
                                "question_review_variant_mode": True,
                                "knowledge_context": "题库参考资料：直接接触土体浇筑的构件不应小于70mm。",
                            },
                        },
                    }
                ],
                "trace": {
                    "lightweight_counters": {
                        "bank_hits": 0,
                        "llm_calls": 1,
                        "retriever_calls": 1,
                        "lightweight_batch_fallback": "similar_source_variant",
                    }
                },
            }

    monkeypatch.setattr("deeptutor.agents.question.coordinator.AgentCoordinator", FakeCoordinator)
    _patch_llm_config(monkeypatch)

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(_review_context_with_canonical(), bus))

    assert calls
    assert calls[0]["allow_lightweight_fallback"] is False
    assert calls[0]["allow_similar_source_variant"] is True
    result = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "基于题库/知识库相似来源生成的变式题" in result.metadata["response"]
    assert "不是原题复刻" in result.metadata["response"]
    assert "正确答案" in result.metadata["response"]
    assert result.metadata["active_object"] == {}
    assert result.metadata["question_followup_context"] == {}
    block = result.metadata["presentation"]["blocks"][0]
    assert block["review_mode"] is True
    assert block["submit_hint"] == "题目讲评，已展示解析，不需要提交答案。"


def test_deep_question_does_not_contain_question_review_evidence_parser() -> None:
    source = (ROOT / "deeptutor/capabilities/deep_question.py").read_text(encoding="utf-8")
    forbidden = (
        "_parse_question_review_evidence_ref",
        "_parse_question_review_options",
        "_promote_question_review_evidence_result",
        "_question_review_qa_pair_from_template_evidence",
        "_question_review_evidence_matches_topic",
    )
    for needle in forbidden:
        assert needle not in source


@pytest.mark.asyncio
async def test_question_review_missing_canonical_result_does_not_parse_template_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """deep_question is a wrapper; qbank/evidence parsing belongs in the coordinator."""

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
    assert calls[0]["allow_similar_source_variant"] is True
    result = next(event for event in events if event.type == StreamEventType.RESULT)
    assert "还没有定位到" in result.metadata["response"]
    assert "请把完整题干" in result.metadata["response"]
    assert result.metadata["active_object"] == {}
    assert result.metadata["question_followup_context"] == {}
    assert "presentation" not in result.metadata


def test_missing_question_review_feedback_no_prompt_leak() -> None:
    # task#22 残留漏点(Langfuse 实证):此罐头此前逐字嵌入 focus=topic，而上游 caller
    # 传入的 topic 可能被污染成内部出题锚点 prompt → system prompt 脚手架原样泄露给学生。
    # 去毒后:不嵌入任何外部串(与 question_lifecycle_skills low_information 罐头同口径)。
    from deeptutor.capabilities.deep_question import _render_missing_question_review_feedback

    poisoned = (
        "继续 请严格围绕以下当前学习锚点出题，不要偏题，不要超纲；"
        "当前会话主题：给我出一道市政公用工程实务的单选题练练"
    )
    out = _render_missing_question_review_feedback(poisoned)
    assert "请严格围绕" not in out
    assert "当前会话主题" not in out
    assert "继续 请严格围绕" not in out
    assert "屋面防水" not in _render_missing_question_review_feedback("屋面防水")
    assert "还没有定位到" in out and "请把完整题干" in out


def _missing_question_review_coordinator(calls: list[dict[str, Any]]):
    """Coordinator returning a non-renderable result → drives the S5 bare-build
    (missing_question_bank_hit) fallback at deep_question.py:~4281."""

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
                "templates": [],
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

    return FakeCoordinator


@pytest.mark.asyncio
async def test_s5_bare_build_appends_unconditional_fabricate_shadow_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OBSERVE-ONLY live-shadow blind-spot #2: the S5 review-render bare
    ``build_turn_semantic_decision(...)`` fabricates a second-authority decision
    UNCONDITIONALLY — even when a canonical decision is present. It must append a
    ``unconditional_fabricate`` shadow hit (site=S5_review_render) carrying the
    scene and the REAL canonical_present, so the 7-day window can prove (or
    disprove) generation/review fabrication per-site/per-scene. RED before the
    append site exists."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.AgentCoordinator",
        _missing_question_review_coordinator(calls),
    )
    _patch_llm_config(monkeypatch)

    # Canonical decision IS present in metadata — S5 still fabricates a second
    # one (the blind spot the canonical-missing guard cannot see).
    ctx = _review_context()
    ctx.metadata["turn_semantic_decision"] = {
        "relation_to_active_object": "ask_about_active_object",
        "next_action": "route_to_followup_explainer",
        "allowed_patch": "no_state_change",
        "confidence": 1.0,
        "reason": "canonical present",
    }

    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(ctx, bus))

    hits = ctx.metadata["trace_metadata"]["control_plane_shadow_hits"]
    s5_hits = [h for h in hits if h.get("site") == "S5_review_render"]
    assert len(s5_hits) == 1, hits
    hit = s5_hits[0]
    assert hit["fact"] == "turn_semantic_decision"
    assert hit["writer_role"] == "unconditional_fabricate"
    assert hit["writer_symbol"] == "run"
    assert hit["path"] == "deep_question"
    assert hit["scene"] == "question_review"
    # canonical_present is computed REALLY — here it is True, exposing that S5
    # fabricates even when the canonical decision exists.
    assert hit["canonical_present"] is True


@pytest.mark.asyncio
async def test_canonical_missing_guard_hit_carries_scene_and_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OBSERVE-ONLY blind-spot #1: the canonical-missing guard hit must carry the
    scene + a ``site=canonical_missing_guard`` tag so the window can attribute
    fabrication per-scene (generation vs review). The review context has NO
    canonical turn_semantic_decision → the guard fires. RED before the fields
    are added."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.AgentCoordinator",
        _missing_question_review_coordinator(calls),
    )
    _patch_llm_config(monkeypatch)

    ctx = _review_context()  # no canonical turn_semantic_decision → guard fires
    capability = DeepQuestionCapability()
    await _collect_events(lambda bus: capability.run(ctx, bus))

    hits = ctx.metadata["trace_metadata"]["control_plane_shadow_hits"]
    guard_hits = [h for h in hits if h.get("site") == "canonical_missing_guard"]
    assert len(guard_hits) == 1, hits
    guard = guard_hits[0]
    assert guard["writer_role"] == "compat_projection"
    assert guard["canonical_present"] is False
    assert guard["scene"] == "question_review"
