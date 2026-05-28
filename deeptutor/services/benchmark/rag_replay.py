"""RAG interception shim for record/replay (harness 9+ roadmap H3 — RAG真实面 coverage).

Wraps the canonical RAG query entry (``RAGPipeline.search``) so a turn's
retrieval results can be recorded once (live, against the real KB) and
replayed deterministically (zero network / zero KB / zero key). Only the
non-deterministic retrieval call is intercepted; the rest of the pipeline
executes normally — the record-and-replay principle.

Scope (deliberately minimal, parallels ``llm_replay``): provides the wrapper
functions only. Actual wiring into production code (swap
``RAGPipeline.search`` with the wrapper) is done at integration time;
recording itself requires either a reachable RAG/embedding stack or a prior
cassette dump.

The recorded value is stored in the cassette's ``tool`` slot via the standard
``tool_key`` — single Cassette authority, no parallel store. The shim
just provides the key recipe (``rag.search.{kb}`` namespace) and the
record/replay wrapper closures.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from deeptutor.services.benchmark.cassette import Cassette, tool_key

# A search call: (query, kb_name, **kwargs) -> dict. We type the wrappers
# loosely (``Any``) so they slot in cleanly as a replacement for
# ``RAGPipeline.search`` regardless of the concrete return shape.
RAGSearchFn = Callable[..., Awaitable[Any]]


def search_key(*, kb_name: str, query: str, kwargs: dict[str, Any] | None = None) -> str:
    """Cassette key for one ``RAGPipeline.search`` call.

    Namespaced under ``rag.search.{kb_name}`` so a stray ``tool_key`` collision
    with a real tool of the same name is impossible. ``kwargs`` is digested
    in full so any retriever knob (top_k, filter, etc.) that affects the
    distribution is part of the key.
    """
    return tool_key(
        name=f"rag.search.{kb_name}",
        args={"query": query, "kwargs": dict(kwargs or {})},
    )


def build_recording_search(real_search: RAGSearchFn, cassette: Cassette) -> RAGSearchFn:
    """Wrap ``real_search``: call it live, record the dict result, return it."""

    async def _search(query: str, kb_name: str, **kwargs: Any) -> Any:
        result = await real_search(query, kb_name, **kwargs)
        cassette.record_tool(search_key(kb_name=kb_name, query=query, kwargs=kwargs), result)
        return result

    return _search


def build_replaying_search(cassette: Cassette) -> RAGSearchFn:
    """Replay the recorded retrieval for a call; raise on a cassette miss.

    A miss means the query / kb / kwargs drifted from the recording — exactly
    the determinism-regression signal we want surfaced (parallel to
    ``llm_replay.build_replaying_stream``), not silently swallowed.
    """

    async def _search(query: str, kb_name: str, **kwargs: Any) -> Any:
        return cassette.replay_tool(
            search_key(kb_name=kb_name, query=query, kwargs=kwargs)
        )

    return _search
