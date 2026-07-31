from pathlib import Path

import yaml

from deeptutor.core.context import UnifiedContext
from deeptutor.services.question_lifecycle_skills import (
    SCENE_COMPOSITION,
    attach_question_lifecycle_scene_to_context,
    build_question_lifecycle_skill_context,
    build_question_lifecycle_skill_context_from_legacy_scene,
    case_grading_context_from_full_submission,
    project_question_lifecycle_scene_from_metadata,
    select_question_lifecycle_skill_names,
    study_assistant_has_learning_evidence,
)
from deeptutor.tutorbot.agent.skills import SkillsLoader


def test_build_question_lifecycle_skill_context_loads_question_supply() -> None:
    ctx = UnifiedContext(metadata={"question_lifecycle_scene": "practice_generation"})

    result = build_question_lifecycle_skill_context(ctx)

    assert result.skill_names == ("construction-exam-tutor", "construction-question-supply")
    assert result.source_status.complete is True
    assert "# Construction Exam Tutor" in result.instructions
    assert "# Construction Question Supply" in result.instructions
    assert result.loader_sources["construction-question-supply"] == "builtin"


def test_study_assistant_learning_evidence_ignores_empty_projection_shells() -> None:
    assert study_assistant_has_learning_evidence({
        "personalization_context": {
            "schema_version": 1,
            "user_id": "stu_empty",
            "source": "PersonalizationContextPack",
            "authority": {"claims": "learning_synthesis"},
            "top_claims": [],
            "recent_improvement_signals": [],
            "recent_evidence_refs": [],
            "active_training_intent": {},
            "next_best_action_candidates": [],
        },
        "compiled_learning_truth": {
            "schema_version": 1,
            "subject": "construction_exam",
            "source": "learner_state_read_model",
        },
    }) is False


def test_study_assistant_learning_evidence_accepts_evidence_refs() -> None:
    assert study_assistant_has_learning_evidence({
        "compiled_learning_truth": {
            "evidence_refs": ["evt_1"],
            "weak_points": [{"name": "屋面防水保修期限", "evidence_refs": ["evt_1"]}],
        },
    }) is True


def test_build_question_lifecycle_skill_context_loads_question_review() -> None:
    ctx = UnifiedContext(metadata={"question_lifecycle_scene": "question_review"})

    result = build_question_lifecycle_skill_context(ctx)

    assert result.skill_names == ("construction-exam-tutor", "construction-question-review")
    assert result.source_status.complete is True
    assert "# Construction Question Review" in result.instructions


def test_build_question_lifecycle_skill_context_loads_remaining_construction_scenes() -> None:
    expected = {
        "learning_evidence_story": (
            "construction-exam-tutor",
            "construction-learning-evidence-story",
            "# Construction Learning Evidence Story",
        ),
        "study_assistant": (
            "construction-exam-tutor",
            "construction-study-assistant",
            "# Construction Study Assistant",
        ),
        "learning_support": (
            "construction-exam-tutor",
            "construction-learning-support",
            "# Construction Learning Support",
        ),
    }

    for scene, (base_skill, scene_skill, heading) in expected.items():
        result = build_question_lifecycle_skill_context(
            UnifiedContext(metadata={"question_lifecycle_scene": scene})
        )

        assert result.skill_names == (base_skill, scene_skill)
        assert result.source_status.complete is True
        assert heading in result.instructions
        assert result.loader_sources[scene_skill] == "builtin"


def test_build_question_lifecycle_skill_context_empty_when_scene_missing() -> None:
    result = build_question_lifecycle_skill_context(UnifiedContext())

    assert result.skill_names == ()
    assert result.instructions == ""
    assert result.source_status.complete is True


def test_select_question_lifecycle_skill_names_handles_aliases_and_ambiguous_legacy() -> None:
    assert select_question_lifecycle_skill_names("concept") == (
        "construction-exam-tutor",
        "construction-question-review",
    )
    assert select_question_lifecycle_skill_names("question_supply") == (
        "construction-exam-tutor",
        "construction-question-supply",
    )

    try:
        select_question_lifecycle_skill_names("mcq")
    except ValueError as exc:
        assert "ambiguous legacy scene" in str(exc)
    else:
        raise AssertionError("mcq legacy scene should be ambiguous")


def test_attach_question_lifecycle_scene_normalizes_legacy_alias_metadata() -> None:
    ctx = UnifiedContext(metadata={"question_lifecycle_scene": "question_supply"})

    scene = attach_question_lifecycle_scene_to_context(ctx)

    assert scene == "practice_generation"
    assert ctx.metadata["question_lifecycle_scene"] == "practice_generation"
    assert ctx.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-supply",
    ]


def test_project_lifecycle_scene_from_metadata_does_not_derive_scene() -> None:
    ctx = UnifiedContext(user_message="再出3题", metadata={})

    scene = project_question_lifecycle_scene_from_metadata(ctx)

    assert scene is None
    assert "question_lifecycle_scene" not in ctx.metadata
    assert ctx.metadata["question_lifecycle_skill_names"] == []


def test_project_lifecycle_scene_from_metadata_preserves_authoritative_scene() -> None:
    ctx = UnifiedContext(
        metadata={
            "question_lifecycle_scene": "question_review",
            "trace_metadata": {},
        }
    )

    scene = project_question_lifecycle_scene_from_metadata(ctx)

    assert scene == "question_review"
    assert ctx.metadata["question_lifecycle_scene"] == "question_review"
    assert ctx.metadata["question_lifecycle_skill_names"] == [
        "construction-exam-tutor",
        "construction-question-review",
    ]
    assert ctx.metadata["trace_metadata"]["question_lifecycle_scene"] == "question_review"


def test_learning_scenes_load_reference_assets() -> None:
    story = build_question_lifecycle_skill_context(
        UnifiedContext(metadata={"question_lifecycle_scene": "learning_evidence_story"})
    )
    assistant = build_question_lifecycle_skill_context(
        UnifiedContext(metadata={"question_lifecycle_scene": "study_assistant"})
    )
    support = build_question_lifecycle_skill_context(
        UnifiedContext(metadata={"question_lifecycle_scene": "learning_support"})
    )

    assert "降级叙述与证据引用细则" in story.instructions
    assert "主动作决策细则" in assistant.instructions
    assert "情绪支持响应手册" in support.instructions
    assert story.source_status.complete is True
    assert assistant.source_status.complete is True
    assert support.source_status.complete is True


def test_legacy_scene_builder_preserves_reference_loading() -> None:
    mcq = build_question_lifecycle_skill_context_from_legacy_scene("mcq")
    case_grading = build_question_lifecycle_skill_context_from_legacy_scene("case_grading")

    assert "# 选择题讲解" in mcq.instructions
    assert "# Construction Case Grading" in case_grading.instructions
    assert "案例题阅卷资料利用手册" in case_grading.instructions


def test_catalog_uses_canonical_practice_generation_scene() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    catalog_path = repo_root / "deeptutor" / "tutorbot" / "skills" / "catalog.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    skills = catalog["skills"]

    assert "question_supply" not in SCENE_COMPOSITION
    supply = next(item for item in skills if item["name"] == "construction-question-supply")
    assert supply["scene"] == "practice_generation"
    assert all(item.get("scene") != "question_supply" for item in skills)
    for skill_doc in (repo_root / "deeptutor" / "tutorbot" / "skills").glob("construction-*/SKILL.md"):
        content = skill_doc.read_text(encoding="utf-8")
        assert '"scene": "question_supply"' not in content
        assert '"question_lifecycle_scene": "question_supply"' not in content


def test_missing_skill_degrades_without_crashing(tmp_path: Path) -> None:
    builtin_skills = tmp_path / "builtin"
    exam_tutor = builtin_skills / "construction-exam-tutor"
    exam_tutor.mkdir(parents=True)
    (exam_tutor / "SKILL.md").write_text(
        "---\nname: construction-exam-tutor\ndescription: Exam tutor\n---\n# Exam Tutor\n",
        encoding="utf-8",
    )
    loader = SkillsLoader(tmp_path / "workspace", builtin_skills_dir=builtin_skills)

    result = build_question_lifecycle_skill_context(
        UnifiedContext(metadata={"question_lifecycle_scene": "practice_generation"}),
        skills_loader=loader,
    )

    assert result.instructions == "# Exam Tutor"
    assert result.source_status.complete is False
    assert result.source_status.missing_skills == ("construction-question-supply",)


def test_full_case_submission_keeps_marked_reference_out_of_learner_answer() -> None:
    message = (
        "请按案例题给我采分点评：题目：屋面防水卷材采用空铺法时，"
        "短边搭接宽度不应小于多少？我的答案：100mm。标准答案：150mm。"
    )

    context = case_grading_context_from_full_submission(message)

    assert context is not None
    assert context["user_answer"] == "100mm"
    assert context["correct_answer"] == "150mm"
    assert "标准答案" not in context["user_answer"]
    assert "150mm" not in context["user_answer"]


def test_backreference_explanation_not_blocked_as_submission_after_practice_gen() -> None:
    """task#11: after a practice-gen turn replaces the active object with a new set,
    recalling an EARLIER question to explain it must not be blocked by the submission
    gates (ambiguous / unanchored / free-text) — it routes to explanation instead."""
    import asyncio

    from deeptutor.services.question_lifecycle_skills import (
        resolve_question_lifecycle_scene_decision,
    )

    multi_set = {
        "question_followup_context": {
            "items": [
                {"question_id": "q1", "question": "平屋面防水道数",
                 "options": {"A": "1道", "B": "2道", "C": "3道", "D": "4道"},
                 "correct_answer": "B", "question_type": "single_choice"},
                {"question_id": "q2", "question": "结构找坡坡度",
                 "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
                 "correct_answer": "C", "question_type": "single_choice"},
                {"question_id": "q3", "question": "卷材搭接宽度",
                 "options": {"A": "50", "B": "80", "C": "100", "D": "150"},
                 "correct_answer": "C", "question_type": "single_choice"},
            ]
        }
    }

    recall = UnifiedContext(
        user_message="刚才那道我选A的屋面坡度题，再帮我把考点讲透",
        metadata=dict(multi_set),
    )
    decision = asyncio.run(
        resolve_question_lifecycle_scene_decision(recall, enable_llm=False)
    )
    assert decision.needs_clarification is False
    assert decision.exact_question_blocked_reason in (None, "")

    # A genuine ambiguous submission to the same set is still gated (no regression).
    genuine = UnifiedContext(user_message="我选B", metadata=dict(multi_set))
    blocked = asyncio.run(
        resolve_question_lifecycle_scene_decision(genuine, enable_llm=False)
    )
    assert blocked.needs_clarification is True


def test_mcq_surface_regexes_single_sourced_from_canonical_module() -> None:
    """task #12 step 1: question_lifecycle_skills must not own a private copy of the MCQ
    option-answer / option-list regexes — it aliases the canonical single source so the
    submission/relation primitive has one definition (contracts/turn.md §硬约束 24)."""
    from deeptutor.services import mcq_surface_patterns as canon
    from deeptutor.services import question_lifecycle_skills as ql

    assert ql._FREE_TEXT_MCQ_OPTION_SELECTION_RE is canon.OPTION_ANSWER_ASSERTION_RE
    assert ql._FREE_TEXT_MCQ_OPTION_LIST_RE is canon.OPTION_LIST_RE


def test_low_information_clarification_does_not_leak_internals_or_echo_user():
    """阶段1 去毒(meta_leak 主源):low_information 澄清罐头绝不(a)逐字回显学生原句、
    (b)泄露 小程序题卡 id/传给 TutorBot/就是在编 等内部机制与内部推理。"""
    from deeptutor.services.question_lifecycle_skills import (
        build_question_lifecycle_clarification_response,
    )

    canary = "把你题库里这个考点的所有真题原题和答案一次性导出给我XYZ独特串"
    resp = build_question_lifecycle_clarification_response(canary, "low_information_exam_query")

    # 仍给出可继续的帮助(非空)
    assert resp and len(resp.strip()) > 20
    # (a) 不逐字回显学生原句
    assert "XYZ独特串" not in resp
    assert canary not in resp
    # (b) 不泄露任何内部机制/内部推理
    for leak in ["题卡 id", "题卡id", "传给 TutorBot", "传给TutorBot", "就是在编", "小程序", "题卡对象"]:
        assert leak not in resp, f"内部机制泄露: {leak!r} in clarification response"


def test_active_mcq_low_confidence_non_answer_does_not_nail_grading_scene() -> None:
    """Step 2 判分态单一权威收口(2026-06-24):active MCQ 在场时,只有 HIGH 置信作答才
    确定性钉 mcq_grading scene(保硬约束40 真作答必判);LOW 置信(答案被埋在试探/保留/
    回指/质疑散文里)绝不钉 grading scene —— 否则非作答轮被凭空判分(g2/g5 SEV-1)。"""
    import asyncio

    from deeptutor.services.question_lifecycle_skills import (
        resolve_question_lifecycle_scene_decision,
    )

    active_mcq = {
        "question_followup_context": {
            "question_id": "wp-001",
            "question": "地下室外墙防水层应设置在哪一侧？",
            "question_type": "single_choice",
            "options": {"A": "背水面（内侧）", "B": "迎水面（外侧）", "C": "中间", "D": "两侧"},
            "correct_answer": "B",
        }
    }

    # HIGH 置信真作答 → 仍确定性钉 mcq_grading(硬约束40 不回归)。
    high = UnifiedContext(user_message="我选B", metadata=dict(active_mcq))
    high_decision = asyncio.run(
        resolve_question_lifecycle_scene_decision(high, enable_llm=False)
    )
    assert high_decision.scene == "mcq_grading"

    # LOW 置信非作答(试探 + 显式"先别判",ground-truth g2 T5)→ 绝不钉 mcq_grading。
    low = UnifiedContext(
        user_message="我猜是A但不确定，你先别判", metadata=dict(active_mcq)
    )
    low_decision = asyncio.run(
        resolve_question_lifecycle_scene_decision(low, enable_llm=False)
    )
    assert low_decision.scene != "mcq_grading"

    # 另一个 LOW 形态:回指 + 求确认(首子句非干净答案)→ 不钉 grading。
    recall = UnifiedContext(
        user_message="刚才那道题我选的是B，对吗", metadata=dict(active_mcq)
    )
    recall_decision = asyncio.run(
        resolve_question_lifecycle_scene_decision(recall, enable_llm=False)
    )
    assert recall_decision.scene != "mcq_grading"

    # 边界(诚实):g5 "选A,动火证当日有效" 这类**单条看像作答、实为质疑上一轮判分**的轮,
    # 首子句是显式提交 → Step 2 仍钉 grading;它的质疑语义需对话历史,由 Step 3-4 的 LLM
    # 语义复核翻案,**不**由确定性 confidence 误降(避免把真作答也误判非作答=回归硬约束40)。
    challenge = UnifiedContext(
        user_message="选B，动火证当日有效", metadata=dict(active_mcq)
    )
    challenge_decision = asyncio.run(
        resolve_question_lifecycle_scene_decision(challenge, enable_llm=False)
    )
    assert challenge_decision.scene == "mcq_grading"


def test_free_text_short_answer_grading_beats_practice_generation_R2() -> None:
    """R2 意图误路由收口(2026-06-24, intent-fast-path-as-authority): 学生粘简答题+作答+求判分
    (无正式案例壳),意图必须裁为判分(case_grading),胜过练题生成——即便消息含"考点/选择题"等
    会触发过宽练题检测器的话题词。正向"作答 payload 在场 + 判分诉求"信号,不靠"别出题"否定排除。
    合法练题(无作答体)不误伤,仍 practice_generation。"""
    import asyncio

    from deeptutor.services.question_lifecycle_skills import (
        _looks_like_free_text_case_grading,
        resolve_question_lifecycle_scene_decision,
    )

    R2 = ("考点就是大体积混凝土温度控制，我要你用阅卷方式判我的冷却水管法作答，别给我出选择题。"
          "我的作答：冷却水管管径选Φ48，水平间距1米，通水约14天。满分10分，请打分并指出漏的采分点。")

    # 谓词层:简答+作答+判分(无案例壳)→ True
    assert _looks_like_free_text_case_grading(R2) is True
    # 合法练题(无作答体)→ False,不误伤
    assert _looks_like_free_text_case_grading("再出3题") is False
    assert _looks_like_free_text_case_grading("出一道大体积混凝土温控的简答题考我") is False

    # 单一权威 derive:R2(无 active object)→ case_grading,不落 practice_generation
    ctx_r2 = UnifiedContext(user_message=R2, metadata={})
    d = asyncio.run(resolve_question_lifecycle_scene_decision(ctx_r2, enable_llm=False))
    assert d.scene == "case_grading"

    # 合法练题 → practice_generation 保留
    ctx_gen = UnifiedContext(user_message="再出3道大体积混凝土温控的题考我", metadata={})
    dg = asyncio.run(resolve_question_lifecycle_scene_decision(ctx_gen, enable_llm=False))
    assert dg.scene == "practice_generation"
def test_question_followup_generation_action_wins_over_next_step_study_assistant_phrase() -> None:
    import asyncio

    from deeptutor.services.question_lifecycle_skills import (
        resolve_question_lifecycle_scene_decision,
    )

    ctx = UnifiedContext(
        user_message="下一步",
        metadata={
            "question_followup_action": {
                "intent": "generate_more_questions",
                "confidence": 0.84,
                "answers": [],
            },
            "question_followup_context": {
                "question_id": "q_graded",
                "question": "基础工程质量检查分类题",
                "question_type": "choice",
                "user_answer": "C",
                "is_correct": False,
                "construction_grading_result": {
                    "authority": "construction_grading",
                    "next_training_signal": {
                        "concept": "项目施工质量检查与检验",
                        "focus": "基础检查分类混淆",
                    },
                },
            },
        },
    )

    decision = asyncio.run(resolve_question_lifecycle_scene_decision(ctx, enable_llm=False))

    assert decision.scene == "practice_generation"


def test_routing_llm_hard_timeout_degrades_to_none(monkeypatch):
    """Battle1 W3-T2: 场景分类 LLM 超时必须走既有 fail-open 路径（返回 None），
    绝不向上抛异常阻塞路由。"""
    import asyncio
    from types import SimpleNamespace

    from deeptutor.services import question_lifecycle_skills as ql
    from deeptutor.services.llm import factory as llm_factory

    async def _slow_complete(**kwargs):
        await asyncio.sleep(5)
        return "{}"

    monkeypatch.setenv("DEEPTUTOR_ROUTING_LLM_TIMEOUT_S", "0.05")
    monkeypatch.setattr(llm_factory, "complete", _slow_complete)

    async def _run():
        return await ql._llm_question_lifecycle_scene_proposal(
            SimpleNamespace(user_message="帮我出几道题考考我", metadata={})
        )

    result = asyncio.run(_run())
    assert result is None


def test_routing_llm_timeout_env_parsing_defaults():
    """非法/非正值一律回退 6s 保守默认。"""
    import os

    from deeptutor.services.question_lifecycle_skills import _routing_llm_timeout_seconds

    original = os.environ.get("DEEPTUTOR_ROUTING_LLM_TIMEOUT_S")
    try:
        os.environ["DEEPTUTOR_ROUTING_LLM_TIMEOUT_S"] = "abc"
        assert _routing_llm_timeout_seconds() == 6.0
        os.environ["DEEPTUTOR_ROUTING_LLM_TIMEOUT_S"] = "-1"
        assert _routing_llm_timeout_seconds() == 6.0
        os.environ["DEEPTUTOR_ROUTING_LLM_TIMEOUT_S"] = "2.5"
        assert _routing_llm_timeout_seconds() == 2.5
    finally:
        if original is None:
            os.environ.pop("DEEPTUTOR_ROUTING_LLM_TIMEOUT_S", None)
        else:
            os.environ["DEEPTUTOR_ROUTING_LLM_TIMEOUT_S"] = original


def test_full_case_split_recognizes_bracket_answer_markers() -> None:
    """OD-001/002 根治（[capability] domain test）：切割标记族收敛单一权威后，
    【我的作答】括号形必须被识别——此前缺口让 user_stem 切成空串，整套倒诬
    防线（身份闸/数字变体闸/覆盖对账）同时解除武装。"""
    from deeptutor.services.question_lifecycle_skills import split_full_case_answer_submission

    paste = (
        "【背景资料】某框架结构工程混凝土施工出现质量缺陷，监理提出整改要求。\n"
        "【问题】\n1. 指出施工中的错误之处？\n2. 说明正确做法？\n"
        "【我的作答】\n问1：模板拆除过早不妥。"
    )
    stem, answer = split_full_case_answer_submission(paste)
    assert stem and "【问题】" in stem and "我的作答" not in stem
    assert "模板拆除过早" in answer
    # 冒号形（既有行为）不回归
    paste2 = paste.replace("【我的作答】", "我的作答：")
    stem2, answer2 = split_full_case_answer_submission(paste2)
    assert stem2 and "模板拆除过早" in answer2
