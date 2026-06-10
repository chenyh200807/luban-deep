"""M35 runtime shadow payload builder: blocked artifacts must fail open, not get graded."""
from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.m35_artifact_shadow import (
    build_m35_artifact_shadow_payload,
)


def _blocked_artifact() -> dict[str, Any]:
    return {
        "version_id": "qga_v0_test",
        "status": "blocked",
        "quality_gates": {
            "score_sum_ok": False,
            "source_pollution_count": 0,
            "source_refs_verified_rate": 1.0,
            "blocked_reasons": ["score_sum_mismatch"],
        },
        "scoring_points": [
            {
                "point_id": "P1",
                "label": "指出需要专家论证",
                "max_score": 1.0,
                "policy_type": "qualitative",
            }
        ],
    }


def test_blocked_artifact_short_circuits_shadow(monkeypatch):
    import deeptutor.services.construction_grading.question_grading_artifacts as qga

    monkeypatch.setattr(
        qga, "build_question_grading_artifact", lambda _qid: _blocked_artifact()
    )

    payload = build_m35_artifact_shadow_payload(
        question_id="Q1-NA",
        student_answer="需要组织专家论证",
        student_id="qa_m35",
    )

    assert payload["shadow_status"] == "artifact_blocked"
    assert payload["point_matches"] == []
    assert payload["official_score_allowed"] is False
    assert payload["teacher_review_required"] is True
    assert "awarded_score_shadow" not in payload or payload["awarded_score_shadow"] is None


def test_polluted_artifact_short_circuits_shadow(monkeypatch):
    import deeptutor.services.construction_grading.question_grading_artifacts as qga

    artifact = _blocked_artifact()
    artifact["status"] = "published"
    artifact["quality_gates"] = {
        "score_sum_ok": True,
        "source_pollution_count": 2,
        "source_refs_verified_rate": 1.0,
        "blocked_reasons": [],
    }
    monkeypatch.setattr(
        qga, "build_question_grading_artifact", lambda _qid: artifact
    )

    payload = build_m35_artifact_shadow_payload(
        question_id="Q1-NA",
        student_answer="需要组织专家论证",
        student_id="qa_m35",
    )

    assert payload["shadow_status"] == "artifact_blocked"
    assert payload["point_matches"] == []
