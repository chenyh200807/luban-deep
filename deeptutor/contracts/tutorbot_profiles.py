from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TutorBotKnowledgeChainProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    bot_ids: list[str] = Field(default_factory=list)
    interaction_profiles: list[str] = Field(default_factory=list)
    default_tools: list[str] = Field(default_factory=list)
    default_knowledge_bases: list[str] = Field(default_factory=list)
    supabase_kb_aliases: list[str] = Field(default_factory=list)


def _build_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    return model_type.model_json_schema(mode="validation")


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower()


CONSTRUCTION_EXAM_TUTORBOT_PROFILE = TutorBotKnowledgeChainProfile(
    id="construction_exam_grounded",
    bot_ids=["construction-exam-coach"],
    interaction_profiles=["construction_exam_tutor", "construction_exam_tutor_v1", "mini_tutorbot"],
    default_tools=["rag"],
    default_knowledge_bases=["construction-exam"],
    supabase_kb_aliases=["construction-exam", "construction-exam-coach"],
)


TUTORBOT_KNOWLEDGE_CHAIN_PROFILES: tuple[TutorBotKnowledgeChainProfile, ...] = (
    CONSTRUCTION_EXAM_TUTORBOT_PROFILE,
)

TUTORBOT_KNOWLEDGE_CHAIN_PROFILE_SCHEMAS: dict[str, dict[str, Any]] = {
    "tutorbot_knowledge_chain_profile": _build_schema(TutorBotKnowledgeChainProfile),
}


def iter_tutorbot_knowledge_chain_profiles() -> tuple[TutorBotKnowledgeChainProfile, ...]:
    return TUTORBOT_KNOWLEDGE_CHAIN_PROFILES


def resolve_tutorbot_knowledge_chain_profile(
    *,
    bot_id: str | None = None,
    interaction_profile: str | None = None,
) -> TutorBotKnowledgeChainProfile | None:
    normalized_bot_id = _normalize(bot_id)
    normalized_interaction_profile = _normalize(interaction_profile)
    for profile in TUTORBOT_KNOWLEDGE_CHAIN_PROFILES:
        if normalized_bot_id and normalized_bot_id in {_normalize(item) for item in profile.bot_ids}:
            return profile
        if normalized_interaction_profile and normalized_interaction_profile in {
            _normalize(item) for item in profile.interaction_profiles
        }:
            return profile
    return None


def export_tutorbot_profile_contract() -> dict[str, Any]:
    return {
        "profiles": [profile.model_dump(exclude_none=True) for profile in TUTORBOT_KNOWLEDGE_CHAIN_PROFILES],
        "schemas": {key: dict(value) for key, value in TUTORBOT_KNOWLEDGE_CHAIN_PROFILE_SCHEMAS.items()},
    }


__all__ = [
    "CONSTRUCTION_EXAM_TUTORBOT_PROFILE",
    "TUTORBOT_KNOWLEDGE_CHAIN_PROFILES",
    "TUTORBOT_KNOWLEDGE_CHAIN_PROFILE_SCHEMAS",
    "TutorBotKnowledgeChainProfile",
    "export_tutorbot_profile_contract",
    "iter_tutorbot_knowledge_chain_profiles",
    "resolve_tutorbot_knowledge_chain_profile",
]
