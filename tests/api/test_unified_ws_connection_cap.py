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


# --- Redis-shared path (redis.asyncio) --------------------------------------
# The per-process tests above force Redis=None. This block exercises the SHARED
# ZSET path with an in-memory ASYNC fake, pinning the async pipeline/zrem wiring:
# pipeline command methods queue synchronously and return the pipe, only execute()
# and zrem are awaited (matching redis.asyncio semantics).


class _FakeAsyncPipeline:
    def __init__(self, store: dict[str, dict[str, float]]) -> None:
        self._store = store
        self._results: list[object] = []

    def zremrangebyscore(self, key: str, min_score: float, max_score: float):
        members = self._store.setdefault(key, {})
        purged = [m for m, s in members.items() if min_score <= s <= max_score]
        for m in purged:
            members.pop(m, None)
        self._results.append(len(purged))
        return self

    def zadd(self, key: str, mapping: dict[str, float]):
        members = self._store.setdefault(key, {})
        added = sum(1 for m in mapping if m not in members)
        members.update(mapping)
        self._results.append(added)
        return self

    def zcard(self, key: str):
        self._results.append(len(self._store.get(key, {})))
        return self

    def expire(self, key: str, ttl: int):
        self._results.append(True)
        return self

    async def execute(self) -> list[object]:
        return self._results


class _FakeAsyncRedis:
    """Minimal in-memory async ZSET mimicking the redis.asyncio surface used here."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, float]] = {}

    def pipeline(self) -> _FakeAsyncPipeline:
        return _FakeAsyncPipeline(self._store)

    async def zrem(self, key: str, member: str) -> int:
        members = self._store.get(key, {})
        return 1 if members.pop(member, None) is not None else 0


def test_redis_shared_path_enforces_cap_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap = mod._MAX_WS_CONNECTIONS_PER_USER
    fake = _FakeAsyncRedis()
    # Override the autouse fixture's Redis=None for this test only.
    monkeypatch.setattr(mod, "_ws_conn_redis", fake)
    monkeypatch.setattr(mod, "_ws_conn_redis_resolved", True)

    async def _exercise() -> tuple[list[str | None], str | None, str | None]:
        acquired = [await mod._try_acquire_ws_slot("ru") for _ in range(cap)]
        over_cap = await mod._try_acquire_ws_slot("ru")        # cap+1 -> rolled back
        await mod._release_ws_slot("ru", acquired[0])          # free one slot
        after_release = await mod._try_acquire_ws_slot("ru")   # allowed again
        return acquired, over_cap, after_release

    acquired, over_cap, after_release = asyncio.run(_exercise())
    assert all(t is not None and t.startswith("redis:") for t in acquired)
    assert over_cap is None
    assert after_release is not None
    # Over-cap reservation was undone via awaited zrem -> ZSET holds exactly `cap`.
    assert len(fake._store["deeptutor:ws-conn:ru"]) == cap
