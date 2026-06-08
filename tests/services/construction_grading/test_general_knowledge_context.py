"""M34 Task 1: general knowledge context composes canonical resolution with compiled teaching packs."""
from __future__ import annotations

from deeptutor.services.construction_grading import general_knowledge_context as gkc


def test_anchor_candidates_walk_leaf_to_ancestors() -> None:
    assert gkc._anchor_candidates("1A411011-01-a") == [
        "1A411011-01-a",
        "1A411011-01",
        "1A411011",
    ]
    assert gkc._anchor_candidates("1A411011") == ["1A411011"]
    assert gkc._anchor_candidates("") == []


def test_free_text_resolves_to_teaching_pack() -> None:
    out = gkc.resolve_general_knowledge_context("高层住宅的建筑高度是怎么界定的？")
    assert out is not None, "on-syllabus knowledge question must resolve to a teaching pack"
    assert out["tier"] == "teaching_context_not_answer_key"
    assert out["official_score_allowed"] is False
    assert out["llm_may_decide_correctness"] is False
    assert out["classified_leaf"]
    assert out["resolved_anchor"]
    assert isinstance(out["sources"], dict)
    assert any(out["sources"].get(s) for s in ("textbook", "standard", "lecture", "question"))


def test_off_syllabus_text_falls_open_to_none() -> None:
    assert gkc.resolve_general_knowledge_context("今天天气怎么样啊随便聊聊") is None


def test_empty_text_falls_open() -> None:
    assert gkc.resolve_general_knowledge_context("") is None
    assert gkc.resolve_general_knowledge_context("   ") is None
