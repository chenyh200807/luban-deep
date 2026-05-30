"""TDD for the additive semantic-router decision telemetry tuple.

Closes the 3 instrumentation breakpoints from the 2026-05-30 baseline:
  1. raw input captured in-place (not post-join)
  2. final executed capability + drove_route (decision vs lifecycle override)
  3. non-discriminative default/fallback decisions explicitly flagged

The function is pure (no IO) so it is behavior-preserving by construction —
it only reads metadata that the orchestrator already set and never changes any
routing decision.
"""
from __future__ import annotations

from deeptutor.services.semantic_router_telemetry import build_semantic_router_telemetry


def test_primary_mode_marks_decision_as_having_driven_route() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "route_to_grading",
                "confidence": 0.92,
                "reason": "用户消息是'我选B'，提交当前题目答案。",
                "relation_to_active_object": "answer_active_object",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="我选B",
    )

    assert telemetry["drove_route"] is True
    assert telemetry["mode"] == "primary"
    assert telemetry["final_executed_capability"] == "deep_question"
    assert telemetry["captured_raw_input"] == "我选B"
    assert telemetry["semantic_decision"]["next_action"] == "route_to_grading"
    assert telemetry["semantic_decision"]["confidence"] == 0.92
    assert telemetry["is_default_template"] is False


def test_lifecycle_override_marks_decision_as_not_driving_route() -> None:
    # Lifecycle decided deep_question before the semantic router; the recorded
    # turn_semantic_decision was bookkeeping only.
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "question_lifecycle",
            "turn_semantic_decision": {
                "next_action": "route_to_generation",
                "confidence": 0.7,
                "reason": "active-object bookkeeping",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="出道题",
    )

    assert telemetry["drove_route"] is False
    assert telemetry["mode"] == "question_lifecycle"


def test_decision_capability_mismatch_with_chat_is_not_driving() -> None:
    # Decision said generation but the turn actually ran as chat (the 18% bucket).
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "disabled",
            "turn_semantic_decision": {
                "next_action": "route_to_generation",
                "confidence": 0.7,
                "reason": "当前 session 仍在开放对话，但输入明显转入新练题对象。",
            },
        },
        final_executed_capability="chat",
        captured_raw_input="建筑构造是什么？",
    )

    assert telemetry["drove_route"] is False
    assert telemetry["final_executed_capability"] == "chat"


def test_default_template_reason_is_flagged() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "route_to_generation",
                "confidence": 0.7,
                "reason": "当前 session 仍在开放对话，但输入明显转入新练题对象。",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="",
    )

    assert telemetry["is_default_template"] is True


def test_deterministic_fallback_reason_is_flagged() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "route_to_followup_explainer",
                "confidence": 0.55,
                "reason": "deterministic fallback 命中题目追问特征，作为语义降级保底。",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="我选C",
    )

    assert telemetry["is_default_template"] is True


def test_hold_and_wait_zero_confidence_is_flagged_non_discriminative() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "hold_and_wait",
                "confidence": 0.0,
                "reason": "uncertain",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="为什么",
    )

    assert telemetry["is_default_template"] is True


def test_missing_decision_is_safe() -> None:
    telemetry = build_semantic_router_telemetry(
        context_metadata={},
        final_executed_capability="chat",
        captured_raw_input="你好",
    )

    assert telemetry["drove_route"] is False
    assert telemetry["mode"] == ""
    assert telemetry["semantic_decision"] == {}
    assert telemetry["is_default_template"] is False
    assert telemetry["captured_raw_input"] == "你好"


def test_build_telemetry_event_payload_is_internal_turn_event() -> None:
    from deeptutor.services.semantic_router_telemetry import (
        build_semantic_router_telemetry_event,
    )

    event = build_semantic_router_telemetry_event(
        context_metadata={
            "semantic_router_mode": "primary",
            "turn_semantic_decision": {
                "next_action": "route_to_grading",
                "confidence": 0.92,
                "reason": "用户消息是'我选B'。",
            },
        },
        final_executed_capability="deep_question",
        captured_raw_input="我选B",
    )

    assert event["type"] == "observation"
    assert event["source"] == "turn_runtime"
    assert event["stage"] == "semantic_router_telemetry"
    assert event["visibility"] == "internal"
    tele = event["metadata"]["semantic_router_telemetry"]
    assert tele["drove_route"] is True
    assert tele["captured_raw_input"] == "我选B"
    assert tele["final_executed_capability"] == "deep_question"
