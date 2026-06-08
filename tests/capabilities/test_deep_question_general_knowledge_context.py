"""M34 Task 2: thin wrapper attaches general-knowledge teaching context only when gated."""
from __future__ import annotations

from types import SimpleNamespace

import deeptutor.capabilities.deep_question as dq


def _ctx(*, user_id: str, message: str, flag: bool) -> SimpleNamespace:
    return SimpleNamespace(
        user_message=message,
        metadata={
            "general_knowledge_context": flag,
            "learner_user_id": user_id,
        },
        config_overrides={},
    )


def test_default_off_attaches_nothing() -> None:
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="qa_alice", message="高层住宅的建筑高度怎么界定？", flag=False),
        result_payload=payload,
    )
    assert "luban_general_knowledge_context" not in payload


def test_flag_on_cohort_on_syllabus_attaches_teaching_context() -> None:
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="qa_alice", message="高层住宅的建筑高度怎么界定？", flag=True),
        result_payload=payload,
    )
    block = payload.get("luban_general_knowledge_context")
    assert block and block["official_score_allowed"] is False
    assert block["tier"] == "teaching_context_not_answer_key"


def test_kill_switch_overrides_flag(monkeypatch) -> None:
    monkeypatch.setenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", "false")
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="qa_alice", message="高层住宅的建筑高度怎么界定？", flag=True),
        result_payload=payload,
    )
    assert payload.get("luban_general_knowledge_context", {}).get("killed_by_switch") is True


def test_non_cohort_user_attaches_nothing() -> None:
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="real_student_42", message="高层住宅的建筑高度怎么界定？", flag=True),
        result_payload=payload,
    )
    assert "luban_general_knowledge_context" not in payload


def test_off_syllabus_falls_open_no_block() -> None:
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="qa_alice", message="今天天气怎么样随便聊聊", flag=True),
        result_payload=payload,
    )
    assert "luban_general_knowledge_context" not in payload
