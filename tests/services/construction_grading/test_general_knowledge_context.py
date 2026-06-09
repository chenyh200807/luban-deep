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
    assert out["confidence"]["status"] == "high"
    assert out["confidence"]["policy"] == "query_path_source_alignment_v1"


def test_wrong_chapter_candidate_falls_open_before_injection() -> None:
    assert gkc.resolve_general_knowledge_context("建筑防火分区面积怎么理解？") is None


def test_top_k_query_plan_reranks_contract_claim_to_claim_path() -> None:
    out = gkc.resolve_general_knowledge_context("施工合同索赔成立条件是什么？")

    assert out is not None
    assert "索赔" in out["leaf_name_path"]
    assert out["query_plan"]["intent"] == "case_judgment"
    assert out["confidence"]["status"] == "high"


def test_query_plan_rejects_source_polluted_wrong_path_for_total_float() -> None:
    plan = gkc.build_general_knowledge_query_plan("双代号网络计划总时差怎么算？")

    assert plan["intent"] == "calculation"
    assert any(
        "source_path_conflict" in candidate.get("negative_evidence", [])
        for candidate in plan["candidates"]
        if "水泥" in candidate.get("leaf_name_path", "")
    )
    assert gkc.resolve_general_knowledge_context("双代号网络计划总时差怎么算？") is None


def test_off_syllabus_text_falls_open_to_none() -> None:
    assert gkc.resolve_general_knowledge_context("今天天气怎么样啊随便聊聊") is None


def test_empty_text_falls_open() -> None:
    assert gkc.resolve_general_knowledge_context("") is None
    assert gkc.resolve_general_knowledge_context("   ") is None
