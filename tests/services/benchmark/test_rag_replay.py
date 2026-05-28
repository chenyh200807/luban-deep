"""Tests for RAG record/replay wrapper (offline, no network).

Validates the key contract + record/replay round-trip with an injected fake
``search`` so the deterministic-RAG path is provably correct before a real
KB / staging is ever reached (mirrors ``test_llm_replay`` shape).
"""

from __future__ import annotations

import asyncio

import pytest

from deeptutor.services.benchmark.cassette import Cassette
from deeptutor.services.benchmark.rag_replay import (
    build_recording_search,
    build_replaying_search,
    search_key,
)


def test_search_key_is_stable_across_kwarg_order() -> None:
    k1 = search_key(kb_name="kb1", query="q", kwargs={"top_k": 3, "filter": "x"})
    k2 = search_key(kb_name="kb1", query="q", kwargs={"filter": "x", "top_k": 3})
    assert k1 == k2


def test_search_key_changes_with_kb_query_or_kwargs() -> None:
    base = search_key(kb_name="kb1", query="q", kwargs={"top_k": 3})
    assert base != search_key(kb_name="kb2", query="q", kwargs={"top_k": 3})
    assert base != search_key(kb_name="kb1", query="q2", kwargs={"top_k": 3})
    assert base != search_key(kb_name="kb1", query="q", kwargs={"top_k": 5})


def test_record_then_replay_round_trips_the_dict() -> None:
    cassette = Cassette()
    recorded = {"chunks": [{"content": "c1", "score": 0.9}, {"content": "c2", "score": 0.8}]}

    async def real_search(query: str, kb_name: str, **kwargs):
        return recorded  # the "live" call

    async def main() -> None:
        # 1) recording pass: stores into cassette
        rec = build_recording_search(real_search, cassette)
        assert await rec("query", "kb1", top_k=2) == recorded
        # 2) replay pass: returns the same dict, never touches real_search
        async def real_search_should_not_be_called(*a, **k):  # noqa: ARG001
            raise AssertionError("replay must not call live search")

        rep = build_replaying_search(cassette)
        assert await rep("query", "kb1", top_k=2) == recorded

    asyncio.run(main())


def test_replay_miss_raises_keyerror_on_drift() -> None:
    """A miss is the regression/drift signal — must NOT silently swallow."""
    rep = build_replaying_search(Cassette())  # empty cassette

    async def main() -> None:
        with pytest.raises(KeyError, match="cassette miss"):
            await rep("any query", "any_kb")

    asyncio.run(main())
