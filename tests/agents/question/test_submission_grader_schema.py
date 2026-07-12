"""
plan §Phase 4 Step 4.2 / Batch D.2 — explanation schema 校验 + 模板兜底。

Battle2 S2-T1（2026-07-12）：REQUIRED 7 段收紧为 4 必备段 +
OPTIONAL_SECTION_KEYS 3 条件段（缺失不追讨 repair、不模板兜底）。
"""

from __future__ import annotations

import pytest

from deeptutor.agents.question.agents.submission_grader_schema import (
    CHOICE_EXTRA_KEYS,
    OPTIONAL_SECTION_KEYS,
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


def test_required_section_keys_are_the_compact_four() -> None:
    """Battle2 S2-T1 权威常量：4 必备段 + 3 条件段，单一权威不漂移。"""
    assert REQUIRED_SECTION_KEYS == ("verdict", "correct_answer", "why_wrong", "next_practice")
    assert OPTIONAL_SECTION_KEYS == ("knowledge_point", "common_pitfall", "mnemonic")
    assert not set(REQUIRED_SECTION_KEYS) & set(OPTIONAL_SECTION_KEYS)


def test_parse_explanation_extracts_required_and_optional_sections() -> None:
    sections = parse_explanation_sections(_FULL_EXPLANATION, question_type="choice", is_correct=False)
    missing = sections.missing_required()
    # 选择题答错时还要求 option_analysis；上面没给，所以会缺一段
    assert "option_analysis" in missing
    # required 段全部被识别；旧 7 段输出中的条件段也照常解析透传
    for key in REQUIRED_SECTION_KEYS:
        assert key in sections.sections, f"{key} not extracted"
    for key in OPTIONAL_SECTION_KEYS:
        assert key in sections.sections, f"optional {key} should still be parsed"


def test_legacy_seven_section_output_has_no_missing_required() -> None:
    """单调放松：flag off 旧 prompt 的 7 段输出在新 schema 下 missing==[]（不产生新 repair）。"""
    full = _FULL_EXPLANATION + "\n### 逐项解析\nA错 B对 C错 D错。\n"
    parsed, missing = validate_explanation_sections(full, question_type="choice", is_correct=False)
    assert missing == []
    assert isinstance(parsed, ExplanationSections)


def test_compact_shape_without_optional_sections_has_no_missing_required() -> None:
    """新 compact 形状（4 必备 + 逐项，无易错点/口诀/知识点）不触发 repair。"""
    compact = """\
### 阅卷结论
本题答错，你答了 A、正确答案是 B。

### 正确答案
B（按顺序关闭）。依据防火门规范要求，考点：防火门关闭方式。

### 为什么错
把顺序器保证的顺序关闭理解成了自动关闭，属概念混淆。

### 下一步
现在把"双扇防火门按顺序关闭"抄 1 遍。

### 逐项解析
你选的 A（同时关闭）错：双扇门须分先后；B 正确：顺序器保证按顺序关闭；C/D 一句话带过：均不符合规范表述。
"""
    parsed, missing = validate_explanation_sections(compact, question_type="choice", is_correct=False)
    assert missing == []
    for key in OPTIONAL_SECTION_KEYS:
        assert key not in parsed.sections


def test_validate_explanation_returns_missing_keys_when_sections_absent() -> None:
    parsed, missing = validate_explanation_sections(
        "本题答错。仅此一句，无章节。",
        question_type="choice",
        is_correct=False,
    )
    # 所有 4 必备段 + option_analysis 都缺；条件段缺失不进 missing
    expected = set(REQUIRED_SECTION_KEYS) | set(CHOICE_EXTRA_KEYS)
    assert set(missing) >= expected - {"verdict"}  # verdict 可能 fuzzy match
    assert not set(missing) & set(OPTIONAL_SECTION_KEYS)
    assert isinstance(parsed, ExplanationSections)


def test_apply_fallback_templates_fills_missing_sections() -> None:
    parsed = ExplanationSections(sections={"verdict": "本题答错"}, question_type="choice", is_correct=False)
    repaired = apply_fallback_templates(parsed)
    for key in REQUIRED_SECTION_KEYS:
        assert str(repaired.sections.get(key, "")).strip(), f"{key} not filled by template"
    # option_analysis 也应该被填
    assert "option_analysis" in repaired.sections
    # 条件段不追讨：模板不为 optional keys 兜底（缺失=合法省略）
    for key in OPTIONAL_SECTION_KEYS:
        assert key not in repaired.sections


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


def test_apply_fallback_templates_open_world_avoids_server_authority_claims() -> None:
    """开放世界判分（无题库 authority）时，fallback 模板不得声称服务端 grading_result/grading_key。

    根因修复 2026-06-11：MCQ 缺标准答案降级开放世界判分后，若 LLM 漏段触发模板兜底，
    旧模板的"本题判定见服务端 grading_result"/"正确答案以服务端 grading_key.correct_answer
    为准"会把无 authority 的开放裁决洗白成题库官方结论（Codex 审查 P1）。
    """
    parsed = ExplanationSections(sections={}, question_type="choice", is_correct=None)
    repaired = apply_fallback_templates(parsed, authority_present=False)
    blob = "\n".join(repaired.sections.values())
    assert "grading_result" not in blob
    assert "grading_key" not in blob
    # 仍要把缺段填满，保证用户不见空段。
    for key in REQUIRED_SECTION_KEYS:
        assert str(repaired.sections.get(key, "")).strip(), f"{key} not filled by open-world template"


def test_apply_fallback_templates_default_preserves_authoritative_wording() -> None:
    """默认（authority_present=True）保持既有服务端 authority 措辞，不回归。"""
    parsed = ExplanationSections(sections={}, question_type="choice", is_correct=False)
    repaired = apply_fallback_templates(parsed)
    assert "grading_result" in "\n".join(repaired.sections.values())
