"""Question lifecycle skill composition.

This module is a thin composition layer over TutorBot's existing
``SkillsLoader``. It owns scene -> skill stack mapping, but not routing,
grading, learner-state writes, or RAG policy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeptutor.core.context import UnifiedContext
from deeptutor.tutorbot.agent.skills import SkillsLoader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceStatus:
    complete: bool
    missing_skills: tuple[str, ...] = ()
    missing_assets: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillContext:
    scene: str | None
    skill_names: tuple[str, ...]
    instructions: str
    source_status: SourceStatus
    loader_sources: dict[str, str]


SCENE_COMPOSITION: dict[str, tuple[str, ...]] = {
    "practice_generation": ("construction-exam-tutor", "construction-question-supply"),
    "question_supply": ("construction-exam-tutor", "construction-question-supply"),
    "question_review": ("construction-exam-tutor", "construction-question-review"),
    "mcq_grading": ("construction-exam-tutor", "construction-mcq-grading"),
    "case_grading": ("construction-exam-tutor", "construction-case-grading"),
    "learning_evidence_story": ("construction-exam-tutor", "construction-learning-evidence-story"),
    "study_assistant": ("construction-exam-tutor", "construction-study-assistant"),
    "learning_support": ("construction-exam-tutor", "construction-learning-support"),
}

_LEGACY_COMPOSITION: dict[str, tuple[str, ...]] = {
    "general": ("construction-exam-tutor",),
    "concept": ("construction-exam-tutor",),
    "mcq": ("construction-exam-tutor",),
    "case": ("construction-exam-tutor",),
    "error_review": ("construction-exam-tutor",),
    "mcq_grading": SCENE_COMPOSITION["mcq_grading"],
    "case_grading": SCENE_COMPOSITION["case_grading"],
    "question_supply": SCENE_COMPOSITION["question_supply"],
    "question_review": SCENE_COMPOSITION["question_review"],
    "practice_generation": SCENE_COMPOSITION["practice_generation"],
}

_LEGACY_SCENE_ALIASES: dict[str, str | None] = {
    "general": None,
    "concept": "question_review",
    "mcq": None,
    "case": None,
    "mcq_grading": "mcq_grading",
    "case_grading": "case_grading",
    "error_review": "question_review",
}

_SCENE_REFERENCE_FILES: dict[str, dict[str, tuple[str, ...]]] = {
    "concept": {"construction-exam-tutor": ("references/concept-explainer.md",)},
    "mcq": {"construction-exam-tutor": ("references/mcq-review.md",)},
    "case": {"construction-exam-tutor": ("references/case-analysis.md",)},
    "error_review": {"construction-exam-tutor": ("references/error-review.md",)},
    "mcq_grading": {
        "construction-mcq-grading": (
            "references/mcq-grading-protocol.md",
            "references/mcq-error-taxonomy.md",
            "references/mcq-source-grounding.md",
        )
    },
    "case_grading": {
        "construction-case-grading": (
            "references/data-authority.md",
            "references/source-grounding.md",
            "references/grading-protocol.md",
            "references/error-taxonomy.md",
        )
    },
}

_LECTURE_TOPIC_REFERENCES = {
    "waterproof": "references/waterproof.md",
    "energy_saving": "references/energy-saving.md",
    "decoration": "references/decoration.md",
}

_MISSING_LOGGED: set[str] = set()


def select_question_lifecycle_skill_names(scene: str | None) -> tuple[str, ...]:
    """Return the skill stack for a canonical question lifecycle scene."""
    normalized = _normalize_scene(scene)
    if normalized is None:
        return ()
    return SCENE_COMPOSITION[normalized]


def build_question_lifecycle_skill_context(
    ctx: UnifiedContext,
    *,
    skills_loader: SkillsLoader | None = None,
) -> SkillContext:
    """Build instructions for the scene already selected by upstream runtime."""
    scene = _context_scene(ctx)
    if scene is None:
        return SkillContext(
            scene=None,
            skill_names=(),
            instructions="",
            source_status=SourceStatus(complete=True),
            loader_sources={},
        )
    skill_names = select_question_lifecycle_skill_names(scene)
    return _build_skill_context(
        scene=scene,
        skill_names=skill_names,
        reference_scene=scene,
        skills_loader=skills_loader,
    )


def build_question_lifecycle_skill_context_from_legacy_scene(
    scene: str | None = "general",
    *,
    skills_loader: SkillsLoader | None = None,
) -> SkillContext:
    """Compatibility adapter for legacy ``ConstructionExamScene`` callers."""
    legacy_scene = str(scene or "general").strip() or "general"
    if legacy_scene not in _LEGACY_COMPOSITION:
        legacy_scene = "general"
    return _build_skill_context(
        scene=legacy_scene,
        skill_names=_LEGACY_COMPOSITION[legacy_scene],
        reference_scene=legacy_scene,
        skills_loader=skills_loader,
    )


def build_lecture_skill_instruction(
    topic: str | None,
    *,
    skills_loader: SkillsLoader | None = None,
) -> str:
    """Build the lecture-topic instruction through the canonical skill loader."""
    reference = _LECTURE_TOPIC_REFERENCES.get(str(topic or "").strip())
    if not reference:
        return ""
    loader = skills_loader or _default_loader()
    parts: list[str] = []
    skill_body = loader.load_skill("lecture-waterproof-energy-decoration")
    if skill_body:
        parts.append(loader._strip_frontmatter(skill_body).strip())
    reference_body = loader.load_skill_asset("lecture-waterproof-energy-decoration", reference)
    if reference_body:
        parts.append(reference_body.strip())
    return "\n\n".join(part for part in parts if part).strip()


def _context_scene(ctx: UnifiedContext) -> str | None:
    metadata = ctx.metadata if isinstance(ctx.metadata, dict) else {}
    raw = getattr(ctx, "question_lifecycle_scene", None) or metadata.get("question_lifecycle_scene")
    if raw is None:
        return None
    return str(raw).strip() or None


def _normalize_scene(scene: str | None) -> str | None:
    if scene is None:
        return None
    value = str(scene).strip()
    if not value:
        return None
    if value in SCENE_COMPOSITION:
        return value
    if value in {"mcq", "case"}:
        raise ValueError("ambiguous legacy scene")
    if value in _LEGACY_SCENE_ALIASES:
        canonical = _LEGACY_SCENE_ALIASES[value]
        if canonical is None:
            return None
        return canonical
    raise ValueError(f"unknown question lifecycle scene: {value}")


def _build_skill_context(
    *,
    scene: str,
    skill_names: tuple[str, ...],
    reference_scene: str,
    skills_loader: SkillsLoader | None,
) -> SkillContext:
    loader = skills_loader or _default_loader()
    available = {
        str(item.get("name") or ""): str(item.get("source") or "")
        for item in loader.list_skills(filter_unavailable=False)
    }
    parts: list[str] = []
    missing_skills: list[str] = []
    missing_assets: list[str] = []
    loader_sources: dict[str, str] = {}

    for skill_name in skill_names:
        body = loader.load_skill(skill_name)
        if not body:
            _log_missing_once(skill_name)
            missing_skills.append(skill_name)
            continue
        loader_sources[skill_name] = available.get(skill_name, "unknown")
        parts.append(loader._strip_frontmatter(body).strip())
        for relative_path in _SCENE_REFERENCE_FILES.get(reference_scene, {}).get(skill_name, ()):
            asset = loader.load_skill_asset(skill_name, relative_path)
            if asset:
                parts.append(asset.strip())
            else:
                missing_assets.append(f"{skill_name}/{relative_path}")

    return SkillContext(
        scene=scene,
        skill_names=skill_names,
        instructions="\n\n".join(part for part in parts if part).strip(),
        source_status=SourceStatus(
            complete=not missing_skills and not missing_assets,
            missing_skills=tuple(missing_skills),
            missing_assets=tuple(missing_assets),
        ),
        loader_sources=loader_sources,
    )


def _default_loader() -> SkillsLoader:
    return SkillsLoader(Path.cwd())


def _log_missing_once(skill_name: str) -> None:
    if skill_name in _MISSING_LOGGED:
        return
    _MISSING_LOGGED.add(skill_name)
    logger.warning("Missing question lifecycle skill: %s", skill_name)
