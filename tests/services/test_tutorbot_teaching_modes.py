from deeptutor.tutorbot.teaching_modes import (
    detect_construction_exam_scene,
    detect_lecture_topic,
    get_construction_exam_skill_instruction,
    get_lecture_skill_instruction,
    get_teaching_mode_instruction,
    normalize_teaching_mode,
)


def test_normalize_teaching_mode_defaults_to_smart():
    assert normalize_teaching_mode(None) == "smart"
    assert normalize_teaching_mode("") == "smart"
    assert normalize_teaching_mode("intelligent") == "smart"


def test_normalize_teaching_mode_accepts_fast_and_deep():
    assert normalize_teaching_mode("fast") == "fast"
    assert normalize_teaching_mode("FAST") == "fast"
    assert normalize_teaching_mode("deep") == "deep"


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
