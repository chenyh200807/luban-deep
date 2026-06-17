from __future__ import annotations

import json
from pathlib import Path

from scripts.enforce_luban_agentic_span_guard import enforce_span_guard


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    packet = {
        "tasks": [
            {
                "case_id": "QX",
                "student_id": "S1",
                "student_answer": "学生原文写出了防护栏杆。",
            }
        ]
    }
    predictions = {
        "slice_id": "fixture",
        "prediction_sets": [
            {
                "arm": "deepseek_v4_flash_dual_adjudicated",
                "predictions": [
                    {
                        "case_id": "QX",
                        "student_id": "S1",
                        "point_id": "P1",
                        "hit": "hit",
                        "score": 1,
                        "evidence_span": "标准答案里的防护栏杆，不是学生原文",
                        "unsupported": False,
                        "high_risk": False,
                        "disposition": "agree",
                    },
                    {
                        "case_id": "QX",
                        "student_id": "S1",
                        "point_id": "P2",
                        "hit": "hit",
                        "score": 1,
                        "evidence_span": "防护栏杆",
                        "unsupported": False,
                        "high_risk": False,
                        "disposition": "agree",
                    },
                ],
            }
        ],
    }
    packet_path = tmp_path / "packet.json"
    predictions_path = tmp_path / "predictions.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    predictions_path.write_text(json.dumps(predictions, ensure_ascii=False), encoding="utf-8")
    return packet_path, predictions_path


def test_span_guard_demotes_hit_when_span_is_not_from_student_answer(tmp_path: Path) -> None:
    packet_path, predictions_path = _write_inputs(tmp_path)

    result = enforce_span_guard(
        packet_path=packet_path,
        predictions_path=predictions_path,
        output_path=tmp_path / "guarded.json",
    )

    guarded = json.loads((tmp_path / "guarded.json").read_text(encoding="utf-8"))
    first = guarded["prediction_sets"][0]["predictions"][0]
    second = guarded["prediction_sets"][0]["predictions"][1]
    assert result["forced_count"] == 1
    assert first["hit"] == "miss"
    assert first["score"] == 0.0
    assert first["unsupported"] is True
    assert first["high_risk"] is True
    assert first["disposition"] == "span_guard_forced_miss"
    assert first["span_guard"]["original_hit"] == "hit"
    assert second["hit"] == "hit"
    assert second.get("span_guard", {}).get("status") == "passed"
