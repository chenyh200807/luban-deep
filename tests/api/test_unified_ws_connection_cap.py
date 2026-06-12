"""Per-user concurrent WS connection cap — anti fd/memory-exhaustion DoS.

These exercise the in-process fallback path (no Redis configured); the Redis-shared
path uses the same cap semantics via a self-healing ZSET.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("fastapi")

from deeptutor.api.routers import unified_ws as mod


@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the per-process path (no Redis) for deterministic, dependency-free tests.
    monkeypatch.setattr(mod, "_ws_conn_redis_resolved", True)
    monkeypatch.setattr(mod, "_ws_conn_redis", None)
    mod._active_ws_connections.clear()
    yield
    mod._active_ws_connections.clear()


def test_cap_blocks_after_max_concurrent_then_frees_on_release() -> None:
    cap = mod._MAX_WS_CONNECTIONS_PER_USER

    async def _exercise() -> tuple[list[str | None], str | None, str | None]:
        acquired = [await mod._try_acquire_ws_slot("u1") for _ in range(cap)]
        over_cap = await mod._try_acquire_ws_slot("u1")   # one past the cap -> None
        await mod._release_ws_slot("u1", acquired[0])     # free one slot
        after_release = await mod._try_acquire_ws_slot("u1")  # now allowed again
        return acquired, over_cap, after_release

    acquired, over_cap, after_release = asyncio.run(_exercise())
    assert all(t is not None for t in acquired)  # first `cap` connections allowed
    assert over_cap is None                       # cap+1 rejected
    assert after_release is not None              # releasing a slot lets a new one in


def test_cap_is_per_user_not_global() -> None:
    async def _exercise() -> str | None:
        for _ in range(mod._MAX_WS_CONNECTIONS_PER_USER):
            await mod._try_acquire_ws_slot("user_a")
        # a different user is unaffected by user_a saturating their own cap
        return await mod._try_acquire_ws_slot("user_b")

    assert asyncio.run(_exercise()) is not None


def test_release_cleans_up_registry_entry() -> None:
    async def _exercise() -> bool:
        token = await mod._try_acquire_ws_slot("solo")
        await mod._release_ws_slot("solo", token)
        return "solo" in mod._active_ws_connections

    assert asyncio.run(_exercise()) is False  # no leaked zero-count entries
