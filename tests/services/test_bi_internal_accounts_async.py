from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.api.routers import bi as bi_router
from deeptutor.services.bi_service import BIService


def _service_with_rest(
    monkeypatch: pytest.MonkeyPatch,
    rest,
) -> BIService:
    service = object.__new__(BIService)
    service._internal_exclusion_cache = None
    monkeypatch.setattr(service, "_supabase_internal_accounts", rest)
    return service


def test_internal_accounts_endpoint_reads_one_snapshot_and_applies_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "id": "audit-3",
            "user_id": "user-a",
            "is_internal": False,
            "operator_id": "admin",
            "reason": "remove marker",
            "created_at": "2026-07-22T03:00:00Z",
        },
        {
            "id": "audit-2",
            "user_id": "user-b",
            "is_internal": True,
            "operator_id": "admin",
            "reason": "test account",
            "created_at": "2026-07-22T02:00:00Z",
        },
        {
            "id": "audit-1",
            "user_id": "user-a",
            "is_internal": True,
            "operator_id": "admin",
            "reason": "old marker",
            "created_at": "2026-07-22T01:00:00Z",
        },
    ]
    calls: list[tuple[str, dict[str, Any]]] = []

    def rest(method: str, *, params=None, body=None):
        calls.append((method, dict(params or {})))
        return rows

    service = _service_with_rest(monkeypatch, rest)
    monkeypatch.setattr(bi_router, "get_bi_service", lambda: service)

    payload = asyncio.run(
        bi_router.bi_internal_accounts(
            limit=2,
            auth=SimpleNamespace(user_id="admin"),
        )
    )

    assert calls == [
        (
            "GET",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "2000",
            },
        )
    ]
    assert payload["audit"] == rows[:2]
    assert payload["states"] == {"user-a": rows[0], "user-b": rows[1]}
    assert payload["available"] is True
    assert payload["internal_accounts"] == [rows[1]]
    assert payload["total_internal"] == 1


def test_internal_accounts_snapshot_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rest(method: str, *, params=None, body=None):
        assert method == "GET"
        time.sleep(0.08)
        return []

    service = _service_with_rest(monkeypatch, rest)

    async def scenario() -> None:
        request = asyncio.create_task(service.get_internal_accounts_snapshot(limit=10))
        ticks = 0
        while not request.done():
            ticks += 1
            await asyncio.sleep(0.005)
        payload = request.result()
        assert ticks >= 3, "event-loop ticker must keep running while REST waits in a worker thread"
        assert payload["states"] == {}
        assert payload["available"] is True

    asyncio.run(scenario())


def test_mark_internal_account_does_not_block_event_loop_and_invalidates_exclusion_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted = {
        "user_id": "user-a",
        "is_internal": True,
        "operator_id": "admin",
        "reason": "automation account",
    }

    def rest(method: str, *, params=None, body=None):
        assert method == "POST"
        assert body == posted
        time.sleep(0.08)
        return [{**posted, "id": "audit-new"}]

    service = _service_with_rest(monkeypatch, rest)
    service._internal_exclusion_cache = (time.monotonic(), frozenset({"old-user"}))

    async def scenario() -> None:
        request = asyncio.create_task(
            service.mark_internal_account(
                user_id="user-a",
                is_internal=True,
                operator_id="admin",
                reason="automation account",
            )
        )
        ticks = 0
        while not request.done():
            ticks += 1
            await asyncio.sleep(0.005)
        result = request.result()
        assert ticks >= 3, "event-loop ticker must keep running while POST waits in a worker thread"
        assert result["id"] == "audit-new"

    asyncio.run(scenario())
    assert service._internal_exclusion_cache is None
