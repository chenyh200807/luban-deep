from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.run_luban_heldout_post_label_gate import run_post_label_gate


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path, *, filled: bool) -> dict[str, Path]:
    base = tmp_path / "slice"
    gate = tmp_path / "gate"
    base.mkdir()
    manifest = {
        "slice_id": "heldout",
        "selected_samples": [
            {
                "case_id": "Q1",
                "student_id": "S1",
                "artifact_point_scores": {"P1": 0},
                "ledger_point_rows": [{"point_id": "P1", "ledger_hit": "hit", "max_score": 1, "gold_score": 1}],
            }
        ],
    }
    packet = {
        "slice_id": "heldout",
        "cases": [{"case_id": "Q1", "samples": [{"student_id": "S1", "answer_text": "学生写出防护栏杆。"}]}],
    }
    predictions = {
        "slice_id": "heldout",
        "prediction_sets": [
            {
                "arm": "qwen37plus_nothink_primary",
                "predictions": [
                    {
                        "case_id": "Q1",
                        "student_id": "S1",
                        "point_id": "P1",
                        "hit": "hit",
                        "score": 1,
                        "confidence": 0.9,
                        "evidence_span": "防护栏杆",
                        "rationale": "fixture",
                        "unsupported": False,
                    }
                ],
            }
        ],
    }
    labels = [
        {
            "case_id": "Q1",
            "student_id": "S1",
            "point_id": "P1",
            "max_score": "1",
            "point_label": "防护栏杆",
            "human_hit": "hit" if filled else "",
            "human_score": "1" if filled else "",
            "human_error_codes": "",
            "human_note": "fixture" if filled else "",
        }
    ]
    paths = {
        "manifest": base / "manifest.json",
        "packet": base / "packet.json",
        "labels_template": base / "labels_template.csv",
        "labels_filled": base / "labels_filled.csv",
        "predictions": base / "predictions.json",
        "human_metrics": base / "human_metrics.json",
        "slices_config": gate / "slices_config.json",
        "output_dir": gate,
    }
    gate.mkdir(parents=True)
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    paths["packet"].write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    paths["predictions"].write_text(json.dumps(predictions, ensure_ascii=False), encoding="utf-8")
    _write_csv(paths["labels_template"], labels)
    if filled:
        _write_csv(paths["labels_filled"], labels)
    config = {
        "slices": [
            {
                "name": "heldout",
                "manifest": str(paths["manifest"]),
                "labels": str(paths["labels_template"]),
                "labels_filled": str(paths["labels_filled"]),
                "review_packet": str(paths["packet"]),
                "predictions": str(paths["predictions"]),
            }
        ]
    }
    paths["slices_config"].write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return paths


def test_post_label_gate_blocks_when_labels_are_missing(tmp_path: Path) -> None:
    paths = _fixture(tmp_path, filled=False)

    result = run_post_label_gate(
        manifest_path=paths["manifest"],
        labels_path=paths["labels_template"],
        review_book_path=None,
        template_path=paths["labels_template"],
        write_labels_csv_path=paths["labels_filled"],
        human_metrics_output_path=paths["human_metrics"],
        slices_config_path=paths["slices_config"],
        expansion_output_dir=paths["output_dir"],
    )

    assert result["status"] == "blocked_human_labels_incomplete"
    assert result["human_validation"]["validation"]["missing_count"] == 1
    assert result["expansion_gate"]["status"] == "blocked_human_labels_incomplete"
    assert paths["human_metrics"].exists()
    assert (paths["output_dir"] / "FINDING_heldout_post_label_gate.md").exists()


def test_post_label_gate_runs_expansion_after_complete_labels(tmp_path: Path) -> None:
    paths = _fixture(tmp_path, filled=True)

    result = run_post_label_gate(
        manifest_path=paths["manifest"],
        labels_path=paths["labels_filled"],
        review_book_path=None,
        template_path=paths["labels_template"],
        write_labels_csv_path=paths["labels_filled"],
        human_metrics_output_path=paths["human_metrics"],
        slices_config_path=paths["slices_config"],
        expansion_output_dir=paths["output_dir"],
    )

    assert result["status"] == "fail"
    assert result["human_validation"]["validation"]["is_complete"] is True
    assert result["expansion_gate"]["status"] == "fail"
    assert result["expansion_gate"]["arms"]["qwen37plus_nothink_primary"]["sample_count"] == 1


def test_post_label_gate_accepts_csv_direct_fill_without_review_book(tmp_path: Path) -> None:
    paths = _fixture(tmp_path, filled=True)

    result = run_post_label_gate(
        manifest_path=paths["manifest"],
        labels_path=paths["labels_filled"],
        review_book_path=None,
        template_path=paths["labels_template"],
        write_labels_csv_path=paths["labels_filled"],
        human_metrics_output_path=paths["human_metrics"],
        slices_config_path=paths["slices_config"],
        expansion_output_dir=paths["output_dir"],
    )

    assert result["human_validation"]["label_file"] == str(paths["labels_filled"])
    assert "review_book_conversion" not in result
    assert result["human_validation"]["validation"]["is_complete"] is True
