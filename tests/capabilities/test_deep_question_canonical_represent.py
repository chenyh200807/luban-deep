"""M4(i) 方案②: deep_question deterministic canonical re-present emit.

The followup branch of DeepQuestionCapability would otherwise hand a "重排/重新
展示" request to a free LLM (route_to_followup_explainer), producing a divergent
option surface that causes grading 倒诬. Instead it re-presents the active single
MCQ deterministically from the single authority (active_object.state_snapshot)
via ``_emit_canonical_represent`` — preserving the active object so a subsequent
answer is graded against the same surface the learner just saw.
"""

from __future__ import annotations

import pytest

from deeptutor.capabilities.deep_question import DeepQuestionCapability
from deeptutor.core.stream import StreamEventType
from deeptutor.core.stream_bus import StreamBus


def _mcq_active_object() -> dict[str, object]:
    return {
        "object_type": "single_question",
        "object_id": "q_1",
        "state_snapshot": {
            "question_id": "q_1",
            "question": "一级建造师注册证书的有效期是几年？",
            "question_type": "choice",
            "options": {"A": "1年", "B": "3年", "C": "4年", "D": "5年"},
            "user_answer": "",
            "is_correct": None,
            "multi_select": False,
            "items": [],
        },
    }


def _result_payload(stream: StreamBus) -> dict:
    result_events = [e for e in stream._history if e.type == StreamEventType.RESULT]
    assert result_events, "expected a result event"
    return result_events[-1].metadata


@pytest.mark.asyncio
async def test_emit_canonical_represent_emits_canonical_order_and_preserves_object() -> None:
    active_object = _mcq_active_object()
    stream = StreamBus()
    response_text = (
        "一级建造师注册证书的有效期是几年？\n\n"
        "A. 1年\nB. 3年\nC. 4年\nD. 5年\n\n"
        "（选项顺序与原题保持一致，以保证判分准确。请直接回复你选的字母。）"
    )

    await DeepQuestionCapability()._emit_canonical_represent(
        stream=stream,
        turn_id="t-represent",
        active_object=active_object,
        suspended_object_stack=[],
        turn_semantic_decision={"relation_to_active_object": "ask_about_active_object"},
        response_text=response_text,
    )

    payload = _result_payload(stream)
    # 1. The canonical (original-order) re-presentation is the emitted response.
    assert "B. 3年" in str(payload["response"])
    assert payload["execution_path"] == "deep_question_canonical_mcq_represent"
    assert payload["question_authority_source"] == "canonical_mcq_represent"

    # 2. The active object / question context are PRESERVED (state not lost),
    #    so a subsequent answer grades against the same canonical surface.
    assert payload["active_object"].get("object_id") == "q_1"
    fctx = payload["question_followup_context"]
    assert isinstance(fctx, dict) and fctx.get("question_type") == "choice"
    assert (fctx.get("options") or {}).get("B") == "3年"

    # 3. No answer / explanation revealed by the re-present itself.
    assert payload["reveal_answers"] is False
    assert payload["reveal_explanations"] is False


def test_build_canonical_represent_wired_into_followup_branch() -> None:
    """Guard: the shared single-authority helper is imported & used by the
    deep_question followup branch (not a dangling import)."""

    import inspect

    from deeptutor.capabilities import deep_question as dq

    assert hasattr(dq, "build_canonical_represent_response")
    src = inspect.getsource(dq.DeepQuestionCapability.run)
    assert "build_canonical_represent_response(" in src
    assert "_emit_canonical_represent(" in src
