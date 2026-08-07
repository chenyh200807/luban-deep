from __future__ import annotations

from deeptutor.services.assessment.blueprint import ability_dimensions_by_section
from deeptutor.services.assessment.report_read_model import (
    build_pass_readiness_report,
    build_result_report,
)


NOW = "2026-08-05T12:00:00Z"

_SECTION_PLAN = [
    ("pr_objective_single", 2),
    ("pr_objective_multi", 2),
    ("pr_case_safety", 2),
    ("pr_case_schedule", 2),
    ("pr_case_quality", 2),
    ("pr_answer_discrimination", 1),
    ("pr_scoring_point_recognition", 1),
]


def _scored_result(*, wrong_question_ids: set[str] | None = None) -> dict:
    wrong = wrong_question_ids or set()
    items = []
    index = 0
    for section_id, count in _SECTION_PLAN:
        for _ in range(count):
            index += 1
            question_id = f"q{index:02d}"
            is_correct = question_id not in wrong
            items.append(
                {
                    "question_id": question_id,
                    "source_question_id": f"src_{question_id}",
                    "question_stem": f"题干 {question_id}",
                    "question_type": "single_choice",
                    "section_id": section_id,
                    "section_label": section_id,
                    "learner_answer": "A",
                    "correct_answer": "A" if is_correct else "B",
                    "is_correct": is_correct,
                    "is_blank": False,
                    "flags": [],
                    "knowledge_points": [f"考点 {question_id}"],
                    "simple_explanation": "解析",
                    "error_codes": [] if is_correct else ["M01"],
                    "measurement_confidence": "medium",
                }
            )
    correct_count = sum(1 for item in items if item["is_correct"])
    return {
        "score_summary": {
            "score_pct": round(correct_count / len(items) * 100),
            "correct_count": correct_count,
            "answered_count": len(items),
            "scored_count": len(items),
            "blank_count": 0,
        },
        "measurement_confidence": {"level": "high", "completion_rate": 1.0, "seconds_per_item": 30, "reasons": []},
        "items": items,
    }


def _probe_questions() -> list[dict]:
    return [
        {
            "question_id": "probe_attempt",
            "question_type": "profile_probe",
            "scored": False,
            "profile_topic": "attempt_history",
            "option_values": {"A": "first_attempt", "B": "retaker_passed_public_last_year"},
        },
        {
            "question_id": "probe_score",
            "question_type": "profile_probe",
            "scored": False,
            "profile_topic": "recent_score_band",
            "option_values": {"A": "no_prior_score", "D": "score_80_95"},
        },
        {
            "question_id": "probe_hours",
            "question_type": "profile_probe",
            "scored": False,
            "profile_topic": "weekly_study_hours",
            "option_values": {"A": "lt_5", "C": "10_20"},
        },
    ]


def _build(*, answers: dict[str, str], wrong: set[str] | None = None) -> dict:
    return build_pass_readiness_report(
        quiz_id="quiz_pr_1",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_architecture_v1_form_1",
        scored_result=_scored_result(wrong_question_ids=wrong),
        session_questions=_probe_questions(),
        answers=answers,
        writeback_refs={"writeback_status": {"status": "pending"}},
        now_iso=NOW,
    )


def test_envelope_is_pass_readiness_v1_with_full_7_2_block() -> None:
    report = _build(answers={"probe_score": "D", "probe_hours": "C", "probe_attempt": "A"})

    assert report["schema_version"] == "pass-readiness-v1"
    block = report["pass_readiness"]
    for field in (
        "estimated_score_band",
        "pass_line",
        "ability_readiness",
        "prep_feasibility",
        "risk_band",
        "evidence_coverage",
        "band_policy_version",
        "reference_pass_interval",
        "model_version",
        "form_version",
        "item_pool_version",
        "generated_at",
    ):
        assert field in block, field
    assert block["pass_line"] == 96
    assert block["band_policy_version"] == "band-v1"
    assert block["form_version"] == "pass_readiness_architecture_v1_form_1"
    assert block["item_pool_version"] == "pass_readiness_architecture_v1"
    assert block["generated_at"] == NOW
    assert block["band_lower"] % 5 == 0 and block["band_upper"] % 5 == 0
    assert block["self_reported_score_label"] == "自报未核验"
    # Base p0a fields are retained for the existing rendering chain.
    assert report["score_summary"]["scored_count"] == 12
    assert len(report["items"]) == 12


def test_item_dimension_binding_yields_4_4_4_observations() -> None:
    binding = ability_dimensions_by_section("pass_readiness_architecture_v1")
    assert len(binding) == 7

    report = _build(answers={})
    dims = report["pass_readiness"]["ability_readiness_detail"]["dimensions"]

    assert dims["core_knowledge"]["observations"] == 4
    assert dims["construction_logic"]["observations"] == 4
    assert dims["case_scoring_point_recognition"]["observations"] == 4
    assert dims["answer_expression"]["measured"] is False
    assert "answer_expression" in report["pass_readiness"]["unmeasured_dimensions"]


def test_same_submission_reproduces_identical_report_with_fixed_now() -> None:
    answers = {"probe_score": "D", "probe_hours": "C", "probe_attempt": "B"}
    wrong = {"q01", "q05", "q09"}

    first = _build(answers=answers, wrong=wrong)
    second = _build(answers=answers, wrong=wrong)

    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_probe_feasibility_answers_never_move_the_band() -> None:
    tight = _build(answers={"probe_hours": "A"})
    ample = _build(answers={"probe_hours": "C"})

    assert tight["pass_readiness"]["estimated_score_band"] == ample["pass_readiness"]["estimated_score_band"]
    assert tight["pass_readiness"]["prep_feasibility"] != ample["pass_readiness"]["prep_feasibility"]


def test_p0a_builder_behavior_is_unchanged() -> None:
    report = build_result_report(
        quiz_id="quiz_topic_1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        topic_label="防水专题测评",
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        scored_result=_scored_result(),
    )

    assert report["schema_version"] == "p0a-v1"
    assert "pass_readiness" not in report


# ── 证据卡诊断链(2026-08-07 owner 实拍「解析全是空的」根因回归) ──────────
# 病灶:考试面投影(必须隐藏答案)被复用为报告面投影(必须展示诊断),
# 于是三条供给车道各自权威里已审的逐选项诊断一条都没到报告,
# 前端只能长期显示「该采分点的易错点整理中」。


def _diagnosis_questions() -> list[dict]:
    """私有会话快照:q01 带签发诊断,q03 无诊断(用于验证不编造)。"""

    return [
        {
            "question_id": "q01",
            "question_type": "single_choice",
            "scored": True,
            "answer": "A",
            "options": [
                {"key": "A", "text": "普通部位 7d、抗渗与后浇带 ≥14d"},
                {"key": "B", "text": "全部统一按 7d 养护"},
            ],
            "answer_diagnosis": {
                "scoring_point": "施工缝·处理工序",
                "model_answer": "抗渗混凝土与后浇带养护不得少于 14d。",
                "source": "kc:leaf:concrete_joint",
                "options": {
                    "B": {
                        "pitfall": "记了个 7d 就想一刀切省事。",
                        "why_missed": "抗渗与后浇带必须不少于 14d，统一 7d 违反规范。",
                        "fix": "抗渗、后浇带养护≥14d，不能按 7d。",
                        "source": "exam:2024:第10题",
                    }
                },
            },
        },
        {"question_id": "q03", "question_type": "single_choice", "scored": True, "answer": "A"},
    ]


def _wrong_on(question_id: str, letter: str) -> dict:
    scored = _scored_result(wrong_question_ids={question_id})
    for item in scored["items"]:
        if item["question_id"] == question_id:
            item["learner_answer"] = letter
    return scored


def test_evidence_items_carry_issued_diagnosis_for_the_chosen_option() -> None:
    report = build_pass_readiness_report(
        quiz_id="quiz_pr_1",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_form_1",
        scored_result=_wrong_on("q01", "B"),
        session_questions=_diagnosis_questions() + _probe_questions(),
        answers={"q01": "B"},
        now_iso=NOW,
    )

    evidence = report["pass_readiness"]["evidence_items"]
    card = next(item for item in evidence if item["question_id"] == "q01")
    assert card["pitfall"] == "记了个 7d 就想一刀切省事。"
    assert card["why_missed"].startswith("抗渗与后浇带必须不少于 14d")
    assert card["fix"].startswith("抗渗、后浇带养护≥14d")
    assert card["scoring_point"] == "施工缝·处理工序"
    # 对照面(owner 2026-08-07 实拍「看不出正确答案是哪个」回归):
    # 你的作答/正确答案都要带选项原文,采分点要带能得分的确切表述。
    assert card["learner_answer"] == "B"
    assert card["learner_option_text"] == "B. 全部统一按 7d 养护"
    assert card["correct_answer"] == "A"
    assert card["correct_option_text"] == "A. 普通部位 7d、抗渗与后浇带 ≥14d"
    assert card["scoring_wording"] == "抗渗混凝土与后浇带养护不得少于 14d。"
    # 依据来源人话化:exam 引用翻成人话;机器锚只留在 source_ref(排障),不进 source。
    assert card["source"] == "2024 年真题·第10题"
    assert card["source_ref"] == "exam:2024:第10题"


def test_multi_select_why_missed_targets_missed_and_extra_letters() -> None:
    """owner 2026-08-07 实拍卡18回归:多选漏选时,学员实选的是对的选项,
    拿它的解读当「为什么丢分」=答非所问。错因必须锚定 错选+漏选 字母集。"""

    questions = [
        {
            "question_id": "q01",
            "question_type": "multi_choice",
            "scored": True,
            "answer": "ACD",
            "options": [
                {"key": "A", "text": "柱在梁、板顶面"},
                {"key": "B", "text": "任意位置"},
                {"key": "C", "text": "有主次梁的楼板在次梁跨中1/3"},
                {"key": "D", "text": "墙在纵横墙交接处"},
            ],
            "answer_diagnosis": {
                "scoring_point": "施工缝·留置位置",
                "options": {
                    "A": {"why_missed": "柱应留水平缝,位置在梁、板顶面。"},
                    "B": {"why_missed": "单向板只能平行短边,不是任意位置。"},
                    "C": {"why_missed": "次梁跨中1/3剪力小。"},
                },
            },
        },
        {"question_id": "q03", "question_type": "single_choice", "scored": True, "answer": "A"},
    ]
    scored = _scored_result(wrong_question_ids={"q01"})
    for item in scored["items"]:
        if item["question_id"] == "q01":
            item["learner_answer"] = "BC"  # 错选 B + 漏选 A/D,C 选对了
            item["question_type"] = "multi_choice"
    report = build_pass_readiness_report(
        quiz_id="quiz_pr_8",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_form_1",
        scored_result=scored,
        session_questions=questions + _probe_questions(),
        answers={"q01": "BC"},
        now_iso=NOW,
    )

    card = next(
        item for item in report["pass_readiness"]["evidence_items"] if item["question_id"] == "q01"
    )
    # 错因逐项点名错选/漏选,而不是复读选对的 C
    assert "错选 B：单向板只能平行短边" in card["why_missed"]
    assert "漏选 A：柱应留水平缝" in card["why_missed"]
    assert "漏选 D（墙在纵横墙交接处）" in card["why_missed"]
    assert "次梁跨中1/3剪力小" not in card["why_missed"]


def test_scoring_point_scrubs_internal_authoring_shorthand() -> None:
    """owner 2026-08-07:「判型·条件维」这类编题内部速记直出=敷衍。
    维度段剥净;剥完不成话留白;真人话标签原样保留。"""

    from deeptutor.services.assessment.report_read_model import _learner_facing_scoring_point

    assert _learner_facing_scoring_point("施工缝·处理工序") == "施工缝·处理工序"
    assert _learner_facing_scoring_point("支护选型·条件维") == "支护选型"
    assert _learner_facing_scoring_point("步距K·计算表达维") == "步距K"
    assert _learner_facing_scoring_point("灭火器·上集") == "灭火器"
    assert _learner_facing_scoring_point("判型·条件维") == ""
    assert _learner_facing_scoring_point("采分诊断·末题") == ""
    assert _learner_facing_scoring_point("") == ""


def test_scoring_point_never_falls_back_to_chapter_level_knowledge_points() -> None:
    """章节级 knowledge_points(如「主体结构工程施工」)不是采分点,
    无签发采分点时诚实留白(owner 2026-08-07 实拍)。"""

    report = build_pass_readiness_report(
        quiz_id="quiz_pr_9",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_form_1",
        scored_result=_wrong_on("q03", "C"),
        session_questions=_diagnosis_questions() + _probe_questions(),
        answers={"q03": "C"},
        now_iso=NOW,
    )

    card = next(
        item for item in report["pass_readiness"]["evidence_items"] if item["question_id"] == "q03"
    )
    assert card["scoring_point"] == ""


def test_evidence_wording_always_surfaces_issued_model_answer() -> None:
    """设计反转回归(owner 2026-08-07 实拍拍板):正确答案行=对照角色,
    采分点规则句=记忆角色——文本相近也必须各自在位,禁相似度压制。"""

    questions = _diagnosis_questions()
    questions[0]["answer_diagnosis"]["model_answer"] = "普通部位 7d、抗渗与后浇带≥14d"
    report = build_pass_readiness_report(
        quiz_id="quiz_pr_6",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_form_1",
        scored_result=_wrong_on("q01", "B"),
        session_questions=questions + _probe_questions(),
        answers={"q01": "B"},
        now_iso=NOW,
    )

    card = next(
        item for item in report["pass_readiness"]["evidence_items"] if item["question_id"] == "q01"
    )
    assert card["scoring_wording"] == "普通部位 7d、抗渗与后浇带≥14d"


def test_evidence_source_translates_textbook_node_anchor() -> None:
    """kc:/ca:/cc: 锚带教材节点码时,经 taxonomy 单一权威翻成「教材·章节名」(永不露码)。"""

    report = build_pass_readiness_report(
        quiz_id="quiz_pr_7",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_form_1",
        scored_result=_wrong_on("q01", "B"),
        session_questions=[
            {
                **_diagnosis_questions()[0],
                "answer_diagnosis": {
                    "scoring_point": "施工缝·处理工序",
                    "source": "kc:1A413030_103_0196:1",
                    "options": {"B": {"why_missed": "顺序颠倒。"}},
                },
            },
            _diagnosis_questions()[1],
        ]
        + _probe_questions(),
        answers={"q01": "B"},
        now_iso=NOW,
    )

    card = next(
        item for item in report["pass_readiness"]["evidence_items"] if item["question_id"] == "q01"
    )
    assert card["source"].startswith("教材·")
    assert "1A413030" not in card["source"]
    assert card["source_ref"] == "kc:1A413030_103_0196:1"


def test_evidence_source_never_shows_machine_anchor() -> None:
    report = build_pass_readiness_report(
        quiz_id="quiz_pr_5",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_form_1",
        scored_result=_wrong_on("q01", "B"),
        session_questions=[
            {
                **_diagnosis_questions()[0],
                "answer_diagnosis": {
                    "scoring_point": "施工缝·处理工序",
                    "source": "kc:leaf:concrete_joint",
                    "options": {"B": {"why_missed": "顺序颠倒。"}},
                },
            },
            _diagnosis_questions()[1],
        ]
        + _probe_questions(),
        answers={"q01": "B"},
        now_iso=NOW,
    )

    card = next(
        item for item in report["pass_readiness"]["evidence_items"] if item["question_id"] == "q01"
    )
    # owner 实拍病灶:依据来源整行显示机器锚。无节点码可翻时人话面必须留空。
    assert card["source"] == ""
    assert card["source_ref"] == "kc:leaf:concrete_joint"


def test_evidence_items_leave_fields_blank_rather_than_fabricate() -> None:
    report = build_pass_readiness_report(
        quiz_id="quiz_pr_2",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_form_1",
        scored_result=_wrong_on("q03", "C"),
        session_questions=_diagnosis_questions() + _probe_questions(),
        answers={"q03": "C"},
        now_iso=NOW,
    )

    card = next(
        item for item in report["pass_readiness"]["evidence_items"] if item["question_id"] == "q03"
    )
    # 权威没有诊断 → 三个诊断字段一律留空,由前端整行不渲染;绝不填通用套话。
    assert card["pitfall"] == ""
    assert card["why_missed"] == ""
    assert card["fix"] == ""


def test_evidence_items_only_cover_wrong_answers() -> None:
    report = build_pass_readiness_report(
        quiz_id="quiz_pr_3",
        assessment_type="pass_readiness",
        subject_id="construction_exam",
        topic_label="一建过线体检",
        blueprint_version="pass_readiness_architecture_v1",
        form_id="pass_readiness_form_1",
        scored_result=_wrong_on("q01", "B"),
        session_questions=_diagnosis_questions() + _probe_questions(),
        answers={"q01": "B"},
        now_iso=NOW,
    )

    evidence = report["pass_readiness"]["evidence_items"]
    assert [item["question_id"] for item in evidence] == ["q01"]
