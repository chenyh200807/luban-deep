from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load_script(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / file_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


production_default_gate = _load_script(
    "knowql_nexus_l5_production_default_gate",
    "run_luban_knowql_nexus_l5_production_default_gate.py",
)
canonical_truth_gate = _load_script(
    "knowql_nexus_l5_canonical_truth_gate",
    "run_luban_knowql_nexus_l5_canonical_truth_gate.py",
)


def test_l5_production_default_gate_blocks_without_signed_authorization() -> None:
    report = production_default_gate.build_l5_production_default_gate(
        l4_readiness=_l4_readiness_ready_but_blocked(),
    )

    assert report["schema"] == "knowql_nexus_l5_production_default_gate.v1"
    assert report["verdict"] == "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
    assert "signed_production_default_authorization_missing" in report["blockers"]
    assert report["decisions"]["production_default_allowed"] is False
    assert report["decisions"]["env_mutation_allowed"] is False
    assert report["decisions"]["published_registry_write_allowed"] is False
    assert report["decisions"]["remote_write_allowed"] is False
    assert report["safety"]["production_write_count"] == 0
    assert report["safety"]["official_score_write_count"] == 0
    assert report["not_exercised"] == [
        "production_default_flip",
        "env_mutation",
        "published_registry_write",
        "remote_write",
    ]


def test_l5_canonical_truth_gate_blocks_without_signed_authorization() -> None:
    report = canonical_truth_gate.build_l5_canonical_truth_gate(
        l4_readiness=_l4_readiness_ready_but_blocked(),
    )

    assert report["schema"] == "knowql_nexus_l5_canonical_truth_gate.v1"
    assert report["verdict"] == "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
    assert "signed_canonical_truth_authorization_missing" in report["blockers"]
    assert "same_point_real_retest_proof_missing" in report["blockers"]
    assert report["decisions"]["canonical_truth_write_allowed"] is False
    assert report["decisions"]["learner_memory_event_write_allowed"] is False
    assert report["decisions"]["remote_write_allowed"] is False
    assert report["safety"]["canonical_truth_write_count"] == 0
    assert report["safety"]["learner_memory_write_count"] == 0
    assert "teacher_final_or_certified_policy_required" in report["stop_conditions"]


def test_l5_gate_clis_write_blocked_reports(tmp_path: Path) -> None:
    l4_path = tmp_path / "l4.json"
    l4_path.write_text(json.dumps(_l4_readiness_ready_but_blocked(), ensure_ascii=False), encoding="utf-8")
    production_out = tmp_path / "production_default_gate.json"
    canonical_out = tmp_path / "canonical_truth_gate.json"

    production_exit = production_default_gate.main(["--l4-readiness", str(l4_path), "--output", str(production_out)])
    canonical_exit = canonical_truth_gate.main(["--l4-readiness", str(l4_path), "--output", str(canonical_out)])

    assert production_exit == 0
    assert canonical_exit == 0
    assert json.loads(production_out.read_text("utf-8"))["verdict"] == "BLOCKED_PENDING_SIGNED_AUTHORIZATION"
    assert json.loads(canonical_out.read_text("utf-8"))["verdict"] == "BLOCKED_PENDING_SIGNED_AUTHORIZATION"


def _l4_readiness_ready_but_blocked() -> dict[str, object]:
    return {
        "schema": "knowql_nexus_l4_authorization_readiness.v1",
        "verdict": "BLOCKED_FOR_PRODUCTION_AUTHORIZATION",
        "live_readback_status": "L4_LIVE_READBACK_READY",
        "production_authorization_status": "L4_PRODUCTION_AUTHORIZATION_BLOCKED",
        "claim_ceiling": {
            "authorized_scope": "test2_qa_operator_live_readback",
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
        "production_blockers": [
            "production_default_authorization_missing",
            "canonical_truth_authorization_missing",
        ],
        "safety_violations": [],
    }
