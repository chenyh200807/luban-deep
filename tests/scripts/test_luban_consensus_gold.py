from __future__ import annotations

import json
from pathlib import Path

from scripts.build_luban_consensus_gold import build_consensus_gold


def _write(path: Path, obj: object) -> Path:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def _golden(tmp: Path) -> Path:
    return _write(
        tmp / "golden.json",
        {
            "cases": [
                {
                    "case_id": "QX",
                    "gold_scoring_points": [
                        {"point_id": "P1", "max_score": 1, "point_type": "text_term", "required_terms_v1_5": ["见证人员"]},
                        {"point_id": "P2", "max_score": 1, "point_type": "text_term", "required_terms_v1_5": ["防护栏杆"]},
                    ],
                }
            ]
        },
    )


def _packet(tmp: Path) -> Path:
    return _write(
        tmp / "packet.json",
        {"tasks": [{"case_id": "QX", "student_id": "S1", "scoring_points": [{"point_id": "P1"}, {"point_id": "P2"}], "student_answer": "见证人员负责"}]},
    )


def _model(tmp: Path, name: str, p1_hit: str, p2_hit: str) -> tuple[str, Path]:
    path = _write(
        tmp / f"{name}.json",
        {
            "prediction_sets": [
                {
                    "arm": name,
                    "predictions": [
                        {"case_id": "QX", "student_id": "S1", "point_id": "P1", "hit": p1_hit, "score": 1 if p1_hit == "hit" else 0},
                        {"case_id": "QX", "student_id": "S1", "point_id": "P2", "hit": p2_hit, "score": 1 if p2_hit == "hit" else 0},
                    ],
                }
            ]
        },
    )
    return name, path


def test_consensus_builder_handles_four_model_predictions_unanimous_and_split(tmp_path: Path) -> None:
    golden, packet = _golden(tmp_path), _packet(tmp_path)
    # P1: all 4 agree hit -> unanimous. P2: 2 hit / 2 miss -> split frontier.
    arms = [
        _model(tmp_path, "m1", "hit", "hit"),
        _model(tmp_path, "m2", "hit", "hit"),
        _model(tmp_path, "m3", "hit", "miss"),
        _model(tmp_path, "m4", "hit", "miss"),
    ]
    result = build_consensus_gold(model_arms=arms, golden_path=golden, packet_path=packet)
    gold = {(g["point_id"]): g for g in result["gold"]}
    assert result["n_models"] == 4
    assert gold["P1"]["basis"] == "unanimous_consensus"
    assert gold["P1"]["gold_hit"] == "hit"
    assert gold["P2"]["basis"] == "split_frontier_needs_human"
    assert gold["P2"]["gold_hit"] is None  # frontier is not auto-golded


def test_consensus_builder_list_rule_deterministic_is_off_by_default(tmp_path: Path) -> None:
    # A list_rule point: even if required-term regex would override, default must keep pure consensus.
    golden = _write(
        tmp_path / "golden.json",
        {
            "cases": [
                {
                    "case_id": "QX",
                    "gold_scoring_points": [
                        {"point_id": "P1", "max_score": 2, "point_type": "text_term",
                         "list_rule": "命中2项满分", "required_terms_v1_5": ["甲", "乙"]},
                    ],
                }
            ]
        },
    )
    packet = _write(tmp_path / "packet.json", {"tasks": [{"case_id": "QX", "student_id": "S1", "scoring_points": [{"point_id": "P1"}], "student_answer": "只写了甲"}]})
    arms = [
        _model_one(tmp_path, "m1", "hit"), _model_one(tmp_path, "m2", "hit"),
        _model_one(tmp_path, "m3", "hit"), _model_one(tmp_path, "m4", "hit"),
    ]
    default = build_consensus_gold(model_arms=arms, golden_path=golden, packet_path=packet)
    assert default["gold"][0]["basis"] == "unanimous_consensus"  # NOT list_rule_deterministic
    forced = build_consensus_gold(model_arms=arms, golden_path=golden, packet_path=packet, list_rule_deterministic=True)
    assert forced["gold"][0]["basis"] == "list_rule_deterministic"  # opt-in only


def _model_one(tmp: Path, name: str, p1_hit: str) -> tuple[str, Path]:
    path = _write(
        tmp / f"{name}.json",
        {"prediction_sets": [{"arm": name, "predictions": [
            {"case_id": "QX", "student_id": "S1", "point_id": "P1", "hit": p1_hit, "score": 2 if p1_hit == "hit" else 0}]}]},
    )
    return name, path
