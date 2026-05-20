from __future__ import annotations

from scripts.report_semantic_router_rollout import build_report


def test_report_counts_tutorbot_as_chat_like_shadow_downgrade() -> None:
    report = build_report(
        [
            {
                "semantic_router_mode": "shadow",
                "semantic_router_selected_capability": "tutorbot",
                "semantic_router_shadow_route": "deep_question",
                "turn_semantic_decision": {"confidence": 0.91},
            },
            {
                "semantic_router_mode": "shadow",
                "semantic_router_selected_capability": "chat",
                "semantic_router_shadow_route": "deep_question",
                "turn_semantic_decision": {"confidence": 0.82},
            },
        ]
    )

    assert report["shadow_disagreement_count"] == 2
    assert report["deep_question_to_chat_disagreements"] == 2
