from __future__ import annotations

import json
from pathlib import Path

from scripts.build_luban_heldout_review_book import build_review_book
from scripts.score_luban_human_validation_slice import parse_review_book_markdown


def test_build_review_book_is_blind_and_parseable_after_teacher_fill(tmp_path: Path) -> None:
    packet = {
        "slice_id": "luban-qwen-heldout-ledger-internal",
        "grading_guideline": "踩字给分。",
        "tasks": [
            {
                "case_id": "Q1",
                "student_id": "S1",
                "stem": "题干",
                "official_answer": "标准答案",
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
                "student_answer": "学生写出防护栏杆。",
            }
        ],
    }
    packet_path = tmp_path / "packet.json"
    output_path = tmp_path / "review.md"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")

    result = build_review_book(packet_path=packet_path, output_path=output_path)

    markdown = output_path.read_text(encoding="utf-8")
    assert result["task_count"] == 1
    assert result["point_row_count"] == 1
    assert "# 1. Q1" in markdown
    assert "### 学生 S1" in markdown
    assert "| P1 | 1 |  |  |  |" in markdown
    assert "ground_truth_ledger" not in markdown
    assert "ledger" not in markdown.lower()
    assert "artifact_first" not in markdown
    assert "qwen" not in markdown.lower()
    assert "deepseek" not in markdown.lower()

    filled = markdown.replace("| P1 | 1 |  |  |  |", "| P1 | 1 | hit | 1 | 命中防护栏杆 |")
    rows = parse_review_book_markdown(filled)
    assert rows == [
        {
            "case_id": "Q1",
            "student_id": "S1",
            "point_id": "P1",
            "human_hit": "hit",
            "human_score": "1",
            "human_error_codes": "",
            "human_note": "命中防护栏杆",
        }
    ]
