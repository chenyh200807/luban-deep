"""
plan §Phase 5 / Batch E.2 — progressive disclosure + difficulty pacing.
"""

from __future__ import annotations

import pytest

from deeptutor.agents.question.agents.submission_grader_schema import ExplanationSections
from deeptutor.services.construction_grading.progressive_disclosure import (
    ACTION_SLUGS,
    ActionChip,
    build_progressive_disclosure,
    classify_difficulty_pacing,
)


def test_progressive_disclosure_includes_required_top_level_keys() -> None:
    parsed = ExplanationSections(
        sections={
            "verdict": "本题答错",
            "correct_answer": "B",
            "why_wrong": "忽略了专项方案审批前置条件",
            "knowledge_point": "危大工程审批程序",
            "common_pitfall": "把专项方案与一般工程混淆",
            "mnemonic": "先论后审",
            "next_practice": "继续做 3 道同考点题",
        },
        question_type="choice",
        is_correct=False,
    )
    payload = build_progressive_disclosure(
        explanation=parsed,
        is_correct=False,
        grading_source="grading_key",
        pacing="hold",
    ).to_dict()
    for key in ("verdict", "one_line_diagnosis", "primary_next_action", "sections"):
        assert key in payload
    assert payload["grading_source"] == "grading_key"
    assert payload["primary_next_action"]["slug"] in ACTION_SLUGS


def test_progressive_disclosure_truncates_verdict_to_120_chars() -> None:
    long_verdict = "本题答错。" * 100  # 远超 120 字
    parsed = ExplanationSections(
        sections={"verdict": long_verdict},
        question_type="choice",
        is_correct=False,
    )
    payload = build_progressive_disclosure(explanation=parsed, is_correct=False).to_dict()
    assert len(payload["verdict"]) <= 120


def test_progressive_disclosure_caps_secondary_actions_to_two() -> None:
    parsed = ExplanationSections(sections={}, question_type="choice", is_correct=False)
    payload = build_progressive_disclosure(
        explanation=parsed, is_correct=False, pacing="suggest_consolidation"
    ).to_dict()
    assert len(payload["secondary_actions"]) <= 2
    # 主行动是讲透
    assert payload["primary_next_action"]["slug"] == "explain_thoroughly"


def test_classify_pacing_suggests_consolidation_after_two_consecutive_wrong() -> None:
    # 最近到最早：False, False, True, True
    pacing = classify_difficulty_pacing([False, False, True, True])
    assert pacing == "suggest_consolidation"


def test_classify_pacing_suggests_step_up_after_three_consecutive_right() -> None:
    pacing = classify_difficulty_pacing([True, True, True, False])
    assert pacing == "suggest_step_up"


def test_classify_pacing_holds_for_mixed_outcomes() -> None:
    assert classify_difficulty_pacing([True, False, True]) == "hold"
    assert classify_difficulty_pacing([]) == "hold"
    assert classify_difficulty_pacing([True, True]) == "hold"  # 不足 3


def test_show_mnemonic_chip_only_when_mnemonic_section_present() -> None:
    """Battle2 S2-T1：mnemonic 是条件段——无口诀不挂"看记忆口诀" chip（防点开空口诀）。"""
    without = ExplanationSections(
        sections={"verdict": "本题答错", "why_wrong": "概念混淆"},
        question_type="choice",
        is_correct=False,
    )
    payload = build_progressive_disclosure(
        explanation=without, is_correct=False, pacing="suggest_consolidation"
    ).to_dict()
    slugs = [chip["slug"] for chip in payload["secondary_actions"]]
    assert "show_mnemonic" not in slugs

    with_mnemonic = ExplanationSections(
        sections={"verdict": "本题答错", "mnemonic": "先论后审，谁论谁审"},
        question_type="choice",
        is_correct=False,
    )
    payload = build_progressive_disclosure(
        explanation=with_mnemonic, is_correct=False, pacing="suggest_consolidation"
    ).to_dict()
    slugs = [chip["slug"] for chip in payload["secondary_actions"]]
    assert "show_mnemonic" in slugs


def test_step_up_pacing_mnemonic_chip_conditional() -> None:
    empty = ExplanationSections(sections={}, question_type="choice", is_correct=True)
    payload = build_progressive_disclosure(
        explanation=empty, is_correct=True, pacing="suggest_step_up"
    ).to_dict()
    assert payload["primary_next_action"]["slug"] == "practice_more_3"
    assert [chip["slug"] for chip in payload["secondary_actions"]] == []


def test_action_chips_label_uses_chinese() -> None:
    parsed = ExplanationSections(sections={}, question_type="choice", is_correct=False)
    payload = build_progressive_disclosure(
        explanation=parsed, is_correct=False, pacing="suggest_consolidation"
    ).to_dict()
    primary = payload["primary_next_action"]
    assert primary["label"] in {"再练3题", "讲透这个点", "看记忆口诀"}
