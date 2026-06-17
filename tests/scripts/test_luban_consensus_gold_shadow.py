from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_consensus_gold_shadow import build_gold_manifest, run_shadow_gate


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _fixture_files(tmp_path: Path) -> dict[str, Path]:
    gold = _write_json(
        tmp_path / "gold.json",
        [
            {"case_id": "Q1", "student_id": "S1", "point_id": "P1", "gold_hit": "hit", "gold_score": 1},
            {"case_id": "Q1", "student_id": "S1", "point_id": "P2", "gold_hit": "miss", "gold_score": 0},
        ],
    )
    frontier = _write_json(
        tmp_path / "frontier.json",
        [{"case_id": "Q1", "student_id": "S1", "point_id": "P3", "resolution_class": "needs_policy_review"}],
    )
    summary = _write_json(
        tmp_path / "summary.json",
        {
            "original_total_points": 3,
            "consensus_gold_v1_points": 2,
            "auto_gold_coverage": 0.6667,
            "frontier_unresolved": 1,
            "frontier_resolution_classes": {"needs_policy_review": 1},
        },
    )
    adjudicated = _write_json(tmp_path / "adjudicated.json", [{"case_id": "Q1"}])
    golden = _write_json(
        tmp_path / "golden.json",
        {
            "cases": [
                {
                    "case_id": "Q1",
                    "gold_scoring_points": [
                        {"point_id": "P1", "max_score": 1, "point_type": "text_term"},
                        {"point_id": "P2", "max_score": 1, "point_type": "text_term"},
                    ],
                }
            ]
        },
    )
    return {"gold": gold, "frontier": frontier, "summary": summary, "adjudicated": adjudicated, "golden": golden}


def _predictions(path: Path, predictions: list[dict[str, object]], arm: str = "qwen") -> Path:
    return _write_json(path, {"prediction_sets": [{"arm": arm, "predictions": predictions}]})


def test_manifest_freezes_hashes_and_forbidden_uses(tmp_path: Path) -> None:
    files = _fixture_files(tmp_path)
    manifest = build_gold_manifest(
        gold_path=files["gold"],
        summary_path=files["summary"],
        adjudicated_path=files["adjudicated"],
        unresolved_path=files["frontier"],
        output_path=tmp_path / "manifest.json",
    )

    assert manifest["gold_points"] == 2
    assert manifest["unresolved_points"] == 1
    assert manifest["input_hashes"][str(files["gold"])]["sha256"]
    assert "production runtime grading" in manifest["forbidden_uses"]
    assert "human gold claim" in manifest["forbidden_uses"]
    assert (tmp_path / "manifest.json").exists()


def test_shadow_gate_passes_complete_supported_predictions(tmp_path: Path) -> None:
    files = _fixture_files(tmp_path)
    manifest = build_gold_manifest(
        gold_path=files["gold"],
        summary_path=files["summary"],
        adjudicated_path=files["adjudicated"],
        unresolved_path=files["frontier"],
        output_path=tmp_path / "manifest.json",
    )
    predictions = _predictions(
        tmp_path / "predictions.json",
        [
            {"case_id": "Q1", "student_id": "S1", "point_id": "P1", "hit": "hit", "score": 1, "unsupported": False, "evidence_span": "x"},
            {"case_id": "Q1", "student_id": "S1", "point_id": "P2", "hit": "miss", "score": 0, "unsupported": False, "evidence_span": ""},
            {"case_id": "Q1", "student_id": "S1", "point_id": "P3", "hit": "hit", "score": 1, "unsupported": False, "evidence_span": "unresolved ignored"},
        ],
    )

    result = run_shadow_gate(
        gold_path=files["gold"],
        manifest_path=tmp_path / "manifest.json",
        predictions_path=predictions,
        arm="qwen",
        golden_path=files["golden"],
        output_dir=tmp_path / "out",
    )

    assert manifest["gold_points"] == 2
    assert result["pass"] is True
    assert result["evaluated_points"] == 2
    assert result["point_hit_agreement"] == 1.0
    assert result["missing_predictions"] == 0
    assert result["unsupported_positive"] == 0
    assert (tmp_path / "out" / "consensus_gold_shadow_report.md").exists()


def test_shadow_gate_fails_missing_or_unsupported_positive(tmp_path: Path) -> None:
    files = _fixture_files(tmp_path)
    build_gold_manifest(
        gold_path=files["gold"],
        summary_path=files["summary"],
        adjudicated_path=files["adjudicated"],
        unresolved_path=files["frontier"],
        output_path=tmp_path / "manifest.json",
    )
    predictions = _predictions(
        tmp_path / "predictions.json",
        [
            {"case_id": "Q1", "student_id": "S1", "point_id": "P1", "hit": "hit", "score": 1, "unsupported": True, "evidence_span": ""},
        ],
    )

    result = run_shadow_gate(
        gold_path=files["gold"],
        manifest_path=tmp_path / "manifest.json",
        predictions_path=predictions,
        arm="qwen",
        golden_path=files["golden"],
        output_dir=tmp_path / "out",
    )

    assert result["pass"] is False
    assert result["missing_predictions"] == 1
    assert result["unsupported_positive"] == 1
    assert result["point_hit_agreement"] == 0.5
