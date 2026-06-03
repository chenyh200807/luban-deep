from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_learning_brain_actionable_edge_coverage import collect_actionable_edge_coverage


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
