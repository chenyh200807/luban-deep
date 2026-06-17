from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.score_luban_v1_5_spotcheck import (
    _answer_excerpt,
    build_spotcheck_packet,
    score_spotcheck_packet,
    select_spotcheck_rows,
)


def _point(point_id: str, *, category: str | None = None) -> dict:
    repairs = []
    if category:
        repairs.append({"category": category, "original_term": f"{category}-{point_id}"})
    return {
        "point_id": point_id,
        "label": f"必须写出术语{point_id}",
        "max_score": 2.0,
        "term_squeeze_v1_5": {"repairs": repairs},
        "textbook_provenance": {
            "terms": [
                {
                    "term": f"术语{point_id}",
                    "anchors": [{"source_path": "2026教材/book.json", "span_text": f"教材原文术语{point_id}"}],
                }
            ]
        },
    }


def _label(point_id: str, *, hit: str = "hit", score: float = 2.0, ex_b: bool = False) -> dict:
    return {
        "case_id": "Q1",
        "sample_id": "S1",
        "point_id": point_id,
        "hit": hit,
        "score": score,
        "max_score": 2.0,
        "resolution_class": "A",
        "is_deterministic": True,
        "independent_triage_applied": ex_b,
    }


def _fixture() -> dict:
    return {
        "cases": [
            {
                "case_id": "Q1",
                "stem": "题干",
                "gold_scoring_points": [
                    _point("P1", category="rubric_is_paraphrase"),
                    _point("P2"),
                    _point("P3", category="genuinely_absent"),
                    _point("P4"),
                ],
                "eval_samples": [
                    {
                        "student_id": "S1",
                        "answer_text": "学生答案写了术语P1，也写了术语P2。",
                        "no_human_v1_5_labels": [
                            _label("P1"),
                            _label("P2", ex_b=True),
                            _label("P3", hit="miss", score=0.0),
                            _label("P4"),
                        ],
                    }
                ],
            }
        ]
    }


def test_select_spotcheck_rows_is_deterministic_and_stratified() -> None:
    rows = select_spotcheck_rows(_fixture(), limits={"paraphrase": 10, "ex_class_b": 10, "genuinely_absent": 4, "stable_deterministic": 3})

    assert [row["stratum"] for row in rows] == [
        "paraphrase",
        "ex_class_b",
        "genuinely_absent",
        "stable_deterministic",
    ]
    assert rows[0]["case_id"] == "Q1"
    assert rows[0]["point_id"] == "P1"
    assert rows[1]["point_id"] == "P2"
    assert rows[2]["point_id"] == "P3"
    assert rows[3]["point_id"] == "P4"


def test_build_packet_blinds_pipeline_labels(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.csv"
    keys_path = tmp_path / "keys.json"

    summary = build_spotcheck_packet(_fixture(), packet_path=packet_path, keys_path=keys_path)

    with packet_path.open(encoding="utf-8") as handle:
        packet_rows = list(csv.DictReader(handle))
    keys = json.loads(keys_path.read_text(encoding="utf-8"))

    assert summary["stratum_counts"] == {
        "ex_class_b": 1,
        "genuinely_absent": 1,
        "paraphrase": 1,
        "stable_deterministic": 1,
    }
    forbidden = {"pipeline_hit", "pipeline_score", "resolution_class"}
    assert forbidden.isdisjoint(packet_rows[0])
    assert {"human_hit", "human_score", "human_note"}.issubset(packet_rows[0])
    assert keys["items"][0]["pipeline_hit"] == "hit"
    assert keys["items"][0]["resolution_class"] == "A"


def test_answer_excerpt_keeps_full_answer_context_when_term_is_not_located() -> None:
    answer = "前置说明。" + ("无关内容" * 60) + "最后才出现关键作答：先浇筑梁板混凝土。"
    excerpt = _answer_excerpt(
        answer,
        {"matched_terms": []},
        {"required_terms_v1_5": [], "label": "关键作答"},
    )

    assert "最后才出现关键作答" in excerpt
    assert len(excerpt) >= len(answer)


def test_score_spotcheck_packet_reports_stratum_breakdown(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.csv"
    keys_path = tmp_path / "keys.json"
    build_spotcheck_packet(_fixture(), packet_path=packet_path, keys_path=keys_path)

    rows = list(csv.DictReader(packet_path.open(encoding="utf-8")))
    rows[0]["human_hit"] = "miss"
    rows[0]["human_score"] = "0"
    rows[1]["human_hit"] = "hit"
    rows[1]["human_score"] = "2"
    rows[2]["human_hit"] = "miss"
    rows[2]["human_score"] = "0"
    rows[3]["human_hit"] = "hit"
    rows[3]["human_score"] = "2"
    with packet_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    result = score_spotcheck_packet(packet_path, keys_path)

    assert result["overall"]["point_count"] == 4
    assert result["overall"]["pre_adjudication_disagreement_count"] == 1
    assert result["by_stratum"]["paraphrase"]["disagreement_rate"] == 1.0
    assert result["by_stratum"]["ex_class_b"]["disagreement_rate"] == 0.0
    assert result["decision"]["status"] == "expand_or_rework_suspect_stratum"
