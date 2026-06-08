from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/audit_luban_grading_to_brain_current_gap.py"


def test_current_gap_audit_outputs_s1_s12_matrix(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path)],
        cwd=REPO,
        check=True,
    )

    matrix = json.loads((tmp_path / "coverage_matrix.json").read_text(encoding="utf-8"))
    scenarios = matrix["scenarios"]
    assert [row["id"] for row in scenarios] == [f"S{i}" for i in range(1, 13)]
    assert all(row["evidence_refs"] for row in scenarios)
    assert all(row["status"] in {"done", "partial", "blocker"} for row in scenarios)

    gaps = matrix["remaining_gates"]
    assert gaps["production_default"] == "gated_authorization_required"
    assert gaps["canonical_learner_truth_write"] == "gated_authorization_required"
    assert gaps["published_registry"] == "gated_authorization_required"
    assert gaps["remote_or_db_write"] == "gated_authorization_required"

    assert matrix["quality_gates"]["fp"] == 0
    assert matrix["quality_gates"]["source_mismatch"] == 0
    assert matrix["quality_gates"]["production_write"] == 0
    assert matrix["single_authority"]["no_second_learner_memory"] is True
    assert (tmp_path / "FINDING_grading_to_brain_current_gap_audit.md").exists()


def test_current_gap_audit_outputs_authorization_gate_decision_package(
    tmp_path: Path,
) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path)],
        cwd=REPO,
        check=True,
    )

    package = json.loads(
        (tmp_path / "authorization_gate_decision_package.json").read_text(
            encoding="utf-8"
        )
    )
    assert package["scope"] == "read_only_authorization_decision_package"
    assert package["production_write_count"] == 0
    assert package["canonical_truth_written"] is False

    gates = package["gates"]
    assert set(gates) == {
        "G1_limited_production_default",
        "G2_broad_production_default",
        "G3_published_registry",
        "G4_canonical_learner_truth_write",
        "G5_remote_or_db_write",
        "G6_real_wechat_package_page_automation",
    }
    assert gates["G1_limited_production_default"]["recommended_next"] is True
    assert gates["G2_broad_production_default"]["recommended_next"] is False
    assert gates["G4_canonical_learner_truth_write"]["promotion_path"] == (
        "teacher_final_plus_real_retest_only"
    )
    assert all(
        gate["without_authorization"] == "decision_package_only"
        for gate in gates.values()
    )
    assert all(gate["evidence_refs"] for gate in gates.values())
    assert package["single_authority"]["no_second_grading_truth"] is True
    assert package["single_authority"]["no_second_learner_truth"] is True
    assert (tmp_path / "AUTHORIZATION_GATES_grading_to_brain.md").exists()


def test_current_gap_audit_outputs_g1_limited_default_preflight(
    tmp_path: Path,
) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path)],
        cwd=REPO,
        check=True,
    )

    preflight = json.loads(
        (tmp_path / "G1_LIMITED_DEFAULT_PREFLIGHT.json").read_text(
            encoding="utf-8"
        )
    )
    assert preflight["gate_id"] == "G1_limited_production_default"
    assert preflight["scope"] == "read_only_pre_authorization_preflight"
    assert preflight["verdict"] == "ready_for_user_authorization"
    assert preflight["execution_mode"] == "read_only_no_flip"
    assert preflight["without_authorization"] == "decision_package_only"
    assert preflight["allowed_scope_after_authorization"] == (
        "qa_/operator_ cohort only"
    )

    assert preflight["production_write_count"] == 0
    assert preflight["canonical_truth_written"] is False
    assert preflight["remote_write_count"] == 0
    assert preflight["published_registry_executed"] is False

    assert preflight["preconditions"]["m19c_limited_default_flip"] == "GO"
    assert preflight["preconditions"]["m19d_soak_verdict"] == "GO"
    assert preflight["preconditions"]["rollback_readiness"] is True
    assert preflight["preconditions"]["broad_default"] == "NO-GO"
    assert preflight["preconditions"]["canonical_learner_truth_write"] == "NO-GO"
    assert all(preflight["evidence_ok"].values())
    assert preflight["single_authority"]["no_second_grading_truth"] is True
    assert preflight["single_authority"]["no_second_learner_truth"] is True
    assert (tmp_path / "G1_LIMITED_DEFAULT_PREFLIGHT.md").exists()


def test_current_gap_audit_outputs_explicit_loop_completion_audit(
    tmp_path: Path,
) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path)],
        cwd=REPO,
        check=True,
    )

    audit = json.loads((tmp_path / "completion_audit.json").read_text(encoding="utf-8"))
    requirements = audit["requirements"]
    assert [row["id"] for row in requirements] == [f"R{i}" for i in range(1, 8)]
    assert all(row["evidence_refs"] for row in requirements)
    assert all(row["evidence_ok"] for row in requirements)

    by_id = {row["id"]: row for row in requirements}
    assert by_id["R1"]["status"] == "done"
    assert set(by_id["R1"]["required_fields"]) == {
        "point_id",
        "knowledge_point",
        "policy_type",
        "hit",
        "score",
        "max_score",
        "mistake_type",
        "evidence_span",
        "required_term",
        "high_risk_review",
    }
    assert by_id["R4"]["pcp_role"] == "read_only_feedback_to_grading"
    assert by_id["R5"]["promotion_path"] == "teacher_final_only"
    assert by_id["R6"]["promotion_path"] == "real_retest_only"
    assert by_id["R7"]["authority"] == "Learning Brain read model"
    assert by_id["R7"]["empty_spin_prevented"] is True

    assert audit["summary"]["done"] >= 6
    assert audit["summary"]["authorization_gated"] >= 1
    assert audit["single_authority"]["no_second_mastery"] is True
    assert (tmp_path / "COMPLETION_AUDIT_grading_to_brain.md").exists()


def test_current_gap_audit_outputs_final_acceptance_report(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(tmp_path)],
        cwd=REPO,
        check=True,
    )

    report = json.loads(
        (tmp_path / "FINAL_ACCEPTANCE_REPORT_grading_to_brain.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["verdict"] == "not_complete_authorization_required"
    assert report["coverage_summary"] == {
        "done": 10,
        "partial": 2,
        "blocker": 0,
        "evidence_missing_count": 0,
    }
    assert report["completion_summary"]["authorization_gated"] == 1
    assert report["quality_gates"]["fp"] == 0
    assert report["quality_gates"]["production_write"] == 0
    assert report["remaining_authorization_gates"] == [
        "canonical_learner_truth_write",
        "production_default",
        "published_registry",
        "remote_or_db_write",
        "real_wechat_package_page_automation",
    ]
    assert report["artifacts"]["coverage_matrix"].endswith("coverage_matrix.json")
    assert report["artifacts"]["completion_audit"].endswith("completion_audit.json")
    assert report["artifacts"]["authorization_package"].endswith(
        "authorization_gate_decision_package.json"
    )
    assert report["current_commit"]
    assert any(
        "test_luban_grading_to_brain_current_gap_audit.py" in command["command"]
        for command in report["fresh_verification_commands"]
    )
    assert (tmp_path / "FINAL_ACCEPTANCE_REPORT_grading_to_brain.md").exists()
