from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from deeptutor.services.benchmark.learning_brain_personalization_eval import (
    evaluate_golden_projection,
    evaluate_personalization_cases,
)


FIXTURE = Path("tests/fixtures/learning_brain_personalization_cases.json")
GOLDEN = Path("tests/fixtures/learning_brain_golden_projection.json")


def test_personalization_fixture_covers_required_case_matrix() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    case_ids = {case["case_id"] for case in fixture["cases"]}

    assert {
        "lbp_001_confirmed_retest",
        "lbp_002_no_evidence_starter",
        "lbp_003_repeated_weak_point",
        "lbp_004_stale_needs_retest",
        "lbp_005_contradicted_claim",
        "lbp_006_exact_question_conflict",
        "lbp_007_standard_authority_conflict",
        "lbp_008_notebook_subjective_focus",
        "lbp_009_training_intent_absent",
        "lbp_010_improved_after_training",
    }.issubset(case_ids)


def test_no_evidence_case_does_not_require_evidence_backed_retest() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    no_evidence = next(case for case in fixture["cases"] if case["case_id"] == "lbp_002_no_evidence_starter")

    assert no_evidence["learning_brain"]["weak_points"] == []
    assert no_evidence["expected"]["must_reference_evidence"] is False
    assert no_evidence["expected"]["expected_action_type"] == "starter_action"
    assert "retest_training" in no_evidence["expected"]["forbidden_action_types"]


def test_learning_brain_personalization_eval_passes_release_metrics() -> None:
    result = evaluate_personalization_cases(FIXTURE)

    assert result["verdict"] == "pass"
    assert result["metrics"]["personalization_hit_rate"] == 1.0
    assert result["metrics"]["evidence_coverage"] >= 0.95
    assert result["metrics"]["generic_fallback_rate"] <= 0.05
    assert result["metrics"]["unsupported_claim_rate"] == 0.0


def test_learning_brain_golden_projection_has_evidence_backed_actions() -> None:
    result = evaluate_golden_projection(GOLDEN)

    assert result["unsupported_claim_rate"] == 0.0
    assert result["evidence_coverage"] >= 0.95


def test_learning_brain_personalization_eval_cli_gate_passes() -> None:
    output = subprocess.check_output(
        [
            sys.executable,
            "-m",
            "deeptutor.services.benchmark.learning_brain_personalization_eval",
            "--fixture",
            str(FIXTURE),
            "--min-evidence-coverage",
            "0.95",
            "--max-generic-fallback-rate",
            "0.05",
        ],
        text=True,
    )

    assert "verdict=pass" in output
