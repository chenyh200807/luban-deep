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
    """Battle2 S2-T1 权威常量：4 必备段 + OPTIONAL 条件段，单一权威不漂移。
    采分点 2026-07-21 恢复为第 4 个 OPTIONAL 条件段（非必备，成本权衡见 schema 注释）。"""
    assert REQUIRED_SECTION_KEYS == ("verdict", "correct_answer", "why_wrong", "next_practice")
    assert OPTIONAL_SECTION_KEYS == ("knowledge_point", "common_pitfall", "mnemonic", "scoring_points")
    assert not set(REQUIRED_SECTION_KEYS) & set(OPTIONAL_SECTION_KEYS)


def test_parse_explanation_extracts_required_and_optional_sections() -> None:
    sections = parse_explanation_sections(_FULL_EXPLANATION, question_type="choice", is_correct=False)
    missing = sections.missing_required()
    # 选择题答错时还要求 option_analysis；上面没给，所以会缺一段
    assert "option_analysis" in missing
    # required 段全部被识别；旧 7 段输出中的条件段也照常解析透传
    for key in REQUIRED_SECTION_KEYS:
        assert key in sections.sections, f"{key} not extracted"
    # 旧 7 段语料含 knowledge_point/common_pitfall/mnemonic 三个条件段；scoring_points
    # 是 2026-07-21 恢复的新 OPTIONAL 段，_FULL_EXPLANATION 这版没有,故此处只查旧三段。
    for key in ("knowledge_point", "common_pitfall", "mnemonic"):
        assert key in sections.sections, f"optional {key} should still be parsed"


def test_legacy_seven_section_output_has_no_missing_required() -> None:
    """完整选择题错题输出（含 逐项解析 + 采分点）在新 schema 下 missing==[]。"""
    full = (
        _FULL_EXPLANATION
        + "\n### 逐项解析\nA错 B对 C错 D错。\n"
        + "\n### 采分点\n选 B 得分：顺序器保证按顺序关闭；错选 A 丢在把顺序关闭当同时关闭。\n"
    )
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
    # 采分点是 OPTIONAL，缺它不进 missing；4 必备 + option_analysis 齐全故 missing==[]。
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


# ── 采分点段恢复（2026-07-21，owner 拍板；Battle2 c5bdffe58 un-fold）──────────────


def test_scoring_points_restored_as_optional_not_choice_required() -> None:
    """采分点恢复为 OPTIONAL 段而非选择题必备段：CHOICE_EXTRA 仍只有逐项解析(缺则 repair)，
    采分点在 OPTIONAL(缺不 repair)。这是"可见走 prompt markdown、不反转 Battle2 repair 成本
    保证"的单一权威落点。case 的 scoring_points_hit/missed 与之正交、不受影响。"""
    assert CHOICE_EXTRA_KEYS == ("option_analysis",)
    assert "scoring_points" in OPTIONAL_SECTION_KEYS
    assert "scoring_points" not in CHOICE_EXTRA_KEYS


def test_scoring_points_alias_parses_as_independent_section_not_folded() -> None:
    """`### 采分点` 解析为独立 scoring_points 段，不再折叠进 correct_answer。"""
    text = (
        "### 正确答案\nB 选项（按顺序关闭）。\n"
        "### 采分点\n选 B 得分：顺序器保证按顺序关闭；错选 A 丢在把顺序当同时。\n"
    )
    parsed = parse_explanation_sections(text, question_type="choice", is_correct=False)
    assert "scoring_points" in parsed.sections
    assert "顺序器" in parsed.sections["scoring_points"]
    # 未被折叠：correct_answer 只含正确答案段正文，不含采分点正文。
    assert "顺序器" not in parsed.sections.get("correct_answer", "")
    assert parsed.sections["correct_answer"].strip() == "B 选项（按顺序关闭）。"


def test_choice_wrong_does_not_require_scoring_points_but_parses_it() -> None:
    """采分点列 OPTIONAL 非必备（成本权衡）：选择题错题缺采分点不进 missing_required、
    不触发第二次全量 LLM（保住 Battle2「compact 跳过 repair」成本保证）。可见采分点靠
    prompt 驱动的 markdown 直渲，不靠 repair 追讨。若 eval 证实漏采分点率高再提升为必备。"""
    text = (
        "### 阅卷结论\n本题答错。\n### 正确答案\nB。\n### 为什么错\n概念混淆。\n"
        "### 下一步\n抄 1 遍。\n### 逐项解析\nA错 B对。\n"
    )
    _, missing = validate_explanation_sections(text, question_type="choice", is_correct=False)
    assert "scoring_points" not in missing
    # 但采分点若给了，un-fold 生效：解析为独立 scoring_points 段。
    with_sp = text + "### 采分点\n选 B 得分：顺序器保证按顺序关闭。\n"
    parsed_sp, _ = validate_explanation_sections(with_sp, question_type="choice", is_correct=False)
    assert "顺序器" in parsed_sp.sections.get("scoring_points", "")


def test_correct_choice_does_not_require_scoring_points() -> None:
    """选择题答对时不追讨采分点（与 option_analysis 一致，避免无谓 repair）。"""
    text = (
        "### 阅卷结论\n本题答对。\n### 正确答案\nB。\n### 为什么错\n判断依据正确。\n"
        "### 下一步\n继续。\n"
    )
    _, missing = validate_explanation_sections(text, question_type="choice", is_correct=True)
    assert "scoring_points" not in missing
    assert "option_analysis" not in missing


def test_case_scoring_points_hit_still_resolves_despite_generic_alias() -> None:
    """case 的 `### 采分点命中` 仍解析为 scoring_points_hit（最长别名优先，不被通用采分点截胡）。"""
    text = "### 采分点命中\nP1、P2 命中。\n### 漏点\nP3 漏。\n"
    parsed = parse_explanation_sections(text, question_type="case", is_correct=False)
    assert parsed.sections.get("scoring_points_hit", "").startswith("P1")
    assert "scoring_points_missed" in parsed.sections
    # 通用 choice 采分点 key 不应出现在 case 解析里。
    assert "scoring_points" not in parsed.sections


def test_case_path_missing_required_unaffected_by_choice_scoring_points() -> None:
    """case 必备段仍是 hit/missed/rewritten，不含 choice 的 scoring_points。"""
    parsed = ExplanationSections(sections={}, question_type="case", is_correct=False)
    missing = parsed.missing_required()
    assert {"scoring_points_hit", "scoring_points_missed", "rewritten_answer"} <= set(missing)
    assert "scoring_points" not in missing
    assert "option_analysis" not in missing


def test_scoring_points_fallback_template_is_honest_when_explicitly_repaired() -> None:
    """采分点列 OPTIONAL，missing_required 不含它，正常不走兜底；但若显式 missing 追讨
    (或未来提升为必备)，兜底文案必须诚实：默认可引服务端 authority，开放世界不得冒称题库
    官方结论（守 §硬约束 40）。"""
    choice = ExplanationSections(sections={}, question_type="choice", is_correct=False)
    # OPTIONAL：不显式传 missing 时，采分点不被兜底（不在 missing_required）。
    assert "scoring_points" not in apply_fallback_templates(choice).sections
    # 显式追讨时兜底文案存在且诚实。
    default_sp = apply_fallback_templates(choice, missing=["scoring_points"]).sections["scoring_points"]
    assert default_sp.strip()
    ow_sp = apply_fallback_templates(
        choice, missing=["scoring_points"], authority_present=False
    ).sections["scoring_points"]
    assert ow_sp.strip()
    assert "grading_result" not in ow_sp and "grading_key" not in ow_sp
    # 开放世界模板必须显式否认题库官方（"非题库官方结论"这类免责话术），不得正面声称权威。
    assert "非题库官方" in ow_sp
