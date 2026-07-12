"""
Battle2 S2-T4 — deterministic 判分反馈去通用套话（零 LLM 路径）。

治的病：deep_question._objective_explanation 旧版硬编码"采分点 3 条 + 易错点 3 条"
通用检查清单（owner 亲见的"套话"真源），对每道题无差别输出最大宽度。

新契约：
  * MCQ deterministic 输出中"采分点"段整段删除（MCQ 无采分点概念）。
  * "易错点"降级为题库行特异性投影（trap_type / pitfalls / common_mistakes），
    无特异性内容则整段省略；禁通用检查清单。
  * "记忆口诀"（正确项关键词投影，已是特异性）保留。
  * 判定行 / 答案字母对齐 / 逐项解析行为回归不变。
"""

from __future__ import annotations

from deeptutor.capabilities.deep_question import (
    _objective_explanation,
    _objective_specific_pitfalls,
    _render_deterministic_grading_feedback,
)


# 旧版六条通用套话原文（deep_question.py 旧 1456-1463 行）。任何一条出现即回归。
_LEGACY_BOILERPLATE_SENTENCES = (
    "抓住题干限定词，先判断它问的是对象、顺序、数值、范围还是做法是否妥当",
    "对照正确选项中的规范关键词，不用相近概念替代标准表述",
    "排除与题干对象不一致、顺序颠倒、数值范围错误或绝对化的干扰项",
    "看到熟悉词就选，忽略题干真正限定的工程部位或构造要求",
    "把“可以/应当/不得”“同时/顺序”“不小于/不大于”等关键词看反",
    "多选或判断类题容易漏选一个正确约束，或把相关但不属于本题问法的选项带入",
)

# 文案铁律：禁"看穿/识破"类审视语气（记忆 luban-copy-tone-no-see-through-words）。
_FORBIDDEN_TONE_WORDS = ("看穿", "识破", "揭穿", "露馅")


def _wrong_answer_context(**extra: object) -> dict[str, object]:
    context: dict[str, object] = {
        "question_id": "q_det_1",
        "question_type": "choice",
        "question": "关于双扇防火门关闭方式的说法，正确的是？",
        "options": {
            "A": "同时关闭",
            "B": "按顺序关闭",
            "C": "自动关闭",
            "D": "手动关闭",
        },
        "user_answer": "C",
        "correct_answer": "B",
        "is_correct": False,
    }
    context.update(extra)
    return context


def test_mcq_deterministic_output_has_no_scoring_point_section() -> None:
    output = _objective_explanation(_wrong_answer_context())
    assert "采分点" not in output


def test_no_trap_type_omits_pitfall_section_entirely() -> None:
    output = _objective_explanation(_wrong_answer_context())
    assert "易错点" not in output
    for sentence in _LEGACY_BOILERPLATE_SENTENCES:
        assert sentence not in output, f"legacy boilerplate leaked: {sentence}"


def test_trap_type_renders_specific_pitfall_without_boilerplate() -> None:
    output = _objective_explanation(
        _wrong_answer_context(trap_type="顺序器功能与自动关闭混淆")
    )
    assert "易错点" in output
    assert "顺序器功能与自动关闭混淆" in output
    for sentence in _LEGACY_BOILERPLATE_SENTENCES:
        assert sentence not in output, f"legacy boilerplate leaked: {sentence}"


def test_pitfalls_list_and_metadata_mirror_are_projected_capped_at_two() -> None:
    pitfalls = _objective_specific_pitfalls(
        {
            "pitfalls": ["陷阱一", "陷阱二", "陷阱三"],
            "metadata": {"trap_type": "metadata 陷阱"},
        }
    )
    assert pitfalls == ["陷阱一", "陷阱二"]

    metadata_only = _objective_specific_pitfalls({"metadata": {"pitfalls": ["仅 metadata 陷阱"]}})
    assert metadata_only == ["仅 metadata 陷阱"]

    assert _objective_specific_pitfalls({}) == []
    assert _objective_specific_pitfalls({"trap_type": "", "pitfalls": []}) == []


def test_pitfalls_projected_from_grading_result_evidence_refs() -> None:
    """题库行经 normalize_question_followup_context 白名单后，trap_type 只存活在
    construction_grading_result.evidence_refs（source=questions_bank）——投影必须认这条通道。"""
    pitfalls = _objective_specific_pitfalls(
        {
            "construction_grading_result": {
                "is_correct": False,
                "evidence_refs": [
                    {"source": "questions_bank", "field": "correct_answer", "value": "B"},
                    {"source": "questions_bank", "field": "trap_type", "value": "顺序器功能与自动关闭混淆"},
                ],
            }
        }
    )
    assert pitfalls == ["顺序器功能与自动关闭混淆"]


def test_letter_alignment_and_option_analysis_regression() -> None:
    output = _objective_explanation(_wrong_answer_context())
    assert "正确选项是 B（按顺序关闭）" in output
    assert "你选择的是 C（自动关闭）" in output
    assert "逐项解析" in output
    assert "C. 自动关闭：误选项" in output
    assert "B. 按顺序关闭：正确项" in output
    assert "你为什么会错" in output
    assert "记忆口诀" in output


def test_correct_answer_row_keeps_short_shape_without_checklists() -> None:
    output = _objective_explanation(
        _wrong_answer_context(user_answer="B", is_correct=True)
    )
    assert "采分点" not in output
    assert "易错点" not in output
    assert "记忆口诀" in output
    for sentence in _LEGACY_BOILERPLATE_SENTENCES:
        assert sentence not in output


def test_render_deterministic_feedback_verdict_and_tone() -> None:
    # trap_type 顶层键会被 normalize_question_followup_context 白名单剥掉，
    # 真实通道 = construction_grading_result.evidence_refs（题库行判分证据）。
    feedback = _render_deterministic_grading_feedback(
        {
            "items": [
                _wrong_answer_context(
                    construction_grading_result={
                        "is_correct": False,
                        "evidence_refs": [
                            {
                                "source": "questions_bank",
                                "field": "trap_type",
                                "value": "顺序器功能与自动关闭混淆",
                            }
                        ],
                    }
                )
            ]
        }
    )
    assert "阅卷结论" in feedback
    assert "**结果：** 错误" in feedback
    assert "**正确答案：** B（按顺序关闭）" in feedback
    assert "顺序器功能与自动关闭混淆" in feedback
    for word in _FORBIDDEN_TONE_WORDS:
        assert word not in feedback, f"forbidden tone word: {word}"


def test_render_deterministic_feedback_batch_keeps_per_item_answers() -> None:
    items = [
        _wrong_answer_context(),
        _wrong_answer_context(
            question_id="q_det_2", user_answer="B", is_correct=True
        ),
    ]
    feedback = _render_deterministic_grading_feedback({"items": items})
    assert "**得分：** 1/2题" in feedback
    assert "### 第1题：错误" in feedback
    assert "### 第2题：正确" in feedback
    assert "采分点" not in feedback
