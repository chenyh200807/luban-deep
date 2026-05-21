"""
plan §Phase 4 Step 4.2 / Batch D.2 — explanation 7 段 schema 校验 + 模板兜底。
"""

from __future__ import annotations

import pytest

from deeptutor.agents.question.agents.submission_grader_schema import (
    CHOICE_EXTRA_KEYS,
    REQUIRED_SECTION_KEYS,
    ExplanationSections,
    apply_fallback_templates,
    parse_explanation_sections,
    validate_explanation_sections,
)


_FULL_EXPLANATION = """\
### 阅卷结论
本题答错。

### 正确答案
B 选项。

### 为什么错
你忽略了"专家论证程序"这一前置条件。

### 知识点
建设工程安全管理 / 危大工程专项方案审批程序。

### 易错点
把专项方案审批程序与一般工程审批混淆。

### 记忆口诀
"先论后审，谁论谁审"。

### 下一步
继续做 3 道同考点变式题，然后回看错题。
"""


def test_parse_explanation_extracts_seven_required_sections() -> None:
    sections = parse_explanation_sections(_FULL_EXPLANATION, question_type="choice", is_correct=False)
    missing = sections.missing_required()
    # 选择题答错时还要求 option_analysis；上面没给，所以会缺一段
    assert "option_analysis" in missing
    # 但 7 个 required 段都应该被识别
    for key in REQUIRED_SECTION_KEYS:
        assert key in sections.sections, f"{key} not extracted"


def test_validate_explanation_returns_missing_keys_when_sections_absent() -> None:
    parsed, missing = validate_explanation_sections(
        "本题答错。仅此一句，无章节。",
        question_type="choice",
        is_correct=False,
    )
    # 所有 7 段 + option_analysis 都缺
    expected = set(REQUIRED_SECTION_KEYS) | set(CHOICE_EXTRA_KEYS)
    assert set(missing) >= expected - {"verdict"}  # 至少 6 缺，verdict 可能 fuzzy match
    assert isinstance(parsed, ExplanationSections)


def test_apply_fallback_templates_fills_missing_sections() -> None:
    parsed = ExplanationSections(sections={"verdict": "本题答错"}, question_type="choice", is_correct=False)
    repaired = apply_fallback_templates(parsed)
    for key in REQUIRED_SECTION_KEYS:
        assert str(repaired.sections.get(key, "")).strip(), f"{key} not filled by template"
    # option_analysis 也应该被填
    assert "option_analysis" in repaired.sections


def test_case_question_required_sections_include_scoring_points() -> None:
    sections = parse_explanation_sections(
        "### 阅卷结论\n本题部分得分。\n### 采分点命中\nP1。\n",
        question_type="case",
        is_correct=False,
    )
    missing = sections.missing_required()
    # 案例题额外要求 scoring_points_missed / rewritten_answer 等
    assert "scoring_points_missed" in missing
    assert "rewritten_answer" in missing


def test_apply_fallback_does_not_overwrite_existing_sections() -> None:
    parsed = ExplanationSections(
        sections={
            "verdict": "本题答对",
            "correct_answer": "标准答案是 B。",
            "why_wrong": "",
        },
        question_type="choice",
        is_correct=True,
    )
    repaired = apply_fallback_templates(parsed)
    assert repaired.sections["verdict"] == "本题答对"
    assert repaired.sections["correct_answer"] == "标准答案是 B。"
