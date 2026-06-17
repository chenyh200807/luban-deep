from __future__ import annotations

from typing import Any

import pytest

from deeptutor.services.construction_grading.question_grading_registry import (
    QuestionGradingRegistry,
)


def _artifact(question_id: str, status: str) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "version_id": "qga_v0_test",
        "status": status,
        "status_reason": "test",
        "quality_gates": {"auto_certifiable_point_count": 1 if status == "published" else 0},
        "scoring_points": [
            {
                "point_id": "P1",
                "label": "施工总进度计划表(图)",
                "max_score": 2,
                "policy_type": "exact_required",
                "required_terms": ["施工总进度计划表(图)"],
                "list_rule": None,
                "calculation_spec": None,
                "penalty_rule": None,
                "auto_certifiable": status == "published",
                "source_status": "ok" if status == "published" else "missing_or_weak",
                "source_refs": [],
            }
        ],
    }


def _registry() -> QuestionGradingRegistry:
    return QuestionGradingRegistry(
        [
            _artifact("published-case", "published"),
            _artifact("draft-case", "draft"),
        ]
    )


def _fake_draft(question: dict[str, Any], student_answer: str, *, student_id: str, artifact_gate: Any) -> dict[str, Any]:
    from deeptutor.services.construction_grading.ai_draft_shadow import build_ai_draft

    return build_ai_draft(
        question,
        student_answer,
        [
            {
                "point_id": "P1",
                "hit": "hit",
                "score": 2,
                "evidence_span": "施工总进度计划表(图)",
                "rationale": "命中官方术语",
            }
        ],
        points=question["scoring_points"],
        student_id=student_id,
        artifact_gate=artifact_gate,
    )


def test_published_case_generates_shadow_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _fake_draft)

    result = adapter.build_runtime_shadow_result(
        question_id="published-case",
        student_id="qa_runtime_shadow_20260604",
        student_answer="我补充施工总进度计划表(图)。",
        engine="deepseek_fast",
        registry=_registry(),
    )

    assert result["authority"] == "luban_grading_engine_shadow"
    assert result["not_production_grade"] is True
    assert result["writeback_performed"] is False
    assert result["artifact_gate"]["artifact_status"] == "published"
    assert result["point_results"]
    assert result["point_results"][0]["evidence_span"] == "施工总进度计划表(图)"
    assert result["scores"]["model_draft_score"] == 2.0
    assert result["learning_evidence_payload_preview"]["event_type"] == "learning_evidence"


def test_draft_artifact_fails_closed_no_auto_certified(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _fake_draft)

    result = adapter.build_runtime_shadow_result(
        question_id="draft-case",
        student_id="qa_runtime_shadow_20260604",
        student_answer="我补充施工总进度计划表(图)。",
        engine="deepseek_fast",
        registry=_registry(),
    )

    assert result["artifact_gate"]["artifact_status"] == "draft"
    assert result["scores"]["auto_certified_score"] == 0.0
    assert result["teacher_review_required"] is True
    assert result["point_results"][0]["auto_certified"] is False
    assert result["point_results"][0]["high_risk_review"] is True


def test_missing_artifact_fails_closed_without_engine_call(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_build_deepseek_fast_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("engine must not run")),
    )

    result = adapter.build_runtime_shadow_result(
        question_id="missing-case",
        student_id="qa_runtime_shadow_20260604",
        student_answer="任意答案",
        engine="deepseek_fast",
        registry=_registry(),
    )

    assert result["artifact_gate"]["artifact_status"] == "artifact_missing"
    assert result["point_results"] == []
    assert result["teacher_review_required"] is True
    assert result["shadow_status"] == "artifact_missing"


def test_non_qa_student_cannot_enable_qa_shadow(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_build_deepseek_fast_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unsafe user must not run")),
    )

    result = adapter.build_runtime_shadow_result(
        question_id="published-case",
        student_id="real_student_123",
        student_answer="我补充施工总进度计划表(图)。",
        engine="deepseek_fast",
        registry=_registry(),
    )

    assert result["shadow_status"] == "qa_student_required"
    assert result["writeback_performed"] is False
    assert result["point_results"] == []


def test_best_quality_unavailable_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "_build_best_quality_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(adapter.RuntimeShadowUnavailable("best_quality_unavailable")),
    )

    result = adapter.build_runtime_shadow_result(
        question_id="published-case",
        student_id="qa_runtime_shadow_20260604",
        student_answer="我补充施工总进度计划表(图)。",
        engine="best_quality_4model",
        registry=_registry(),
    )

    assert result["shadow_status"] == "engine_unavailable"
    assert result["unavailable_reason"] == "best_quality_unavailable"
    assert result["point_results"] == []
    assert result["scores"]["auto_certified_score"] == 0.0


def test_shadow_does_not_call_kernel_rag_or_writeback(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _fake_draft)
    monkeypatch.setattr(
        "deeptutor.services.construction_grading.case_kernel.CaseGradingSkillKernel.grade",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("kernel must not run")),
    )
    monkeypatch.setattr(
        "deeptutor.services.construction_grading.writeback.write_grading_error_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("writeback must not run")),
    )

    result = adapter.build_runtime_shadow_result(
        question_id="published-case",
        student_id="qa_runtime_shadow_20260604",
        student_answer="我补充施工总进度计划表(图)。",
        engine="deepseek_fast",
        registry=_registry(),
    )

    assert result["writeback_performed"] is False
    assert result["not_production_grade"] is True


def test_legacy_mode_returns_legacy_result_without_shadow() -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    legacy_result = {"authority": "construction_grading", "score_awarded": 1}

    result = adapter.attach_runtime_shadow_result(
        {
            "student_id": "qa_runtime_shadow_20260604",
            "question_followup_context": {
                "question_id": "published-case",
                "question_type": "case",
                "user_answer": "我补充施工总进度计划表(图)。",
            },
        },
        legacy_grading_result=legacy_result,
        grading_engine_mode=adapter.LEGACY_MODE,
    )

    assert result["legacy_grading_result"] is legacy_result
    assert result["shadow_result"] is None


def test_shadow_attach_preserves_legacy_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.construction_grading import runtime_shadow_adapter as adapter

    monkeypatch.setattr(adapter, "_build_deepseek_fast_draft", _fake_draft)
    legacy_result = {"authority": "construction_grading", "score_awarded": 1}

    result = adapter.attach_runtime_shadow_result(
        {
            "student_id": "qa_runtime_shadow_20260604",
            "question_followup_context": {
                "question_id": "published-case",
                "question_type": "case",
                "user_answer": "我补充施工总进度计划表(图)。",
            },
        },
        legacy_grading_result=legacy_result,
        grading_engine_mode=adapter.LUBAN_AI_DRAFT_SHADOW_MODE,
        ai_draft_builder=_fake_draft,
    )

    assert result["legacy_grading_result"] == {"authority": "construction_grading", "score_awarded": 1}
    assert result["shadow_result"]["authority"] == "luban_grading_engine_shadow"
    assert result["shadow_result"]["writeback_performed"] is False
