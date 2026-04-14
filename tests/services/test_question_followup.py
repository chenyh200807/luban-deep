from __future__ import annotations

from deeptutor.services.question_followup import (
    build_question_followup_context_from_summary,
    detect_answer_reveal_preference,
    detect_requested_question_type,
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


def test_build_question_followup_context_from_summary_keeps_all_items() -> None:
    context = build_question_followup_context_from_summary(
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
