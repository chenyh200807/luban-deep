from __future__ import annotations

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel


def test_case_kernel_projects_rubric_from_existing_question_bank_fields() -> None:
    row = {
        "id": 8243,
        "question_type": "case_study",
        "question_stem": "指出危大工程专项方案管理的不妥之处。",
        "correct_answer": "应编制专项施工方案；超过一定规模应组织专家论证；实施前应进行安全技术交底。",
        "analysis": "这类题按方案编制、审核审批、专家论证、交底、实施检查验收链条得分。",
        "grading_keywords": ["专项施工方案", "专家论证", "安全技术交底"],
        "structured_rules": [
            {
                "condition": "模板支撑高度 >= 8m",
                "requirement": "需编制专项施工方案并专家论证",
            }
        ],
        "testing_focus": "危大工程专项方案流程",
        "node_code": "1A432000",
        "source_meta": {"source": "2025一建《建筑实务》电子教材"},
    }
    evidence_rows = [
        {
            "source": "kb_chunks",
            "field": "metadata.exam_matrix",
            "text": "危大工程应按方案、审批、论证、交底、验收闭环作答。",
        },
        {
            "source": "standard_articles",
            "field": "logic_constraints",
            "text": "超过一定规模危大工程专项施工方案应组织专家论证。",
        },
    ]

    result = CaseGradingSkillKernel().grade(
        question_row=row,
        user_answer="施工单位应编制专项施工方案，并加强现场管理。",
        evidence_rows=evidence_rows,
    )

    assert result.grading_mode == "projected_rubric"
    assert result.max_score >= 3
    assert result.score_awarded == 1.0
    assert [item.status for item in result.rubric_items].count("miss") >= 2
    assert any(ref.source == "questions_bank" and ref.field == "grading_keywords" for ref in result.evidence_refs)
    assert any(ref.source == "kb_chunks" for ref in result.evidence_refs)
    assert any(ref.source == "standard_articles" for ref in result.evidence_refs)
    assert any(event.error_code == "E02" for event in result.error_events)
    assert any(event.error_code == "E04" for event in result.error_events)
    assert result.next_training_signal["concept"] == "1A432000"


def test_case_kernel_uses_curated_rubric_when_available() -> None:
    row = {
        "id": "case-1",
        "question_type": "case_study",
        "grading_rubric": [
            {
                "criterion": "应组织专家论证",
                "score": 2,
                "keywords": ["专家论证"],
                "required_meaning": "超过一定规模危大工程专项方案应专家论证",
            }
        ],
        "correct_answer": "应组织专家论证。",
    }

    result = CaseGradingSkillKernel().grade(
        question_row=row,
        user_answer="超过一定规模危大工程应组织专家论证。",
    )

    assert result.grading_mode == "curated_rubric"
    assert result.max_score == 2
    assert result.score_awarded == 2
    assert result.rubric_items[0].status == "full"
