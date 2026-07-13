from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[2] / "docs/原始数据/数据盘点/scripts/run_learning_graph_pilot_ab.py"
_SPEC = importlib.util.spec_from_file_location("learning_graph_pilot_ab", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
pilot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pilot)


def test_parse_model_response_rejects_multiple_selected_topics() -> None:
    parsed = pilot.parse_model_response(
        '{"decision":"select_prerequisite","selected_topic_id":"np01",'
        '"selected_topic_ids":["np01","np02"]}'
    )
    assert parsed["parse_status"] == "invalid"


def test_score_prediction_requires_acceptable_topic() -> None:
    case = {"case_id": "NP-01"}
    gold = {
        "gold_action": "select_prerequisite",
        "acceptable_topic_ids": ["np01"],
        "forbidden_topic_ids": ["np02"],
    }
    wrong = {"parse_status": "valid", "decision": "select_prerequisite", "selected_topic_id": "np02"}
    right = {"parse_status": "valid", "decision": "select_prerequisite", "selected_topic_id": "np01"}
    assert pilot.score_prediction(case, gold, wrong)["correct"] is False
    assert pilot.score_prediction(case, gold, right)["correct"] is True


def test_score_prediction_handles_direct_and_abstain_actions() -> None:
    direct = {"case_id": "NP-04"}
    direct_gold = {"gold_action": "teach_target_directly", "acceptable_topic_ids": [], "forbidden_topic_ids": ["np01"]}
    abstain = {"case_id": "NP-08"}
    abstain_gold = {"gold_action": "ask_for_evidence", "acceptable_topic_ids": [], "forbidden_topic_ids": ["np05"]}
    direct_prediction = {"parse_status": "valid", "decision": "teach_target_directly", "selected_topic_id": None}
    abstain_prediction = {"parse_status": "valid", "decision": "ask_for_evidence", "selected_topic_id": None}
    assert pilot.score_prediction(direct, direct_gold, direct_prediction)["correct"] is True
    assert pilot.score_prediction(abstain, abstain_gold, abstain_prediction)["correct"] is True


def test_score_prediction_invalid_response_still_reports_safety_fields() -> None:
    result = pilot.score_prediction(
        {"case_id": "NP-99"},
        {"gold_action": "ask_for_evidence", "acceptable_topic_ids": [], "forbidden_topic_ids": []},
        {"parse_status": "invalid", "parse_error": "invalid_json"},
    )
    assert result["correct"] is False
    assert result["unsupported_claim_count"] == 0
    assert result["authority_drift"] is False


def test_compare_pairs_counts_graph_wins_without_collapsing_wrong_ties() -> None:
    rows = []
    for i in range(20):
        rows.append({
            "case_id": f"NP-{i + 1:02d}",
            "baseline_correct": i < 13,
            "graph_correct": i < 16,
        })
    result = pilot.compare_pairs(rows, bootstrap_samples=200, seed=20260710)
    assert result["baseline_accuracy"] == 0.65
    assert result["graph_accuracy"] == 0.8
    assert result["paired_lift_pp"] == 15.0
    assert result["graph_wins"] == 3
    assert result["baseline_wins"] == 0
    assert result["tie_both_wrong"] == 4
    assert result["tie_both_correct"] == 13


def test_active_graph_excludes_pending_and_rejected_edges() -> None:
    edges = [
        {"src": "np01", "dst": "np02", "strength": "hard", "status": "active"},
        {"src": "np04", "dst": "np05", "strength": "hard", "status": "pending"},
        {"src": "np07", "dst": "np08", "strength": "hard", "status": "rejected"},
    ]
    assert pilot.active_graph_edges(edges) == [edges[0]]
