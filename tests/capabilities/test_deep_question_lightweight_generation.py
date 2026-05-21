"""
plan §Phase 2 Batch B / §goal Batch B 必跑测试 (review-2026-05-20).

覆盖：
  * lightweight=True 时 coordinator 跳过 idea_agent。
  * 1-3 题 batch generator 并行调用一次（每题 1 次 LLM）。
  * questions_bank 命中时 LLM calls = 0（短路）。
  * QAPair 携带 hidden grading_key。
  * trace counters 字段。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from deeptutor.agents.question.coordinator import AgentCoordinator
from deeptutor.agents.question.models import QAPair, QuestionTemplate


class _FakeGenerator:
    """Stub generator with both batch and per-item entry points.

    * ``process_batch_lightweight`` is the main lightweight path (1 LLM per batch).
    * ``process`` is only the fallback path; call_count counts per-item LLM.
    """

    def __init__(self, batch_fail: bool = False) -> None:
        self.call_count = 0
        self.batch_call_count = 0
        self.last_lightweight: bool | None = None
        self.batch_fail = batch_fail

    async def process_batch_lightweight(
        self,
        templates: list[QuestionTemplate],
        user_topic: str = "",
        preference: str = "",
        history_context: str = "",
    ) -> list[QAPair] | None:
        self.batch_call_count += 1
        if self.batch_fail:
            return None
        return [
            QAPair(
                question_id=t.question_id,
                question=f"Stub Q for {t.concentration}",
                correct_answer="",
                explanation="",
                question_type=t.question_type or "choice",
                options={"A": "a", "B": "b", "C": "c", "D": "d"},
                concentration=t.concentration,
                difficulty=t.difficulty,
                validation={"schema_ok": True, "source": "lightweight_batch_llm"},
                metadata={"lightweight_generation": True},
                grading_key={
                    "correct_answer": "B",
                    "scoring_points": ["sp1"],
                    "common_traps": [],
                    "minimal_rationale": "",
                    "source": "lightweight_batch_llm",
                },
            )
            for t in templates
        ]

    async def process(
        self,
        template: QuestionTemplate,
        user_topic: str = "",
        preference: str = "",
        history_context: str = "",
        previous_questions: Any | None = None,
        require_explanation: bool = True,
        lightweight_generation: bool = False,
    ) -> QAPair:
        self.call_count += 1
        self.last_lightweight = lightweight_generation
        return QAPair(
            question_id=template.question_id,
            question=f"Stub Q for {template.concentration}",
            correct_answer="B",
            explanation="",
            question_type=template.question_type or "choice",
            options={"A": "a", "B": "b", "C": "c", "D": "d"},
            concentration=template.concentration,
            difficulty=template.difficulty,
            validation={"schema_ok": True},
            metadata={"lightweight_generation": lightweight_generation},
        )


def _stub_coordinator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    batch_fail: bool = False,
) -> tuple[AgentCoordinator, _FakeGenerator]:
    # 避免 BaseAgent 真的去加载 LLM 配置；patch _create_generator 与 idea agent。
    fake_gen = _FakeGenerator(batch_fail=batch_fail)
    monkeypatch.setattr(AgentCoordinator, "_create_generator", lambda self: fake_gen)

    class _IdeaAgentNeverCalled:
        async def process(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("idea_agent must NOT be called in lightweight path")

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: _IdeaAgentNeverCalled(),
    )

    async def _no_rag(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"answer": "", "provider": "stub"}

    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.rag_search",
        _no_rag,
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_persist_summary",
        lambda self, summary: None,
    )

    coord = AgentCoordinator(language="zh", enable_idea_rag=False)
    return coord, fake_gen


def test_lightweight_uses_single_llm_batch_for_three_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # plan §Batch B Gap 1 — 1-3 题必须一次 LLM。
    coord, fake_gen = _stub_coordinator(monkeypatch)

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出3题",
            preference="",
            num_questions=3,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )

    assert fake_gen.batch_call_count == 1, "1-3 题必须用 1 次 batch LLM"
    assert fake_gen.call_count == 0, "成功 batch 路径不应触发逐题 fallback"
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("llm_calls") == 1
    assert counters.get("retriever_calls") == 1
    assert counters.get("generated_explanation") is False
    assert counters.get("lightweight_batch_fallback") == "none"


def test_lightweight_uses_at_most_two_llm_calls_for_five_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # plan §Batch B Gap 1 — 4-5 题最多 2 次 LLM。
    coord, fake_gen = _stub_coordinator(monkeypatch)

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出5题",
            preference="",
            num_questions=5,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )

    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("llm_calls") <= 2, "4-5 题最多 2 次 LLM"
    assert counters.get("lightweight_batch_fallback") in {"none", "split_batch"}


def test_lightweight_falls_back_to_parallel_when_batch_path_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # plan §Batch B Gap 1 — batch fail 时降级到 parallel，trace 必须标记。
    coord, fake_gen = _stub_coordinator(monkeypatch, batch_fail=True)

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出2题",
            preference="",
            num_questions=2,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("lightweight_batch_fallback") == "parallel"
    # 2 题 parallel fallback：1 次 batch (failed) + 2 次 per-item = 3 次 llm_calls
    assert counters.get("llm_calls") >= 2
    assert fake_gen.call_count == 2


def test_lightweight_results_carry_hidden_grading_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, _ = _stub_coordinator(monkeypatch)
    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出2题",
            preference="",
            num_questions=2,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )
    items = result.get("results") or []
    assert items, "lightweight summary should include result rows"
    for row in items:
        qa_pair = row.get("qa_pair") or {}
        gk = qa_pair.get("grading_key") or {}
        assert isinstance(gk, dict)
        assert gk.get("correct_answer"), "grading_key.correct_answer must be set for lightweight QAPair"
        assert gk.get("source") in {"lightweight_batch_llm", "lightweight_llm"}


def test_lightweight_bank_hit_short_circuits_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """plan §Phase 2 Step 2.4 (B1) — questions_bank 命中应该跳过 LLM。"""
    coord, fake_gen = _stub_coordinator(monkeypatch)

    async def _hit_rag(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "answer": "",
            "provider": "stub",
            "kb_name": "stub-kb",
            "exact_question": {
                "stem": "下列哪一项属于法律？",
                "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
                "correct_answer": "A",
                "analysis": "由 questions_bank 命中。",
                "source_group": "exact_question",
            },
            "evidence_bundle": {
                "sources": [
                    {
                        "_source_group": "questions_bank",
                        "chunk_id": "tb_q_1",
                        "stem": "下列哪一项属于法律？",
                        "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
                    }
                ]
            },
        }

    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.rag_search",
        _hit_rag,
    )
    # 同时切换 enable_idea_rag，让 anchor 能调 rag_search
    coord.enable_idea_rag = True
    coord.kb_name = "stub-kb"

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出1题，考一下法律基础",
            preference="",
            num_questions=1,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("bank_hits") == 1, "exact_question 命中必须计入 bank_hits"
    assert fake_gen.call_count == 0, "questions_bank 命中应该完全跳过 LLM"
    assert counters.get("llm_calls") == 0
    # QA item 应该携带 grading_key 来自 questions_bank
    items = result.get("results") or []
    assert items
    qa_pair = items[0].get("qa_pair") or {}
    gk = qa_pair.get("grading_key") or {}
    assert gk.get("source") == "questions_bank"
    assert gk.get("correct_answer") == "A"


def test_lightweight_three_questions_counters_equal_real_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch)
    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出3题",
            preference="",
            num_questions=3,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert fake_gen.batch_call_count == 1
    assert fake_gen.call_count == 0
    assert counters.get("llm_calls") == fake_gen.batch_call_count + fake_gen.call_count == 1


def test_lightweight_five_questions_counters_exactly_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch)
    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出5题",
            preference="",
            num_questions=5,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert fake_gen.batch_call_count == 2
    assert fake_gen.call_count == 0
    assert counters.get("llm_calls") == fake_gen.batch_call_count + fake_gen.call_count == 2
    assert counters.get("lightweight_batch_fallback") == "split_batch"


def test_lightweight_four_questions_counters_exactly_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch)
    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出4题",
            preference="",
            num_questions=4,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert fake_gen.batch_call_count == 2
    assert counters.get("llm_calls") == 2
    assert counters.get("lightweight_batch_fallback") == "split_batch"


def test_lightweight_parallel_fallback_counters_match_real_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch, batch_fail=True)
    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="再出2题",
            preference="",
            num_questions=2,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
        )
    )
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert fake_gen.batch_call_count == 1
    assert fake_gen.call_count == 2
    assert counters.get("llm_calls") == fake_gen.batch_call_count + fake_gen.call_count == 3
    assert counters.get("lightweight_batch_fallback") == "parallel"
