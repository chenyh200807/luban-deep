"""Shared question-lifecycle skill context builder.

Plan: ``docs/plan/2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md``

This module is the **single non-SkillsLoader entry point** that may read
construction scene SKILL.md files. It wraps
:class:`deeptutor.tutorbot.agent.skills.SkillsLoader` so that
``deep_question`` / ``question_followup`` / ``construction_grading`` /
``teaching_modes`` consume one composition table, one alias map, and one
loader. Plan §5.0 verification target #2 enforces this invariant via grep.

The builder accepts an explicit scene string; the **single decider** for the
scene of a turn is ``ChatOrchestrator`` (plan §5.1). Downstream readers must
read ``UnifiedContext.question_lifecycle_scene`` rather than re-detect.

Legacy ``ConstructionExamScene`` (``general``/``concept``/``mcq``/...) values
are mapped through ``_LEGACY_SCENE_ALIASES`` for backwards compatibility with
the ``teaching_modes.get_construction_exam_skill_instruction`` shim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from deeptutor.tutorbot.agent.skills import BUILTIN_SKILLS_DIR, SkillsLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical scene → skill stack composition
# ---------------------------------------------------------------------------

# Plan §5.0 Six-Question Check #3: scene → skill mapping lives only here.
SCENE_COMPOSITION: dict[str, tuple[str, ...]] = {
    "practice_generation": ("construction-exam-tutor", "construction-question-supply"),
    "question_review": ("construction-exam-tutor", "construction-question-review"),
    "mcq_grading": ("construction-exam-tutor", "construction-mcq-grading"),
    "case_grading": ("construction-exam-tutor", "construction-case-grading"),
    "learning_evidence_story": (
        "construction-exam-tutor",
        "construction-learning-evidence-story",
    ),
    "study_assistant": ("construction-exam-tutor", "construction-study-assistant"),
    "learning_support": ("construction-exam-tutor", "construction-learning-support"),
}

# Plan §5.2 alias map. Sentinel ``_AMBIGUOUS`` forces callers to resolve via
# active object before the builder can map to a canonical scene.
_AMBIGUOUS = object()

_LEGACY_SCENE_ALIASES: dict[str, Optional[str] | object] = {
    "general": None,
    "concept": "question_review",
    "mcq": _AMBIGUOUS,
    "mcq_grading": "mcq_grading",
    "case": _AMBIGUOUS,
    "case_grading": "case_grading",
    "error_review": "question_review",
}


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceStatus:
    """Tracks completeness of skill content loading.

    ``complete=False`` means one or more required skill files were missing on
    disk; the missing names are listed in ``missing_skills``. Per plan §6.7
    invariant #1, builder degrades gracefully instead of raising.
    """

    complete: bool
    missing_skills: tuple[str, ...]


@dataclass(frozen=True)
class SkillContext:
    """Frozen payload describing the runtime skill stack for one turn."""

    scene: Optional[str]
    skill_names: tuple[str, ...]
    instructions: str
    source_status: SourceStatus
    # v2.1 R15: per-skill loader_source for staging↔prod drift detection.
    loader_sources: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Sentinel workspace path: SkillsLoader needs a workspace, but we want all
# loads to go through the canonical ``BUILTIN_SKILLS_DIR``. Pointing the
# workspace at a guaranteed-nonexistent path keeps the workspace branch a
# no-op while preserving the builtin lookup.
_SENTINEL_WORKSPACE = Path("/__question_lifecycle_no_workspace__")

# Re-entrancy guard for once-per-process missing-skill warnings (plan §6.7 #3).
_WARNED_MISSING: set[str] = set()


def _default_loader() -> SkillsLoader:
    return SkillsLoader(workspace=_SENTINEL_WORKSPACE, builtin_skills_dir=BUILTIN_SKILLS_DIR)


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter (identical to SkillsLoader._strip_frontmatter)."""
    if not content.startswith("---"):
        return content
    import re

    match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
    if match:
        return content[match.end():].strip()
    return content


def _load_skill_text(name: str) -> Optional[str]:
    """Load and strip frontmatter of a skill by name; return None if missing."""
    loader = _default_loader()
    raw = loader.load_skill(name)
    if raw is None:
        return None
    return _strip_frontmatter(raw)


def _resolve_loader_source(name: str) -> str:
    """Per plan v2.1 R15: tag where the skill content came from."""
    workspace_path = _SENTINEL_WORKSPACE / "skills" / name / "SKILL.md"
    if workspace_path.exists():
        return "workspace"
    builtin_path = BUILTIN_SKILLS_DIR / name / "SKILL.md"
    if builtin_path.exists():
        return "builtin"
    return "missing"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_question_lifecycle_skill_names(scene: Optional[str]) -> tuple[str, ...]:
    """Pure lookup helper. Returns the skill name tuple for a canonical scene.

    Returns an empty tuple for ``None`` or any scene not in
    ``SCENE_COMPOSITION``. Callers in capability code paths should use
    :func:`build_question_lifecycle_skill_context` instead.
    """
    if scene is None:
        return ()
    return SCENE_COMPOSITION.get(scene, ())


def build_question_lifecycle_skill_context(scene: Optional[str]) -> SkillContext:
    """Compose the runtime skill stack for a given canonical scene.

    Parameters
    ----------
    scene
        Canonical scene name from :data:`SCENE_COMPOSITION`. ``None`` returns
        an empty context (caller treats as fallback / chat). Unknown scene
        names also return an empty payload, but echo the scene back so traces
        can still attribute the routing decision (plan §6.5 v2-5 — no silent
        upgrade to a default scene).
    """
    if scene is None:
        return SkillContext(
            scene=None,
            skill_names=(),
            instructions="",
            source_status=SourceStatus(complete=True, missing_skills=()),
            loader_sources={},
        )

    skill_names = SCENE_COMPOSITION.get(scene, ())
    if not skill_names:
        return SkillContext(
            scene=scene,
            skill_names=(),
            instructions="",
            source_status=SourceStatus(complete=True, missing_skills=()),
            loader_sources={},
        )

    parts: list[str] = []
    missing: list[str] = []
    loader_sources: dict[str, str] = {}

    for name in skill_names:
        text = _load_skill_text(name)
        loader_sources[name] = _resolve_loader_source(name)
        if text is None:
            missing.append(name)
            if name not in _WARNED_MISSING:
                _WARNED_MISSING.add(name)
                logger.warning(
                    "question_lifecycle_skill_context: required skill %r missing on disk; "
                    "degrading source_status.complete=False",
                    name,
                )
            continue
        parts.append(text)

    return SkillContext(
        scene=scene,
        skill_names=skill_names,
        instructions="\n\n---\n\n".join(parts),
        source_status=SourceStatus(complete=not missing, missing_skills=tuple(missing)),
        loader_sources=loader_sources,
    )


def build_question_lifecycle_skill_context_from_legacy_scene(
    legacy_scene: Optional[str],
) -> SkillContext:
    """Bridge for legacy ``ConstructionExamScene`` callers (Task 2.5 shim).

    Resolves the legacy alias map (§5.2) and delegates. Raises ``ValueError``
    when the legacy value is ambiguous (``mcq`` / ``case`` collapse two
    canonical scenes and require the caller to inspect active-object /
    submission state before choosing).
    """
    if legacy_scene is None:
        return build_question_lifecycle_skill_context(None)

    canonical = _LEGACY_SCENE_ALIASES.get(legacy_scene.lower(), legacy_scene)
    if canonical is _AMBIGUOUS:
        raise ValueError(
            f"ambiguous legacy scene {legacy_scene!r}: caller must resolve "
            "to practice_generation or {mcq,case}_grading via active object "
            "before invoking the lifecycle skill builder"
        )
    return build_question_lifecycle_skill_context(canonical)  # type: ignore[arg-type]
