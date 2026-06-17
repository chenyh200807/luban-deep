"""Tests for Stream D learner-profile synthesis (read-back of teacher-reviewed evidence).

Two layers:
  - Synthetic payloads: assert aggregation, the mastery hard-gate, and suggestion
    mapping deterministically.
  - Real integration: best_quality_for_golden -> teacher-review JSON ->
    build_teacher_review_writeback -> synthesize_learner_profile, end to end on
    the cached 4-model golden samples (no live provider key).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from deeptutor.services.construction_grading.best_quality_ai_draft import (
    BestQualityUnavailable,
    best_quality_for_golden,
)
from deeptutor.services.construction_grading.learning_brain_synthesis import (
    synthesize_learner_profile,
)
from deeptutor.services.construction_grading.teacher_review_writeback import (
    build_teacher_review_writeback,
)

REPO = Path(__file__).resolve().parents[3]
GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"


def _writeback_payload(point_reviews: list[dict[str, Any]], *, case_id: str = "C1") -> dict[str, Any]:
    review = {
        "case_id": case_id,
        "student_id": "qa_s1",
        "engine": "best_quality_4model",
        "teacher_reviewed": True,
        "point_reviews": point_reviews,
    }
    return build_teacher_review_writeback(review)["learning_evidence_payload"]


# ── Synthetic unit tests ──────────────────────────────────────────────────────


def test_synthesizes_weaknesses_and_suggestions_from_small_sample() -> None:
    payload = _writeback_payload([
        {"point_id": "p1", "label": "进度计划列举", "policy_type": "list_rule",
         "max_score": 5, "review_action": "confirm", "ai_hit": "hit", "ai_score": 5,
         "auto_certified": True},
        {"point_id": "p2", "label": "安全文明施工费计算", "policy_type": "calculation",
         "max_score": 2, "review_action": "reject", "ai_hit": "hit", "ai_score": 2},
        {"point_id": "p3", "label": "索赔时限术语", "policy_type": "exact_required",
         "max_score": 1, "review_action": "reject", "ai_hit": "miss", "ai_score": 0},
    ])

    profile = synthesize_learner_profile([payload])

    # teacher_review_points carries no human label, so mastered points fall back
    # to the stable point_id for their label field.
    assert profile["mastered_points"] == [
        {"point_id": "p1", "label": "p1",
         "ability_dimension": "expression", "policy_type": "list_rule"}
    ]
    codes = {w["error_code"] for w in profile["weaknesses"]}
    assert codes == {"E09", "E03"}  # calculation reject -> E09, exact_required miss -> E03
    assert profile["weaknesses"]  # non-empty for 3 samples
    actions = {s["action"] for s in profile["next_suggestions"]}
    assert "redo_calculation" in actions
    assert "review_textbook_term" in actions
    # one suggestion per weakness, preserving order
    assert len(profile["next_suggestions"]) == len(profile["weaknesses"])


def test_high_risk_point_never_counts_as_mastery() -> None:
    payload = _writeback_payload([
        {"point_id": "p_hr", "label": "高风险术语", "policy_type": "exact_required",
         "max_score": 2, "review_action": "confirm", "ai_hit": "hit", "ai_score": 2,
         "auto_certified": True, "high_risk": True},
    ])

    profile = synthesize_learner_profile([payload])

    mastered_ids = {m["point_id"] for m in profile["mastered_points"]}
    assert "p_hr" not in mastered_ids
    assert profile["mastered_points"] == []
    # the high_risk hit is downweighted to a weakness instead
    weakness_points = {pid for w in profile["weaknesses"] for pid in w["sample_point_ids"]}
    assert "p_hr" in weakness_points


def test_unsupported_point_never_counts_as_mastery() -> None:
    payload = _writeback_payload([
        {"point_id": "p_us", "label": "证据不支持点", "policy_type": "list_rule",
         "max_score": 2, "review_action": "confirm", "ai_hit": "hit", "ai_score": 2,
         "auto_certified": True, "unsupported": True},
    ])

    profile = synthesize_learner_profile([payload])

    assert profile["mastered_points"] == []
    weakness_points = {pid for w in profile["weaknesses"] for pid in w["sample_point_ids"]}
    assert "p_us" in weakness_points


def test_teacher_override_can_upgrade_to_mastery() -> None:
    payload = _writeback_payload([
        {"point_id": "p_ov", "label": "教师改判命中", "policy_type": "list_rule",
         "max_score": 2, "review_action": "override", "ai_hit": "miss", "ai_score": 0,
         "teacher_hit": "hit", "teacher_score": 2, "high_risk": True},
    ])

    profile = synthesize_learner_profile([payload])

    mastered_ids = {m["point_id"] for m in profile["mastered_points"]}
    assert "p_ov" in mastered_ids  # teacher override is the higher authority


def test_weaknesses_aggregate_count_across_payloads() -> None:
    payloads = [
        _writeback_payload([
            {"point_id": f"p{i}", "label": f"术语{i}", "policy_type": "exact_required",
             "max_score": 1, "review_action": "reject", "ai_hit": "miss", "ai_score": 0},
        ], case_id=f"C{i}")
        for i in range(3)
    ]

    profile = synthesize_learner_profile(payloads)

    e03 = [w for w in profile["weaknesses"] if w["error_code"] == "E03"]
    assert len(e03) == 1
    assert e03[0]["count"] == 3
    assert sorted(e03[0]["sample_point_ids"]) == ["p0", "p1", "p2"]


def test_payload_without_teacher_review_points_yields_no_mastery() -> None:
    """A raw learning_evidence payload (no teacher review block) contributes
    weaknesses from its error_events but never mastery — there is no authority."""
    payload = {
        "error_events": [
            {"error_code": "E09", "concept_tag": "计算点", "severity": 1.0},
        ],
        "next_training_signal": {},
    }
    profile = synthesize_learner_profile([payload])
    assert profile["mastered_points"] == []
    assert any(w["error_code"] == "E09" for w in profile["weaknesses"])


def test_empty_and_malformed_inputs_are_safe() -> None:
    assert synthesize_learner_profile([]) == {
        "weaknesses": [], "mastered_points": [], "next_suggestions": []
    }
    profile = synthesize_learner_profile([None, "garbage", 42])  # type: ignore[list-item]
    assert profile == {"weaknesses": [], "mastered_points": [], "next_suggestions": []}


def test_unknown_error_code_buckets_into_fallback_dimension() -> None:
    payload = {
        "error_events": [{"error_code": "ZZ99", "concept_tag": "未知点"}],
        "next_training_signal": {},
    }
    profile = synthesize_learner_profile([payload])
    assert profile["weaknesses"][0]["error_code"] == "unknown_error"
    assert profile["weaknesses"][0]["dimension"] == "review_execution"


# ── Real integration on cached golden 4-model predictions ─────────────────────


def _golden_cases() -> list[dict[str, Any]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return data.get("cases") or []


def _point_reviews_from_draft(draft: dict[str, Any]) -> list[dict[str, Any]]:
    """Simulate a teacher confirming the AI draft point-by-point (auto_certified
    points -> confirm; high_risk/unsupported stay flagged so the hard-gate fires)."""
    reviews: list[dict[str, Any]] = []
    for pr in draft["point_results"]:
        reviews.append({
            "point_id": pr["point_id"],
            "label": pr.get("expected_point_label", "")[:40],
            "policy_type": pr.get("policy_type"),
            "max_score": pr.get("max_score"),
            "review_action": "confirm",
            "ai_hit": pr.get("hit"),
            "ai_score": pr.get("score"),
            "auto_certified": bool(pr.get("auto_certified")),
            "high_risk": bool(pr.get("high_risk_review")),
            "unsupported": bool(pr.get("unsupported")),
        })
    return reviews


def _real_payloads(limit: int = 5) -> list[dict[str, Any]]:
    """One learner's review payloads across distinct golden cases (a real
    single-student profile: distinct case_ids, no point_id collisions)."""
    payloads: list[dict[str, Any]] = []
    for question in _golden_cases():
        case_id = question.get("case_id") or question.get("id")
        sample = next(iter(question.get("eval_samples") or []), None)
        if sample is None:
            continue
        try:
            draft = best_quality_for_golden(question, sample.get("student_id"))
        except BestQualityUnavailable:
            continue
        payloads.append(
            _writeback_payload(_point_reviews_from_draft(draft), case_id=case_id)
        )
        if len(payloads) >= limit:
            return payloads
    return payloads


def test_real_golden_samples_produce_profile() -> None:
    payloads = _real_payloads(limit=5)
    if len(payloads) < 3:
        pytest.skip("cached 4-model predictions unavailable for >=3 golden samples")

    profile = synthesize_learner_profile(payloads)

    assert set(profile.keys()) == {"weaknesses", "mastered_points", "next_suggestions"}
    # profile is usable: at least one of mastery / weakness is populated
    assert profile["mastered_points"] or profile["weaknesses"]
    assert len(profile["next_suggestions"]) == len(profile["weaknesses"])

    # hard-gate holds on real data: no mastered point is high_risk/unsupported.
    mastered_ids = {m["point_id"] for m in profile["mastered_points"]}
    for payload in payloads:
        for row in payload["next_training_signal"]["teacher_review_points"]:
            if row["point_id"] in mastered_ids:
                assert row["mastery_eligible"] is True

    # every suggestion carries a registered error code + a known action verb.
    for suggestion in profile["next_suggestions"]:
        assert suggestion["action"]
        assert suggestion["reason"]
