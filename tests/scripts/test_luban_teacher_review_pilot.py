"""Stream B — deterministic tests for the teacher-review pilot closed loop.

No live provider key (cached 4-model predictions only). dry_run only. Asserts:
  - the pilot runs end-to-end for all subjects;
  - teacher-final overrides the AI draft (override upgrades, reject downgrades);
  - a high_risk point that is NOT teacher-confirmed never becomes mastery;
  - the Learning-Brain read-back yields at least one weakness AND one mastery signal.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.construction_grading.teacher_review_pilot import (
    confirm_ai,
    override_upgrade,
    reject_overcredit,
    run_pilot,
    run_pilot_subject,
)

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"


@pytest.fixture(scope="module")
def cases() -> dict[str, dict]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return {c["case_id"]: c for c in data.get("cases", [])}


@pytest.fixture(scope="module")
def pilot(cases: dict[str, dict]) -> dict:
    subjects = [
        {"golden_case": cases["Q10-1A422000"], "student_id": "S2"},
        {"golden_case": cases["Q1-NA"], "student_id": "S2",
         "policy_by_point": {"P1": reject_overcredit}},
        {"golden_case": cases["Q20-1A413000"], "student_id": "S2"},
        {"golden_case": cases["Q8-1A413030"], "student_id": "S1"},
        {"golden_case": cases["Q4-1A434000-罚则"], "student_id": "S4",
         "policy_by_point": {"P1": override_upgrade}},
    ]
    return run_pilot(subjects)


def test_pilot_runs_for_all_subjects(pilot: dict) -> None:
    assert len(pilot["subjects"]) == 5
    for subject in pilot["subjects"]:
        wb = subject["writeback"]
        # dry_run is forced True end-to-end — no real user / DB is touched.
        assert wb["dry_run"] is True
        assert "writeback_count" not in wb  # dry-run never persists
        # every point produced a write_plan row + a teacher-final point event
        draft_points = subject["draft"]["point_results"]
        assert len(wb["write_plan"]) == len(draft_points)
        signal = wb["learning_evidence_payload"]["next_training_signal"]
        assert signal["grading_source"] == "teacher_review"
        assert signal["teacher_reviewed"] is True
        assert len(signal["teacher_review_points"]) == len(draft_points)


def test_reviewer_is_marked_synthetic(pilot: dict) -> None:
    # quasi-real: we never impersonate a named human.
    for subject in pilot["subjects"]:
        assert subject["review_json"]["reviewer_is_synthetic"] is True


def test_teacher_override_upgrades_ai(cases: dict[str, dict]) -> None:
    # Q4 P1: AI scored it a miss; teacher override -> full hit -> mastery.
    result = run_pilot_subject(
        cases["Q4-1A434000-罚则"], "S4", policy_by_point={"P1": override_upgrade}
    )
    p1 = next(r for r in result["writeback"]["write_plan"] if r["point_id"] == "P1")
    assert p1["authority"] == "teacher_override"
    assert p1["ai_hit"] == "miss"
    assert p1["final_hit"] == "hit"
    assert p1["mastery_eligible"] is True
    assert "P1" in result["writeback"]["mastery_point_ids"]


def test_teacher_reject_downgrades_overcredit(cases: dict[str, dict]) -> None:
    # Q1 P1: AI gave partial high_risk credit; teacher rejects -> miss -> no mastery.
    result = run_pilot_subject(
        cases["Q1-NA"], "S2", policy_by_point={"P1": reject_overcredit}
    )
    p1 = result["writeback"]["write_plan"][0]
    assert p1["point_id"] == "P1"
    assert p1["authority"] == "teacher_reject"
    assert p1["final_hit"] == "miss"
    assert p1["mastery_eligible"] is False
    assert result["writeback"]["mastery_point_ids"] == []


def test_high_risk_not_confirmed_never_mastery(cases: dict[str, dict]) -> None:
    # The single-authority guard: a high_risk point reviewed with plain `confirm`
    # (NOT an override) still earns no mastery, even though the teacher signed off.
    result = run_pilot_subject(cases["Q1-NA"], "S2", default_policy=confirm_ai)
    p1 = result["writeback"]["write_plan"][0]
    assert p1["high_risk_review"] is True
    assert p1["review_action"] == "confirm"
    assert p1["mastery_eligible"] is False
    assert "P1" not in result["writeback"]["mastery_point_ids"]


def test_basically_correct_becomes_mastery(cases: dict[str, dict]) -> None:
    # Q8 S1: a clean full hit confirmed by the teacher -> mastery evidence.
    result = run_pilot_subject(cases["Q8-1A413030"], "S1")
    assert result["writeback"]["mastery_point_ids"] == ["P1"]


def test_synthesis_has_weakness_and_mastery(pilot: dict) -> None:
    syn = pilot["synthesis"]
    assert len(syn["weaknesses"]) >= 1
    assert len(syn["mastered_points"]) >= 1
    # one next-step suggestion per weakness, same ordering
    assert len(syn["next_suggestions"]) == len(syn["weaknesses"])
    # weakness signals carry a registry error_code + ability_dimension
    for w in syn["weaknesses"]:
        assert w["error_code"]
        assert w["dimension"]
        assert w["count"] >= 1


def test_synthesis_mastery_only_from_teacher_final(pilot: dict) -> None:
    # Every mastered point must trace back to a teacher-final mastery_eligible row;
    # high_risk / rejected points must be absent.
    eligible: set[str] = set()
    for subject in pilot["subjects"]:
        eligible.update(subject["writeback"]["mastery_point_ids"])
    mastered_ids = {m["point_id"] for m in pilot["synthesis"]["mastered_points"]}
    assert mastered_ids <= eligible
    assert mastered_ids  # at least one mastery signal exists
