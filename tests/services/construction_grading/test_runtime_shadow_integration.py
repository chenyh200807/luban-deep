"""Integration test for the QA/test runtime-shadow wire in deep_question.

Exercises the REAL wire helper ``deep_question._maybe_attach_runtime_shadow`` against
the real golden Registry, with a deterministic engine builder (no live provider call).

Truth levels (see FINDING):
- REAL: the wire helper, the flag gating, the QuestionGradingArtifact Registry, the
  ArtifactRuntimeGate, the legacy-untouched contract.
- SIMULATED: the per-point model predictions (deterministic fixture) instead of a live
  DeepSeek/Best-Quality call, so the test is hermetic.
"""
from __future__ import annotations

from typing import Any

from deeptutor.capabilities import deep_question as dq
from deeptutor.core.context import UnifiedContext
from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

# real golden questions with known runtime-gate status
PUBLISHED = "Q17-1A433000"  # published, has auto-certifiable + weak points
DRAFT = "QD-SYNTH-DRAFT"    # synthetic draft (0 auto-certifiable, no high_risk); the
                            # bank's former draft (Q20) is now correctly blocked by the
                            # declared-total/point-sum gate
BLOCKED = "Q15-NA"          # blocked (0 auto + high_risk)
MISSING = "Q-DOES-NOT-EXIST"


def _synthetic_draft_registry():
    from deeptutor.services.construction_grading import artifact_runtime_gate as arg
    from deeptutor.services.construction_grading.question_grading_registry import (
        QuestionGradingRegistry,
        build_default_registry,
    )

    base = build_default_registry()
    registry = QuestionGradingRegistry(
        [base.get_artifact(qid) for qid in base.question_ids()]
    )
    registry.add(
        {
            "question_id": DRAFT,
            "version_id": "qga_v0_synth",
            "status": "draft",
            "scoring_points": [
                {
                    "point_id": "P1",
                    "label": "x",
                    "max_score": 2.0,
                    "policy_type": "qualitative",
                    "auto_certifiable": False,
                    "source_status": "missing",
                }
            ],
            "quality_gates": {"auto_certifiable_point_count": 0, "blocked_reasons": []},
        }
    )
    return registry


def _legacy() -> dict[str, Any]:
    return {"authority": "construction_grading", "type": "case", "score_awarded": 1.0, "max_score": 2.0}


def _graded_context(question_id: str, answer: str) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "user_answer": answer,
        "question_type": "case",
        "construction_grading_result": _legacy(),
    }


def _ctx(*, user_id: str | None, flag: bool, engine: str = "deepseek_fast") -> UnifiedContext:
    metadata: dict[str, Any] = {}
    if user_id is not None:
        metadata["user_id"] = user_id
    if flag:
        metadata["grading_engine_runtime_shadow"] = True
        metadata["grading_engine_runtime_shadow_engine"] = engine
    return UnifiedContext(session_id="s", user_message="m", metadata=metadata)


def _deterministic_builder(question, student_answer, *, student_id, artifact_gate):
    """Hit every scoring point with evidence_span == the answer (always a valid span),
    then let the real artifact gate decide auto vs pending."""
    from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft

    preds = [
        {
            "point_id": sp["point_id"],
            "hit": "hit",
            "score": float(sp.get("max_score") or 1),
            "evidence_span": student_answer,
            "rationale": "qa fixture",
        }
        for sp in (question.get("scoring_points") or [])
    ]
    return build_ai_draft(
        question, student_answer, preds,
        points=question.get("scoring_points") or [],
        student_id=student_id, artifact_gate=artifact_gate,
    )


def _run(question_id, *, user_id, flag, engine="deepseek_fast", answer="施工总进度计划表(图)，甲乙丙，措施一二三。"):
    payload: dict[str, Any] = {"construction_grading_result": _legacy()}
    dq._maybe_attach_runtime_shadow(
        context=_ctx(user_id=user_id, flag=flag, engine=engine),
        graded_context=_graded_context(question_id, answer),
        result_payload=payload,
    )
    return payload


def test_no_flag_means_no_shadow_key(monkeypatch):
    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _deterministic_builder)
    payload = _run(PUBLISHED, user_id="qa_runtime_20260604", flag=False)
    assert "luban_grading_engine_shadow" not in payload
    assert payload["construction_grading_result"] == _legacy()  # legacy byte-identical


def test_flag_plus_qa_student_attaches_shadow(monkeypatch):
    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _deterministic_builder)
    payload = _run(PUBLISHED, user_id="qa_runtime_20260604", flag=True)
    shadow = payload["luban_grading_engine_shadow"]
    assert shadow["authority"] == "luban_grading_engine_shadow"
    assert shadow["not_production_grade"] is True
    assert shadow["writeback_performed"] is False
    assert shadow["artifact_gate"]["artifact_status"] == "published"
    assert shadow["point_results"]
    # published -> at least one auto-certified point, and every positive carries a span
    autos = [p for p in shadow["point_results"] if p["auto_certified"]]
    assert autos
    for p in autos:
        assert p.get("evidence_span")
    # legacy untouched
    assert payload["construction_grading_result"] == _legacy()


def test_flag_plus_non_qa_student_is_qa_student_required(monkeypatch):
    # engine must NOT run for a non-QA student
    monkeypatch.setattr(
        adapter, "_build_deepseek_fast_draft",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("engine must not run for non-QA")),
    )
    payload = _run(PUBLISHED, user_id="real_student_123", flag=True)
    shadow = payload["luban_grading_engine_shadow"]
    assert shadow["shadow_status"] == "qa_student_required"
    assert shadow["point_results"] == []
    assert shadow["writeback_performed"] is False
    assert payload["construction_grading_result"] == _legacy()


def test_draft_case_no_auto_certification(monkeypatch):
    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _deterministic_builder)
    from deeptutor.services.construction_grading import artifact_runtime_gate as arg

    registry = _synthetic_draft_registry()
    monkeypatch.setattr(arg, "_default_registry", lambda: registry)
    shadow = _run(DRAFT, user_id="qa_runtime_20260604", flag=True)["luban_grading_engine_shadow"]
    assert shadow["artifact_gate"]["artifact_status"] == "draft"
    assert shadow["scores"]["auto_certified_score"] == 0.0
    assert shadow["teacher_review_required"] is True
    assert all(p["auto_certified"] is False for p in shadow["point_results"])


def test_blocked_case_no_auto_certification(monkeypatch):
    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _deterministic_builder)
    shadow = _run(BLOCKED, user_id="test_qa_user", flag=True)["luban_grading_engine_shadow"]
    assert shadow["artifact_gate"]["artifact_status"] == "blocked"
    assert shadow["scores"]["auto_certified_score"] == 0.0
    assert all(p["auto_certified"] is False for p in shadow["point_results"])


def test_missing_artifact_fails_closed_without_engine(monkeypatch):
    # engine must NOT run when the artifact is missing
    monkeypatch.setattr(
        adapter, "_build_deepseek_fast_draft",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("engine must not run when missing")),
    )
    shadow = _run(MISSING, user_id="qa_runtime_20260604", flag=True)["luban_grading_engine_shadow"]
    assert shadow["artifact_gate"]["artifact_status"] == "artifact_missing"
    assert shadow["point_results"] == []
    assert shadow["writeback_performed"] is False


def test_adapter_exception_fails_closed_and_legacy_survives(monkeypatch):
    monkeypatch.setattr(
        adapter, "_build_deepseek_fast_draft",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider boom")),
    )
    payload = _run(PUBLISHED, user_id="qa_runtime_20260604", flag=True)
    shadow = payload["luban_grading_engine_shadow"]
    # adapter catches RuntimeShadowUnavailable/BestQualityUnavailable; a raw RuntimeError
    # bubbles to the wire helper's fail-closed branch -> engine_unavailable.
    assert shadow["shadow_status"] in {"engine_unavailable"}
    assert shadow["writeback_performed"] is False
    # legacy still returns intact
    assert payload["construction_grading_result"] == _legacy()


def test_shadow_does_not_call_kernel_or_writeback(monkeypatch):
    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _deterministic_builder)
    monkeypatch.setattr(
        "deeptutor.services.construction_grading.case_kernel.CaseGradingSkillKernel.grade",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("kernel must not run")),
    )
    monkeypatch.setattr(
        dq, "write_grading_error_events",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("writeback must not run")),
    )
    payload = _run(PUBLISHED, user_id="qa_runtime_20260604", flag=True)
    assert payload["luban_grading_engine_shadow"]["writeback_performed"] is False
    assert "learning_evidence_payload_preview" in payload["luban_grading_engine_shadow"]
