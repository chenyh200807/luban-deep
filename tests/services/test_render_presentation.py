from __future__ import annotations

from deeptutor.services.render_presentation import (
    build_canonical_presentation,
    build_mcq_block_from_result_summary,
)


def _choice_summary() -> dict:
    return {
        "results": [
            {
                "qa_pair": {
                    "question_id": "q_1",
                    "question": "某防水工程题目",
                    "question_type": "choice",
                    "options": {
                        "A": "方案A",
                        "B": "方案B",
                    },
                    "correct_answer": "B",
                    "explanation": "B 更符合规范。",
                    "difficulty": "medium",
                    "concentration": "地下防水",
                }
            }
        ]
    }


def test_build_mcq_block_from_result_summary_returns_structured_questions() -> None:
    block = build_mcq_block_from_result_summary(_choice_summary())
    assert block is not None
    assert block["type"] == "mcq"
    assert block["questions"][0]["question_id"] == "q_1"
    assert block["questions"][0]["options"][1]["key"] == "B"
    assert block["questions"][0]["followup_context"]["correct_answer"] == "B"


def test_build_mcq_block_from_result_summary_uses_metadata_knowledge_context_when_explanation_omitted() -> None:
    summary = _choice_summary()
    summary["results"][0]["qa_pair"]["explanation"] = ""
    summary["results"][0]["qa_pair"]["metadata"] = {"knowledge_context": "网络计划里自由时差只看不影响紧后最早开始的余量。"}

    block = build_mcq_block_from_result_summary(summary)

    assert block is not None
    assert (
        block["questions"][0]["followup_context"]["knowledge_context"]
        == "网络计划里自由时差只看不影响紧后最早开始的余量。"
    )


def test_build_canonical_presentation_wraps_blocks_and_fallback_text() -> None:
    presentation = build_canonical_presentation(
        content="### Question 1\n某防水工程题目",
        result_summary=_choice_summary(),
    )
    assert presentation is not None
    assert presentation["blocks"][0]["type"] == "mcq"
    assert presentation["fallback_text"].startswith("### Question 1")
    assert presentation["meta"]["streamingMode"] == "block_finalized"


def test_build_canonical_presentation_normalizes_structured_blocks_and_filters_invalid_blocks() -> None:
    presentation = build_canonical_presentation(
        content="教学内容",
        result_summary=_choice_summary(),
        blocks=[
            {
                "type": "table",
                "headers": [
                    "列1",
                    {"text": "列2", "align": "center", "highlight": True},
                ],
                "rows": [
                    ["A1", "A2"],
                    [
                        {"text": "B1", "align": "right"},
                        "B2",
                    ],
                ],
                "caption": "  结构化表格  ",
                "mobile_strategy": "compact_cards",
            },
            {
                "type": "formula_block",
                "latex": "x^2+1",
                "display_text": "x²+1",
                "svg_url": "https://example.com/formula.svg",
                "copy_text": "x^2+1",
            },
            {
                "type": "formula_inline",
                "latex": "a+b",
            },
            {
                "type": "mcq",
                "questions": [
                    {
                        "index": 1,
                        "stem": "请选择正确选项",
                        "question_type": "single_choice",
                        "options": [
                            {"key": "A", "text": "方案A"},
                            {"key": "B", "text": "方案B"},
                        ],
                        "question_id": "q_raw",
                    }
                ],
                "submit_hint": "请选择后提交答案",
                "receipt": "",
                "review_mode": False,
            },
            {"type": "table", "headers": [], "rows": []},
            {"type": "formula_block"},
            {"type": "unknown", "text": "drop me"},
        ],
    )
    assert presentation is not None
    assert [block["type"] for block in presentation["blocks"]] == [
        "table",
        "formula_block",
        "formula_inline",
        "mcq",
    ]

    table_block = presentation["blocks"][0]
    assert table_block["headers"][1]["align"] == "center"
    assert table_block["headers"][1]["highlight"] is True
    assert table_block["rows"][1][0]["align"] == "right"
    assert table_block["caption"] == "结构化表格"
    assert table_block["mobile_strategy"] == "compact_cards"

    formula_block = presentation["blocks"][1]
    assert formula_block["latex"] == "x^2+1"
    assert formula_block["display_text"] == "x²+1"
    assert formula_block["svg_url"] == "https://example.com/formula.svg"
    assert formula_block["copy_text"] == "x^2+1"

    inline_formula_block = presentation["blocks"][2]
    assert inline_formula_block["type"] == "formula_inline"
    assert inline_formula_block["display_text"] == "a+b"
    assert inline_formula_block["copy_text"] == "a+b"
    assert len([block for block in presentation["blocks"] if block["type"] == "mcq"]) == 1


def test_build_canonical_presentation_normalizes_steps_recap_and_chart_blocks() -> None:
    presentation = build_canonical_presentation(
        content="教学内容",
        blocks=[
            {
                "type": "steps",
                "title": "解题步骤",
                "style": "ordered",
                "items": [
                    "先整理条件",
                    {
                        "index": 4,
                        "text": "列出已知量",
                        "detail": "标出单位",
                        "status": "doing",
                    },
                ],
            },
            {
                "type": "recap",
                "title": "本节课总结",
                "summary": "先结构化，再渲染。",
                "bullets": ["步骤要稳定", "总结要轻量"],
            },
            {
                "type": "chart",
                "chart_type": "line",
                "title": "趋势图",
                "caption": "数据变化趋势",
                "series": [
                    {
                        "name": "A组",
                        "type": "line",
                        "data": [1, 2, 3],
                        "color": "red",
                    }
                ],
                "axes": {
                    "x": {
                        "label": "时间",
                        "categories": ["第一周", "第二周"],
                    },
                    "y": {
                        "label": "数量",
                        "unit": "个",
                        "min": 0,
                        "max": 3,
                    },
                },
                "legend": {
                    "show": True,
                    "position": "top",
                    "labels": ["A组"],
                },
                "summary": "趋势说明",
            },
        ],
    )

    assert presentation is not None
    assert [block["type"] for block in presentation["blocks"]] == ["steps", "recap", "chart"]

    steps_block = presentation["blocks"][0]
    assert steps_block["title"] == "解题步骤"
    assert steps_block["style"] == "ordered"
    assert steps_block["steps"][0]["index"] == 1
    assert steps_block["steps"][0]["title"] == "先整理条件"
    assert steps_block["steps"][1]["index"] == 4
    assert steps_block["steps"][1]["detail"] == "标出单位"
    assert steps_block["steps"][1]["status"] == "doing"

    recap_block = presentation["blocks"][1]
    assert recap_block["title"] == "本节课总结"
    assert recap_block["summary"] == "先结构化，再渲染。"
    assert recap_block["bullets"] == ["步骤要稳定", "总结要轻量"]

    chart_block = presentation["blocks"][2]
    assert chart_block["chart_type"] == "line"
    assert chart_block["title"] == "趋势图"
    assert chart_block["series"][0]["name"] == "A组"
    assert chart_block["series"][0]["data"] == [1, 2, 3]
    assert chart_block["axes"]["x"]["categories"] == ["第一周", "第二周"]
    assert chart_block["legend"]["position"] == "top"
    assert chart_block["summary"] == "趋势说明"


def test_build_canonical_presentation_preserves_chart_fallback_table_without_main_chart_fields() -> None:
    presentation = build_canonical_presentation(
        content="教学内容",
        blocks=[
            {
                "type": "chart",
                "fallback_table": {
                    "headers": [
                        {"text": "阶段"},
                        {"text": "数值"},
                    ],
                    "rows": [
                        ["第一周", "10"],
                        ["第二周", "12"],
                    ],
                },
                "summary": "没有主图时仍保留表格信息",
            }
        ],
    )

    assert presentation is not None
    assert presentation["blocks"][0]["type"] == "chart"
    assert presentation["blocks"][0]["chart_type"] == ""
    assert presentation["blocks"][0]["fallback_table"]["headers"][0]["text"] == "阶段"
    assert presentation["blocks"][0]["fallback_table"]["rows"][1][1]["text"] == "12"
    assert presentation["blocks"][0]["summary"] == "没有主图时仍保留表格信息"


def test_build_canonical_presentation_does_not_guess_steps_or_chart_from_plain_text() -> None:
    presentation = build_canonical_presentation(
        content="教学内容",
        blocks=[
            {
                "type": "steps",
                "text": "只是一段说明，不是结构化步骤",
            },
            {
                "type": "chart",
                "text": "只是一段说明，不是结构化图表",
            },
        ],
    )

    assert presentation is None


def test_build_canonical_presentation_normalizes_legacy_summary_alias_to_recap() -> None:
    presentation = build_canonical_presentation(
        content="总结",
        blocks=[
            {
                "type": "summary",
                "text": "本节课总结",
            }
        ],
    )

    assert presentation is not None
    assert presentation["blocks"] == [
        {
            "type": "recap",
            "schema_version": 1,
            "title": "教学总结",
            "summary": "本节课总结",
        }
    ]
