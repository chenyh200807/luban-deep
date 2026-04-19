from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TurnStatus = Literal["idle", "running", "completed", "failed", "cancelled"]
StreamTransport = Literal["websocket"]
TurnEventVisibility = Literal["public", "internal"]
ActiveObjectType = Literal[
    "question_set",
    "single_question",
    "guide_page",
    "study_plan",
    "open_chat_topic",
]
TurnSemanticRelation = Literal[
    "answer_active_object",
    "revise_answer_on_active_object",
    "ask_about_active_object",
    "continue_same_learning_flow",
    "switch_to_new_object",
    "temporary_detour",
    "out_of_scope_chat",
    "uncertain",
]
TurnSemanticNextAction = Literal[
    "route_to_grading",
    "route_to_followup_explainer",
    "route_to_generation",
    "route_to_guide",
    "route_to_general_chat",
    "route_to_account_or_product_help",
    "ask_clarifying_question",
    "hold_and_wait",
]
TurnSemanticAllowedPatch = Literal[
    "update_answer_slot",
    "append_answer_slots",
    "set_active_object",
    "suspend_current_object",
    "resume_suspended_object",
    "clear_active_object",
    "no_state_change",
]
TurnEventType = Literal[
    "stage_start",
    "stage_end",
    "thinking",
    "observation",
    "content",
    "tool_call",
    "tool_result",
    "progress",
    "sources",
    "result",
    "error",
    "session",
    "done",
]


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


class UnifiedTurnStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TurnEventType
    source: str = ""
    stage: str = ""
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    visibility: TurnEventVisibility = "public"
    session_id: str = ""
    turn_id: str = ""
    seq: int = 0
    timestamp: float | None = None


class UnifiedTurnObjectRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: ActiveObjectType | Literal[""] = ""
    object_id: str = ""


class UnifiedTurnActiveObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: ActiveObjectType
    object_id: str
    scope: dict[str, Any] = Field(default_factory=dict)
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    entered_at: str = ""
    last_touched_at: str = ""
    source_turn_id: str = ""


class UnifiedTurnSuspendedObjectStack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UnifiedTurnActiveObject] = Field(default_factory=list)


class UnifiedTurnSemanticDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_to_active_object: TurnSemanticRelation
    next_action: TurnSemanticNextAction
    allowed_patch: list[TurnSemanticAllowedPatch] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    target_object_ref: UnifiedTurnObjectRef = Field(default_factory=UnifiedTurnObjectRef)


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
    "turn_stream_event": _build_schema(UnifiedTurnStreamEvent),
    "active_object": _build_schema(UnifiedTurnActiveObject),
    "suspended_object_stack": _build_schema(UnifiedTurnSuspendedObjectStack),
    "turn_semantic_decision": _build_schema(UnifiedTurnSemanticDecision),
}


def export_unified_turn_contract() -> dict[str, Any]:
    return {
        "version": 2,
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
    "execution_engine",
    "bot_id",
    "tool_calls",
    "sources",
    "authority_applied",
    "source",
    "interaction_profile",
    "chat_mode",
    "active_object",
    "suspended_object_stack",
    "turn_semantic_decision",
    "question_followup_context",
    "semantic_router_mode",
    "semantic_router_mode_reason",
    "semantic_router_scope",
    "semantic_router_scope_match",
    "semantic_router_shadow_decision",
    "semantic_router_shadow_route",
    "semantic_router_selected_capability",
    "context_route",
    "task_anchor_type",
    "escalation_level",
    "route_confidence",
    "loaded_sources",
    "candidate_sources",
    "excluded_sources",
    "token_budget_total",
    "token_budget_used",
    "token_budget_by_source",
    "compression_applied",
    "history_search_applied",
    "fallback_path",
    "exact_question",
    "authoritative_answer",
    "corrected_from",
    "visibility",
    "assistant_content_source",
)


__all__ = [
    "TurnStatus",
    "ActiveObjectType",
    "UNIFIED_TURN_TRACE_FIELDS",
    "UNIFIED_TURN_SCHEMAS",
    "UnifiedTurnActiveObject",
    "UnifiedBotSummary",
    "UnifiedConversationSummary",
    "UnifiedTurnObjectRef",
    "UnifiedTurnCancelMessage",
    "UnifiedTurnResumeMessage",
    "UnifiedTurnSemanticDecision",
    "UnifiedTurnStartMessage",
    "UnifiedTurnStartResponse",
    "UnifiedTurnStreamBootstrap",
    "UnifiedTurnStreamEvent",
    "UnifiedTurnSuspendedObjectStack",
    "UnifiedTurnSubscribeMessage",
    "UnifiedTurnSubscribeSessionMessage",
    "UnifiedTurnSummary",
    "UnifiedTurnUnsubscribeMessage",
    "build_turn_stream_bootstrap",
    "export_unified_turn_contract",
]
