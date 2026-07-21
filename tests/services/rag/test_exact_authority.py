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


def test_build_exact_authority_response_honors_explicit_brief_mcq_request() -> None:
    response = build_exact_authority_response(
        {
            "answer_kind": "mcq",
            "stem": "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（　　）。",
            "options": [
                {"key": "A", "value": "1%"},
                {"key": "B", "value": "2%"},
                {"key": "C", "value": "3%"},
                {"key": "D", "value": "5%"},
            ],
            "correct_answer": "D",
            "analysis": "屋面最小坡度：压型金属板：5%。",
        },
        user_message="别展开，一句话告诉我，我选C对不对。",
    )

    assert response == "不对，标准答案是 D（D. 5%），题库解析依据是：屋面最小坡度：压型金属板：5%。"
    assert "##" not in response
    assert "下一步建议" not in response


def test_build_exact_authority_response_honors_do_not_review_whole_question() -> None:
    response = build_exact_authority_response(
        {
            "answer_kind": "mcq",
            "stem": "地下连续墙施工质量控制，下列说法正确的有？",
            "options": [
                {"key": "A", "value": "槽段长度8-10m"},
                {"key": "B", "value": "导墙高度1.0m"},
                {"key": "C", "value": "现浇钢筋混凝土导墙"},
                {"key": "D", "value": "导管法连续浇筑混凝土"},
                {"key": "E", "value": "设计强度后墙底注浆"},
            ],
            "correct_answer": "CDE",
            "analysis": "A 错误；地下连续墙单元槽段长度宜为 4～6m。B 错误；导墙高度应≥1.2m。",
        },
        user_message="我实际选的是ACDE，对吗？别讲全题。",
    )

    assert response.startswith("不对，标准答案是 CDE")
    assert "题库解析依据是" in response
    assert "##" not in response
    assert "下一步建议" not in response


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

    # 方法脚手架 topic-agnostic：只从本题字段派生，不假设数值形态、不硬编码保护层。
    assert notes["scoring_points"] == [
        "圈定题干限定的对象与条件：一般环境中，直接接触土体浇筑的构件，其钢筋的混凝土保护层厚度不应小于（ ）mm。",
        "对照题库标准答案锁定关键依据：D. 70。",
        "逐项比对题库解析，排除与之不符的干扰项。",
    ]
    assert notes["pitfalls"] == [
        "被表述相近的干扰项带走，忽略题干限定的对象与条件。",
        "只记住结论本身，没有回到题库解析里的判定依据。",
    ]
    assert notes["mnemonic"] == "先圈对象与条件，再对照题库答案：D. 70。"
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


def test_build_mcq_review_notes_has_no_cross_topic_leak_on_conceptual_question() -> None:
    """回归证伪:概念题(立杆严禁搭接,非数值/非保护层题)的方法脚手架里,绝不能出现
    上一版硬编码进 pitfalls/mnemonic 的“保护层厚度 / 直接接土 / 规范数值”字面量——
    那是通用投影器把单一题型假设跨题泄露的病。脚手架应只引用本题自身字段。"""
    notes = build_mcq_review_notes_from_exact_question(
        {
            "answer_kind": "mcq",
            "stem": "关于模板支撑立杆的连接方式，下列说法正确的是（ ）。",
            "options": {
                "A": "立杆可以采用搭接，搭接长度不小于500mm。",
                "B": "立杆必须采用对接或套接，严禁搭接。",
                "C": "立杆搭接与水平杆要求一致。",
                "D": "立杆连接方式不影响承载力。",
            },
            "correct_answer": "B",
            "analysis": "模板支撑立杆必须采用对接或套接，严禁搭接；搭接仅适用于水平杆等非承重杆件。",
        }
    )

    scaffold_text = " ".join(notes["scoring_points"] + notes["pitfalls"] + [notes["mnemonic"]])
    for leaked in ("保护层", "直接接土", "直接接触土体", "规范数值", "干扰数值"):
        assert leaked not in scaffold_text, f"跨题泄露的硬编码字面量: {leaked}"
    # 脚手架必须引用本题的标准答案(topic-faithful),而非别题模板。
    assert "B. 立杆必须采用对接或套接，严禁搭接。" in notes["mnemonic"]
    assert notes["option_analysis"][1]["verdict"] == "正确"


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
