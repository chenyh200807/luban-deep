from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LearnerStateControlSurface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_key: Literal["user_id"] = "user_id"
    service: str = "LearnerStateService"
    writeback_entry: str = "structured_writeback_pipeline"
    heartbeat_subject: Literal["user_id"] = "user_id"
    summary_truth: Literal["learner_summaries"] = "learner_summaries"


class LearnerStateTableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: Literal["reused", "new"]
    source_truth: str
    fields: list[str] = Field(default_factory=list)
    read_paths: list[str] = Field(default_factory=list)
    write_paths: list[str] = Field(default_factory=list)


class LearnerStateContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    subject: Literal["learner_state"] = "learner_state"
    control_surface: LearnerStateControlSurface = Field(default_factory=LearnerStateControlSurface)
    runtime_read_order: list[str] = Field(default_factory=list)
    writeback_sources: list[str] = Field(default_factory=list)
    reused_tables: list[LearnerStateTableSpec] = Field(default_factory=list)
    new_tables: list[LearnerStateTableSpec] = Field(default_factory=list)
    phase_2_reserved_tables: list[LearnerStateTableSpec] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    docs: dict[str, str] = Field(default_factory=dict)


def _build_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    return model_type.model_json_schema(mode="validation")


LEARNER_STATE_CONTROL_SURFACE = LearnerStateControlSurface()

LEARNER_STATE_REUSED_TABLES: tuple[LearnerStateTableSpec, ...] = (
    LearnerStateTableSpec(
        name="user_profiles",
        role="reused",
        source_truth="learner profile",
        fields=[
            "user_id",
            "summary",
            "attributes",
            "last_updated",
        ],
        read_paths=[
            "TutorBot runtime",
            "Guided Learning",
            "Heartbeat",
            "profile/settings pages",
        ],
        write_paths=[
            "onboarding",
            "profile/settings",
            "controlled profile refinement",
        ],
    ),
    LearnerStateTableSpec(
        name="user_stats",
        role="reused",
        source_truth="learner progress",
        fields=[
            "user_id",
            "mastery_level",
            "knowledge_map",
            "current_question_context",
            "radar_history",
            "total_attempts",
            "error_count",
            "last_practiced_at",
            "last_updated",
            "tag",
        ],
        read_paths=[
            "TutorBot runtime",
            "quiz/review",
            "Guided Learning",
            "Heartbeat",
        ],
        write_paths=[
            "question/deep_question result merge",
            "review pipeline",
            "guided learning completion progress writer",
        ],
    ),
    LearnerStateTableSpec(
        name="user_goals",
        role="reused",
        source_truth="learner goals",
        fields=[
            "id",
            "user_id",
            "goal_type",
            "title",
            "target_node_codes",
            "target_question_count",
            "progress",
            "deadline",
            "created_at",
            "completed_at",
        ],
        read_paths=[
            "onboarding",
            "study plan generator",
            "Heartbeat",
            "TutorBot planning",
        ],
        write_paths=[
            "onboarding goal setting",
            "learning plan adjustment",
            "goal completion updates",
        ],
    ),
)

LEARNER_STATE_NEW_TABLES: tuple[LearnerStateTableSpec, ...] = (
    LearnerStateTableSpec(
        name="learner_summaries",
        role="new",
        source_truth="learner summary",
        fields=[
            "user_id",
            "summary_md",
            "summary_structured_json",
            "last_refreshed_from_turn_id",
            "last_refreshed_from_feature",
            "updated_at",
        ],
        read_paths=[
            "TutorBot runtime",
            "Guided Learning",
            "Notebook",
            "review aggregation",
        ],
        write_paths=[
            "session digest aggregator",
            "guided learning completion aggregator",
            "notebook summary aggregator",
        ],
    ),
    LearnerStateTableSpec(
        name="learner_memory_events",
        role="new",
        source_truth="learner memory events",
        fields=[
            "event_id",
            "user_id",
            "source_feature",
            "source_id",
            "source_bot_id",
            "memory_kind",
            "payload_json",
            "dedupe_key",
            "created_at",
        ],
        read_paths=[
            "summary rebuild",
            "progress rebuild",
            "audit / replay",
        ],
        write_paths=[
            "structured writeback pipeline",
        ],
    ),
    LearnerStateTableSpec(
        name="learning_plans",
        role="new",
        source_truth="learning plan",
        fields=[
            "plan_id",
            "user_id",
            "source_bot_id",
            "source_material_refs_json",
            "knowledge_points_json",
            "status",
            "current_index",
            "completion_summary_md",
            "created_at",
            "updated_at",
        ],
        read_paths=[
            "Guided Learning",
            "TutorBot planning",
            "Heartbeat",
        ],
        write_paths=[
            "guided learning plan creation",
            "guided learning plan adjustment",
        ],
    ),
    LearnerStateTableSpec(
        name="learning_plan_pages",
        role="new",
        source_truth="learning plan page state",
        fields=[
            "plan_id",
            "page_index",
            "page_status",
            "html_content",
            "error_message",
            "generated_at",
        ],
        read_paths=[
            "Guided Learning rendering",
        ],
        write_paths=[
            "guided learning page generation",
        ],
    ),
    LearnerStateTableSpec(
        name="heartbeat_jobs",
        role="new",
        source_truth="learner heartbeat schedule",
        fields=[
            "job_id",
            "user_id",
            "bot_id",
            "channel",
            "policy_json",
            "next_run_at",
            "last_run_at",
            "last_result_json",
            "failure_count",
            "status",
            "created_at",
            "updated_at",
        ],
        read_paths=[
            "heartbeat scheduler",
            "Heartbeat decisions",
        ],
        write_paths=[
            "heartbeat job creation",
            "heartbeat policy updates",
            "heartbeat execution logs",
        ],
    ),
)

LEARNER_STATE_PHASE_2_RESERVED_TABLES: tuple[LearnerStateTableSpec, ...] = (
    LearnerStateTableSpec(
        name="bot_learner_overlays",
        role="new",
        source_truth="bot-learner local overlay",
        fields=[
            "bot_id",
            "user_id",
            "local_focus_json",
            "active_plan_id",
            "teaching_policy_override_json",
            "heartbeat_override_json",
            "channel_presence_override_json",
            "local_notebook_scope_refs_json",
            "engagement_state_json",
            "promotion_candidates_json",
            "working_memory_projection_md",
            "version",
            "created_at",
            "updated_at",
        ],
        read_paths=[
            "TutorBot runtime phase 2",
            "Guided Learning phase 2",
            "heartbeat arbitration phase 2",
        ],
        write_paths=[
            "overlay patch pipeline",
            "promotion candidate append",
            "working memory projection refresh",
        ],
    ),
    LearnerStateTableSpec(
        name="bot_learner_overlay_events",
        role="new",
        source_truth="overlay event stream",
        fields=[
            "event_id",
            "bot_id",
            "user_id",
            "source_feature",
            "source_id",
            "patch_kind",
            "payload_json",
            "dedupe_key",
            "created_at",
        ],
        read_paths=[
            "overlay replay",
            "promotion pipeline",
            "audit / debugging",
        ],
        write_paths=[
            "overlay patch pipeline",
        ],
    ),
    LearnerStateTableSpec(
        name="bot_learner_overlay_audit",
        role="new",
        source_truth="overlay audit log",
        fields=[
            "audit_id",
            "bot_id",
            "user_id",
            "actor",
            "action",
            "fields_json",
            "metadata_json",
            "created_at",
        ],
        read_paths=[
            "operations audit",
            "support / debugging",
        ],
        write_paths=[
            "operations overrides",
            "critical overlay mutations",
        ],
    ),
)

LEARNER_STATE_RUNTIME_READ_ORDER: tuple[str, ...] = (
    "current input",
    "session state",
    "active question / current learning step",
    "learner profile",
    "learner summary",
    "learner progress",
    "notebook / guide references",
    "bot template",
)

LEARNER_STATE_WRITEBACK_SOURCES: tuple[str, ...] = (
    "chat",
    "guided_learning",
    "notebook",
    "quiz",
    "review",
    "heartbeat",
)

LEARNER_STATE_INVARIANTS: tuple[str, ...] = (
    "phase 1 learner state truth is keyed by user_id only",
    "user_profiles is the learner profile truth",
    "user_stats is the learner progress truth",
    "user_goals is the learner goals truth",
    "learner_summaries is the summary truth",
    "learner_memory_events is the unified long-term event stream",
    "heartbeat jobs are scheduled per user_id",
    "phase 2 overlay, if introduced, must remain local and subordinate to learner state truth",
    "TutorBot workspace memory must not override learner state truth",
)

LEARNER_STATE_DOCS: dict[str, str] = {
    "contract": "/contracts/learner-state.md",
    "prd": "/doc/plan/2026-04-15-learner-state-memory-guided-learning-prd.md",
    "supabase_appendix": "/doc/plan/2026-04-15-learner-state-supabase-schema-appendix.md",
    "service_design": "/doc/plan/2026-04-15-learner-state-service-design.md",
    "overlay_prd": "/doc/plan/2026-04-15-bot-learner-overlay-prd.md",
    "overlay_service_design": "/doc/plan/2026-04-15-bot-learner-overlay-service-design.md",
}

LEARNER_STATE_CONTRACT = LearnerStateContract(
    control_surface=LEARNER_STATE_CONTROL_SURFACE,
    runtime_read_order=list(LEARNER_STATE_RUNTIME_READ_ORDER),
    writeback_sources=list(LEARNER_STATE_WRITEBACK_SOURCES),
    reused_tables=list(LEARNER_STATE_REUSED_TABLES),
    new_tables=list(LEARNER_STATE_NEW_TABLES),
    phase_2_reserved_tables=list(LEARNER_STATE_PHASE_2_RESERVED_TABLES),
    invariants=list(LEARNER_STATE_INVARIANTS),
    docs=dict(LEARNER_STATE_DOCS),
)

LEARNER_STATE_SCHEMAS: dict[str, dict[str, Any]] = {
    "learner_state_contract": _build_schema(LearnerStateContract),
    "learner_state_control_surface": _build_schema(LearnerStateControlSurface),
    "learner_state_table_spec": _build_schema(LearnerStateTableSpec),
}


def export_learner_state_contract() -> dict[str, Any]:
    return {
        **LEARNER_STATE_CONTRACT.model_dump(exclude_none=True),
        "tables": {
            "reused": [table.model_dump(exclude_none=True) for table in LEARNER_STATE_REUSED_TABLES],
            "new": [table.model_dump(exclude_none=True) for table in LEARNER_STATE_NEW_TABLES],
            "phase_2_reserved": [
                table.model_dump(exclude_none=True) for table in LEARNER_STATE_PHASE_2_RESERVED_TABLES
            ],
        },
        "schemas": {key: dict(value) for key, value in LEARNER_STATE_SCHEMAS.items()},
    }


__all__ = [
    "LEARNER_STATE_CONTRACT",
    "LEARNER_STATE_CONTROL_SURFACE",
    "LEARNER_STATE_DOCS",
    "LEARNER_STATE_INVARIANTS",
    "LEARNER_STATE_NEW_TABLES",
    "LEARNER_STATE_PHASE_2_RESERVED_TABLES",
    "LEARNER_STATE_REUSED_TABLES",
    "LEARNER_STATE_RUNTIME_READ_ORDER",
    "LEARNER_STATE_SCHEMAS",
    "LEARNER_STATE_WRITEBACK_SOURCES",
    "LearnerStateContract",
    "LearnerStateControlSurface",
    "LearnerStateTableSpec",
    "export_learner_state_contract",
]
