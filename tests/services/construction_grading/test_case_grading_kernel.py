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


def test_case_kernel_shadow_artifact_path_keeps_legacy_score_and_adds_point_matches() -> None:
    artifact = {
        "version_id": "qga_v0_20260604",
        "status": "published",
        "quality_gates": {"source_refs_verified_rate": 1.0},
        "scoring_points": [
            {
                "point_id": "P1",
                "label": "应组织专家论证",
                "max_score": 2,
                "policy_type": "semantic_allowed",
                "required_terms": ["专家论证"],
            },
            {
                "point_id": "P2",
                "label": "应进行安全技术交底",
                "max_score": 1,
                "policy_type": "exact_required",
                "required_terms": ["安全技术交底"],
            },
        ],
    }
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "Q1-NA", "node_code": "1A432000"},
        user_answer="需要组织专家论证，并进行安全技术交底。",
        grading_key={
            "scoring_points": [
                {"criterion": "专家论证", "keywords": ["专家论证"], "score": 1},
            ]
        },
        artifact_shadow=True,
        grading_artifact=artifact,
        artifact_judge_fn=lambda point, answer: {"status": "hit", "evidence_span": answer}
        if point["point_id"] in {"P1", "P2"}
        else {"status": "miss"},
    ).to_dict()

    assert result["score_awarded"] == 1
    assert result["rubric_items"][0]["criterion"] == "专家论证"
    shadow = result["luban_m35_artifact_shadow"]
    assert shadow["artifact_version"] == "qga_v0_20260604"
    assert shadow["legacy_artifact_status"] == "published"
    assert shadow["m35_runtime_status"] == "release_candidate"
    assert shadow["point_matches"]
    assert shadow["point_matches"][0]["point_id"] == "P1"
    assert shadow["official_score_allowed"] is False
    assert shadow["source_validity"] == 1.0


def test_case_kernel_shadow_artifact_missing_falls_back_to_legacy_only() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "Q-missing", "node_code": "1A432000"},
        user_answer="需要组织专家论证。",
        grading_key={
            "scoring_points": [
                {"criterion": "专家论证", "keywords": ["专家论证"], "score": 1},
            ]
        },
        artifact_shadow=True,
        grading_artifact={"artifact_missing": True, "case_id": "Q-missing"},
        artifact_judge_fn=lambda _point, _answer: {"status": "hit"},
    ).to_dict()

    assert result["score_awarded"] == 1
    assert result["max_score"] == 1
    assert "luban_m35_artifact_shadow" not in result


def test_case_kernel_shadow_failure_falls_back_to_legacy_only() -> None:
    def broken_judge(_point: dict[str, object], _answer: str) -> dict[str, object]:
        raise RuntimeError("judge unavailable")

    result = CaseGradingSkillKernel().grade(
        question_row={"id": "Q-fail-closed", "node_code": "1A432000"},
        user_answer="需要组织专家论证。",
        grading_key={
            "scoring_points": [
                {"criterion": "专家论证", "keywords": ["专家论证"], "score": 1},
            ]
        },
        artifact_shadow=True,
        grading_artifact={
            "version_id": "qga_v0_20260604",
            "status": "published",
            "scoring_points": [
                {
                    "point_id": "P1",
                    "label": "应组织专家论证",
                    "max_score": 1,
                    "policy_type": "semantic_allowed",
                }
            ],
        },
        artifact_judge_fn=broken_judge,
    ).to_dict()

    assert result["score_awarded"] == 1
    assert "luban_m35_artifact_shadow" not in result


def test_case_kernel_blocked_or_polluted_artifact_falls_back_to_legacy_only() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "Q-blocked", "node_code": "1A432000"},
        user_answer="需要组织专家论证。",
        grading_key={
            "scoring_points": [
                {"criterion": "专家论证", "keywords": ["专家论证"], "score": 1},
            ]
        },
        artifact_shadow=True,
        grading_artifact={
            "version_id": "qga_v0_20260604",
            "status": "blocked",
            "quality_gates": {
                "score_sum_ok": False,
                "source_pollution_count": 1,
                "blocked_reasons": ["source_pollution"],
            },
            "scoring_points": [
                {
                    "point_id": "P1",
                    "label": "应组织专家论证",
                    "max_score": 1,
                    "policy_type": "semantic_allowed",
                }
            ],
        },
        artifact_judge_fn=lambda _point, _answer: {"status": "hit"},
    ).to_dict()

    assert result["score_awarded"] == 1
    assert "luban_m35_artifact_shadow" not in result


def test_case_kernel_shadow_off_never_calls_artifact_judge() -> None:
    def forbidden_judge(_point: dict[str, object], _answer: str) -> dict[str, object]:
        raise AssertionError("shadow judge should not run when artifact_shadow is false")

    result = CaseGradingSkillKernel().grade(
        question_row={"id": "Q-shadow-off", "node_code": "1A432000"},
        user_answer="需要组织专家论证。",
        grading_key={
            "scoring_points": [
                {"criterion": "专家论证", "keywords": ["专家论证"], "score": 1},
            ]
        },
        artifact_shadow=False,
        grading_artifact={
            "version_id": "qga_v0_20260604",
            "status": "published",
            "scoring_points": [
                {
                    "point_id": "P1",
                    "label": "应组织专家论证",
                    "max_score": 1,
                    "policy_type": "semantic_allowed",
                }
            ],
        },
        artifact_judge_fn=forbidden_judge,
    ).to_dict()

    assert result["score_awarded"] == 1
    assert "luban_m35_artifact_shadow" not in result


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


# ─────────────────────────────────────────────────────────────────────────────
# Batch D.2 / Gap 2 — grading_key.scoring_points 优先 + open_skill 标记
# ─────────────────────────────────────────────────────────────────────────────


def test_case_grading_prefers_grading_key_scoring_points_over_row_rubric() -> None:
    from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel

    kernel = CaseGradingSkillKernel()
    row = {
        "id": "case_legacy_1",
        "node_code": "1A431000",
        "grading_rubric": [{"criterion": "旧采分点", "keywords": ["旧"], "score": 1}],
        "testing_focus": "专项方案",
    }
    grading_key = {
        "scoring_points": [
            {"criterion": "专项方案审批程序", "keywords": ["专项方案", "审批"], "score": 1},
            "专家论证",
        ]
    }
    user_answer = "专项方案审批专家论证"
    result = kernel.grade(question_row=row, user_answer=user_answer, grading_key=grading_key)
    assert result.grading_mode == "curated_rubric"
    assert result.next_training_signal["grading_source"] == "grading_key"
    assert result.next_training_signal["case_grading_mode"] == "curated_rubric"
    criteria = [item.criterion for item in result.rubric_items]
    assert "专项方案审批程序" in criteria
    assert "专家论证" in criteria


def test_case_grading_falls_back_to_questions_bank_when_grading_key_absent() -> None:
    from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel

    kernel = CaseGradingSkillKernel()
    row = {
        "id": "case_legacy_2",
        "node_code": "1A431000",
        "grading_rubric": [{"criterion": "专项方案审批", "keywords": ["审批"], "score": 1}],
    }
    result = kernel.grade(question_row=row, user_answer="审批", grading_key=None)
    assert result.next_training_signal["grading_source"] == "questions_bank"
    assert result.grading_mode == "curated_rubric"


def test_case_grading_marks_open_skill_when_no_authority_available() -> None:
    from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel

    kernel = CaseGradingSkillKernel()
    row = {"id": "case_open_1", "node_code": "1A431000"}
    result = kernel.grade(question_row=row, user_answer="任意作答", grading_key=None)
    # 既无 grading_key 也无 grading_rubric，projected 也空 → open_skill
    assert result.grading_mode == "open_skill"
    assert result.next_training_signal["grading_source"] == "open_skill_fallback"
    assert result.next_training_signal["case_grading_mode"] == "open_skill"


def test_grading_key_matches_official_term_punctuation_variants_only() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "case-official-term-normalization", "node_code": "1A432000"},
        user_answer="分期分批实施工程的开、竣工日期及工期一览表",
        grading_key={
            "scoring_points": [
                {
                    "criterion": "P1::分期(分批)实施工程的开、竣工日期及工期一览表",
                    "keywords": ["分期(分批)实施工程的开、竣工日期及工期一览表"],
                    "score": 1,
                }
            ]
        },
    )

    assert result.score_awarded == 1
    assert result.rubric_items[0].status == "full"
    assert result.rubric_items[0].keywords == ["分期(分批)实施工程的开、竣工日期及工期一览表"]


def test_grading_key_normalization_does_not_expand_synonyms() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "case-no-synonyms", "node_code": "1A432000"},
        user_answer="施工单位应诚信经营。",
        grading_key={
            "scoring_points": [
                {
                    "criterion": "P1::诚实信用",
                    "keywords": ["诚实信用"],
                    "score": 1,
                }
            ]
        },
    )

    assert result.score_awarded == 0
    assert result.rubric_items[0].status == "miss"


def test_grading_key_matches_official_slash_variants_without_synonyms() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "case-slash-variant", "node_code": "1A412000"},
        user_answer="受压接头可不受限制。",
        grading_key={
            "scoring_points": [
                {
                    "criterion": "P1::受压接头(可)不受限制/无限制",
                    "keywords": ["受压接头(可)不受限制/无限制"],
                    "score": 1,
                }
            ]
        },
    )

    assert result.score_awarded == 1
    assert result.rubric_items[0].status == "full"


def test_grading_key_multi_answer_penalty_zeroes_scoped_points_only() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "case-penalty", "node_code": "1A434000"},
        user_answer=(
            "不妥:试验员制作见证记录;不妥:总包支付检测费;"
            "不妥:检测委托单由试验员填报;不妥:建设单位委托检测机构。"
            "见证记录还包括取样、制样、标识、封志、送检、现场检测。"
        ),
        grading_key={
            "scoring_points": [
                {"criterion": "P1::见证人员", "keywords": ["见证人员"], "score": 2},
                {"criterion": "P2::建设单位", "keywords": ["建设单位"], "score": 2},
                {"criterion": "P3::现场检测", "keywords": ["现场检测"], "score": 3},
            ],
            "penalty_rules": [
                {
                    "rule_id": "multi_answer_no_score",
                    "type": "multi_answer_no_score",
                    "trigger": {"max_answered_items": 2, "pattern": "不妥"},
                    "zero_point_ids": ["P1", "P2"],
                }
            ],
        },
    )

    awarded_by_criterion = {item.criterion: item.awarded_score for item in result.rubric_items}
    assert awarded_by_criterion["P1::见证人员"] == 0
    assert awarded_by_criterion["P2::建设单位"] == 0
    assert awarded_by_criterion["P3::现场检测"] == 3
    assert result.score_awarded == 3
    assert result.next_training_signal["penalty_rules_applied"] == ["multi_answer_no_score"]


def test_grading_key_rejects_overbroad_compiled_terms() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "case-overmatch", "node_code": "1A432000"},
        user_answer="总包合同实施管理的原则有质量第一原则、安全生产原则、进度控制原则。",
        grading_key={
            "scoring_points": [
                {
                    "criterion": "P2::原则",
                    "keywords": ["原则"],
                    "score": 2.4,
                }
            ]
        },
    )

    assert result.score_awarded == 0
    assert result.rubric_items[0].status == "miss"


def test_grading_key_answer_label_prevents_fill_blank_cross_match() -> None:
    result = CaseGradingSkillKernel().grade(
        question_row={"id": "case-fill-blank", "node_code": "1A422000"},
        user_answer="A：禁止。B：限制。",
        grading_key={
            "scoring_points": [
                {
                    "criterion": "P1::限制",
                    "keywords": ["限制"],
                    "score": 1,
                    "answer_label": "A",
                },
                {
                    "criterion": "P2::禁止",
                    "keywords": ["禁止"],
                    "score": 1,
                    "answer_label": "B",
                },
            ]
        },
    )

    assert result.score_awarded == 0
    assert [item.status for item in result.rubric_items] == ["miss", "miss"]
