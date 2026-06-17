from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.score_luban_shadow_expansion_gate import run_expansion_gate


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _slice(tmp_path: Path, name: str, *, human_hit: str = "hit", human_score: str = "1") -> dict[str, str]:
    base = tmp_path / name
    base.mkdir()
    manifest = {
        "slice_id": name,
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
        "slice_id": name,
        "cases": [
            {
                "case_id": "Q1",
                "samples": [{"student_id": "S1", "answer_text": "学生写出防护栏杆。"}],
            }
        ],
    }
    labels = [
        {
            "case_id": "Q1",
            "student_id": "S1",
            "point_id": "P1",
            "human_hit": human_hit,
            "human_score": human_score,
            "human_error_codes": "",
            "human_note": "fixture",
        }
    ]
    predictions = {
        "slice_id": name,
        "prediction_sets": [
            {
                "arm": "qwen37_plus_thinking_primary",
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
    (base / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (base / "packet.json").write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    _write_csv(base / "labels.csv", labels)
    (base / "predictions.json").write_text(json.dumps(predictions, ensure_ascii=False), encoding="utf-8")
    return {
        "name": name,
        "manifest": str(base / "manifest.json"),
        "labels": str(base / "labels.csv"),
        "review_packet": str(base / "packet.json"),
        "predictions": str(base / "predictions.json"),
    }


def test_expansion_gate_blocks_when_human_labels_are_missing(tmp_path: Path) -> None:
    pending = _slice(tmp_path, "pending", human_hit="", human_score="")

    result = run_expansion_gate(slices=[pending], output_dir=tmp_path / "out")

    assert result["status"] == "blocked_human_labels_incomplete"
    assert result["slice_validations"][0]["validation"]["missing_count"] == 1
    assert "arms" not in result
    assert (tmp_path / "out" / "shadow_expansion_gate.json").exists()


def test_expansion_gate_scores_complete_slices_and_applies_thresholds(tmp_path: Path) -> None:
    dev = _slice(tmp_path, "dev")
    heldout = _slice(tmp_path, "heldout")

    result = run_expansion_gate(slices=[dev, heldout], output_dir=tmp_path / "out")

    assert result["status"] == "fail"
    arm = result["arms"]["qwen37_plus_thinking_primary"]
    assert arm["sample_count"] == 2
    assert arm["point_count"] == 2
    assert arm["point_hit_agreement"] == 1.0
    assert arm["mean_abs_score_delta"] == 0.0
    assert arm["unsupported_judgment_count"] == 0
    assert "sample_count=2 < 50" in arm["gate_reasons"]


def test_expansion_gate_prefers_filled_labels_when_available(tmp_path: Path) -> None:
    slice_spec = _slice(tmp_path, "heldout", human_hit="", human_score="")
    labels_filled = Path(slice_spec["labels"]).with_name("labels_filled.csv")
    _write_csv(
        labels_filled,
        [
            {
                "case_id": "Q1",
                "student_id": "S1",
                "point_id": "P1",
                "human_hit": "hit",
                "human_score": "1",
                "human_error_codes": "",
                "human_note": "filled",
            }
        ],
    )
    slice_spec["labels_filled"] = str(labels_filled)

    result = run_expansion_gate(slices=[slice_spec], output_dir=tmp_path / "out")

    assert result["slice_validations"][0]["validation"]["is_complete"] is True
    assert result["slices"][0]["label_file"] == str(labels_filled)
