from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BotRuntimeDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_ids: list[str] = Field(default_factory=list)
    execution_engine: Literal["capability", "tutorbot_runtime"] = "capability"
    default_tools: list[str] = Field(default_factory=list)
    default_knowledge_bases: list[str] = Field(default_factory=list)
    supabase_kb_aliases: list[str] = Field(default_factory=list)


def _build_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    return model_type.model_json_schema(mode="validation")


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower()


CONSTRUCTION_EXAM_BOT_DEFAULTS = BotRuntimeDefaults(
    bot_ids=["construction-exam-coach"],
    execution_engine="tutorbot_runtime",
    default_tools=["rag"],
    default_knowledge_bases=["construction-exam"],
    supabase_kb_aliases=[
        "construction-exam",
        "construction-exam-coach",
        "construction-exam-tutor",
        "construction_exam_tutor",
        "construction-knowledge",
        "construction_knowledge",
    ],
)


BOT_RUNTIME_DEFAULTS: tuple[BotRuntimeDefaults, ...] = (
    CONSTRUCTION_EXAM_BOT_DEFAULTS,
)

BOT_RUNTIME_DEFAULT_SCHEMAS: dict[str, dict[str, Any]] = {
    "bot_runtime_defaults": _build_schema(BotRuntimeDefaults),
}


def iter_bot_runtime_defaults() -> tuple[BotRuntimeDefaults, ...]:
    return BOT_RUNTIME_DEFAULTS


def resolve_bot_runtime_defaults(
    *,
    bot_id: str | None = None,
) -> BotRuntimeDefaults | None:
    normalized_bot_id = _normalize(bot_id)
    for defaults in BOT_RUNTIME_DEFAULTS:
        if normalized_bot_id and normalized_bot_id in {_normalize(item) for item in defaults.bot_ids}:
            return defaults
    return None


def export_bot_runtime_defaults_contract() -> dict[str, Any]:
    return {
        "defaults": [defaults.model_dump(exclude_none=True) for defaults in BOT_RUNTIME_DEFAULTS],
        "schemas": {key: dict(value) for key, value in BOT_RUNTIME_DEFAULT_SCHEMAS.items()},
    }


__all__ = [
    "BOT_RUNTIME_DEFAULTS",
    "BOT_RUNTIME_DEFAULT_SCHEMAS",
    "CONSTRUCTION_EXAM_BOT_DEFAULTS",
    "BotRuntimeDefaults",
    "export_bot_runtime_defaults_contract",
    "iter_bot_runtime_defaults",
    "resolve_bot_runtime_defaults",
]
