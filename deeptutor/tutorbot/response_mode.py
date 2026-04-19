from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TutorBotResponseMode = Literal["smart", "fast", "deep"]
ResponseDensity = Literal["short", "balanced", "detailed"]


@dataclass(frozen=True)
class ModeExecutionPolicy:
    requested_mode: TutorBotResponseMode
    effective_mode: TutorBotResponseMode
    max_tool_rounds: int
    allow_deep_stage: bool
    response_density: ResponseDensity
    latency_budget_ms: int
    response_mode_degrade_reason: str = ""


def normalize_requested_response_mode(value: Any) -> TutorBotResponseMode:
    if value is None:
        return "smart"

    normalized = str(value).strip().lower()
    if normalized in {"fast", "deep"}:
        return normalized
    return "smart"


def resolve_requested_response_mode(
    chat_mode: Any,
    interaction_hints: dict[str, Any] | None,
) -> TutorBotResponseMode:
    hints = interaction_hints or {}

    if chat_mode is not None and str(chat_mode).strip():
        return normalize_requested_response_mode(chat_mode)

    if "requested_response_mode" in hints:
        return normalize_requested_response_mode(
            hints.get("requested_response_mode"),
        )

    if "teaching_mode" in hints:
        return normalize_requested_response_mode(hints.get("teaching_mode"))

    return "smart"


def build_mode_execution_policy(mode: Any) -> ModeExecutionPolicy:
    effective_mode = normalize_requested_response_mode(mode)

    if effective_mode == "fast":
        return ModeExecutionPolicy(
            requested_mode=effective_mode,
            effective_mode=effective_mode,
            max_tool_rounds=1,
            allow_deep_stage=False,
            response_density="short",
            latency_budget_ms=6000,
        )

    if effective_mode == "deep":
        return ModeExecutionPolicy(
            requested_mode=effective_mode,
            effective_mode=effective_mode,
            max_tool_rounds=4,
            allow_deep_stage=True,
            response_density="detailed",
            latency_budget_ms=20000,
        )

    return ModeExecutionPolicy(
        requested_mode="smart",
        effective_mode="smart",
        max_tool_rounds=2,
        allow_deep_stage=False,
        response_density="balanced",
        latency_budget_ms=12000,
    )
