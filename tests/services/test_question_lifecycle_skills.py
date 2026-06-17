from pathlib import Path

import yaml

from deeptutor.core.context import UnifiedContext
from deeptutor.services.question_lifecycle_skills import (
    SCENE_COMPOSITION,
    attach_question_lifecycle_scene_to_context,
    build_question_lifecycle_skill_context,
    build_question_lifecycle_skill_context_from_legacy_scene,
    project_question_lifecycle_scene_from_metadata,
    select_question_lifecycle_skill_names,
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
