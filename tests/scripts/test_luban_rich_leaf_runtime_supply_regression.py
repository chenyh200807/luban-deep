from __future__ import annotations

import json
from pathlib import Path


def _unit(unit_id: str, lane: str) -> dict:
    return {
        "unit_id": unit_id,
        "leaf_id": f"L-{unit_id}",
        "artifact_id": f"A-{unit_id}",
        "missing_lane": lane,
        "source_ref": {
            "source_lane": lane,
            "source_path": f"{lane}/source.json",
            "record_id": f"{lane.upper()}-1",
            "span": f"{lane} source span",
            "span_hash": f"hash-{unit_id}",
            "support_candidate": True,
        },
        "provenance": {
            "candidate_id": f"RC-{unit_id}",
            "audit_item_id": f"audit:{unit_id}",
            "review_decision": "accept_source_ref_candidate",
            "reviewer_role": "semantic_evidence_reviewer",
        },
        "candidate_only": True,
        "review_only": True,
        "install_allowed": False,
        "runtime_install_allowed": False,
        "production_default": False,
    }


def _bundle(*units: dict) -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_supply_candidate_bundle.v1",
        "version": "v_test",
        "status": "candidate_ready_for_regression" if units else "no_reviewed_candidates",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_supply_candidate": True,
            "regression_required": True,
            "install_allowed": False,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
        },
        "summary": {
            "reviewed_candidate_count": len(units),
            "supply_unit_count": len(units),
            "rejected_candidate_count": 0,
        },
        "manifest": {"bundle_hash": "hash", "hash_algorithm": "sha256"},
        "supply_units": list(units),
        "rejected_candidates": [],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_runtime_supply_regression_projects_by_task_without_question_source_pollution() -> None:
    from scripts.run_luban_rich_leaf_runtime_supply_regression import run_runtime_supply_regression

    report = run_runtime_supply_regression(
        runtime_supply_candidate=_bundle(_unit("textbook-1", "textbook"), _unit("question-1", "question"))
    )

    assert report["schema"] == "luban_rich_leaf_runtime_supply_regression.v1"
    assert report["verdict"] == "PASS"
    assert report["classification"]["runtime_install_allowed"] is False
    by_task = {projection["task"]: projection for projection in report["task_projections"]}
    assert by_task["grading"]["projected_unit_count"] == 2
    assert by_task["grading"]["projected_lane_counts"] == {"question": 1, "textbook": 1}
    assert by_task["rag_answer"]["projected_unit_count"] == 1
    assert by_task["rag_answer"]["excluded_lane_counts"] == {"question": 1}
    assert by_task["tutoring"]["projected_unit_count"] == 1
    assert by_task["tutoring"]["excluded_lane_counts"] == {"question": 1}
    assert by_task["next_action"]["projected_unit_count"] == 0
    assert by_task["next_action"]["exclusion_reasons"] == {"source_refs_not_allowed_for_task": 2}
    assert by_task["review"]["projected_unit_count"] == 2


def test_runtime_supply_regression_fails_when_candidate_can_install_runtime() -> None:
    from scripts.run_luban_rich_leaf_runtime_supply_regression import run_runtime_supply_regression

    bundle = _bundle(_unit("textbook-1", "textbook"))
    bundle["classification"]["runtime_install_allowed"] = True

    report = run_runtime_supply_regression(runtime_supply_candidate=bundle)

    assert report["verdict"] == "FAIL"
    assert "classification_runtime_install_allowed" in report["blockers"]


def test_runtime_supply_regression_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_runtime_supply_regression import main

    candidate = tmp_path / "rich_leaf_runtime_supply_candidate.json"
    out_dir = tmp_path / "out"
    candidate.write_text(json.dumps(_bundle(_unit("standard-1", "standard")), ensure_ascii=False), encoding="utf-8")

    exit_code = main(["--runtime-supply-candidate", str(candidate), "--output-dir", str(out_dir)])

    assert exit_code == 0
    payload = json.loads((out_dir / "runtime_supply_regression.json").read_text("utf-8"))
    assert payload["verdict"] == "PASS"
    assert payload["summary"]["input_supply_unit_count"] == 1
