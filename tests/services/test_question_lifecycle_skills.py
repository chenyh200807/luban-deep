"""Tests for deeptutor.services.question_lifecycle_skills.

Plan: docs/plan/2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md
Task 2 (v2) — shared question lifecycle skill context builder; the only consumer
of `_LEGACY_SCENE_ALIASES` and the single non-SkillsLoader module allowed to
read SKILL.md files (via SkillsLoader).
"""

from __future__ import annotations

import pytest

from deeptutor.services.question_lifecycle_skills import (
    SCENE_COMPOSITION,
    SkillContext,
    SourceStatus,
    build_question_lifecycle_skill_context,
    build_question_lifecycle_skill_context_from_legacy_scene,
    select_question_lifecycle_skill_names,
)


# ---------------------------------------------------------------------------
# Scene composition mapping (canonical scenes)
# ---------------------------------------------------------------------------


def test_scene_composition_covers_all_canonical_scenes():
    expected_scenes = {
        "practice_generation",
        "question_review",
        "mcq_grading",
        "case_grading",
        "learning_evidence_story",
        "study_assistant",
        "learning_support",
    }
    assert set(SCENE_COMPOSITION) == expected_scenes


@pytest.mark.parametrize(
    "scene,expected_skills",
    [
        ("practice_generation", ("construction-exam-tutor", "construction-question-supply")),
        ("question_review", ("construction-exam-tutor", "construction-question-review")),
        ("mcq_grading", ("construction-exam-tutor", "construction-mcq-grading")),
        ("case_grading", ("construction-exam-tutor", "construction-case-grading")),
        (
            "learning_evidence_story",
            ("construction-exam-tutor", "construction-learning-evidence-story"),
        ),
        ("study_assistant", ("construction-exam-tutor", "construction-study-assistant")),
        ("learning_support", ("construction-exam-tutor", "construction-learning-support")),
    ],
)
def test_select_question_lifecycle_skill_names_canonical(scene, expected_skills):
    assert select_question_lifecycle_skill_names(scene) == expected_skills


def test_select_question_lifecycle_skill_names_none_returns_empty():
    """Scene=None → no skill stack injected; downstream falls back to chat."""
    assert select_question_lifecycle_skill_names(None) == ()


# ---------------------------------------------------------------------------
# Legacy alias map
# ---------------------------------------------------------------------------


def test_legacy_alias_concept_maps_to_question_review():
    ctx = build_question_lifecycle_skill_context_from_legacy_scene("concept")
    assert ctx.scene == "question_review"
    assert ctx.skill_names == (
        "construction-exam-tutor",
        "construction-question-review",
    )


def test_legacy_alias_error_review_maps_to_question_review():
    ctx = build_question_lifecycle_skill_context_from_legacy_scene("error_review")
    assert ctx.scene == "question_review"


def test_legacy_alias_general_maps_to_none():
    ctx = build_question_lifecycle_skill_context_from_legacy_scene("general")
    assert ctx.scene is None
    assert ctx.skill_names == ()
    assert ctx.instructions == ""


def test_legacy_alias_mcq_grading_passthrough():
    ctx = build_question_lifecycle_skill_context_from_legacy_scene("mcq_grading")
    assert ctx.scene == "mcq_grading"


def test_legacy_alias_ambiguous_mcq_raises():
    """v2 Task 2 test #8: legacy 'mcq' is ambiguous (supply vs grading);
    caller must resolve via active object before calling builder."""
    with pytest.raises(ValueError, match="ambiguous"):
        build_question_lifecycle_skill_context_from_legacy_scene("mcq")


def test_legacy_alias_ambiguous_case_raises():
    with pytest.raises(ValueError, match="ambiguous"):
        build_question_lifecycle_skill_context_from_legacy_scene("case")


# ---------------------------------------------------------------------------
# build_question_lifecycle_skill_context — payload shape
# ---------------------------------------------------------------------------


def test_build_practice_generation_returns_full_payload():
    ctx = build_question_lifecycle_skill_context("practice_generation")
    assert isinstance(ctx, SkillContext)
    assert ctx.scene == "practice_generation"
    assert ctx.skill_names == (
        "construction-exam-tutor",
        "construction-question-supply",
    )
    assert "# Construction Question Supply" in ctx.instructions
    assert "# Construction Exam Tutor" in ctx.instructions
    assert ctx.source_status.complete is True
    assert ctx.source_status.missing_skills == ()


def test_build_none_scene_returns_empty_payload():
    ctx = build_question_lifecycle_skill_context(None)
    assert ctx.scene is None
    assert ctx.skill_names == ()
    assert ctx.instructions == ""
    assert ctx.source_status.complete is True
    assert ctx.source_status.missing_skills == ()


def test_build_unknown_scene_returns_empty_payload():
    """Unknown scene → empty (caller treats as fallback / chat); no exception."""
    ctx = build_question_lifecycle_skill_context("not_a_real_scene")
    assert ctx.scene == "not_a_real_scene"  # echo back for tracing
    assert ctx.skill_names == ()
    assert ctx.instructions == ""


# ---------------------------------------------------------------------------
# Missing-skill degraded mode (v2 §6.7 invariant #1)
# ---------------------------------------------------------------------------


def test_missing_skill_degrades_source_status(monkeypatch):
    """If one of the composed skills is missing on disk, builder must return
    source_status.complete=False with the missing skill name listed; must not raise."""
    from deeptutor.services import question_lifecycle_skills as mod

    real_load = mod._load_skill_text

    def fake_load(name: str) -> str | None:
        if name == "construction-question-supply":
            return None
        return real_load(name)

    monkeypatch.setattr(mod, "_load_skill_text", fake_load)
    # Drop cached missing-skill warning state (one-shot per process invariant).
    mod._WARNED_MISSING.clear()

    ctx = build_question_lifecycle_skill_context("practice_generation")
    assert ctx.scene == "practice_generation"
    assert ctx.source_status.complete is False
    assert "construction-question-supply" in ctx.source_status.missing_skills
    # exam-tutor still loaded
    assert "# Construction Exam Tutor" in ctx.instructions


def test_missing_skill_warning_logged_once_per_process(monkeypatch, caplog):
    """Per plan §6.7 invariant #3: missing skills logged once per process per name."""
    from deeptutor.services import question_lifecycle_skills as mod

    real_load = mod._load_skill_text  # capture original before monkeypatch

    def fake_load(name: str) -> str | None:
        if name == "construction-question-supply":
            return None
        return real_load(name)

    # Reset and patch
    mod._WARNED_MISSING.clear()
    monkeypatch.setattr(mod, "_load_skill_text", fake_load)

    import logging
    with caplog.at_level(logging.WARNING, logger=mod.logger.name):
        build_question_lifecycle_skill_context("practice_generation")
        build_question_lifecycle_skill_context("practice_generation")
        build_question_lifecycle_skill_context("practice_generation")

    warnings = [r for r in caplog.records if "construction-question-supply" in r.getMessage()]
    assert len(warnings) == 1, f"expected 1 warning, got {len(warnings)}"


# ---------------------------------------------------------------------------
# Loader source telemetry (v2.1 R15 — staging↔prod drift detection)
# ---------------------------------------------------------------------------


def test_skill_context_includes_loader_source_per_skill():
    """SkillContext exposes per-skill loader source for drift detection (workspace vs builtin)."""
    ctx = build_question_lifecycle_skill_context("practice_generation")
    assert hasattr(ctx, "loader_sources")
    assert isinstance(ctx.loader_sources, dict)
    for skill_name in ctx.skill_names:
        assert skill_name in ctx.loader_sources, f"missing loader_source for {skill_name}"
        assert ctx.loader_sources[skill_name] in {"workspace", "builtin"}
