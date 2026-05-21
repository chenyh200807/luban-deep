"""
plan §Phase 3 Step 3.2 / Batch C Gap 3 — public boundary redaction.

测试在 ``/api/v1/ws`` 出库 stream event 时，hidden grading authority 不应泄露。
"""

from __future__ import annotations

import json

import pytest

from deeptutor.api.routers.unified_ws import (
    _redact_active_object_for_public,
    _redact_event_for_public,
    _redact_metadata_for_public,
)


def test_redact_event_drops_grading_key_from_metadata() -> None:
    event = {
        "type": "result",
        "metadata": {
            "question_followup_context": {
                "question_id": "qs_1",
                "items": [
                    {
                        "question_id": "q_1",
                        "question": "Q1",
                        "correct_answer": "B",
                        "explanation": "hidden",
                        "grading_key": {"correct_answer": "B", "scoring_points": ["sp1"]},
                    }
                ],
            },
            "active_object": {
                "object_type": "question_set",
                "state_snapshot": {
                    "question_id": "qs_1",
                    "correct_answer": "B",
                    "items": [
                        {"question_id": "q_1", "correct_answer": "B", "grading_key": {"correct_answer": "B"}}
                    ],
                },
            },
            "scoring_points": ["should be redacted"],
            "grading_key": {"correct_answer": "B"},
        },
    }
    redacted = _redact_event_for_public(event)
    blob = json.dumps(redacted, ensure_ascii=False)
    for forbidden in ("grading_key", "scoring_points", "correct_answer", "explanation", "hidden"):
        assert forbidden not in blob, f"public event leaked {forbidden}"
    # 非 metadata 部分保留
    assert redacted["type"] == "result"
    # 关键 question_id 仍保留供前端定位
    assert "q_1" in blob


def test_redact_event_keeps_safe_fields_intact() -> None:
    event = {
        "type": "stage_end",
        "content": "本题已生成",
        "metadata": {
            "presentation": {"blocks": [{"type": "question", "id": "q_1"}]},
            "question_followup_context": {
                "question_id": "q_1",
                "question": "Hello?",
                "options": {"A": "a", "B": "b"},
            },
        },
    }
    redacted = _redact_event_for_public(event)
    assert redacted["content"] == "本题已生成"
    # presentation 不应被破坏
    assert redacted["metadata"]["presentation"]["blocks"][0]["id"] == "q_1"
    # question / options 仍可见
    qctx = redacted["metadata"]["question_followup_context"]
    assert qctx["options"]["A"] == "a"


def test_redact_active_object_state_snapshot_drops_grading_key() -> None:
    ao = {
        "object_type": "question_set",
        "state_snapshot": {
            "question_id": "qs",
            "correct_answer": "A",
            "explanation": "hidden",
            "items": [
                {"question_id": "q1", "correct_answer": "A", "grading_key": {"correct_answer": "A"}}
            ],
        },
    }
    cleaned = _redact_active_object_for_public(ao)
    snap = cleaned["state_snapshot"]
    blob = json.dumps(snap, ensure_ascii=False)
    for forbidden in ("grading_key", "correct_answer", "explanation"):
        assert forbidden not in blob, f"active_object snapshot leaked {forbidden}"


def test_redact_metadata_recursively_clears_nested_metadata() -> None:
    metadata = {
        "metadata": {
            "question_followup_context": {
                "question_id": "qs_2",
                "items": [
                    {"question_id": "q_2", "grading_key": {"correct_answer": "C"}, "explanation": "leak"}
                ],
            }
        }
    }
    cleaned = _redact_metadata_for_public(metadata)
    blob = json.dumps(cleaned, ensure_ascii=False)
    for forbidden in ("grading_key", "explanation", "leak", "correct_answer"):
        assert forbidden not in blob


def test_redact_event_no_metadata_passthrough() -> None:
    event = {"type": "session", "session_id": "s1"}
    assert _redact_event_for_public(event) == event
