"""Nexus-like compilation decision package aggregation tests."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_nexus_compilation_decision_package import build_decision_package


def test_decision_package_preserves_shadow_authority_and_release_no_go(tmp_path):
    package = build_decision_package(output_dir=tmp_path)

    assert package["schema_version"] == "luban_nexus_compilation_decision.v1"
    assert package["overall"]["phase1_shadow_verdict"] == "WEAK-GO"
    assert package["overall"]["release_verdict"] == "NO-GO"
    assert package["overall"]["quality_claim_allowed"] is False

    m35 = package["tracks"]["m35_case_scoring"]
    assert m35["status"] == "phase1_shadow_effectiveness_passed"
    assert m35["verdict_ceiling"] == "DIRECTIONAL_SHADOW"
    assert m35["artifact_first_llm_judge"]["score_mae"] < m35["legacy"]["score_mae"]
    assert m35["artifact_first_llm_judge"]["fail_open_rate"] < m35["legacy"]["fail_open_rate"]
    assert m35["not_release_reasons"]

    m34 = package["tracks"]["m34_general_knowledge"]
    assert m34["system_wide_default"] == "NO-GO"
    assert "online_shadow_or_compiler_repair_pending" in m34["blockers"]

    loop = package["tracks"]["grading_to_brain"]
    assert loop["status"] == "hermetic_trace_passed"
    assert loop["release_truth_written"] is False

    flywheel = package["tracks"]["compiler_feedback_flywheel"]
    assert flywheel["status"] == "partial"
    assert flywheel["open_work_orders"]

    for value in package["safety"].values():
        assert value in (False, 0)

    written = tmp_path / "decision_package.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8")) == package
