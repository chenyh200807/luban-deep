from __future__ import annotations

import json
from pathlib import Path

from scripts.run_luban_unified_typed_policy_models import (
    build_prompt,
    merge_predictions,
    parse_prediction_array,
)


def _task() -> dict:
    return {
        "case_id": "Q1",
        "student_id": "S1",
        "task_id": "Q1::S1",
        "student_answer": "学生写出防护栏杆。",
        "official_answer": "防护栏杆",
        "penalty_rule": "",
        "scoring_points": [
            {
                "point_id": "P1",
                "label": "必须写出防护栏杆",
                "max_score": 1,
                "typed_policy": {
                    "policy_type": "exact_required",
                    "required_terms": ["防护栏杆"],
                    "list_spec": None,
                    "numeric_spec": None,
                    "penalty_spec": None,
                },
            }
        ],
    }


def test_build_prompt_includes_typed_policy_and_no_human_labels() -> None:
    prompt = build_prompt(_task(), arm="qwen37_plus_thinking_primary")

    assert "typed_policy" in prompt
    assert "不要把 required_terms 当作全局 substring 硬门" in prompt
    assert "防护栏杆" in prompt
    assert "human_hit" not in prompt
    assert "human_score" not in prompt


def test_parse_prediction_array_tolerates_code_fences_and_trailing_commas() -> None:
    parsed = parse_prediction_array(
        """```json
        [{"point_id":"P1","hit":"hit","score":1,"evidence_span":"防护栏杆",}]
        ```"""
    )

    assert parsed[0]["point_id"] == "P1"
    assert parsed[0]["hit"] == "hit"


def test_merge_predictions_replaces_arm_without_dropping_other_arms(tmp_path: Path) -> None:
    output = tmp_path / "predictions.json"
    output.write_text(
        json.dumps(
            {
                "slice_id": "slice-x",
                "prediction_sets": [
                    {"arm": "qwen37_plus_thinking_primary", "predictions": [{"point_id": "old"}]},
                    {"arm": "deepseek_v4_flash_typed_policy_primary", "predictions": []},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    merge_predictions(
        output_path=output,
        slice_id="slice-x",
        arm="qwen37_plus_thinking_primary",
        predictions=[{"point_id": "P1", "case_id": "Q1", "student_id": "S1"}],
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    arms = {row["arm"]: row["predictions"] for row in payload["prediction_sets"]}
    assert arms["qwen37_plus_thinking_primary"][0]["point_id"] == "P1"
    assert arms["deepseek_v4_flash_typed_policy_primary"] == []
