from deeptutor.tutorbot.response_mode import (
    build_mode_execution_policy,
    normalize_requested_response_mode,
    resolve_requested_response_mode,
)


def test_normalize_requested_response_mode_maps_auto_and_unknown_to_smart():
    assert normalize_requested_response_mode(None) == "smart"
    assert normalize_requested_response_mode("") == "smart"
    assert normalize_requested_response_mode("AUTO") == "smart"
    assert normalize_requested_response_mode("unknown") == "smart"


def test_resolve_requested_response_mode_prefers_explicit_config_then_new_hint_then_legacy_hint():
    assert resolve_requested_response_mode(chat_mode="", interaction_hints=None) == "smart"
    assert resolve_requested_response_mode(
        chat_mode="fast",
        interaction_hints={
            "requested_response_mode": "deep",
            "teaching_mode": "smart",
        },
    ) == "fast"
    assert resolve_requested_response_mode(
        chat_mode="",
        interaction_hints={
            "requested_response_mode": "fast",
            "teaching_mode": "deep",
        },
    ) == "fast"
    assert resolve_requested_response_mode(chat_mode="deep", interaction_hints={}) == "deep"
    assert resolve_requested_response_mode(
        chat_mode="",
        interaction_hints={"requested_response_mode": "fast"},
    ) == "fast"
    assert resolve_requested_response_mode(
        chat_mode="",
        interaction_hints={"teaching_mode": "deep"},
    ) == "deep"


def test_build_mode_execution_policy_returns_expected_budget_shape():
    fast = build_mode_execution_policy("fast")
    smart = build_mode_execution_policy("smart")
    deep = build_mode_execution_policy("deep")

    assert fast.requested_mode == fast.effective_mode == "fast"
    assert smart.requested_mode == smart.effective_mode == "smart"
    assert deep.requested_mode == deep.effective_mode == "deep"
    assert fast.max_tool_rounds == 1
    assert fast.allow_deep_stage is False
    assert fast.response_density == "short"
    assert fast.latency_budget_ms == 6000
    assert smart.max_tool_rounds == 2
    assert smart.allow_deep_stage is False
    assert smart.response_density == "balanced"
    assert smart.latency_budget_ms == 12000
    assert deep.allow_deep_stage is True
    assert deep.max_tool_rounds == 4
    assert deep.response_density == "detailed"
    assert deep.latency_budget_ms == 20000
    assert deep.latency_budget_ms > smart.latency_budget_ms > fast.latency_budget_ms
