from __future__ import annotations

from deeptutor.services.llm.executors import _apply_provider_thinking_mode


def test_deepseek_executor_disables_thinking_by_default() -> None:
    payload: dict[str, object] = {}

    _apply_provider_thinking_mode(
        payload,
        provider_name="deepseek",
        reasoning_effort=None,
    )

    assert payload == {"extra_body": {"thinking": {"type": "disabled"}}}


def test_deepseek_executor_enables_thinking_only_when_explicit() -> None:
    payload: dict[str, object] = {}

    _apply_provider_thinking_mode(
        payload,
        provider_name="deepseek",
        reasoning_effort="high",
    )

    assert payload == {
        "reasoning_effort": "high",
        "extra_body": {"thinking": {"type": "enabled"}},
    }


def test_non_deepseek_executor_keeps_existing_reasoning_effort_behavior() -> None:
    payload: dict[str, object] = {}

    _apply_provider_thinking_mode(
        payload,
        provider_name="openai",
        reasoning_effort="high",
    )

    assert payload == {"reasoning_effort": "high"}
