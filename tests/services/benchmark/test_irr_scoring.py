from __future__ import annotations

from deeptutor.services.benchmark.irr_scoring import score_point_label_agreement
from deeptutor.services.benchmark.luban_no_human_v1_5 import merge_independent_resolution_labels


def test_score_point_label_agreement_reports_pre_adjudication_disagreements() -> None:
    labels_a = [
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P1", "hit": "hit", "score": 1.0},
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P2", "hit": "miss", "score": 0.0},
    ]
    labels_b = [
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P1", "hit": "hit", "score": 1.0},
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P2", "hit": "partial", "score": 0.5},
    ]

    result = score_point_label_agreement(labels_a, labels_b)

    assert result["point_count"] == 2
    assert result["hit_agreement"] == 0.5
    assert result["score_exact_agreement"] == 0.5
    assert result["mean_abs_score_delta"] == 0.25
    assert result["pre_adjudication_disagreement_count"] == 1
    assert result["pre_adjudication_disagreements"][0]["point_id"] == "P2"
    assert result["cluster_bootstrap_ci"]["metric"] == "hit_agreement"


def test_merge_independent_resolution_labels_demotes_only_agreed_a_items() -> None:
    queue = [
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P1"},
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P2"},
    ]
    labels_a = [
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P1", "resolution_class": "A"},
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P2", "resolution_class": "A"},
    ]
    labels_b = [
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P1", "resolution_class": "A"},
        {"case_id": "Q1", "sample_id": "S1", "point_id": "P2", "resolution_class": "B"},
    ]

    merged = merge_independent_resolution_labels(queue, labels_a, labels_b)

    assert merged["counts"] == {"A": 1, "B": 1, "C": 0}
    assert merged["rows"][0]["resolution_class"] == "A"
    assert merged["rows"][1]["resolution_class"] == "B"
