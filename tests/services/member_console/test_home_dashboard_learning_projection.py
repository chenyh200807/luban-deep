from __future__ import annotations

from deeptutor.services.learner_state.home_personalization import build_home_dashboard_learning_projection


def test_home_dashboard_focus_uses_current_weak_point_and_conversation_signal() -> None:
    dashboard = build_home_dashboard_learning_projection(
        weak_nodes=[{"name": "主体结构", "error_label": "多选漏选"}],
        conversation_events=[],
    )

    assert dashboard["today_focus"]["title"] == "今日焦点：主体结构"
    assert "多选漏选" in dashboard["today_focus"]["meta"]
    assert dashboard["today_focus"]["intent"]["concept_label"] == "主体结构"
    assert dashboard["recommended_prompts"][0]["intent"]["source"] == "home_dashboard"
    assert len({item["prompt_type"] for item in dashboard["recommended_prompts"]}) > 1


def test_home_dashboard_falls_back_when_no_learning_facts() -> None:
    dashboard = build_home_dashboard_learning_projection(
        weak_nodes=[],
        conversation_events=[],
        subject_id="unknown",
    )

    assert dashboard["source_status"]["fallback_used"] is True
    assert dashboard["recommended_prompts"][0]["intent"]["reason"] == "starter"
