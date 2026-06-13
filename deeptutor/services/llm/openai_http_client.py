"""LLM client factory — SR4 single authority for OpenAI / Anthropic / Azure SDK construction.

Why this file owns SDK construction (v2.1 SR4): the OpenAI / Anthropic SDKs
default to 600s timeout. A single hung LLM call would pin a turn worker for 10
minutes, cascading into worker starvation under modest load. This factory
injects sane default timeouts and consolidates DISABLE_SSL_VERIFY handling so
the 8 previous direct-construction sites can't disagree.

Public API:
- ``make_openai_client(api_key, base_url, *, timeout, default_headers, ...)``
- ``make_azure_openai_client(api_key, azure_endpoint, api_version, *, timeout, ...)``
- ``make_anthropic_client(api_key, base_url, *, timeout, default_headers, ...)``

Backward-compat (kept for callers that only need the DISABLE_SSL_VERIFY shim):
- ``build_openai_http_client(**kwargs) -> httpx.AsyncClient | None``
- ``openai_client_kwargs(**httpx_kwargs) -> dict[str, Any]``

CI gate: ``scripts/ci/check_llm_client_factory.sh`` forbids direct
``AsyncOpenAI(`` / ``AsyncAnthropic(`` / ``AsyncAzureOpenAI(`` calls anywhere
outside this file.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any
import weakref

from anthropic import AsyncAnthropic
import httpx
from openai import AsyncAzureOpenAI, AsyncOpenAI

from deeptutor.services.llm.exceptions import LLMConfigError
from deeptutor.services.runtime_env import env_flag, is_production_environment

logger = logging.getLogger(__name__)
_warning_lock = threading.Lock()
_warning_logged = False


# ---------------------------------------------------------------------------
# Timeouts (codex review R4: per-provider override; Anthropic long-reasoning can run > 60s)
# ---------------------------------------------------------------------------

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


_LLM_TIMEOUT_TOTAL = _env_float("LLM_TIMEOUT_TOTAL_S", 60.0)
_LLM_TIMEOUT_CONNECT = _env_float("LLM_TIMEOUT_CONNECT_S", 10.0)
_LLM_TIMEOUT_ANTHROPIC = _env_float("LLM_TIMEOUT_ANTHROPIC_TOTAL_S", 180.0)


def default_llm_timeout() -> httpx.Timeout:
    return httpx.Timeout(_LLM_TIMEOUT_TOTAL, connect=_LLM_TIMEOUT_CONNECT)


def default_anthropic_timeout() -> httpx.Timeout:
    return httpx.Timeout(_LLM_TIMEOUT_ANTHROPIC, connect=_LLM_TIMEOUT_CONNECT)


# ---------------------------------------------------------------------------
# SSL verify bypass (dev / test only — never production)
# ---------------------------------------------------------------------------

def disable_ssl_verify_enabled() -> bool:
    if not env_flag("DISABLE_SSL_VERIFY", default=False):
        return False
    if is_production_environment():
        raise LLMConfigError("DISABLE_SSL_VERIFY is not allowed in production")
    global _warning_logged
    with _warning_lock:
        if not _warning_logged:
            logger.warning(
                "SSL verification is disabled via DISABLE_SSL_VERIFY. This is unsafe "
                "and must not be used in production environments."
            )
            _warning_logged = True
    return True


def _shared_httpx_client(*, timeout: httpx.Timeout) -> httpx.AsyncClient:
    """Build a shared httpx.AsyncClient with timeout + DISABLE_SSL_VERIFY honored."""
    return httpx.AsyncClient(timeout=timeout, verify=not disable_ssl_verify_enabled())


# ---------------------------------------------------------------------------
# Factories (SR4 single authority)
# ---------------------------------------------------------------------------

def make_openai_client(
    api_key: str | None,
    base_url: str | None = None,
    *,
    timeout: httpx.Timeout | None = None,
    default_headers: dict[str, str] | None = None,
    max_retries: int = 0,
    **extra: Any,
) -> AsyncOpenAI:
    """Build an AsyncOpenAI client with project-default timeout (60s / 10s connect).

    Pass ``timeout=httpx.Timeout(...)`` to override per-call; leave unset for
    defaults. ``extra`` is passed through to AsyncOpenAI() unchanged.

    NOTE: every call builds a NEW httpx connection pool that is never closed
    (the SDK does not own injected http_clients). High-frequency callers must
    use ``get_pooled_openai_client()`` instead and pass per-call headers via
    the request-level ``extra_headers=`` kwarg.
    """
    timeout = timeout or default_llm_timeout()
    return AsyncOpenAI(
        api_key=api_key or "no-key",
        base_url=base_url,
        default_headers=default_headers,
        max_retries=max_retries,
        http_client=_shared_httpx_client(timeout=timeout),
        **extra,
    )


# Pool keyed by the RUNNING event loop first, then by upstream. An httpx async
# connection pool binds to the event loop it is first used on; the AsyncOpenAI
# client must NOT be shared across loops. Several call sites reach this factory
# from an ephemeral `asyncio.run(...)` inside a worker thread (post-turn topic
# inference, cohort-gated grading adjudicator, rubric batch judge, CLI). A single
# process-global client would either fail in those worker loops or — worse — get
# cached while bound to a loop that asyncio.run() then closes, poisoning every
# subsequent main-loop LLM call. Per-loop caching keeps the main-loop reuse win
# (one pooled client per upstream, no per-call pool leak on the hot path) while
# giving each ephemeral loop its own client that is GC'd when the loop is.
_pooled_clients_by_loop: "weakref.WeakKeyDictionary[Any, dict[tuple[str, str, bool], AsyncOpenAI]]" = (
    weakref.WeakKeyDictionary()
)
_pooled_clients_lock = threading.Lock()


def get_pooled_openai_client(
    api_key: str | None,
    base_url: str | None = None,
) -> AsyncOpenAI:
    """Loop-scoped AsyncOpenAI keyed by (api_key, base_url), sharing one httpx
    connection pool per upstream WITHIN the running event loop — no per-call TLS
    handshake, no leaked sockets waiting on GC on the hot path. The client is
    bound to the loop that is running when it is created; callers in an ephemeral
    ``asyncio.run`` loop transparently get a distinct client for that loop.
    Callers needing a custom timeout or client-level headers should fall back to
    ``make_openai_client()`` and manage the client's lifetime themselves.
    Per-call headers go on the request: ``...create(..., extra_headers=...)``.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (rare sync caller) — return a fresh client; the caller
        # owns its lifetime and there is no loop to scope/reuse against.
        return make_openai_client(api_key, base_url=base_url)
    cache_key = (api_key or "no-key", base_url or "", disable_ssl_verify_enabled())
    with _pooled_clients_lock:
        loop_cache = _pooled_clients_by_loop.get(loop)
        if loop_cache is None:
            loop_cache = {}
            _pooled_clients_by_loop[loop] = loop_cache
        client = loop_cache.get(cache_key)
        if client is None:
            client = make_openai_client(api_key, base_url=base_url)
            loop_cache[cache_key] = client
        return client


def make_azure_openai_client(
    api_key: str | None,
    azure_endpoint: str,
    api_version: str,
    *,
    timeout: httpx.Timeout | None = None,
    default_headers: dict[str, str] | None = None,
    max_retries: int = 0,
    **extra: Any,
) -> AsyncAzureOpenAI:
    timeout = timeout or default_llm_timeout()
    return AsyncAzureOpenAI(
        api_key=api_key or "no-key",
        azure_endpoint=azure_endpoint,
        api_version=api_version,
        default_headers=default_headers,
        max_retries=max_retries,
        http_client=_shared_httpx_client(timeout=timeout),
        **extra,
    )


def make_anthropic_client(
    api_key: str | None,
    base_url: str | None = None,
    *,
    timeout: httpx.Timeout | None = None,
    default_headers: dict[str, str] | None = None,
    max_retries: int = 0,
    **extra: Any,
) -> AsyncAnthropic:
    """Build an AsyncAnthropic client. Default timeout 180s (reasoning models can run long).

    Caller can still override via ``timeout=`` arg.
    """
    timeout = timeout or default_anthropic_timeout()
    kwargs: dict[str, Any] = {
        "max_retries": max_retries,
        "http_client": _shared_httpx_client(timeout=timeout),
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    if default_headers:
        kwargs["default_headers"] = default_headers
    kwargs.update(extra)
    return AsyncAnthropic(**kwargs)


# ---------------------------------------------------------------------------
# Backward-compat helpers (callers that just want DISABLE_SSL_VERIFY handling)
# ---------------------------------------------------------------------------

def build_openai_http_client(**kwargs: Any) -> httpx.AsyncClient | None:
    if not disable_ssl_verify_enabled():
        return None
    return httpx.AsyncClient(verify=False, **kwargs)  # nosec B501


def openai_client_kwargs(**httpx_kwargs: Any) -> dict[str, Any]:
    """Returns ``{"http_client": <client>}`` if DISABLE_SSL_VERIFY is on; else ``{}``.

    Deprecated: prefer ``make_openai_client()`` which handles timeout + ssl together.
    Kept for backward compat with one external call site.
    """
    client = build_openai_http_client(**httpx_kwargs)
    return {"http_client": client} if client is not None else {}
