"""gap_1 / M28: the live deep_question grading surface must emit a Learning-Brain
preview built from the SAME compiled context the grading surface used.

This proves ``build_learning_evidence_from_context_pack`` is reachable from the
production ``/api/v1/ws`` grading runtime — not only from scripts/tests
(production consumer calls were 0). PREVIEW only: never raises mastery, never
writes canonical truth, never mutates the legacy ``construction_grading_result``.
"""
from __future__ import annotations

import inspect

from deeptutor.capabilities.deep_question import (
    DeepQuestionCapability,
    _maybe_attach_learning_evidence_preview,
)
from deeptutor.services.construction_grading.deep_question_adapter import (
    build_deep_question_grading_result,
)


def _graded_context(user_answer: str = "A") -> dict:
    qc = {
        "question_id": "Q_MCQ_1",
        "question_type": "single_choice",
        "stem": "建筑物构成不包括？",
        "options": {"A": "结构", "B": "围护", "C": "设备", "D": "投标"},
        "correct_answer": "D",
    }
    grading_result = build_deep_question_grading_result(qc, user_answer=user_answer)
    assert grading_result is not None and "compiled_context" in grading_result
    ctx = dict(qc)
    ctx["user_answer"] = user_answer
    ctx["construction_grading_result"] = grading_result
    return ctx


def test_preview_attached_and_reuses_same_compiled_context() -> None:
    graded = _graded_context()
    payload: dict = {}
    _maybe_attach_learning_evidence_preview(
        graded_context=graded, result_payload=payload, turn_id="t1"
    )
    preview = payload["learning_evidence_preview"]
    # PREVIEW only — the authority invariants the fat skill guarantees must hold here.
    assert preview["preview_only"] is True
    assert preview["mastery_raised"] is False
    assert preview["canonical_truth_written"] is False
    # Derived from the SAME pack the grading surface used (no re-assembled context).
    cc = graded["construction_grading_result"]["compiled_context"]
    assert preview["compiled_context_provenance"]["pack_hash"] == cc["provenance"]["pack_hash"]


def test_kill_switch_keeps_legacy_payload_byte_identical(monkeypatch) -> None:
    monkeypatch.setenv("LUBAN_LEARNING_EVIDENCE_PREVIEW_DISABLED", "1")
    graded = _graded_context()
    payload: dict = {"construction_grading_result": graded["construction_grading_result"]}
    before = dict(payload)
    _maybe_attach_learning_evidence_preview(
        graded_context=graded, result_payload=payload, turn_id="t1"
    )
    assert payload == before
    assert "learning_evidence_preview" not in payload


def test_fail_closed_without_grading_result_leaves_legacy_untouched() -> None:
    payload: dict = {}
    _maybe_attach_learning_evidence_preview(
        graded_context={"question_id": "x"}, result_payload=payload, turn_id="t1"
    )
    assert "learning_evidence_preview" not in payload


def test_does_not_mutate_legacy_grading_result() -> None:
    graded = _graded_context()
    legacy = graded["construction_grading_result"]
    legacy_before = dict(legacy)
    payload: dict = {"construction_grading_result": legacy}
    _maybe_attach_learning_evidence_preview(
        graded_context=graded, result_payload=payload, turn_id="t1"
    )
    assert payload["construction_grading_result"] == legacy_before


def test_session_id_forwarded_into_preview() -> None:
    graded = _graded_context()
    payload: dict = {}
    _maybe_attach_learning_evidence_preview(
        graded_context=graded, result_payload=payload, turn_id="t1", session_id="s1"
    )
    assert payload["learning_evidence_preview"]["session_id"] == "s1"


def test_wired_into_live_grading_surface() -> None:
    """gap_1 regression guard: the consumer must stay reachable from the live
    grading runtime, not only from offline scripts/tests — and must carry the real
    turn/session correlation so downstream dedupe keys are not blank."""
    src = inspect.getsource(DeepQuestionCapability._emit_grading_result)
    assert "_maybe_attach_learning_evidence_preview" in src
    assert "session_id=str(context.session_id" in src


def test_v1_llm_adjudication_receives_personalization_context_readonly() -> None:
    """Grading-to-Brain regression: the v1 adjudication wrapper must forward the
    single PersonalizationContextPack from turn metadata into the fat skill.
    The wrapper may not synthesize its own learner profile or recommendation."""
    import deeptutor.capabilities.deep_question as deep_question

    src = inspect.getsource(deep_question._maybe_attach_v1_llm_adjudication)
    assert 'context.metadata.get("personalization_context")' in src
    assert "personalization_context_pack=" in src
    assert "build_personalization_context_pack" not in src
