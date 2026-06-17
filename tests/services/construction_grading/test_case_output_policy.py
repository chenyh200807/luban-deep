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
    assert "未命中评分真相层，本轮不硬估分" in fallback
    assert "本次不硬估标准分" in fallback
    assert "预计得分\n**4分" not in fallback
    assert "你当前作答：不妥，应龄期28天" in fallback


def test_case_grading_without_v1_authority_always_returns_diagnostic() -> None:
    metadata = {
        "question_lifecycle_scene": "case_grading",
        "v1_case_graded": False,
        "score_authority": "v1_provider_unavailable",
    }

    fallback = AgentLoop._case_grading_no_authority_score_fallback(
        "你的作答方向基本正确，我帮你按小问拆解。",
        runtime_metadata=metadata,
        user_message="【背景资料】某工程。\n【问题】指出不妥。\n作答：不妥。",
    )

    assert "未命中评分真相层，本轮不硬估分" in fallback
    assert metadata["v1_case_graded"] is False


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


def test_unclassified_out_of_bank_case_score_demotes_without_authority() -> None:
    # P1-A safety net: an out-of-bank case grading request the lifecycle did NOT
    # tag as case_grading (scene empty) must not be allowed to assert an official
    # case score with no authority of any kind (RE-22 / RE-23).
    metadata = {
        "question_lifecycle_scene": None,
        "authority_applied": False,
        "exact_question": {},
    }
    assert should_demote_case_grading_hard_score(
        "这道题属于案例题阅卷场景\n\n## 评定结果\n你的答案：不得分。",
        runtime_metadata=metadata,
    )
    assert should_demote_case_grading_hard_score(
        "你的答案 0 个采分点，0 分——判断方向反了。",
        runtime_metadata=metadata,
    )


def test_unclassified_bolded_bare_score_verdict_demotes_without_authority() -> None:
    # P1-A gap (R3-16): a forced bare bolded score verdict ("**0分。**") on an
    # out-of-bank case turn with no authority must still be demoted.
    metadata = {
        "question_lifecycle_scene": None,
        "authority_applied": False,
        "exact_question": {},
    }
    assert should_demote_case_grading_hard_score(
        "## 结论\n**0分。**\n## 判断依据\n你写的“妥当”遗漏了关键限定条件。",
        runtime_metadata=metadata,
    )


def test_unclassified_score_with_active_question_authority_not_demoted() -> None:
    # A turn with real active-question authority (MCQ follow-up grading) must not
    # be demoted even when the lifecycle scene is unset and a score is shown.
    metadata = {
        "question_lifecycle_scene": None,
        "active_object": {"object_type": "single_question", "object_id": "historical:abc"},
    }
    assert not should_demote_case_grading_hard_score(
        "## 评定结果\n你的答案：不得分。",
        runtime_metadata=metadata,
    )


def test_unclassified_teaching_with_score_point_label_not_demoted() -> None:
    # Teaching that merely uses a 采分点 label with no score verdict on an
    # unclassified turn must not be demoted into the case diagnostic (RE-32).
    metadata = {
        "question_lifecycle_scene": None,
        "authority_applied": False,
        "exact_question": {},
    }
    assert not should_demote_case_grading_hard_score(
        "女儿墙顶点就是最高点的常见构成。\n\n## 采分点\n题干关键词是“保护规划区内”。",
        runtime_metadata=metadata,
    )


def test_unclassified_knowledge_answer_not_demoted() -> None:
    # A plain knowledge answer on an unclassified turn must not be demoted.
    metadata = {
        "question_lifecycle_scene": None,
        "authority_applied": False,
        "exact_question": {},
    }
    assert not should_demote_case_grading_hard_score(
        "没问题。按月度完成量的 85% 支付进度款，不低于 80% 的下限即可。",
        runtime_metadata=metadata,
    )


def test_unclassified_unit_price_and_rubric_teaching_not_demoted() -> None:
    # The score-verdict regex must not fire on unit prices ("45分/平米") or rubric
    # teaching ("满分100分") on an unclassified no-authority turn.
    metadata = {
        "question_lifecycle_scene": None,
        "authority_applied": False,
        "exact_question": {},
    }
    assert not should_demote_case_grading_hard_score(
        "脚手架搭设费用约为 45 分/平米，超高按 5分/平米 计取。",
        runtime_metadata=metadata,
    )
    assert not should_demote_case_grading_hard_score(
        "质量评定满分 100 分，优良率不低于 80% 即评优良。",
        runtime_metadata=metadata,
    )


def test_unclassified_score_fraction_verdict_still_demoted() -> None:
    # A genuine score fraction verdict ("0分/5分") on a no-authority turn demotes.
    metadata = {
        "question_lifecycle_scene": None,
        "authority_applied": False,
        "exact_question": {},
    }
    assert should_demote_case_grading_hard_score(
        "## 评定结果\n你的答案：0分/5分。",
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
