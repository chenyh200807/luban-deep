from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.build_luban_multimodel_jury_gold import run_jury_analysis


def _write_predictions(path: Path, arm: str, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"slice_id": "jury-fixture", "prediction_sets": [{"arm": arm, "predictions": rows}]}, ensure_ascii=False),
        encoding="utf-8",
    )


def _prediction(case_id: str, student_id: str, point_id: str, hit: str, score: float) -> dict[str, object]:
    return {
        "case_id": case_id,
        "student_id": student_id,
        "point_id": point_id,
        "hit": hit,
        "score": score,
        "confidence": 0.9,
        "evidence_span": "防护栏杆" if hit != "miss" else "",
        "rationale": "fixture",
        "unsupported": False,
    }


def _write_manifest_and_labels(tmp_path: Path) -> tuple[Path, Path]:
    manifest = {
        "slice_id": "jury-fixture",
        "selected_samples": [
            {
                "case_id": "Q1",
                "student_id": "S1",
                "ledger_point_rows": [
                    {"point_id": "P1", "ledger_hit": "hit", "max_score": 1, "gold_score": 1},
                    {"point_id": "P2", "ledger_hit": "miss", "max_score": 1, "gold_score": 0},
                ],
            }
        ],
    }
    labels = [
        {"case_id": "Q1", "student_id": "S1", "point_id": "P1", "human_hit": "hit", "human_score": "1"},
        {"case_id": "Q1", "student_id": "S1", "point_id": "P2", "human_hit": "miss", "human_score": "0"},
    ]
    manifest_path = tmp_path / "manifest.json"
    labels_path = tmp_path / "labels.csv"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with labels_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "student_id", "point_id", "human_hit", "human_score"])
        writer.writeheader()
        writer.writerows(labels)
    return manifest_path, labels_path


def test_jury_analysis_builds_leave_one_out_gold_and_frontier(tmp_path: Path) -> None:
    manifest_path, labels_path = _write_manifest_and_labels(tmp_path)
    gpt = tmp_path / "gpt.json"
    opus = tmp_path / "opus.json"
    deepseek = tmp_path / "deepseek.json"
    qwen = tmp_path / "qwen.json"
    _write_predictions(gpt, "gpt55_primary", [_prediction("Q1", "S1", "P1", "hit", 1), _prediction("Q1", "S1", "P2", "miss", 0)])
    _write_predictions(opus, "opus48_reviewer", [_prediction("Q1", "S1", "P1", "hit", 1), _prediction("Q1", "S1", "P2", "hit", 1)])
    _write_predictions(deepseek, "deepseek_primary", [_prediction("Q1", "S1", "P1", "hit", 1), _prediction("Q1", "S1", "P2", "miss", 0)])
    _write_predictions(qwen, "qwen_primary", [_prediction("Q1", "S1", "P1", "hit", 1), _prediction("Q1", "S1", "P2", "miss", 0)])

    result = run_jury_analysis(
        manifest_path=manifest_path,
        labels_path=labels_path,
        arm_specs=[
            f"{gpt}:gpt55_primary:gpt",
            f"{opus}:opus48_reviewer:opus",
            f"{deepseek}:deepseek_primary:deepseek",
            f"{qwen}:qwen_primary:qwen",
        ],
        target_arm="qwen",
        output_dir=tmp_path / "out",
    )

    assert result["summary"]["total_points"] == 2
    assert result["summary"]["full_consensus_points"] == 1
    assert result["summary"]["frontier_points"] == 1
    assert result["target_vs_jury"]["target_arm"] == "qwen"
    assert result["target_vs_jury"]["jury_point_count"] == 1
    assert result["target_vs_jury"]["point_hit_agreement"] == 1.0
    assert result["human_checks"]["jury_vs_human"]["point_hit_agreement"] == 1.0
    assert (tmp_path / "out" / "jury_consensus_points.json").exists()
    assert (tmp_path / "out" / "jury_frontier_points.json").exists()
    assert (tmp_path / "out" / "jury_frontier_queue.csv").exists()
    assert (tmp_path / "out" / "target_disagreements.csv").exists()
    assert (tmp_path / "out" / "FINDING_multimodel_jury_gold.md").exists()
