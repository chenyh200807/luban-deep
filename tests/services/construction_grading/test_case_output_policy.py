from __future__ import annotations

from deeptutor.services.construction_grading.case_output_policy import (
    build_case_grading_diagnostic_only_response,
    case_grading_score_authority_available,
    should_demote_case_grading_hard_score,
)
from deeptutor.tutorbot.agent.loop import AgentLoop


def test_case_grading_without_score_authority_demotes_hard_score() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "authority_applied": False,
        "exact_question": {},
    }
    response = "## 预计得分\n**4分 / 满分5分**\n"

    assert should_demote_case_grading_hard_score(response, runtime_metadata=metadata)
    fallback = build_case_grading_diagnostic_only_response(
        "案例：墙体施工。我的答案：不妥，应龄期28天。帮我批改"
    )
    assert "本次不硬估标准分" in fallback
    assert "预计得分\n**4分" not in fallback
    assert "你当前作答：不妥，应龄期28天" in fallback


def test_case_grading_without_score_authority_demotes_official_grading_tone() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "authority_applied": False,
        "exact_question": {},
    }
    response = "## 采分点批改\n1. 龄期28天：命中。\n2. 含水率：判错。"

    assert should_demote_case_grading_hard_score(response, runtime_metadata=metadata)
    assert not should_demote_case_grading_hard_score(
        "## 评分口径\n提分诊断\n\n## 预计得分\n本次不硬估标准分。",
        runtime_metadata=metadata,
    )


def test_case_grading_with_exact_case_authority_keeps_score_path() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "authority_applied": True,
        "exact_question": {
            "answer_kind": "case_study",
            "covered_subquestions": [{"authoritative_answer": "应编制专项方案"}],
        },
    }

    assert case_grading_score_authority_available(metadata)
    assert not should_demote_case_grading_hard_score(
        "## 预计得分\n**4分 / 满分5分**\n",
        runtime_metadata=metadata,
    )


def test_case_grading_authority_applied_without_case_evidence_is_not_enough() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "authority_applied": True,
        "exact_question": {},
    }

    assert not case_grading_score_authority_available(metadata)
    assert should_demote_case_grading_hard_score(
        "## 预计得分\n**4分 / 满分5分**\n",
        runtime_metadata=metadata,
    )


def test_case_bundle_shape_without_score_evidence_is_not_enough() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "authority_applied": True,
        "exact_question": {
            "answer_kind": "case_bundle",
            "case_bundle": {
                "covered_subquestions": [{"display_index": "1", "stem": "分析不妥之处"}],
                "coverage_state": "full",
            },
        },
    }

    assert not case_grading_score_authority_available(metadata)
    assert should_demote_case_grading_hard_score(
        "## 预计得分\n**4分 / 满分5分**\n",
        runtime_metadata=metadata,
    )


def test_grading_key_shape_without_scoring_points_is_not_enough() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "authority_applied": True,
        "exact_question": {
            "answer_kind": "case_study",
            "grading_key": {"scoring_points": []},
            "covered_subquestions": [{"display_index": "1"}],
        },
    }

    assert not case_grading_score_authority_available(metadata)


def test_case_bundle_answer_kind_with_case_bundle_keeps_score_path() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "authority_applied": False,
        "exact_question": {
            "answer_kind": "case_bundle",
            "case_bundle": {
                "covered_subquestions": [{"authoritative_answer": "龄期应达到28天"}],
                "coverage_state": "full",
            },
        },
    }

    assert case_grading_score_authority_available(metadata)
    assert not should_demote_case_grading_hard_score(
        "## 预计得分\n**4分 / 满分5分**\n",
        runtime_metadata=metadata,
    )


def test_case_grading_key_scoring_points_keep_score_path() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "authority_applied": True,
        "exact_question": {
            "answer_kind": "case_study",
            "grading_key": {"scoring_points": ["指出专项施工方案审批问题"]},
        },
    }

    assert case_grading_score_authority_available(metadata)
    assert not should_demote_case_grading_hard_score(
        "## 预计得分\n**4分 / 满分5分**\n",
        runtime_metadata=metadata,
    )


def test_non_case_grading_hard_score_is_not_case_policy() -> None:
    metadata = {
        "question_lifecycle_scene": "mcq_grading",
        "authority_applied": False,
    }

    assert not should_demote_case_grading_hard_score(
        "## 预计得分\n**4分 / 满分5分**\n",
        runtime_metadata=metadata,
    )


def test_case_grading_without_score_authority_suppresses_streaming() -> None:
    assert AgentLoop._should_suppress_stream_for_degraded_answer(
        user_message="案例：墙体施工。我的答案：不妥。帮我批改",
        runtime_metadata={
            "question_lifecycle_scene": "case_grading",
            "authority_applied": False,
            "exact_question": {},
        },
    )
    assert not AgentLoop._should_suppress_stream_for_degraded_answer(
        user_message="案例：墙体施工。我的答案：不妥。帮我批改",
        runtime_metadata={
            "question_lifecycle_scene": "case_grading",
            "authority_applied": True,
            "exact_question": {
                "answer_kind": "case_study",
                "covered_subquestions": [{"authoritative_answer": "应编制专项方案"}],
            },
        },
    )
