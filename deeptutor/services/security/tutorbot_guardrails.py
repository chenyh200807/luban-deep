"""Thin TutorBot guardrail wrappers around the canonical security skill."""

from __future__ import annotations

from dataclasses import dataclass

from deeptutor.services.security.tutorbot_security_skill import (
    TutorBotSecurityDecision,
    TutorBotSecuritySkill,
)


@dataclass(frozen=True)
class TutorBotGuardrailResult:
    blocked: bool
    level: str
    signals: tuple[str, ...] = ()
    content: str | None = None


def _wrap(decision: TutorBotSecurityDecision) -> TutorBotGuardrailResult:
    return TutorBotGuardrailResult(
        blocked=decision.blocked,
        level=decision.level,
        signals=decision.signals,
        content=decision.content,
    )


def normalize_guardrail_text(text: str | None) -> str:
    return TutorBotSecuritySkill.normalize_text(text)


def classify_tutorbot_user_input(text: str | None) -> TutorBotGuardrailResult:
    return _wrap(TutorBotSecuritySkill.classify_user_input(text))


def sanitize_untrusted_context(text: str | None, *, source: str = "tool") -> TutorBotGuardrailResult:
    return _wrap(TutorBotSecuritySkill.sanitize_untrusted_context(text, source=source))


def guard_tutorbot_output(text: str | None) -> TutorBotGuardrailResult:
    return _wrap(TutorBotSecuritySkill.guard_output(text))
