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


def test_case_kernel_demotes_drifted_grading_keywords_to_answer_authority() -> None:
    row = {
        "id": 9006,
        "question_type": "case_study",
        "question_stem": "指出装修阶段施工用电专项安全检查中的不妥之处，并写出正确做法。",
        "correct_answer": (
            "不妥之处：① 仅按项目临时用电施工组织设计进行施工用电管理；"
            "② 现场瓷砖切割机与砂浆搅拌机共用一个开关箱；"
            "③ 主教学楼一开关箱使用插座插头与配电箱连接。"
            "正确做法：① 装饰装修施工阶段，应补充编制单项施工用电方案；"
            "② 用电设备必须配备专用的开关箱，严禁2台及以上用电设备共用一个开关箱；"
            "③ 配电箱、开关箱的电源进线端严禁采用插头和插座做活动连接。"
        ),
        "analysis": "装饰装修阶段需补充专项用电方案；每台设备应有独立开关箱；电源进线端严禁使用插头插座连接。",
        "grading_keywords": [
            "坠落高度超过2m的安装使用梯子攀登作业",
            "防护栏应为黑黄或红白相间的条纹标示",
            "操作平台",
        ],
        "testing_focus": "临时用电管理、开关箱配置、配电箱连接",
        "node_code": "1A436000",
    }

    result = CaseGradingSkillKernel().grade(
        question_row=row,
        user_answer="瓷砖切割机和砂浆搅拌机共用一个开关箱不妥，应分开设置。",
    )

    assert result.grading_mode == "projected_rubric"
    assert result.max_score == 3
    assert result.score_awarded == 1
    assert all("grading_keywords" not in item.source_fields for item in result.rubric_items)
    assert any("临时用电施工组织设计" in item.criterion for item in result.rubric_items)
    assert any("插座插头" in item.criterion for item in result.rubric_items)


def test_case_kernel_partial_trusted_keywords_do_not_replace_answer_rubric() -> None:
    row = {
        "id": "case-partial-keywords",
        "question_type": "case_study",
        "correct_answer": (
            "不妥之处：① 未编制临时用电施工组织设计；② 共用一个开关箱；③ 插座插头活动连接。"
            "正确做法：① 应编制单项施工用电方案；② 应采用专用开关箱；"
            "③ 插头和插座应配套使用，不得活动连接。"
        ),
        "analysis": "临时用电管理应从方案、开关箱、连接方式三个点判分。",
        "grading_keywords": ["共用一个开关箱"],
        "testing_focus": "临时用电管理",
        "node_code": "1A436000",
    }

    result = CaseGradingSkillKernel().grade(
        question_row=row,
        user_answer="共用一个开关箱不妥，应采用专用开关箱。",
    )

    assert result.grading_mode == "projected_rubric"
    assert result.max_score == 3
    assert result.score_awarded == 1
    assert len(result.rubric_items) == 3
