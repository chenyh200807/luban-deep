from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "knowql_nexus_l5_signed_authorization_package",
    REPO / "scripts" / "run_luban_knowql_nexus_l5_signed_authorization_package.py",
)
signed_authorization_package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(signed_authorization_package)


def test_l5_signed_authorization_package_is_unsigned_and_no_write() -> None:
    package = signed_authorization_package.build_signed_authorization_package(
        l4_readiness=_l4_readiness_with_resolved_stage5(),
        production_default_gate=_l5_production_default_blocked(),
        canonical_truth_gate=_l5_canonical_truth_blocked(),
    )

    assert package["schema"] == "knowql_nexus_l5_signed_authorization_package.v1"
    assert package["verdict"] == "READY_FOR_HUMAN_SIGNATURE"
    assert package["classification"]["authorization_package_only"] is True
    assert package["classification"]["no_write"] is True
    assert package["safety"]["production_write_count"] == 0
    assert package["safety"]["canonical_truth_write_count"] == 0
    assert package["safety"]["remote_write_count"] == 0
    assert package["authorization_forms"]["consented_pilot"]["schema"] == (
        "knowql_nexus_l5_consented_pilot_authorization.v1"
    )
    assert package["authorization_forms"]["consented_pilot"]["authorization_decision"]["signed_authorization"] is False
    assert package["authorization_forms"]["consented_pilot"]["authorization_decision"][
        "real_student_cohort_authorized"
    ] is False
    assert package["authorization_forms"]["consented_pilot"]["scope"]["minimum_subjects_per_arm"] == 30
    assert package["authorization_forms"]["consented_pilot"]["scope"]["production_default_after_signature"] is False
    assert package["authorization_forms"]["production_default"]["schema"] == (
        "knowql_nexus_l5_production_default_authorization.v1"
    )
    assert package["authorization_forms"]["production_default"]["authorization_decision"]["signed_authorization"] is False
    assert package["authorization_forms"]["production_default"]["authorization_decision"]["production_default_authorized"] is False
    assert package["authorization_forms"]["canonical_truth"]["schema"] == (
        "knowql_nexus_l5_canonical_truth_authorization.v1"
    )
    assert package["authorization_forms"]["canonical_truth"]["authorization_decision"]["signed_authorization"] is False
    assert package["authorization_forms"]["canonical_truth"]["authorization_decision"]["canonical_truth_authorized"] is False
    assert "production_default_flip" in package["blocked_actions"]
    assert "canonical_truth_write" in package["blocked_actions"]


def test_l5_signed_authorization_package_stays_blocked_when_stage5_unresolved() -> None:
    package = signed_authorization_package.build_signed_authorization_package(
        l4_readiness=_l4_readiness_with_unresolved_stage5(),
        production_default_gate=_l5_production_default_blocked(),
        canonical_truth_gate=_l5_canonical_truth_blocked(),
    )

    assert package["verdict"] == "BLOCKED_BEFORE_SIGNATURE"
    assert "stage5_human_gold_over_credit_blocker" in package["blockers"]
    assert package["authorization_forms"]["production_default"]["authorization_decision"]["signed_authorization"] is False
    assert package["authorization_forms"]["canonical_truth"]["authorization_decision"]["signed_authorization"] is False


def test_l5_signed_authorization_package_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    l4_path = tmp_path / "l4.json"
    production_gate_path = tmp_path / "production_gate.json"
    canonical_gate_path = tmp_path / "canonical_gate.json"
    output_path = tmp_path / "signed_authorization_package.json"
    markdown_path = tmp_path / "signed_authorization_package.md"
    l4_path.write_text(json.dumps(_l4_readiness_with_resolved_stage5(), ensure_ascii=False), encoding="utf-8")
    production_gate_path.write_text(json.dumps(_l5_production_default_blocked(), ensure_ascii=False), encoding="utf-8")
    canonical_gate_path.write_text(json.dumps(_l5_canonical_truth_blocked(), ensure_ascii=False), encoding="utf-8")

    exit_code = signed_authorization_package.main(
        [
            "--l4-readiness",
            str(l4_path),
            "--production-default-gate",
            str(production_gate_path),
            "--canonical-truth-gate",
            str(canonical_gate_path),
            "--output",
            str(output_path),
            "--markdown-output",
            str(markdown_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text("utf-8"))
    markdown = markdown_path.read_text("utf-8")
    assert payload["verdict"] == "READY_FOR_HUMAN_SIGNATURE"
    assert "signed_authorization=false" in markdown
    assert "real_student_cohort_authorized=false" in markdown
    assert "production_default_authorized=false" in markdown
    assert "canonical_truth_authorized=false" in markdown


def _l4_readiness_with_resolved_stage5() -> dict[str, object]:
    return {
        "schema": "knowql_nexus_l4_authorization_readiness.v1",
        "verdict": "BLOCKED_FOR_PRODUCTION_AUTHORIZATION",
        "live_readback_status": "L4_LIVE_READBACK_READY",
        "production_authorization_status": "L4_PRODUCTION_AUTHORIZATION_BLOCKED",
        "production_blockers": [
            "production_default_authorization_missing",
            "canonical_truth_authorization_missing",
            "official_score_authorization_missing",
            "published_registry_authorization_missing",
        ],
        "summary": {
            "canonical_truth_write_count": 0,
            "official_score_write_count": 0,
            "production_write_count": 0,
            "unsafe_write_signal_count": 0,
        },
        "source_manifest": {"inputs": {"stage5_canary_report": {"sha256": "abc"}}},
        "deployment_probe": {"host_sha": "sha", "container_sha": "sha"},
    }


def _l4_readiness_with_unresolved_stage5() -> dict[str, object]:
    payload = _l4_readiness_with_resolved_stage5()
    payload["production_blockers"] = [
        "stage5_human_gold_over_credit_blocker",
        "stage5_canary_not_ready",
    ]
    return payload


def _l5_production_default_blocked() -> dict[str, object]:
    return {
        "schema": "knowql_nexus_l5_production_default_gate.v1",
        "verdict": "BLOCKED_PENDING_SIGNED_AUTHORIZATION",
        "blockers": ["signed_production_default_authorization_missing"],
        "decisions": {
            "production_default_allowed": False,
            "env_mutation_allowed": False,
            "published_registry_write_allowed": False,
            "official_score_allowed": False,
            "remote_write_allowed": False,
        },
        "safety": {
            "production_write_count": 0,
            "official_score_write_count": 0,
            "canonical_truth_write_count": 0,
            "remote_write_count": 0,
        },
    }


def _l5_canonical_truth_blocked() -> dict[str, object]:
    return {
        "schema": "knowql_nexus_l5_canonical_truth_gate.v1",
        "verdict": "BLOCKED_PENDING_SIGNED_AUTHORIZATION",
        "blockers": ["signed_canonical_truth_authorization_missing"],
        "decisions": {
            "canonical_truth_write_allowed": False,
            "learner_memory_event_write_allowed": False,
            "read_model_write_allowed": False,
            "remote_write_allowed": False,
        },
        "safety": {
            "canonical_truth_write_count": 0,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "remote_write_count": 0,
        },
    }
