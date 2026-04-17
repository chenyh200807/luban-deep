from __future__ import annotations

from deeptutor.services.question_followup import (
    build_question_followup_context_from_presentation,
    build_question_followup_context_from_result_summary,
    detect_answer_reveal_preference,
    detect_requested_question_type,
    extract_choice_result_summary_from_text,
    resolve_submission,
)


def test_detect_requested_question_type_prefers_explicit_written_case() -> None:
    question_type, is_explicit = detect_requested_question_type(
        "围绕基坑工程给我出一道案例题"
    )

    assert question_type == "written"
    assert is_explicit is True


def test_detect_answer_reveal_preference_respects_suppress_request() -> None:
    assert detect_answer_reveal_preference("先别给答案，只问我第1问") is False


def test_resolve_submission_maps_judgment_text_to_option_key() -> None:
    target, answer = resolve_submission(
        "我答：错。批改。",
        {
            "question_id": "q_1",
            "question": "判断：流水步距反映相邻专业队投入的时间间隔。",
            "question_type": "choice",
            "options": {"A": "对", "B": "错"},
            "correct_answer": "B",
        },
    )

    assert target is not None
    assert answer == "B"


def test_build_question_followup_context_from_result_summary_keeps_all_items() -> None:
    context = build_question_followup_context_from_result_summary(
        {
            "results": [
                {
                    "qa_pair": {
                        "question_id": "q_1",
                        "question_type": "written",
                        "question": "案例背景......第1问：判断是否合理。",
                        "correct_answer": "不合理",
                        "explanation": "因为工序冲突。",
                    }
                },
                {
                    "qa_pair": {
                        "question_id": "q_2",
                        "question_type": "written",
                        "question": "第2问：说明理由。",
                        "correct_answer": "略",
                        "explanation": "略",
                    }
                },
            ]
        },
        "### Question 1\n案例背景......\n### Question 2\n说明理由。",
        reveal_answers=False,
        reveal_explanations=False,
    )

    assert context is not None
    assert len(context["items"]) == 2
    assert context["reveal_answers"] is False
    assert context["correct_answer"] == ""


def test_build_question_followup_context_from_presentation_keeps_all_items() -> None:
    context = build_question_followup_context_from_presentation(
        {
            "blocks": [
                {
                    "type": "mcq",
                    "questions": [
                        {
                            "question_id": "q_1",
                            "stem": "防火门构造的基本要求有（ ）。",
                            "question_type": "multi_choice",
                            "options": [
                                {"key": "A", "text": "甲级防火门耐火极限为 1.5h"},
                                {"key": "B", "text": "向内开启"},
                            ],
                            "followup_context": {
                                "question_id": "q_1",
                                "question": "防火门构造的基本要求有（ ）。",
                                "question_type": "choice",
                                "options": {"A": "甲级防火门耐火极限为 1.5h", "B": "向内开启"},
                                "correct_answer": "A",
                                "explanation": "A 正确。",
                            },
                        },
                        {
                            "question_id": "q_2",
                            "stem": "倒置式屋面保温层应设置在（ ）。",
                            "question_type": "single_choice",
                            "options": [
                                {"key": "A", "text": "找平层下"},
                                {"key": "B", "text": "防水层上"},
                            ],
                            "followup_context": {
                                "question_id": "q_2",
                                "question": "倒置式屋面保温层应设置在（ ）。",
                                "question_type": "choice",
                                "options": {"A": "找平层下", "B": "防水层上"},
                                "correct_answer": "B",
                                "explanation": "B 正确。",
                            },
                        },
                    ],
                }
            ]
        },
        "### Question 1\n...\n### Question 2\n...",
        reveal_answers=False,
        reveal_explanations=False,
    )

    assert context is not None
    assert len(context["items"]) == 2
    assert context["question"].startswith("### Question 1")
    assert context["correct_answer"] == ""


def test_extract_choice_result_summary_from_text_supports_chinese_numbered_titles() -> None:
    result_summary = extract_choice_result_summary_from_text(
        "\n".join(
            [
                "现在给你三道题。",
                "",
                "## 题目一：建筑构造",
                "防火门构造的基本要求有（ ）。",
                "A. 甲级防火门耐火极限为 1.5h",
                "B. 向内开启",
                "C. 关闭后应能从内外两侧手动开启",
                "D. 具有自行关闭功能",
                "E. 开启后，门扇不应跨越变形缝",
                "",
                "## 题目二：屋面工程",
                "倒置式屋面保温层应设置在（ ）。",
                "A. 找平层下",
                "B. 防水层上",
                "C. 结构层上",
                "D. 保护层下",
            ]
        )
    )

    assert result_summary is not None
    assert len(result_summary["results"]) == 2
    first = result_summary["results"][0]["qa_pair"]
    assert first["question"] == "防火门构造的基本要求有（ ）。"
    assert first["multi_select"] is True
    assert first["options"]["E"] == "开启后，门扇不应跨越变形缝"


def test_extract_choice_result_summary_from_text_keeps_explanation_outside_bare_question_marker() -> None:
    result_summary = extract_choice_result_summary_from_text(
        "\n".join(
            [
                "我先给你讲解防水工程的核心知识点，然后出一道选择题。",
                "",
                "## 防水工程核心知识讲解",
                "",
                "### 一、屋面防水",
                "1. 防水层应按等级和设防要求设置。",
                "",
                "## 现在给你出一道选择题：",
                "",
                "**题目：** 关于室内防水工程，下列做法正确的是：",
                "A. 卫生间墙面防水层高度做到1.2m即可",
                "B. 淋浴区墙面防水层高度应不小于1.8m",
                "C. 厨房地面不需要做防水层",
                "D. 独立水容器防水不属于室内防水范畴",
            ]
        )
    )

    assert result_summary is not None
    assert len(result_summary["results"]) == 1
    first = result_summary["results"][0]["qa_pair"]
    assert first["question"] == "关于室内防水工程，下列做法正确的是："
    assert first["options"]["B"] == "淋浴区墙面防水层高度应不小于1.8m"
