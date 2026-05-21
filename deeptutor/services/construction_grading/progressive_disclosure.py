"""
Progressive disclosure read-model for construction-exam grading explanations.

plan §Phase 5 / Batch E.2 ─ 把答后解释 wrap 成"首屏短结论 + 一句话卡点 + 一个主行动 +
可折叠 sections"的读模型。本模块只构建数据结构（dataclass + dict serialization），
不调 LLM；调用方在拿到 ExplanationSections 之后用本函数生成对外 payload。

也包含 ``classify_difficulty_pacing()``：
  * 连续答错 2 次（或更多） → ``suggest_consolidation`` （讲透 / 基础巩固）
  * 连续答对 3 次（或更多） → ``suggest_step_up`` （提高难度）
  * 其它 → ``hold``

action chips 语义（plan §goal Batch E.10）：
  * ``再练3题``
  * ``讲透这个点``
  * ``看记忆口诀``
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Iterable, Literal

from deeptutor.agents.question.agents.submission_grader_schema import (
    CHOICE_EXTRA_KEYS,
    CASE_EXTRA_KEYS,
    REQUIRED_SECTION_KEYS,
    ExplanationSections,
)


# 首屏中文结论最大长度（plan §goal Batch E.6）。
_FIRST_SCREEN_MAX_CHARS = 120

# 标准 action chip slugs。
ACTION_SLUGS: tuple[str, ...] = (
    "practice_more_3",     # 再练3题
    "explain_thoroughly",  # 讲透这个点
    "show_mnemonic",       # 看记忆口诀
)

_ACTION_LABELS: dict[str, str] = {
    "practice_more_3": "再练3题",
    "explain_thoroughly": "讲透这个点",
    "show_mnemonic": "看记忆口诀",
}


DifficultyPacing = Literal["hold", "suggest_consolidation", "suggest_step_up"]


@dataclass
class ActionChip:
    slug: str
    label: str
    role: Literal["primary", "secondary"] = "secondary"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class ProgressiveDisclosurePayload:
    """Read-model payload that the wx mini-program / web client consumes.

    Fields:
      verdict: 首屏判定 (10-20 字，例 "本题答错"/"本题答对")
      one_line_diagnosis: 一句话卡点 (≤ 50 字)
      primary_next_action: 主行动 ActionChip
      secondary_actions: 至多 2 个辅助 ActionChip
      sections: ExplanationSections.sections (折叠展示)
      difficulty_pacing: hold / suggest_consolidation / suggest_step_up
    """

    verdict: str
    one_line_diagnosis: str
    primary_next_action: ActionChip
    secondary_actions: list[ActionChip] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    difficulty_pacing: DifficultyPacing = "hold"
    grading_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "one_line_diagnosis": self.one_line_diagnosis,
            "primary_next_action": self.primary_next_action.to_dict(),
            "secondary_actions": [chip.to_dict() for chip in self.secondary_actions[:2]],
            "sections": dict(self.sections),
            "difficulty_pacing": self.difficulty_pacing,
            "grading_source": self.grading_source,
        }


def build_progressive_disclosure(
    *,
    explanation: ExplanationSections,
    is_correct: bool | None,
    grading_source: str = "",
    pacing: DifficultyPacing = "hold",
) -> ProgressiveDisclosurePayload:
    """Construct progressive-disclosure payload from parsed explanation sections.

    Truncates ``verdict`` and ``one_line_diagnosis`` to plan §goal Batch E.6 limit.
    """
    verdict_text = _select_verdict(explanation, is_correct=is_correct)
    diagnosis_text = _select_diagnosis(explanation, is_correct=is_correct, pacing=pacing)
    primary, secondaries = _select_actions(explanation, is_correct=is_correct, pacing=pacing)
    return ProgressiveDisclosurePayload(
        verdict=_truncate(verdict_text, _FIRST_SCREEN_MAX_CHARS),
        one_line_diagnosis=_truncate(diagnosis_text, 50),
        primary_next_action=primary,
        secondary_actions=secondaries[:2],
        sections=dict(explanation.sections),
        difficulty_pacing=pacing,
        grading_source=grading_source,
    )


def classify_difficulty_pacing(recent_outcomes: Iterable[bool]) -> DifficultyPacing:
    """Difficulty pacing 决策（plan §goal Batch E.8/E.9）。

    ``recent_outcomes`` 从最近到最早排序的布尔列表，``True`` = 答对、``False`` = 答错。
    规则：
      * 连续 2 个最近答错 → suggest_consolidation
      * 连续 3 个最近答对 → suggest_step_up
      * 否则 hold
    """
    outcomes = [bool(item) for item in recent_outcomes]
    if len(outcomes) >= 2 and outcomes[0] is False and outcomes[1] is False:
        return "suggest_consolidation"
    if len(outcomes) >= 3 and outcomes[0] is True and outcomes[1] is True and outcomes[2] is True:
        return "suggest_step_up"
    return "hold"


def _select_verdict(explanation: ExplanationSections, *, is_correct: bool | None) -> str:
    explicit = str(explanation.sections.get("verdict", "")).strip()
    if explicit:
        return explicit
    if is_correct is True:
        return "本题答对，结论已确认。"
    if is_correct is False:
        return "本题答案与标准不一致。"
    return "本题判定待补，请稍后查看。"


def _select_diagnosis(
    explanation: ExplanationSections,
    *,
    is_correct: bool | None,
    pacing: DifficultyPacing,
) -> str:
    why = str(explanation.sections.get("why_wrong", "")).strip()
    if why:
        return why
    if is_correct is True:
        return "保持节奏，下一题继续巩固。"
    if pacing == "suggest_consolidation":
        return "最近连续 2 次未答对，建议先把这一类题讲透。"
    if is_correct is False:
        return "本次未答对，可以先看错因再继续练。"
    return "建议先确认上一道题的作答结果。"


def _select_actions(
    explanation: ExplanationSections,
    *,
    is_correct: bool | None,
    pacing: DifficultyPacing,
) -> tuple[ActionChip, list[ActionChip]]:
    if pacing == "suggest_consolidation" or is_correct is False:
        primary = ActionChip(slug="explain_thoroughly", label=_ACTION_LABELS["explain_thoroughly"], role="primary")
        secondaries = [
            ActionChip(slug="show_mnemonic", label=_ACTION_LABELS["show_mnemonic"], role="secondary"),
            ActionChip(slug="practice_more_3", label=_ACTION_LABELS["practice_more_3"], role="secondary"),
        ]
        return primary, secondaries
    if pacing == "suggest_step_up":
        primary = ActionChip(slug="practice_more_3", label=_ACTION_LABELS["practice_more_3"], role="primary")
        secondaries = [
            ActionChip(slug="show_mnemonic", label=_ACTION_LABELS["show_mnemonic"], role="secondary"),
        ]
        return primary, secondaries
    # 默认 hold
    primary = ActionChip(slug="practice_more_3", label=_ACTION_LABELS["practice_more_3"], role="primary")
    secondaries = [
        ActionChip(slug="explain_thoroughly", label=_ACTION_LABELS["explain_thoroughly"], role="secondary"),
    ]
    return primary, secondaries


def _truncate(text: str, limit: int) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    if limit <= 1:
        return raw[:limit]
    return raw[: max(0, limit - 1)] + "…"


__all__ = (
    "ACTION_SLUGS",
    "ActionChip",
    "DifficultyPacing",
    "ProgressiveDisclosurePayload",
    "build_progressive_disclosure",
    "classify_difficulty_pacing",
)
