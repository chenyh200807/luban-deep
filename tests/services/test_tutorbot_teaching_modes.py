import deeptutor.tutorbot.teaching_modes as teaching_modes_module
from deeptutor.tutorbot.teaching_modes import (
    build_continuity_anchor_instruction,
    detect_construction_exam_scene,
    detect_lecture_topic,
    get_anchor_preservation_instruction,
    get_construction_exam_skill_instruction,
    get_lecture_skill_instruction,
    get_teaching_mode_instruction,
    looks_like_practice_generation_request,
    normalize_anchor_terms_in_response,
    normalize_teaching_mode,
)
from deeptutor.tutorbot.response_mode import (
    build_mode_execution_policy,
    resolve_requested_response_mode,
)


def test_normalize_teaching_mode_defaults_to_smart():
    assert normalize_teaching_mode(None) == "smart"
    assert normalize_teaching_mode("") == "smart"
    assert normalize_teaching_mode("AUTO") == "smart"
    assert normalize_teaching_mode("intelligent") == "smart"


def test_normalize_teaching_mode_accepts_fast_and_deep():
    assert normalize_teaching_mode("fast") == "fast"
    assert normalize_teaching_mode("FAST") == "fast"
    assert normalize_teaching_mode("deep") == "deep"


def test_normalize_teaching_mode_delegates_to_requested_response_mode_normalizer(monkeypatch):
    calls: list[object] = []

    def _fake_normalizer(value: object) -> str:
        calls.append(value)
        return "smart"

    monkeypatch.setattr(
        teaching_modes_module,
        "normalize_requested_response_mode",
        _fake_normalizer,
        raising=False,
    )

    assert normalize_teaching_mode("AUTO") == "smart"
    assert calls == ["AUTO"]


def test_resolve_requested_response_mode_prefers_new_hint_over_legacy_teaching_mode():
    assert resolve_requested_response_mode(
        chat_mode="",
        interaction_hints={
            "requested_response_mode": "deep",
            "teaching_mode": "fast",
        },
    ) == "deep"


def test_mode_execution_policy_separates_fast_and_deep_workflows():
    fast = build_mode_execution_policy("fast", selected_mode="fast")
    deep = build_mode_execution_policy("deep", selected_mode="deep")

    assert fast.knowledge_strategy == "kb_first"
    assert fast.workflow == "single_shot_with_prefetch"
    assert fast.model_fallback_allowed is True
    assert fast.web_search_allowed is True
    assert fast.execution_path == "tutorbot_kb_first_fast_policy"
    assert fast.max_tool_rounds < deep.max_tool_rounds
    assert fast.allow_deep_stage is False

    assert deep.knowledge_strategy == "kb_first"
    assert deep.workflow == "full_agent_loop"
    assert deep.model_fallback_allowed is True
    assert deep.web_search_allowed is True
    assert deep.execution_path == "tutorbot_kb_first_full_agent_policy"
    assert deep.allow_deep_stage is True


def test_looks_like_practice_generation_request_accepts_natural_one_question_phrasing():
    assert looks_like_practice_generation_request("给我一道题测试一下这个知识点") is True
    assert looks_like_practice_generation_request("给我5道题练练") is True
    assert looks_like_practice_generation_request("选择题") is True
    assert looks_like_practice_generation_request("给我出选择题") is True
    assert looks_like_practice_generation_request("给我出简答题") is True
    assert looks_like_practice_generation_request("请生成一道建筑构造练习题") is True
    assert looks_like_practice_generation_request("生成3道防水工程选择题") is True
    assert looks_like_practice_generation_request("我想练习建筑构造相关的题目") is True
    assert looks_like_practice_generation_request("我想练习防水工程相关简答题") is True
    assert looks_like_practice_generation_request("先做一次摸底测评") is True
    assert looks_like_practice_generation_request("帮我做一次入门摸底测试") is True
    assert looks_like_practice_generation_request("开始一轮小测") is True


def test_looks_like_practice_generation_request_rejects_learning_strategy_phrasing():
    assert looks_like_practice_generation_request("我现在最大问题是记不住，做题时规范数字总串，给我一个今晚能执行的学习法") is False
    assert looks_like_practice_generation_request("给我一个练习方法，不要出题") is False
    assert looks_like_practice_generation_request("讲一下自测清单怎么用") is False
    assert looks_like_practice_generation_request("查看摸底报告") is False
    assert (
        looks_like_practice_generation_request(
            "请根据我的学习记录和最近进度，围绕施工组织设计安排下一步学习推进："
            "先判断我当前更适合知识讲解、例题带练、错因复盘还是少量自测；"
            "不要默认生成整套训练题。"
        )
        is False
    )


def test_get_teaching_mode_instruction_matches_expected_density():
    fast = get_teaching_mode_instruction("fast")
    deep = get_teaching_mode_instruction("deep")
    smart = get_teaching_mode_instruction("smart")

    assert "采分点" in fast
    assert "易错点" in fast
    assert "400 字左右" in fast

    assert "记忆口诀" in deep
    assert "心得" in deep
    assert "案例题" in deep

    assert smart == ""


def test_get_anchor_preservation_instruction_preserves_explicit_case_anchor_wording():
    instruction = get_anchor_preservation_instruction("你用盖一栋6层住宅楼举个例子讲讲")

    assert "6层住宅楼" in instruction
    assert "必须至少显式保留一次" in instruction
    assert "不要自行缩写、泛化或换称呼" in instruction


def test_build_continuity_anchor_instruction_uses_authoritative_context_anchor():
    instruction = build_continuity_anchor_instruction(
        "你接着我前面那个例子讲，不要重新开始。",
        active_object={
            "object_type": "open_chat_topic",
            "object_id": "session-1",
            "state_snapshot": {
                "title": "流水施工入门",
                "compressed_summary": "用户一直在用6层住宅楼的例子理解流水节拍和施工段。",
            },
        },
        conversation_context_text="最近一直在沿用6层住宅楼这个案例。",
    )

    assert "延续前文" in instruction
    assert "6层住宅楼" in instruction
    assert "不要重新起一个泛化的新例子" in instruction


def test_normalize_anchor_terms_in_response_restores_exact_user_anchor_wording():
    normalized = normalize_anchor_terms_in_response(
        user_message="你用盖一栋6层住宅楼举个例子讲讲",
        response="想象你盖一栋 6 层住宅楼，先做第一层，再做第二层。",
    )

    assert "6层住宅楼" in normalized


def test_detect_construction_exam_scene_routes_to_expected_variants():
    assert detect_construction_exam_scene("什么是流水施工？", answer_type="knowledge_explainer") == "concept"
    assert detect_construction_exam_scene("这道单选题选什么？A. B. C. D.", answer_type="problem_solving") == "mcq"
    assert detect_construction_exam_scene("请分析这道案例题的答题思路") == "case"
    assert detect_construction_exam_scene("请批改这道案例题答案，看看能得几分") == "case_grading"
    assert detect_construction_exam_scene("这道单选题我选A，对吗？") == "mcq_grading"
    assert (
        detect_construction_exam_scene(
            "我选ACD，帮我判分",
            followup_context={"question_type": "multi_choice", "user_answer": ["A", "C", "D"]},
        )
        == "mcq_grading"
    )
    assert (
        detect_construction_exam_scene(
            "帮我判分，漏了哪些采分点",
            followup_context={"question_type": "case_study", "user_answer": "应加强管理"},
        )
        == "case_grading"
    )
    assert detect_construction_exam_scene(
        "我为什么又做错了",
        followup_context={"user_answer": "A", "correct_answer": "B", "is_correct": False},
    ) == "error_review"


def test_get_construction_exam_skill_instruction_uses_progressive_scene_loading():
    mcq_instruction = get_construction_exam_skill_instruction("mcq")
    concept_instruction = get_construction_exam_skill_instruction("concept")
    mcq_grading_instruction = get_construction_exam_skill_instruction("mcq_grading")
    case_grading_instruction = get_construction_exam_skill_instruction("case_grading")

    assert "渐进式加载" in mcq_instruction
    assert "# 选择题讲解" in mcq_instruction
    assert "# 概念讲解" in concept_instruction
    assert "# 选择题讲解" not in concept_instruction
    assert "# Construction MCQ Grading" in mcq_grading_instruction
    assert "确定性优先" in mcq_grading_instruction
    assert "选择题判分协议" in mcq_grading_instruction
    assert "线上 Supabase 对账结论" in mcq_grading_instruction
    assert "option_reasoning" in mcq_grading_instruction
    assert "# 选择题讲解" not in mcq_grading_instruction
    assert "# Construction Case Grading" in case_grading_instruction
    assert "三档阅卷模式" in case_grading_instruction
    assert "案例题阅卷资料利用手册" in case_grading_instruction
    assert "kb_chunks.metadata" in case_grading_instruction
    assert "standard_articles" in case_grading_instruction
    assert "# 案例题讲解" not in case_grading_instruction


def test_lecture_skill_instruction_routes_by_topic():
    assert detect_lecture_topic("地下防水和卷材防水怎么区分") == "waterproof"
    assert detect_lecture_topic("节能门窗和气密性怎么考") == "energy_saving"
    assert detect_lecture_topic("抹灰工程常见通病有哪些") == "decoration"

    waterproof_instruction = get_lecture_skill_instruction("屋面防水通病怎么答")
    decoration_instruction = get_lecture_skill_instruction("轻质隔墙施工流程")

    assert "# 防水专题" in waterproof_instruction
    assert "# 装修专题" in decoration_instruction


# ---------------------------------------------------------------------------
# Plan 2026-05-24 question lifecycle skill authority — construction scene pack
# ---------------------------------------------------------------------------

from deeptutor.tutorbot.agent.skills import BUILTIN_SKILLS_DIR

_REQUIRED_SCENE_SKILLS: dict[str, tuple[str, ...]] = {
    "construction-question-supply": ("出题", "继续练", "摸底", "QuestionArtifact", "reveal_answers"),
    "construction-question-review": ("真题", "题干", "选项", "逐项", "未作答"),
    "construction-learning-evidence-story": ("evidence_refs", "错因", "历史", "PII"),
    "construction-study-assistant": ("training_intent", "今天学什么", "下一步", "study_plan"),
    "construction-learning-support": ("没动力", "焦虑", "鼓励", "情绪", "crisis"),
}


def test_construction_scene_skill_pack_files_exist():
    """Plan §6.1 + v2 R3: five scene SKILL.md files must exist."""
    for skill_name in _REQUIRED_SCENE_SKILLS:
        skill_file = BUILTIN_SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_file.exists(), f"missing required scene skill: {skill_file}"


def test_construction_scene_skills_contain_required_keywords():
    """Plan §6.5: each skill encodes scene-specific anchors."""
    for skill_name, required in _REQUIRED_SCENE_SKILLS.items():
        skill_file = BUILTIN_SKILLS_DIR / skill_name / "SKILL.md"
        text = skill_file.read_text(encoding="utf-8")
        for keyword in required:
            assert keyword in text, f"{skill_name} missing required keyword: {keyword!r}"


def test_construction_scene_skills_anti_patterns_have_three_entries():
    """v2.1 R18 / R21: every new SKILL.md must list at least 3 ### ❌ anti-patterns."""
    for skill_name in _REQUIRED_SCENE_SKILLS:
        text = (BUILTIN_SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "## Anti-Patterns" in text, f"{skill_name} missing '## Anti-Patterns' section"
        anti_pattern_section = text.split("## Anti-Patterns", 1)[1]
        count = anti_pattern_section.count("### ❌")
        assert count >= 3, (
            f"{skill_name}: Anti-Patterns section has {count} '### ❌' entries (need >=3)"
        )


def test_learner_state_narration_skills_have_scope_guard_keywords():
    """Plan §6.1 v2.1 R6: narration skills must declare presentation-only scope.

    These three skills must not contain DB field names, thresholds, SQL keywords,
    or numeric percentage thresholds — those facts live in learner_state read
    model contracts, not in markdown.
    """
    forbidden_substrings = ("SELECT ", "JOIN ", "WHERE ")
    narration_skills = (
        "construction-learning-evidence-story",
        "construction-study-assistant",
        "construction-learning-support",
    )
    for skill_name in narration_skills:
        text = (BUILTIN_SKILLS_DIR / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for token in forbidden_substrings:
            assert token not in text, (
                f"{skill_name}: forbidden SQL token {token!r} found — narration "
                "skills must stay presentation-only (plan §6.1 v2.1 R6)"
            )
