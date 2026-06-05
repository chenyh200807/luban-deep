from __future__ import annotations

import json
from pathlib import Path

from scripts.build_luban_frontier_adjudicated_gold import adjudicate_frontier


def _golden(tmp: Path) -> Path:
    p = tmp / "golden.json"
    p.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "QX",
                        "gold_scoring_points": [
                            {"point_id": "PA", "max_score": 1, "point_type": "text_term"},
                            {"point_id": "PB", "max_score": 6, "point_type": "text_term", "list_rule": "k/n"},
                            {"point_id": "PC", "max_score": 2, "point_type": "text_term"},
                            {"point_id": "PD", "max_score": 1, "point_type": "text_term"},
                            {"point_id": "PE", "max_score": 1, "point_type": "text_term"},
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return p


def _arms(*hits_scores):
    names = ["gpt", "opus", "deepseek", "qwen"]
    return {
        n: {"hit": h, "score": s, "supported": True, "evidence_span": "x", "rationale": "r"}
        for n, (h, s) in zip(names, hits_scores)
    }


def _frontier(tmp: Path) -> Path:
    p = tmp / "frontier.json"
    rows = [
        {"case_id": "QX", "student_id": "S1", "point_id": "PA", "arms": _arms(("hit", 1), ("hit", 1), ("hit", 1), ("hit", 1))},
        {"case_id": "QX", "student_id": "S1", "point_id": "PB", "arms": _arms(("hit", 6), ("hit", 6), ("hit", 6), ("hit", 5))},
        # 3 miss + 1 lenient hit on exact_required -> resolved_with_dissent (strict majority upheld)
        {"case_id": "QX", "student_id": "S1", "point_id": "PC", "arms": _arms(("hit", 2), ("miss", 0), ("miss", 0), ("miss", 0))},
        # 2-2 split -> needs_policy_review
        {"case_id": "QX", "student_id": "S1", "point_id": "PD", "arms": _arms(("hit", 1), ("hit", 1), ("miss", 0), ("miss", 0))},
        # 3 lenient hit + 1 strict miss -> needs_policy_review (lenient majority, strict dissent)
        {"case_id": "QX", "student_id": "S1", "point_id": "PE", "arms": _arms(("hit", 1), ("hit", 1), ("hit", 1), ("miss", 0))},
    ]
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return p


def test_adjudicator_classifies_four_resolution_classes(tmp_path: Path) -> None:
    adj = adjudicate_frontier(frontier_path=_frontier(tmp_path), golden_path=_golden(tmp_path))
    by = {r["point_id"]: r for r in adj}
    assert by["PA"]["resolution_class"] == "resolved_auto_gold"
    assert by["PB"]["resolution_class"] == "resolved_score_normalized"
    assert by["PC"]["resolution_class"] == "resolved_with_dissent"
    assert by["PC"]["gold_hit"] == "miss"  # strict 3-model majority upheld over lenient dissent
    assert by["PC"]["dissent_arm"] == "gpt"
    assert by["PD"]["resolution_class"] == "needs_policy_review"  # split
    assert by["PE"]["resolution_class"] == "needs_policy_review"  # lenient majority vs strict dissent


def test_resolved_score_normalized_uses_median_model_score(tmp_path: Path) -> None:
    adj = adjudicate_frontier(frontier_path=_frontier(tmp_path), golden_path=_golden(tmp_path))
    pb = next(r for r in adj if r["point_id"] == "PB")
    # 4 hit votes with scores 6,6,6,5 -> median 6.0
    assert pb["gold_hit"] == "hit"
    assert pb["gold_score"] == 6.0


def test_calculation_disagreement_is_policy_review(tmp_path: Path) -> None:
    golden = tmp_path / "g.json"
    golden.write_text(json.dumps({"cases": [{"case_id": "QX", "gold_scoring_points": [{"point_id": "P1", "max_score": 2, "point_type": "calculation"}]}]}), encoding="utf-8")
    frontier = tmp_path / "f.json"
    frontier.write_text(json.dumps([{"case_id": "QX", "student_id": "S1", "point_id": "P1", "arms": _arms(("hit", 2), ("hit", 2), ("miss", 0), ("miss", 0))}]), encoding="utf-8")
    adj = adjudicate_frontier(frontier_path=frontier, golden_path=golden)
    assert adj[0]["resolution_class"] == "needs_policy_review"
    assert adj[0]["policy_type"] == "calculation"
