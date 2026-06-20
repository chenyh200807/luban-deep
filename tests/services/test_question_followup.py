from __future__ import annotations

import json

import pytest

from deeptutor.services.question_followup import (
    annotate_batch_submission_context,
    apply_followup_action_to_context,
    answers_match,
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_presentation,
    build_question_followup_context_from_result_summary,
    detect_answer_reveal_preference,
    detect_requested_question_type,
    extract_choice_result_summary_from_text,
    looks_like_question_followup,
    normalize_question_followup_context,
    resolve_submission,
    resolve_submission_attempt,
    should_block_unanswered_reference_reveal,
    should_reveal_reference_material,
)
from deeptutor.services.render_presentation import build_canonical_presentation


def test_detect_requested_question_type_prefers_explicit_written_case() -> None:
    question_type, is_explicit = detect_requested_question_type(
        "围绕基坑工程给我出一道案例题"
    )

    assert question_type == "written"
    assert is_explicit is True


def test_detect_answer_reveal_preference_respects_suppress_request() -> None:
    assert detect_answer_reveal_preference("先别给答案，只问我第1问") is False
    assert detect_answer_reveal_preference("先不要直接给答案，先给作答要求") is False
    assert detect_answer_reveal_preference("不要先给答案，先考我") is False
    assert detect_answer_reveal_preference("出3道建筑实务单选题，先不公布答案。") is False


def test_resolve_submission_attempt_extracts_numbered_batch_with_wo_xuan_prefix() -> None:
    question_set = {
        "question_id": "quiz_generated",
        "question": "第1题...\n第2题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题",
                "question_type": "single_choice",
                "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                "grading_key": {"correct_answer": "A"},
            },
            {
                "question_id": "q_2",
                "question": "第2题",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                "grading_key": {"correct_answer": "B"},
            },
        ],
    }

    target, submission = resolve_submission_attempt(
        "第1题我选AC，第2题我选BD，批改一下。",
        question_set,
    )

    assert target is not None
    assert submission == {
        "kind": "batch",
        "answers": [
            {"index": 1, "question_id": "q_1", "user_answer": "AC"},
            {"index": 2, "question_id": "q_2", "user_answer": "BD"},
        ],
    }


def test_build_choice_result_summary_reads_canonical_answer_from_exact_question_metadata() -> None:
    summary = build_choice_result_summary_from_exact_question(
        {
            "id": "historical:q1",
            "answer_kind": "mcq",
            "stem": "历史建筑高度怎么算？",
            "options": [
                {"key": "A", "value": "檐口顶点"},
                {"key": "B", "value": "屋脊"},
                {"key": "C", "value": "墙顶点"},
                {"key": "D", "value": "最高点"},
            ],
            "analysis": "应按室外设计地坪至建（构）筑物最高点计算。",
            "metadata": {"canonical_correct_answer": "D"},
        }
    )

    assert summary is not None
    qa_pair = summary["results"][0]["qa_pair"]
    assert qa_pair["correct_answer"] == "D"
    assert qa_pair["explanation"] == "应按室外设计地坪至建（构）筑物最高点计算。"


def test_resolve_submission_attempt_rejects_multi_option_single_choice_without_item_anchor() -> None:
    target, submission = resolve_submission_attempt(
        "我选AC，批改一下。",
        {
            "question_id": "q_single",
            "question": "单选题。",
            "question_type": "single_choice",
            "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
            "grading_key": {"correct_answer": "A"},
        },
    )

    assert target is not None
    assert submission is None


def test_unanswered_question_does_not_reveal_answer_on_direct_answer_request() -> None:
    question_context = {
        "question_id": "q1",
        "question": "验槽通常主要采用什么方法？",
        "question_type": "choice",
        "options": {"A": "观察法", "B": "钎探法"},
        "correct_answer": "A",
        "explanation": "观察法为主，钎探法为辅。",
    }

    assert should_reveal_reference_material("直接告诉我答案", question_context) is False


def test_unanswered_question_set_blocks_indexed_reference_reveal_until_attempt() -> None:
    question_context = {
        "question_id": "quiz_generated",
        "question": "第1题...\n第2题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题",
                "question_type": "single_choice",
                "options": {"A": "A1", "B": "B1"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "第2题",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2"},
                "grading_key": {"correct_answer": "B"},
            },
        ],
    }

    assert should_block_unanswered_reference_reveal(
        "现在公布第2题答案和解析，不要批第1题。",
        question_context,
    ) is True
    assert should_reveal_reference_material(
        "现在公布第2题答案和解析，不要批第1题。",
        question_context,
    ) is False

    attempted_context = dict(question_context)
    attempted_context["items"] = [dict(item) for item in question_context["items"]]
    attempted_context["items"][1]["user_answer"] = "A"
    attempted_context["items"][1]["is_correct"] = False

    assert should_block_unanswered_reference_reveal(
        "现在公布第2题答案和解析，不要批第1题。",
        attempted_context,
    ) is False

    assert should_block_unanswered_reference_reveal(
        "第2题参考哪个规范？先不要公布答案。",
        question_context,
    ) is True

    assert should_block_unanswered_reference_reveal(
        "现在公布第3题答案和解析。",
        question_context,
    ) is True


def test_unanswered_question_reveals_when_learner_explicitly_concedes() -> None:
    question_context = {
        "question_id": "q1",
        "question": "验槽通常主要采用什么方法？",
        "question_type": "choice",
        "options": {"A": "观察法", "B": "钎探法"},
        "correct_answer": "A",
    }

    assert should_reveal_reference_material("我放弃这题，直接告诉我答案", question_context) is True


def test_answered_question_can_reveal_reference_material() -> None:
    question_context = {
        "question_id": "q1",
        "question": "验槽通常主要采用什么方法？",
        "question_type": "choice",
        "options": {"A": "观察法", "B": "钎探法"},
        "correct_answer": "A",
        "user_answer": "B",
        "is_correct": False,
    }

    assert should_reveal_reference_material("直接告诉我答案", question_context) is True


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


def test_resolve_submission_attempt_extracts_explicit_natural_option_values() -> None:
    target, submission = resolve_submission_attempt(
        "五个候选是施工方案、支架构造、底座与托撑、构配件材质、支架稳定。我只勾施工方案+支架构造+支架稳定，能拿满吗？",
        {
            "question_id": "q_template_support",
            "question": "模板支架检查评分表保证项目包括哪些？",
            "question_type": "choice",
            "options": {
                "A": "施工方案",
                "B": "支架构造",
                "C": "底座与托撑",
                "D": "构配件材质",
                "E": "支架稳定",
            },
            "correct_answer": "ABE",
            "multi_select": True,
        },
    )

    assert target is not None
    assert submission == {
        "kind": "single",
        "answer": "ABE",
        "question_id": "q_template_support",
    }


def test_resolve_submission_attempt_maps_answer_value_to_current_option_key() -> None:
    question_context = {
        "question_id": "q_waterproof_life",
        "question": "室内工程防水设计工作年限不应低于（ ）。",
        "question_type": "single_choice",
        "options": {"A": "50年", "B": "25年", "C": "20年", "D": "15年"},
        "correct_answer": "B",
    }

    target, submission = resolve_submission_attempt("我答25年", question_context)

    assert target is not None
    assert submission == {
        "kind": "single",
        "answer": "B",
        "question_id": "q_waterproof_life",
    }


def test_resolve_submission_attempt_uses_answer_tail_not_option_table_letters() -> None:
    question_context = {
        "question_id": "q_waterproof_life",
        "question": "室内工程防水设计工作年限不应低于（ ）。",
        "question_type": "single_choice",
        "options": {"A": "50年", "B": "25年", "C": "20年", "D": "15年"},
        "correct_answer": "B",
    }

    target, submission = resolve_submission_attempt(
        (
            "室内工程防水设计工作年限不应低于（ ）。"
            "A.50年 B.25年 C.20年 D.15年，我答25年，直接判，一句话"
        ),
        question_context,
    )

    assert target is not None
    assert submission == {
        "kind": "single",
        "answer": "B",
        "question_id": "q_waterproof_life",
    }


def test_resolve_submission_attempt_uses_letter_tail_not_option_table_letters() -> None:
    question_context = {
        "question_id": "q_waterproof_life",
        "question": "室内工程防水设计工作年限不应低于（ ）。",
        "question_type": "single_choice",
        "options": {"A": "50年", "B": "25年", "C": "20年", "D": "15年"},
        "correct_answer": "B",
    }

    target, submission = resolve_submission_attempt(
        (
            "室内工程防水设计工作年限不应低于（ ）。"
            "A.50年 B.25年 C.20年 D.15年，我答B，直接判，一句话"
        ),
        question_context,
    )

    assert target is not None
    assert submission == {
        "kind": "single",
        "answer": "B",
        "question_id": "q_waterproof_life",
    }


def test_resolve_submission_attempt_does_not_treat_option_table_as_answer() -> None:
    question_context = {
        "question_id": "q_waterproof_life",
        "question": "室内工程防水设计工作年限不应低于（ ）。",
        "question_type": "single_choice",
        "options": {"A": "50年", "B": "25年", "C": "20年", "D": "15年"},
        "correct_answer": "B",
    }

    target, submission = resolve_submission_attempt(
        "室内工程防水设计工作年限不应低于（ ）。A.50年 B.25年 C.20年 D.15年",
        question_context,
    )

    assert target is not None
    assert submission is None


def test_answers_match_compares_option_value_to_current_correct_letter() -> None:
    question_context = {
        "question_id": "q_waterproof_life",
        "question": "室内工程防水设计工作年限不应低于（ ）。",
        "question_type": "single_choice",
        "options": {"A": "50年", "B": "25年", "C": "20年", "D": "15年"},
        "correct_answer": "B",
    }

    assert answers_match("25年", "B", question_context) is True
    assert answers_match("50年", "B", question_context) is False


def test_resolve_submission_attempt_extracts_explicit_letters_after_option_table() -> None:
    target, submission = resolve_submission_attempt(
        (
            "地下连续墙施工质量控制多选：A.槽段长度8-10m B.导墙高度1.0m "
            "C.现浇钢筋混凝土导墙 D.导管法连续浇筑混凝土 "
            "E.设计强度后墙底注浆。我实际选的是ACDE，对吗？"
        ),
        {
            "question_id": "q_wall",
            "question": "地下连续墙施工质量控制，下列说法正确的有？",
            "question_type": "choice",
            "options": {
                "A": "槽段长度8-10m",
                "B": "导墙高度1.0m",
                "C": "现浇钢筋混凝土导墙",
                "D": "导管法连续浇筑混凝土",
                "E": "设计强度后墙底注浆",
            },
            "correct_answer": "CDE",
            "multi_select": True,
        },
    )

    assert target is not None
    assert submission == {
        "kind": "single",
        "answer": "ACDE",
        "question_id": "q_wall",
    }


def test_resolve_submission_attempt_accepts_subjective_case_answer() -> None:
    target, submission = resolve_submission_attempt(
        "我的答案：共用一个开关箱不妥，应采用专用开关箱。请按案例题阅卷标准批改。",
        {
            "question_id": "case_1",
            "question": "指出临时用电管理中的不妥之处。",
            "question_type": "case",
            "correct_answer": "共用一个开关箱不妥，应采用专用开关箱。",
        },
    )

    assert target is not None
    assert submission is not None
    assert submission["kind"] == "single"
    assert submission["question_id"] == "case_1"
    assert submission["answer"] == "共用一个开关箱不妥，应采用专用开关箱"


@pytest.mark.parametrize(
    "message",
    [
        "我的答案是：防水工程施工前应检查基层是否平整。",
        "我的答案是：应说明如何进行蓄水试验。",
    ],
)
def test_resolve_submission_attempt_keeps_explicit_subjective_answer_with_question_words(
    message: str,
) -> None:
    target, submission = resolve_submission_attempt(
        message,
        {
            "question_id": "case_1",
            "question": "指出防水施工前应检查的内容。",
            "question_type": "case",
            "correct_answer": "防水工程施工前应检查基层是否平整。",
        },
    )

    assert target is not None
    assert submission is not None
    assert submission["kind"] == "single"
    assert submission["question_id"] == "case_1"


def test_resolve_submission_attempt_keeps_subjective_explanation_as_followup() -> None:
    target, submission = resolve_submission_attempt(
        "为什么这道题要写专用开关箱？",
        {
            "question_id": "case_1",
            "question": "指出临时用电管理中的不妥之处。",
            "question_type": "case",
            "correct_answer": "共用一个开关箱不妥，应采用专用开关箱。",
        },
    )

    assert target is not None
    assert submission is None


def test_resolve_submission_attempt_keeps_english_written_explanation_as_followup() -> None:
    target, submission = resolve_submission_attempt(
        "Why was my answer wrong?",
        {
            "question_id": "q_3",
            "question": "What does density mean in win-rate comparison?",
            "question_type": "written",
            "user_answer": "coverage",
            "correct_answer": "relevant information without redundancy",
            "is_correct": False,
            "explanation": "Density is about relevant content without redundancy.",
        },
    )

    assert target is not None
    assert submission is None


@pytest.mark.parametrize(
    "message",
    [
        "为什么不是B？一句话。",
        "为什么不是 B？一句话。",
        "B为什么不对？",
        "B为啥错？",
        "那C为什么不对？一句话。",
        "C为什么不对",
        "B怎么扣？",
        "C不对吗？",
        "A错在哪里？一句话",
        "A错在哪？",
        "A哪里错了？",
        "那C呢？",
        "那C呢？一句话",
        "我不是要重新提交C，是想知道C为什么不对；用刚才那题回答。",
        "我不是要重新提交C",
        "如果我选B，你会怎么扣？",
        "这里是不是屋脊？如果选B会怎么判？",
        "不选A为什么不行？",
        "不是提交C，解释一下C错在哪里。",
        "别把B当我的答案，我是问B为什么扣分。",
    ],
)
def test_resolve_submission_attempt_keeps_option_challenge_as_followup(
    message: str,
) -> None:
    question_context = {
        "question_id": "q_ratio",
        "question": "某企业本期营业收入为1000万元，利润总额为50万元，则营业利润率为？",
        "question_type": "choice",
        "options": {"A": "2%", "B": "3%", "C": "4%", "D": "5%"},
        "correct_answer": "D",
        "user_answer": "B",
        "is_correct": False,
    }

    target, submission = resolve_submission_attempt(message, question_context)

    assert target is not None
    assert submission is None
    assert looks_like_question_followup(message, question_context) is True


def test_resolve_submission_attempt_keeps_option_value_challenge_as_followup() -> None:
    question_context = {
        "question_id": "q_diaphragm_wall",
        "question": "关于地下连续墙施工要求，正确的有（ ）。",
        "question_type": "multiple_choice",
        "options": {
            "A": "地下连续墙单元槽段长度宜为8～10m",
            "B": "导墙高度不应小于1.0m",
            "C": "应设置现浇钢筋混凝土导墙",
            "D": "水下混凝土应采用导管法连续浇筑",
            "E": "混凝土达到设计强度后方可进行墙底注浆",
        },
        "correct_answer": "CDE",
        "user_answer": "ACDE",
        "is_correct": False,
    }

    target, submission = resolve_submission_attempt("那1.0m行不行？一句话", question_context)

    assert target is not None
    assert submission is None
    assert looks_like_question_followup("那1.0m行不行？一句话", question_context) is True


@pytest.mark.parametrize("message", ["我选B", "我改成B", "答案是B", "B"])
def test_resolve_submission_attempt_keeps_explicit_option_submission(
    message: str,
) -> None:
    target, submission = resolve_submission_attempt(
        message,
        {
            "question_id": "q_ratio",
            "question": "某企业本期营业收入为1000万元，利润总额为50万元，则营业利润率为？",
            "question_type": "choice",
            "options": {"A": "2%", "B": "3%", "C": "4%", "D": "5%"},
            "correct_answer": "D",
            "user_answer": "B",
            "is_correct": False,
        },
    )

    assert target is not None
    assert submission == {
        "kind": "single",
        "answer": "B",
        "question_id": "q_ratio",
    }


@pytest.mark.parametrize(
    "message",
    [
        "选择题",
        "给我出单选题",
        "给我出简答题",
        "我想练习防水工程相关简答题",
        "讲讲防水工程",
        "答案是什么",
        "我的答案是什么",
        "防水工程怎么施工",
    ],
)
def test_resolve_submission_attempt_does_not_treat_generation_or_explainer_as_subjective_answer(
    message: str,
) -> None:
    target, submission = resolve_submission_attempt(
        message,
        {
            "question_id": "case_1",
            "question": "指出临时用电管理中的不妥之处。",
            "question_type": "case",
            "correct_answer": "共用一个开关箱不妥，应采用专用开关箱。",
        },
    )

    assert target is not None
    assert submission is None


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


def test_resolve_submission_attempt_supports_renderer_generated_batch_submission() -> None:
    question_set = {
        "question_id": "quiz_renderer",
        "question": "第1题...\n第2题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "题1",
                "question_type": "single_choice",
                "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                "correct_answer": "B",
            },
            {
                "question_id": "q_2",
                "question": "题2",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                "correct_answer": "B",
            },
        ],
    }

    target, submission = resolve_submission_attempt(
        "提交作答，请批改：第1题：B；第2题：B",
        question_set,
    )

    assert target is not None
    assert submission is not None
    assert submission["kind"] == "batch"
    assert [item["question_id"] for item in submission["answers"]] == ["q_1", "q_2"]
    assert [item["user_answer"] for item in submission["answers"]] == ["B", "B"]


def test_resolve_submission_attempt_keeps_unmatched_numbered_batch_refs_explicit() -> None:
    question_set = {
        "question_id": "quiz_unmatched",
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
                "correct_answer": "B",
            },
            {
                "question_id": "q_3",
                "question": "题3",
                "question_type": "single_choice",
                "options": {"A": "A3", "B": "B3", "C": "C3", "D": "D3"},
                "correct_answer": "C",
            },
        ],
    }

    target, submission = resolve_submission_attempt("q1 A, q3 C, q5 B", question_set)

    assert target is not None
    assert submission is not None
    assert submission["kind"] == "batch"
    assert submission["answers"] == [
        {"index": 1, "question_id": "q_1", "user_answer": "A"},
        {"index": 3, "question_id": "q_3", "user_answer": "C"},
        {"index": 5, "question_id": "", "user_answer": "B", "unmatched": True},
    ]
    graded = annotate_batch_submission_context(question_set, submission["answers"])
    assert graded is not None
    assert [item.get("user_answer", "") for item in graded["items"]] == ["A", "", "C"]
    assert graded["unmatched_answer_refs"] == [
        {"index": 5, "question_id": "", "user_answer": "B"}
    ]


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


def test_resolve_submission_attempt_supports_compact_numbered_batch_variants() -> None:
    question_set = {
        "question_id": "quiz_3_numbered",
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

    for message in (
        "第一题A第二题C第三题D",
        "第1题A第2题C第3题D",
        "1A2C3D",
        "1a2c3d",
        "1:A 2:C 3:D",
        "一A二C三D",
    ):
        target, submission = resolve_submission_attempt(message, question_set)
        assert target is not None
        assert submission is not None
        assert submission["kind"] == "batch"
        assert [item["user_answer"] for item in submission["answers"]] == ["A", "C", "D"]
        assert looks_like_question_followup(message, question_set) is True


def test_resolve_submission_attempt_supports_prefixed_compact_batch_letters() -> None:
    question_set = {
        "question_id": "quiz_3_prefixed",
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

    expected_answers = {
        "我的：acd": ["A", "C", "D"],
        "我的答案：ACD": ["A", "C", "D"],
        "答案是acd": ["A", "C", "D"],
        "前面三题我选acd": ["A", "C", "D"],
        "cad吧": ["C", "A", "D"],
    }
    for message, expected in expected_answers.items():
        target, submission = resolve_submission_attempt(message, question_set)
        assert target is not None
        assert submission is not None
        assert submission["kind"] == "batch"
        assert [item["user_answer"] for item in submission["answers"]] == expected


def test_resolve_submission_attempt_supports_batch_correction_with_other_answers_unchanged() -> None:
    question_set = {
        "question_id": "quiz_correction",
        "question": "第1题...\n第2题...\n第3题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "题1",
                "question_type": "single_choice",
                "options": {"A": "A1", "B": "B1", "C": "C1", "D": "D1"},
                "correct_answer": "A",
                "user_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "题2",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2", "D": "D2"},
                "correct_answer": "C",
                "user_answer": "B",
            },
            {
                "question_id": "q_3",
                "question": "题3",
                "question_type": "single_choice",
                "options": {"A": "A3", "B": "B3", "C": "C3", "D": "D3"},
                "correct_answer": "D",
                "user_answer": "D",
            },
        ],
    }

    target, submission = resolve_submission_attempt("第2题改成C，其他不变", question_set)

    assert target is not None
    assert submission is not None
    assert submission["kind"] == "batch"
    assert [item["user_answer"] for item in submission["answers"]] == ["A", "C", "D"]


def test_apply_followup_action_to_context_preserves_other_answers_for_llm_revisions() -> None:
    question_set = {
        "question_id": "quiz_llm_revision",
        "question": "第1题...\n第2题...\n第3题...",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "题1",
                "question_type": "single_choice",
                "correct_answer": "C",
                "user_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "题2",
                "question_type": "single_choice",
                "correct_answer": "B",
                "user_answer": "B",
            },
            {
                "question_id": "q_3",
                "question": "题3",
                "question_type": "single_choice",
                "correct_answer": "D",
                "user_answer": "D",
            },
        ],
    }

    graded = apply_followup_action_to_context(
        question_set,
        {
            "intent": "revise_answers",
            "preserve_other_answers": True,
            "answers": [
                {
                    "index": 1,
                    "question_id": "q_1",
                    "user_answer": "C",
                }
            ],
        },
    )

    assert graded is not None
    assert [item["user_answer"] for item in graded["items"]] == ["C", "B", "D"]
    assert [item["is_correct"] for item in graded["items"]] == [True, True, True]


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


def test_resolve_submission_attempt_requires_question_index_for_multi_question_single_letter() -> None:
    question_set = {
        "question_id": "quiz_3",
        "question": "第1题...\n第2题...\n第3题...",
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
                "question": "第2题单选",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2"},
                "correct_answer": "B",
            },
        ],
    }

    target, submission = resolve_submission_attempt("我选B", question_set)

    assert target is not None
    assert submission == {
        "kind": "ambiguous",
        "answer": "B",
        "requires_question_index": True,
    }


def test_resolve_submission_attempt_accepts_q_number_single_submission() -> None:
    question_set = {
        "question_id": "quiz_4",
        "question": "第1题...\n第2题...\n第3题...",
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
                "question": "第2题单选",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2"},
                "correct_answer": "B",
            },
        ],
    }

    target, submission = resolve_submission_attempt("q2 选C", question_set)

    assert target is not None
    assert target["question_id"] == "q_2"
    assert submission == {
        "kind": "single",
        "answer": "C",
        "question_id": "q_2",
    }


@pytest.mark.parametrize("message", ["q2 为什么选C", "第2题为什么选C", "q2 答案是什么"])
def test_resolve_submission_attempt_keeps_q_numbered_question_as_followup(message: str) -> None:
    question_set = {
        "question_id": "quiz_5",
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
                "question": "第2题单选",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2"},
                "correct_answer": "B",
            },
        ],
    }

    target, submission = resolve_submission_attempt(message, question_set)

    assert target is not None
    assert target["question_id"] == "q_2"
    assert submission is None


def test_looks_like_question_followup_accepts_q_numbered_answer_request() -> None:
    question_set = {
        "question_id": "quiz_6",
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
                "question": "第2题单选",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2", "C": "C2"},
                "correct_answer": "B",
            },
        ],
    }

    assert looks_like_question_followup("q2 答案是什么", question_set) is True


def test_resolve_submission_attempt_keeps_single_numbered_case_answer_unsplit() -> None:
    question_set = {
        "question_id": "case_set_1",
        "question": "第1问...\n第2问...",
        "question_type": "case",
        "items": [
            {
                "question_id": "case_q1",
                "question": "第1问",
                "question_type": "case",
                "correct_answer": "应说明组织责任。",
            },
            {
                "question_id": "case_q2",
                "question": "第2问",
                "question_type": "case",
                "correct_answer": "施工缝未按规范处理，需要返工整改。",
            },
        ],
    }

    target, submission = resolve_submission_attempt(
        "第2问我的答案是施工缝未按规范处理，需要返工整改",
        question_set,
    )

    assert target is not None
    assert target["question_id"] == "case_q2"
    assert submission == {
        "kind": "single",
        "answer": "施工缝未按规范处理，需要返工整改",
        "question_id": "case_q2",
    }


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


def test_build_question_followup_context_from_result_summary_keeps_metadata_knowledge_context() -> None:
    context = build_question_followup_context_from_result_summary(
        {
            "results": [
                {
                    "qa_pair": {
                        "question_id": "q_1",
                        "question_type": "choice",
                        "question": "总时差和自由时差的区别，以下哪项正确？",
                        "options": {"A": "说法A", "B": "说法B"},
                        "correct_answer": "B",
                        "explanation": "",
                        "metadata": {
                            "knowledge_context": "自由时差是不影响紧后工作最早开始的机动时间。"
                        },
                    }
                }
            ]
        },
        "### Question 1\n总时差和自由时差的区别，以下哪项正确？",
        reveal_answers=False,
        reveal_explanations=False,
    )

    assert context is not None
    assert context["items"][0]["knowledge_context"] == "自由时差是不影响紧后工作最早开始的机动时间。"


def test_normalize_question_followup_context_preserves_compact_evidence_refs() -> None:
    context = normalize_question_followup_context(
        {
            "question_id": "case_1",
            "question": "某危大工程专项方案应如何组织论证？",
            "question_type": "case",
            "correct_answer": "应组织专家论证，并编制专项施工方案后按规定审批。",
            "evidence_refs": [
                {
                    "source": "evidence_bundle",
                    "field": "kb_chunks",
                    "content": "危大工程应编制专项施工方案，超过一定规模的应组织专家论证。",
                }
            ],
        }
    )

    assert context is not None
    assert context["evidence_refs"] == [
        {
            "source": "evidence_bundle",
            "field": "kb_chunks",
            "content": "危大工程应编制专项施工方案，超过一定规模的应组织专家论证。",
            "source_type": "evidence_bundle",
            "public_quote": "危大工程应编制专项施工方案，超过一定规模的应组织专家论证。",
        }
    ]


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


def test_canonical_presentation_keeps_choice_aliases_as_interactive_cards() -> None:
    presentation = build_canonical_presentation(
        content="### Question 1\n...\n### Question 2\n...",
        result_summary={
            "results": [
                {
                    "qa_pair": {
                        "question_id": "q_1",
                        "question_type": "single_choice",
                        "question": "《建筑法》属于（ ）。",
                        "options": {"A": "法律", "B": "行政法规"},
                        "correct_answer": "A",
                    }
                },
                {
                    "qa_pair": {
                        "question_id": "q_2",
                        "question_type": "multi_choice",
                        "question": "正确的说法有（ ）。",
                        "options": {"A": "说法A", "B": "说法B", "C": "说法C"},
                        "correct_answer": "AB",
                    }
                },
            ]
        },
        reveal_answers=False,
        reveal_explanations=False,
    )

    assert presentation is not None
    mcq_block = presentation["blocks"][0]
    assert len(mcq_block["questions"]) == 2
    assert mcq_block["questions"][0]["question_type"] == "single_choice"
    assert mcq_block["questions"][1]["question_type"] == "multi_choice"
    assert mcq_block["questions"][0]["followup_context"]["correct_answer"] == ""
    assert mcq_block["questions"][1]["followup_context"]["correct_answer"] == ""


def test_merge_redacted_single_submission_with_authoritative_question_set() -> None:
    from deeptutor.services.session.turn_runtime import (
        _merge_public_submission_with_authoritative_context,
    )

    public_context = {
        "question_id": "q_2",
        "question": "《建设工程安全生产管理条例》属于（ ）。",
        "question_type": "choice",
        "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
        "correct_answer": "",
        "user_answer": "B",
    }
    authoritative_context = {
        "question_id": "question_set",
        "question": "相关五道题",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "《建筑法》属于（ ）。",
                "question_type": "choice",
                "options": {"A": "法律", "B": "行政法规"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "《建设工程安全生产管理条例》属于（ ）。",
                "question_type": "choice",
                "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
                "correct_answer": "B",
                "explanation": "条例由国务院制定，属于行政法规。",
            },
        ],
    }

    merged = _merge_public_submission_with_authoritative_context(
        public_context,
        authoritative_context,
    )

    assert merged is not None
    assert merged["question_id"] == "q_2"
    assert merged["correct_answer"] == "B"
    assert merged["user_answer"] == "B"
    assert "国务院" in merged["explanation"]


def test_merge_redacted_batch_submission_restores_all_authoritative_items_by_id() -> None:
    from deeptutor.services.session.turn_runtime import (
        _merge_public_submission_with_authoritative_context,
    )

    public_context = {
        "question_id": "question_set",
        "question": "相关五道题",
        "question_type": "choice",
        "items": [
            {"question_id": "q_5", "question": "题5", "question_type": "single_choice", "correct_answer": "", "user_answer": "D"},
            {"question_id": "q_1", "question": "题1", "question_type": "single_choice", "correct_answer": "", "user_answer": "A"},
            {"question_id": "q_2", "question": "题2", "question_type": "single_choice", "correct_answer": "", "user_answer": "B"},
        ],
    }
    authoritative_context = {
        "question_id": "question_set",
        "question": "相关五道题",
        "question_type": "choice",
        "items": [
            {"question_id": "q_1", "question": "题1", "question_type": "single_choice", "correct_answer": "A", "explanation": "第1题解析"},
            {"question_id": "q_2", "question": "题2", "question_type": "single_choice", "correct_answer": "B", "explanation": "第2题解析"},
            {"question_id": "q_3", "question": "题3", "question_type": "single_choice", "correct_answer": "C", "explanation": "第3题解析"},
            {"question_id": "q_4", "question": "题4", "question_type": "single_choice", "correct_answer": "A", "explanation": "第4题解析"},
            {"question_id": "q_5", "question": "题5", "question_type": "single_choice", "correct_answer": "D", "explanation": "第5题解析"},
        ],
    }

    merged = _merge_public_submission_with_authoritative_context(
        public_context,
        authoritative_context,
    )

    assert merged is not None
    merged_items = {item["question_id"]: item for item in merged["items"]}
    assert list(merged_items) == ["q_1", "q_2", "q_3", "q_4", "q_5"]
    assert merged_items["q_1"]["correct_answer"] == "A"
    assert merged_items["q_1"]["user_answer"] == "A"
    assert merged_items["q_2"]["correct_answer"] == "B"
    assert merged_items["q_2"]["user_answer"] == "B"
    assert merged_items["q_5"]["correct_answer"] == "D"
    assert merged_items["q_5"]["user_answer"] == "D"
    assert merged_items["q_3"]["user_answer"] == ""
    assert "第5题解析" in merged_items["q_5"]["explanation"]


def test_turn_runtime_does_not_promote_ambiguous_multi_question_answer() -> None:
    from deeptutor.services.session.turn_runtime import (
        _submission_action_for_user_message,
    )

    question_set = {
        "question_id": "question_set",
        "question": "相关两道题",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题单选",
                "question_type": "single_choice",
                "options": {"A": "A1", "B": "B1"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "第2题单选",
                "question_type": "single_choice",
                "options": {"A": "A2", "B": "B2"},
                "correct_answer": "B",
            },
        ],
    }

    resolved_context, action = _submission_action_for_user_message("我选B", question_set)

    assert resolved_context is not None
    assert action is None


def test_merge_redacted_batch_submission_recognizes_hidden_grading_key_authority() -> None:
    from deeptutor.services.session.turn_runtime import (
        _merge_public_submission_with_authoritative_context,
    )

    public_context = {
        "question_id": "question_set",
        "question": "相关三道题",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题",
                "question_type": "single_choice",
                "correct_answer": "",
                "user_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "第2题",
                "question_type": "single_choice",
                "correct_answer": "",
                "user_answer": "B",
            },
            {
                "question_id": "q_3",
                "question": "第3题",
                "question_type": "single_choice",
                "correct_answer": "",
                "user_answer": "B",
            },
        ],
    }
    authoritative_context = {
        "question_id": "question_set",
        "question": "相关三道题",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题",
                "question_type": "single_choice",
                "correct_answer": "",
                "grading_key": {"correct_answer": "A"},
                "explanation": "第1题解析",
            },
            {
                "question_id": "q_2",
                "question": "第2题",
                "question_type": "single_choice",
                "correct_answer": "",
                "grading_key": {"correct_answer": "C"},
                "explanation": "第2题解析",
            },
            {
                "question_id": "q_3",
                "question": "第3题",
                "question_type": "single_choice",
                "correct_answer": "",
                "grading_key": {"correct_answer": "B"},
                "explanation": "第3题解析",
            },
        ],
    }

    merged = _merge_public_submission_with_authoritative_context(
        public_context,
        authoritative_context,
    )

    assert merged is not None
    merged_items = {item["question_id"]: item for item in merged["items"]}
    assert merged_items["q_1"]["grading_key"]["correct_answer"] == "A"
    assert merged_items["q_1"]["user_answer"] == "A"
    assert merged_items["q_2"]["grading_key"]["correct_answer"] == "C"
    assert merged_items["q_2"]["user_answer"] == "B"
    assert merged_items["q_3"]["grading_key"]["correct_answer"] == "B"
    assert merged_items["q_3"]["user_answer"] == "B"


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


def test_extract_choice_result_summary_from_text_keeps_scenario_before_problem_marker() -> None:
    result_summary = extract_choice_result_summary_from_text(
        "\n".join(
            [
                "好，考你一道跟刚才内容直接相关的题，看你能不能把知识点用上。",
                "",
                "---",
                "",
                "**题目：**",
                "",
                "某办公楼装修工程施工中，质检员发现以下情况：",
                "",
                "1. 内墙抹灰时，混凝土墙面未做任何处理直接抹灰。",
                "2. 外墙不同基层（混凝土柱与砌体墙）交接处未挂钢丝网。",
                "3. 吊顶工程中，不上人吊顶的吊杆采用直径 6mm 镀锌钢筋，部分吊杆长度达到 1.8m，未设置反支撑。",
                "4. 纸面石膏板吊顶板缝对接严密，未留缝隙。",
                "",
                "**问题：**",
                "",
                "以上 4 项做法中，存在质量隐患的有几项？",
                "",
                "A. 1 项",
                "B. 2 项",
                "C. 3 项",
                "D. 4 项",
            ]
        )
    )

    assert result_summary is not None
    first = result_summary["results"][0]["qa_pair"]
    assert "某办公楼装修工程施工中" in first["question"]
    assert "内墙抹灰时" in first["question"]
    assert "以上 4 项做法中，存在质量隐患的有几项" in first["question"]
    assert first["options"]["D"] == "4 项"


@pytest.mark.parametrize(
    ("heading", "context_line", "problem_line", "expected_problem"),
    [
        ("材料：", "某办公楼装修工程施工中，项目部发现以下做法：", "问题：", "以上做法中存在质量隐患的有几项"),
        ("【背景资料】", "某办公楼装修工程施工中，项目部发现以下做法：", "问题：以上做法中存在质量隐患的有几项？", "以上做法中存在质量隐患的有几项"),
        ("案例：", "某施工现场模板支撑高度较大，项目部未进行专项方案论证。", "问题：", "以上做法中存在质量隐患的有几项"),
        ("题干：", "某工程屋面防水施工完成后进行蓄水试验。", "问题：下列说法正确的是哪一项？", "下列说法正确的是哪一项"),
    ],
)
def test_extract_choice_result_summary_from_text_keeps_context_before_problem_marker(
    heading: str,
    context_line: str,
    problem_line: str,
    expected_problem: str,
) -> None:
    result_summary = extract_choice_result_summary_from_text(
        "\n".join(
            [
                heading,
                context_line,
                "1. 未做基层处理。",
                "2. 未挂钢丝网。",
                "",
                problem_line,
                "" if problem_line.endswith("：") else " ",
                "以上做法中存在质量隐患的有几项？" if problem_line.endswith("：") else "",
                "A. 1 项",
                "B. 2 项",
                "C. 3 项",
                "D. 4 项",
            ]
        )
    )

    assert result_summary is not None
    first = result_summary["results"][0]["qa_pair"]
    assert context_line in first["question"]
    assert "未做基层处理" in first["question"]
    assert expected_problem in first["question"]
    assert first["options"]["D"] == "4 项"


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


# ─────────────────────────────────────────────────────────────────────────────
# Batch C / A5 — grading_key persistence + public redaction
# plan §Phase 3 Step 3.4 acceptance.
# ─────────────────────────────────────────────────────────────────────────────


def test_grading_key_persisted_in_followup_context_item_from_result_summary() -> None:
    from deeptutor.services.question_followup import (
        build_question_followup_context_from_result_summary,
    )

    result_summary = {
        "results": [
            {
                "qa_pair": {
                    "question_id": "q_1",
                    "question": "What is 2+2?",
                    "question_type": "choice",
                    "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
                    "correct_answer": "B",
                    "explanation": "",
                    "grading_key": {
                        "correct_answer": "B",
                        "scoring_points": [],
                        "common_traps": [],
                        "source": "lightweight_llm",
                    },
                }
            }
        ]
    }
    ctx = build_question_followup_context_from_result_summary(
        result_summary,
        rendered_response="2+2=?",
        reveal_answers=False,
    )
    assert ctx is not None
    items = ctx.get("items") or []
    assert items and isinstance(items[0], dict)
    assert items[0].get("grading_key", {}).get("correct_answer") == "B"


def test_hidden_grading_key_supplies_followup_correct_answer_when_public_answer_is_empty() -> None:
    from deeptutor.services.question_followup import (
        build_question_followup_context_from_result_summary,
    )

    result_summary = {
        "results": [
            {
                "qa_pair": {
                    "question_id": "q_1",
                    "question": "自由时差是多少？",
                    "question_type": "choice",
                    "options": {"A": "0天", "B": "1天", "C": "2天", "D": "3天"},
                    "correct_answer": "",
                    "explanation": "",
                    "grading_key": {
                        "correct_answer": "B",
                        "scoring_points": ["自由时差=紧后最早开始-本工作最早完成"],
                        "common_traps": [],
                        "source": "lightweight_batch_llm",
                    },
                }
            }
        ]
    }

    ctx = build_question_followup_context_from_result_summary(
        result_summary,
        rendered_response="自由时差是多少？",
        reveal_answers=False,
    )

    assert ctx is not None
    item = (ctx.get("items") or [])[0]
    assert item["correct_answer"] == "B"
    assert item["grading_key"]["correct_answer"] == "B"
    assert ctx["correct_answer"] == "B"


def test_redact_question_followup_context_for_public_strips_hidden_authority() -> None:
    from deeptutor.services.question_followup import (
        redact_question_followup_context_for_public,
    )

    ctx = {
        "question_id": "qs_1",
        "question": "Hello?",
        "correct_answer": "leak-should-be-removed",
        "explanation": "leak-should-be-removed",
        "items": [
            {
                "question_id": "q_1",
                "question": "Q1",
                "question_type": "choice",
                "options": {"A": "a", "B": "b"},
                "correct_answer": "A",
                "minimal_rationale": "hidden minimal rationale",
                "official_answer": "hidden official answer",
                "explanation": "leak",
                "grading_key": {"correct_answer": "A", "scoring_points": ["sp1"]},
                "scoring_points": ["should be redacted"],
            }
        ],
    }
    public = redact_question_followup_context_for_public(ctx)
    assert public is not None
    payload_blob = json.dumps(public, ensure_ascii=False)
    for forbidden in (
        "grading_key",
        "scoring_points",
        "correct_answer",
        "minimal_rationale",
        "official_answer",
        "hidden minimal rationale",
        "hidden official answer",
        "leak-should-be-removed",
        "leak",
    ):
        assert forbidden not in payload_blob, f"public payload must not leak {forbidden}"
    # 非禁字段保留
    assert public["question_id"] == "qs_1"
    assert public["items"][0]["question_id"] == "q_1"


def test_redact_question_followup_context_for_public_drops_nested_grading_result_authority() -> None:
    """plan §Phase 3 Step 3.2 — nested ``construction_grading_result.correct_answer``
    must be dropped from public payload too. Phase 2 redact_metadata fix covered the
    `/api/v1/ws` boundary; this guards the question_followup serializer that adapter /
    presentation layers consume directly."""

    from deeptutor.services.question_followup import (
        redact_question_followup_context_for_public,
    )

    ctx = {
        "question_id": "qs_2",
        "items": [
            {
                "question_id": "q_2",
                "question": "Q?",
                "question_type": "choice",
                "options": {"A": "a", "B": "b"},
                "is_correct": False,
                "construction_grading_result": {
                    "question_id": "q_2",
                    "user_answer": "A",
                    "correct_answer": "B",
                    "selected_options": ["A"],
                    "missed_options": ["B"],
                    "is_correct": False,
                    "evidence_refs": [
                        {"source": "doc1", "field": "stem", "content": "evidence-stem-content"}
                    ],
                },
            }
        ],
        "construction_grading_result": {
            "user_answer": "A",
            "correct_answer": "B",
            "scoring_points": ["sp"],
            "explanation": "leak-marker-outer",
        },
    }

    public = redact_question_followup_context_for_public(ctx)
    assert public is not None
    blob = json.dumps(public, ensure_ascii=False)
    for forbidden in ("correct_answer", "scoring_points", "explanation", "leak-marker-outer"):
        assert forbidden not in blob, f"nested grading_result still leaks {forbidden}"
    # Non-hidden grading_result fields survive (so adapter still gets diagnostic context)
    item_gr = public["items"][0]["construction_grading_result"]
    assert item_gr["user_answer"] == "A"
    assert item_gr["is_correct"] is False
    assert item_gr["selected_options"] == ["A"]


def test_redact_question_followup_context_for_public_drops_evidence_entry_with_hidden_field() -> None:
    """plan §Phase 3 Step 3.2 — evidence_refs[i] entries whose `field` slot
    references a hidden authority leak the standard answer via the sibling
    `value` / `content` slot. Drop the whole entry."""

    from deeptutor.services.question_followup import (
        redact_question_followup_context_for_public,
    )

    ctx = {
        "question_id": "qs_3",
        "items": [
            {
                "question_id": "q_3",
                "question": "Q?",
                "question_type": "choice",
                "options": {"A": "a", "B": "b"},
                "construction_grading_result": {
                    "user_answer": "A",
                    "evidence_refs": [
                        {"source": "qb", "field": "correct_answer", "value": "B"},
                        {"source": "qb", "field": "grading_key", "value": {"correct_answer": "B"}},
                        {"source": "qb", "field": "knowledge_point", "value": "安全管理"},
                        {"source": "qb", "source_field": "scoring_points", "value": ["sp"]},
                        {"source": "qb", "field": "article", "value": "GB-2021"},
                    ],
                    "rubric_items": [
                        {
                            "criterion": "C1",
                            "source_fields": ["explanation", "correct_answer", "stem"],
                            "evidence_text": "ok",
                        },
                        {
                            "criterion": "C2",
                            "source_fields": ["scoring_points", "explanation"],
                            "evidence_text": "all-hidden",
                        },
                    ],
                },
            }
        ],
    }
    public = redact_question_followup_context_for_public(ctx)
    assert public is not None
    blob = json.dumps(public, ensure_ascii=False)
    # Hidden fields and their sibling values are gone
    for forbidden in ('"correct_answer"', '"grading_key"', '"scoring_points"', '"explanation"'):
        assert forbidden not in blob, f"public payload still leaks {forbidden}"
    refs = public["items"][0]["construction_grading_result"]["evidence_refs"]
    # 3 entries with hidden field/source_field are dropped; 2 safe ones survive
    assert len(refs) == 2
    field_values = sorted(r["field"] for r in refs)
    assert field_values == ["article", "knowledge_point"]
    # rubric_items source_fields filtered, second one's slot dropped (all hidden)
    rubrics = public["items"][0]["construction_grading_result"]["rubric_items"]
    assert rubrics[0]["source_fields"] == ["stem"]
    assert "source_fields" not in rubrics[1]
    assert rubrics[1]["criterion"] == "C2"


def test_redact_question_followup_context_for_public_drops_pgo_official_answer_fields() -> None:
    """PGO shadow/contract payloads contain official answer verbatim slices.

    Those fields are internal grading authority and must not be projected into
    public question follow-up context, even when nested under a shadow result.
    """

    from deeptutor.services.question_followup import (
        redact_question_followup_context_for_public,
    )

    ctx = {
        "question_id": "case_1",
        "items": [
            {
                "question_id": "case_1_sub1",
                "pgo_shadow_result": {
                    "official_slice": "应由见证人员记录其取样、现场检测情况",
                    "atomic_official_slice": "应由见证人员记录其取样、现场检测情况",
                    "official_sub_answer_verbatim": "参考答案逐字片段",
                    "official_analysis": "官方解析逐字文本",
                    "term_provenance": [{"term": "见证记录", "chunk_id": "c1"}],
                    "flaw_span": "试验员如实记录了其取样",
                    "correction_span": "应由见证人员记录其取样",
                    "base_rule": "见证记录应由见证人员制作",
                    "exception_items": ["例外逐字文本"],
                    "evidence_refs": [
                        {"source": "pgo", "field": "official_slice", "value": "应由见证人员记录其取样"},
                        {"source": "pgo", "source_field": "pgo.atomic_official_slice", "content": "官方切片路径泄露"},
                        {"source": "student", "field": "student_evidence_span", "value": "学生写了见证人员记录"},
                    ],
                    "source_fields": ["pgo.atomic_official_slice", "stem"],
                    "student_evidence_span": "学生写了见证人员记录",
                },
            }
        ],
    }

    public = redact_question_followup_context_for_public(ctx)
    assert public is not None
    blob = json.dumps(public, ensure_ascii=False)

    for forbidden in (
        "official_slice",
        "atomic_official_slice",
        "official_sub_answer_verbatim",
        "official_analysis",
        "term_provenance",
        "flaw_span",
        "correction_span",
        "base_rule",
        "exception_items",
        "参考答案逐字片段",
        "官方解析逐字文本",
        "试验员如实记录",
        "官方切片路径泄露",
    ):
        assert forbidden not in blob, f"public followup leaked PGO authority field {forbidden}"
    result = public["items"][0]["pgo_shadow_result"]
    assert result["evidence_refs"] == [
        {"source": "student", "field": "student_evidence_span", "value": "学生写了见证人员记录"}
    ]
    assert result["source_fields"] == ["stem"]
    assert result["student_evidence_span"] == "学生写了见证人员记录"


def test_redact_question_followup_context_for_public_drops_grading_authority_fields() -> None:
    from deeptutor.services.question_followup import (
        redact_question_followup_context_for_public,
    )

    ctx = {
        "question_id": "qs_authority",
        "items": [
            {
                "question_id": "q_authority",
                "construction_grading_result": {
                    "quality_gates": {
                        "score_authority": "official_total_x_verdict_coverage",
                        "per_point_score_authority": "pending_calibration_not_official",
                        "answer_key_authority": "signed_registry_only",
                        "official_total_score_authority": "official_answer_verbatim",
                    },
                    "evidence_refs": [
                        {"field": "answer_key_authority", "value": "signed_registry_only"},
                        {"field": "public_status", "value": "ok"},
                    ],
                    "source_fields": ["answer_key_authority", "public_status"],
                    "public_status": "ok",
                },
            }
        ],
    }

    public = redact_question_followup_context_for_public(ctx)
    assert public is not None
    blob = json.dumps(public, ensure_ascii=False)
    for forbidden in (
        "score_authority",
        "per_point_score_authority",
        "answer_key_authority",
        "official_total_score_authority",
        "official_answer_verbatim",
        "signed_registry_only",
    ):
        assert forbidden not in blob
    result = public["items"][0]["construction_grading_result"]
    assert result["public_status"] == "ok"
    assert result["evidence_refs"] == [{"field": "public_status", "value": "ok"}]
    assert result["source_fields"] == ["public_status"]


def _mcq_ctx() -> dict:
    return {
        "question_id": "q_active_mcq",
        "question": "下列属于垂直运输设备的是？",
        "question_type": "single_choice",
        "options": {"A": "手推车", "B": "井架", "C": "搅拌车", "D": "布料机"},
        "correct_answer": "B",
    }


def test_resolve_submission_attempt_generation_request_is_not_a_submission() -> None:
    # Bug#1 次因 regression: with an active MCQ, a NEW-question / switch request must
    # NOT be mined into an option submission (otherwise a fabricated "你选了A" grading
    # turn fires on a turn where the learner never answered).
    for msg in (
        "再出一道SMA沥青混合料的选择题",
        "换一道真正SMA沥青混合料的题",
        "出一道深基坑支护的单选题",
    ):
        _target, submission = resolve_submission_attempt(msg, _mcq_ctx())
        assert submission is None, f"generation/switch request wrongly graded: {msg!r}"


def test_resolve_submission_attempt_mixed_answer_then_generation_keeps_submission() -> None:
    # §5.1 red line: a turn that LEADS with an explicit answer still submits, even
    # though it also asks for more questions.
    _target, submission = resolve_submission_attempt("我选A，再出3题", _mcq_ctx())
    assert submission is not None
