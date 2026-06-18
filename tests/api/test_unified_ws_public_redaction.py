"""
plan §Phase 3 Step 3.2 / Batch C Gap 3 — public boundary redaction.

测试在 ``/api/v1/ws`` 出库 stream event 时，hidden grading authority 不应泄露。
"""

from __future__ import annotations

import json

import pytest

from deeptutor.api.routers.unified_ws import (
    _MAX_PUBLIC_CONTENT_CHARS,
    _MAX_PUBLIC_METADATA_STR_CHARS,
    _PUBLIC_TRUNCATION_MARKER,
    _clamp_event_for_public,
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


# plan §Phase 3 Step 3.2 — MCQGradingResult.evidence_refs[i] entries describe
# which source field produced the evidence. When ``field`` references a hidden
# authority, the sibling ``value`` / ``content`` slot leaks the hidden value.
# The public boundary must drop the whole entry, not just the key.
def test_redact_metadata_drops_evidence_entry_with_hidden_field() -> None:
    event = {
        "type": "result",
        "metadata": {
            "construction_grading_result": {
                "user_answer": "A",
                "evidence_refs": [
                    {"source": "questions_bank", "field": "correct_answer", "value": "B"},
                    {"source": "questions_bank", "field": "grading_key", "value": {"correct_answer": "B"}},
                    {"source": "questions_bank", "field": "knowledge_point", "value": "安全管理"},
                    {"source": "syllabus", "field": "article", "value": "GB-2021-XX"},
                ],
            }
        },
    }
    redacted = _redact_event_for_public(event)
    blob = json.dumps(redacted, ensure_ascii=False)
    # Hidden entries are dropped entirely (key + sibling value gone)
    assert '"correct_answer"' not in blob
    assert '"grading_key"' not in blob
    # Safe entries survive
    refs = redacted["metadata"]["construction_grading_result"]["evidence_refs"]
    assert len(refs) == 2
    assert any(r["field"] == "knowledge_point" and r["value"] == "安全管理" for r in refs)
    assert any(r["field"] == "article" and r["value"] == "GB-2021-XX" for r in refs)


def test_redact_metadata_drops_evidence_entry_via_source_field_alias() -> None:
    metadata = {
        "evidence_refs": [
            {"source": "qb", "source_field": "correct_answer", "content": "B"},
            {"source": "qb", "source_key": "scoring_points", "content": ["sp"]},
            {"source": "qb", "name": "explanation", "content": "hidden"},
            {"source": "qb", "field": "stem", "content": "题干文字"},
        ]
    }
    redacted = _redact_metadata_for_public(metadata)
    refs = redacted["evidence_refs"]
    assert len(refs) == 1
    assert refs[0]["field"] == "stem"
    assert refs[0]["content"] == "题干文字"


def test_redact_metadata_filters_source_fields_list() -> None:
    metadata = {
        "rubric_items": [
            {
                "criterion": "考点 A",
                "source_fields": ["explanation", "correct_answer", "stem", "options"],
                "evidence_text": "用户写到了关键步骤",
            },
            {
                "criterion": "考点 B",
                "source_fields": ["explanation", "scoring_points"],
                "evidence_text": "全部 source_fields 都是 hidden — 整个 slot 应被 drop",
            },
        ]
    }
    redacted = _redact_metadata_for_public(metadata)
    items = redacted["rubric_items"]
    # First entry: hidden source_fields filtered out, safe ones kept
    assert items[0]["source_fields"] == ["stem", "options"]
    assert items[0]["evidence_text"] == "用户写到了关键步骤"
    # Second entry: source_fields slot dropped entirely; rest preserved
    assert "source_fields" not in items[1]
    assert items[1]["criterion"] == "考点 B"


def test_redact_metadata_drops_pgo_official_answer_fields() -> None:
    event = {
        "type": "result",
        "metadata": {
            "pgo_shadow_result": {
                "question_id": "case_1",
                "official_slice": "应由见证人员记录其取样、现场检测情况",
                "atomic_official_slice": "应由见证人员记录其取样、现场检测情况",
                "official_sub_answer_verbatim": "参考答案逐字片段",
                "official_analysis": "官方解析逐字文本",
                "term_provenance": [{"term": "见证记录", "chunk_id": "c1"}],
                "flaw_span": "试验员如实记录了其取样",
                "correction_span": "应由见证人员记录其取样",
                "base_rule": "见证记录应由见证人员制作",
                "exception_items": ["例外逐字文本"],
                "evidence_refs": [
                    {"source": "pgo", "field": "official_slice", "value": "应由见证人员记录其取样"},
                    {"source": "pgo", "source_field": "pgo.atomic_official_slice", "content": "官方切片路径泄露"},
                    {"source": "student", "field": "student_evidence_span", "value": "学生写了见证人员记录"},
                ],
                "source_fields": ["pgo.atomic_official_slice", "stem"],
                "student_evidence_span": "学生写了见证人员记录",
            }
        },
    }

    redacted = _redact_event_for_public(event)
    blob = json.dumps(redacted, ensure_ascii=False)

    for forbidden in (
        "official_slice",
        "atomic_official_slice",
        "official_sub_answer_verbatim",
        "official_analysis",
        "term_provenance",
        "flaw_span",
        "correction_span",
        "base_rule",
        "exception_items",
        "参考答案逐字片段",
        "官方解析逐字文本",
        "试验员如实记录",
        "官方切片路径泄露",
    ):
        assert forbidden not in blob, f"public WS leaked PGO authority field {forbidden}"
    refs = redacted["metadata"]["pgo_shadow_result"]["evidence_refs"]
    assert refs == [{"source": "student", "field": "student_evidence_span", "value": "学生写了见证人员记录"}]
    assert redacted["metadata"]["pgo_shadow_result"]["source_fields"] == ["stem"]
    assert redacted["metadata"]["pgo_shadow_result"]["student_evidence_span"] == "学生写了见证人员记录"


def test_redact_metadata_drops_grading_authority_metadata_fields() -> None:
    event = {
        "type": "result",
        "metadata": {
            "luban_case_rubric_v1": {
                "quality_gates": {
                    "score_authority": "official_total_x_verdict_coverage",
                    "per_point_score_authority": "pending_calibration_not_official",
                    "answer_key_authority": "signed_registry_only",
                    "official_total_score_authority": "official_answer_verbatim",
                },
                "public_status": "ok",
            },
            "evidence_refs": [
                {"field": "answer_key_authority", "value": "signed_registry_only"},
                {"field": "public_status", "value": "ok"},
            ],
            "source_fields": ["answer_key_authority", "public_status"],
        },
    }

    redacted = _redact_event_for_public(event)
    blob = json.dumps(redacted, ensure_ascii=False)
    for forbidden in (
        "score_authority",
        "per_point_score_authority",
        "answer_key_authority",
        "official_total_score_authority",
        "official_answer_verbatim",
        "signed_registry_only",
    ):
        assert forbidden not in blob
    assert redacted["metadata"]["luban_case_rubric_v1"]["public_status"] == "ok"
    assert redacted["metadata"]["evidence_refs"] == [{"field": "public_status", "value": "ok"}]
    assert redacted["metadata"]["source_fields"] == ["public_status"]


def test_redact_metadata_drops_evidence_inside_question_followup_context() -> None:
    """Nested evidence within ``metadata.question_followup_context`` (handled by
    its own canonical redactor in services.question_followup) must also drop
    hidden-field entries — both boundaries must enforce the same rule."""

    event = {
        "type": "result",
        "metadata": {
            "question_followup_context": {
                "question_id": "qs",
                "items": [
                    {
                        "question_id": "q1",
                        "construction_grading_result": {
                            "user_answer": "A",
                            "evidence_refs": [
                                {"field": "correct_answer", "value": "B"},
                                {"field": "knowledge_point", "value": "安全管理"},
                            ],
                        },
                    }
                ],
            }
        },
    }
    redacted = _redact_event_for_public(event)
    blob = json.dumps(redacted, ensure_ascii=False)
    assert '"correct_answer"' not in blob
    refs = (
        redacted["metadata"]["question_followup_context"]["items"][0]
        ["construction_grading_result"]["evidence_refs"]
    )
    assert len(refs) == 1
    assert refs[0]["field"] == "knowledge_point"


def test_redact_metadata_drops_question_followup_answer_authority_fields() -> None:
    """Question follow-up context uses the shared hidden-key authority.

    Regression for a production audit finding where the WS redactor dropped
    ``correct_answer`` but delegated qctx redaction to a drifted key list that
    still leaked ``minimal_rationale`` and ``official_answer``.
    """

    event = {
        "type": "result",
        "metadata": {
            "question_followup_context": {
                "question_id": "qs",
                "items": [
                    {
                        "question_id": "q1",
                        "user_answer": "A",
                        "minimal_rationale": "hidden rationale",
                        "official_answer": "hidden official answer",
                        "correct_answer": "B",
                    }
                ],
            }
        },
    }

    redacted = _redact_event_for_public(event)
    blob = json.dumps(redacted, ensure_ascii=False)
    for forbidden in (
        "minimal_rationale",
        "official_answer",
        "correct_answer",
        "hidden rationale",
        "hidden official answer",
    ):
        assert forbidden not in blob
    item = redacted["metadata"]["question_followup_context"]["items"][0]
    assert item == {"question_id": "q1", "user_answer": "A"}


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


# ── Oversized event payload clamp (public WS boundary only) ──────────────────
# Backport item: bound the size of the event copy sent to clients over
# /api/v1/ws. Persisted truth (turn_events) and canonical final answer
# (result.metadata.response materialised into messages.content) are NOT
# touched — clamping runs only on the outbound public copy, mirroring how
# _redact_event_for_public operates on a copy at the same boundary.


def test_clamp_event_passthrough_for_normal_event() -> None:
    event = {
        "type": "content",
        "content": "正常的一小段流式正文",
        "metadata": {"status": "running", "visibility": "public"},
        "seq": 3,
    }
    clamped = _clamp_event_for_public(event)
    assert clamped == event


def test_clamp_event_does_not_mutate_input() -> None:
    original_content = "x" * (_MAX_PUBLIC_CONTENT_CHARS + 5000)
    event = {"type": "content", "content": original_content, "metadata": {}}
    _clamp_event_for_public(event)
    # input untouched — clamp returns a new dict
    assert event["content"] == original_content
    assert len(event["content"]) == _MAX_PUBLIC_CONTENT_CHARS + 5000


def test_clamp_event_truncates_oversized_content() -> None:
    event = {
        "type": "content",
        "content": "字" * (_MAX_PUBLIC_CONTENT_CHARS + 2000),
        "metadata": {"status": "running"},
    }
    clamped = _clamp_event_for_public(event)
    assert clamped["content"].endswith(_PUBLIC_TRUNCATION_MARKER)
    assert len(clamped["content"]) == _MAX_PUBLIC_CONTENT_CHARS + len(_PUBLIC_TRUNCATION_MARKER)
    # essential metadata untouched
    assert clamped["metadata"]["status"] == "running"


def test_clamp_event_truncates_oversized_metadata_string_preserving_structure() -> None:
    huge_blob = "A" * (_MAX_PUBLIC_METADATA_STR_CHARS + 4000)
    event = {
        "type": "tool_result",
        "content": "ok",
        "metadata": {
            "status": "completed",
            "image_base64": huge_blob,
            "sources": [{"title": "ref", "url": "https://example.com"}],
            "nested": {"dump": huge_blob},
        },
    }
    clamped = _clamp_event_for_public(event)
    md = clamped["metadata"]
    # oversized strings truncated with marker, structure + small keys intact
    assert md["image_base64"].endswith(_PUBLIC_TRUNCATION_MARKER)
    assert len(md["image_base64"]) == _MAX_PUBLIC_METADATA_STR_CHARS + len(_PUBLIC_TRUNCATION_MARKER)
    assert md["nested"]["dump"].endswith(_PUBLIC_TRUNCATION_MARKER)
    assert md["status"] == "completed"
    assert md["sources"] == [{"title": "ref", "url": "https://example.com"}]
    assert clamped["content"] == "ok"


def test_clamp_event_preserves_short_strings_in_metadata() -> None:
    event = {
        "type": "result",
        "content": "短答案",
        "metadata": {"response": "这是 canonical 最终答案的展示投影，长度正常。", "status": "completed"},
    }
    clamped = _clamp_event_for_public(event)
    assert clamped["metadata"]["response"] == "这是 canonical 最终答案的展示投影，长度正常。"
    assert clamped == event


def test_clamp_composes_after_redaction_on_oversized_event_with_hidden_key() -> None:
    huge_blob = "B" * (_MAX_PUBLIC_METADATA_STR_CHARS + 3000)
    event = {
        "type": "tool_result",
        "content": "ok",
        "metadata": {
            "status": "completed",
            "correct_answer": "B",  # hidden authority — must be dropped by redaction
            "dump": huge_blob,  # oversized — must be clamped
        },
    }
    public = _clamp_event_for_public(_redact_event_for_public(event))
    assert "correct_answer" not in public["metadata"]
    assert public["metadata"]["dump"].endswith(_PUBLIC_TRUNCATION_MARKER)
    assert public["metadata"]["status"] == "completed"
