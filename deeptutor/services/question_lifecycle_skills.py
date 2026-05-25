"""Question lifecycle skill composition.

This module is a thin composition layer over TutorBot's existing
``SkillsLoader``. It owns scene -> skill stack mapping, but not routing,
grading, learner-state writes, or RAG policy.

Single-authority note (plan 2026-05-24 §5.1): the orchestrator records one
``QuestionLifecycleSceneDecision`` per turn. Deterministic helpers collect
stable facts / hard gates; the LLM only proposes a semantic candidate; this
module's business-gated decision is the final scene authority. Downstream
readers must consume ``UnifiedContext.metadata['question_lifecycle_scene']``
rather than re-detecting.

Merge note (2026-05-24): this file integrates the hermes edu-skills booster
shape (already on origin/main: SCENE_COMPOSITION, _LEGACY_COMPOSITION,
_SCENE_REFERENCE_FILES, build_question_lifecycle_skill_context(ctx),
build_lecture_skill_instruction, SourceStatus.missing_assets,
SkillContext.loader_sources) with the question-lifecycle-skill-authority
branch additions (derive_question_lifecycle_scene,
attach_question_lifecycle_scene_to_context).
"""

from __future__ import annotations

import json
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


@dataclass(frozen=True)
class QuestionLifecycleSceneDecision:
    """Resolved lifecycle scene plus decision provenance."""

    scene: str | None
    source: str
    confidence: float
    reason: str
    required_anchor_status: str = ""
    exact_question_blocked_reason: str = ""
    selected_skill_names: tuple[str, ...] = ()
    needs_clarification: bool = False
    llm_scene_candidate: dict[str, Any] | None = None
    business_gate_result: str = ""


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


async def resolve_question_lifecycle_scene_decision(
    ctx: Any,
    *,
    enable_llm: bool = True,
) -> QuestionLifecycleSceneDecision:
    """Resolve lifecycle scene through one authoritative decision payload.

    Deterministic helpers collect stable facts and hard safety gates. The LLM
    may propose a semantic scene candidate, but the final decision is always
    this function's business-gated ``QuestionLifecycleSceneDecision``.
    """

    scene = derive_question_lifecycle_scene(ctx)
    user_message = str(getattr(ctx, "user_message", None) or "").strip()
    metadata = getattr(ctx, "metadata", None) or {}
    unanchored_submission = _looks_like_unanchored_mcq_answer_submission(user_message, metadata)
    low_information_exam_query = is_low_information_exam_query(user_message)
    proposal: QuestionLifecycleSceneDecision | None = None
    if enable_llm and (low_information_exam_query or (scene is None and _should_use_llm_scene_proposal(ctx))):
        proposal = await _llm_question_lifecycle_scene_proposal(ctx)
    llm_candidate = _llm_candidate_payload(proposal)

    if unanchored_submission:
        return QuestionLifecycleSceneDecision(
            scene=None,
            source=proposal.source if proposal is not None else "deterministic",
            confidence=1.0,
            reason="answer submission needs an active question",
            required_anchor_status="missing_active_question",
            exact_question_blocked_reason="unanchored_answer_submission",
            selected_skill_names=(),
            needs_clarification=True,
            llm_scene_candidate=llm_candidate,
            business_gate_result="blocked_unanchored_answer_submission",
        )
    if low_information_exam_query:
        return QuestionLifecycleSceneDecision(
            scene=None,
            source=proposal.source if proposal is not None else "deterministic",
            confidence=1.0,
            reason="low-information exam query needs clarification",
            required_anchor_status="missing_question_anchor",
            exact_question_blocked_reason="low_information_exam_query",
            selected_skill_names=(),
            needs_clarification=True,
            llm_scene_candidate=llm_candidate,
            business_gate_result="blocked_low_information_exam_query",
        )
    if scene is not None:
        skill_names = select_question_lifecycle_skill_names(scene)
        return QuestionLifecycleSceneDecision(
            scene=scene,
            source="deterministic",
            confidence=1.0,
            reason="deterministic lifecycle scene matched",
            required_anchor_status="satisfied",
            selected_skill_names=skill_names,
            llm_scene_candidate=llm_candidate,
            business_gate_result="passed",
        )
    if not enable_llm or not _should_use_llm_scene_proposal(ctx):
        return QuestionLifecycleSceneDecision(
            scene=None,
            source="none",
            confidence=0.0,
            reason="no deterministic scene and LLM proposal not applicable",
            business_gate_result="no_candidate",
        )
    if proposal is None:
        return QuestionLifecycleSceneDecision(
            scene=None,
            source="llm",
            confidence=0.0,
            reason="LLM scene proposal unavailable",
            business_gate_result="llm_unavailable",
        )
    return proposal


def is_low_information_exam_query(query: str) -> bool:
    """Return True when the message is an exam inventory/filter query, not a question.

    Examples: ``2025真题`` / ``历年真题`` / ``防水真题``. These carry a
    subject/year/topic filter, but no concrete stem, options, active question,
    or explicit review/generation verb. They must not unlock exact-answer
    authority.
    """

    text = re.sub(r"\s+", "", str(query or "").strip())
    if not text:
        return False
    if not any(marker in text for marker in ("真题", "试题", "题库", "试卷")):
        return False
    explicit_action_markers = (
        "分析",
        "讲解",
        "解析",
        "讲一",
        "讲这",
        "出",
        "练",
        "训练",
        "测试",
        "考我",
        "做",
        "批改",
        "我选",
        "我答",
        "题干",
        "选项",
        "下列",
        "正确的是",
        "错误的是",
    )
    if any(marker in text for marker in explicit_action_markers):
        return False
    if _FREE_TEXT_MCQ_OPTION_LIST_RE.search(str(query or "")):
        return False
    catalog_markers = ("有哪些", "有吗", "目录", "列表", "哪几道", "多少道", "历年", "往年", "答案")
    if any(marker in text for marker in catalog_markers):
        return True
    if re.fullmatch(r"(?:20\d{2})?[\u4e00-\u9fffA-Za-z0-9]{0,12}(?:真题|试题|题库|试卷)", text):
        return True
    return False


def build_question_lifecycle_clarification_response(message: str, reason: str) -> str:
    """Student-visible clarification for lifecycle turns missing an anchor."""

    reason = str(reason or "").strip()
    if reason == "unanchored_answer_submission":
        return (
            "我还不知道你要批改哪一道题。\n\n"
            "请先发送题干和选项，或在当前题卡里提交答案；如果是刚才那道题，也可以点题卡里的选项再提交。"
        )
    if reason == "low_information_exam_query":
        topic = str(message or "").strip() or "真题"
        return (
            f"你提到的是“{topic}”，但还没有指定要做哪件事。\n\n"
            "你可以这样继续：\n"
            "1. 查看这一类真题目录或考点范围\n"
            "2. 让我出一套真题风格练习\n"
            "3. 粘贴具体题干和选项，我按题目讲评：先展示题目，再给答案、逐项解析、易错点和记忆抓手"
        )
    return ""


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
        "choice",
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
        looks_like_question_followup,
        normalize_question_followup_context,
        resolve_submission_attempt,
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
        _target_context, submission = resolve_submission_attempt(user_message, question_context)
        if submission:
            q_type = str(question_context.get("question_type") or "").strip().lower()
            has_options = bool(question_context.get("options"))
            has_items = bool(question_context.get("items"))
            if q_type in _MCQ_QUESTION_TYPES or has_options or has_items:
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


def _should_use_llm_scene_proposal(ctx: Any) -> bool:
    user_message = str(getattr(ctx, "user_message", None) or "").strip()
    if not user_message:
        return False
    metadata = getattr(ctx, "metadata", None) or {}
    if isinstance(metadata, dict):
        if metadata.get("question_followup_context") or metadata.get("active_object"):
            return False
    hints = (
        "题",
        "真题",
        "练",
        "训练",
        "测",
        "测试",
        "考",
        "解析",
        "讲评",
        "讲解",
        "错题",
        "掌握",
        "学情",
        "今天学什么",
        "学不动",
        "没动力",
    )
    return any(hint in user_message for hint in hints)


def _parse_llm_scene_payload(raw: Any) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


async def _llm_question_lifecycle_scene_proposal(
    ctx: Any,
) -> QuestionLifecycleSceneDecision | None:
    from deeptutor.services.llm import factory as llm_factory  # noqa: WPS433

    user_message = str(getattr(ctx, "user_message", None) or "").strip()
    metadata = getattr(ctx, "metadata", None) or {}
    history_context = (
        str(metadata.get("conversation_context_text") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    prompt_payload = {
        "user_message": user_message,
        "history_context": history_context[:800],
        "allowed_scenes": [
            "practice_generation",
            "question_review",
            "mcq_grading",
            "case_grading",
            "learning_evidence_story",
            "study_assistant",
            "learning_support",
            "none",
        ],
        "rules": [
            "用户要求系统出题、练题、测试、检验掌握情况 -> practice_generation",
            "用户要求分析/讲解/解析一道已有题、真题或题库题 -> question_review",
            "用户给出自己的选择或答案并要求批改 -> mcq_grading 或 case_grading",
            "用户问最近哪里错、学得怎么样 -> learning_evidence_story",
            "用户问今天学什么、下一步学什么 -> study_assistant",
            "用户表达没动力、焦虑、学不动 -> learning_support",
            "无法判断或不是学习题目生命周期场景 -> none",
        ],
    }
    try:
        raw = await llm_factory.complete(
            prompt=(
                "请只输出 JSON 对象，字段固定为 scene, confidence, reason。\n"
                "scene 必须来自 allowed_scenes。confidence 是 0 到 1 的数字。\n"
                f"{json.dumps(prompt_payload, ensure_ascii=False)}"
            ),
            system_prompt=(
                "你是鲁班智考的题目生命周期语义候选建议器。"
                "你只提出 scene 候选，不执行出题、不批改、不生成解析。"
            ),
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=300,
            max_retries=0,
            retry_delay=0.1,
        )
    except Exception:
        logger.debug("LLM question lifecycle scene proposal failed", exc_info=True)
        return None
    payload = _parse_llm_scene_payload(raw)
    if payload is None:
        return None
    raw_scene = str(payload.get("scene") or "").strip()
    if raw_scene == "none":
        scene = None
    else:
        try:
            scene = _normalize_scene(raw_scene)
        except ValueError:
            return None
    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if confidence < 0.72:
        scene = None
    skill_names = select_question_lifecycle_skill_names(scene)
    return QuestionLifecycleSceneDecision(
        scene=scene,
        source="llm",
        confidence=confidence,
        reason=str(payload.get("reason") or "").strip(),
        required_anchor_status="satisfied" if scene else "",
        selected_skill_names=skill_names,
        llm_scene_candidate={
            "scene": scene,
            "confidence": confidence,
            "reason": str(payload.get("reason") or "").strip(),
        },
        business_gate_result="passed" if scene else "llm_none_or_low_confidence",
    )


def _llm_candidate_payload(
    proposal: QuestionLifecycleSceneDecision | None,
) -> dict[str, Any] | None:
    if proposal is None:
        return None
    if isinstance(proposal.llm_scene_candidate, dict):
        return dict(proposal.llm_scene_candidate)
    return {
        "scene": proposal.scene,
        "confidence": proposal.confidence,
        "reason": proposal.reason,
    }


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


def _looks_like_unanchored_mcq_answer_submission(
    user_message: str,
    metadata: Any,
) -> bool:
    if not _FREE_TEXT_MCQ_OPTION_SELECTION_RE.search(user_message):
        return False
    if not isinstance(metadata, dict):
        return True
    question_context = metadata.get("question_followup_context")
    if isinstance(question_context, dict) and question_context.get("question"):
        return False
    active_object = metadata.get("active_object")
    if isinstance(active_object, dict):
        snapshot = active_object.get("state_snapshot")
        if isinstance(snapshot, dict) and snapshot.get("question"):
            return False
    return True


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
