from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "knowql_nexus_l5_consented_pilot_gate",
    REPO / "scripts" / "run_luban_knowql_nexus_l5_consented_pilot_gate.py",
)
consented_pilot_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consented_pilot_gate)


def test_l5_consented_pilot_gate_blocks_without_evidence_or_signature() -> None:
    report = consented_pilot_gate.build_l5_consented_pilot_gate(
        l4_readiness=_l4_readiness_live_ready(),
    )

    assert report["schema"] == "knowql_nexus_l5_consented_pilot_gate.v1"
    assert report["verdict"] == "BLOCKED_PENDING_CONSENTED_PILOT_AUTHORIZATION"
    assert "real_student_cohort_evidence_missing" in report["blockers"]
    assert "signed_consented_pilot_authorization_missing" in report["blockers"]
    assert report["decisions"]["consented_pilot_ab_allowed"] is False
    assert report["decisions"]["production_default_allowed"] is False
    assert report["decisions"]["official_score_allowed"] is False
    assert report["decisions"]["canonical_truth_write_allowed"] is False
    assert report["safety"]["canonical_truth_write_count"] == 0
    assert report["safety"]["official_score_write_count"] == 0


def test_l5_consented_pilot_gate_requires_signed_authorization_even_with_evidence() -> None:
    report = consented_pilot_gate.build_l5_consented_pilot_gate(
        l4_readiness=_l4_readiness_live_ready(),
        real_student_cohort_evidence=_real_student_evidence(),
        authorization_package=_unsigned_pilot_authorization(),
    )

    assert report["verdict"] == "BLOCKED_PENDING_CONSENTED_PILOT_AUTHORIZATION"
    assert "signed_consented_pilot_authorization_missing" in report["blockers"]
    assert "privacy_consent_boundary_missing" not in report["blockers"]
    assert "sample_size_plan_missing" not in report["blockers"]
    assert report["decisions"]["consented_pilot_ab_allowed"] is False


def test_l5_consented_pilot_gate_can_ready_only_pilot_scope() -> None:
    report = consented_pilot_gate.build_l5_consented_pilot_gate(
        l4_readiness=_l4_readiness_live_ready(),
        real_student_cohort_evidence=_real_student_evidence(),
        authorization_package=_signed_pilot_authorization(),
    )

    assert report["verdict"] == "READY_FOR_CONSENTED_PILOT_EXECUTION"
    assert report["blockers"] == []
    assert report["decisions"]["consented_pilot_ab_allowed"] is True
    assert report["decisions"]["production_default_allowed"] is False
    assert report["decisions"]["published_registry_write_allowed"] is False
    assert report["decisions"]["official_score_allowed"] is False
    assert report["decisions"]["canonical_truth_write_allowed"] is False
    assert report["decisions"]["remote_write_allowed"] is False
    assert report["not_exercised"] == [
        "production_default_flip",
        "official_score_write",
        "published_registry_write",
        "canonical_truth_write",
        "remote_write",
    ]


def test_l5_consented_pilot_gate_cli_writes_report(tmp_path: Path) -> None:
    l4_path = tmp_path / "l4.json"
    evidence_path = tmp_path / "real_student_evidence.json"
    auth_path = tmp_path / "pilot_auth.json"
    out_path = tmp_path / "l5_consented_pilot_gate.json"
    l4_path.write_text(json.dumps(_l4_readiness_live_ready(), ensure_ascii=False), encoding="utf-8")
    evidence_path.write_text(json.dumps(_real_student_evidence(), ensure_ascii=False), encoding="utf-8")
    auth_path.write_text(json.dumps(_signed_pilot_authorization(), ensure_ascii=False), encoding="utf-8")

    exit_code = consented_pilot_gate.main(
        [
            "--l4-readiness",
            str(l4_path),
            "--real-student-cohort-evidence",
            str(evidence_path),
            "--authorization-package",
            str(auth_path),
            "--output",
            str(out_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(out_path.read_text("utf-8"))
    assert payload["verdict"] == "READY_FOR_CONSENTED_PILOT_EXECUTION"
    assert payload["decisions"]["consented_pilot_ab_allowed"] is True


def _l4_readiness_live_ready() -> dict[str, object]:
    return {
        "schema": "knowql_nexus_l4_authorization_readiness.v1",
        "verdict": "BLOCKED_FOR_PRODUCTION_AUTHORIZATION",
        "live_readback_status": "L4_LIVE_READBACK_READY",
        "production_authorization_status": "L4_PRODUCTION_AUTHORIZATION_BLOCKED",
        "production_blockers": [
            "real_student_cohort_authorization_missing",
            "privacy_consent_boundary_missing",
            "sample_size_plan_missing",
            "production_default_authorization_missing",
            "official_score_authorization_missing",
            "published_registry_authorization_missing",
            "canonical_truth_authorization_missing",
        ],
        "claim_ceiling": {
            "live_readback_claim_allowed": True,
            "real_student_efficacy_claim_allowed": False,
            "production_default_allowed": False,
            "official_score_allowed": False,
            "published_registry_allowed": False,
            "canonical_truth_write_allowed": False,
        },
        "summary": {
            "canonical_truth_write_count": 0,
            "official_score_write_count": 0,
            "production_write_count": 0,
            "unsafe_write_signal_count": 0,
        },
        "safety_violations": [],
    }


def _real_student_evidence() -> dict[str, object]:
    return {
        "schema": "knowql_nexus_real_student_cohort_evidence.v1",
        "cohort_source": "consented_luban_beta_students",
        "privacy_consent_boundary": "explicit opt-in, study-only analytics, reversible withdrawal",
        "sample_size_plan": {
            "min_subjects_per_arm": 30,
            "arms": ["A0", "B1", "B2"],
            "randomization_unit": "learner",
        },
        "exclusions": ["no minors without guardian consent", "no production default"],
    }


def _unsigned_pilot_authorization() -> dict[str, object]:
    payload = _signed_pilot_authorization()
    decision = payload["authorization_decision"]
    decision["signed_authorization"] = False
    return payload


def _signed_pilot_authorization() -> dict[str, object]:
    return {
        "schema": "knowql_nexus_l5_consented_pilot_authorization.v1",
        "authorization_decision": {
            "signed_authorization": True,
            "real_student_cohort_authorized": True,
            "privacy_consent_authorized": True,
            "sample_size_plan_authorized": True,
            "qa_operator_to_real_student_transition_authorized": True,
            "production_default_authorized": False,
            "official_score_authorized": False,
            "published_registry_authorized": False,
            "canonical_truth_authorized": False,
            "remote_write_authorized": False,
        },
        "signer_roles": [
            "product_owner",
            "privacy_or_data_governance_owner",
            "learning_science_owner",
        ],
    }
