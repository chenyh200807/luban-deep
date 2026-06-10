from __future__ import annotations

import asyncio
import base64
from contextvars import ContextVar
import importlib
import sqlite3
from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from deeptutor.capabilities.chat_mode import get_default_chat_mode
from deeptutor.contracts.unified_turn import UnifiedTurnStartMessage
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.services.config.provider_runtime import ResolvedLLMConfig
from deeptutor.services.semantic_router import build_active_object_from_question_context
from deeptutor.services.session.sqlite_store import (
    SQLiteSessionStore,
    build_active_object_from_session,
    build_user_owner_key,
)
from deeptutor.services.session.turn_runtime import (
    TurnRuntimeManager,
    _assistant_message_metadata,
    _billing_capture_amount_from_usage_summary,
    _build_turn_semantic_decision,
    _enrich_result_question_authority_from_trace,
    _learning_prompt_intent_trace_metadata,
    _LiveSubscriber,
    _request_snapshot_metadata,
    _resolve_question_followup_context_and_action,
    _result_active_object,
    _result_question_followup_context,
    _sanitize_public_terminal_event,
    _TurnExecution,
)

unified_ws_module = importlib.import_module("deeptutor.api.routers.unified_ws")


async def _noop_refresh(**_kwargs):
    return None


def _event_types_without_progress(events: list[dict[str, object]]) -> list[str]:
    return [str(event.get("type") or "") for event in events if event.get("type") != "progress"]


def test_unified_turn_start_schema_rejects_internal_snapshot_fields() -> None:
    with pytest.raises(ValidationError):
        UnifiedTurnStartMessage.model_validate(
            {
                "type": "start_turn",
                "content": "hello",
                "skills": ["proof-checker"],
                "memory_references": ["summary"],
            }
        )


def test_billing_capture_amount_prefers_measured_cost_summary() -> None:
    amount, metadata = _billing_capture_amount_from_usage_summary(
        {
            "total_cost_usd": 0.0351,
            "estimated_total_cost_usd": 0.0,
            "total_input_tokens": 1000,
            "total_output_tokens": 250,
            "total_tokens": 1250,
            "usage_accuracy": "measured",
            "usage_sources": {"provider": 1},
            "models": {"deepseek-v4-flash": 1},
        }
    )

    assert amount == 36
    assert metadata["billing_amount_source"] == "measured_cost"
    assert metadata["billing_cost_source"] == "measured_cost"
    assert metadata["billing_billable_cost"] == 0.0351
    assert metadata["billing_cost_points"] == 36
    assert metadata["usage_total_tokens"] == 1250
    assert metadata["usage_sources"] == {"provider": 1}
    assert metadata["usage_models"] == {"deepseek-v4-flash": 1}


def test_turn_runtime_question_domain_decision_uses_canonical_semantic_shape() -> None:
    decision = _build_turn_semantic_decision(
        active_object={"object_type": "single_question", "object_id": "q_1"},
        followup_question_action={
            "route": "submission",
            "intent": "revise_answers",
            "confidence": 0.92,
            "reason": "用户修正上一题答案。",
        },
    )

    assert decision == {
        "relation_to_active_object": "revise_answer_on_active_object",
        "next_action": "route_to_grading",
        "allowed_patch": ["update_answer_slot"],
        "confidence": 0.92,
        "reason": "用户修正上一题答案。",
        "target_object_ref": {"object_type": "single_question", "object_id": "q_1"},
    }


def test_turn_runtime_enriches_exact_question_authority_before_persisting_active_object() -> None:
    metadata = {
        "question_followup_context": {
            "question_id": "historical:height",
            "question": "历史建筑高度怎么算？",
            "question_type": "choice",
            "options": {"A": "檐口顶点", "B": "屋脊", "C": "墙顶点", "D": "最高点"},
            "user_answer": "C",
            "is_correct": False,
            "items": [
                {
                    "question_id": "historical:height",
                    "question": "历史建筑高度怎么算？",
                    "question_type": "choice",
                    "options": {
                        "A": "檐口顶点",
                        "B": "屋脊",
                        "C": "墙顶点",
                        "D": "最高点",
                    },
                    "user_answer": "C",
                    "is_correct": False,
                }
            ],
        },
        "active_object": {
            "object_id": "historical:height",
            "object_type": "single_question",
            "state_snapshot": {
                "question_id": "historical:height",
                "question": "历史建筑高度怎么算？",
                "question_type": "choice",
                "options": {
                    "A": "檐口顶点",
                    "B": "屋脊",
                    "C": "墙顶点",
                    "D": "最高点",
                },
                "user_answer": "C",
                "is_correct": False,
            },
        },
        "exact_question": {
            "id": "historical:height",
            "answer_kind": "mcq",
            "stem": "历史建筑高度怎么算？",
            "options": [
                {"key": "A", "value": "檐口顶点"},
                {"key": "B", "value": "屋脊"},
                {"key": "C", "value": "墙顶点"},
                {"key": "D", "value": "最高点"},
            ],
            "analysis": "应按室外设计地坪至建（构）筑物最高点计算。",
            "metadata": {"canonical_correct_answer": "D"},
        },
    }

    enriched = _enrich_result_question_authority_from_trace(metadata, metadata)

    context = enriched["question_followup_context"]
    snapshot = enriched["active_object"]["state_snapshot"]
    assert context["correct_answer"] == "D"
    assert snapshot["correct_answer"] == "D"
    assert context["items"][0]["correct_answer"] == "D"
    assert context["user_answer"] == "C"
    assert context["explanation"] == "应按室外设计地坪至建（构）筑物最高点计算。"


def test_learning_prompt_intent_trace_metadata_exports_only_gbrain_observability_fields() -> None:
    metadata = _learning_prompt_intent_trace_metadata(
        {
            "training_intent_id": "lti_123",
            "source": "home_dashboard",
            "concept_id": "concept_waterproof",
            "concept_label": "防水工程",
            "error_code": "waterproof_detail_confusion",
            "error_label": "节点构造混淆",
            "learning_signal_type": "home_prompt_clicked",
            "training_outcome": "improved",
            "evidence_refs": ["evt_1", "evt_2"],
            "attempt_refs": ["attempt_1"],
            "user_question": "我的手机号 13800001234，为什么错？",
            "prompt": "请讲解这道题",
        }
    )

    assert metadata == {
        "gbrain_training_intent_id": "lti_123",
        "gbrain_concept_id": "concept_waterproof",
        "gbrain_error_code": "waterproof_detail_confusion",
        "gbrain_evidence_ref_count": 2,
        "gbrain_attempt_ref_count": 1,
        "gbrain_prescription_authority": "training_intent",
        "gbrain_learning_signal_type": "home_prompt_clicked",
        "gbrain_training_outcome": "improved",
        "gbrain_prompt_source": "home_dashboard",
    }
    assert "user_question" not in metadata
    assert "prompt" not in metadata


class _LifecycleAuthorityStore:
    def __init__(self) -> None:
        self.created_turn_capability: str | None = None
        self.events: list[dict[str, object]] = []

    async def get_active_object(self, _session_id: str) -> None:
        return None

    async def ensure_session(self, session_id: str | None, *, owner_key: str | None = None) -> dict[str, object]:
        return {"id": session_id or "session-runtime-test", "preferences": {}}

    async def update_session_preferences(self, _session_id: str, _preferences: dict[str, object]) -> bool:
        return True

    async def list_active_turns(self, _session_id: str) -> list[dict[str, object]]:
        return []

    async def get_active_turn(self, _session_id: str) -> None:
        return None

    async def create_turn(self, session_id: str, capability: str) -> dict[str, object]:
        self.created_turn_capability = capability
        return {
            "id": "turn-runtime-test",
            "session_id": session_id,
            "status": "running",
            "capability": capability,
        }

    async def append_turn_event(self, _turn_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.events.append(payload)
        return payload


@pytest.mark.asyncio
async def test_turn_runtime_demotes_tutorbot_capability_hint_before_lifecycle_authority(monkeypatch) -> None:
    async def _no_run_turn(self: TurnRuntimeManager, _execution: object) -> None:
        return None

    monkeypatch.setattr(TurnRuntimeManager, "_run_turn", _no_run_turn)
    store = _LifecycleAuthorityStore()
    runtime = TurnRuntimeManager(store=store)  # type: ignore[arg-type]

    _session, turn = await runtime.start_turn(
        {
            "session_id": "session-runtime-test",
            "content": "用一道真题场景理解基础和地基的",
            "capability": "tutorbot",
            "config": {
                "bot_id": "construction-exam-coach",
                "general_knowledge_context": True,
                "grading_engine_textbook_knowledge": True,
                "interaction_profile": "tutorbot",
            },
            "language": "zh",
        }
    )

    assert store.created_turn_capability == ""
    assert turn["capability"] == ""
    execution = runtime._executions[turn["id"]]
    assert execution.capability == ""
    assert execution.payload["capability"] is None
    assert execution.payload["config"]["_entry_capability_hint"] == "tutorbot"
    assert execution.payload["config"]["general_knowledge_context"] is True
    assert execution.payload["config"]["grading_engine_textbook_knowledge"] is True
    if execution.task is not None:
        await asyncio.wait_for(execution.task, timeout=1)


def test_turn_runtime_result_context_does_not_parse_presentation_read_model() -> None:
    metadata = {
        "response": "第1题\nA. 选项A\nB. 选项B",
        "presentation": {
            "kind": "question_set",
            "fallback_text": "第1题\nA. 选项A\nB. 选项B",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题目",
                    "question_type": "choice",
                    "options": {"A": "选项A", "B": "选项B"},
                }
            ],
        },
    }

    assert _result_question_followup_context(metadata) is None
    assert _result_active_object(metadata) is None


def test_billing_capture_amount_uses_estimated_cost_when_measured_missing() -> None:
    amount, metadata = _billing_capture_amount_from_usage_summary(
        {
            "total_cost_usd": 0.0,
            "estimated_total_cost_usd": 0.057,
            "estimated_total_tokens": 3000,
            "usage_accuracy": "estimated",
            "usage_sources": {"estimated": 1},
        }
    )

    assert amount == 57
    assert metadata["billing_amount_source"] == "estimated_cost"
    assert metadata["billing_cost_source"] == "estimated_cost"
    assert metadata["usage_estimated_total_tokens"] == 3000


def test_billing_capture_amount_falls_back_to_minimum_when_cost_missing_or_tiny() -> None:
    missing_amount, missing_metadata = _billing_capture_amount_from_usage_summary(
        {
            "total_cost_usd": 0.0,
            "estimated_total_cost_usd": 0.0,
            "total_tokens": 800,
            "usage_accuracy": "unknown",
        }
    )
    tiny_amount, tiny_metadata = _billing_capture_amount_from_usage_summary(
        {"total_cost_usd": 0.001, "usage_accuracy": "measured"}
    )
    no_summary_amount, no_summary_metadata = _billing_capture_amount_from_usage_summary(None)

    assert missing_amount == 20
    assert missing_metadata["billing_amount_source"] == "fallback_minimum"
    assert missing_metadata["billing_cost_source"] == "missing_cost"
    assert tiny_amount == 20
    assert tiny_metadata["billing_amount_source"] == "fallback_minimum"
    assert tiny_metadata["billing_cost_source"] == "measured_cost"
    assert no_summary_amount == 20
    assert no_summary_metadata["billing_cost_source"] == "missing_usage_summary"


def test_request_snapshot_metadata_redacts_sensitive_fields() -> None:
    metadata = _request_snapshot_metadata(
        payload={
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "language": "zh",
            "llm_selection": {
                "provider": "openai",
                "api_key": "sk-secret",
                "headers": {"Authorization": "Bearer secret-token"},
            },
        },
        content="请分析这道题",
        capability="chat",
        config={
            "bot_id": "construction-exam-coach",
            "api_key": "config-secret",
            "nested": {"token": "nested-secret", "safe": "ok"},
        },
        attachments=[
            {
                "type": "file",
                "url": "store://session/att-1",
                "filename": "photo.png",
                "mime_type": "image/png",
                "base64": "aGVsbG8=",
            }
        ],
        notebook_references=[],
        history_references=[],
        question_notebook_references=[],
        book_references=[],
        requested_skills=[],
        memory_references=[],
        llm_selection={
            "provider": "openai",
            "api_key": "sk-secret",
            "headers": {"Authorization": "Bearer secret-token"},
        },
    )

    snapshot_text = str(metadata)
    assert "sk-secret" not in snapshot_text
    assert "config-secret" not in snapshot_text
    assert "nested-secret" not in snapshot_text
    assert "secret-token" not in snapshot_text
    snapshot = metadata["request_snapshot"]
    assert snapshot["config"]["api_key"] == "[redacted]"
    assert snapshot["config"]["nested"]["token"] == "[redacted]"
    assert snapshot["llmSelection"]["api_key"] == "[redacted]"
    assert snapshot["llmSelection"]["headers"]["Authorization"] == "[redacted]"
    assert snapshot["attachments"] == [
        {
            "type": "file",
            "url": "store://session/att-1",
            "filename": "photo.png",
            "mime_type": "image/png",
        }
    ]


def test_request_snapshot_metadata_persists_turn_identity_for_recovery() -> None:
    metadata = _request_snapshot_metadata(
        payload={"tools": [], "knowledge_bases": [], "language": "zh"},
        content="请批改这道案例题",
        capability="chat",
        config={"client_turn_id": "surface_turn_1"},
        attachments=[],
        notebook_references=[],
        history_references=[],
        question_notebook_references=[],
        book_references=[],
        requested_skills=[],
        memory_references=[],
        llm_selection=None,
        turn_id="turn_1",
    )

    assert metadata["turn_id"] == "turn_1"
    assert metadata["client_turn_id"] == "surface_turn_1"
    assert metadata["request_snapshot"]["config"]["client_turn_id"] == "surface_turn_1"


def test_assistant_message_metadata_persists_turn_identity_for_recovery() -> None:
    metadata = _assistant_message_metadata(
        turn_id="turn_1",
        config={"client_turn_id": "surface_turn_1"},
        terminal_status="completed",
    )

    assert metadata == {
        "turn_id": "turn_1",
        "engine_turn_id": "turn_1",
        "client_turn_id": "surface_turn_1",
        "terminal_status": "completed",
    }


@pytest.mark.asyncio
async def test_redacted_public_followup_context_does_not_override_grading_authority() -> None:
    public_context = {
        "question_id": "q_1",
        "question": "屋面防水卷材施工前，基层应满足哪项要求？",
        "question_type": "choice",
        "options": {"A": "含水率适宜且表面平整", "B": "可带明水直接铺贴"},
        "correct_answer": "",
        "explanation": "",
        "user_answer": "A",
    }
    stored_context = {
        **public_context,
        "correct_answer": "A",
        "explanation": "基层应平整、干净、含水率符合要求。",
        "user_answer": "",
    }

    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="我选 A",
        explicit_context=public_context,
        explicit_action={"intent": "answer_questions", "answers": [{"index": 1, "user_answer": "A"}]},
        candidate_contexts=[stored_context],
    )

    assert resolved_context is not None
    assert resolved_context["correct_answer"] == "A"
    assert resolved_context["explanation"] == "基层应平整、干净、含水率符合要求。"
    assert resolved_context["user_answer"] == "A"
    assert resolved_action is not None


@pytest.mark.asyncio
async def test_redacted_batch_followup_context_uses_hidden_grading_key_authority() -> None:
    public_context = {
        "question_id": "question_set",
        "question": "三道建筑实务选择题",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题",
                "question_type": "single_choice",
                "user_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "第2题",
                "question_type": "single_choice",
                "user_answer": "B",
            },
            {
                "question_id": "q_3",
                "question": "第3题",
                "question_type": "single_choice",
                "user_answer": "B",
            },
        ],
    }
    stored_context = {
        "question_id": "question_set",
        "question": "三道建筑实务选择题",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "第1题",
                "question_type": "single_choice",
                "grading_key": {"correct_answer": "A"},
                "explanation": "第1题解析",
            },
            {
                "question_id": "q_2",
                "question": "第2题",
                "question_type": "single_choice",
                "grading_key": {"correct_answer": "C"},
                "explanation": "第2题解析",
            },
            {
                "question_id": "q_3",
                "question": "第3题",
                "question_type": "single_choice",
                "grading_key": {"correct_answer": "B"},
                "explanation": "第3题解析",
            },
        ],
    }

    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="第1题：A；第2题：B；第3题：B",
        explicit_context=public_context,
        explicit_action=None,
        candidate_contexts=[stored_context],
    )

    assert resolved_context is not None
    resolved_items = {item["question_id"]: item for item in resolved_context["items"]}
    assert resolved_items["q_1"]["grading_key"]["correct_answer"] == "A"
    assert resolved_items["q_2"]["grading_key"]["correct_answer"] == "C"
    assert resolved_items["q_3"]["grading_key"]["correct_answer"] == "B"
    assert resolved_action is not None
    assert resolved_action["intent"] == "answer_questions"
    assert resolved_action["answers"] == [
        {"index": 1, "question_id": "q_1", "user_answer": "A"},
        {"index": 2, "question_id": "q_2", "user_answer": "B"},
        {"index": 3, "question_id": "q_3", "user_answer": "B"},
    ]


@pytest.mark.asyncio
async def test_ambiguous_multi_question_single_letter_is_not_promoted_to_answer_action() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="我选B",
        explicit_context={
            "question_id": "question_set",
            "question": "两道建筑实务选择题",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "第1题",
                    "question_type": "single_choice",
                    "options": {"A": "A1", "B": "B1"},
                    "correct_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "第2题",
                    "question_type": "single_choice",
                    "options": {"A": "A2", "B": "B2"},
                    "correct_answer": "B",
                },
            ],
        },
        explicit_action=None,
        candidate_contexts=[],
    )

    assert resolved_context is not None
    assert resolved_action is None


@pytest.mark.asyncio
async def test_full_new_mcq_does_not_regrade_stale_active_question() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message=(
            "换题：历史建筑的建筑高度应按室外设计地坪至建构筑物什么计算？"
            "A.檐口顶点 B.屋脊 C.墙顶点 D.最高点，我选C，直接批改"
        ),
        explicit_context=None,
        explicit_action=None,
        candidate_contexts=[
            {
                "question_id": "historical:roof_slope",
                "question": "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。",
                "question_type": "single_choice",
                "options": {"A": "5%", "B": "1%", "C": "2%", "D": "3%"},
                "correct_answer": "A",
                "user_answer": "A",
                "is_correct": True,
            }
        ],
    )

    assert resolved_context is None
    assert resolved_action is None


@pytest.mark.asyncio
async def test_full_new_mcq_does_not_regrade_stale_explicit_question() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message=(
            "换题：历史建筑的建筑高度应按室外设计地坪至建构筑物什么计算？"
            "A.檐口顶点 B.屋脊 C.墙顶点 D.最高点，我选C，直接批改"
        ),
        explicit_context={
            "question_id": "historical:roof_slope",
            "question": "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。",
            "question_type": "single_choice",
            "options": {"A": "5%", "B": "1%", "C": "2%", "D": "3%"},
            "correct_answer": "A",
            "user_answer": "A",
            "is_correct": True,
        },
        explicit_action=None,
        candidate_contexts=[],
    )

    assert resolved_context is None
    assert resolved_action is None


@pytest.mark.asyncio
async def test_full_new_mcq_with_same_option_values_does_not_keep_stale_explicit_question() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message=(
            "安全生产法属于（ ）。A.法律 B.行政法规 C.部门规章 D.地方性法规，"
            "我选A，直接批改"
        ),
        explicit_context={
            "question_id": "old_regulation_level",
            "question": "建设工程安全生产管理条例属于（ ）。",
            "question_type": "single_choice",
            "options": {
                "A": "法律",
                "B": "行政法规",
                "C": "部门规章",
                "D": "地方性法规",
            },
            "correct_answer": "B",
        },
        explicit_action=None,
        candidate_contexts=[],
    )

    assert resolved_context is None
    assert resolved_action is None


@pytest.mark.asyncio
async def test_full_same_mcq_keeps_explicit_question_context() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message=(
            "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。"
            "A.5% B.1% C.2% D.3%，我选A，直接批改"
        ),
        explicit_context={
            "question_id": "historical:roof_slope",
            "question": "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。",
            "question_type": "single_choice",
            "options": {"A": "5%", "B": "1%", "C": "2%", "D": "3%"},
            "correct_answer": "A",
        },
        explicit_action=None,
        candidate_contexts=[],
    )

    assert resolved_context is not None
    assert resolved_context["question_id"] == "historical:roof_slope"
    assert resolved_action is not None
    assert resolved_action["intent"] == "answer_questions"
    assert resolved_action["answers"][0]["answer"] == "A"


@pytest.mark.asyncio
async def test_full_same_mcq_keeps_candidate_question_context_without_explicit_context() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message=(
            "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。"
            "A.5% B.1% C.2% D.3%，我选A，直接批改"
        ),
        explicit_context=None,
        explicit_action=None,
        candidate_contexts=[
            {
                "question_id": "historical:roof_slope",
                "question": "某工程屋面做法为压型金属板，当设计无要求时，屋面坡度最小值是（ ）。",
                "question_type": "single_choice",
                "options": {"A": "5%", "B": "1%", "C": "2%", "D": "3%"},
                "correct_answer": "A",
            }
        ],
    )

    assert resolved_context is not None
    assert resolved_context["question_id"] == "historical:roof_slope"
    assert resolved_action is not None
    assert resolved_action["intent"] == "answer_questions"
    assert resolved_action["answers"][0]["answer"] == "A"


@pytest.mark.asyncio
async def test_explicit_question_value_challenge_routes_to_followup() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="那1.0m行不行？一句话",
        explicit_context={
            "question_id": "historical:diaphragm_wall",
            "question": "关于地下连续墙施工要求，正确的有（ ）。",
            "question_type": "multiple_choice",
            "options": {
                "A": "地下连续墙单元槽段长度宜为8～10m",
                "B": "导墙高度不应小于1.0m",
                "C": "应设置现浇钢筋混凝土导墙",
                "D": "水下混凝土应采用导管法连续浇筑",
                "E": "混凝土达到设计强度后方可进行墙底注浆",
            },
            "correct_answer": "CDE",
            "user_answer": "ACDE",
            "is_correct": False,
        },
        explicit_action=None,
        candidate_contexts=[],
    )

    assert resolved_context is not None
    assert resolved_context["question_id"] == "historical:diaphragm_wall"
    assert resolved_action is not None
    assert resolved_action["intent"] == "ask_followup"


@pytest.mark.asyncio
async def test_explicit_question_option_explainer_is_not_treated_as_answer_submission() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="这个题的B为什么对？",
        explicit_context={
            "question_id": "historical:design_stage",
            "question": "工程概算书属于（　　）文件内容。",
            "question_type": "single_choice",
            "options": {"A": "方案设计", "B": "初步设计", "C": "施工图设计", "D": "专项设计"},
            "correct_answer": "B",
            "user_answer": "A",
            "is_correct": False,
        },
        explicit_action=None,
        candidate_contexts=[],
    )

    assert resolved_context is not None
    assert resolved_context["question_id"] == "historical:design_stage"
    assert resolved_action is not None
    assert resolved_action["intent"] == "ask_followup"


@pytest.mark.asyncio
@pytest.mark.parametrize("user_message", ["我选B。", "答案是B。", "B，批改一下。"])
async def test_explicit_question_option_submission_still_routes_to_grading(
    user_message: str,
) -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message=user_message,
        explicit_context={
            "question_id": "historical:design_stage",
            "question": "工程概算书属于（　　）文件内容。",
            "question_type": "single_choice",
            "options": {"A": "方案设计", "B": "初步设计", "C": "施工图设计", "D": "专项设计"},
            "correct_answer": "B",
        },
        explicit_action=None,
        candidate_contexts=[],
    )

    assert resolved_context is not None
    assert resolved_context["question_id"] == "historical:design_stage"
    assert resolved_action is not None
    assert resolved_action["intent"] == "answer_questions"
    assert resolved_action["answers"][0]["answer"] == "B"


@pytest.mark.asyncio
async def test_answered_active_question_can_generate_related_questions_without_regrading() -> None:
    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="再给我相关的五道题，不要给答案，等我作答后再批改",
        explicit_context=None,
        explicit_action=None,
        candidate_contexts=[
            {
                "question_id": "q_2",
                "question": "《建设工程安全生产管理条例》属于（ ）。",
                "question_type": "choice",
                "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
                "correct_answer": "B",
                "explanation": "条例由国务院制定，属于行政法规。",
                "user_answer": "B",
                "is_correct": True,
                "construction_grading_result": {
                    "authority": "construction_grading",
                    "score_awarded": 1.0,
                    "max_score": 1.0,
                },
            }
        ],
    )

    assert resolved_context is not None
    assert resolved_context["user_answer"] == ""
    assert resolved_context["is_correct"] is None
    assert resolved_action is not None
    assert resolved_action["intent"] == "generate_more_questions"
    assert resolved_action["answers"] == []


@pytest.mark.asyncio
async def test_submission_with_next_training_request_routes_to_grading() -> None:
    active_question = {
        "question_id": "q_regulation_level",
        "question": "《建设工程安全生产管理条例》属于（ ）。",
        "question_type": "choice",
        "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
        "correct_answer": "B",
        "explanation": "条例由国务院制定，属于行政法规。",
        "concentration": "法规层级",
    }

    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="我选A，请按建筑实务选择题帮我批改，并告诉我下一题该练什么",
        explicit_context=active_question,
        explicit_action={"intent": "generate_more_questions", "answers": []},
        candidate_contexts=[],
    )

    assert resolved_context is not None
    assert resolved_context["question_id"] == "q_regulation_level"
    assert resolved_action is not None
    assert resolved_action["intent"] == "answer_questions"
    assert resolved_action["answers"] == [
        {"question_id": "q_regulation_level", "answer": "A"}
    ]


@pytest.mark.asyncio
async def test_resolve_question_followup_explicit_context_keeps_option_challenge_from_llm_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _misleading_interpret(_message, _question_context, **_kwargs):
        return {
            "intent": "generate_more_questions",
            "confidence": 0.88,
            "answers": [],
            "reason": "模拟 LLM 把选项追问误判成继续出题。",
        }

    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.interpret_question_followup_action",
        _misleading_interpret,
    )

    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="那C呢？",
        explicit_context={
            "question_id": "historical:roof_slope",
            "question": "压型金属板屋面最低坡度是多少？",
            "question_type": "choice",
            "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
            "correct_answer": "D",
            "user_answer": "B",
            "is_correct": False,
        },
        explicit_action=None,
        candidate_contexts=[],
    )

    assert resolved_context is not None
    assert resolved_context["question_id"] == "historical:roof_slope"
    assert resolved_context["user_answer"] == "B"
    assert resolved_action is not None
    assert resolved_action["intent"] == "ask_followup"


@pytest.mark.asyncio
async def test_resolve_question_followup_explicit_context_ignores_generation_hint_for_option_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _followup_interpret(_message, _question_context, **_kwargs):
        return {
            "intent": "ask_followup",
            "confidence": 0.91,
            "answers": [],
            "reason": "用户是在追问当前题的 C 选项。",
        }

    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.interpret_question_followup_action",
        _followup_interpret,
    )

    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="那C呢？",
        explicit_context={
            "question_id": "historical:roof_slope",
            "question": "压型金属板屋面最低坡度是多少？",
            "question_type": "choice",
            "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
            "correct_answer": "D",
            "user_answer": "B",
            "is_correct": False,
        },
        explicit_action={
            "intent": "generate_more_questions",
            "confidence": 0.9,
            "answers": [],
            "reason": "前端或上游 hint 误把选项追问当成继续出题。",
        },
        candidate_contexts=[],
    )

    assert resolved_context is not None
    assert resolved_context["question_id"] == "historical:roof_slope"
    assert resolved_context["user_answer"] == "B"
    assert resolved_action is not None
    assert resolved_action["intent"] == "ask_followup"


@pytest.mark.asyncio
async def test_resolve_question_followup_does_not_treat_next_question_explainer_as_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_interpret(_message, _question_context, **_kwargs):
        return {
            "intent": "ask_followup",
            "confidence": 0.9,
            "answers": [],
            "reason": "用户是在追问下一题为什么错。",
        }

    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.interpret_question_followup_action",
        _fake_interpret,
    )

    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="下一题为什么错",
        explicit_context=None,
        explicit_action=None,
        candidate_contexts=[
            {
                "question_id": "q_1",
                "question": "第1题：楼梯平台净高最低多少？",
                "question_type": "choice",
                "options": {"A": "2.0m", "B": "2.2m"},
                "correct_answer": "B",
            }
        ],
    )

    assert resolved_context is not None
    assert resolved_action is not None
    assert resolved_action["intent"] == "ask_followup"


@pytest.mark.asyncio
async def test_resolve_question_followup_does_not_treat_question_type_explainer_as_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_interpret(_message, _question_context, **_kwargs):
        return {
            "intent": "ask_followup",
            "confidence": 0.9,
            "answers": [],
            "reason": "用户是在追问下一道选择题为什么错。",
        }

    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.interpret_question_followup_action",
        _fake_interpret,
    )

    resolved_context, resolved_action = await _resolve_question_followup_context_and_action(
        user_message="下一道选择题为什么错",
        explicit_context=None,
        explicit_action=None,
        candidate_contexts=[
            {
                "question_id": "q_1",
                "question": "第1题：楼梯平台净高最低多少？",
                "question_type": "choice",
                "options": {"A": "2.0m", "B": "2.2m"},
                "correct_answer": "B",
            }
        ],
    )

    assert resolved_context is not None
    assert resolved_action is not None
    assert resolved_action["intent"] == "ask_followup"


@pytest.mark.asyncio
async def test_start_turn_merges_redacted_public_submission_with_stored_active_question(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, context):
            captured["selector_active_capability"] = context.active_capability
            return "deep_question"

        async def handle(self, context):
            captured["capability"] = context.active_capability
            captured["config_overrides"] = dict(context.config_overrides)
            captured["question_followup_context"] = dict(
                context.metadata.get("question_followup_context", {}) or {}
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="deep_question",
                metadata={"response": "第2题正确。", "mode": "grading"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="session_redacted_mcq", title="题组")
    authoritative_context = {
        "question_id": "question_set",
        "question": "相关五道题",
        "question_type": "choice",
        "items": [
            {
                "question_id": "q_1",
                "question": "《建筑法》属于（ ）。",
                "question_type": "choice",
                "options": {"A": "法律", "B": "行政法规"},
                "correct_answer": "A",
            },
            {
                "question_id": "q_2",
                "question": "《建设工程安全生产管理条例》属于（ ）。",
                "question_type": "choice",
                "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
                "correct_answer": "B",
                "explanation": "条例由国务院制定，属于行政法规。",
            },
        ],
    }
    active_object = build_active_object_from_question_context(authoritative_context)
    assert active_object is not None
    await store.set_active_object(session["id"], active_object)

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选B",
            "session_id": session["id"],
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "followup_question_context": {
                    "question_id": "q_2",
                    "question": "《建设工程安全生产管理条例》属于（ ）。",
                    "question_type": "choice",
                    "options": {
                        "A": "法律",
                        "B": "行政法规",
                        "C": "部门规章",
                        "D": "地方性法规",
                    },
                    "correct_answer": "",
                    "explanation": "",
                    "user_answer": "B",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    resolved = captured["question_followup_context"]
    assert captured["selector_active_capability"] is None
    assert captured["capability"] == "deep_question"
    assert resolved["question_id"] == "q_2"
    assert resolved["correct_answer"] == "B"
    assert resolved["user_answer"] == "B"
    assert "行政法规" in resolved["explanation"]


@pytest.mark.asyncio
async def test_start_turn_projects_general_knowledge_shadow_flag_to_tutorbot_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, context):
            return "tutorbot"

        async def handle(self, context):
            captured["config_overrides"] = dict(context.config_overrides)
            captured["metadata"] = dict(context.metadata)
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={"response": "TutorBot reply"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "高层住宅的建筑高度是怎么界定的？",
            "session_id": "session_general_knowledge_shadow",
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_profile": "tutorbot",
                "general_knowledge_context": True,
                "billing_context": {
                    "source": "online_shadow",
                    "user_id": "qa_compiled_shadow",
                    "wallet_user_id": "qa_compiled_shadow",
                    "learning_user_id": "qa_compiled_shadow",
                },
            },
        }
    )

    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        if event["type"] == "done":
            break

    assert session["id"] == "session_general_knowledge_shadow"
    assert captured["config_overrides"]["general_knowledge_context"] is True
    assert captured["metadata"]["general_knowledge_context"] is True
    assert captured["metadata"]["source"] == "online_shadow"


@pytest.mark.asyncio
async def test_start_turn_does_not_coerce_string_general_knowledge_flag_to_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, context):
            return "tutorbot"

        async def handle(self, context):
            captured["metadata"] = dict(context.metadata)
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={"response": "TutorBot reply"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "高层住宅的建筑高度是怎么界定的？",
            "session_id": "session_general_knowledge_string_flag",
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_profile": "tutorbot",
                "general_knowledge_context": "false",
            },
        }
    )

    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        if event["type"] == "done":
            break

    assert "general_knowledge_context" not in captured["metadata"]


@pytest.mark.asyncio
async def test_start_turn_recovers_stored_active_question_for_plain_text_option_followup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    async def fake_interpret(_message, _question_context, **_kwargs):
        return {
            "intent": "ask_followup",
            "confidence": 0.9,
            "answers": [],
            "reason": "用户追问当前题的选项。",
        }

    class FakeOrchestrator:
        async def _select_capability(self, context):
            captured["selector_question_followup_context"] = dict(
                context.metadata.get("question_followup_context", {}) or {}
            )
            captured["selector_question_followup_action"] = dict(
                context.metadata.get("question_followup_action", {}) or {}
            )
            captured["selector_active_object"] = dict(context.metadata.get("active_object", {}) or {})
            return "deep_question"

        async def handle(self, context):
            captured["capability"] = context.active_capability
            captured["question_followup_context"] = dict(
                context.metadata.get("question_followup_context", {}) or {}
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="deep_question",
                metadata={
                    "response": "C 也不对；本题标准答案是 D。",
                    "mode": "followup",
                    "question_followup_context": context.metadata.get(
                        "question_followup_context", {}
                    ),
                    "turn_semantic_decision": {
                        "next_action": "route_to_followup_explainer",
                    },
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.services.session.turn_runtime.interpret_question_followup_action", fake_interpret)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="session_plain_option_followup", title="真题")
    active_context = {
        "question_id": "historical:roof_slope",
        "question": "压型金属板屋面最低坡度是多少？",
        "question_type": "choice",
        "options": {"A": "1%", "B": "2%", "C": "3%", "D": "5%"},
        "correct_answer": "D",
        "explanation": "压型金属板屋面最小坡度为 5%。",
        "user_answer": "B",
        "is_correct": False,
    }
    active_object = build_active_object_from_question_context(active_context)
    assert active_object is not None
    await store.set_active_object(session["id"], active_object)

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "那C呢？",
            "session_id": session["id"],
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {"bot_id": "construction-exam-coach"},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    selector_context = captured["selector_question_followup_context"]
    selector_action = captured["selector_question_followup_action"]
    resolved_context = captured["question_followup_context"]
    assert captured["capability"] == "deep_question"
    assert selector_context["question_id"] == "historical:roof_slope"
    assert selector_context["user_answer"] == "B"
    assert selector_context["is_correct"] is False
    assert selector_action["intent"] == "ask_followup"
    assert resolved_context["question_id"] == "historical:roof_slope"
    assert resolved_context["user_answer"] == "B"


@pytest.mark.asyncio
async def test_turn_runtime_replays_events_and_materializes_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **kwargs):
            on_event = kwargs.get("on_event")
            if on_event is not None:
                await on_event(
                    StreamEvent(
                        type=StreamEventType.PROGRESS,
                        source="context",
                        stage="summarizing",
                        content="summarize context",
                    )
                )
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="Hello Frank",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    async def _fake_put(**kwargs):
        return f"store://{kwargs['session_id']}/{kwargs['attachment_id']}"

    monkeypatch.setattr(
        "deeptutor.services.storage.get_attachment_store",
        lambda: SimpleNamespace(put=_fake_put),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello, i'm frank",
            "session_id": None,
            "capability": None,
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "attachments": [
                {
                    "type": "file",
                    "filename": "photo.png",
                    "mime_type": "image/png",
                    "base64": "aGVsbG8=",
                }
            ],
            "language": "zh",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    assert any(event["type"] == "progress" for event in events)
    assert events[-1]["metadata"]["status"] == "completed"

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    snapshot = detail["messages"][0]["metadata"]["request_snapshot"]
    assert snapshot["content"] == "hello, i'm frank"
    assert snapshot["capability"] == "chat"
    assert snapshot["enabledTools"] == ["rag"]
    assert snapshot["knowledgeBases"] == ["construction-exam"]
    assert snapshot["language"] == "zh"
    assert snapshot["attachments"] == [
        {
            "type": "file",
            "url": f"store://{session['id']}/att-1",
            "filename": "photo.png",
            "mime_type": "image/png",
        }
    ]
    assert detail["messages"][1]["content"] == "Hello Frank"
    assert detail["preferences"]["archived"] is False
    assert detail["preferences"]["capability"] == "chat"
    assert detail["preferences"]["chat_mode"] == get_default_chat_mode()
    assert detail["preferences"]["tools"] == ["rag"]
    assert detail["preferences"]["knowledge_bases"] == ["construction-exam"]
    assert detail["preferences"]["language"] == "zh"

    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["status"] == "completed"


@pytest.mark.asyncio
async def test_turn_runtime_extracts_document_attachments_into_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_contexts = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured_contexts.append(context)
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="read the file",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    from deeptutor.services.storage import LocalDiskAttachmentStore

    attachment_store = LocalDiskAttachmentStore(root=tmp_path / "attachments")
    monkeypatch.setattr("deeptutor.services.storage.get_attachment_store", lambda: attachment_store)
    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    encoded = base64.b64encode("attachment lesson text".encode("utf-8")).decode("ascii")
    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "summarize this",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [
                {
                    "type": "file",
                    "filename": "lesson.txt",
                    "mime_type": "text/plain",
                    "base64": encoded,
                }
            ],
            "language": "en",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_contexts
    assert "[Attached Documents]" in captured_contexts[0].user_message
    assert "attachment lesson text" in captured_contexts[0].user_message
    assert captured_contexts[0].attachments[0].base64 == ""
    assert captured_contexts[0].attachments[0].url.startswith("/api/attachments/")

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    user_attachments = detail["messages"][0]["attachments"]
    assert user_attachments[0]["base64"] == ""
    assert user_attachments[0]["extracted_text"] == "attachment lesson text"
    assert user_attachments[0]["url"].startswith("/api/attachments/")
    snapshot = detail["messages"][0]["metadata"]["request_snapshot"]
    assert snapshot["content"] == "summarize this"
    assert snapshot["enabledTools"] == []
    assert snapshot["knowledgeBases"] == []
    assert snapshot["attachments"][0]["extracted_text"] == "attachment lesson text"
    assert "learner_state" not in snapshot
    assert "memory_context" not in snapshot


def test_unified_turn_start_accepts_llm_selection_ids_only() -> None:
    message = UnifiedTurnStartMessage(
        type="start_turn",
        content="hello",
        llm_selection={"profile_id": "p1", "model_id": "m1"},
    )

    assert message.llm_selection == {"profile_id": "p1", "model_id": "m1"}


@pytest.mark.asyncio
async def test_turn_runtime_applies_request_scoped_llm_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    selection = {"profile_id": "llm-p2", "model_id": "llm-m2"}
    captured: dict[str, object] = {}

    class FakeCatalogService:
        def load(self):
            return {
                "version": 1,
                "services": {
                    "llm": {
                        "active_profile_id": "llm-p1",
                        "active_model_id": "llm-m1",
                        "profiles": [
                            {
                                "id": "llm-p1",
                                "name": "Default",
                                "binding": "openai",
                                "base_url": "https://default.example/v1",
                                "api_key": "default-key",
                                "api_version": "",
                                "extra_headers": {},
                                "models": [{"id": "llm-m1", "name": "Default", "model": "gpt-default"}],
                            },
                            {
                                "id": "llm-p2",
                                "name": "Selected",
                                "binding": "dashscope",
                                "base_url": "",
                                "api_key": "selected-key",
                                "api_version": "",
                                "extra_headers": {},
                                "models": [{"id": "llm-m2", "name": "Selected", "model": "qwen-selected"}],
                            },
                        ],
                    },
                    "embedding": {"active_profile_id": None, "active_model_id": None, "profiles": []},
                    "search": {"active_profile_id": None, "profiles": []},
                },
            }

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            from deeptutor.services.llm.config import get_llm_config

            captured["scoped_model"] = get_llm_config().model
            captured["context_metadata"] = dict(context.metadata)
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="selected model response",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    def _resolve_llm_runtime_config(*_args, **kwargs):
        assert kwargs["llm_selection"] == selection
        return ResolvedLLMConfig(
            model="qwen-selected",
            provider_name="dashscope",
            provider_mode="standard",
            binding_hint="dashscope",
            binding="dashscope",
            api_key="selected-key",
            base_url="https://dashscope.example/v1",
            effective_url="https://dashscope.example/v1",
            api_version=None,
            extra_headers={},
            reasoning_effort=None,
        )

    monkeypatch.setattr("deeptutor.services.config.get_model_catalog_service", lambda: FakeCatalogService())
    monkeypatch.setattr(
        "deeptutor.services.model_selection.runtime.resolve_llm_runtime_config",
        _resolve_llm_runtime_config,
    )
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello with selected model",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "llm_selection": selection,
            "language": "en",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert captured["scoped_model"] == "qwen-selected"
    assert captured["context_metadata"]["llm_selection"] == selection
    assert detail["preferences"]["llm_selection"] == selection
    assert detail["messages"][0]["metadata"]["request_snapshot"]["llm_selection"] == selection


@pytest.mark.asyncio
async def test_turn_runtime_captures_exact_authority_response_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="1. 标准答案\n\n2. 标准答案",
                metadata={"call_kind": "exact_authority_response", "call_id": "exact-1"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "案例题",
            "session_id": None,
            "capability": None,
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert events[-1]["type"] == "done"
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["messages"][-1]["role"] == "assistant"
    assert detail["messages"][-1]["content"] == "1. 标准答案\n\n2. 标准答案"


@pytest.mark.asyncio
async def test_turn_runtime_bootstraps_open_chat_active_object_when_no_stronger_object(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_object"] = context.metadata.get("active_object")
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "继续聊这个话题。", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        lambda _observation, **kwargs: captured_updates.append(kwargs),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我们继续聊施工组织总设计",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    active_object = captured["active_object"]
    assert active_object["object_type"] == "open_chat_topic"
    assert active_object["object_id"] == session["id"]
    assert active_object["state_snapshot"]["session_id"] == session["id"]


@pytest.mark.asyncio
async def test_turn_runtime_prefers_result_response_as_assistant_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="## 结论\n",
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="建筑构造是研究建筑物组成与连接方式的技术。",
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "建筑构造是研究建筑物组成与连接方式的技术。"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "建筑构造是什么？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["messages"][-1]["content"] == "建筑构造是研究建筑物组成与连接方式的技术。"


@pytest.mark.asyncio
async def test_turn_runtime_persists_message_turn_identity_for_resume_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "后台恢复可读取这条回答。"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "后台回来后继续同步本轮回答",
            "session_id": "session_resume_identity",
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"client_turn_id": "surface_turn_resume_1"},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    messages = detail["messages"]
    user_message = next(message for message in messages if message["role"] == "user")
    assistant_message = next(message for message in messages if message["role"] == "assistant")

    assert user_message["metadata"]["turn_id"] == turn["id"]
    assert user_message["metadata"]["client_turn_id"] == "surface_turn_resume_1"
    assert assistant_message["metadata"]["turn_id"] == turn["id"]
    assert assistant_message["metadata"]["engine_turn_id"] == turn["id"]
    assert assistant_message["metadata"]["client_turn_id"] == "surface_turn_resume_1"
    assert assistant_message["metadata"]["terminal_status"] == "completed"


@pytest.mark.asyncio
async def test_turn_runtime_excludes_internal_content_from_assistant_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="tutorbot",
                stage="responding",
                content="我来读取相关技能文件。",
                visibility="internal",
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={"response": "建筑构造是研究建筑物组成方式和连接关系的学科。"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "建筑构造是什么？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["messages"][-1]["content"] == "建筑构造是研究建筑物组成方式和连接关系的学科。"
    assert any(event["visibility"] == "internal" for event in events if event["type"] == "content")
    assistant_history_events = [
        item
        for item in detail["messages"][-1]["events"]
        if item.get("type") not in {"done", "session"}
    ]
    assert all(
        item.get("visibility") == "public"
        or (
            item.get("type") == "trace_link"
            and item.get("visibility") == "internal"
            and not str(item.get("content") or "").strip()
        )
        for item in assistant_history_events
    )
    assert all(
        item.get("type") != "content" or item.get("content") != "我来读取相关技能文件。"
        for item in assistant_history_events
    )


@pytest.mark.asyncio
async def test_turn_runtime_routes_construction_exam_bot_to_tutorbot_capability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, context):
            assert context.active_capability is None
            return "tutorbot"

        async def handle(self, context):
            assert context.active_capability == "tutorbot"
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="tutorbot",
                stage="responding",
                content="TutorBot reply",
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你好",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"bot_id": "construction-exam-coach"},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert turn["capability"] == "tutorbot"
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "tutorbot"
    assert detail["preferences"]["tools"] == ["rag"]
    assert detail["preferences"]["knowledge_bases"] == ["construction-exam"]
    assert detail["messages"][-1]["content"] == "TutorBot reply"


@pytest.mark.asyncio
async def test_start_turn_waits_for_first_subscriber_before_running(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TURN_RUNTIME_FIRST_SUBSCRIBER_GRACE_SECONDS", "0.3")
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    started = asyncio.Event()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            started.set()
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="streamed reply",
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你好",
            "session_id": None,
            "capability": "chat",
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    await asyncio.sleep(0.05)
    assert not started.is_set()

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)
        if event["type"] == "done":
            break

    assert started.is_set()
    assert [event["type"] for event in events if event["type"] in {"content", "done"}] == [
        "content",
        "done",
    ]


@pytest.mark.asyncio
async def test_start_turn_emits_public_status_before_capability_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="streamed reply",
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你好",
            "session_id": None,
            "capability": "chat",
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)
        if event["type"] == "done":
            break

    public_status_index = next(
        index
        for index, event in enumerate(events)
        if event["type"] == "progress"
        and event.get("visibility") == "public"
        and event.get("metadata", {}).get("status_kind") == "turn_status"
        and event.get("metadata", {}).get("phase") == "understanding"
    )
    public_writing_status_index = next(
        index
        for index, event in enumerate(events)
        if event["type"] == "progress"
        and event.get("visibility") == "public"
        and event.get("metadata", {}).get("status_kind") == "turn_status"
        and event.get("metadata", {}).get("phase") == "writing"
    )
    first_capability_content_index = next(
        index
        for index, event in enumerate(events)
        if event["type"] == "content" and event.get("source") == "chat"
    )

    assert public_status_index < first_capability_content_index
    assert public_status_index < public_writing_status_index < first_capability_content_index
    assert events[public_status_index]["content"]
    assert events[public_writing_status_index]["content"]


@pytest.mark.asyncio
async def test_turn_runtime_routes_tutorbot_practice_generation_to_deep_question_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, context):
            captured["selector_active_capability"] = context.active_capability
            context.config_overrides["force_generate_questions"] = True
            context.config_overrides["question_type"] = "choice"
            context.config_overrides["reveal_answers"] = False
            context.config_overrides["reveal_explanations"] = False
            return "deep_question"

        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["user_message"] = context.user_message
            captured["config_overrides"] = dict(context.config_overrides)
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="第1题",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="deep_question",
                metadata={
                    "response": "第1题",
                    "mode": "custom",
                    "question_followup_context": {
                        "question_id": "q_1",
                        "question": "施工管理选择题",
                        "question_type": "choice",
                        "correct_answer": "B",
                    },
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        lambda _observation, **kwargs: captured_updates.append(kwargs),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我想练习施工管理，请给我来5道选择题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["selector_active_capability"] is None
    assert captured["active_capability"] == "deep_question"
    assert captured["user_message"] == "我想练习施工管理，请给我来5道选择题"
    assert captured["config_overrides"]["bot_id"] == "construction-exam-coach"
    assert captured["config_overrides"]["force_generate_questions"] is True
    assert captured["config_overrides"]["question_type"] == "choice"
    assert captured["config_overrides"]["reveal_answers"] is False

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "deep_question"
    assert detail["messages"][-1]["content"] == "第1题"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_routes_recent_practice_offer_acceptance_to_deep_question_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    captured_capabilities: list[str] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text=(
                    "Assistant: 记忆口诀强化\n"
                    "主体结构七大类：砼砌钢，钢管型钢铝木全。\n"
                    "需要我出同考点题目帮你巩固一下吗？"
                ),
                token_count=0,
                budget=0,
            )

    class FakeCapability:
        async def run(self, context, bus) -> None:
            captured["active_capability"] = context.active_capability
            captured["config_overrides"] = dict(context.config_overrides)
            captured["metadata"] = dict(context.metadata)
            await bus.content(
                "第1题",
                source="deep_question",
                stage="generation",
                metadata={"call_kind": "llm_final_response"},
            )
            await bus.result(
                {
                    "response": "第1题",
                    "mode": "custom",
                    "question_followup_context": {
                        "question_id": "q_recent_offer",
                        "question": "主体结构练习题",
                        "question_type": "choice",
                        "correct_answer": "A",
                    },
                },
                source="deep_question",
            )

    class FakeRegistry:
        def get(self, name: str):
            captured_capabilities.append(name)
            return FakeCapability()

        def list_capabilities(self) -> list[str]:
            return ["chat", "deep_question", "tutorbot"]

        def get_manifests(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.get_capability_registry",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.get_tool_registry",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="session_recent_offer_acceptance", title="主体结构")
    active_object = build_active_object_from_session(session)
    assert active_object is not None
    await store.set_active_object(session["id"], active_object)

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "要",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] == "deep_question"
    assert captured_capabilities[0] == "deep_question"
    assert captured["config_overrides"]["topic"] == "继续出同考点题目帮我巩固一下"
    assert captured["config_overrides"]["force_generate_questions"] is True
    assert captured["metadata"]["question_followup_action"]["intent"] == "generate_more_questions"
    assert captured["metadata"]["turn_semantic_decision"]["next_action"] == "route_to_generation"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_open_chat_tutorbot_followup_on_tutorbot_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    captured_capabilities: list[str] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="Assistant: 主体结构七大类：砼砌钢，钢管型钢铝木全。",
                token_count=0,
                budget=0,
            )

    class FakeCapability:
        async def run(self, context, bus) -> None:
            captured["active_capability"] = context.active_capability
            captured["metadata"] = dict(context.metadata)
            await bus.content(
                "这是在解释主体结构口诀。",
                source="tutorbot",
                stage="responding",
            )

    class FakeRegistry:
        def get(self, name: str):
            captured_capabilities.append(name)
            return FakeCapability()

        def list_capabilities(self) -> list[str]:
            return ["chat", "deep_question", "tutorbot"]

        def get_manifests(self) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.get_capability_registry",
        lambda: FakeRegistry(),
    )
    monkeypatch.setattr(
        "deeptutor.runtime.orchestrator.get_tool_registry",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="session_tutorbot_open_chat_followup", title="主体结构")
    active_object = build_active_object_from_session(session)
    assert active_object is not None
    await store.set_active_object(session["id"], active_object)

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "这个口诀是什么意思？",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "tutorbot"
    assert captured["active_capability"] == "tutorbot"
    assert captured_capabilities[0] == "tutorbot"
    assert captured["metadata"]["active_object"]["object_type"] == "open_chat_topic"
    assert captured["metadata"]["semantic_router_selected_capability"] == "tutorbot"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "tutorbot"


@pytest.mark.asyncio
async def test_turn_runtime_leaves_tutorbot_question_followup_for_orchestrator_autoroute(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["followup_question_context"] = dict(
                context.metadata.get("question_followup_context", {}) or {}
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="第1题：判断正确",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选B",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "subject_domain": "construction_exam",
                },
                "followup_question_context": {
                    "question_id": "q_1",
                    "question": "关于施工组织设计，下列说法正确的是：",
                    "question_type": "choice",
                    "options": {
                        "A": "说法A",
                        "B": "说法B",
                        "C": "说法C",
                        "D": "说法D",
                    },
                    "correct_answer": "B",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    assert captured["followup_question_context"]["question_id"] == "q_1"
    assert captured["followup_question_context"]["correct_answer"] == "B"
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "deep_question"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_injects_usage_summary_into_result_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                content=(
                    "Error: {'message': 'Authentication Fails, Your api key: ****486e is invalid', "
                    "'type': 'authentication_error', 'param': None, 'code': 'invalid_request_error'}"
                ),
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={
                    "response": "answer",
                    "metadata": {"cost_summary": {"total_tokens": 11, "total_calls": 1}},
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {
            "scope_id": "turn_scope",
            "session_id": "session_scope",
            "turn_id": "turn_scope",
            "capability": "chat",
            "total_input_tokens": 120,
            "total_output_tokens": 45,
            "total_tokens": 165,
            "total_calls": 3,
            "measured_calls": 1,
            "estimated_calls": 2,
            "usage_accuracy": "mixed",
            "usage_sources": {"provider": 1, "tiktoken": 2},
            "models": {"gpt-4o": 3},
            "total_cost_usd": 0.00123,
        },
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    result_event = next(event for event in events if event["type"] == "result")
    cost_summary = result_event["metadata"]["metadata"]["cost_summary"]
    assert cost_summary["total_tokens"] == 165
    assert cost_summary["total_calls"] == 3
    assert cost_summary["usage_accuracy"] == "mixed"
    assert result_event["metadata"]["metadata"]["capability_cost_summary"] == {
        "total_tokens": 11,
        "total_calls": 1,
    }


@pytest.mark.asyncio
async def test_turn_runtime_updates_turn_observation_with_usage_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "answer", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {
            "scope_id": "turn_scope",
            "session_id": "session_scope",
            "turn_id": "turn_scope",
            "capability": "chat",
            "total_input_tokens": 90,
            "total_output_tokens": 10,
            "total_tokens": 100,
            "total_calls": 1,
            "measured_calls": 1,
            "estimated_calls": 0,
            "usage_accuracy": "measured",
            "usage_sources": {"provider": 1},
            "models": {"gpt-4o": 1},
            "total_cost_usd": 0.0008,
        },
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_updates
    final_update = captured_updates[-1]
    assert final_update["usage_details"] == {
        "input": 90.0,
        "output": 10.0,
        "total": 100.0,
    }
    assert final_update["cost_details"] == {
        "input": 0.0,
        "output": 0.0,
        "total": 0.0008,
    }


@pytest.mark.asyncio
async def test_turn_runtime_records_release_lineage_in_observation_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "answer", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.get_release_lineage_metadata",
        lambda: {
            "release_id": "1.0.0+abc123+prod",
            "service_version": "1.0.0",
            "git_sha": "abc123",
            "deployment_environment": "prod",
            "prompt_version": "prompt-v9",
            "ff_snapshot_hash": "ffaa00112233",
        },
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        lambda _observation, **kwargs: captured_updates.append(kwargs),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_updates
    metadata = captured_updates[-1]["metadata"]
    assert metadata["release_id"] == "1.0.0+abc123+prod"
    assert metadata["service_version"] == "1.0.0"
    assert metadata["git_sha"] == "abc123"
    assert metadata["deployment_environment"] == "prod"
    assert metadata["prompt_version"] == "prompt-v9"
    assert metadata["ff_snapshot_hash"] == "ffaa00112233"


@pytest.mark.asyncio
async def test_turn_runtime_records_aae_scores_in_observation_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []

    class FakeSurfaceEventStore:
        def get_turn_summary(self, _turn_id: str) -> dict[str, object]:
            return {
                "turn_id": "turn-test",
                "event_counts": {
                    "first_visible_content_rendered": 1,
                    "done_rendered": 1,
                },
                "first_visible_content_rendered": 1,
                "done_rendered": 1,
                "surface_render_failed": 0,
            }

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "继续分析这道题。", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.get_surface_event_store",
        lambda: FakeSurfaceEventStore(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        lambda _observation, **kwargs: captured_updates.append(kwargs),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "为什么我这题错了",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "followup_question_context": {
                    "parent_quiz_session_id": "quiz_session_1",
                    "question_id": "q_2",
                    "question_type": "choice",
                    "difficulty": "hard",
                    "concentration": "win-rate comparison",
                    "question": "Which criterion best describes density?",
                    "options": {
                        "A": "Coverage",
                        "B": "Informative value",
                        "C": "Relevant content without redundancy",
                        "D": "Credibility",
                    },
                    "user_answer": "B",
                    "correct_answer": "C",
                    "is_correct": True,
                    "explanation": "Density focuses on including relevant content without redundancy.",
                    "knowledge_context": "Density measures whether content is relevant and non-redundant.",
                }
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_updates
    metadata = captured_updates[-1]["metadata"]
    assert metadata["aae_scores"]["correctness_score"]["value"] == 1.0
    assert metadata["aae_scores"]["surface_render_score"]["value"] == 1.0
    assert metadata["aae_scores"]["paid_student_satisfaction_score"]["is_proxy"] is True
    assert metadata["aae_scores"]["latency_class"]["value"] in {"fast", "acceptable", "slow"}
    assert metadata["aae_composite"]["input_count"] >= 2
    assert metadata["aae_composite"]["is_proxy"] is True


@pytest.mark.asyncio
async def test_turn_runtime_wraps_selector_llm_calls_in_parent_turn_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeObservability:
        def __init__(self) -> None:
            self.active_observations: list[str] = []
            self.scope_active = False
            self.started: list[dict[str, object]] = []
            self.scopes: list[SimpleNamespace] = []
            self.updated: list[dict[str, object]] = []

        def usage_scope(self, **kwargs):
            outer = self

            class _UsageScope:
                def __enter__(self):
                    outer.scope_active = True
                    scope = SimpleNamespace(**kwargs)
                    outer.scopes.append(scope)
                    return scope

                def __exit__(self, *_args):
                    outer.scope_active = False
                    return False

            return _UsageScope()

        def start_observation(self, **kwargs):
            outer = self
            name = str(kwargs.get("name") or "")
            parent = outer.active_observations[-1] if outer.active_observations else None

            class _Observation:
                def __enter__(self):
                    outer.started.append(
                        {
                            "name": name,
                            "parent": parent,
                            "scope_active": outer.scope_active,
                            "metadata": dict(kwargs.get("metadata") or {}),
                        }
                    )
                    outer.active_observations.append(name)
                    return SimpleNamespace(name=name)

                def __exit__(self, *_args):
                    outer.active_observations.pop()
                    return False

            return _Observation()

        def update_observation(self, _observation, **kwargs):
            self.updated.append(kwargs)

        def get_current_usage_summary(self):
            return {}

        def summary_metadata(self, _summary):
            return {}

        def usage_details_from_summary(self, _summary):
            return None

        def cost_details_from_summary(self, _summary):
            return None

    fake_observability = FakeObservability()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            with fake_observability.start_observation(
                name="llm.stream",
                as_type="generation",
                metadata={"call_site": "context_builder"},
            ):
                pass
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, _context):
            with fake_observability.start_observation(
                name="llm.complete",
                as_type="generation",
                metadata={"call_site": "selector"},
            ):
                return "deep_question"

        async def handle(self, context):
            assert context.active_capability == "deep_question"
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="第1题",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    class FakeMemoryService:
        def build_memory_context(self):
            return ""

        async def refresh_from_turn(self, **_kwargs):
            with fake_observability.start_observation(
                name="llm.stream",
                as_type="generation",
                metadata={"call_site": "post_turn_memory"},
            ):
                pass

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("deeptutor.services.session.turn_runtime.observability", fake_observability)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: FakeMemoryService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选A",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "followup_question_context": {
                    "question_id": "q_1",
                    "question": "关于单层钢结构吊装顺序的说法，正确的有（ ）。",
                    "question_type": "choice",
                    "options": {"A": "单跨构宜从跨端一侧向另一侧吊装"},
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    selector_llm = next(item for item in fake_observability.started if item["name"] == "llm.complete")
    assert selector_llm["parent"] == "turn.runtime"
    assert selector_llm["scope_active"] is True
    assert fake_observability.scopes[0].capability == "deep_question"
    context_llm = next(
        item
        for item in fake_observability.started
        if item["name"] == "llm.stream" and item["metadata"].get("call_site") == "context_builder"
    )
    assert context_llm["parent"] == "turn.runtime"
    assert context_llm["scope_active"] is True
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))
    memory_llm = next(
        item
        for item in fake_observability.started
        if item["name"] == "llm.stream" and item["metadata"].get("call_site") == "post_turn_memory"
    )
    assert memory_llm["parent"] == "memory.consolidation"
    assert memory_llm["scope_active"] is True


@pytest.mark.asyncio
async def test_turn_runtime_wraps_learner_state_refresh_llm_in_parent_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeObservability:
        def __init__(self) -> None:
            self.active_observation: ContextVar[str | None] = ContextVar(
                "active_observation",
                default=None,
            )
            self.scope_active: ContextVar[bool] = ContextVar(
                "scope_active",
                default=False,
            )
            self.started: list[dict[str, object]] = []
            self.scopes: list[SimpleNamespace] = []

        def usage_scope(self, **kwargs):
            outer = self

            class _UsageScope:
                def __enter__(self):
                    self._token = outer.scope_active.set(True)
                    scope = SimpleNamespace(**kwargs)
                    outer.scopes.append(scope)
                    return scope

                def __exit__(self, *_args):
                    outer.scope_active.reset(self._token)
                    return False

            return _UsageScope()

        def start_observation(self, **kwargs):
            outer = self
            name = str(kwargs.get("name") or "")
            parent = outer.active_observation.get()

            class _Observation:
                def __enter__(self):
                    outer.started.append(
                        {
                            "name": name,
                            "parent": parent,
                            "scope_active": outer.scope_active.get(),
                            "metadata": dict(kwargs.get("metadata") or {}),
                        }
                    )
                    self._token = outer.active_observation.set(name)
                    return SimpleNamespace(name=name)

                def __exit__(self, *_args):
                    outer.active_observation.reset(self._token)
                    return False

            return _Observation()

        def update_observation(self, _observation, **_kwargs):
            return None

        def get_current_usage_summary(self):
            return {}

        def summary_metadata(self, _summary):
            return {}

        def usage_details_from_summary(self, _summary):
            return None

        def cost_details_from_summary(self, _summary):
            return None

    fake_observability = FakeObservability()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="ok",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context(self, **_kwargs):
            return ""

        async def refresh_from_turn(self, **_kwargs):
            with fake_observability.start_observation(
                name="llm.stream",
                as_type="generation",
                metadata={"call_site": "post_turn_learner"},
            ):
                pass

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("deeptutor.services.session.turn_runtime.observability", fake_observability)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wechat",
                    "user_id": "learner-1",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))

    refresh = next(item for item in fake_observability.started if item["name"] == "learner_state.refresh")
    assert refresh["parent"] == "turn.chat"
    assert refresh["scope_active"] is True
    learner_llm = next(
        item
        for item in fake_observability.started
        if item["name"] == "llm.stream" and item["metadata"].get("call_site") == "post_turn_learner"
    )
    assert learner_llm["parent"] == "learner_state.refresh"
    assert learner_llm["scope_active"] is True
    assert fake_observability.scopes[-1].scope_id == f"{turn['id']}:post_turn_refresh"
    assert fake_observability.scopes[-1].turn_id == turn["id"]
    assert fake_observability.scopes[-1].capability == "chat"


@pytest.mark.asyncio
async def test_post_turn_refresh_continues_when_observability_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    refreshed = {"value": False}

    class FailingObservability:
        def usage_scope(self, **_kwargs):
            raise RuntimeError("usage scope unavailable")

        def start_observation(self, **_kwargs):
            raise RuntimeError("observation unavailable")

    class FakeMemoryService:
        async def refresh_from_turn(self, **_kwargs):
            refreshed["value"] = True

    monkeypatch.setattr("deeptutor.services.session.turn_runtime.observability", FailingObservability())

    runtime._schedule_post_turn_refresh(
        turn_id="turn_observability_fail",
        user_id="",
        raw_user_content="hello",
        assistant_content="ok",
        session_id="session_observability_fail",
        capability_name="chat",
        language="zh",
        source_bot_id="",
        context_route="",
        task_anchor_type="",
        learner_state_service=SimpleNamespace(),
        memory_service=FakeMemoryService(),
    )
    await asyncio.gather(*list(runtime._background_tasks))

    assert refreshed["value"] is True


@pytest.mark.asyncio
async def test_turn_runtime_metrics_track_completed_and_failed_turns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.api.runtime_metrics import get_turn_runtime_metrics, reset_turn_runtime_metrics
    from deeptutor.services.observability import get_turn_event_log, reset_turn_event_log

    reset_turn_runtime_metrics()
    reset_turn_event_log(events_dir=tmp_path / "observer_events")
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    usage_scope_closed = {"value": False}

    class FakeUsageScope:
        def __enter__(self):
            usage_scope_closed["value"] = False
            return None

        def __exit__(self, *_args):
            usage_scope_closed["value"] = True
            return False

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class CompletedOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "ok", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FailedOrchestrator:
        async def handle(self, _context):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.usage_scope",
        lambda **_kwargs: FakeUsageScope(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {}
        if usage_scope_closed["value"]
        else {
            "total_input_tokens": 7,
            "total_output_tokens": 5,
            "total_tokens": 12,
            "total_calls": 1,
        },
    )

    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", CompletedOrchestrator)
    _session, completed_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(completed_turn["id"], after_seq=0):
        pass

    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FailedOrchestrator)
    _session, failed_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello again",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(failed_turn["id"], after_seq=0):
        pass

    snapshot = get_turn_runtime_metrics().snapshot()
    assert snapshot["turns_started_total"] == 2
    assert snapshot["turns_completed_total"] == 1
    assert snapshot["turns_failed_total"] == 1
    assert snapshot["turns_in_flight"] == 0
    assert snapshot["turn_avg_latency_ms"] >= 0
    turn_events = get_turn_event_log().load_events()
    assert [item["status"] for item in turn_events] == ["completed", "failed"]
    assert [item["token_total"] for item in turn_events] == [12, 12]
    assert all((item.get("metadata") or {}).get("source") == "turn_runtime_terminal" for item in turn_events)


@pytest.mark.asyncio
async def test_turn_runtime_observer_breaks_down_start_setup_and_capability_stream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.observability import get_turn_event_log, reset_turn_event_log

    reset_turn_event_log(events_dir=tmp_path / "observer_events")
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                content="hello",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={
                    "response": "hello",
                    "metadata": {
                        "llm_stream_telemetry": {
                            "call_count": 1,
                            "calls": [
                                {
                                    "call_site": "fast_policy",
                                    "provider_name": "dashscope",
                                    "model": "deepseek-v4-flash",
                                    "stream_chunk_count": 4,
                                    "stream_content_chunk_count": 3,
                                    "stage_timings_ms": {
                                        "provider_first_content_delta": 123.4,
                                        "provider_stream_read": 456.7,
                                    },
                                }
                            ],
                        }
                    },
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    turn_events = get_turn_event_log().load_events()
    assert len(turn_events) == 1
    metadata = turn_events[0]["metadata"]
    assert "ensure_session" in metadata["start_turn_setup_stage_timings_ms"]
    assert "create_turn" in metadata["start_turn_setup_stage_timings_ms"]
    assert "publish_session_event" in metadata["start_turn_setup_stage_timings_ms"]
    assert "first_event" in metadata["capability_stream_stage_timings_ms"]
    assert "first_content" in metadata["capability_stream_stage_timings_ms"]
    assert "first_result" in metadata["capability_stream_stage_timings_ms"]
    assert "event_persist_total" in metadata["capability_stream_stage_timings_ms"]
    assert metadata["capability_stream_event_counts"]["content"] == 1
    assert metadata["capability_stream_event_counts"]["result"] == 1
    assert metadata["capability_stream_event_counts"]["done"] == 1
    assert metadata["llm_stream_telemetry"]["calls"][0]["provider_name"] == "dashscope"
    assert (
        metadata["llm_stream_telemetry"]["calls"][0]["stage_timings_ms"][
            "provider_first_content_delta"
        ]
        == 123.4
    )


@pytest.mark.asyncio
async def test_turn_runtime_deadline_marks_stuck_turn_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.api.runtime_metrics import get_turn_runtime_metrics, reset_turn_runtime_metrics

    reset_turn_runtime_metrics()
    monkeypatch.setenv("TURN_RUNTIME_FAST_TURN_TIMEOUT_SECONDS", "0.3")
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    started = asyncio.Event()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class StuckOrchestrator:
        async def handle(self, _context):
            started.set()
            yield StreamEvent(
                type=StreamEventType.PROGRESS,
                source="deep_question",
                stage="generation",
                content="Grade q_1",
                metadata={"call_state": "running"},
            )
            await asyncio.Event().wait()

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", StuckOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第1题选B，请批改",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"chat_mode": "fast"},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)
        if event["type"] == "done":
            break

    assert started.is_set()
    assert [event["type"] for event in events[-2:]] == ["error", "done"]
    assert events[-1]["metadata"]["status"] == "failed"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["status"] == "failed"
    assert "runtime deadline" in persisted_turn["error"]
    snapshot = get_turn_runtime_metrics().snapshot()
    assert snapshot["turns_started_total"] == 1
    assert snapshot["turns_failed_total"] == 1
    assert snapshot["turns_in_flight"] == 0


@pytest.mark.asyncio
async def test_turn_runtime_records_semantic_router_rollout_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []
    captured_context: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured_context["config_overrides"] = dict(context.config_overrides)
            context.metadata["semantic_router_mode"] = "shadow"
            context.metadata["semantic_router_mode_reason"] = "shadow_compare_only"
            context.metadata["semantic_router_scope"] = "question_only"
            context.metadata["semantic_router_scope_match"] = True
            context.metadata["semantic_router_shadow_decision"] = {
                "relation_to_active_object": "answer_active_object",
                "next_action": "route_to_grading",
            }
            context.metadata["semantic_router_shadow_route"] = "deep_question"
            context.metadata["semantic_router_selected_capability"] = "chat"
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={"response": "仍按旧链路执行。", "metadata": {}},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "semantic_router_enabled": False,
                "semantic_router_shadow_mode": True,
                "semantic_router_scope": "question_only",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    config_overrides = captured_context["config_overrides"]
    assert config_overrides["semantic_router_enabled"] is False
    assert config_overrides["semantic_router_shadow_mode"] is True
    assert config_overrides["semantic_router_scope"] == "question_only"
    assert captured_updates
    final_update = captured_updates[-1]
    metadata = final_update["metadata"]
    assert metadata["semantic_router_mode"] == "shadow"
    assert metadata["semantic_router_mode_reason"] == "shadow_compare_only"
    assert metadata["semantic_router_scope"] == "question_only"
    assert metadata["semantic_router_scope_match"] is True
    assert metadata["semantic_router_shadow_route"] == "deep_question"
    assert metadata["semantic_router_selected_capability"] == "chat"
    assert metadata["semantic_router_shadow_decision"]["next_action"] == "route_to_grading"


@pytest.mark.asyncio
async def test_turn_runtime_bootstraps_question_followup_context_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            captured["history_messages"] = messages
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["conversation_history"] = context.conversation_history
            captured["config_overrides"] = context.config_overrides
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="Let's discuss this question.",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "Why is my answer wrong?",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {
                "followup_question_context": {
                    "parent_quiz_session_id": "quiz_session_1",
                    "question_id": "q_2",
                    "question_type": "choice",
                    "difficulty": "hard",
                    "concentration": "win-rate comparison",
                    "question": "Which criterion best describes density?",
                    "options": {
                        "A": "Coverage",
                        "B": "Informative value",
                        "C": "Relevant content without redundancy",
                        "D": "Credibility",
                    },
                    "user_answer": "B",
                    "correct_answer": "C",
                    "explanation": "Density focuses on including relevant content without redundancy.",
                    "knowledge_context": "Density measures whether content is relevant and non-redundant.",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert [message["role"] for message in detail["messages"]] == ["system", "user", "assistant"]
    assert "Question Follow-up Context" in detail["messages"][0]["content"]
    assert "Which criterion best describes density?" in detail["messages"][0]["content"]
    assert "User answer: B" in detail["messages"][0]["content"]
    assert captured["conversation_history"][0]["role"] == "system"
    assert "followup_question_context" not in captured["config_overrides"]
    assert captured["metadata"]["question_followup_context"]["question_id"] == "q_2"


@pytest.mark.asyncio
async def test_turn_runtime_publishes_live_events_when_persistence_degrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    session = await store.create_session(session_id="session-live")
    turn = await store.create_turn(session["id"], capability="chat")
    execution = _TurnExecution(
        turn_id=turn["id"],
        session_id=session["id"],
        capability="chat",
        payload={},
    )
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    execution.subscribers.append(_LiveSubscriber(queue=queue))
    runtime._executions[turn["id"]] = execution

    async def _broken_append(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "append_turn_event", _broken_append)
    monkeypatch.setattr(
        TurnRuntimeManager,
        "_mirror_event_to_workspace",
        staticmethod(lambda *_args, **_kwargs: None),
    )

    payload = await runtime._persist_and_publish(
        execution,
        StreamEvent(
            type=StreamEventType.CONTENT,
            source="chat",
            stage="responding",
            content="partial answer",
        ),
    )
    delivered = await queue.get()

    assert execution.persistence_degraded is True
    assert payload["content"] == "partial answer"
    assert delivered["content"] == "partial answer"


@pytest.mark.asyncio
async def test_turn_runtime_recovers_active_question_context_from_previous_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"contexts": []}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        call_count = 0

        async def handle(self, context):
            FakeOrchestrator.call_count += 1
            captured["contexts"].append(context.metadata.get("question_followup_context"))
            if FakeOrchestrator.call_count == 1:
                yield StreamEvent(
                    type=StreamEventType.RESULT,
                    source="deep_question",
                    metadata={
                        "mode": "custom",
                        "question_followup_context": {
                            "question_id": "q_saved",
                            "question": "案例背景......第1问：判断是否合理。",
                            "question_type": "written",
                            "reveal_answers": False,
                            "reveal_explanations": False,
                        },
                    },
                )
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="deep_question",
                    stage="generation",
                    content="第1问：判断是否合理。",
                    metadata={"call_kind": "llm_final_response"},
                )
            else:
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="deep_question",
                    stage="generation",
                    content="好的，只问第1问。",
                    metadata={"call_kind": "llm_final_response"},
                )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "给我一道案例题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass

    second_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "先别给答案，只问我第1问",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(second_turn[1]["id"], after_seq=0):
        pass

    active_context = await store.get_active_question_context(session["id"])
    assert active_context is not None
    assert active_context["question_id"] == "q_saved"
    assert captured["contexts"][1]["question_id"] == "q_saved"


@pytest.mark.asyncio
async def test_turn_runtime_backfills_result_execution_metadata_for_deep_question(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    session = await store.create_session(session_id="session-meta")
    turn = await store.create_turn(session["id"], capability="deep_question")
    execution = _TurnExecution(
        turn_id=turn["id"],
        session_id=session["id"],
        capability="chat",
        payload={
            "capability": None,
            "config": {
                "chat_mode": "fast",
                "interaction_hints": {
                    "requested_response_mode": "smart",
                    "selected_mode": "fast",
                },
            },
        },
    )
    monkeypatch.setattr(
        TurnRuntimeManager,
        "_mirror_event_to_workspace",
        staticmethod(lambda *_args, **_kwargs: None),
    )

    payload = await runtime._persist_and_publish(
        execution,
        StreamEvent(
            type=StreamEventType.RESULT,
            source="deep_question",
            metadata={
                "response": "graded response",
                "mode": "grading",
            },
        ),
    )

    assert payload["metadata"]["selected_mode"] == "fast"
    assert payload["metadata"]["execution_path"] == "deep_question_grading"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_recover_active_question_context_from_presentation_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"contexts": []}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        call_count = 0

        async def handle(self, context):
            FakeOrchestrator.call_count += 1
            captured["contexts"].append(context.metadata.get("question_followup_context"))
            if FakeOrchestrator.call_count == 1:
                yield StreamEvent(
                    type=StreamEventType.RESULT,
                    source="chat",
                    metadata={
                        "response": "### Question 1\n\n关于屋面防水等级和设防要求，下列说法正确的是？\n- A. 说法A\n- B. 说法B\n- C. 说法C\n- D. 说法D",
                        "presentation": {
                            "schema_version": 1,
                            "blocks": [
                                {
                                    "type": "mcq",
                                    "questions": [
                                        {
                                            "index": 1,
                                            "question_id": "q_saved_from_presentation",
                                            "stem": "关于屋面防水等级和设防要求，下列说法正确的是？",
                                            "question_type": "single_choice",
                                            "options": [
                                                {"key": "A", "text": "说法A"},
                                                {"key": "B", "text": "说法B"},
                                                {"key": "C", "text": "说法C"},
                                                {"key": "D", "text": "说法D"},
                                            ],
                                            "followup_context": {
                                                "question_id": "q_saved_from_presentation",
                                                "question": "关于屋面防水等级和设防要求，下列说法正确的是？",
                                                "question_type": "choice",
                                                "options": {
                                                    "A": "说法A",
                                                    "B": "说法B",
                                                    "C": "说法C",
                                                    "D": "说法D",
                                                },
                                                "correct_answer": "C",
                                                "explanation": "C 正确。",
                                            },
                                        }
                                    ],
                                }
                            ],
                            "fallback_text": "### Question 1\n\n关于屋面防水等级和设防要求，下列说法正确的是？\n- A. 说法A\n- B. 说法B\n- C. 说法C\n- D. 说法D",
                        },
                    },
                )
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="chat",
                    stage="responding",
                    content="### Question 1\n\n关于屋面防水等级和设防要求，下列说法正确的是？\n- A. 说法A\n- B. 说法B\n- C. 说法C\n- D. 说法D",
                    metadata={"call_kind": "llm_final_response"},
                )
            else:
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="deep_question",
                    stage="generation",
                    content="你选了 A，正确答案是 C。",
                    metadata={"call_kind": "llm_final_response"},
                )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "给我一道屋面防水单选题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass

    second_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选A。",
            "session_id": session["id"],
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(second_turn[1]["id"], after_seq=0):
        pass

    active_context = await store.get_active_question_context(session["id"])
    assert active_context is None
    assert captured["contexts"] == [None, None]


@pytest.mark.asyncio
async def test_turn_runtime_does_not_pin_tutorbot_for_recovered_question_submission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, _context):
            return "deep_question"

        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="你选了 A。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "q_saved",
            "question": "关于屋面防水等级与对应防水设防道数的要求，以下说法正确的是？",
            "question_type": "choice",
            "options": {
                "A": "一级防水时，防水设防不应少于2道",
                "B": "二级防水时，防水设防不应少于3道",
                "C": "三级防水时，防水设防不应少于2道",
                "D": "一级防水时，防水设防不应少于3道",
            },
            "correct_answer": "D",
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我选A。",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["active_capability"] == "deep_question"
    assert captured["question_followup_context"]["question_id"] == "q_saved"
    assert captured["question_followup_context"]["correct_answer"] == "D"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_pin_tutorbot_when_llm_identifies_followup_that_regex_misses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, _context):
            return "deep_question"

        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            captured["question_followup_action"] = context.metadata.get(
                "question_followup_action"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="按修正后的答案继续批改。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    async def _fake_interpret(_message, question_context, **_kwargs):
        if str((question_context or {}).get("question_id") or "") != "quiz_llm_runtime":
            return None
        return {
            "intent": "revise_answers",
            "confidence": 0.97,
            "preserve_other_answers": True,
            "answers": [
                {
                    "index": 1,
                    "question_id": "q_1",
                    "user_answer": "C",
                }
            ],
            "reason": "用户是在基于已有题组修改第一题答案。",
        }

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.interpret_question_followup_action",
        _fake_interpret,
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_llm_followup")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_llm_runtime",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                    "user_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "B",
                    "user_answer": "B",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "single_choice",
                    "correct_answer": "D",
                    "user_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第一题我改C，别的不动",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] == "deep_question"
    assert captured["question_followup_context"]["question_id"] == "quiz_llm_runtime"
    assert captured["question_followup_action"]["intent"] == "revise_answers"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_treats_choice_type_as_generation_with_stored_active_question(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["metadata"] = dict(context.metadata or {})
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source=context.active_capability or "tutorbot",
                stage="generation",
                content="这里应该继续出一道选择题。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source=context.active_capability or "tutorbot")

    async def _misleading_interpret(_message, question_context, **_kwargs):
        if str((question_context or {}).get("question_id") or "") != "q_choice_saved":
            return None
        return {
            "intent": "answer_questions",
            "confidence": 0.93,
            "answers": [{"index": 1, "question_id": "q_choice_saved", "user_answer": "A"}],
            "reason": "模拟 LLM 把“选择题”误判成上一题答案。",
        }

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.interpret_question_followup_action",
        _misleading_interpret,
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_choice_type_generation")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "q_choice_saved",
            "question": "楼梯平台净高的最低要求是多少？",
            "question_type": "choice",
            "options": {
                "A": "1.8m",
                "B": "2.0m",
                "C": "2.2m",
                "D": "2.4m",
            },
            "correct_answer": "C",
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "选择题",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    metadata = captured["metadata"]
    followup_action = metadata["question_followup_action"]
    followup_context = metadata["question_followup_context"]
    assert followup_action["intent"] == "generate_more_questions"
    assert followup_action["answers"] == []
    assert followup_context["question_id"] == "q_choice_saved"
    assert followup_context.get("user_answer", "") == ""
    assert followup_context.get("is_correct") is None


@pytest.mark.asyncio
async def test_turn_runtime_treats_written_question_type_request_as_generation_with_stored_active_question(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = dict(context.metadata or {})
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source=context.active_capability or "tutorbot",
                stage="generation",
                content="这里应该继续出一道简答题。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source=context.active_capability or "tutorbot")

    async def _misleading_interpret(_message, question_context, **_kwargs):
        if str((question_context or {}).get("question_id") or "") != "q_written_saved":
            return None
        return {
            "intent": "answer_questions",
            "confidence": 0.9,
            "answers": [
                {
                    "index": 1,
                    "question_id": "q_written_saved",
                    "user_answer": "给我出简答题",
                }
            ],
            "reason": "模拟 LLM 把简答题请求误判成上一道主观题答案。",
        }

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.interpret_question_followup_action",
        _misleading_interpret,
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_written_type_generation")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "q_written_saved",
            "question": "指出该防水施工做法中的不妥之处。",
            "question_type": "written",
            "correct_answer": "应指出不妥并写出正确做法。",
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "给我出简答题",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    metadata = captured["metadata"]
    followup_action = metadata["question_followup_action"]
    followup_context = metadata["question_followup_context"]
    assert followup_action["intent"] == "generate_more_questions"
    assert followup_action["answers"] == []
    assert followup_context["question_id"] == "q_written_saved"
    assert followup_context.get("user_answer", "") == ""
    assert followup_context.get("is_correct") is None


@pytest.mark.asyncio
async def test_turn_runtime_suspends_active_question_for_unrelated_general_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = dict(context.metadata)
            captured["active_capability"] = context.active_capability
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="先回答这个新问题。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="session_suspend_question", title="流水施工")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_suspend_runtime",
            "question": "第1题...\n第2题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                    "user_answer": "B",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                    "user_answer": "C",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "先暂停一下。顺便问个别的：横道图和网络图哪个更适合考试答题时分析关键线路？",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_profile": "mini_tutor",
                "interaction_hints": {
                    "profile": "mini_tutor",
                    "teaching_mode": "smart",
                },
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["active_capability"] is None
    assert "question_followup_context" not in captured["metadata"]
    assert captured["metadata"]["context_route"] == "general_learning_query"
    assert captured["metadata"]["active_object"]["object_type"] == "open_chat_topic"
    assert captured["metadata"]["suspended_object_stack"][0]["object_type"] == "question_set"

    stored_active_object = await store.get_active_object(session["id"])
    stored_suspended_stack = await store.get_suspended_object_stack(session["id"])
    assert stored_active_object is not None
    assert stored_active_object["object_type"] == "open_chat_topic"
    assert stored_suspended_stack[0]["object_type"] == "question_set"


@pytest.mark.asyncio
async def test_turn_runtime_suspends_active_question_before_smart_mode_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            captured["metadata"] = dict(context.metadata)
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={
                    "response": "先回答这个新问题。",
                    "selected_mode": "fast",
                    "execution_path": "tutorbot_kb_first_fast_policy",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    session = await store.create_session(
        session_id="session_suspend_question_mode",
        title="流水施工",
    )
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_suspend_runtime_mode",
            "question": "第1题...\n第2题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                    "user_answer": "B",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                    "user_answer": "C",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "先暂停一下。顺便问个别的：横道图和网络图哪个更适合考试答题时分析关键线路？",
            "session_id": session["id"],
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "requested_response_mode": "smart",
                },
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["chat_mode"] == "fast"
    assert "question_followup_context" not in captured["metadata"]
    assert captured["metadata"]["context_route"] == "general_learning_query"
    assert captured["metadata"]["active_object"]["object_type"] == "open_chat_topic"
    metadata = captured_updates[-1]["metadata"]
    assert metadata["chat_mode"] == "fast"
    assert metadata["requested_response_mode"] == "smart"
    assert metadata["effective_response_mode"] == "fast"
    assert metadata["selected_mode"] == "fast"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_batch_submission_in_chat_for_stored_question_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            captured["question_followup_action"] = context.metadata.get(
                "question_followup_action"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始批改这一组题。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_batch_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_batch",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "choice",
                    "correct_answer": "C",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "choice",
                    "correct_answer": "A",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "choice",
                    "correct_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第1题：C；第2题：A；第3题：B",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    assert captured["question_followup_context"]["question_id"] == "quiz_batch"
    assert len(captured["question_followup_context"]["items"]) == 3
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_recovers_tutorbot_mirror_question_set_for_batch_submission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            captured["question_followup_action"] = context.metadata.get(
                "question_followup_action"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始批改前两题。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    user_id = "user_mirror_batch"
    session = await store.create_session(session_id="session_primary_without_question_set")
    mirror_session_id = (
        "tutorbot:bot:construction-exam-coach:"
        f"user:{user_id}:chat:{session['id']}"
    )
    await store.create_session(session_id=mirror_session_id)
    await store.set_active_question_context(
        mirror_session_id,
        {
            "question_id": "quiz_mirror",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "下列哪个不属于主体结构子分部工程？",
                    "question_type": "choice",
                    "options": {
                        "A": "混凝土结构",
                        "B": "网架结构",
                        "C": "砌体结构",
                        "D": "铝合金结构",
                    },
                    "correct_answer": "B",
                },
                {
                    "question_id": "q_2",
                    "question": "以下哪一组全部属于主体结构子分部工程？",
                    "question_type": "choice",
                    "options": {
                        "A": "混凝土结构、砌体结构、钢结构、网架结构",
                        "B": "混凝土结构、砌体结构、钢结构、铝合金结构",
                        "C": "钢管混凝土结构、型钢混凝土结构、网架结构、木结构",
                        "D": "混凝土结构、砌体结构、钢结构、装配式结构",
                    },
                    "correct_answer": "B",
                },
                {
                    "question_id": "q_3",
                    "question": "下列哪个不属于主体结构子分部工程？",
                    "question_type": "choice",
                    "correct_answer": "C",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第1题：B；第2题：B",
            "session_id": session["id"],
            "capability": "tutorbot",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "chat_mode": "deep",
                "interaction_profile": "tutorbot",
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": user_id,
                    "learning_user_id": user_id,
                },
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    resolved = captured["question_followup_context"]
    assert resolved["question_id"] == "quiz_mirror"
    action = captured["question_followup_action"]
    assert action["intent"] == "answer_questions"
    assert [(item["question_id"], item["user_answer"]) for item in action["answers"]] == [
        ("q_1", "B"),
        ("q_2", "B"),
    ]
    assert [
        (item["question_id"], item.get("correct_answer"))
        for item in resolved["items"][:2]
    ] == [("q_1", "B"), ("q_2", "B")]
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_compact_batch_letters_in_chat_for_stored_question_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始按顺序批改。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_compact_batch_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_compact",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "single_choice",
                    "correct_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "ACD；",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    assert [item["question_id"] for item in captured["question_followup_context"]["items"]] == [
        "q_1",
        "q_2",
        "q_3",
    ]
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_compact_numbered_batch_in_chat_for_stored_question_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始按编号顺序批改。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_compact_numbered_batch_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_compact_numbered",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "single_choice",
                    "correct_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第一题A第二题C第三题D",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] is None
    assert [item["question_id"] for item in captured["question_followup_context"]["items"]] == [
        "q_1",
        "q_2",
        "q_3",
    ]
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_keeps_batch_correction_in_chat_for_stored_question_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def _select_capability(self, _context):
            return "deep_question"

        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["question_followup_context"] = context.metadata.get(
                "question_followup_context"
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="开始按修正后的答案批改。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime._resolve_bot_runtime_defaults",
        lambda **_kwargs: {
            "execution_engine": "tutorbot_runtime",
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "defaults_source": "bot_runtime_defaults",
        },
    )

    session = await store.create_session(session_id="session_tutorbot_batch_correction_submission")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "quiz_correction",
            "question": "第1题...\n第2题...\n第3题...",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_1",
                    "question": "题1",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                    "user_answer": "A",
                },
                {
                    "question_id": "q_2",
                    "question": "题2",
                    "question_type": "single_choice",
                    "correct_answer": "C",
                    "user_answer": "B",
                },
                {
                    "question_id": "q_3",
                    "question": "题3",
                    "question_type": "single_choice",
                    "correct_answer": "D",
                    "user_answer": "D",
                },
            ],
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第2题改成C，其他不变",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
            },
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert turn["capability"] == "deep_question"
    assert captured["active_capability"] == "deep_question"
    assert captured["question_followup_context"]["question_id"] == "quiz_correction"
    assert len(captured["question_followup_context"]["items"]) == 3
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_inject_stale_question_context_for_unrelated_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"contexts": []}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["contexts"].append(context.metadata.get("question_followup_context"))
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="普通讲解回复",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="session_general")
    await store.set_active_question_context(
        session["id"],
        {
            "question_id": "q_saved",
            "question": "第1题：判断是否合理。",
            "question_type": "written",
            "reveal_answers": False,
            "reveal_explanations": False,
        },
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "建筑构造是什么？",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["contexts"] == [None]


@pytest.mark.asyncio
async def test_turn_runtime_recovers_orphaned_running_turn_before_new_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="after recovery",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session = await store.create_session(session_id="orphan-session")
    orphan_turn = await store.create_turn(session["id"], capability="chat")

    _session, new_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续下一轮",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    async for _event in runtime.subscribe_turn(new_turn["id"], after_seq=0):
        pass

    recovered = await store.get_turn(orphan_turn["id"])
    assert recovered is not None
    assert recovered["status"] == "failed"


@pytest.mark.asyncio
async def test_turn_runtime_cancels_superseded_running_turn_before_new_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    first_turn_started = asyncio.Event()
    first_turn_cancelled = asyncio.Event()
    orchestrator_calls = {"count": 0}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            orchestrator_calls["count"] += 1
            if orchestrator_calls["count"] == 1:
                first_turn_started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    first_turn_cancelled.set()
                    raise
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="second turn answer",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第一轮问题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    await asyncio.wait_for(first_turn_started.wait(), timeout=1.0)

    _session, second_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第二轮问题",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    await asyncio.wait_for(first_turn_cancelled.wait(), timeout=1.0)
    async for _event in runtime.subscribe_turn(second_turn["id"], after_seq=0):
        pass

    cancelled_turn = await store.get_turn(first_turn["id"])
    completed_turn = await store.get_turn(second_turn["id"])

    assert cancelled_turn is not None
    assert cancelled_turn["status"] == "cancelled"
    assert completed_turn is not None
    assert completed_turn["status"] == "completed"
    messages = await store.get_messages(session["id"])
    cancelled_assistant = [
        item for item in messages
        if item["role"] == "assistant" and "取消" in item["content"]
    ]
    assert cancelled_assistant


@pytest.mark.asyncio
async def test_turn_runtime_preserves_terminal_commit_when_new_turn_arrives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    terminal_commit_started = asyncio.Event()
    release_terminal_commit = asyncio.Event()

    class BlockingAssistantStore(SQLiteSessionStore):
        async def add_message(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            role = kwargs.get("role") if kwargs else None
            content = kwargs.get("content") if kwargs else None
            if role is None and len(args) >= 2:
                role = args[1]
            if content is None and len(args) >= 3:
                content = args[2]
            if role == "assistant" and str(content or "") == "first turn answer":
                terminal_commit_started.set()
                await release_terminal_commit.wait()
            return await super().add_message(*args, **kwargs)

    store = BlockingAssistantStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    orchestrator_calls = {"count": 0}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            orchestrator_calls["count"] += 1
            if orchestrator_calls["count"] == 1:
                yield StreamEvent(
                    type=StreamEventType.CONTENT,
                    source="deep_question",
                    stage="grading",
                    content="first turn answer",
                    metadata={"call_kind": "llm_final_response"},
                )
                yield StreamEvent(type=StreamEventType.DONE, source="deep_question")
                return
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="grading",
                content="second turn answer",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "第一轮 deep question",
            "session_id": None,
            "capability": "deep_question",
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    await asyncio.wait_for(terminal_commit_started.wait(), timeout=1.0)

    second_start = asyncio.create_task(
        runtime.start_turn(
            {
                "type": "start_turn",
                "content": "第二轮 deep question",
                "session_id": session["id"],
                "capability": "deep_question",
                "tools": [],
                "knowledge_bases": [],
                "attachments": [],
                "language": "zh",
                "config": {},
            }
        )
    )
    await asyncio.sleep(0)
    assert not second_start.done()

    release_terminal_commit.set()
    _session, second_turn = await asyncio.wait_for(second_start, timeout=1.0)
    async for _event in runtime.subscribe_turn(second_turn["id"], after_seq=0):
        pass

    first = await store.get_turn(first_turn["id"])
    second = await store.get_turn(second_turn["id"])
    assert first is not None
    assert first["status"] == "completed"
    assert second is not None
    assert second["status"] == "completed"
    messages = await store.get_messages(session["id"])
    assert any(item["role"] == "assistant" and item["content"] == "first turn answer" for item in messages)
    assert all("取消" not in item["content"] for item in messages if item["role"] == "assistant")


@pytest.mark.asyncio
async def test_turn_runtime_fails_closed_for_provider_raw_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            raise RuntimeError("<400> InternalError.Algo.DataInspectionFailed: raw provider rejection")
            yield

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "触发 provider error",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    failed_turn = await store.get_turn(turn["id"])
    messages = await store.get_messages(session["id"])
    error_events = [item for item in events if item.get("type") == "error"]

    assert failed_turn is not None
    assert failed_turn["status"] == "failed"
    assert error_events
    assert "InternalError" not in error_events[-1]["content"]
    assert "DataInspectionFailed" not in error_events[-1]["content"]
    assistant_messages = [item for item in messages if item["role"] == "assistant"]
    assert assistant_messages
    assert "InternalError" not in assistant_messages[-1]["content"]
    assert "DataInspectionFailed" not in assistant_messages[-1]["content"]


@pytest.mark.asyncio
async def test_turn_runtime_fails_closed_for_provider_html_error_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.ERROR,
                source="chat",
                content=(
                    '<!doctype html><html lang="en"><head><title>Example Domain</title></head>'
                    "<body><h1>Example Domain</h1></body></html>"
                ),
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "触发 provider html error",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    messages = await store.get_messages(session["id"])
    error_events = [item for item in events if item.get("type") == "error"]

    assert error_events
    assert "Example Domain" not in error_events[-1]["content"]
    assert "<!doctype html>" not in error_events[-1]["content"]
    assistant_messages = [item for item in messages if item["role"] == "assistant"]
    assert assistant_messages
    assert "Example Domain" not in assistant_messages[-1]["content"]


@pytest.mark.asyncio
async def test_turn_runtime_coerces_provider_auth_error_returned_as_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={
                    "response": (
                        "Error: {'message': 'Authentication Fails, Your api key: ****486e is invalid', "
                        "'type': 'authentication_error', 'param': None, 'code': 'invalid_request_error'}"
                    )
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "触发 provider auth error",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )
    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    messages = await store.get_messages(session["id"])
    assistant_messages = [item for item in messages if item["role"] == "assistant"]
    result_events = [item for item in events if item.get("type") == "result"]
    assert result_events
    assert result_events[-1]["metadata"]["response"] == "暂时未生成适合直接展示的答案，请重试一次。"
    assert "Authentication Fails" not in result_events[-1]["metadata"]["response"]
    assert "invalid_request_error" not in result_events[-1]["metadata"]["response"]
    assert assistant_messages
    assert assistant_messages[-1]["content"] == "暂时未生成适合直接展示的答案，请重试一次。"
    assert "Authentication Fails" not in assistant_messages[-1]["content"]
    assert "invalid_request_error" not in assistant_messages[-1]["content"]


@pytest.mark.asyncio
async def test_turn_runtime_bootstraps_interaction_hints_as_soft_system_guidance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, session_store, *_args, **_kwargs) -> None:
            self.store = session_store

        async def build(self, **kwargs):
            messages = await self.store.get_messages_for_context(kwargs["session_id"])
            captured["history_messages"] = messages
            return SimpleNamespace(
                conversation_history=[
                    {"role": item["role"], "content": item["content"]}
                    for item in messages
                ],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["config_overrides"] = context.config_overrides
            captured["metadata"] = context.metadata
            captured["conversation_history"] = context.conversation_history
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="好的，我们按学习场景来处理。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "考我一道流水施工的题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_hints": {
                    "profile": "tutorbot",
                    "preferred_question_type": "choice",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["preferences"]["interaction_hints"]["profile"] == "tutorbot"
    assert detail["preferences"]["interaction_hints"]["preferred_question_type"] == "choice"
    assert "suppress_answer_reveal_on_generate" not in detail["preferences"]["interaction_hints"]
    assert "interaction_hints" not in captured["config_overrides"]
    assert captured["metadata"]["interaction_hints"]["profile"] == "tutorbot"
    assert captured["metadata"]["context_route"] == "general_learning_query"
    assert captured["metadata"]["escalation_level"] == 1
    assert "suppress_answer_reveal_on_generate" not in captured["metadata"]["interaction_hints"]
    assert captured["conversation_history"] == []


@pytest.mark.asyncio
async def test_turn_runtime_allows_m35_artifact_shadow_flags_as_runtime_only_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "m35_runtime_only.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["config_overrides"] = dict(context.config_overrides)
            captured["metadata"] = dict(context.metadata)
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="responding",
                content="已进入 M35 shadow drill。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "提交案例题答案",
            "session_id": None,
            "capability": "deep_question",
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "grading_engine_m35_artifact_shadow": True,
            },
        }
    )

    async def _collect_events() -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
            events.append(event)
        return events

    events = await asyncio.wait_for(_collect_events(), timeout=5)

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    config = captured["config_overrides"]
    assert config["grading_engine_m35_artifact_shadow"] is True
    metadata = captured["metadata"]
    assert metadata["context_route"] == "general_learning_query"


@pytest.mark.asyncio
async def test_turn_runtime_preserves_current_info_hint_for_mode_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="2026 年一级建造师考试时间需要联网核验。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请联网搜索2026一建考试时间，并给出来源链接。",
            "session_id": None,
            "capability": None,
            "tools": ["web_search"],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "current_info_required": True,
                    "grounding_reasons": ["current_info_required"],
                },
                "bot_id": "construction-exam-coach",
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    hints = detail["preferences"]["interaction_hints"]
    metadata = captured["metadata"]

    assert hints["current_info_required"] is True
    assert hints["grounding_reasons"] == ["current_info_required"]
    assert metadata["interaction_hints"]["current_info_required"] is True
    assert metadata["selected_mode"] == "deep"
    assert metadata["response_mode_selection_reason"] == "current_info_required"
    assert _event_types_without_progress(events) == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_persists_exam_track_as_scoped_runtime_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    async def _noop_run(_execution):
        return None

    monkeypatch.setattr(runtime, "_run_turn", _noop_run)

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "不是一建，是一造案例题，按一级造价工程师口径回答",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    execution = runtime._executions[turn["id"]]
    config = execution.payload["config"]
    detail = await store.get_session(session["id"])

    assert config["exam_track"] == "first_cost"
    assert config["interaction_hints"]["exam_track"] == "first_cost"
    assert detail is not None
    assert detail["preferences"]["exam_track"] == "first_cost"
    assert detail["preferences"]["interaction_hints"]["exam_track"] == "first_cost"


@pytest.mark.asyncio
async def test_turn_runtime_clears_stored_exam_track_when_user_denies_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    session = await store.ensure_session(None)
    await store.update_session_preferences(
        session["id"],
        {
            "exam_track": "first_cost",
            "interaction_hints": {
                "profile": "tutorbot",
                "subject_domain": "construction_exam",
                "exam_track": "first_cost",
            },
        },
    )

    async def _noop_run(_execution):
        return None

    monkeypatch.setattr(runtime, "_run_turn", _noop_run)

    _, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "不是一造，这里先按普通建筑实务问题讲",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    execution = runtime._executions[turn["id"]]
    detail = await store.get_session(session["id"])

    assert "exam_track" not in execution.payload["config"]
    assert execution.payload["config"]["interaction_hints"]["profile"] == "tutorbot"
    assert "exam_track" not in execution.payload["config"]["interaction_hints"]
    assert detail is not None
    assert detail["preferences"].get("exam_track") == ""
    assert "exam_track" not in detail["preferences"]["interaction_hints"]


@pytest.mark.asyncio
async def test_turn_runtime_does_not_restore_stored_exam_track_for_comparison_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    session = await store.ensure_session(None)
    await store.update_session_preferences(
        session["id"],
        {
            "exam_track": "first_cost",
            "interaction_hints": {
                "profile": "tutorbot",
                "subject_domain": "construction_exam",
                "exam_track": "first_cost",
            },
        },
    )

    async def _noop_run(_execution):
        return None

    monkeypatch.setattr(runtime, "_run_turn", _noop_run)

    _, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "一建和一造有什么区别？我该怎么选？",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "subject_domain": "construction_exam",
                },
            },
        }
    )

    execution = runtime._executions[turn["id"]]
    detail = await store.get_session(session["id"])

    assert "exam_track" not in execution.payload["config"]
    assert "exam_track" not in execution.payload["config"]["interaction_hints"]
    assert detail is not None
    assert detail["preferences"]["exam_track"] == "first_cost"
    assert "exam_track" not in detail["preferences"]["interaction_hints"]


@pytest.mark.asyncio
async def test_turn_runtime_normalizes_legacy_mini_tutor_profile_to_tutorbot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["config_overrides"] = dict(context.config_overrides)
            captured["metadata"] = dict(context.metadata)
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="TutorBot ready",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "什么叫流水施工？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_profile": "mini_tutor",
                "interaction_hints": {
                    "profile": "mini_tutor",
                    "teaching_mode": "smart",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["interaction_hints"]["profile"] == "tutorbot"
    assert captured["config_overrides"]["interaction_profile"] == "tutorbot"
    assert captured["metadata"]["interaction_hints"]["profile"] == "tutorbot"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_treat_default_rag_binding_as_grounding_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这是一般讲解。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请讲解一下流水施工",
            "session_id": None,
            "capability": None,
            "tools": ["rag"],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "general_learning_query"


@pytest.mark.asyncio
async def test_turn_runtime_preserves_auto_capability_selection_when_unspecified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["active_capability"] = context.active_capability
            captured["user_message"] = context.user_message
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_question",
                stage="generation",
                content="### Question 1\n流水施工中，流水步距反映什么？",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_question")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "考我一道流水施工的题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert captured["active_capability"] is None
    assert captured["user_message"] == "考我一道流水施工的题"

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "deep_question"
    persisted_turn = await store.get_turn(turn["id"])
    assert persisted_turn is not None
    assert persisted_turn["capability"] == "deep_question"
    assert _event_types_without_progress(events) == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_marks_explicit_chat_mode_in_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode_explicit"] = context.metadata.get("chat_mode_explicit")
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="fast mode reply",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "解释一下流水施工",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"chat_mode": "fast"},
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert captured["chat_mode_explicit"] is True
    assert _event_types_without_progress(events) == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_uses_canonical_requested_response_mode_to_set_explicit_chat_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            captured["chat_mode_explicit"] = context.metadata.get("chat_mode_explicit")
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="fast mode reply",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "解释一下屋面防水等级",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "requested_response_mode": "fast",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert captured["chat_mode"] == "fast"
    assert captured["chat_mode_explicit"] is True
    assert detail["preferences"]["chat_mode"] == "fast"
    assert _event_types_without_progress(events) == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_prefers_requested_response_mode_hint_when_chat_mode_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            captured["chat_mode_explicit"] = context.metadata.get("chat_mode_explicit")
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="fast mode via requested_response_mode",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "简要说明流水节拍",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "interaction_hints": {
                    "profile": "tutorbot",
                    "entry_role": "tutorbot",
                    "requested_response_mode": "fast",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert captured["chat_mode"] == "fast"
    assert captured["chat_mode_explicit"] is True
    assert detail["preferences"]["chat_mode"] == "fast"
    assert _event_types_without_progress(events) == ["session", "content", "done"]


@pytest.mark.asyncio
async def test_turn_runtime_trace_requested_response_mode_records_selected_mode_for_smart_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="chat",
                metadata={
                    "response": "smart mode from chat_mode",
                    "metadata": {},
                    "selected_mode": "fast",
                    "execution_path": "tutorbot_kb_first_fast_policy",
                    "exact_fast_path_hit": False,
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "概括一下流水施工",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured_updates
    metadata = captured_updates[-1]["metadata"]
    assert metadata["chat_mode"] == "fast"
    assert metadata["requested_response_mode"] == "smart"
    assert metadata["effective_response_mode"] == "fast"
    assert metadata["selected_mode"] == "fast"


@pytest.mark.asyncio
async def test_turn_runtime_open_chat_active_object_does_not_force_deep_mode_for_smart_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            captured["active_object"] = context.metadata.get("active_object")
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={
                    "response": "简短回答",
                    "selected_mode": "fast",
                    "execution_path": "tutorbot_kb_first_fast_policy",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    session = await store.create_session(session_id="session_open_chat_mode", title="新对话")
    active_object = build_active_object_from_session(session)
    assert active_object is not None
    await store.set_active_object(session["id"], active_object)

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "什么是流水节拍，简单说一下",
            "session_id": session["id"],
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "requested_response_mode": "smart",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["chat_mode"] == "fast"
    assert captured["active_object"]["object_type"] == "open_chat_topic"
    metadata = captured_updates[-1]["metadata"]
    assert metadata["chat_mode"] == "fast"
    assert metadata["requested_response_mode"] == "smart"
    assert metadata["effective_response_mode"] == "fast"
    assert metadata["selected_mode"] == "fast"
    assert metadata["execution_path"] == "tutorbot_kb_first_fast_policy"


@pytest.mark.asyncio
async def test_turn_runtime_separates_requested_smart_from_selected_fast_in_trace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_updates: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["chat_mode"] = context.config_overrides.get("chat_mode")
            yield StreamEvent(
                type=StreamEventType.RESULT,
                source="tutorbot",
                metadata={
                    "response": "简短回答",
                    "selected_mode": "fast",
                    "execution_path": "tutorbot_kb_first_fast_policy",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                },
            )
            yield StreamEvent(type=StreamEventType.DONE, source="tutorbot")

    def _capture_update(_observation, **kwargs):
        captured_updates.append(kwargs)

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {},
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.update_observation",
        _capture_update,
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "什么是流水节拍，简单说一下",
            "session_id": None,
            "capability": "tutorbot",
            "tools": [],
            "knowledge_bases": ["construction-exam"],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "chat_mode": "smart",
                "interaction_hints": {
                    "profile": "tutorbot",
                    "requested_response_mode": "smart",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["chat_mode"] == "fast"
    metadata = captured_updates[-1]["metadata"]
    assert metadata["chat_mode"] == "fast"
    assert metadata["requested_response_mode"] == "smart"
    assert metadata["effective_response_mode"] == "fast"
    assert metadata["selected_mode"] == "fast"
    assert metadata["execution_path"] == "tutorbot_kb_first_fast_policy"
    assert metadata["exact_fast_path_hit"] is False


def test_bind_authenticated_user_promotes_legacy_response_mode_hints() -> None:
    payload = {
        "type": "start_turn",
        "config": {
            "requested_response_mode": "deep",
            "teaching_mode": "fast",
            "interaction_hints": {
                "profile": "tutorbot",
                "requested_response_mode": "smart",
            },
        },
    }

    bound = unified_ws_module._bind_authenticated_user(payload, current_user=None)
    config = bound["config"]
    hints = config["interaction_hints"]

    assert hints["profile"] == "tutorbot"
    assert hints["requested_response_mode"] == "smart"
    assert "teaching_mode" not in hints
    assert "requested_response_mode" not in config
    assert "teaching_mode" not in config


@pytest.mark.asyncio
@pytest.mark.parametrize("persist_user_message", [True, False])
async def test_turn_runtime_captures_points_for_mini_program_turns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    persist_user_message: bool,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", "true")

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这是一次会扣分的回复。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeMemberService:
        def record_chat_learning(self, user_id: str, *, query: str, assistant_content: str):
            captured["learning_user_id"] = user_id
            captured["learning_query"] = query
            captured["learning_content"] = assistant_content
            return {"today_done": 1}

    class FakeWalletService:
        is_configured = True

        def record_usage_points(
            self,
            *,
            user_id: str,
            amount_points: int,
            idempotency_key: str,
            reference_id: str,
            reason: str = "capture",
            reference_type: str = "ai_usage",
            metadata: dict[str, object] | None = None,
        ):
            captured["wallet_user_id"] = user_id
            captured["amount_points"] = amount_points
            captured["idempotency_key"] = idempotency_key
            captured["reference_id"] = reference_id
            captured["reason"] = reason
            captured["reference_type"] = reference_type
            captured["capture_metadata"] = dict(metadata or {})
            return {"captured": amount_points}

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.member_console.get_member_console_service",
        lambda: FakeMemberService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.wallet.get_wallet_service",
        lambda: FakeWalletService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {
            "total_cost_usd": 0.0351,
            "estimated_total_cost_usd": 0.0,
            "total_input_tokens": 1000,
            "total_output_tokens": 250,
            "total_tokens": 1250,
            "usage_accuracy": "measured",
            "usage_sources": {"provider": 1},
            "models": {"deepseek-v4-flash": 1},
        },
    )

    runtime_config = {
        "billing_context": {
            "source": "wx_miniprogram",
            "user_id": "student_demo",
            "wallet_user_id": "wallet_demo",
            "learning_user_id": "learner_demo",
        }
    }
    if not persist_user_message:
        runtime_config["_persist_user_message"] = False

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "考我一道题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": runtime_config,
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    assert captured == {
        "wallet_user_id": "wallet_demo",
        "amount_points": 36,
        "idempotency_key": f"mini_program_capture:{turn['id']}",
        "reference_id": turn["id"],
        "reason": "capture",
        "reference_type": "ai_usage",
        "capture_metadata": {
            "source": "wx_miniprogram",
            "turn_id": turn["id"],
            "session_id": session["id"],
            "billing_amount_source": "measured_cost",
            "billing_cost_source": "measured_cost",
            "billing_cost_point_scale": 1000,
            "billing_minimum_points": 20,
            "billing_measured_cost": 0.0351,
            "billing_estimated_cost": 0.0,
            "billing_billable_cost": 0.0351,
            "billing_cost_points": 36,
            "usage_accuracy": "measured",
            "usage_total_input_tokens": 1000,
            "usage_total_output_tokens": 250,
            "usage_total_tokens": 1250,
            "usage_estimated_input_tokens": 0,
            "usage_estimated_output_tokens": 0,
            "usage_estimated_total_tokens": 0,
            "usage_sources": {"provider": 1},
            "usage_models": {"deepseek-v4-flash": 1},
        },
        "learning_user_id": "learner_demo",
        "learning_query": "考我一道题",
        "learning_content": "这是一次会扣分的回复。",
    }
    stored_messages = await store.get_messages_for_context(session["id"])
    stored_roles = [message["role"] for message in stored_messages]
    assert stored_roles == (["user", "assistant"] if persist_user_message else ["assistant"])


@pytest.mark.asyncio
async def test_turn_runtime_marks_usage_scope_billable_after_wallet_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    marked_billable: dict[str, object] = {}
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", "true")

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这是一次会扣分的回复。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeWalletService:
        is_configured = True

        def record_usage_points(
            self,
            *,
            user_id: str,
            amount_points: int,
            idempotency_key: str,
            reference_id: str,
            reason: str = "capture",
            reference_type: str = "ai_usage",
            metadata: dict[str, object] | None = None,
        ):
            return {"captured": amount_points}

    def fake_mark_usage_scope_billable(
        *,
        turn_id: str,
        billing_capture: dict[str, object],
    ) -> int:
        marked_billable["turn_id"] = turn_id
        marked_billable["billing_capture"] = dict(billing_capture)
        return 1

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.wallet.get_wallet_service",
        lambda: FakeWalletService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.get_current_usage_summary",
        lambda: {
            "total_cost_usd": 0.0,
            "estimated_total_cost_usd": 0.0,
            "total_tokens": 250,
            "usage_accuracy": "measured",
            "usage_sources": {"provider": 1},
            "models": {"deepseek-v4-flash": 1},
        },
    )
    monkeypatch.setattr(
        "deeptutor.services.session.turn_runtime.observability.mark_usage_scope_billable",
        fake_mark_usage_scope_billable,
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "考我一道题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                    "wallet_user_id": "wallet_demo",
                }
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert session["id"]
    assert marked_billable["turn_id"] == turn["id"]
    billing_capture = marked_billable["billing_capture"]
    assert billing_capture["status"] == "captured"
    assert billing_capture["idempotency_key"] == f"mini_program_capture:{turn['id']}"


@pytest.mark.asyncio
async def test_turn_runtime_skips_mini_program_capture_without_wallet_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这是一次不会扣分的回复。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeMemberService:
        def record_chat_learning(self, user_id: str, *, query: str, assistant_content: str):
            captured["learning_user_id"] = user_id
            captured["learning_query"] = query
            captured["learning_content"] = assistant_content
            return {"today_done": 1}

    class FakeWalletService:
        is_configured = True

        def record_usage_points(self, **_kwargs):
            captured["wallet_capture_called"] = True
            return {"captured": 20}

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.member_console.get_member_console_service",
        lambda: FakeMemberService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.wallet.get_wallet_service",
        lambda: FakeWalletService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续解释这道题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                    "learning_user_id": "learner_demo",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    assert captured == {
        "learning_user_id": "learner_demo",
        "learning_query": "继续解释这道题",
        "learning_content": "这是一次不会扣分的回复。",
    }


def test_turn_runtime_internal_qa_billing_bypass_skips_wallet_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS", "true")
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    runtime = TurnRuntimeManager(SQLiteSessionStore(tmp_path / "chat_history.db"))

    class FailingWalletService:
        def record_usage_points(self, **_kwargs):
            raise AssertionError("wallet capture must not run in internal QA billing bypass")

    class FakeMemberService:
        def get_profile(self, _user_id: str):
            return {
                "user_id": "auth_2d9eac155d264e93941b9ec6",
                "username": "qa_student_demo",
            }

    monkeypatch.setattr(
        "deeptutor.services.wallet.get_wallet_service",
        lambda: FailingWalletService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.member_console.get_member_console_service",
        lambda: FakeMemberService(),
    )

    result = runtime._capture_mobile_points(
        {
            "source": "wx_miniprogram",
            "user_id": canonical_uid,
            "wallet_user_id": canonical_uid,
            "learning_user_id": canonical_uid,
        },
        "这是一次内部 QA 回复。",
        session_id="session-1",
        turn_id="turn-1",
        usage_summary={"total_tokens": 123, "total_calls": 1},
    )

    assert result == {
        "status": "bypassed",
        "reason": "internal_qa_billing_bypass",
        "wallet_user_id": canonical_uid,
        "idempotency_key": "mini_program_capture:turn-1",
    }


def test_turn_runtime_internal_qa_billing_bypass_keeps_non_qa_wallet_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS", "true")
    monkeypatch.setenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", "true")
    runtime = TurnRuntimeManager(SQLiteSessionStore(tmp_path / "chat_history.db"))
    calls: list[dict[str, object]] = []

    class RecordingWalletService:
        def record_usage_points(self, **kwargs):
            calls.append(dict(kwargs))
            return SimpleNamespace(
                captured_micros=20_000_000,
                requested_micros=20_000_000,
                balance_after_micros=80_000_000,
            )

    monkeypatch.setattr(
        "deeptutor.services.wallet.get_wallet_service",
        lambda: RecordingWalletService(),
    )

    result = runtime._capture_mobile_points(
        {
            "source": "wx_miniprogram",
            "user_id": "student_demo",
            "wallet_user_id": "wallet_demo",
            "learning_user_id": "student_demo",
        },
        "这是一次普通用户回复。",
        session_id="session-1",
        turn_id="turn-1",
        usage_summary={"total_tokens": 123, "total_calls": 1},
    )

    assert result and result["status"] == "captured"
    assert calls and calls[0]["user_id"] == "wallet_demo"


def test_turn_runtime_meters_mini_program_usage_without_charging_when_enforcement_off(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED", raising=False)
    runtime = TurnRuntimeManager(SQLiteSessionStore(tmp_path / "chat_history.db"))
    meter_calls: list[dict[str, object]] = []

    class FailingWalletService:
        def record_usage_points(self, **_kwargs):
            raise AssertionError("wallet capture must not run when billing enforcement is disabled")

    class RecordingUsageMeter:
        def record_usage_event(self, **kwargs):
            meter_calls.append(dict(kwargs))
            return True

    monkeypatch.setattr(
        "deeptutor.services.wallet.get_wallet_service",
        lambda: FailingWalletService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.member_usage_meter.get_member_usage_meter",
        lambda: RecordingUsageMeter(),
    )

    result = runtime._capture_mobile_points(
        {
            "source": "wx_miniprogram",
            "user_id": "student_demo",
            "wallet_user_id": "wallet_demo",
            "learning_user_id": "learner_demo",
        },
        "这是一次内测计量但不扣费的回复。",
        session_id="session-1",
        turn_id="turn-1",
        usage_summary={
            "total_cost_usd": 0.0351,
            "estimated_total_cost_usd": 0.0,
            "total_tokens": 1250,
            "usage_accuracy": "measured",
        },
    )

    assert result == {
        "status": "metered_not_charged",
        "reason": "billing_enforcement_disabled",
        "wallet_user_id": "wallet_demo",
        "idempotency_key": "mini_program_capture:turn-1",
        "amount_points": 36,
        "billing_amount_source": "measured_cost",
        "billing_cost_source": "measured_cost",
        "captured_micros": 0,
        "requested_micros": 36_000_000,
        "balance_after_micros": 0,
    }
    assert meter_calls == [
        {
            "wallet_user_id": "wallet_demo",
            "learning_user_id": "learner_demo",
            "source": "wx_miniprogram",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "amount_points": 36,
            "dedupe_key": "mini_program_meter:turn-1",
            "status": "metered_not_charged",
            "metadata": {
                "source": "wx_miniprogram",
                "turn_id": "turn-1",
                "session_id": "session-1",
                "billing_amount_source": "measured_cost",
                "billing_cost_source": "measured_cost",
                "billing_cost_point_scale": 1000,
                "billing_minimum_points": 20,
                "billing_measured_cost": 0.0351,
                "billing_estimated_cost": 0.0,
                "billing_billable_cost": 0.0351,
                "billing_cost_points": 36,
                "usage_accuracy": "measured",
                "usage_total_input_tokens": 0,
                "usage_total_output_tokens": 0,
                "usage_total_tokens": 1250,
                "usage_estimated_input_tokens": 0,
                "usage_estimated_output_tokens": 0,
                "usage_estimated_total_tokens": 0,
            },
        }
    ]


@pytest.mark.asyncio
async def test_turn_runtime_rejects_deep_research_without_explicit_config(
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    with pytest.raises(RuntimeError, match="Invalid deep research config"):
        await runtime.start_turn(
            {
                "type": "start_turn",
                "content": "research transformers",
                "session_id": None,
                "capability": "deep_research",
                "tools": ["rag"],
                "knowledge_bases": ["research-kb"],
                "attachments": [],
                "language": "en",
                "config": {},
            }
        )


@pytest.mark.asyncio
async def test_turn_runtime_persists_deep_research_session_preference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="deep_research",
                stage="reporting",
                content="Research report ready.",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="deep_research")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "research transformers",
            "session_id": None,
            "capability": "deep_research",
            "tools": ["rag", "web_search"],
            "knowledge_bases": ["research-kb"],
            "attachments": [],
            "language": "en",
            "config": {
                "mode": "report",
                "depth": "standard",
                "sources": ["kb", "web"],
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["capability"] == "deep_research"
    assert detail["preferences"]["tools"] == ["rag", "web_search"]


@pytest.mark.asyncio
async def test_turn_runtime_injects_memory_and_refreshes_after_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="Recent chat summary",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["conversation_history"] = context.conversation_history
            captured["memory_context"] = context.memory_context
            captured["conversation_context_text"] = context.metadata.get("conversation_context_text")
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="Stored reply",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    refresh_calls: list[dict[str, object]] = []

    async def fake_refresh_from_turn(**kwargs):
        refresh_calls.append(kwargs)
        return None

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "## Memory\n## Preferences\n- Prefer concise answers.",
            refresh_from_turn=fake_refresh_from_turn,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "hello, i'm frank",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "en",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    await asyncio.sleep(0)

    assert captured["memory_context"] == "## Memory\n## Preferences\n- Prefer concise answers."
    assert captured["conversation_history"] == []
    assert captured["conversation_context_text"] == "Recent chat summary"
    assert refresh_calls[0]["assistant_message"] == "Stored reply"


@pytest.mark.asyncio
async def test_turn_runtime_does_not_block_done_on_background_memory_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="Recent chat summary",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="后台刷新前先返回",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    async def fake_refresh_from_turn(**kwargs):
        refresh_started.set()
        await release_refresh.wait()
        return None

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "## Memory\n- fast",
            refresh_from_turn=fake_refresh_from_turn,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "建筑构造是什么？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    async def _collect() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
            events.append(event)
        return events

    events = await asyncio.wait_for(_collect(), timeout=0.5)
    assert _event_types_without_progress(events) == ["session", "content", "done"]

    await asyncio.wait_for(refresh_started.wait(), timeout=0.5)
    release_refresh.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_skips_heavy_context_for_low_signal_query(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"notebook_called": False}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["notebook_context"] = context.notebook_context
            captured["history_context"] = context.history_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="当前还剩 20 点。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeNotebookManager:
        def get_records_by_references(self, _refs):
            captured["notebook_called"] = True
            return [{"id": "note_1", "title": "不应加载", "summary": "不应出现"}]

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("deeptutor.services.notebook.notebook_manager", FakeNotebookManager())
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "还有多少点数",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "notebook_references": [{"notebook_id": "nb_1", "id": "rec_1"}],
            "history_references": ["session_prev"],
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["user_message"] == "还有多少点数"
    assert captured["notebook_context"] == ""
    assert captured["history_context"] == ""
    assert captured["metadata"]["context_route"] == "low_signal_social"
    assert captured["metadata"]["loaded_sources"] == []
    assert captured["notebook_called"] is False


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_loads_history_evidence_for_cross_session_recall(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    history_session = await store.create_session("历史会话")
    await store.update_summary(
        history_session["id"],
        "之前建议先复习流水施工，再做网络计划，最后回到案例题。",
        0,
    )
    await store.add_message(
        session_id=history_session["id"],
        role="assistant",
        content="先复习流水施工，再做网络计划。",
        capability="chat",
    )

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["history_context"] = context.history_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="上次我建议你先复习流水施工。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你上次建议我怎么复习？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "history_references": [history_session["id"]],
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "cross_session_recall"
    assert captured["metadata"]["escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["target_escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["escalation_attempts"] == [1, 2, 3]
    assert captured["metadata"]["context_pack_trace"]["escalation_stop_reason"] == "target_level_reached"
    assert "history" in captured["metadata"]["loaded_sources"]
    assert "blocks" in captured["metadata"]["context_pack_trace"]
    assert captured["metadata"]["context_pack_trace"]["blocks"]["evidence"]["selected_candidates"]
    assert "之前建议先复习流水施工" in captured["history_context"]
    assert "参考证据" in captured["user_message"]
    assert "当前用户问题" in captured["user_message"]


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_implicitly_recalls_cross_session_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    history_session = await store.create_session("历史会话", owner_key=build_user_owner_key("student_demo"))
    await store.update_summary(
        history_session["id"],
        "之前建议先复习流水施工，再做网络计划，最后回到案例题。",
        0,
    )
    await store.add_message(
        session_id=history_session["id"],
        role="assistant",
        content="先复习流水施工，再做网络计划。",
        capability="chat",
    )

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["history_context"] = context.history_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="上次我建议你先复习流水施工。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你上次建议我怎么复习？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                }
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "cross_session_recall"
    assert captured["metadata"]["history_search_applied"] is True
    assert captured["metadata"]["escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["target_escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["escalation_attempts"] == [1, 2, 3]
    assert captured["metadata"]["context_pack_trace"]["escalation_stop_reason"] == "target_level_reached"
    assert "history" in captured["metadata"]["loaded_sources"]
    assert "Title: 历史会话" in captured["history_context"]
    assert "之前建议先复习流水施工" in captured["history_context"]


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_respects_history_source_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    history_session = await store.create_session("历史会话", owner_key=build_user_owner_key("student_demo"))
    await store.update_summary(history_session["id"], "之前建议先复习流水施工。", 0)
    await store.add_message(
        session_id=history_session["id"],
        role="assistant",
        content="先复习流水施工。",
        capability="chat",
    )

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["history_context"] = context.history_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这轮不应加载历史证据。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你上次建议我怎么复习？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                },
                "context_sources": {
                    "history": False,
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "cross_session_recall"
    assert captured["metadata"]["history_search_applied"] is False
    assert captured["metadata"]["context_pack_trace"]["target_escalation_level"] == 3
    assert captured["metadata"]["context_pack_trace"]["source_flags"]["history"] is False
    assert captured["metadata"]["context_pack_trace"]["escalation_stop_reason"] == "source_flag_disabled:history"
    assert "history" not in captured["metadata"]["loaded_sources"]
    assert captured["history_context"] == ""


@pytest.mark.asyncio
async def test_turn_runtime_can_fallback_to_legacy_context_builder_by_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="legacy-summary",
                context_text="legacy-context",
                token_count=16,
                budget=128,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = context.metadata
            captured["user_message"] = context.user_message
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="走旧链路。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请讲解一下这个概念",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "context_orchestration_enabled": False,
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["fallback_path"] == "legacy"
    assert captured["metadata"]["escalation_level"] == 0
    assert captured["metadata"]["context_pack_trace"]["fallback_path"] == "legacy"
    assert captured["metadata"]["context_pack_trace"]["fallback_stage"] == "legacy_flag"
    assert captured["metadata"]["context_pack_trace"]["fallback_reason"] == "context_orchestration_disabled"
    assert captured["user_message"] == "请讲解一下这个概念"


@pytest.mark.asyncio
async def test_turn_runtime_records_stage_specific_orchestration_fallback_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class BrokenContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            raise RuntimeError("builder boom")

    class FakeOrchestrator:
        async def handle(self, context):
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="已退回旧链路。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", BrokenContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请讲解一下这个概念",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["fallback_path"] == "legacy_context_builder:session_history"
    assert captured["metadata"]["escalation_level"] == 0
    assert captured["metadata"]["context_pack_trace"]["fallback_path"] == "legacy_context_builder:session_history"
    assert captured["metadata"]["context_pack_trace"]["fallback_stage"] == "session_history"
    assert captured["metadata"]["context_pack_trace"]["fallback_reason"] == "RuntimeError"


@pytest.mark.asyncio
async def test_turn_runtime_writes_home_prompt_conversation_learning_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeObservability:
        def __init__(self) -> None:
            self.started: list[dict[str, object]] = []

        def usage_scope(self, **_kwargs):
            class _UsageScope:
                def __enter__(self):
                    return SimpleNamespace()

                def __exit__(self, *_args):
                    return False

            return _UsageScope()

        def start_observation(self, **kwargs):
            outer = self

            class _Observation:
                def __enter__(self):
                    outer.started.append(
                        {
                            "name": str(kwargs.get("name") or ""),
                            "metadata": dict(kwargs.get("metadata") or {}),
                        }
                    )
                    return SimpleNamespace()

                def __exit__(self, *_args):
                    return False

            return _Observation()

        def update_observation(self, _observation, **_kwargs):
            return None

        def get_current_usage_summary(self):
            return {}

        def summary_metadata(self, _summary):
            return {}

        def usage_details_from_summary(self, _summary):
            return None

        def cost_details_from_summary(self, _summary):
            return None

    fake_observability = FakeObservability()

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="主体结构多选题要逐项判断所有必要条件。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context(self, **_kwargs):
            return ""

        async def refresh_from_turn(self, **kwargs):
            captured["refresh"] = kwargs

        def append_memory_event(self, user_id: str, **kwargs):
            captured["append_memory_event"] = {"user_id": user_id, **kwargs}
            return SimpleNamespace(event_id="evt_conversation")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("deeptutor.services.session.turn_runtime.observability", fake_observability)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我手机号 13800001234，主体结构多选题为什么容易漏选？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                    "learning_user_id": "student_demo",
                },
                "learning_prompt_intent": {
                    "source": "home_dashboard",
                    "concept_label": "主体结构",
                    "error_label": "多选漏选",
                    "subject_id": "construction_exam_1",
                    "training_intent_id": "lti_123",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    for _ in range(20):
        if "append_memory_event" in captured:
            break
        await asyncio.sleep(0.01)

    written = captured["append_memory_event"]
    payload = written["payload_json"]
    assert written["user_id"] == "student_demo"
    assert written["source_feature"] == "conversation_synthesis"
    assert written["memory_kind"] == "learning_evidence"
    assert payload["event_type"] == "learning_evidence"
    assert payload["evidence_source"] == "conversation_synthesis"
    assert payload["learning_signal_type"] == "home_prompt_clicked"
    assert payload["subject_id"] == "construction_exam_1"
    assert payload["training_intent_id"] == "lti_123"
    assert "13800001234" not in payload["user_question"]
    turn_trace = next(item for item in fake_observability.started if item["name"] == "turn.chat")
    assert turn_trace["metadata"]["gbrain_training_intent_id"] == "lti_123"
    assert turn_trace["metadata"]["gbrain_prescription_authority"] == "training_intent"
    assert turn_trace["metadata"]["gbrain_prompt_source"] == "home_dashboard"


@pytest.mark.asyncio
async def test_turn_runtime_writes_conversation_learning_evidence_without_prompt_intent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="主体结构多选题漏选，通常是因为只看到一个确定项就停止判断，应该逐项核对所有必要条件。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context(self, **_kwargs):
            return ""

        async def refresh_from_turn(self, **kwargs):
            captured["refresh"] = kwargs

        def append_memory_event(self, user_id: str, **kwargs):
            captured["append_memory_event"] = {"user_id": user_id, **kwargs}
            return SimpleNamespace(event_id="evt_conversation")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "主体结构多选题为什么容易漏选？怎么区分该不该选？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                    "learning_user_id": "student_demo",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    for _ in range(20):
        if "append_memory_event" in captured:
            break
        await asyncio.sleep(0.01)

    written = captured["append_memory_event"]
    payload = written["payload_json"]
    assert written["user_id"] == "student_demo"
    assert written["source_feature"] == "conversation_synthesis"
    assert written["memory_kind"] == "learning_evidence"
    assert payload["event_type"] == "learning_evidence"
    assert payload["evidence_source"] == "conversation_synthesis"
    assert payload["learning_signal_type"] == "mistake_explain"
    assert payload["concept"]["label"] == "主体结构"
    assert payload["error"]["label"] == "多选漏选"
    assert payload["quality"]["truth_eligible"] is False


@pytest.mark.asyncio
async def test_turn_runtime_does_not_write_greeting_conversation_learning_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, _context):
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="你好，有什么可以帮你？",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context(self, **_kwargs):
            return ""

        async def refresh_from_turn(self, **kwargs):
            captured["refresh"] = kwargs

        def append_memory_event(self, user_id: str, **kwargs):
            captured["append_memory_event"] = {"user_id": user_id, **kwargs}
            return SimpleNamespace(event_id="evt_conversation")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "你好",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                    "learning_user_id": "student_demo",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    await asyncio.sleep(0.05)

    assert "append_memory_event" not in captured


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_prioritizes_active_plan_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeLearningPlanService:
        def read_guided_session_view(self, plan_id: str):
            if plan_id != "plan_demo":
                return None
            return {
                "session_id": "plan_demo",
                "user_id": "",
                "status": "in_progress",
                "current_index": 1,
                "summary": "当前正在学流水施工与网络计划。",
                "notebook_id": "nb_demo",
                "notebook_name": "施工组织",
                "progress": 50,
                "ready_count": 2,
                "page_count": 3,
                "pages": [
                    {
                        "page_index": 0,
                        "knowledge_title": "流水施工基础",
                        "knowledge_summary": "先理解流水节拍与流水步距。",
                        "user_difficulty": "medium",
                    },
                    {
                        "page_index": 1,
                        "knowledge_title": "网络计划关键线路",
                        "knowledge_summary": "继续聚焦关键线路、总时差和自由时差。",
                        "user_difficulty": "hard",
                    },
                ],
            }

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="继续当前学习页面。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.learning_plan.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.context_sources.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续刚才这个学习页面",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"active_plan_id": "plan_demo"},
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    assert captured["metadata"]["context_route"] == "guided_plan_continuation"
    assert captured["metadata"]["active_object"]["object_type"] == "guide_page"
    assert captured["metadata"]["active_object"]["state_snapshot"]["plan_id"] == "plan_demo"
    assert "question_followup_context" not in captured["metadata"]
    assert "question_followup_action" not in captured["metadata"]
    assert "active_plan" in captured["metadata"]["loaded_sources"]
    assert "网络计划关键线路" in captured["user_message"]
    assert "当前用户问题" in captured["user_message"]
    build_stage_timings = captured["metadata"]["context_pack_trace"]["build_stage_timings_ms"]
    for stage in (
        "route_resolver",
        "context_budget",
        "session_history",
        "learner_state",
        "source_loader_notebook_plan",
        "candidate_build",
        "context_pack",
        "pack_render",
    ):
        assert build_stage_timings[stage] >= 0

    stored_active_object = await store.get_active_object(session["id"])
    assert stored_active_object is not None
    assert stored_active_object["object_type"] == "guide_page"


@pytest.mark.asyncio
async def test_turn_runtime_recovers_guided_plan_active_object_without_repassing_plan_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeLearningPlanService:
        def read_guided_session_view(self, plan_id: str):
            if plan_id != "plan_demo":
                return None
            return {
                "session_id": "plan_demo",
                "user_id": "",
                "status": "in_progress",
                "current_index": 1,
                "summary": "当前正在学流水施工与网络计划。",
                "notebook_id": "nb_demo",
                "notebook_name": "施工组织",
                "progress": 50,
                "ready_count": 2,
                "page_count": 3,
                "pages": [
                    {
                        "page_index": 1,
                        "knowledge_title": "网络计划关键线路",
                        "knowledge_summary": "继续聚焦关键线路、总时差和自由时差。",
                        "user_difficulty": "hard",
                    },
                ],
            }

    class FakeOrchestrator:
        async def handle(self, context):
            captured.append(
                {
                    "user_message": context.user_message,
                    "metadata": context.metadata,
                }
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="继续当前学习页面。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.learning_plan.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.context_sources.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续刚才这个学习页面",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {"active_plan_id": "plan_demo"},
        }
    )
    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass

    second_turn_payload = {
        "type": "start_turn",
        "content": "继续刚才这个学习页面",
        "session_id": session["id"],
        "capability": None,
        "tools": [],
        "knowledge_bases": [],
        "attachments": [],
        "language": "zh",
        "config": {},
    }
    _session, second_turn = await runtime.start_turn(second_turn_payload)
    async for _event in runtime.subscribe_turn(second_turn["id"], after_seq=0):
        pass

    assert len(captured) == 2
    second_metadata = captured[1]["metadata"]
    assert second_metadata["active_object"]["object_type"] == "guide_page"
    assert second_metadata["active_object"]["state_snapshot"]["plan_id"] == "plan_demo"
    assert second_metadata["context_route"] == "guided_plan_continuation"
    assert "active_plan" in second_metadata["loaded_sources"]


@pytest.mark.asyncio
async def test_turn_runtime_recovers_latest_user_plan_for_plan_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeLearningPlanService:
        def list_plans(self):
            return [
                {
                    "session_id": "other_user_plan",
                    "user_id": "other_user",
                    "status": "in_progress",
                    "updated_at": 2000.0,
                },
                {
                    "session_id": "plan_user_latest",
                    "user_id": "student_demo",
                    "status": "in_progress",
                    "updated_at": 1000.0,
                },
            ]

        def read_guided_session_view(self, plan_id: str):
            if plan_id != "plan_user_latest":
                return None
            return {
                "session_id": "plan_user_latest",
                "user_id": "student_demo",
                "status": "in_progress",
                "current_index": 0,
                "summary": "继续推进建筑构造专项训练。",
                "notebook_id": "nb_demo",
                "notebook_name": "建筑构造",
                "progress": 30,
                "ready_count": 1,
                "page_count": 3,
                "pages": [
                    {
                        "page_index": 0,
                        "knowledge_title": "建筑构造专项训练",
                        "knowledge_summary": "今天继续巩固建筑构造核心考点。",
                        "user_difficulty": "medium",
                    },
                ],
            }

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="这是你的学习计划。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.learning_plan.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.session.context_sources.get_learning_plan_service",
        lambda: FakeLearningPlanService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续我的学习计划",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "billing_context": {
                    "source": "wx_miniprogram",
                    "user_id": "student_demo",
                }
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    metadata = captured["metadata"]
    assert metadata["context_route"] == "guided_plan_continuation"
    assert metadata["active_object"]["state_snapshot"]["plan_id"] == "plan_user_latest"
    assert "active_plan" in metadata["loaded_sources"]
    assert "建筑构造专项训练" in captured["user_message"]
    assert "other_user_plan" not in str(captured["user_message"])


@pytest.mark.asyncio
async def test_turn_runtime_uses_user_scoped_learner_state_when_user_id_is_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"global_memory_called": False, "global_refresh_called": False}
    refresh_calls: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="Recent chat summary",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["memory_context"] = context.memory_context
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="User scoped reply",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context(self, *, user_id: str, language: str = "en", max_chars: int = 5000):
            captured["learner_user_id"] = user_id
            captured["learner_language"] = language
            return "## 学员级长期状态\n### Student Profile\n- user: student_demo"

        async def refresh_from_turn(self, **kwargs):
            refresh_calls.append(kwargs)
            return None

    class FakeOverlayService:
        def read_overlay(self, bot_id: str, user_id: str):
            captured["overlay_read"] = {"bot_id": bot_id, "user_id": user_id}
            return {
                "effective_overlay": {},
                "promotion_candidates": [],
                "heartbeat_override_candidate": {},
            }

        def patch_overlay(self, bot_id: str, user_id: str, patch: dict, *, source_feature: str, source_id: str):
            captured["overlay_patch"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "patch": patch,
                "source_feature": source_feature,
                "source_id": source_id,
            }
            return {"effective_overlay": {}}

        def apply_promotions(self, bot_id: str, user_id: str, *, learner_state_service, min_confidence: float = 0.7, max_candidates: int = 10):
            captured["overlay_promotions"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "min_confidence": min_confidence,
                "max_candidates": max_candidates,
                "learner_state_service_type": learner_state_service.__class__.__name__,
            }
            return {"applied": [], "dropped": [], "acked_ids": [], "dropped_ids": []}

    async def _unexpected_global_refresh(**_kwargs):
        captured["global_refresh_called"] = True
        return None

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: captured.__setitem__("global_memory_called", True) or "## Global Memory",
            refresh_from_turn=_unexpected_global_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: FakeOverlayService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续我的专项训练",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                }
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    assert captured["memory_context"] == "## 学员级长期状态\n### Student Profile\n- user: student_demo"
    assert captured["learner_user_id"] == "student_demo"
    assert captured["global_memory_called"] is False
    assert captured["global_refresh_called"] is False
    assert captured["overlay_read"] == {
        "bot_id": "construction-exam-coach",
        "user_id": "student_demo",
    }
    assert captured["overlay_patch"]["bot_id"] == "construction-exam-coach"
    assert captured["overlay_patch"]["source_feature"] == "turn"
    assert captured["overlay_promotions"]["bot_id"] == "construction-exam-coach"
    assert refresh_calls[0]["user_id"] == "student_demo"
    assert refresh_calls[0]["assistant_message"] == "User scoped reply"
    assert refresh_calls[0]["source_bot_id"] == "construction-exam-coach"


@pytest.mark.asyncio
async def test_turn_runtime_uses_guide_completion_summary_from_real_learner_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.learner_state.service import LearnerStateService

    class PathServiceStub:
        @property
        def project_root(self):
            return tmp_path

        def get_user_root(self):
            return tmp_path

        def get_learner_state_root(self):
            return tmp_path / "learner_state"

        def get_learner_state_outbox_db(self):
            return tmp_path / "runtime" / "outbox.db"

        def get_guide_dir(self):
            path = tmp_path / "workspace" / "guide"
            path.mkdir(parents=True, exist_ok=True)
            return path

    class MemberServiceStub:
        def get_profile(self, user_id: str):
            return {
                "user_id": user_id,
                "display_name": "陈同学",
                "difficulty_preference": "medium",
                "explanation_style": "detailed",
                "focus_topic": "地基基础",
                "daily_target": 30,
            }

        def get_today_progress(self, _user_id: str):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_chapter_progress(self, _user_id: str):
            return []

    class DisabledCoreStore:
        is_configured = False

    async def _no_summary_rewrite(**_kwargs):
        yield "NO_CHANGE"

    learner_state_service = LearnerStateService(
        path_service=PathServiceStub(),
        member_service=MemberServiceStub(),
        core_store=DisabledCoreStore(),
    )
    await learner_state_service.record_guide_completion(
        user_id="student_demo",
        guide_id="guide_foundation_1",
        notebook_name="地基基础",
        summary="已完成地基承载力与沉降控制的引导学习，下一步应做案例题巩固。",
        knowledge_points=[
            {
                "knowledge_title": "地基承载力验算",
                "knowledge_summary": "先明确承载力修正与基础埋深。",
                "user_difficulty": "hard",
            }
        ],
        source_bot_id="construction-exam-coach",
    )

    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {"global_memory_called": False}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["memory_context"] = context.memory_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="下一步做案例题巩固。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeOverlayService:
        def read_overlay(self, _bot_id: str, _user_id: str):
            return {"effective_overlay": {}, "promotion_candidates": [], "heartbeat_override_candidate": {}}

        def patch_overlay(self, *_args, **_kwargs):
            return {"effective_overlay": {}}

        def apply_promotions(self, *_args, **_kwargs):
            return {"applied": [], "dropped": [], "acked_ids": [], "dropped_ids": []}

    monkeypatch.setattr("deeptutor.services.learner_state.service.llm_stream", _no_summary_rewrite)
    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: captured.__setitem__("global_memory_called", True) or "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: learner_state_service,
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: FakeOverlayService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我下一步应该怎么复习？",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass

    memory_context = str(captured["memory_context"])
    assert captured["global_memory_called"] is False
    assert "最近完成的引导学习" in memory_context
    assert "已完成地基承载力与沉降控制的引导学习" in memory_context
    assert "地基承载力验算" in memory_context


@pytest.mark.asyncio
async def test_turn_runtime_context_orchestration_loads_bot_overlay_into_context_pack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["user_message"] = context.user_message
            captured["memory_context"] = context.memory_context
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="继续专项训练。",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    class FakeLearnerStateService:
        def build_context_candidates(self, *, user_id: str, query: str, route: str, language: str = "en"):
            captured["learner_context_request"] = {
                "user_id": user_id,
                "query": query,
                "route": route,
                "language": language,
            }
            return {
                "learner_candidates": [],
                "memory_candidates": [],
                "compiled_learning_truth": {
                    "subject": "construction_exam_learning_truth",
                    "weak_points": [{"concept_id": "1A432000", "error_code": "E02"}],
                },
                # Grading-to-Brain loop: PCP surfaced by build_context_candidates must reach the live turn.
                "personalization_context": {
                    "schema_version": 1,
                    "source": "PersonalizationContextPack",
                    "top_claims": [{"claim_id": "claim-1", "concept_id": "1A432000",
                                    "claim_status": "confirmed"}],
                    "next_best_action_candidates": [],
                },
            }

        async def refresh_from_turn(self, **_kwargs):
            return None

    class FakeOverlayService:
        def read_overlay(self, bot_id: str, user_id: str):
            captured["overlay_request"] = {"bot_id": bot_id, "user_id": user_id}
            return {
                "effective_overlay": {
                    "local_focus": {
                        "current_goal": "聚焦建筑案例题第 2 问",
                        "teaching_intent": "保持追问，不要切题",
                    },
                    "working_memory_projection": "刚才停在案例题第 2 问，先完成关键线路判断。",
                }
            }

        def patch_overlay(self, bot_id: str, user_id: str, patch: dict, *, source_feature: str, source_id: str):
            captured["overlay_patch"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "patch": patch,
                "source_feature": source_feature,
                "source_id": source_id,
            }
            return {"effective_overlay": {}}

        def apply_promotions(self, bot_id: str, user_id: str, *, learner_state_service, min_confidence: float = 0.7, max_candidates: int = 10):
            captured["overlay_promotions"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "min_confidence": min_confidence,
                "max_candidates": max_candidates,
            }
            return {"applied": [], "dropped": [], "acked_ids": [], "dropped_ids": []}

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: FakeOverlayService(),
    )

    _session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "继续刚才的专项训练",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_overlay",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(turn["id"], after_seq=0):
        pass
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))

    metadata = dict(captured["metadata"])
    assert metadata["compiled_learning_truth"]["subject"] == "construction_exam_learning_truth"
    # Grading-to-Brain loop closed: the PersonalizationContextPack reaches the live turn metadata
    # (consumers loop.py / RAGAdapterTool / deep_question already read metadata["personalization_context"]).
    assert metadata["personalization_context"]["source"] == "PersonalizationContextPack"
    assert metadata["personalization_context"]["top_claims"][0]["concept_id"] == "1A432000"
    trace = dict(metadata["context_pack_trace"])
    learner_selected = list(trace["blocks"]["learner"]["selected_candidates"])
    evidence_selected = list(trace["blocks"]["evidence"]["selected_candidates"])

    assert captured["overlay_request"] == {
        "bot_id": "construction-exam-coach",
        "user_id": "student_overlay",
    }
    assert captured["learner_context_request"] == {
        "user_id": "student_overlay",
        "query": "继续刚才的专项训练",
        "route": metadata["context_route"],
        "language": "zh",
    }
    assert "overlay" in metadata["loaded_sources"]
    assert "overlay" in metadata["candidate_sources"]
    assert int(trace["overlay_candidate_count"]) >= 2
    assert any(
        str(item.get("metadata", {}).get("source_tag", "")) == "overlay_local_focus"
        for item in learner_selected
    )
    assert any(
        str(item.get("metadata", {}).get("source_tag", "")) == "overlay_working_memory"
        for item in evidence_selected
    )
    assert "Bot 局部 Focus" in str(captured["memory_context"])
    assert "刚才停在案例题第 2 问" in str(captured["user_message"])
    assert "当前用户问题" in str(captured["user_message"])
    assert captured["overlay_patch"]["bot_id"] == "construction-exam-coach"
    assert captured["overlay_patch"]["source_feature"] == "turn"
    assert captured["overlay_promotions"]["bot_id"] == "construction-exam-coach"


@pytest.mark.asyncio
async def test_turn_runtime_end_to_end_applies_overlay_promotion_and_reads_next_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from deeptutor.services.learner_state.overlay_service import BotLearnerOverlayService
    from deeptutor.services.learner_state.service import LearnerStateService

    class PathServiceStub:
        @property
        def project_root(self):
            return tmp_path

        def get_user_root(self):
            return tmp_path

        def get_learner_state_root(self):
            path = tmp_path / "learner_state"
            path.mkdir(parents=True, exist_ok=True)
            return path

        def get_learner_state_outbox_db(self):
            return tmp_path / "runtime" / "outbox.db"

        def get_guide_dir(self):
            path = tmp_path / "workspace" / "guide"
            path.mkdir(parents=True, exist_ok=True)
            return path

    class MemberServiceStub:
        def get_profile(self, user_id: str):
            return {
                "user_id": user_id,
                "display_name": "陈同学",
                "difficulty_preference": "medium",
                "explanation_style": "detailed",
                "focus_topic": "案例题",
                "daily_target": 30,
            }

        def get_today_progress(self, _user_id: str):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_chapter_progress(self, _user_id: str):
            return []

    class DisabledCoreStore:
        is_configured = False

    async def _no_summary_rewrite(**_kwargs):
        yield "NO_CHANGE"

    path_service = PathServiceStub()
    learner_state_service = LearnerStateService(
        path_service=path_service,
        member_service=MemberServiceStub(),
        core_store=DisabledCoreStore(),
    )
    overlay_service = BotLearnerOverlayService(path_service=path_service)
    overlay_service.promote_candidate(
        "case-study-coach",
        "student_demo",
        "possible_weak_point",
        {
            "topic": "防火间距",
            "confidence": 0.93,
            "promotion_basis": "structured_result",
        },
        source_feature="quiz",
        source_id="quiz_case_1",
    )

    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured_contexts: list[dict[str, object]] = []

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def context_window_tokens(self, _llm_config) -> int:
            return 8192

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=512,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured_contexts.append(
                {
                    "user_message": context.user_message,
                    "memory_context": context.memory_context,
                    "metadata": context.metadata,
                }
            )
            reply = "已记录本轮案例题复习。" if len(captured_contexts) == 1 else "已读取你的薄弱点。"
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content=reply,
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.learner_state.service.llm_stream", _no_summary_rewrite)
    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace(max_tokens=1024))
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_learner_state_service",
        lambda: learner_state_service,
    )
    monkeypatch.setattr(
        "deeptutor.services.learner_state.get_bot_learner_overlay_service",
        lambda: overlay_service,
    )

    session, first_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "我刚做完案例题，帮我记录一下。",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "case-study-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(first_turn["id"], after_seq=0):
        pass
    if runtime._background_tasks:
        await asyncio.gather(*list(runtime._background_tasks))

    progress = learner_state_service.read_progress("student_demo")
    weak_points = list((progress.get("knowledge_map") or {}).get("weak_points") or [])
    assert "防火间距" in weak_points
    assert overlay_service.read_overlay("case-study-coach", "student_demo")["promotion_candidates"] == []
    assert any(
        event.memory_kind == "overlay_promotion"
        and (event.payload_json.get("payload") or {}).get("topic") == "防火间距"
        for event in learner_state_service.list_memory_events("student_demo", limit=20)
    )

    _session, second_turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "回顾一下之前记录的防火间距薄弱点。",
            "session_id": session["id"],
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "case-study-coach",
                "billing_context": {
                    "source": "app",
                    "user_id": "student_demo",
                },
            },
        }
    )

    async for _event in runtime.subscribe_turn(second_turn["id"], after_seq=0):
        pass

    assert len(captured_contexts) >= 2
    second_context = captured_contexts[-1]
    assert "防火间距" in str(second_context["user_message"])
    assert "overlay_promotion" in str(second_context["user_message"])
    assert "learner_progress" in str(second_context["memory_context"])
    assert "memory" in dict(second_context["metadata"]).get("candidate_sources", [])


@pytest.mark.asyncio
async def test_turn_runtime_injects_tutorbot_default_knowledge_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store = SQLiteSessionStore(tmp_path / "chat_history.db")
    runtime = TurnRuntimeManager(store)
    captured: dict[str, object] = {}

    class FakeContextBuilder:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def build(self, **_kwargs):
            return SimpleNamespace(
                conversation_history=[],
                conversation_summary="",
                context_text="",
                token_count=0,
                budget=0,
            )

    class FakeOrchestrator:
        async def handle(self, context):
            captured["enabled_tools"] = context.enabled_tools
            captured["knowledge_bases"] = context.knowledge_bases
            captured["metadata"] = context.metadata
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                source="chat",
                stage="responding",
                content="知识链已启用",
                metadata={"call_kind": "llm_final_response"},
            )
            yield StreamEvent(type=StreamEventType.DONE, source="chat")

    monkeypatch.setattr("deeptutor.services.llm.config.get_llm_config", lambda: SimpleNamespace())
    monkeypatch.setattr("deeptutor.services.session.context_builder.ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr("deeptutor.runtime.orchestrator.ChatOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "deeptutor.services.memory.get_memory_service",
        lambda: SimpleNamespace(
            build_memory_context=lambda: "",
            refresh_from_turn=_noop_refresh,
        ),
    )

    session, turn = await runtime.start_turn(
        {
            "type": "start_turn",
            "content": "请分析这道建筑案例题",
            "session_id": None,
            "capability": None,
            "tools": [],
            "knowledge_bases": [],
            "attachments": [],
            "language": "zh",
            "config": {
                "bot_id": "construction-exam-coach",
                "interaction_profile": "tutorbot",
            },
        }
    )

    events = []
    async for event in runtime.subscribe_turn(turn["id"], after_seq=0):
        events.append(event)

    assert _event_types_without_progress(events) == ["session", "content", "done"]
    assert captured["enabled_tools"] == ["rag"]
    assert captured["knowledge_bases"] == ["construction-exam"]

    detail = await store.get_session_with_messages(session["id"])
    assert detail is not None
    assert detail["preferences"]["tools"] == ["rag"]
    assert detail["preferences"]["knowledge_bases"] == ["construction-exam"]


# plan §Phase 3 Step 3.2 / Batch C Gap 3 — unified_ws redaction smoke.
def test_unified_ws_redacts_hidden_grading_authority_at_public_boundary() -> None:
    from deeptutor.api.routers.unified_ws import _redact_event_for_public

    event = {
        "type": "result",
        "metadata": {
            "question_followup_context": {
                "question_id": "qs",
                "items": [
                    {
                        "question_id": "q1",
                        "question": "Q1",
                        "correct_answer": "B",
                        "grading_key": {"correct_answer": "B"},
                        "explanation": "hidden",
                    }
                ],
            }
        },
    }
    redacted = _redact_event_for_public(event)
    import json as _json
    blob = _json.dumps(redacted, ensure_ascii=False)
    for forbidden in ("grading_key", "correct_answer", "explanation", "hidden"):
        assert forbidden not in blob


# Regression: streaming CONTENT deltas must keep whitespace verbatim.
# Previously _sanitize_public_terminal_event ran every CONTENT delta through
# normalize_markdown_for_tutorbot(coerce_user_visible_answer(...)) — paragraph-
# level transforms that dropped pure-newline deltas to "" and stripped
# leading/trailing whitespace, breaking ATX heading and list parsing in the
# frontend markdown renderer.

def _make_sanitize_content_event(content: str) -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.CONTENT,
        content=content,
        source="tutorbot",
        metadata={"call_kind": "llm_final_response"},
    )


@pytest.mark.parametrize("delta", ["\n", "\n\n", " ", "  \n  "])
def test_sanitize_pure_whitespace_content_delta_is_preserved(delta: str) -> None:
    event = _make_sanitize_content_event(delta)
    _sanitize_public_terminal_event(event, dict(event.metadata or {}))
    assert event.content == delta


def test_sanitize_trailing_newline_in_content_delta_is_preserved() -> None:
    delta = "结论：\n"
    event = _make_sanitize_content_event(delta)
    _sanitize_public_terminal_event(event, dict(event.metadata or {}))
    assert event.content == delta


def test_sanitize_leading_newline_in_content_delta_is_preserved() -> None:
    delta = "\n### 一、基本原则"
    event = _make_sanitize_content_event(delta)
    _sanitize_public_terminal_event(event, dict(event.metadata or {}))
    assert event.content == delta


def test_sanitize_appended_deltas_round_trip_to_markdown_heading() -> None:
    deltas = [
        "位置的主要要求：\n",
        "\n",
        "### 一、基本原则",
        "\n",
        "\n",
        "施工缝应留置在 ",
    ]
    out: list[str] = []
    for delta in deltas:
        event = _make_sanitize_content_event(delta)
        _sanitize_public_terminal_event(event, dict(event.metadata or {}))
        assert isinstance(event.content, str)
        out.append(event.content)
    joined = "".join(out)
    assert "\n\n### 一、基本原则" in joined
    assert "### 一、基本原则\n\n施工缝应留置在" in joined


def test_offer_to_subscriber_bounds_queue_and_preserves_sentinel() -> None:
    """F7: bounded live-subscriber queue drops the oldest event on overflow,
    never raises, stays at maxsize, and always delivers the terminal None sentinel."""
    from deeptutor.services.session.turn_runtime import (
        _MAX_LIVE_SUBSCRIBER_QUEUE_SIZE,
        _offer_to_subscriber,
    )

    # Overflow with live events: never raises, queue stays bounded, oldest dropped.
    q: asyncio.Queue = asyncio.Queue(maxsize=4)
    for i in range(20):
        _offer_to_subscriber(q, {"seq": i})
    assert q.qsize() == 4
    seqs = [q.get_nowait()["seq"] for _ in range(4)]
    assert seqs == [16, 17, 18, 19]  # freshest kept, oldest evicted

    # The None close sentinel must land even when the queue is full
    # (a slow consumer must never hang waiting for end-of-stream).
    q2: asyncio.Queue = asyncio.Queue(maxsize=2)
    _offer_to_subscriber(q2, {"seq": 0})
    _offer_to_subscriber(q2, {"seq": 1})
    assert q2.full()
    _offer_to_subscriber(q2, None)  # must not raise; must enqueue None
    drained = [q2.get_nowait() for _ in range(q2.qsize())]
    assert None in drained

    assert _MAX_LIVE_SUBSCRIBER_QUEUE_SIZE >= 256  # sane bound, headroom for healthy consumers


def test_ws_rejects_oversized_inbound_frame(tmp_path, monkeypatch) -> None:
    """F5: an authenticated client sending a frame above the app-layer char cap is
    rejected fail-fast with a clear error (not silently truncated); normal payload passes."""
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from deeptutor.api import _secure_router as secure_router_mod
    from deeptutor.api.dependencies import AuthContext
    from deeptutor.api.routers.unified_ws import _MAX_WS_INBOUND_FRAME_CHARS, router
    from deeptutor.services.session import SQLiteSessionStore

    store = SQLiteSessionStore(db_path=tmp_path / "ws-f5.db")

    class _FakeRuntime:
        async def start_turn(self, payload):
            return {"id": "session_new"}, {"id": "turn_new"}

        async def subscribe_turn(self, turn_id, after_seq=0):
            yield {
                "type": "done",
                "metadata": {"status": "completed"},
                "session_id": "session_new",
                "turn_id": turn_id,
                "seq": 1,
                "timestamp": 0,
            }

    monkeypatch.setattr(
        secure_router_mod,
        "resolve_auth_context",
        lambda _authorization: AuthContext(
            user_id="u1", provider="test", token="t", claims={"uid": "u1"}, is_admin=False
        ),
    )
    monkeypatch.setattr("deeptutor.services.session.get_sqlite_session_store", lambda: store)
    monkeypatch.setattr("deeptutor.services.session.get_turn_runtime_manager", lambda: _FakeRuntime())

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/ws") as websocket:
            websocket.send_json(
                {"type": "start_turn", "content": "x" * (_MAX_WS_INBOUND_FRAME_CHARS + 100)}
            )
            oversized = websocket.receive_json()
            assert oversized["type"] == "error"
            assert "too large" in oversized["content"].lower()

            # Normal-size payload is processed (not rejected as too large).
            websocket.send_json({"type": "start_turn", "content": "hello"})
            normal = websocket.receive_json()
            assert not (
                normal.get("type") == "error"
                and "too large" in str(normal.get("content", "")).lower()
            )


@pytest.mark.asyncio
async def test_ws_subscription_cleanup_swallows_failed_forward_task_for_contract_coverage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from deeptutor.api.routers.unified_ws import _await_stopped_subscription_task

    async def fail() -> None:
        raise RuntimeError("subscriber failed")

    task = asyncio.create_task(fail())
    await asyncio.sleep(0)

    await _await_stopped_subscription_task("turn-contract-test", task)

    assert "turn-contract-test" in caplog.text
    assert "subscriber failed" in caplog.text
