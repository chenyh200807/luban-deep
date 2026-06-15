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


def test_l41_hardening_consumes_auxiliary_gates_and_preserves_claim_ceiling() -> None:
    report = knowql_nexus_l4_readiness.build_l4_authorization_readiness(
        l1_summary=_l1_go_summary(),
        l2_summary=_l2_go_summary(),
        l3_summary=_l3_go_summary(),
        pgo_supply_verification=_pgo_supply_ok(),
        stage5_canary_report=_stage5_canary_ok(),
        canonical_truth_policy_matrix=_canonical_truth_policy_matrix_ok(),
        deployment_probe=_deployment_probe_ok(),
        negative_summaries=[
            {
                "source_path": "artifacts/luban_grading_artifacts/knowql_nexus_l2_learning_ab_bad/summary.json",
                "decision": {"status": "L2_LEARNING_AB_NO_GO", "reasons": ["b2_g3_preview_missing"]},
            },
            {
                "source_path": "artifacts/luban_grading_artifacts/knowql_nexus_l3_cohort_ab_bad/summary.json",
                "decision": {"status": "L3_COHORT_AB_NO_GO", "reasons": ["duplicate_learner_detected"]},
            },
        ],
    )

    assert report["gates"]["pgo_supply_verification"]["passed"] is True
    assert report["gates"]["stage5_canary"]["passed"] is True
    assert report["gates"]["canonical_truth_policy_matrix"]["passed"] is True
    assert report["gates"]["deployment_lineage"]["passed"] is True
    assert report["source_manifest"]["inputs"]["pgo_supply_verification"]["schema"] == "luban_pgo_runtime_supply_verification.v1"
    assert report["deployment_probe"]["host_sha"] == "16dbb13dcc2be1ed5ac40feec7682283fd098620"
    assert report["deployment_probe"]["container_sha"] == "16dbb13dcc2be1ed5ac40feec7682283fd098620"
    assert any(item["kind"] == "historical_negative_run" and item["code"] == "L2_LEARNING_AB_NO_GO" for item in report["negative_evidence"])
    assert any(item["kind"] == "historical_negative_run" and item["code"] == "L3_COHORT_AB_NO_GO" for item in report["negative_evidence"])
    assert report["decisions"]["production_default_allowed"] is False
    assert report["decisions"]["canonical_truth_write_allowed"] is False
    assert report["production_authorization_status"] == "L4_PRODUCTION_AUTHORIZATION_BLOCKED"


def test_l41_stage5_human_boundary_blocker_blocks_production_authorization() -> None:
    stage5 = _stage5_canary_ok()
    stage5["over_credit"]["human_boundary"]["broad_flip_blocker"] = True

    report = knowql_nexus_l4_readiness.build_l4_authorization_readiness(
        l1_summary=_l1_go_summary(),
        l2_summary=_l2_go_summary(),
        l3_summary=_l3_go_summary(),
        pgo_supply_verification=_pgo_supply_ok(),
        stage5_canary_report=stage5,
        canonical_truth_policy_matrix=_canonical_truth_policy_matrix_ok(),
        deployment_probe=_deployment_probe_ok(),
    )

    assert report["gates"]["stage5_canary"]["passed"] is False
    assert "stage5_human_gold_over_credit_blocker" in report["production_blockers"]
    assert any(
        item["kind"] == "gate_not_passed" and item["code"] == "stage5_canary"
        for item in report["negative_evidence"]
    )


def test_l41_cli_writes_source_manifest_and_deployment_probe(tmp_path: Path) -> None:
    l1_path = tmp_path / "l1_summary.json"
    l2_path = tmp_path / "l2_summary.json"
    l3_path = tmp_path / "l3_summary.json"
    pgo_supply_path = tmp_path / "pgo_supply_verification.json"
    stage5_path = tmp_path / "stage5_canary.json"
    canonical_policy_path = tmp_path / "canonical_truth_policy_matrix.json"
    deployment_probe_path = tmp_path / "deployment_probe_input.json"
    negative_path = tmp_path / "negative_summary.json"
    output_path = tmp_path / "authorization_readiness.json"
    source_manifest_path = tmp_path / "source_manifest.json"
    deployment_probe_output_path = tmp_path / "deployment_probe.json"
    l1_path.write_text(json.dumps(_l1_go_summary(), ensure_ascii=False), encoding="utf-8")
    l2_path.write_text(json.dumps(_l2_go_summary(), ensure_ascii=False), encoding="utf-8")
    l3_path.write_text(json.dumps(_l3_go_summary(), ensure_ascii=False), encoding="utf-8")
    pgo_supply_path.write_text(json.dumps(_pgo_supply_ok(), ensure_ascii=False), encoding="utf-8")
    stage5_path.write_text(json.dumps(_stage5_canary_ok(), ensure_ascii=False), encoding="utf-8")
    canonical_policy_path.write_text(json.dumps(_canonical_truth_policy_matrix_ok(), ensure_ascii=False), encoding="utf-8")
    deployment_probe_path.write_text(json.dumps(_deployment_probe_ok(), ensure_ascii=False), encoding="utf-8")
    negative_path.write_text(
        json.dumps({"decision": {"status": "L2_SAFETY_NO_GO", "reasons": ["transport_error"]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = knowql_nexus_l4_readiness.main(
        [
            "--l1-summary",
            str(l1_path),
            "--l2-summary",
            str(l2_path),
            "--l3-summary",
            str(l3_path),
            "--pgo-supply-verification",
            str(pgo_supply_path),
            "--stage5-canary-report",
            str(stage5_path),
            "--canonical-truth-policy-matrix",
            str(canonical_policy_path),
            "--deployment-probe",
            str(deployment_probe_path),
            "--negative-summary",
            str(negative_path),
            "--output",
            str(output_path),
            "--source-manifest-output",
            str(source_manifest_path),
            "--deployment-probe-output",
            str(deployment_probe_output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text("utf-8"))
    source_manifest = json.loads(source_manifest_path.read_text("utf-8"))
    deployment_probe = json.loads(deployment_probe_output_path.read_text("utf-8"))
    assert payload["gates"]["deployment_lineage"]["passed"] is True
    assert source_manifest["inputs"]["stage5_canary_report"]["sha256"]
    assert deployment_probe["public_endpoints"]["healthz"]["status_code"] == 200


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


def _pgo_supply_ok() -> dict[str, object]:
    return {
        "schema": "luban_pgo_runtime_supply_verification.v1",
        "status": "ok",
        "blockers": [],
        "checks": {
            "content_hash_match": True,
            "canonical_pointer_match": True,
            "production_default_off": True,
            "published_false": True,
            "no_minted_scores": True,
        },
        "manifest": {
            "namespace": "case_rubric_scored_pgo",
            "status": "release_candidate",
            "published": False,
            "production_default": "off",
            "content_hash": "sha256:test",
        },
    }


def _stage5_canary_ok() -> dict[str, object]:
    return {
        "schema": "luban_pgo_stage5_canary_gate.v1",
        "status": "qa_operator_canary_go",
        "blockers": [],
        "production_default_flip_allowed": False,
        "canonical_write_allowed": False,
        "remote_write_allowed": False,
        "cohort_gate": {"allowed": True, "invalid_cohort_ids": []},
        "runtime_supply": {"status": "ok"},
        "worker_restart_probe": {
            "fresh_process_verifier": {"status": "ok"},
            "runtime_loader": {"status": "ok"},
        },
        "over_credit": {
            "gate_overcredit_new_le_legacy": True,
            "human_boundary": {"broad_flip_blocker": False},
        },
    }


def _canonical_truth_policy_matrix_ok() -> dict[str, object]:
    return {
        "schema": "luban_canonical_truth_policy_matrix.v1",
        "status": "ok",
        "policy_source": "deeptutor/services/learner_state/canonical_truth_policy.py:canonical_truth_promotion_decision",
        "cases": {
            "trusted_stable_teacher_final": {"allowed": True, "reason": "trusted_adjudication_authorized"},
            "preview_candidate": {"allowed": False, "reason": "stable_learner_claim_required"},
            "no_adjudication": {"allowed": False, "reason": "trusted_adjudication_required"},
        },
        "canonical_write_allowed": False,
    }


def _deployment_probe_ok() -> dict[str, object]:
    return {
        "schema": "knowql_nexus_deployment_probe.v1",
        "status": "ok",
        "public_base_url": "https://test2.yousenjiaoyu.com",
        "host_sha": "16dbb13dcc2be1ed5ac40feec7682283fd098620",
        "container_sha": "16dbb13dcc2be1ed5ac40feec7682283fd098620",
        "sha_match": True,
        "public_endpoints": {
            "healthz": {"status_code": 200},
            "readyz": {"status_code": 200, "ready": True},
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
