from __future__ import annotations

from deeptutor.services.rag.provenance import (
    apply_provenance_ranking,
    build_ranking_trace,
    extract_provenance_features,
)


def test_extract_provenance_features_for_compiled_truth() -> None:
    features = extract_provenance_features(
        {
            "chunk_id": "compiled-truth:concept:1A432000",
            "_source_group": "compiled_learning_truth",
            "source_type": "compiled_learning_truth",
            "evidence_level": "L2_confirmed",
            "supporting_event_ids": ["evt1", "evt2"],
        }
    )

    assert features["source_group"] == "compiled_learning_truth"
    assert features["manual_confirmed"] is True
    assert features["supporting_event_ids"] == ["evt1", "evt2"]
    assert features["supporting_event_count"] == 2


def test_apply_provenance_ranking_keeps_exact_question_ahead_of_compiled_truth() -> None:
    ranked = apply_provenance_ranking(
        [
            {
                "chunk_id": "compiled-truth:concept:1A432000",
                "_source_group": "compiled_learning_truth",
                "source_type": "compiled_learning_truth",
                "evidence_level": "L2_confirmed",
                "weighted_rrf_score": 0.08,
            },
            {
                "chunk_id": "q1",
                "_source_group": "question_exact_text",
                "source_type": "questions_bank",
                "weighted_rrf_score": 0.04,
            },
        ],
        exact_question_present=True,
    )

    assert ranked[0]["chunk_id"] == "q1"
    assert ranked[1]["chunk_id"] == "compiled-truth:concept:1A432000"
    assert ranked[1]["_provenance_rank_adjustment"] < 0


def test_apply_provenance_ranking_can_trace_without_changing_order() -> None:
    docs = [
        {
            "chunk_id": "compiled-truth:concept:1A432000",
            "_source_group": "compiled_learning_truth",
            "source_type": "compiled_learning_truth",
            "evidence_level": "L2_confirmed",
            "weighted_rrf_score": 0.08,
        },
        {
            "chunk_id": "q1",
            "_source_group": "question_exact_text",
            "source_type": "questions_bank",
            "weighted_rrf_score": 0.04,
        },
    ]

    ranked = apply_provenance_ranking(docs, exact_question_present=True, enabled=False)

    assert [item["chunk_id"] for item in ranked] == [
        "compiled-truth:concept:1A432000",
        "q1",
    ]
    assert ranked[0]["_provenance_features"]["source_group"] == "compiled_learning_truth"
    assert ranked[0]["_provenance_rank_adjustment"] == 0.0


def test_build_ranking_trace_exposes_source_features() -> None:
    trace = build_ranking_trace(
        [
            {
                "chunk_id": "compiled-truth:error:1A432000:E02",
                "_source_group": "compiled_learning_truth",
                "source_type": "compiled_learning_truth",
                "evidence_level": "L1_repeated",
            }
        ],
        authority_order=["exact_question", "compiled_learning_truth"],
        shadow_sources=[
            {
                "chunk_id": "compiled-truth:weak:1A432000:E02",
                "_source_group": "compiled_learning_truth",
                "source_type": "compiled_learning_truth",
                "evidence_level": "L2_confirmed",
            }
        ],
        ranking_policy={"provenance_boost_enabled": False},
    )

    assert trace["fusion"] == "weighted_rrf_with_provenance"
    assert trace["authority_order"] == ["exact_question", "compiled_learning_truth"]
    assert trace["provenance_features"][0]["evidence_level"] == "L1_repeated"
    assert trace["ranking_policy"]["provenance_boost_enabled"] is False
    assert trace["shadow_sources"][0]["chunk_id"] == "compiled-truth:weak:1A432000:E02"
