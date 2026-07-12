from __future__ import annotations

import pytest

from deeptutor.services.assessment.deep_explanation import (
    DailyExplanationBudget,
    attach_deep_explanation,
    build_explanation_cache_key,
    build_static_deep_explanation,
)


def test_deep_explanation_cache_key_includes_result_hash() -> None:
    key1 = build_explanation_cache_key("quiz1", "q1", "answer-a", "grade-1", "p1-v1")
    key2 = build_explanation_cache_key("quiz1", "q1", "answer-a", "grade-2", "p1-v1")

    assert key1 != key2


def test_deep_explanation_never_changes_score() -> None:
    report = {
        "quiz_id": "quiz1",
        "score_summary": {"score_pct": 50, "correct_count": 1},
        "score": 50,
        "wrong_items": [{"question_id": "q1", "simple_explanation": "先看防水节点。"}],
    }

    explained = attach_deep_explanation(
        report,
        question_id="q1",
        explanation={"summary": "地下防水节点需要先判断构造层次。"},
    )

    assert explained["score"] == 50
    assert explained["score_summary"] == report["score_summary"]
    assert explained["wrong_items"][0]["deep_explanation"]["summary"] == "地下防水节点需要先判断构造层次。"
    assert "deep_explanation" not in report["wrong_items"][0]


def test_daily_explanation_budget_blocks_cache_miss_after_limit() -> None:
    budget = DailyExplanationBudget(max_misses_per_user_per_day=2)

    assert budget.record_cache_miss("u1") == 1
    assert budget.record_cache_miss("u1") == 2
    with pytest.raises(RuntimeError, match="assessment_deep_explanation_budget_exceeded"):
        budget.record_cache_miss("u1")


def test_static_deep_explanation_is_projection_only() -> None:
    explanation = build_static_deep_explanation(
        question={
            "question_id": "q1",
            "question_stem": "地下防水卷材搭接做法正确的是？",
            "simple_explanation": "搭接宽度和节点处理要符合规范。",
            "knowledge_points": ["地下防水"],
        },
        learner_answer="B",
        correct_answer="A",
    )

    assert explanation["score_mutation_allowed"] is False
    assert explanation["knowledge_points"] == ["地下防水"]
    assert "搭接宽度" in explanation["summary"]


@pytest.mark.asyncio
async def test_generate_llm_deep_explanation_observes_call(monkeypatch) -> None:
    """Observe-only wiring: the out-of-turn-pipeline LLM call carries an
    identifiable Langfuse generation name, keeps its explicit max_tokens ceiling,
    and records a duration sample into the runtime metrics histogram."""
    import deeptutor.services.llm as llm_module
    from deeptutor.api.runtime_metrics import (
        get_turn_runtime_metrics,
        reset_turn_runtime_metrics,
    )
    from deeptutor.services.assessment.deep_explanation import (
        generate_llm_deep_explanation,
    )

    reset_turn_runtime_metrics()
    captured: dict[str, object] = {}

    async def _fake_complete(prompt, **kwargs):
        captured.update(kwargs)
        captured["prompt"] = prompt
        return '{"summary": "先判断构造层次。", "why_wrong": "漏看限定词。"}'

    monkeypatch.setattr(llm_module, "complete", _fake_complete)

    result = await generate_llm_deep_explanation(
        question={"question_id": "q1", "question_stem": "地下防水", "options": ["A", "B"]},
        learner_answer="A",
        correct_answer="B",
        quiz_id="quiz1",
        question_id="q1",
    )

    assert captured["observation_name"] == "assessment.deep_explanation"
    assert captured["max_tokens"] == 1200
    assert result["summary"] == "先判断构造层次。"

    entry = get_turn_runtime_metrics().snapshot()["assessment_explanation_ms"]
    assert entry is not None
    assert entry["count"] == 1
    reset_turn_runtime_metrics()


@pytest.mark.asyncio
async def test_generate_llm_deep_explanation_records_duration_even_on_error(monkeypatch) -> None:
    """Duration is recorded in a finally block, so a failed LLM call still yields
    an ops-visible latency sample and the error propagates unchanged."""
    import deeptutor.services.llm as llm_module
    from deeptutor.api.runtime_metrics import (
        get_turn_runtime_metrics,
        reset_turn_runtime_metrics,
    )
    from deeptutor.services.assessment.deep_explanation import (
        generate_llm_deep_explanation,
    )

    reset_turn_runtime_metrics()

    async def _boom(prompt, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm_module, "complete", _boom)

    with pytest.raises(RuntimeError, match="provider down"):
        await generate_llm_deep_explanation(
            question={"question_id": "q1"},
            learner_answer="A",
            correct_answer="B",
            quiz_id="quiz1",
            question_id="q1",
        )

    entry = get_turn_runtime_metrics().snapshot()["assessment_explanation_ms"]
    assert entry is not None
    assert entry["count"] == 1
    reset_turn_runtime_metrics()
