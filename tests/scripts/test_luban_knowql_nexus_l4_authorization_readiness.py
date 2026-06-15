from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "knowql_nexus_l4_readiness",
    REPO / "scripts" / "run_luban_knowql_nexus_l4_authorization_readiness.py",
)
knowql_nexus_l4_readiness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(knowql_nexus_l4_readiness)


def test_l4_readiness_accepts_l1_l2_l3_go_but_blocks_production_authorization() -> None:
    report = knowql_nexus_l4_readiness.build_l4_authorization_readiness(
        l1_summary=_l1_go_summary(),
        l2_summary=_l2_go_summary(),
        l3_summary=_l3_go_summary(),
    )

    assert report["schema"] == "knowql_nexus_l4_authorization_readiness.v1"
    assert report["verdict"] == "BLOCKED_FOR_PRODUCTION_AUTHORIZATION"
    assert report["live_readback_status"] == "L4_LIVE_READBACK_READY"
    assert report["production_authorization_status"] == "L4_PRODUCTION_AUTHORIZATION_BLOCKED"
    assert report["gates"]["l1_shadow_performance"]["passed"] is True
    assert report["gates"]["l2_learning_efficiency"]["passed"] is True
    assert report["gates"]["l3_authorized_cohort"]["passed"] is True
    assert "real_student_cohort_authorization_missing" in report["production_blockers"]
    assert "privacy_consent_boundary_missing" in report["production_blockers"]
    assert "sample_size_plan_missing" in report["production_blockers"]
    assert "official_score_authorization_missing" in report["production_blockers"]
    assert "published_registry_authorization_missing" in report["production_blockers"]
    assert "canonical_truth_authorization_missing" in report["production_blockers"]
    assert report["decisions"]["live_readback_claim_allowed"] is True
    assert report["decisions"]["real_student_efficacy_claim_allowed"] is False
    assert report["decisions"]["production_default_allowed"] is False
    assert report["decisions"]["official_score_allowed"] is False
    assert report["decisions"]["published_registry_allowed"] is False
    assert report["decisions"]["canonical_truth_write_allowed"] is False
    assert report["claim_ceiling"]["authorized_scope"] == "test2_qa_operator_live_readback"
    assert report["claim_ceiling"]["real_student_efficacy_claim_allowed"] is False
    assert "production_default_flip" in report["blocked_actions"]
    assert "official_score_write" in report["blocked_actions"]
    assert "published_registry_write" in report["blocked_actions"]
    assert "canonical_truth_write" in report["blocked_actions"]
    assert "any canonical/official/unsafe write appears before signed authorization" in report["stop_conditions"]
    assert report["negative_evidence"][0]["kind"] == "production_blocker"
    assert report["safety"]["canonical_truth_write_count"] == 0
    assert report["safety"]["official_score_write_count"] == 0
    assert report["safety"]["unsafe_write_signal_count"] == 0


def test_l4_readiness_fails_closed_on_any_write_signal() -> None:
    l3_summary = _l3_go_summary()
    l3_summary["safety"]["canonical_truth_write_count"] = 1

    report = knowql_nexus_l4_readiness.build_l4_authorization_readiness(
        l1_summary=_l1_go_summary(),
        l2_summary=_l2_go_summary(),
        l3_summary=l3_summary,
    )

    assert report["verdict"] == "NO_GO_SAFETY_INVARIANT"
    assert report["live_readback_status"] == "L4_LIVE_READBACK_BLOCKED"
    assert "l3_summary:canonical_truth_write_count_nonzero" in report["safety_violations"]
    assert any(
        item["kind"] == "safety_violation" and item["code"] == "l3_summary:canonical_truth_write_count_nonzero"
        for item in report["negative_evidence"]
    )
    assert report["decisions"]["live_readback_claim_allowed"] is False
    assert report["decisions"]["canonical_truth_write_allowed"] is False


def test_l4_readiness_real_student_evidence_is_not_enough_without_signed_authorization() -> None:
    report = knowql_nexus_l4_readiness.build_l4_authorization_readiness(
        l1_summary=_l1_go_summary(),
        l2_summary=_l2_go_summary(),
        l3_summary=_l3_go_summary(),
        real_student_cohort_evidence={
            "schema": "knowql_nexus_real_student_cohort_evidence.v1",
            "cohort_source": "consented_pilot",
            "privacy_consent_boundary": "pilot_terms_2026_06",
            "sample_size_plan": {"min_subjects_per_arm": 30},
        },
    )

    assert report["gates"]["real_student_cohort_evidence"]["passed"] is True
    assert "real_student_cohort_authorization_missing" in report["production_blockers"]
    assert "privacy_consent_boundary_missing" not in report["production_blockers"]
    assert "sample_size_plan_missing" not in report["production_blockers"]
    assert report["decisions"]["real_student_efficacy_claim_allowed"] is False
    assert report["decisions"]["production_default_allowed"] is False


def test_l4_readiness_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    l1_path = tmp_path / "l1_summary.json"
    l2_path = tmp_path / "l2_summary.json"
    l3_path = tmp_path / "l3_summary.json"
    output_path = tmp_path / "l4_authorization_readiness.json"
    markdown_path = tmp_path / "l4_authorization_readiness.md"
    summary_path = tmp_path / "summary.json"
    negative_evidence_path = tmp_path / "negative_evidence.jsonl"
    l1_path.write_text(json.dumps(_l1_go_summary(), ensure_ascii=False), encoding="utf-8")
    l2_path.write_text(json.dumps(_l2_go_summary(), ensure_ascii=False), encoding="utf-8")
    l3_path.write_text(json.dumps(_l3_go_summary(), ensure_ascii=False), encoding="utf-8")

    exit_code = knowql_nexus_l4_readiness.main(
        [
            "--l1-summary",
            str(l1_path),
            "--l2-summary",
            str(l2_path),
            "--l3-summary",
            str(l3_path),
            "--output",
            str(output_path),
            "--markdown-output",
            str(markdown_path),
            "--summary-output",
            str(summary_path),
            "--negative-evidence-output",
            str(negative_evidence_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text("utf-8"))
    summary = json.loads(summary_path.read_text("utf-8"))
    negative_evidence = [json.loads(line) for line in negative_evidence_path.read_text("utf-8").splitlines()]
    markdown = markdown_path.read_text("utf-8")
    assert payload["verdict"] == "BLOCKED_FOR_PRODUCTION_AUTHORIZATION"
    assert payload["summary"]["production_blocker_count"] >= 6
    assert summary["verdict"] == "BLOCKED_FOR_PRODUCTION_AUTHORIZATION"
    assert negative_evidence
    assert "canonical_truth_write_allowed=false" in markdown


def _l1_go_summary() -> dict[str, object]:
    return {
        "decision": {
            "status": "L1_SHADOW_AB_GO",
            "canonical_truth_written": False,
            "official_score_written": False,
            "reasons": [],
        },
        "comparison": {
            "completed_pairs": 30,
            "min_pairs": 30,
            "p95_latency_delta_pct": 0.020807,
        },
        "safety": {
            "a_pgo_shadow_present_count": 0,
            "b_pgo_shadow_effective_count": 30,
            "b_knowql_runtime_consumed_count": 30,
            "pgo_g3_preview_readback_count": 30,
            "canonical_truth_write_count": 0,
            "official_score_write_count": 0,
            "unsafe_write_signal_count": 0,
        },
    }


def _l2_go_summary() -> dict[str, object]:
    return {
        "decision": {
            "status": "L2_LEARNING_AB_GO",
            "safety_status": "L2_SAFETY_GO",
            "effect_status": "L2_EFFECT_POSITIVE",
            "canonical_truth_written": False,
            "official_score_written": False,
            "reasons": [],
        },
        "comparison": {
            "completed_loops": {"A0": 10, "B1": 10, "B2": 10},
            "b2_outcome_miss_reduction_lift_vs_b1": 5.0,
            "b2_p95_latency_delta_pct_vs_b1": 49.752505,
            "b2_payload_delta_pct_vs_b1": 10.001534,
        },
        "safety": {
            "a0_pgo_shadow_present_count": 0,
            "b1_pgo_shadow_present_count": 0,
            "b2_pgo_shadow_effective_count": 20,
            "b2_knowql_runtime_consumed_count": 20,
            "b2_g3_preview_readback_count": 20,
            "b2_nba_intervention_applied_count": 10,
            "canonical_truth_write_count": 0,
            "official_score_write_count": 0,
            "unsafe_write_signal_count": 0,
        },
    }


def _l3_go_summary() -> dict[str, object]:
    return {
        "decision": {
            "status": "L3_COHORT_AB_GO",
            "safety_status": "L3_SAFETY_GO",
            "effect_status": "L3_EFFECT_POSITIVE",
            "canonical_truth_written": False,
            "official_score_written": False,
            "human_learner_claim_allowed": False,
            "production_learner_claim_allowed": False,
            "reasons": [],
        },
        "cohort": {
            "cohort_mode": "authorized_qa_operator",
            "subjects_by_arm": {"A0": 5, "B1": 5, "B2": 5},
            "subject_count": 15,
            "learner_count": 15,
            "distinct_learner_per_subject": True,
            "human_learner_claim_allowed": False,
            "production_learner_claim_allowed": False,
        },
        "comparison": {
            "completed_loops": {"A0": 5, "B1": 5, "B2": 5},
            "b2_real_cohort_outcome_miss_reduction_lift_vs_b1": 5.0,
            "b2_p95_latency_delta_pct_vs_b1": -44.902579,
            "b2_payload_delta_pct_vs_b1": 9.982498,
            "min_subjects_per_arm": 5,
        },
        "safety": {
            "a0_pgo_shadow_present_count": 0,
            "b1_pgo_shadow_present_count": 0,
            "b2_pgo_shadow_effective_count": 10,
            "b2_knowql_runtime_consumed_count": 10,
            "b2_g3_preview_readback_count": 10,
            "b2_nba_intervention_applied_count": 5,
            "canonical_truth_write_count": 0,
            "official_score_write_count": 0,
            "unsafe_write_signal_count": 0,
        },
    }
