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
