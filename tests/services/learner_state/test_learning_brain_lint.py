from __future__ import annotations

from deeptutor.services.learner_state.learning_brain_lint import (
    CONTRADICTED_CLAIM,
    GENERIC_PERSONALIZATION,
    GRAPH_GAP,
    MISSING_NEXT_ACTION,
    STALE_CLAIM_NEEDS_RETEST,
    UNSUPPORTED_CLAIM,
    lint_learning_brain_projection,
)


def test_learning_brain_lint_flags_unsupported_claim() -> None:
    issues = lint_learning_brain_projection({
        "weak_points": [{"concept_id": "1A432000", "claim": "掌握不稳", "evidence_refs": []}],
    })

    assert issues[0]["code"] == UNSUPPORTED_CLAIM


def test_learning_brain_lint_flags_required_personalization_issue_codes() -> None:
    issues = lint_learning_brain_projection(
        {
            "weak_points": [
                {
                    "concept_id": "1A432000",
                    "error_code": "E02",
                    "claim": "掌握不稳",
                    "claim_status": "stale",
                    "evidence_refs": ["evt1"],
                },
                {
                    "concept_id": "1A432000",
                    "error_code": "E03",
                    "claim": "证据冲突",
                    "claim_status": "contradicted",
                    "evidence_refs": ["evt2"],
                    "conflicting_event_ids": ["evt3"],
                },
            ],
            "next_best_actions": [],
            "typed_graph": {"readiness_gaps": [{"code": "missing_training_edge"}]},
            "personalization_context": {
                "next_best_action_candidates": [
                    {"title": "先完成一组练习", "evidence_refs": []}
                ]
            },
        }
    )

    codes = {issue["code"] for issue in issues}
    assert {
        STALE_CLAIM_NEEDS_RETEST,
        CONTRADICTED_CLAIM,
        MISSING_NEXT_ACTION,
        GRAPH_GAP,
        GENERIC_PERSONALIZATION,
    }.issubset(codes)


def test_learning_brain_lint_treats_string_evidence_ref_as_single_ref() -> None:
    issues = lint_learning_brain_projection({
        "weak_points": [{"concept_id": "1A432000", "claim": "掌握不稳", "evidence_refs": "evt_string"}],
        "next_best_actions": [{"title": "先练防水工程", "evidence_refs": "evt_string"}],
    })

    assert not any(issue["code"] == UNSUPPORTED_CLAIM for issue in issues)
