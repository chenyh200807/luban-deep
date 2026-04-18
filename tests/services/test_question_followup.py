from __future__ import annotations

from deeptutor.services.question_followup import (
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_presentation,
    build_question_followup_context_from_result_summary,
    detect_answer_reveal_preference,
    detect_requested_question_type,
    extract_choice_result_summary_from_text,
    looks_like_question_followup,
    resolve_submission,
    resolve_submission_attempt,
)


def test_detect_requested_question_type_prefers_explicit_written_case() -> None:
    question_type, is_explicit = detect_requested_question_type(
        "围绕基坑工程给我出一道案例题"
    )

    assert question_type == "written"
    assert is_explicit is True


def test_detect_answer_reveal_preference_respects_suppress_request() -> None:
    assert detect_answer_reveal_preference("先别给答案，只问我第1问") is False
    assert detect_answer_reveal_preference("先不要直接给答案，先给作答要求") is False


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


def test_resolve_submission_attempt_supports_numbered_batch_submission() -> None:
    question_set = {
        "question_id": "quiz_1",
        "question": "第1题...\n第2题...\n第3题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "题1",
                "question_type": "choice",
                "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                "correct_answer": "C",
            },
            {
                "question_id": "q_2",
                "question": "题2",
                "question_type": "choice",
                "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_3",
                "question": "题3",
                "question_type": "choice",
                "options": {"A": "A3", "B": "B3", "C": "C3", "D": "D3"},
                "correct_answer": "B",
            },
        ],
    }

    target, submission = resolve_submission_attempt(
        "第1题：C；第2题：A；第3题：B",
        question_set,
    )

    assert target is not None
    assert submission is not None
    assert submission["kind"] == "batch"
    assert [item["question_id"] for item in submission["answers"]] == ["q_1", "q_2", "q_3"]
    assert [item["user_answer"] for item in submission["answers"]] == ["C", "A", "B"]


def test_resolve_submission_attempt_supports_positional_batch_submission_variants() -> None:
    question_set = {
        "question_id": "quiz_2",
        "question": "第1题...\n第2题...\n第3题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "题1",
                "question_type": "choice",
                "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                "correct_answer": "B",
            },
            {
                "question_id": "q_2",
                "question": "题2",
                "question_type": "choice",
                "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                "correct_answer": "D",
            },
            {
                "question_id": "q_3",
                "question": "题3",
                "question_type": "choice",
                "options": {"A": "A3", "B": "B3", "C": "C3", "D": "D3"},
                "correct_answer": "A",
            },
        ],
    }

    for message in ("B D A", "B，D，A", "1.B 2.D 3.A", "1) B\n2) D\n3) A"):
        target, submission = resolve_submission_attempt(message, question_set)
        assert target is not None
        assert submission is not None
        assert submission["kind"] == "batch"
        assert [item["user_answer"] for item in submission["answers"]] == ["B", "D", "A"]
        assert looks_like_question_followup(message, question_set) is True


def test_resolve_submission_attempt_supports_compact_batch_letters_when_context_is_question_set() -> None:
    question_set = {
        "question_id": "quiz_3",
        "question": "第1题...\n第2题...\n第3题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "题1",
                "question_type": "single_choice",
                "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "题2",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                "correct_answer": "C",
            },
            {
                "question_id": "q_3",
                "question": "题3",
                "question_type": "single_choice",
                "options": {"A": "A3", "B": "B3", "C": "C3", "D": "D3"},
                "correct_answer": "D",
            },
        ],
    }

    for message in ("ACD", "ACD；", "答案：ACD"):
        target, submission = resolve_submission_attempt(message, question_set)
        assert target is not None
        assert submission is not None
        assert submission["kind"] == "batch"
        assert [item["user_answer"] for item in submission["answers"]] == ["A", "C", "D"]
        assert looks_like_question_followup(message, question_set) is True


def test_resolve_submission_keeps_compact_letters_for_single_multi_select_question() -> None:
    target, answer = resolve_submission(
        "ACD",
        {
            "question_id": "q_multi",
            "question": "下列关于防火门设置要求，正确的有（ ）。",
            "question_type": "multi_choice",
            "options": {
                "A": "甲级耐火极限 1.5h",
                "B": "向内开启",
                "C": "用于疏散应自行关闭",
                "D": "不应跨越变形缝",
            },
            "correct_answer": "ACD",
            "multi_select": True,
        },
    )

    assert target is not None
    assert answer == "ACD"


def test_resolve_submission_rejects_compact_letters_for_single_single_choice_question() -> None:
    target, answer = resolve_submission(
        "ACD",
        {
            "question_id": "q_single",
            "question": "下列说法正确的是（ ）。",
            "question_type": "single_choice",
            "options": {
                "A": "说法A",
                "B": "说法B",
                "C": "说法C",
                "D": "说法D",
            },
            "correct_answer": "B",
        },
    )

    assert target is not None
    assert answer is None


def test_resolve_submission_attempt_does_not_split_compact_letters_when_question_set_contains_multi_select() -> None:
    question_set = {
        "question_id": "quiz_4",
        "question": "第1题...\n第2题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题单选",
                "question_type": "single_choice",
                "options": {"A": "A1", "B": "B1", "C": "C1"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "第2题多选，正确的有（ ）。",
                "question_type": "multi_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                "correct_answer": "CD",
                "multi_select": True,
            },
        ],
    }

    target, submission = resolve_submission_attempt("ACD", question_set)

    assert target is not None
    assert submission is None


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


def test_extract_choice_result_summary_from_text_supports_bold_answer_markers() -> None:
    result_summary = extract_choice_result_summary_from_text(
        "\n".join(
            [
                "**题目**：关于混凝土养护开始时间，下列哪项说法是正确的？",
                "A. 混凝土应在初凝前开始养护",
                "B. 混凝土应在终凝后开始养护",
                "C. 混凝土应在终凝前开始养护",
                "D. 混凝土应在浇筑后立即开始养护",
                "",
                "**答案**：C",
                "",
                "**解析**：终凝前开始养护更符合规范要求。",
            ]
        )
    )

    assert result_summary is not None
    first = result_summary["results"][0]["qa_pair"]
    assert first["correct_answer"] == "C"
    assert "终凝前开始养护" in first["explanation"]


def test_extract_choice_result_summary_from_text_rejects_answer_only_authority_blocks() -> None:
    result_summary = extract_choice_result_summary_from_text(
        "\n".join(
            [
                "标准答案：CDE",
                "解析：【解析】考察考点 1A411021 建筑构造设计要求",
                "A 选项，防火门、防火窗应划分为甲、乙、丙三级。",
                "BC 选项，防火门应向疏散方向开启。",
                "【选项分析】",
                "A. × 甲级防火门耐火极限应为1.5h，不是1.0h",
                "B. × 应向疏散方向开启，不一定是向内",
                "C. ✓ 正确，符合规范要求",
                "D. ✓ 正确，疏散区域需自动关闭",
                "E. ✓ 正确，防止变形缝影响防火性能",
            ]
        )
    )

    assert result_summary is None


def test_build_choice_result_summary_from_exact_question_preserves_original_stem_and_options() -> None:
    result_summary = build_choice_result_summary_from_exact_question(
        {
            "id": "exact_q_1",
            "answer_kind": "mcq",
            "stem": "关于防火门设置要求，下列说法正确的是（ ）。",
            "options": {
                "A": "甲级防火门耐火极限为 1.5h",
                "B": "乙级防火门耐火极限为 1.0h",
                "C": "应向疏散方向开启",
                "D": "用于疏散的防火门应具有自行关闭功能",
            },
            "correct_answer": "CD",
            "analysis": "C、D 正确。",
        }
    )

    assert result_summary is not None
    qa_pair = result_summary["results"][0]["qa_pair"]
    assert qa_pair["question_id"] == "exact_q_1"
    assert qa_pair["question"] == "关于防火门设置要求，下列说法正确的是（ ）。"
    assert qa_pair["options"]["D"] == "用于疏散的防火门应具有自行关闭功能"
    assert qa_pair["correct_answer"] == "CD"
    assert qa_pair["multi_select"] is True


def test_build_choice_result_summary_from_exact_question_skips_missing_options() -> None:
    assert (
        build_choice_result_summary_from_exact_question(
            {
                "id": "exact_q_missing_options",
                "answer_kind": "mcq",
                "stem": "关于模板拆除，下列说法正确的是（ ）。",
                "options": None,
                "correct_answer": "B",
                "analysis": "B 正确。",
            }
        )
        is None
    )
