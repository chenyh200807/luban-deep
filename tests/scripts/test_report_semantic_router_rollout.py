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


from scripts.report_semantic_router_rollout import build_telemetry_report


def _tele(**kw):
    base = {
        "semantic_router_telemetry": {
            "captured_raw_input": kw.get("inp", "x"),
            "semantic_decision": {"next_action": kw.get("na", "route_to_grading")},
            "final_executed_capability": kw.get("cap", "deep_question"),
            "drove_route": kw.get("drove", True),
            "is_default_template": kw.get("tmpl", False),
            "mode": kw.get("mode", "primary"),
        }
    }
    return base


def test_telemetry_report_separates_judgeable_from_non_discriminative() -> None:
    records = [
        _tele(drove=True, tmpl=False, na="route_to_grading"),       # judgeable
        _tele(drove=True, tmpl=False, na="route_to_generation"),    # judgeable
        _tele(drove=True, tmpl=True, na="route_to_generation"),     # default template -> excluded
        _tele(drove=False, tmpl=False, na="route_to_grading"),      # lifecycle override -> excluded
    ]
    report = build_telemetry_report(records)

    assert report["total"] == 4
    assert report["drove_route_count"] == 3
    assert report["default_template_count"] == 1
    # judgeable = drove_route AND not default_template
    assert report["judgeable_count"] == 2
    assert report["non_discriminative_excluded"] == 2


def test_telemetry_report_buckets_by_next_action_on_judgeable() -> None:
    records = [
        _tele(drove=True, tmpl=False, na="route_to_grading"),
        _tele(drove=True, tmpl=False, na="route_to_grading"),
        _tele(drove=True, tmpl=False, na="route_to_followup_explainer"),
    ]
    report = build_telemetry_report(records)

    assert report["judgeable_by_next_action"]["route_to_grading"] == 2
    assert report["judgeable_by_next_action"]["route_to_followup_explainer"] == 1


def test_telemetry_report_flags_decision_capability_mismatch() -> None:
    # decision said generation/deep_question but ran as chat -> mismatch
    records = [
        {
            "semantic_router_telemetry": {
                "captured_raw_input": "建筑构造是什么？",
                "semantic_decision": {"next_action": "route_to_generation"},
                "final_executed_capability": "chat",
                "drove_route": False,
                "is_default_template": True,
                "mode": "disabled",
            }
        }
    ]
    report = build_telemetry_report(records)
    assert report["total"] == 1
    assert report["judgeable_count"] == 0
