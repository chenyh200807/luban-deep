from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "knowql_nexus_l3_ab",
    REPO / "scripts" / "run_luban_knowql_nexus_l3_cohort_ab.py",
)
knowql_nexus_l3_ab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(knowql_nexus_l3_ab)


def test_l3_cohort_schedule_randomizes_distinct_learners_per_arm() -> None:
    schedule = knowql_nexus_l3_ab.build_cohort_schedule(
        subjects_per_arm=3,
        seed=20260615,
        username_prefix="qa_pgo_l3_ab",
    )

    assert len(schedule) == 9
    assert {subject.arm for subject in schedule} == {"A0", "B1", "B2"}
    assert {subject.arm: sum(1 for item in schedule if item.arm == subject.arm) for subject in schedule} == {
        "A0": 3,
        "B1": 3,
        "B2": 3,
    }
    assert len({subject.subject_id for subject in schedule}) == 9
    assert len({subject.username for subject in schedule}) == 9
    assert all(subject.username.startswith("qa_pgo_l3_ab_") for subject in schedule)


def test_l3_preregistration_discloses_cohort_scope_and_fixed_metrics() -> None:
    prereg = knowql_nexus_l3_ab.build_l3_preregistration(
        scenario_count=5,
        subjects_per_arm=5,
        min_subjects_per_arm=5,
        cohort_mode="authorized_qa_operator",
        min_b2_outcome_miss_reduction_lift=1.0,
        max_b2_p95_latency_delta_pct=250.0,
        max_b2_payload_delta_pct=50.0,
    )

    assert prereg["schema_version"] == "knowql_nexus_l3_cohort_preregistration.v1"
    assert prereg["primary_effect_metric"] == "b2_real_cohort_outcome_miss_reduction_lift_vs_b1"
    assert prereg["population"] == "authorized_qa_operator_test2_cohort"
    assert prereg["human_learner_claim_allowed"] is False
    assert prereg["production_learner_claim_allowed"] is False
    assert "distinct_learner_per_subject == true" in prereg["safety_guardrails"]
    assert "canonical_truth_write_count == 0" in prereg["safety_guardrails"]
    assert prereg["minimum_subjects_per_arm"] == 5


def test_l3_auth_uses_register_token_without_immediate_login() -> None:
    payload = {
        "token": "dtm.test-token",
        "token_type": "Bearer",
        "user_id": "auth_123",
    }

    assert knowql_nexus_l3_ab.extract_token_from_auth_payload(payload) == "dtm.test-token"
    assert knowql_nexus_l3_ab.extract_token_from_auth_payload({"access_token": "alt-token"}) == "alt-token"
    assert knowql_nexus_l3_ab.extract_token_from_auth_payload({"token": ""}) == ""
    assert knowql_nexus_l3_ab.extract_user_id_from_auth_payload(payload) == "auth_123"
    assert knowql_nexus_l3_ab.extract_user_id_from_auth_payload({"user": {"id": "nested_uid"}}) == "nested_uid"


def test_l3_subject_rows_include_cohort_auth_diagnostics() -> None:
    subject = knowql_nexus_l3_ab.CohortSubject(
        subject_index=7,
        subject_id="l3s007_b2_2",
        arm="B2",
        scenario_index=1,
        username="qa_pgo_l3_ab_diag",
        password="pw",
        phone="13700000007",
    )
    row: dict[str, object] = {}

    knowql_nexus_l3_ab._attach_subject_fields(
        row,
        subject,
        order_index=3,
        auth={"auth_mode": "register_token", "attempt": 2, "auth_user_id": "auth_abc"},
        cohort_mode="production_learner",
    )

    assert row["subject_id"] == "l3s007_b2_2"
    assert row["learner_username"] == "qa_pgo_l3_ab_diag"
    assert row["cohort_mode"] == "production_learner"
    assert row["auth_mode"] == "register_token"
    assert row["auth_attempt"] == 2
    assert row["auth_user_id"] == "auth_abc"


def test_l3_summary_requires_distinct_subjects_and_keeps_l2_safety() -> None:
    rows = [
        _row("A0", "initial", 1, "s-a0", "qa_a0", outcome_misses=2),
        _row("A0", "retest", 1, "s-a0", "qa_a0", outcome_misses=2),
        _row("B1", "initial", 2, "s-b1", "qa_b1", outcome_misses=2),
        _row("B1", "retest", 2, "s-b1", "qa_b1", outcome_misses=2),
        _row("B2", "initial", 3, "s-b2", "qa_b2", outcome_misses=2, pgo=True, g3=True, nba=True),
        _row("B2", "retest", 3, "s-b2", "qa_b2", outcome_misses=0, pgo=True, g3=True, nba=True, nba_applied=True),
    ]

    summary = knowql_nexus_l3_ab.summarize_l3_rows(
        rows,
        b3_rows=[],
        min_subjects_per_arm=1,
        min_b2_outcome_miss_reduction_lift=1.0,
    )

    assert summary["decision"]["status"] == "L3_COHORT_AB_GO"
    assert summary["cohort"]["subjects_by_arm"] == {"A0": 1, "B1": 1, "B2": 1}
    assert summary["cohort"]["distinct_learner_per_subject"] is True
    assert summary["comparison"]["b2_real_cohort_outcome_miss_reduction_lift_vs_b1"] == 2.0
    assert summary["decision"]["canonical_truth_written"] is False
    assert summary["decision"]["production_learner_claim_allowed"] is False

    duplicate = [dict(row) for row in rows]
    duplicate[-1]["learner_username"] = "qa_b1"
    blocked = knowql_nexus_l3_ab.summarize_l3_rows(
        duplicate,
        b3_rows=[],
        min_subjects_per_arm=1,
        min_b2_outcome_miss_reduction_lift=1.0,
    )

    assert blocked["decision"]["status"] == "L3_COHORT_AB_NO_GO"
    assert "duplicate_learner_detected" in blocked["decision"]["reasons"]


def _row(
    arm: str,
    phase: str,
    loop_index: int,
    subject_id: str,
    learner_username: str,
    *,
    outcome_misses: int,
    pgo: bool = False,
    g3: bool = False,
    nba: bool = False,
    nba_applied: bool = False,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "construction_grading_result": {
            "score_awarded": 0.5,
            "max_score": 1.0,
        }
    }
    if pgo:
        metadata["luban_case_rubric_pgo_shadow"] = {
            "shadow_status": "ok",
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "point_verdicts": {"hit": "hit"},
            "knowql_query": {"runtime_consumed": True, "fail_open": False},
        }
    if g3:
        metadata["pgo_grading_to_brain"] = {
            "writeback_count": 1,
            "canonical_truth_written": False,
            "claim_promotion_allowed": False,
            "scoring_point_map_readback": {"items_count": 1},
        }
        if nba:
            metadata["pgo_grading_to_brain"]["next_best_action"] = {
                "title": "先练采分点",
                "prescription_authority": "training_intent",
            }
    return {
        "arm": arm,
        "turn_phase": phase,
        "loop_index": loop_index,
        "subject_id": subject_id,
        "learner_username": learner_username,
        "ok": True,
        "duration_ms": 1000.0,
        "payload_bytes": 1000,
        "ttft_ms": 100.0,
        "first_result_ms": 500.0,
        "streaming_observed": True,
        "content_event_count": 1,
        "sealed_block_status": "not_exercised",
        "score_first_observed": True,
        "async_explanation_status": "not_exercised",
        "metadata": metadata,
        "nba_intervention_applied": nba_applied,
        "outcome_score_ratio": max(0.0, 1.0 - float(outcome_misses) / 2.0),
        "outcome_miss_count": outcome_misses,
    }
