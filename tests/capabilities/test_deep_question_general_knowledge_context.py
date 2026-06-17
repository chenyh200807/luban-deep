"""M34: general-knowledge teaching context is shadow/cohort gated and killable."""
from __future__ import annotations

from types import SimpleNamespace

import deeptutor.capabilities.deep_question as dq


def _ctx(*, user_id: str, message: str, flag: bool | None = None) -> SimpleNamespace:
    config_overrides = {}
    if flag is not None:
        config_overrides["general_knowledge_context"] = flag
    return SimpleNamespace(
        user_message=message,
        metadata={
            "learner_user_id": user_id,
        },
        config_overrides=config_overrides,
    )


def test_default_off_real_user_does_not_attach_teaching_context() -> None:
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="real_student_42", message="高层住宅的建筑高度怎么界定？"),
        result_payload=payload,
    )
    assert "luban_general_knowledge_context" not in payload


def test_explicit_false_disables_production_default() -> None:
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="real_student_42", message="高层住宅的建筑高度怎么界定？", flag=False),
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


def test_metadata_flag_is_not_enablement_authority() -> None:
    context = _ctx(user_id="qa_alice", message="高层住宅的建筑高度怎么界定？", flag=False)
    context.metadata["general_knowledge_context"] = True
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=context,
        result_payload=payload,
    )
    assert "luban_general_knowledge_context" not in payload


def test_items_batch_context_counts_as_active_question_context() -> None:
    assert dq._has_active_question_context(
        {
            "items": [
                {
                    "question_id": "q1",
                    "question": "事件一中模板支架搭设有哪些不妥？",
                    "question_type": "case",
                }
            ]
        }
    ) is True
    assert dq._has_active_question_context({}) is False


def test_kill_switch_overrides_flag(monkeypatch) -> None:
    monkeypatch.setenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED", "false")
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="qa_alice", message="高层住宅的建筑高度怎么界定？", flag=True),
        result_payload=payload,
    )
    assert payload.get("luban_general_knowledge_context", {}).get("killed_by_switch") is True


def test_optional_cohort_env_can_restrict_rollout(monkeypatch) -> None:
    monkeypatch.setenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT", "qa_,operator_")
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="real_student_42", message="高层住宅的建筑高度怎么界定？"),
        result_payload=payload,
    )
    assert "luban_general_knowledge_context" not in payload


def test_optional_cohort_env_can_enable_shadow_rollout(monkeypatch) -> None:
    monkeypatch.setenv("LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT", "qa_,operator_")
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="qa_alice", message="高层住宅的建筑高度怎么界定？"),
        result_payload=payload,
    )
    block = payload.get("luban_general_knowledge_context")
    assert block and block["official_score_allowed"] is False
    assert block["tier"] == "teaching_context_not_answer_key"


def test_off_syllabus_falls_open_no_block() -> None:
    payload: dict = {}
    dq._maybe_attach_general_knowledge_context(
        context=_ctx(user_id="real_student_42", message="今天天气怎么样随便聊聊"),
        result_payload=payload,
    )
    assert "luban_general_knowledge_context" not in payload
