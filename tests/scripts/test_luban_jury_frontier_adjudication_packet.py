from __future__ import annotations

import json
from pathlib import Path

from scripts.build_luban_jury_frontier_adjudication_packet import build_frontier_adjudication_packet


def test_builds_blind_frontier_adjudication_packet(tmp_path: Path) -> None:
    packet_path = tmp_path / "agentic_packet.json"
    frontier_path = tmp_path / "jury_frontier_points.json"
    output_dir = tmp_path / "out"

    packet_path.write_text(
        json.dumps(
            {
                "slice_id": "dev-slice",
                "grading_guideline": {"踩字口径": "近义不算"},
                "tasks": [
                    {
                        "case_id": "Q1",
                        "student_id": "S1",
                        "question_node": "1A430000",
                        "stem": "题干",
                        "official_answer": "标准答案",
                        "student_answer": "学生写了防护栏杆。",
                        "scoring_points": [
                            {
                                "point_id": "P1",
                                "label": "必须写出防护栏杆",
                                "max_score": 1,
                                "official_basis": "防护栏杆",
                                "list_rule": "",
                                "penalty_rule": None,
                            }
                        ],
                        "ground_truth_ledger": {"should_not": "leak"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    frontier_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "Q1",
                    "student_id": "S1",
                    "point_id": "P1",
                    "top_hit": "hit",
                    "top_score": 1,
                    "top_vote_count": 2,
                    "unsupported_arms": [],
                    "arms": {
                        "gpt55": {
                            "hit": "hit",
                            "score": 1,
                            "supported": True,
                            "evidence_span": "防护栏杆",
                            "rationale": "逐字命中",
                        },
                        "qwen37": {
                            "hit": "miss",
                            "score": 0,
                            "supported": True,
                            "evidence_span": "",
                            "rationale": "human_note 里曾经这样写，但这里必须盲化",
                        },
                    },
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_frontier_adjudication_packet(
        frontier_path=frontier_path,
        source_packet_path=packet_path,
        output_dir=output_dir,
    )

    assert result["frontier_point_count"] == 1
    adjudication_packet = json.loads((output_dir / "frontier_adjudication_packet.json").read_text(encoding="utf-8"))
    task = adjudication_packet["tasks"][0]
    assert task["case_id"] == "Q1"
    assert task["scoring_point"]["label"] == "必须写出防护栏杆"
    assert task["model_judgments"]["gpt55"]["hit"] == "hit"
    assert task["model_judgments"]["qwen37"]["hit"] == "miss"
    assert task["model_judgments"]["qwen37"]["rationale"] == "[redacted: non-blind rationale metadata]"
    assert "ground_truth_ledger" not in json.dumps(adjudication_packet, ensure_ascii=False)
    assert "human_hit" not in json.dumps(adjudication_packet, ensure_ascii=False)
    assert "human_note" not in json.dumps(adjudication_packet, ensure_ascii=False)
    assert (output_dir / "frontier_adjudication_template.json").exists()
    assert (output_dir / "frontier_adjudication_prompt.md").exists()
    assert (output_dir / "FINDING_jury_frontier_adjudication_packet.md").exists()
