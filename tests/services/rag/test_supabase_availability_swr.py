"""Battle2 S5-T3: the Supabase Data API availability gate serves the cached
verdict with stale-while-revalidate expiry — a user turn never waits on the
~0.3s probe once a verdict exists; a single-flight background task refreshes
expired entries. Cold start (no cached verdict) probes inline (old behavior).
Known-restricted (402) stays fail-closed.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from deeptutor.services.rag.exceptions import RAGSearchError
from deeptutor.services.rag.pipelines import supabase as supabase_module


@pytest.fixture(autouse=True)
def _clear_availability_state():
    supabase_module._SUPABASE_AVAILABILITY_CACHE.clear()
    supabase_module._SUPABASE_AVAILABILITY_REFRESH.clear()
    yield
    supabase_module._SUPABASE_AVAILABILITY_CACHE.clear()
    supabase_module._SUPABASE_AVAILABILITY_REFRESH.clear()


def _config():
    return supabase_module.SupabaseSearchConfig(
        url="https://example.supabase.co",
        service_key="test-key",  # pragma: allowlist secret
        timeout_s=5.0,
        sources=["standard"],
        include_questions=True,
        top_k=2,
        fetch_count=4,
        match_threshold=0.5,
        vector_weight=1.0,
        text_weight=1.0,
        source_weights={},
        question_weights={},
        max_per_document=2,
        query_expansion_enabled=False,
        max_query_variants=1,
        second_pass_enabled=False,
        second_pass_max_queries=1,
        second_pass_min_hits=1,
        second_pass_max_dup_ratio=1.0,
        rerank_enabled=False,
        rerank_window=2,
        rerank_timeout_s=2.0,
        exact_question_enabled=False,
        exact_question_text_first=False,
        exact_question_min_similarity=0.9,
        exact_question_max_text_len=128,
        exact_question_text_rpc_enabled=False,
    )


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.supabase.co/rest/v1/kb_chunks")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)


class _FakeClient:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.get_calls = 0

    async def get(self, url, headers=None, params=None):
        _ = (url, headers, params)
        self.get_calls += 1
        return _FakeResponse(self.status_code)


def _cache_key(config) -> str:
    return config.url.rstrip("/")


@pytest.mark.asyncio
async def test_stale_available_entry_serves_turn_and_refreshes_in_background(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    turn_client = _FakeClient()
    refresh_client = _FakeClient()
    monkeypatch.setattr(pipeline, "_get_client", lambda *a, **k: _async_return(refresh_client))

    stale_at = time.monotonic() - supabase_module._SUPABASE_AVAILABILITY_TTL_S - 1
    supabase_module._SUPABASE_AVAILABILITY_CACHE[_cache_key(config)] = (True, stale_at)

    await pipeline._assert_data_api_available(client=turn_client, config=config)

    assert turn_client.get_calls == 0  # the turn never probed
    refresh_task = supabase_module._SUPABASE_AVAILABILITY_REFRESH.get(_cache_key(config))
    assert refresh_task is not None
    await refresh_task
    assert refresh_client.get_calls == 1  # background probe ran
    is_available, checked_at = supabase_module._SUPABASE_AVAILABILITY_CACHE[_cache_key(config)]
    assert is_available is True
    assert checked_at > stale_at  # verdict timestamp refreshed


@pytest.mark.asyncio
async def test_stale_restricted_entry_still_fails_closed_then_recovers(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    turn_client = _FakeClient()
    refresh_client = _FakeClient(status_code=200)
    monkeypatch.setattr(pipeline, "_get_client", lambda *a, **k: _async_return(refresh_client))

    stale_at = time.monotonic() - supabase_module._SUPABASE_AVAILABILITY_TTL_S - 1
    supabase_module._SUPABASE_AVAILABILITY_CACHE[_cache_key(config)] = (False, stale_at)

    with pytest.raises(RAGSearchError) as excinfo:
        await pipeline._assert_data_api_available(client=turn_client, config=config)
    assert excinfo.value.retryable is False
    assert "402" in str(excinfo.value)
    assert turn_client.get_calls == 0

    refresh_task = supabase_module._SUPABASE_AVAILABILITY_REFRESH.get(_cache_key(config))
    assert refresh_task is not None
    await refresh_task  # probe recovers the verdict

    await pipeline._assert_data_api_available(client=turn_client, config=config)  # now passes
    assert turn_client.get_calls == 0


@pytest.mark.asyncio
async def test_cold_start_probes_inline_once(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    client = _FakeClient()

    await pipeline._assert_data_api_available(client=client, config=config)

    assert client.get_calls == 1
    assert supabase_module._SUPABASE_AVAILABILITY_CACHE[_cache_key(config)][0] is True
    assert _cache_key(config) not in supabase_module._SUPABASE_AVAILABILITY_REFRESH


@pytest.mark.asyncio
async def test_refresh_is_single_flight(monkeypatch) -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    gate = asyncio.Event()
    probe_calls = 0

    async def _slow_probe(*, client, config):
        nonlocal probe_calls
        probe_calls += 1
        await gate.wait()
        supabase_module._SUPABASE_AVAILABILITY_CACHE[_cache_key(config)] = (
            True,
            time.monotonic(),
        )

    monkeypatch.setattr(pipeline, "_probe_data_api", _slow_probe)
    monkeypatch.setattr(pipeline, "_get_client", lambda *a, **k: _async_return(_FakeClient()))

    stale_at = time.monotonic() - supabase_module._SUPABASE_AVAILABILITY_TTL_S - 1
    supabase_module._SUPABASE_AVAILABILITY_CACHE[_cache_key(config)] = (True, stale_at)

    turn_client = _FakeClient()
    await pipeline._assert_data_api_available(client=turn_client, config=config)
    first_task = supabase_module._SUPABASE_AVAILABILITY_REFRESH[_cache_key(config)]
    await pipeline._assert_data_api_available(client=turn_client, config=config)
    second_task = supabase_module._SUPABASE_AVAILABILITY_REFRESH[_cache_key(config)]

    assert first_task is second_task  # no duplicate in-flight refresh
    gate.set()
    await first_task
    assert probe_calls == 1


@pytest.mark.asyncio
async def test_cold_start_402_fails_closed_and_caches_restricted() -> None:
    pipeline = supabase_module.SupabasePipeline()
    config = _config()
    client = _FakeClient(status_code=402)

    with pytest.raises(RAGSearchError) as excinfo:
        await pipeline._assert_data_api_available(client=client, config=config)

    assert excinfo.value.retryable is False
    assert supabase_module._SUPABASE_AVAILABILITY_CACHE[_cache_key(config)][0] is False

    # Within TTL the restricted verdict keeps failing closed without re-probing.
    with pytest.raises(RAGSearchError):
        await pipeline._assert_data_api_available(client=client, config=config)
    assert client.get_calls == 1


async def _async_return(value):
    return value
