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


# plan §Phase 3 Step 3.2 — progress events such as deep_question generation
# observations expose ``metadata.question.correct_answer`` / ``grading_key`` /
# ``explanation`` directly on a generic dict that is NOT one of the canonical
# redacted surfaces (question_followup_context / active_object). The public
# boundary must drop those keys at any nesting depth.
def test_redact_metadata_question_subobject_drops_hidden_keys() -> None:
    event = {
        "type": "progress",
        "visibility": "internal",
        "stage": "generation",
        "metadata": {
            "question": {
                "question_id": "q_demo",
                "stem": "请选择正确答案",
                "options": [{"id": "A", "text": "alpha"}, {"id": "B", "text": "beta"}],
                "correct_answer": "A",
                "grading_key": {"correct_answer": "A", "scoring_points": ["sp1"]},
                "explanation": "因为 alpha 才对……",
            }
        },
    }
    redacted = _redact_event_for_public(event)
    question = redacted["metadata"]["question"]
    for forbidden in ("correct_answer", "grading_key", "explanation"):
        assert forbidden not in question, f"metadata.question still leaks {forbidden}"
    # 安全字段保留
    assert question["question_id"] == "q_demo"
    assert question["stem"] == "请选择正确答案"
    assert question["options"][0]["id"] == "A"


def test_redact_metadata_drops_hidden_keys_in_list_items() -> None:
    metadata = {
        "questions": [
            {
                "question_id": "q_1",
                "correct_answer": "A",
                "grading_key": {"correct_answer": "A"},
                "explanation": "leak1",
            },
            {
                "question_id": "q_2",
                "scoring_points": ["leak-sp"],
                "stem": "ok",
            },
        ]
    }
    redacted = _redact_metadata_for_public(metadata)
    blob = json.dumps(redacted, ensure_ascii=False)
    for forbidden in ("correct_answer", "grading_key", "explanation", "scoring_points", "leak1", "leak-sp"):
        assert forbidden not in blob, f"list items still leak {forbidden}"
    assert redacted["questions"][0]["question_id"] == "q_1"
    assert redacted["questions"][1]["stem"] == "ok"


def test_redact_metadata_drops_hidden_keys_in_deeply_nested_dict() -> None:
    metadata = {
        "audit": {
            "trace": {
                "samples": [
                    {
                        "name": "sample-A",
                        "payload": {
                            "question": {
                                "stem": "Q?",
                                "correct_answer": "B",
                                "grading_key": {"scoring_points": ["sp"]},
                            }
                        },
                    }
                ]
            }
        }
    }
    redacted = _redact_metadata_for_public(metadata)
    blob = json.dumps(redacted, ensure_ascii=False)
    for forbidden in ("correct_answer", "grading_key", "scoring_points"):
        assert forbidden not in blob, f"deeply nested leak: {forbidden}"
    assert (
        redacted["audit"]["trace"]["samples"][0]["payload"]["question"]["stem"] == "Q?"
    )


def test_redact_metadata_preserves_string_bodies_and_non_hidden_keys() -> None:
    # 用户可见 markdown 正文（例如 ``content`` / ``response``）含 "正确答案" 之类的
    # 解释文本，不应被字符串替换；只 drop hidden dict key。
    metadata = {
        "presentation": {"blocks": [{"type": "markdown", "text": "Q1 正确答案 是 A"}]},
        "response": "请看下面的解析与正确答案：……",
        "tool_traces": [],
    }
    redacted = _redact_metadata_for_public(metadata)
    assert redacted["presentation"]["blocks"][0]["text"] == "Q1 正确答案 是 A"
    assert redacted["response"] == "请看下面的解析与正确答案：……"
    assert redacted["tool_traces"] == []
