from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TurnStatus = Literal["idle", "running", "completed", "failed", "cancelled"]
StreamTransport = Literal["websocket"]


class UnifiedTurnStartMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["message", "start_turn"]
    content: str
    capability: str | None = None
    session_id: str | None = None
    tools: list[str] = Field(default_factory=list)
    knowledge_bases: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    language: str = "en"
    config: dict[str, Any] = Field(default_factory=dict)
    notebook_references: list[dict[str, Any]] = Field(default_factory=list)
    history_references: list[str] = Field(default_factory=list)


class UnifiedTurnSubscribeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["subscribe_turn"]
    turn_id: str
    after_seq: int = 0


class UnifiedTurnResumeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["resume_from"]
    turn_id: str
    seq: int = 0


class UnifiedTurnSubscribeSessionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["subscribe_session"]
    session_id: str
    after_seq: int = 0


class UnifiedTurnCancelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["cancel_turn"]
    turn_id: str


class UnifiedTurnUnsubscribeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["unsubscribe"]
    turn_id: str | None = None
    session_id: str | None = None


class UnifiedTurnSubscribePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["subscribe_turn"] = "subscribe_turn"
    turn_id: str
    after_seq: int = 0


class UnifiedTurnResumePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["resume_from"] = "resume_from"
    turn_id: str
    seq: int = 0


class UnifiedTurnStreamBootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: StreamTransport = "websocket"
    url: str = "/api/v1/ws"
    chat_id: str
    subscribe: UnifiedTurnSubscribePayload
    resume: UnifiedTurnResumePayload


class UnifiedTurnSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    capability: str
    status: TurnStatus


class UnifiedConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    created_at: str


class UnifiedBotSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class UnifiedTurnStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: UnifiedConversationSummary
    turn: UnifiedTurnSummary
    bot: UnifiedBotSummary | None = None
    stream: UnifiedTurnStreamBootstrap


def _build_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    return model_type.model_json_schema(mode="validation")


def build_turn_stream_bootstrap(*, session_id: str, turn_id: str) -> dict[str, Any]:
    return UnifiedTurnStreamBootstrap(
        chat_id=session_id,
        subscribe=UnifiedTurnSubscribePayload(turn_id=turn_id, after_seq=0),
        resume=UnifiedTurnResumePayload(turn_id=turn_id, seq=0),
    ).model_dump(exclude_none=True)


UNIFIED_TURN_SCHEMAS: dict[str, dict[str, Any]] = {
    "start_turn_message": _build_schema(UnifiedTurnStartMessage),
    "subscribe_turn_message": _build_schema(UnifiedTurnSubscribeMessage),
    "resume_turn_message": _build_schema(UnifiedTurnResumeMessage),
    "subscribe_session_message": _build_schema(UnifiedTurnSubscribeSessionMessage),
    "cancel_turn_message": _build_schema(UnifiedTurnCancelMessage),
    "unsubscribe_message": _build_schema(UnifiedTurnUnsubscribeMessage),
    "turn_start_response": _build_schema(UnifiedTurnStartResponse),
}


def export_unified_turn_contract() -> dict[str, Any]:
    return {
        "version": 1,
        "transport": {"primary_websocket": "/api/v1/ws"},
        "schemas": {key: dict(value) for key, value in UNIFIED_TURN_SCHEMAS.items()},
        "trace_fields": list(UNIFIED_TURN_TRACE_FIELDS),
        "docs": {
            "contract": "/CONTRACT.md",
            "guide": "/docs/zh/guide/unified-turn-contract.md",
        },
    }


UNIFIED_TURN_TRACE_FIELDS: tuple[str, ...] = (
    "session_id",
    "turn_id",
    "capability",
    "bot_id",
    "knowledge_chain_profile",
    "knowledge_chain_source",
    "source",
    "interaction_profile",
    "chat_mode",
    "question_followup_context",
    "exact_question",
    "authoritative_answer",
    "corrected_from",
)


__all__ = [
    "TurnStatus",
    "UNIFIED_TURN_TRACE_FIELDS",
    "UNIFIED_TURN_SCHEMAS",
    "UnifiedBotSummary",
    "UnifiedConversationSummary",
    "UnifiedTurnCancelMessage",
    "UnifiedTurnResumeMessage",
    "UnifiedTurnStartMessage",
    "UnifiedTurnStartResponse",
    "UnifiedTurnStreamBootstrap",
    "UnifiedTurnSubscribeMessage",
    "UnifiedTurnSubscribeSessionMessage",
    "UnifiedTurnSummary",
    "UnifiedTurnUnsubscribeMessage",
    "build_turn_stream_bootstrap",
    "export_unified_turn_contract",
]
