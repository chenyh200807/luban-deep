"""Question lifecycle skill composition.

This module is a thin composition layer over TutorBot's existing
``SkillsLoader``. It owns scene -> skill stack mapping, but not routing,
grading, learner-state writes, or RAG policy.

Single-decider note (plan 2026-05-24 §5.1): scene for a turn is decided
exactly once via :func:`derive_question_lifecycle_scene` and attached to
``UnifiedContext.metadata['question_lifecycle_scene']`` by
:func:`attach_question_lifecycle_scene_to_context`. Downstream readers
must consume that metadata rather than re-detecting. Once
``ChatOrchestrator`` (plan Task 0.7) becomes the single attach point,
capability-side ``attach_*`` calls can be removed.

Merge note (2026-05-24): this file integrates the hermes edu-skills booster
shape (already on origin/main: SCENE_COMPOSITION, _LEGACY_COMPOSITION,
_SCENE_REFERENCE_FILES, build_question_lifecycle_skill_context(ctx),
build_lecture_skill_instruction, SourceStatus.missing_assets,
SkillContext.loader_sources) with the question-lifecycle-skill-authority
branch additions (derive_question_lifecycle_scene,
attach_question_lifecycle_scene_to_context).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deeptutor.core.context import UnifiedContext

if TYPE_CHECKING:
    from deeptutor.tutorbot.agent.skills import SkillsLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceStatus:
    """Tracks completeness of skill / reference asset loading."""

    complete: bool
    missing_skills: tuple[str, ...] = ()
    missing_assets: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillContext:
    """Frozen payload describing the runtime skill stack for one turn."""

    scene: str | None
    skill_names: tuple[str, ...]
    instructions: str
    source_status: SourceStatus
    loader_sources: dict[str, str]


# ---------------------------------------------------------------------------
# Canonical scene → skill stack composition
# ---------------------------------------------------------------------------

SCENE_COMPOSITION: dict[str, tuple[str, ...]] = {
    "practice_generation": ("construction-exam-tutor", "construction-question-supply"),
    "question_review": ("construction-exam-tutor", "construction-question-review"),
    "mcq_grading": ("construction-exam-tutor", "construction-mcq-grading"),
    "case_grading": ("construction-exam-tutor", "construction-case-grading"),
    "learning_evidence_story": ("construction-exam-tutor", "construction-learning-evidence-story"),
    "study_assistant": ("construction-exam-tutor", "construction-study-assistant"),
    "learning_support": ("construction-exam-tutor", "construction-learning-support"),
}

# Legacy ConstructionExamScene → skill stack. Used only by the legacy shim
# (`build_question_lifecycle_skill_context_from_legacy_scene`) so that
# `teaching_modes.get_construction_exam_skill_instruction` keeps backward
# compatibility for callers that have not yet migrated to canonical scenes.
_LEGACY_COMPOSITION: dict[str, tuple[str, ...]] = {
    "general": ("construction-exam-tutor",),
    "concept": ("construction-exam-tutor",),
    "mcq": ("construction-exam-tutor",),
    "case": ("construction-exam-tutor",),
    "error_review": ("construction-exam-tutor",),
    "mcq_grading": SCENE_COMPOSITION["mcq_grading"],
    "case_grading": SCENE_COMPOSITION["case_grading"],
    "question_supply": SCENE_COMPOSITION["practice_generation"],
    "question_review": SCENE_COMPOSITION["question_review"],
    "practice_generation": SCENE_COMPOSITION["practice_generation"],
}

# Legacy → canonical alias for telemetry / trace attribution (plan §5.2).
# ``mcq`` / ``case`` are intentionally not mapped because the legacy
# semantics collapse two canonical scenes; the legacy shim still loads
# the legacy stack from ``_LEGACY_COMPOSITION`` and surfaces the legacy
# value on ``SkillContext.scene``.
_LEGACY_SCENE_ALIASES: dict[str, str | None] = {
    "general": None,
    "concept": "question_review",
    "mcq": None,
    "case": None,
    "mcq_grading": "mcq_grading",
    "case_grading": "case_grading",
    "error_review": "question_review",
    "question_supply": "practice_generation",
}

# Per-scene per-skill reference asset paths.
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

# Once-per-process missing-skill warning de-duplication.
_MISSING_LOGGED: set[str] = set()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
    """Build instructions for the scene already attached to ``ctx.metadata``.

    The scene must already be attached to
    ``ctx.metadata['question_lifecycle_scene']`` by
    :func:`attach_question_lifecycle_scene_to_context`. If absent, returns
    an empty context (caller falls back to chat).
    """
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
    """Compatibility adapter for legacy ``ConstructionExamScene`` callers.

    The legacy stack (skills + references) is loaded via
    :data:`_LEGACY_COMPOSITION` + :data:`_SCENE_REFERENCE_FILES`. The
    returned ``SkillContext.scene`` carries the legacy value so callers
    that surface it as telemetry preserve the legacy semantics; consumers
    that need the canonical alias can map via :data:`_LEGACY_SCENE_ALIASES`.
    """
    legacy_scene = str(scene or "general").strip() or "general"
    if legacy_scene not in _LEGACY_COMPOSITION:
        legacy_scene = "general"
    return _build_skill_context(
        scene=legacy_scene,
        skill_names=_LEGACY_COMPOSITION[legacy_scene],
        reference_scene=legacy_scene,
        skills_loader=skills_loader,
    )


def build_default_construction_exam_skill_context(
    *,
    skills_loader: SkillsLoader | None = None,
) -> SkillContext:
    """Build the base construction tutor skill without deriving a scene."""
    return _build_skill_context(
        scene=None,
        skill_names=("construction-exam-tutor",),
        reference_scene=None,
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


# ---------------------------------------------------------------------------
# Scene derivation + attach (plan §5.1 Single Decider implementation point)
# ---------------------------------------------------------------------------
#
# Currently invoked at capability entry boundaries (e.g. deep_question.run)
# as a stopgap until ChatOrchestrator (plan Task 0.7) becomes the single
# attach point. Idempotent: an upstream-set scene (including explicit None)
# is honored.

_LEARNING_EVIDENCE_PHRASES: tuple[str, ...] = (
    "我最近哪里错",
    "为什么我总错",
    "我的弱点",
    "我最近练得",
    "我最近学的怎么样",
    "我最近学得怎么样",
    "最近学习情况",
    "最近学习状态",
    "我的学情",
    "学习记录",
    "最近进度",
    "学习进度",
    "当前薄弱点",
    "我的薄弱点",
    "学习进度怎么样",
    "学习报告",
    "掌握情况",
    "学习证据",
    "错因回顾",
    "复盘错题",
    "错题",
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

_QUESTION_REVIEW_FREETEXT_PHRASES: tuple[str, ...] = (
    "分析一道真题",
    "分析这道真题",
    "讲解一道真题",
    "讲一道真题",
    "解析一道真题",
)
_QUESTION_REVIEW_FREETEXT_RE = re.compile(
    r"(?:分析|讲解|解析|讲)\s*(?:一|1)?\s*(?:道|题)?[^，。！？；\n]{0,24}?真题"
)

_FREE_TEXT_CASE_GRADING_CONTEXT_MARKERS: tuple[str, ...] = (
    "案例题",
    "背景资料",
)
_FREE_TEXT_GRADING_ACTION_MARKERS: tuple[str, ...] = (
    "我的答案",
    "请批改",
    "批改",
    "估分",
    "漏掉",
    "采分点",
)
_FREE_TEXT_MCQ_GRADING_CONTEXT_MARKERS: tuple[str, ...] = (
    "单选题",
    "多选题",
    "选择题",
)
_FREE_TEXT_MCQ_GRADING_ACTION_MARKERS: tuple[str, ...] = (
    "我选",
    "对吗",
    "请批改",
    "批改",
    "判断",
)
_FREE_TEXT_MCQ_OPTION_SELECTION_RE = re.compile(
    r"(?:我选|我选择|选|答案是|我的答案是)\s*[A-DＡ-Ｄ]",
    re.IGNORECASE,
)
_FREE_TEXT_MCQ_OPTION_LIST_RE = re.compile(
    r"(?:^|[\s，。；;：:])A[\.．、:：\s][^，。；;\n]{0,80}"
    r"(?:[\s，。；;：:])B[\.．、:：\s]",
    re.IGNORECASE,
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


def derive_question_lifecycle_scene(ctx: Any) -> str | None:
    """Plan §5.1 single-decider implementation.

    Reads ``ctx.user_message`` and ``ctx.metadata`` (UnifiedContext-shaped
    or any duck-typed object). Returns a canonical scene name from
    :data:`SCENE_COMPOSITION` or ``None`` if the turn does not match any
    lifecycle scene (fallback to chat).

    Priority order (active-object submission wins over free-text intent
    per plan §6.5 v2-1 mixed-turn rule):

    1. Active-object + parseable submission → ``mcq_grading`` or
       ``case_grading``.
    2. Explicit practice generation intent → ``practice_generation``.
    3. Free-text question-review intent / active-object + follow-up
       intent → ``question_review``.
    4. Narrow free-text intent matching → ``learning_evidence_story`` /
       ``study_assistant`` / ``learning_support``.
    5. Otherwise → ``None``.
    """
    # Local imports avoid module-load circular deps.
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

    if question_context:
        submission = extract_submission_answer(user_message, question_context)
        if submission:
            q_type = str(question_context.get("question_type") or "").strip().lower()
            has_options = bool(question_context.get("options"))
            if q_type in _MCQ_QUESTION_TYPES or has_options:
                return "mcq_grading"
            return "case_grading"

    if looks_like_practice_generation_request(user_message):
        return "practice_generation"

    if any(phrase in user_message for phrase in _QUESTION_REVIEW_FREETEXT_PHRASES) or (
        _QUESTION_REVIEW_FREETEXT_RE.search(user_message) is not None
    ):
        return "question_review"

    if question_context and looks_like_question_followup(user_message, question_context):
        return "question_review"

    if _looks_like_free_text_case_grading(user_message):
        return "case_grading"
    if _looks_like_free_text_mcq_grading(user_message):
        return "mcq_grading"

    if any(phrase in user_message for phrase in _LEARNING_SUPPORT_PHRASES):
        return "learning_support"
    if any(phrase in user_message for phrase in _LEARNING_EVIDENCE_PHRASES):
        return "learning_evidence_story"
    if any(phrase in user_message for phrase in _STUDY_ASSISTANT_PHRASES):
        return "study_assistant"

    return None


def attach_question_lifecycle_scene_to_context(ctx: Any) -> str | None:
    """Idempotently attach the derived lifecycle scene to ``ctx.metadata``.

    Honors any pre-existing ``metadata['question_lifecycle_scene']`` value
    (including explicit ``None``) so an earlier upstream decider wins.
    Also refreshes ``metadata['question_lifecycle_skill_names']`` to
    match the resolved scene. Returns the scene attached (or ``None``).
    """
    metadata = getattr(ctx, "metadata", None)
    if not isinstance(metadata, dict):
        return None

    if "question_lifecycle_scene" in metadata:
        scene = _normalize_scene(metadata.get("question_lifecycle_scene"))
    else:
        scene = _normalize_scene(derive_question_lifecycle_scene(ctx))
    metadata["question_lifecycle_scene"] = scene

    if scene is not None:
        skill_names = list(SCENE_COMPOSITION[scene])
        metadata["question_lifecycle_skill_names"] = skill_names
        trace_meta = metadata.setdefault("trace_metadata", {})
        if isinstance(trace_meta, dict):
            trace_meta["question_lifecycle_scene"] = scene
            trace_meta["question_lifecycle_skill_names"] = list(skill_names)
            trace_meta["skill_stack"] = list(skill_names)
    else:
        metadata.setdefault("question_lifecycle_skill_names", [])

    return scene


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _looks_like_free_text_case_grading(user_message: str) -> bool:
    return any(marker in user_message for marker in _FREE_TEXT_CASE_GRADING_CONTEXT_MARKERS) and any(
        marker in user_message for marker in _FREE_TEXT_GRADING_ACTION_MARKERS
    )


def _looks_like_free_text_mcq_grading(user_message: str) -> bool:
    has_question_signal = any(
        marker in user_message for marker in _FREE_TEXT_MCQ_GRADING_CONTEXT_MARKERS
    ) or (_FREE_TEXT_MCQ_OPTION_LIST_RE.search(user_message) is not None)
    has_option_selection = _FREE_TEXT_MCQ_OPTION_SELECTION_RE.search(user_message) is not None
    has_grading_action = has_option_selection or any(
        marker in user_message
        for marker in _FREE_TEXT_MCQ_GRADING_ACTION_MARKERS
        if marker != "我选"
    )
    return has_question_signal and has_grading_action


def _context_scene(ctx: UnifiedContext) -> str | None:
    metadata = ctx.metadata if isinstance(ctx.metadata, dict) else {}
    raw = getattr(ctx, "question_lifecycle_scene", None) or metadata.get("question_lifecycle_scene")
    if raw is None:
        return None
    return _normalize_scene(str(raw).strip() or None)


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
    scene: str | None,
    skill_names: tuple[str, ...],
    reference_scene: str | None,
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
    # Lazy import keeps pure scene derivation safe for minimal server import
    # checks, where TutorBot's optional skill-loader dependencies may be absent.
    from deeptutor.tutorbot.agent.skills import SkillsLoader  # noqa: WPS433

    return SkillsLoader(Path.cwd())


def _log_missing_once(skill_name: str) -> None:
    if skill_name in _MISSING_LOGGED:
        return
    _MISSING_LOGGED.add(skill_name)
    logger.warning("Missing question lifecycle skill: %s", skill_name)
