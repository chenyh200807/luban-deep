from __future__ import annotations

from typing import Any

from deeptutor.services.member_console.directory import SupabaseMemberDirectoryReadModel


class _FakeResponse:
    def __init__(self, payload: list[dict[str, Any]]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict[str, Any]]:
        return self._payload


class _PagedClient:
    def __init__(self, rows: list[dict[str, Any]], *, page_cap: int = 1000) -> None:
        self.rows = rows
        self.page_cap = page_cap
        self.calls: list[dict[str, Any]] = []

    def get(self, _url: str, *, headers: dict[str, str], params: dict[str, Any]) -> _FakeResponse:
        del headers
        self.calls.append(dict(params))
        offset = int(params.get("offset") or 0)
        requested_limit = int(params.get("limit") or self.page_cap)
        capped_limit = min(requested_limit, self.page_cap)
        return _FakeResponse(self.rows[offset : offset + capped_limit])


def _row(index: int) -> dict[str, Any]:
    return {
        "user_id": f"user-{index:04d}",
        "identifier": f"user-{index:04d}",
        "phone": "",
        "display_name": "",
        "profession": "",
        "exam_target": "",
        "plan_id": "",
        "balance_micros": 0,
        "frozen_micros": 0,
        "wallet_created_at": "",
        "wallet_updated_at": "",
        "first_chat_at": "",
        "last_chat_at": "",
        "total_conversations": 0,
        "total_messages": 0,
        "has_user_record": True,
        "has_wallet": False,
        "has_profile": False,
        "has_chat_history": False,
    }


def test_member_directory_paginates_past_single_postgrest_page_cap() -> None:
    client = _PagedClient([_row(index) for index in range(2401)], page_cap=1000)
    directory = SupabaseMemberDirectoryReadModel(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )

    members = directory.list_members(limit=2401)

    assert len(members) == 2401
    assert members[0]["user_id"] == "user-0000"
    assert members[-1]["user_id"] == "user-2400"
    assert [call["offset"] for call in client.calls] == [0, 1000, 2000]
    assert [call["limit"] for call in client.calls] == [1000, 1000, 401]


def test_member_directory_stops_on_short_page() -> None:
    client = _PagedClient([_row(index) for index in range(1001)], page_cap=1000)
    directory = SupabaseMemberDirectoryReadModel(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )

    members = directory.list_members(limit=5000)

    assert len(members) == 1001
    assert [call["offset"] for call in client.calls] == [0, 1000]
    assert [call["limit"] for call in client.calls] == [1000, 1000]
