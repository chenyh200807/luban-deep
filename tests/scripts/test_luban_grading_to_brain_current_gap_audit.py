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
