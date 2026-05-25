from __future__ import annotations

from deeptutor.services.rag.exact_authority import (
    build_exact_authority_response,
    build_mcq_review_notes_from_exact_question,
    exact_authority_response_matches,
    extract_exact_question_authority_from_metadata,
    normalize_exact_authority_display_text,
    resolve_exact_authority_response_from_authority,
    should_force_exact_authority,
)


def test_extract_exact_question_authority_normalizes_case_bundle() -> None:
    authority = extract_exact_question_authority_from_metadata(
        {
            "exact_question": {
                "answer_kind": "case_study",
                "case_bundle": {
                    "covered_subquestions": [
                        {
                            "display_index": "1",
                            "prompt": "Q1",
                            "authoritative_answer": "A1",
                        }
                    ],
                    "missing_subquestions": [],
                    "coverage_ratio": 1.0,
                    "coverage_state": "multi_subquestion_exact",
                },
            }
        }
    )

    assert authority is not None
    assert authority["authority_kind"] == "case_study"
    assert authority["covered_subquestions"][0]["authoritative_answer"] == "A1"
    assert authority["coverage_state"] == "multi_subquestion_exact"


def test_should_force_exact_authority_requires_full_case_coverage() -> None:
    assert should_force_exact_authority(
        {
            "answer_kind": "case_study",
            "covered_subquestions": [{"display_index": "1", "authoritative_answer": "A1"}],
            "missing_subquestions": [{"display_index": "2", "prompt": "Q2"}],
            "coverage_ratio": 0.5,
            "coverage_state": "single_subquestion_only",
        }
    ) is False
    assert should_force_exact_authority(
        {
            "answer_kind": "case_study",
            "covered_subquestions": [{"display_index": "1", "authoritative_answer": "A1"}],
            "missing_subquestions": [],
            "coverage_ratio": 1.0,
            "coverage_state": "multi_subquestion_exact",
        }
    ) is False
    assert should_force_exact_authority(
        {
            "answer_kind": "case_study",
            "covered_subquestions": [
                {"display_index": "2", "authoritative_answer": "A2"},
                {"display_index": "5", "authoritative_answer": "A5"},
            ],
            "missing_subquestions": [{"display_index": "1", "prompt": "Q1"}],
            "coverage_ratio": 0.4,
            "coverage_state": "multi_subquestion_exact",
            "query_subquestion_count": 5,
        }
    ) is False
    assert should_force_exact_authority({"answer_kind": "mcq", "correct_answer": "A"}) is True


def test_build_exact_authority_response_renders_mcq_as_learning_report() -> None:
    response = build_exact_authority_response(
        {
            "answer_kind": "mcq",
            "stem": "结构的可靠性包括（　　）",
            "options": [
                {"key": "A", "value": "稳定"},
                {"key": "B", "value": "安全性"},
                {"key": "C", "value": "耐久性"},
                {"key": "D", "value": "经济性"},
                {"key": "E", "value": "适用性"},
            ],
            "correct_answer": "BCE",
            "analysis": "结构的可靠性包括安全性、适用性、耐久性。",
        }
    )

    assert "## 📊 阅卷结论" in response
    assert "## 🧐 解析" in response
    assert "## ⚠️ 易错点" in response
    assert "## 🎯 核心要点" in response
    assert "## 🚀 下一步建议" in response
    assert "标准答案：BCE（B. 安全性、C. 耐久性、E. 适用性）" in response
    assert "结构的可靠性包括安全性、适用性、耐久性。" in response
    assert "安全性 + 耐久性 + 适用性" in response


def test_build_exact_authority_response_strips_internal_analysis_markers() -> None:
    response = build_exact_authority_response(
        {
            "answer_kind": "mcq",
            "stem": "结构的可靠性包括（　　）\n\nA.稳定\nB.安全性",
            "options": [
                {"key": "A", "value": "稳定"},
                {"key": "B", "value": "安全性"},
            ],
            "correct_answer": "B",
            "analysis": "【解析】结构的可靠性包括安全性。\n【选项分析】\nA. ✗ 稳定是安全性的一部分 [concept_confusion]\nB. ✓ 安全性正确",
        }
    )

    assert "[concept_confusion]" not in response
    assert "✓" not in response
    assert "✗" not in response
    assert "标准答案：B（B. 安全性）" in response
    assert "结构的可靠性包括安全性。" in response
    assert "| A. 稳定 | 稳定是安全性的一部分 |" in response


def test_build_mcq_review_notes_projects_exact_question_teaching_payload() -> None:
    notes = build_mcq_review_notes_from_exact_question(
        {
            "answer_kind": "mcq",
            "stem": "一般环境中，直接接触土体浇筑的构件，其钢筋的混凝土保护层厚度不应小于（ ）mm。",
            "options": {"A": "55", "B": "60", "C": "65", "D": "70"},
            "correct_answer": "D",
            "analysis": "直接接触土体浇筑的构件，其混凝土保护层厚度不应小于70mm。",
        }
    )

    assert notes["scoring_points"] == [
        "圈出题干对象：一般环境中，直接接触土体浇筑的构件，其钢筋的混凝土保护层厚度不应小于（ ）mm。",
        "抓住标准答案对应的规范数值：D. 70。",
        "逐项排除相近但不符合题库解析的干扰数值。",
    ]
    assert notes["pitfalls"] == [
        "把相近数值当成规范要求，忽略题干对象。",
        "只记住保护层厚度这一考点，没有锁定“直接接触土体浇筑的构件”。",
    ]
    assert notes["mnemonic"] == "直接接土先加厚，保护层记 70。"
    assert notes["option_analysis"][0] == {
        "key": "A",
        "verdict": "不正确",
        "analysis": "55 低于标准值 70，不能满足题干中的“不应小于”要求。",
    }
    assert notes["option_analysis"][-1] == {
        "key": "D",
        "verdict": "正确",
        "analysis": "70 对应题库标准答案；直接接触土体浇筑的构件，其混凝土保护层厚度不应小于70mm。",
    }


def test_normalize_exact_authority_display_text_unescapes_literal_newlines() -> None:
    assert normalize_exact_authority_display_text("结论。\\n理由：按题库解析。") == "结论。\n理由：按题库解析。"


def test_build_exact_authority_response_renders_case_as_markdown() -> None:
    response = build_exact_authority_response(
        {
            "answer_kind": "case_study",
            "covered_subquestions": [
                {
                    "display_index": "5",
                    "prompt": "分步骤列式计算钢结构装饰架的造价是多少万元？",
                    "authoritative_answer": "造价：3335.40 万元。\\n按清单计价汇总。",
                    "analysis": "【解析】注意税金基数包含规费。",
                }
            ],
        }
    )

    assert response.startswith("## 标准作答")
    assert "### 第5问" in response
    assert "3335.40 万元" in response
    assert "**采分点：**" in response
    assert "**易错点：**" in response
    assert "## 记忆口诀" in response
    assert "【解析】" not in response
    assert "\\n" not in response


def test_exact_authority_response_matches_requires_authoritative_answer_and_values() -> None:
    exact_question = {
        "answer_kind": "mcq",
        "correct_answer": "BCE",
        "options": [
            {"key": "A", "value": "稳定"},
            {"key": "B", "value": "安全性"},
            {"key": "C", "value": "耐久性"},
            {"key": "D", "value": "经济性"},
            {"key": "E", "value": "适用性"},
        ],
    }

    assert exact_authority_response_matches(
        exact_question,
        "这题考结构可靠性的三项要求。\n标准答案：B、C、E。\nB 安全性、C 耐久性、E 适用性都属于可靠性要求。",
    )
    assert exact_authority_response_matches(
        exact_question,
        (
            "## 📊 阅卷结论\n"
            "标准答案：BCE（B. 安全性、C. 耐久性、E. 适用性）。\n\n"
            "## 🧐 解析\n结构的可靠性包括安全性、适用性、耐久性。\n\n"
            "## ⚠️ 易错点\nA 稳定不是独立可靠性指标；D 经济性不是可靠性指标。\n\n"
            "## 🎯 核心要点\nB 安全性、C 耐久性、E 适用性。\n\n"
            "## 🚀 下一步建议\n再做 1 道同类题。"
        ),
    )
    assert not exact_authority_response_matches(
        exact_question,
        "这题答案容易误选。\n标准答案：A、B、C、E。\n安全性、耐久性、适用性都要关注。",
    )
    assert not exact_authority_response_matches(
        exact_question,
        "这题考结构可靠性。\n标准答案：B、C、E。\n安全性和耐久性都属于可靠性要求。",
    )
    assert not exact_authority_response_matches(
        exact_question,
        (
            "题干：结构的可靠性包括（　　）\n选项：A 稳定 B 安全性 C 耐久性 D 经济性 E 适用性\n"
            "标准答案：B、C、E。\n"
            "这道题考查的是对结构可靠性的深入理解。在工程上，结构的可靠性不仅涉及承载能力，"
            "还可能涉及偶然事件、裂缝宽度、挠度控制、钢筋锈蚀、混凝土碳化、造价管理、"
            "长期维护策略和多种施工条件下的综合判断，因此需要从完整工程生命周期展开分析。"
        ),
    )


def test_resolve_exact_authority_response_does_not_terminal_render_case() -> None:
    assert (
        resolve_exact_authority_response_from_authority(
            {
                "authority_kind": "case_study",
                "covered_subquestions": [
                    {"display_index": "1", "authoritative_answer": "A1"},
                    {"display_index": "2", "authoritative_answer": "A2"},
                ],
                "missing_subquestions": [],
                "coverage_ratio": 1.0,
            }
        )
        is None
    )
    assert (
        resolve_exact_authority_response_from_authority(
            {
                "authority_kind": "case_study",
                "covered_subquestions": [{"display_index": "1", "authoritative_answer": "A1"}],
                "missing_subquestions": [{"display_index": "2", "prompt": "Q2"}],
                "coverage_ratio": 0.5,
            }
        )
        is None
    )
