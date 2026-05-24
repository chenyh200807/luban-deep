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
# Per plan §5.2, legacy ConstructionExamScene values are mapped to canonical
# lifecycle scenes for telemetry / trace attribution. ``general`` has no
# canonical counterpart (it loads exam-tutor only). For the legacy *shim* path
# (``_from_legacy_scene``), the actual skill stack is defined by
# :data:`_LEGACY_SCENE_STACK` rather than this alias map, because legacy
# callers expect the *legacy reference assets* (e.g. ``references/mcq-review.md``)
# to appear in the instructions string.
_LEGACY_SCENE_ALIASES: dict[str, Optional[str]] = {
    "general": None,
    "concept": "question_review",
    "mcq": "question_review",            # legacy mcq = MCQ explain
    "mcq_grading": "mcq_grading",
    "case": "question_review",           # legacy case = case explain
    "case_grading": "case_grading",
    "error_review": "question_review",
}

# Legacy shim skill stack: each legacy scene maps to (skill_names, reference_assets).
# This mirrors what ``teaching_modes.get_construction_exam_skill_instruction``
# used to assemble inline; we move the assembly into the single loader so the
# scattered file-reading paths in ``teaching_modes`` can be removed.
_LEGACY_SCENE_STACK: dict[str, tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = {
    "general": (
        ("construction-exam-tutor",),
        (),
    ),
    "concept": (
        ("construction-exam-tutor",),
        (("construction-exam-tutor", "references/concept-explainer.md"),),
    ),
    "mcq": (
        ("construction-exam-tutor",),
        (("construction-exam-tutor", "references/mcq-review.md"),),
    ),
    "mcq_grading": (
        ("construction-exam-tutor", "construction-mcq-grading"),
        (
            ("construction-mcq-grading", "references/mcq-grading-protocol.md"),
            ("construction-mcq-grading", "references/mcq-error-taxonomy.md"),
            ("construction-mcq-grading", "references/mcq-source-grounding.md"),
        ),
    ),
    "case": (
        ("construction-exam-tutor",),
        (("construction-exam-tutor", "references/case-analysis.md"),),
    ),
    "case_grading": (
        ("construction-exam-tutor", "construction-case-grading"),
        (
            ("construction-case-grading", "references/grading-protocol.md"),
            ("construction-case-grading", "references/data-authority.md"),
            ("construction-case-grading", "references/source-grounding.md"),
            ("construction-case-grading", "references/error-taxonomy.md"),
        ),
    ),
    "error_review": (
        ("construction-exam-tutor",),
        (("construction-exam-tutor", "references/error-review.md"),),
    ),
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


def _load_skill_asset(name: str, relpath: str) -> Optional[str]:
    """Load an arbitrary asset (e.g. ``references/foo.md``) under a skill dir."""
    return _default_loader().read_skill_asset(name, relpath)


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

    Loads the legacy scene's full skill stack (skills + reference assets)
    via :data:`_LEGACY_SCENE_STACK` so that
    ``teaching_modes.get_construction_exam_skill_instruction`` can be reduced
    to a one-line wrapper. The ``scene`` field on the returned ``SkillContext``
    is set to the *canonical* alias (from :data:`_LEGACY_SCENE_ALIASES`) for
    telemetry; ``skill_names`` reflects the legacy stack.

    Unknown legacy values degrade to ``general`` (exam-tutor only) rather than
    raising — callers using the public API still get a sensible payload.
    """
    if legacy_scene is None:
        legacy_key = "general"
    else:
        legacy_key = legacy_scene.lower()

    stack = _LEGACY_SCENE_STACK.get(legacy_key, _LEGACY_SCENE_STACK["general"])
    skill_names, ref_assets = stack
    canonical_scene = _LEGACY_SCENE_ALIASES.get(legacy_key, None)

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
                    "question_lifecycle_skill_context (legacy %r): required skill "
                    "%r missing on disk; degrading source_status.complete=False",
                    legacy_key,
                    name,
                )
            continue
        parts.append(text)

    for skill_name, relpath in ref_assets:
        asset = _load_skill_asset(skill_name, relpath)
        if asset is None:
            missing.append(f"{skill_name}/{relpath}")
            continue
        parts.append(asset)

    return SkillContext(
        scene=canonical_scene,
        skill_names=tuple(skill_names),
        instructions="\n\n---\n\n".join(parts),
        source_status=SourceStatus(complete=not missing, missing_skills=tuple(missing)),
        loader_sources=loader_sources,
    )


# ---------------------------------------------------------------------------
# Scene derivation (plan §5.1 Single Decider implementation point)
# ---------------------------------------------------------------------------
#
# This helper is the *single derivation point* for the question lifecycle scene
# of a turn. It is currently invoked at the deep_question / question_followup /
# TutorBot loop entry boundaries; per plan §5.1, future work (Task 0.7) should
# escalate the call to a single earlier point in ChatOrchestrator so that
# downstream readers only consume ``UnifiedContext.metadata["question_lifecycle_scene"]``
# without re-detecting.
#
# Best-effort free-text intent matching is intentionally narrow (a small set of
# anchor phrases) — anything broader belongs in the semantic router. Per plan
# §6.5 v2-5, low-confidence inputs fall through to ``None`` (chat fallback)
# rather than being silently upgraded to a default scene.

_LEARNING_EVIDENCE_PHRASES: tuple[str, ...] = (
    "我最近哪里错",
    "为什么我总错",
    "我的弱点",
    "我最近练得",
    "学习证据",
    "错因回顾",
    "复盘错题",
    "为什么总错",
)

_STUDY_ASSISTANT_PHRASES: tuple[str, ...] = (
    "今天学什么",
    "下一步",
    "接下来该练",
    "给我安排",
    "训练建议",
    "下一步怎么做",
    "接下来该学什么",
)

_LEARNING_SUPPORT_PHRASES: tuple[str, ...] = (
    "没动力",
    "焦虑",
    "想放弃",
    "学不动",
    "好累",
    "想哭",
    "压力好大",
    "撑不下去",
    "我学不动",
    "学不下去",
)

# Free-text question review intent (no active object yet). Per plan §5
# Authority Matrix row 2: phrases like "分析一道真题" should land on
# construction-question-review so the caller can either reuse an existing
# active object or render a stem first before explanation.
_QUESTION_REVIEW_FREETEXT_PHRASES: tuple[str, ...] = (
    "分析一道真题",
    "分析这道真题",
    "讲解一道真题",
    "讲一道真题",
    "解析一道真题",
)

_MCQ_QUESTION_TYPES: frozenset[str] = frozenset(
    {
        "single_choice",
        "multi_choice",
        "multiple_choice",
        "true_false",
        "judgment",
        "mcq",
    }
)


def derive_question_lifecycle_scene(ctx: Any) -> Optional[str]:
    """Plan §5.1 single-decider implementation.

    Reads ``ctx.user_message`` and ``ctx.metadata`` (UnifiedContext-shaped or
    any duck-typed object with those two attributes). Returns a canonical
    scene name from :data:`SCENE_COMPOSITION` or ``None`` if the turn does
    not match any lifecycle scene (fallback to chat).

    Priority order (active-object submission wins over free-text intent per
    plan §6.5 v2-1 mixed-turn rule):

    1. Active-object + parseable submission → ``mcq_grading`` or ``case_grading``
       (driven by the active question's type).
    2. Explicit practice generation intent ("再出 N 题", etc.) → ``practice_generation``.
    3. Active-object + follow-up intent (no submission) → ``question_review``.
    4. Narrow free-text intent matching → ``learning_evidence_story`` /
       ``study_assistant`` / ``learning_support``.
    5. Otherwise → ``None``.
    """
    # Local imports to avoid circular imports at module load.
    from deeptutor.services.question_followup import (  # noqa: WPS433
        extract_submission_answer,
        looks_like_question_followup,
        normalize_question_followup_context,
    )
    from deeptutor.tutorbot.teaching_modes import (  # noqa: WPS433
        looks_like_practice_generation_request,
    )

    user_message = (getattr(ctx, "user_message", None) or "").strip()
    if not user_message:
        return None

    metadata = getattr(ctx, "metadata", None) or {}
    question_context = normalize_question_followup_context(
        metadata.get("question_followup_context") if isinstance(metadata, dict) else None
    ) or {}

    # Priority 1: active-object + submission → grading scene.
    if question_context:
        submission = extract_submission_answer(user_message, question_context)
        if submission:
            # normalize_question_followup_context flattens question_type to a
            # top-level field; MCQ-ness is also evidenced by an options dict.
            q_type = str(question_context.get("question_type") or "").strip().lower()
            has_options = bool(question_context.get("options"))
            if q_type in _MCQ_QUESTION_TYPES or has_options:
                return "mcq_grading"
            return "case_grading"

    # Priority 2: explicit practice generation intent.
    if looks_like_practice_generation_request(user_message):
        return "practice_generation"

    # Priority 3a: free-text question review intent (no active object yet).
    if any(phrase in user_message for phrase in _QUESTION_REVIEW_FREETEXT_PHRASES):
        return "question_review"

    # Priority 3b: active object + follow-up intent (no submission).
    if question_context and looks_like_question_followup(user_message, question_context):
        return "question_review"

    # Priority 4: narrow free-text intent matching.
    if any(phrase in user_message for phrase in _LEARNING_SUPPORT_PHRASES):
        return "learning_support"
    if any(phrase in user_message for phrase in _LEARNING_EVIDENCE_PHRASES):
        return "learning_evidence_story"
    if any(phrase in user_message for phrase in _STUDY_ASSISTANT_PHRASES):
        return "study_assistant"

    return None


def attach_question_lifecycle_scene_to_context(ctx: Any) -> Optional[str]:
    """Idempotently attach the derived lifecycle scene to ``ctx.metadata``.

    Idempotency note (plan §5.1): if ``ctx.metadata["question_lifecycle_scene"]``
    is already set (e.g. by ChatOrchestrator once Task 0.7 lands), this
    function does not overwrite it. Downstream callers can call this helper
    safely at any number of entry points without re-deriving — the
    earliest-decided scene wins.

    Also writes ``ctx.metadata["question_lifecycle_skill_names"]`` for trace
    attribution. Per plan §6.6 these are diagnostic-only fields; they must
    not be injected into student-visible prompts.

    Returns the scene that ended up on the context (or ``None``).
    """
    metadata = getattr(ctx, "metadata", None)
    if not isinstance(metadata, dict):
        return None

    existing = metadata.get("question_lifecycle_scene")
    if "question_lifecycle_scene" in metadata:
        # Honor whatever the upstream decider set, even if it is explicitly None.
        scene = existing
    else:
        scene = derive_question_lifecycle_scene(ctx)
        metadata["question_lifecycle_scene"] = scene

    if scene is not None:
        # Always refresh the skill_names projection to match the (possibly
        # orchestrator-overridden) scene.
        metadata["question_lifecycle_skill_names"] = list(SCENE_COMPOSITION.get(scene, ()))
    else:
        metadata.setdefault("question_lifecycle_skill_names", [])

    return scene
