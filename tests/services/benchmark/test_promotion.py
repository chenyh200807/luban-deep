from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from deeptutor.services.benchmark.promotion import (
    build_case_acceptance_snapshot,
    promote_registry_case_payload,
)
from deeptutor.services.benchmark.registry import load_benchmark_registry


def _load_payload() -> dict:
    fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "benchmark_phase1_registry.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_acceptance_snapshot_answers_prd_section_16_questions() -> None:
    payload = _load_payload()

    snapshot = build_case_acceptance_snapshot(payload, "grounding.rag.case_set")

    assert snapshot == {
        "case_id": "grounding.rag.case_set",
        "registered": True,
        "contract_domain": "grounding_contract",
        "suite_names": ["regression_watch"],
        "failure_taxonomy_scope": ["FAIL_GROUNDEDNESS"],
        "affects_pre_release_gate": False,
        "is_incident_promoted": True,
        "promotion_status": "promoted",
        "promoted_from_case_id": "continuity.long_dialog.focus",
    }


def test_promote_registry_case_payload_enforces_incident_to_regression_flow(tmp_path: Path) -> None:
    payload = _load_payload()

    promoted = promote_registry_case_payload(
        registry_payload=payload,
        case_id="surface.web.ack.smoke",
        target_tier="regression_tier",
        reason="stable incident replay",
    )
    target_path = tmp_path / "promoted_registry.json"
    target_path.write_text(json.dumps(promoted, ensure_ascii=False, indent=2), encoding="utf-8")
    reloaded = load_benchmark_registry(target_path)
    case = reloaded.cases["surface.web.ack.smoke"]

    assert case.case_tier == "regression_tier"
    assert case.promotion_status == "promoted"
    assert case.promoted_from_case_id == "surface.web.ack.smoke"
    assert case.is_incident_promoted is True


def test_promote_registry_case_payload_rejects_invalid_transition() -> None:
    payload = _load_payload()

    with pytest.raises(ValueError, match="Invalid promotion transition"):
        promote_registry_case_payload(
            registry_payload=payload,
            case_id="surface.web.ack.smoke",
            target_tier="gate_stable",
        )


def test_promote_benchmark_case_cli_writes_proposal(tmp_path: Path) -> None:
    output_path = tmp_path / "registry_promoted.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/promote_benchmark_case.py",
            "--case-id",
            "surface.web.ack.smoke",
            "--target-tier",
            "regression_tier",
            "--output-registry-path",
            str(output_path),
            "--reason",
            "stable incident replay",
        ],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Benchmark promotion proposal written" in completed.stdout
    assert output_path.exists()
    reloaded = load_benchmark_registry(output_path)
    assert reloaded.cases["surface.web.ack.smoke"].case_tier == "regression_tier"
