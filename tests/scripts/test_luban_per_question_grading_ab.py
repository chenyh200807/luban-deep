from __future__ import annotations

import json

import scripts.run_luban_per_question_grading_ab as mod


def _contract() -> dict:
    return {
        "stem": "题干",
        "scoring_points": [
            {"point_id": "LONG::POINT::1", "official_slice": "甲", "sub_type": "enumeration"},
            {"point_id": "LONG::POINT::2", "official_slice": "乙", "sub_type": "enumeration"},
        ],
        "output_contract": {"must_emit_one_verdict_per_point_id": True},
    }


def test_arm_b_prompt_uses_compact_idx_output_not_long_point_ids() -> None:
    message = mod._arm_b_messages(contract=_contract(), student_answer="甲")[0]["content"]
    payload = json.loads(message)

    assert payload["scoring_points"] == [
        {"i": 1, "s": "甲", "t": "enumeration"},
        {"i": 2, "s": "乙", "t": "enumeration"},
    ]
    assert "LONG::POINT::1" not in message
    assert '"v":[[1,"h","学生原句"]]' in payload["instruction"]


def test_compact_arm_b_verdicts_map_idx_back_to_real_point_ids() -> None:
    data = {"v": [[1, "h", "甲"], [2, "m", ""]], "score_pct": 0.5}

    verdicts = mod._arm_b_verdicts(data, _contract())

    assert verdicts == {
        "LONG::POINT::1": "hit",
        "LONG::POINT::2": "miss",
    }


def test_arm_b_verdicts_keep_legacy_verbose_format_compatible() -> None:
    data = {
        "verdicts": [
            {"point_id": "LONG::POINT::1", "verdict": "partial", "evidence_span": "甲"},
            {"point_id": "LONG::POINT::2", "verdict": "contradiction", "evidence_span": ""},
        ],
        "score_pct": 0.25,
    }

    verdicts = mod._arm_b_verdicts(data, _contract())

    assert verdicts == {
        "LONG::POINT::1": "partial",
        "LONG::POINT::2": "contradiction",
    }
