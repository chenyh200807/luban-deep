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


def test_non_deepseek_executor_empty_effort_is_noop() -> None:
    # 其他 provider 兜底路径逐字不变:空 effort 不发任何参数。
    payload: dict[str, object] = {}

    _apply_provider_thinking_mode(
        payload,
        provider_name="openai",
        reasoning_effort=None,
    )

    assert payload == {}


# --- dashscope 分支(本次修复:此前命中 deepseek 提前 return,thinking 空转)---

def test_dashscope_executor_disables_thinking_only_when_explicit_disabled() -> None:
    payload: dict[str, object] = {}

    _apply_provider_thinking_mode(
        payload,
        provider_name="dashscope",
        reasoning_effort="disabled",
    )

    # 与 tutorbot openai_compat 路径一致:dashscope 用 enable_thinking=False。
    assert payload == {"extra_body": {"enable_thinking": False}}


def test_dashscope_executor_empty_effort_sends_no_thinking_param() -> None:
    # 零回归红线:空 effort 的 dashscope 调用不被关思考(保持 provider 默认=思考)。
    payload: dict[str, object] = {}

    _apply_provider_thinking_mode(
        payload,
        provider_name="dashscope",
        reasoning_effort=None,
    )

    assert payload == {}


def test_dashscope_executor_non_disabled_effort_passes_through() -> None:
    # 非 disabled 的显式 effort 透传 reasoning_effort,不发 enable_thinking。
    payload: dict[str, object] = {}

    _apply_provider_thinking_mode(
        payload,
        provider_name="dashscope",
        reasoning_effort="high",
    )

    assert payload == {"reasoning_effort": "high"}


def test_dashscope_executor_recognizes_all_disabled_aliases() -> None:
    for alias in ("minimal", "none", "disabled", "off", "false", "0", "OFF", " none "):
        payload: dict[str, object] = {}
        _apply_provider_thinking_mode(
            payload,
            provider_name="dashscope",
            reasoning_effort=alias,
        )
        assert payload == {"extra_body": {"enable_thinking": False}}, alias
