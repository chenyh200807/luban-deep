from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_learning_brain_actionable_edge_coverage import (
    collect_actionable_edge_coverage,
    source_coverage_failures,
)


def _write_event(path: Path, *, source_feature: str, edges: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "memory_kind": "learning_evidence",
        "source_feature": source_feature,
        "payload_json": {
            "typed_edges": edges,
        },
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_collect_actionable_edge_coverage_counts_real_edge_types(tmp_path: Path) -> None:
    user_file = tmp_path / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl"
    _write_event(
        user_file,
        source_feature="construction_grading",
        edges=[
            {"edge_type": "question_tests_concept"},
            {"edge_type": "error_points_to_training"},
        ],
    )
    _write_event(
        user_file,
        source_feature="assessment_testset",
        edges=[],
    )

    report = collect_actionable_edge_coverage(tmp_path / "learner_state")

    assert report["total"]["learning_evidence_events"] == 2
    assert report["total"]["events_with_actionable_edges"] == 1
    assert report["total"]["actionable_edge_coverage"] == 0.5
    assert report["edge_counts"]["error_points_to_training"] == 1
    assert report["by_source"]["construction_grading"]["events_with_actionable_edges"] == 1


def test_source_coverage_failures_can_gate_specific_empty_entrypoints(tmp_path: Path) -> None:
    user_file = tmp_path / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl"
    _write_event(
        user_file,
        source_feature="construction_grading",
        edges=[{"edge_type": "error_points_to_training"}],
    )
    _write_event(
        user_file,
        source_feature="assessment_testset",
        edges=[],
    )

    report = collect_actionable_edge_coverage(tmp_path / "learner_state")
    failures = source_coverage_failures(
        report,
        min_source_coverages={"assessment_testset": 0.1, "construction_grading": 0.1},
    )

    assert failures == [
        {
            "source": "assessment_testset",
            "coverage": 0.0,
            "min_actionable_coverage": 0.1,
            "learning_evidence_events": 1,
        }
    ]
