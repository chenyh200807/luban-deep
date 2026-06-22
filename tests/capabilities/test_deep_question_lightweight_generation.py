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


def test_lightweight_question_review_without_bank_hit_disables_llm_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch)

    async def _miss_rag(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"answer": "", "provider": "stub", "kb_name": "stub-kb"}

    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.rag_search",
        _miss_rag,
    )
    coord.enable_idea_rag = True
    coord.kb_name = "stub-kb"

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="分析一道钢筋保护层的真题",
            preference="",
            num_questions=1,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
            allow_lightweight_fallback=False,
            allow_similar_source_variant=True,
        )
    )

    assert result.get("results") == []
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("bank_hits") == 0
    assert counters.get("llm_calls") == 0
    assert counters.get("lightweight_batch_fallback") == "disabled"
    assert fake_gen.call_count == 0
    assert fake_gen.batch_call_count == 0


def test_question_review_uses_similar_rag_source_for_variant_when_bank_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch)

    async def _similar_source_rag(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "answer": "相似来源：直接接触土体浇筑的普通钢筋混凝土构件，其混凝土保护层厚度不应小于70mm。",
            "provider": "stub",
            "kb_name": "stub-kb",
            "evidence_bundle": {
                "retrieval_status": "ok",
                "sources": [
                    {
                        "_source_group": "TEXTBOOK",
                        "chunk_id": "CET_1A411011_P0027_001",
                        "content": "混凝土保护层厚度：直接接触土体浇筑的构件不应小于70mm。",
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.rag_search",
        _similar_source_rag,
    )
    coord.enable_idea_rag = True
    coord.kb_name = "stub-kb"

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="分析一道钢筋保护层的真题",
            preference="",
            num_questions=1,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
            allow_lightweight_fallback=False,
            allow_similar_source_variant=True,
        )
    )

    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("bank_hits") == 0
    assert counters.get("llm_calls") == 1
    assert counters.get("lightweight_batch_fallback") == "similar_source_variant"
    assert fake_gen.call_count == 0
    assert fake_gen.batch_call_count == 1
    items = result.get("results") or []
    assert len(items) == 1
    qa_pair = items[0].get("qa_pair") or {}
    metadata = qa_pair.get("metadata") or {}
    grading_key = qa_pair.get("grading_key") or {}
    validation = qa_pair.get("validation") or {}
    assert metadata.get("source") == "similar_question_variant"
    assert metadata.get("question_review_variant_mode") is True
    assert metadata.get("variant_source") == "rag_answer_text"
    assert metadata.get("evidence_refs")
    assert grading_key.get("source") == "similar_question_variant"
    assert validation.get("source") == "similar_question_variant"


def test_question_review_uses_evidence_only_source_for_variant_when_bank_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch)

    async def _evidence_only_rag(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "answer": "",
            "provider": "stub",
            "kb_name": "stub-kb",
            "evidence_bundle": {
                "retrieval_status": "ok",
                "sources": [
                    {
                        "_source_group": "EXAM",
                        "chunk_id": "EXAM_1A412010_P0002_02",
                        "content": "直接接触土体浇筑的普通钢筋混凝土构件，其混凝土保护层厚度不应小于70mm。",
                    }
                ],
            },
        }

    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.rag_search",
        _evidence_only_rag,
    )
    coord.enable_idea_rag = True
    coord.kb_name = "stub-kb"

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="分析一道钢筋保护层的真题",
            preference="",
            num_questions=1,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
            allow_lightweight_fallback=False,
            allow_similar_source_variant=True,
        )
    )

    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("lightweight_batch_fallback") == "similar_source_variant"
    assert fake_gen.batch_call_count == 1
    qa_pair = (result.get("results") or [])[0].get("qa_pair") or {}
    metadata = qa_pair.get("metadata") or {}
    assert metadata.get("variant_source") == "rag_evidence_text"
    assert metadata.get("evidence_refs")


def test_lightweight_topic_rag_error_degrades_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch)

    async def _broken_rag(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("embedding config missing")

    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.rag_search",
        _broken_rag,
    )
    coord.enable_idea_rag = True
    coord.kb_name = "stub-kb"

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="分析一道钢筋保护层的真题",
            preference="",
            num_questions=1,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
            allow_lightweight_fallback=False,
        )
    )

    assert result.get("results") == []
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("bank_hits") == 0
    assert counters.get("llm_calls") == 0
    assert counters.get("lightweight_batch_fallback") == "disabled"
    retrieval = ((result.get("trace") or {}).get("batches") or [{}])[0].get("retrieval") or {}
    assert retrieval.get("error") == "embedding config missing"
    assert fake_gen.call_count == 0
    assert fake_gen.batch_call_count == 0


def test_question_review_builds_qapair_from_matching_evidence_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trace 85363 shape: exact_question can drift, but qbank evidence has the real MCQ."""
    coord, fake_gen = _stub_coordinator(monkeypatch)

    async def _hit_rag(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "answer": "",
            "provider": "stub",
            "kb_name": "stub-kb",
            "exact_question": {
                "stem": "不利于提高框架结构抗震性能的措施是（　　）。",
                "options": {"A": "加强梁柱节点", "B": "采用短柱"},
                "correct_answer": "B",
                "analysis": "这是一个不相关的检索命中，不能作为本轮讲评题。",
                "source_group": "question_exact_text",
            },
            "evidence_bundle": {
                "sources": [
                    {
                        "_source_group": "TEXTBOOK",
                        "chunk_id": "question-14576",
                        "content": (
                            "【题目】一般环境中，直接接触土体浇筑的构件，"
                            "其钢筋的混凝土保护层厚度不应小于（ ）mm。\n"
                            "【选项】[\"A. 55\", \"B. 60\", \"C. 65\", \"D. 70\"]\n"
                            "【答案】D\n"
                            "【解析】直接接触土体浇筑的构件，其混凝土保护层厚度不应小于70mm。"
                        ),
                    }
                ]
            },
        }

    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.rag_search",
        _hit_rag,
    )
    coord.enable_idea_rag = True
    coord.kb_name = "stub-kb"

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="分析一道钢筋保护层的真题",
            preference="",
            num_questions=1,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
            allow_lightweight_fallback=False,
        )
    )

    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("bank_hits") == 1
    assert counters.get("llm_calls") == 0
    assert fake_gen.call_count == 0
    assert fake_gen.batch_call_count == 0
    items = result.get("results") or []
    assert len(items) == 1
    qa_pair = items[0].get("qa_pair") or {}
    assert "混凝土保护层厚度" in qa_pair.get("question", "")
    assert qa_pair.get("options") == {"A": "55", "B": "60", "C": "65", "D": "70"}
    assert qa_pair.get("explanation") == "直接接触土体浇筑的构件，其混凝土保护层厚度不应小于70mm。"
    assert (qa_pair.get("grading_key") or {}).get("correct_answer") == "D"
    assert (qa_pair.get("metadata") or {}).get("source") == "questions_bank"
    assert (qa_pair.get("metadata") or {}).get("source_group") == "TEXTBOOK"
    metadata = qa_pair.get("metadata") or {}
    assert metadata.get("scoring_points") == [
        "圈出题干对象：一般环境中，直接接触土体浇筑的构件，其钢筋的混凝土保护层厚度不应小于（ ）mm。",
        "抓住标准答案对应的规范数值：D. 70。",
        "逐项排除相近但不符合题库解析的干扰数值。",
    ]
    assert metadata.get("pitfalls") == [
        "把相近数值当成规范要求，忽略题干对象。",
        "只记住保护层厚度这一考点，没有锁定“直接接触土体浇筑的构件”。",
    ]
    assert metadata.get("mnemonic") == "直接接土先加厚，保护层记 70。"
    option_analysis = metadata.get("option_analysis") or []
    assert len(option_analysis) == 4
    assert option_analysis[0]["key"] == "A"
    assert "低于标准值 70" in option_analysis[0]["analysis"]
    assert option_analysis[-1] == {
        "key": "D",
        "verdict": "正确",
        "analysis": "70 对应题库标准答案；直接接触土体浇筑的构件，其混凝土保护层厚度不应小于70mm。",
    }


def test_question_review_does_not_build_qapair_from_unrelated_evidence_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coord, fake_gen = _stub_coordinator(monkeypatch)

    async def _hit_rag(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "answer": "",
            "provider": "stub",
            "kb_name": "stub-kb",
            "exact_question": {},
            "evidence_bundle": {
                "sources": [
                    {
                        "_source_group": "TEXTBOOK",
                        "chunk_id": "question-unrelated",
                        "content": (
                            "【题目】不利于提高钢筋混凝土框架结构抗震性能的措施是（　　）。\n"
                            "【选项】[\"A. 加强梁柱节点\", \"B. 采用短柱\", \"C. 提高延性\", \"D. 合理布置抗侧力构件\"]\n"
                            "【答案】B\n"
                            "【解析】短柱延性差，不利于抗震。"
                        ),
                    }
                ]
            },
        }

    monkeypatch.setattr(
        "deeptutor.agents.question.coordinator.rag_search",
        _hit_rag,
    )
    coord.enable_idea_rag = True
    coord.kb_name = "stub-kb"

    result = asyncio.run(
        coord.generate_from_topic(
            user_topic="分析一道钢筋保护层的真题",
            preference="",
            num_questions=1,
            difficulty="easy",
            question_type="choice",
            lightweight_generation=True,
            require_explanation=False,
            allow_lightweight_fallback=False,
        )
    )

    assert result.get("results") == []
    counters = (result.get("trace") or {}).get("lightweight_counters") or {}
    assert counters.get("bank_hits") == 0
    assert counters.get("llm_calls") == 0
    assert fake_gen.call_count == 0
    assert fake_gen.batch_call_count == 0


def test_structured_anchor_parser_handles_inline_options_without_swallowing_answer() -> None:
    parsed = AgentCoordinator._extract_structured_anchor_from_answer(
        "【题目】验槽通常主要采用什么方法？\n"
        "A. 观察法\n"
        "B. 钎探法\n"
        "C. 洛阳铲法\n"
        "D. 钻探法\n"
        "【答案】A\n"
        "【解析】验槽通常主要采用观察法，钎探法是辅助方法。"
    )

    assert parsed is not None
    assert parsed["reference_question"] == "验槽通常主要采用什么方法？"
    assert parsed["reference_answer"] == "A"
    assert parsed["options"] == {
        "A": "观察法",
        "B": "钎探法",
        "C": "洛阳铲法",
        "D": "钻探法",
    }
    assert parsed["analysis"] == "验槽通常主要采用观察法，钎探法是辅助方法。"


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


def test_looks_like_non_exam_garbage_blocks_garbage_not_real_questions():
    """阶段2 止血(B 出题管线):明显非一建考试题(拼音/字形/英文/语用/通识)必须被拦,
    绝不 emit 给学生;真实建筑/市政工程题不可误伤(误判→漏判防回归)。"""
    from deeptutor.capabilities.deep_question import _looks_like_non_exam_garbage

    for garbage in [
        "### 第1题 '出'字的正确读音是? A.chū B.cū C.chù D.qū",
        "### 第1题 '来'的字形结构属于? A.左右结构 B.上下结构",
        "Which is a characteristic of a 莫名其妙的题? A. xxx B. yyy",
        "法国的首都是哪里? A.巴黎 B.伦敦 C.柏林",
        "'行行行你说得对'这句话最常用来表达什么? A.真诚赞同 B.讽刺认同",
    ]:
        assert _looks_like_non_exam_garbage(garbage), f"未拦垃圾题: {garbage[:30]}"

    for real in [
        "### 第1题 危大工程中需组织专家论证的是? A.开挖深度4m基坑 B.跨度16m模板支撑",
        "热拌沥青混合料初压温度应控制在多少摄氏度? A.110 B.135 C.150 D.170",
        "施工总平面布置中,易燃易爆库房应布置在? A.下风向 B.上风向 C.主导风向上风侧",
        "地下连续墙单元槽段长度宜为多少? A.4~6m B.8~10m C.12~15m",
    ]:
        assert not _looks_like_non_exam_garbage(real), f"误伤真题: {real[:30]}"
