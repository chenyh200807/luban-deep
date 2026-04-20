from __future__ import annotations

from deeptutor.services.observability.aae_scores import build_turn_aae_metadata


def test_build_turn_aae_metadata_marks_proxy_and_coverage() -> None:
    payload = build_turn_aae_metadata(
        trace_metadata={
            "context_route": "active_question_followup",
            "question_followup_context": {
                "is_correct": True,
            },
        },
        assistant_event_summary={
            "sources": [{"title": "规范依据"}],
        },
        terminal_status="completed",
        turn_duration_ms=5200.0,
        surface_turn_summary={
            "first_visible_content_rendered": 1,
            "done_rendered": 1,
            "surface_render_failed": 0,
        },
    )

    scores = payload["aae_scores"]
    assert scores["correctness_score"]["value"] == 1.0
    assert scores["groundedness_score"]["is_proxy"] is True
    assert scores["continuity_score"]["value"] == 1.0
    assert scores["surface_render_score"]["value"] == 1.0
    assert scores["latency_class"]["value"] == "fast"
    assert scores["paid_student_satisfaction_score"]["is_proxy"] is True
    assert payload["aae_composite"] == {
        "value": 1.0,
        "coverage_ratio": 1.0,
        "input_count": 5,
        "is_proxy": True,
    }
    assert "proxy" in payload["aae_review_note"]
