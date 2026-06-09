"""System-level compiled knowledge service facade.

The service may reuse construction-grading canonical bundles, but callers should
not have to import a grading namespace to get compiled teaching context.
"""
from __future__ import annotations


def test_system_compiled_knowledge_service_resolves_teaching_context() -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge

    out = general_knowledge.resolve_general_knowledge_context(
        "施工合同索赔成立条件是什么？"
    )

    assert out is not None
    assert out["authority"] == "luban_general_knowledge_context"
    assert out["tier"] == "teaching_context_not_answer_key"
    assert out["official_score_allowed"] is False
    assert out["llm_may_decide_correctness"] is False
    assert "索赔" in out["leaf_name_path"]
    assert out["query_plan"]["policy"] == "compiled_query_plan_v1"


def test_top_k_query_plan_does_not_require_single_winner(monkeypatch) -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge

    monkeypatch.setattr(general_knowledge._CR, "to_canonical", lambda _text: None)

    out = general_knowledge.resolve_general_knowledge_context("施工合同索赔成立条件是什么？")

    assert out is not None
    assert "索赔" in out["leaf_name_path"]
    assert out["query_plan"]["initial_leaf"] is None


def test_strict_primary_path_terms_reject_source_only_acceptance_match() -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge

    plan = general_knowledge.build_general_knowledge_query_plan("分部工程质量验收谁组织？")

    assert any(
        "primary_path_mismatch" in candidate.get("negative_evidence", [])
        for candidate in plan["candidates"]
        if "质量验收" in candidate.get("leaf_name_path", "")
        and "分部工程" not in candidate.get("leaf_name_path", "")
    )
    assert general_knowledge.resolve_general_knowledge_context("分部工程质量验收谁组织？") is None


def test_legacy_construction_grading_import_stays_compatible() -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge
    from deeptutor.services.construction_grading import general_knowledge_context

    assert (
        general_knowledge_context.resolve_general_knowledge_context
        is general_knowledge.resolve_general_knowledge_context
    )
    assert (
        general_knowledge_context.build_general_knowledge_query_plan
        is general_knowledge.build_general_knowledge_query_plan
    )
