from __future__ import annotations

import json

from deeptutor.services.construction_grading.compiled_context import (
    LubanContextPack,
    build_luban_context_pack,
)


def _objective_release_resolution() -> dict:
    return {
        "status": "resolved",
        "question_id": "CET_2023_01",
        "question_type": "single_choice",
        "stem": "建筑物的构成不包括？",
        "options": {"A": "结构体系", "B": "围护体系", "C": "设备体系", "D": "投标体系"},
        "answer_key": "D",
        "registry_status": "release_candidate",
        "source_refs": [{"ref": "textbook:1A411011", "provenance_kind": "compiled_source_ref"}],
    }


def test_objective_release_candidate_allows_controlled_official() -> None:
    pack = build_luban_context_pack(resolution=_objective_release_resolution())
    assert isinstance(pack, LubanContextPack)
    assert pack.official_score_allowed is True
    assert pack.diagnostic_policy["controlled_official"] is True
    assert pack.diagnostic_policy["unverified_diagnostic_allowed"] is False
    assert pack.diagnostic_policy["llm_may_change_answer_key"] is False
    assert pack.diagnostic_policy["retrieval_may_become_answer_key"] is False
    json.dumps(pack.to_dict(), ensure_ascii=False)


def test_case_signed_rubric_official_mode() -> None:
    resolution = {
        "status": "resolved",
        "question_id": "CASE_2024_03",
        "question_type": "case",
        "rubric": [{"point_id": "p1", "text": "工期顺延需书面通知"}],
        "registry_status": "release_candidate",
        "required_terms": ["书面通知"],
        "risk_flags": ["high_risk_point"],
    }
    pack = build_luban_context_pack(resolution=resolution)
    assert pack.official_score_allowed is True
    assert pack.rubric_context["rubric_signed"] is True
    assert pack.rubric_context["required_terms"] == ["书面通知"]
    assert pack.rubric_context["risk_flags"] == ["high_risk_point"]


def test_candidate_grade_blocks_official_score() -> None:
    resolution = {
        "status": "candidate",
        "question_id": "CAND_99",
        "question_type": "single_choice",
        "answer_key": "B",
        "registry_status": "real_source_candidate",
    }
    pack = build_luban_context_pack(resolution=resolution)
    assert pack.official_score_allowed is False
    assert pack.diagnostic_policy["needs_review_reason"] == "candidate_not_release_truth"
    assert pack.diagnostic_policy["candidate_work_order"]["promote_to_release"] is False


def test_retrieval_only_sources_never_answer_key() -> None:
    resolution = {
        "status": "resolved",
        "question_id": "CONCEPT_1",
        "question_type": "concept",
        "registry_status": "release_candidate",
    }
    sources = [
        {
            "id": "CET_1A411011_P002",
            "source_table": "kb_v5.chunks",
            "title": "建筑物构成",
            "source_span": "p.2 建筑物构成",
            "content_hash": "abc123",
            "score": 0.9,
        }
    ]
    pack = build_luban_context_pack(resolution=resolution, retrieval_sources=sources)
    assert pack.source_context["retrieval_is_grading_authority"] is False
    rref = pack.source_context["retrieval_refs"][0]
    assert rref["is_answer_key"] is False
    assert rref["source_table"] == "kb_v5.chunks"
    assert rref["provenance_kind"] == "retrieval_only"


def test_open_world_unresolved_no_official_no_leak() -> None:
    resolution = {
        "status": "unresolved",
        "question_id": "",
        "stem": "施工现场临时用电三级配电是什么？",
    }
    pack = build_luban_context_pack(resolution=resolution)
    assert pack.official_score_allowed is False
    assert pack.diagnostic_policy["unverified_diagnostic_allowed"] is True
    assert pack.diagnostic_policy["needs_review_reason"] == "not_in_bank_open_world"
    assert pack.diagnostic_policy["candidate_work_order"]["needed"] is True
    assert pack.diagnostic_policy["candidate_work_order"]["kind"] == "open_world_compiler_candidate"
    # No official answer leak: unresolved with an answer key would trip the guard.
    assert pack.provenance["no_official_answer_leak"] is True


def test_unresolved_with_answer_key_flags_leak_guard() -> None:
    # An unresolved question must never carry a usable official answer key into the pack.
    resolution = {"status": "unresolved", "question_id": "X", "answer_key": "A"}
    pack = build_luban_context_pack(resolution=resolution)
    assert pack.official_score_allowed is False
    assert pack.provenance["no_official_answer_leak"] is False  # guard detects the leak attempt


def test_learner_context_not_second_memory_authority() -> None:
    pack = build_luban_context_pack(
        resolution=_objective_release_resolution(),
        learner_context={"pcp": {"weak_points": ["合同变更"]}, "active_training_intent": "case"},
    )
    assert pack.learner_context["is_second_memory_authority"] is False
    assert pack.learner_context["active_training_intent"] == "case"
    assert pack.budget_policy["efficiency_is_constraint_not_goal"] is True


def test_pack_hash_is_stable_and_provenance_present() -> None:
    a = build_luban_context_pack(resolution=_objective_release_resolution())
    b = build_luban_context_pack(resolution=_objective_release_resolution())
    assert a.provenance["pack_hash"] == b.provenance["pack_hash"]
    assert a.provenance["schema_version"] == "luban_context_pack.v1"
