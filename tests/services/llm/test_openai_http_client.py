from __future__ import annotations

import pytest

from deeptutor.services.llm.exceptions import LLMConfigError


def test_openai_http_client_not_created_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeptutor.services.llm.openai_http_client import openai_client_kwargs

    monkeypatch.delenv("DISABLE_SSL_VERIFY", raising=False)

    assert openai_client_kwargs() == {}


def test_openai_http_client_rejects_disabled_tls_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.llm.openai_http_client import openai_client_kwargs

    monkeypatch.setenv("DISABLE_SSL_VERIFY", "1")
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")

    with pytest.raises(LLMConfigError, match="DISABLE_SSL_VERIFY is not allowed in production"):
        openai_client_kwargs()


def test_pooled_client_is_scoped_per_event_loop() -> None:
    """A pooled AsyncOpenAI binds its httpx pool to the loop it is created on.
    The same loop must reuse one client (pool reuse / leak fix), but a distinct
    loop — e.g. an ephemeral asyncio.run in a worker thread doing post-turn topic
    inference or cohort-gated grading — must get its OWN client, never the one
    bound to (and possibly closed with) another loop. Regression for the pooling
    change that would otherwise poison the main loop's client."""
    import asyncio

    from deeptutor.services.llm.openai_http_client import get_pooled_openai_client

    async def _two_in_one_loop() -> tuple[object, object]:
        a = get_pooled_openai_client("k", base_url="https://pool-scope.example.com")
        b = get_pooled_openai_client("k", base_url="https://pool-scope.example.com")
        return a, b

    loop_a_first, loop_a_second = asyncio.run(_two_in_one_loop())
    # Same loop -> same instance (reuse, no per-call pool).
    assert loop_a_first is loop_a_second

    loop_b_only, _ = asyncio.run(_two_in_one_loop())
    # Different loop -> different instance (no cross-loop sharing/poisoning).
    assert loop_b_only is not loop_a_first


def test_pooled_client_without_running_loop_returns_fresh() -> None:
    """Called with no running loop (rare sync caller), the factory returns a fresh
    client the caller owns, rather than caching against a non-existent loop."""
    from deeptutor.services.llm.openai_http_client import get_pooled_openai_client

    first = get_pooled_openai_client("k", base_url="https://no-loop.example.com")
    second = get_pooled_openai_client("k", base_url="https://no-loop.example.com")
    assert first is not second
