"""Compatibility wrapper for the legacy tutorbot profile contract name."""

from __future__ import annotations

from deeptutor.contracts.bot_runtime_defaults import (
    BOT_RUNTIME_DEFAULTS,
    BOT_RUNTIME_DEFAULT_SCHEMAS,
    CONSTRUCTION_EXAM_BOT_DEFAULTS,
    BotRuntimeDefaults,
    export_bot_runtime_defaults_contract,
    iter_bot_runtime_defaults,
    resolve_bot_runtime_defaults,
)

TutorBotRuntimeDefaults = BotRuntimeDefaults
CONSTRUCTION_EXAM_TUTORBOT_DEFAULTS = CONSTRUCTION_EXAM_BOT_DEFAULTS
TUTORBOT_RUNTIME_DEFAULTS = BOT_RUNTIME_DEFAULTS
TUTORBOT_RUNTIME_DEFAULT_SCHEMAS = BOT_RUNTIME_DEFAULT_SCHEMAS


def iter_tutorbot_runtime_defaults() -> tuple[BotRuntimeDefaults, ...]:
    return iter_bot_runtime_defaults()


def resolve_tutorbot_runtime_defaults(
    *,
    bot_id: str | None = None,
) -> BotRuntimeDefaults | None:
    return resolve_bot_runtime_defaults(bot_id=bot_id)


def export_tutorbot_profile_contract() -> dict[str, dict]:
    return export_bot_runtime_defaults_contract()


__all__ = [
    "BOT_RUNTIME_DEFAULTS",
    "BOT_RUNTIME_DEFAULT_SCHEMAS",
    "CONSTRUCTION_EXAM_BOT_DEFAULTS",
    "CONSTRUCTION_EXAM_TUTORBOT_DEFAULTS",
    "BotRuntimeDefaults",
    "TUTORBOT_RUNTIME_DEFAULTS",
    "TUTORBOT_RUNTIME_DEFAULT_SCHEMAS",
    "TutorBotRuntimeDefaults",
    "export_bot_runtime_defaults_contract",
    "export_tutorbot_profile_contract",
    "iter_bot_runtime_defaults",
    "iter_tutorbot_runtime_defaults",
    "resolve_bot_runtime_defaults",
    "resolve_tutorbot_runtime_defaults",
]
