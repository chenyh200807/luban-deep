import deeptutor.tutorbot.teaching_modes as teaching_modes_module
from deeptutor.tutorbot.teaching_modes import (
    detect_construction_exam_scene,
    detect_lecture_topic,
    get_construction_exam_skill_instruction,
    get_lecture_skill_instruction,
    get_teaching_mode_instruction,
    looks_like_practice_generation_request,
    normalize_teaching_mode,
)
from deeptutor.tutorbot.response_mode import resolve_requested_response_mode


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


def test_looks_like_practice_generation_request_accepts_natural_one_question_phrasing():
    assert looks_like_practice_generation_request("给我一道题测试一下这个知识点") is True
    assert looks_like_practice_generation_request("给我5道题练练") is True


def test_looks_like_practice_generation_request_rejects_learning_strategy_phrasing():
    assert looks_like_practice_generation_request("我现在最大问题是记不住，做题时规范数字总串，给我一个今晚能执行的学习法") is False
    assert looks_like_practice_generation_request("给我一个练习方法，不要出题") is False


def test_get_teaching_mode_instruction_matches_expected_density():
    fast = get_teaching_mode_instruction("fast")
    deep = get_teaching_mode_instruction("deep")
    smart = get_teaching_mode_instruction("smart")

    assert "踩分点" in fast
    assert "易错点" in fast
    assert "400 字左右" in fast

    assert "记忆口诀" in deep
    assert "心得" in deep
    assert "案例题" in deep

    assert smart == ""


def test_detect_construction_exam_scene_routes_to_expected_variants():
    assert detect_construction_exam_scene("什么是流水施工？", answer_type="knowledge_explainer") == "concept"
    assert detect_construction_exam_scene("这道单选题选什么？A. B. C. D.", answer_type="problem_solving") == "mcq"
    assert detect_construction_exam_scene("请分析这道案例题的答题思路") == "case"
    assert detect_construction_exam_scene(
        "我为什么又做错了",
        followup_context={"user_answer": "A", "correct_answer": "B", "is_correct": False},
    ) == "error_review"


def test_get_construction_exam_skill_instruction_uses_progressive_scene_loading():
    mcq_instruction = get_construction_exam_skill_instruction("mcq")
    concept_instruction = get_construction_exam_skill_instruction("concept")

    assert "渐进式加载" in mcq_instruction
    assert "# 选择题讲解" in mcq_instruction
    assert "# 概念讲解" in concept_instruction
    assert "# 选择题讲解" not in concept_instruction


def test_lecture_skill_instruction_routes_by_topic():
    assert detect_lecture_topic("地下防水和卷材防水怎么区分") == "waterproof"
    assert detect_lecture_topic("节能门窗和气密性怎么考") == "energy_saving"
    assert detect_lecture_topic("抹灰工程常见通病有哪些") == "decoration"

    waterproof_instruction = get_lecture_skill_instruction("屋面防水通病怎么答")
    decoration_instruction = get_lecture_skill_instruction("轻质隔墙施工流程")

    assert "# 防水专题" in waterproof_instruction
    assert "# 装修专题" in decoration_instruction
