from deeptutor.tutorbot.response_mode import (
    build_mode_execution_policy,
    normalize_requested_response_mode,
    resolve_requested_response_mode,
    select_response_mode,
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
    smart = build_mode_execution_policy("smart", selected_mode="fast")
    deep = build_mode_execution_policy("deep")

    assert fast.requested_mode == fast.effective_mode == fast.selected_mode == "fast"
    assert smart.requested_mode == "smart"
    assert smart.effective_mode == smart.selected_mode == "fast"
    assert deep.requested_mode == deep.effective_mode == deep.selected_mode == "deep"
    assert fast.max_tool_rounds == 1
    assert fast.allow_deep_stage is False
    assert fast.response_density == "short"
    assert fast.latency_budget_ms == 6000
    assert fast.preferred_model == "qwen3.5-flash"
    assert smart.max_tool_rounds == 1
    assert smart.allow_deep_stage is False
    assert smart.response_density == "short"
    assert smart.latency_budget_ms == 6000
    assert smart.preferred_model == "qwen3.5-flash"
    assert deep.allow_deep_stage is True
    assert deep.max_tool_rounds == 4
    assert deep.response_density == "detailed"
    assert deep.latency_budget_ms == 20000
    assert deep.preferred_model == ""
    assert deep.latency_budget_ms > fast.latency_budget_ms


def test_select_response_mode_routes_smart_between_fast_and_deep() -> None:
    selected_fast, fast_reason = select_response_mode(
        "smart",
        user_message="什么是流水节拍，简单说一下",
        interaction_hints={},
        has_active_object=False,
    )
    selected_deep, deep_reason = select_response_mode(
        "smart",
        user_message="请基于同一个案例，详细对比两次变更后的招投标与合同管理风险",
        interaction_hints={"current_info_required": True},
        has_active_object=True,
    )

    assert selected_fast == "fast"
    assert "simple_explainer" in fast_reason
    assert selected_deep == "deep"
    assert "active_object" in deep_reason
