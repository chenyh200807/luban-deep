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
    def __init__(
        self,
        *,
        member_rows: list[dict[str, Any]],
        alias_rows: list[dict[str, Any]],
        user_rows: list[dict[str, Any]] | None = None,
        page_cap: int = 1000,
    ) -> None:
        self.rows_by_table = {
            "v_members": member_rows,
            "user_identity_aliases": alias_rows,
            "users": user_rows or [],
        }
        self.page_cap = page_cap
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, Any]) -> _FakeResponse:
        del headers
        table = url.rstrip("/").rsplit("/", 1)[-1]
        self.calls.append({"table": table, **dict(params)})
        rows = list(self.rows_by_table[table])
        id_column = "user_id" if table == "v_members" else "id" if table == "users" else ""
        id_filter = str(params.get(id_column) or "")
        if id_column and id_filter.startswith("in.(") and id_filter.endswith(")"):
            requested_ids = set(id_filter[4:-1].split(","))
            rows = [row for row in rows if str(row.get(id_column) or "") in requested_ids]
        order = str(params.get("order") or "")
        if table == "user_identity_aliases" and any("created_at" in row for row in rows):
            rows = sorted(rows, key=lambda row: str(row.get("user_id") or ""))
            rows = sorted(
                rows,
                key=lambda row: str(row.get("created_at") or ""),
                reverse="created_at.desc" in order,
            )
        offset = int(params.get("offset") or 0)
        requested_limit = int(params.get("limit") or self.page_cap)
        capped_limit = min(requested_limit, self.page_cap)
        return _FakeResponse(rows[offset : offset + capped_limit])


def _member_row(index: int, *, phone: str = "") -> dict[str, Any]:
    return {
        "user_id": f"user-{index:04d}",
        "identifier": f"user-{index:04d}",
        "phone": phone,
        "display_name": "",
        "profession": "",
        "exam_target": "",
        "plan_id": "",
        "balance_micros": 0,
        "frozen_micros": 0,
        "wallet_created_at": "",
        "wallet_updated_at": "",
        "has_user_record": True,
        "has_wallet": False,
        "has_profile": False,
    }


def _phone_alias(
    index: int,
    *,
    source: str = "phone_backfill",
    phone: str | None = None,
    created_at: str = "",
    verified_at: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "user_id": f"user-{index:04d}",
        "alias_value": phone or f"1555886{index:04d}",
        "source": source,
    }
    if created_at:
        row["created_at"] = created_at
    if verified_at:
        row["verified_at"] = verified_at
    if metadata is not None:
        row["metadata"] = metadata
    return row


def _directory(client: _PagedClient) -> SupabaseMemberDirectoryReadModel:
    return SupabaseMemberDirectoryReadModel(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )


def test_member_directory_paginates_trusted_phone_aliases_past_single_postgrest_page_cap() -> None:
    client = _PagedClient(
        member_rows=[_member_row(index) for index in range(2401)],
        alias_rows=[_phone_alias(index) for index in range(2401)],
        page_cap=1000,
    )

    members = _directory(client).list_members(limit=2401)

    assert len(members) == 2401
    assert members[0]["user_id"] == "user-0000"
    assert members[-1]["user_id"] == "user-2400"
    alias_calls = [call for call in client.calls if call["table"] == "user_identity_aliases"]
    assert [call["offset"] for call in alias_calls] == [0, 1000, 2000]
    assert [call["limit"] for call in alias_calls] == [1000, 1000, 1000]


def test_member_directory_batches_member_queries_before_postgrest_url_limit() -> None:
    client = _PagedClient(
        member_rows=[_member_row(index) for index in range(635)],
        alias_rows=[_phone_alias(index) for index in range(635)],
        user_rows=[
            {
                "id": f"user-{index:04d}",
                "identifier": f"user-{index:04d}",
                "createdAt": "",
                "metadata": {},
                "phone": "",
            }
            for index in range(635)
        ],
    )

    members = _directory(client).list_members(limit=635)

    assert len(members) == 635
    for table, id_column in (("v_members", "user_id"), ("users", "id")):
        calls = [call for call in client.calls if call["table"] == table]
        assert len(calls) > 1
        assert max(len(str(call[id_column])[4:-1].split(",")) for call in calls) <= 100


def test_member_directory_stops_on_short_phone_alias_page() -> None:
    client = _PagedClient(
        member_rows=[_member_row(index) for index in range(1001)],
        alias_rows=[_phone_alias(index) for index in range(1001)],
        page_cap=1000,
    )

    members = _directory(client).list_members(limit=5000)

    assert len(members) == 1001
    alias_calls = [call for call in client.calls if call["table"] == "user_identity_aliases"]
    assert [call["offset"] for call in alias_calls] == [0, 1000]
    assert [call["limit"] for call in alias_calls] == [1000, 1000]


def test_member_directory_excludes_public_users_backfill_phone_aliases() -> None:
    client = _PagedClient(
        member_rows=[_member_row(1), _member_row(2)],
        alias_rows=[
            _phone_alias(1, source="public_users_backfill", phone="15558860001"),
            _phone_alias(2, source="phone_backfill", phone="15558860002"),
        ],
    )

    members = _directory(client).list_members(limit=10)

    assert [member["user_id"] for member in members] == ["user-0002"]
    assert members[0]["phone"] == "15558860002"


def test_member_directory_uses_phone_alias_when_member_view_has_no_row() -> None:
    client = _PagedClient(
        member_rows=[],
        alias_rows=[_phone_alias(1, source="phone_verification", phone="15558860001")],
    )

    members = _directory(client).list_members(limit=10)

    assert len(members) == 1
    assert members[0]["user_id"] == "user-0001"
    assert members[0]["phone"] == "15558860001"
    assert members[0]["member_directory_source"] == "supabase.phone_identity_aliases+v_members"


def test_member_directory_prefers_recent_phone_alias_candidates_past_read_cap() -> None:
    client = _PagedClient(
        member_rows=[],
        alias_rows=[
            *[
                _phone_alias(
                    index,
                    source="phone_backfill",
                    phone=f"1555886{index:04d}",
                    created_at=f"2026-06-01T00:{index:02d}:00+00:00",
                )
                for index in range(10)
            ],
            _phone_alias(
                99,
                source="phone_verification",
                phone="15558860099",
                created_at="2026-07-08T12:00:00+00:00",
                verified_at="2026-07-08T12:01:00+00:00",
            ),
        ],
        page_cap=4,
    )

    members = _directory(client).list_members(limit=1)

    assert [member["user_id"] for member in members] == ["user-0099"]
    assert members[0]["created_at"] == "2026-07-08T12:01:00+00:00"
    alias_calls = [call for call in client.calls if call["table"] == "user_identity_aliases"]
    assert alias_calls[0]["order"] == "created_at.desc,user_id.asc"


def test_member_directory_hydrates_user_identifier_and_metadata_for_alias_only_member() -> None:
    client = _PagedClient(
        member_rows=[],
        alias_rows=[
            _phone_alias(
                1,
                source="phone_verification",
                phone="15558860001",
                created_at="2026-07-08T12:00:00+00:00",
            )
        ],
        user_rows=[
            {
                "id": "user-0001",
                "identifier": "qa_eval_codex_20260708",
                "createdAt": "2026-07-08T12:00:00+00:00",
                "metadata": {"account_kind": "eval_runner", "actor_type": "machine"},
            }
        ],
    )

    members = _directory(client).list_members(limit=10)

    assert members[0]["display_name"] == "qa_eval_codex_20260708"
    assert "qa_eval_codex_20260708" in members[0]["alias_user_ids"]
    assert members[0]["identity_metadata"] == {
        "account_kind": "eval_runner",
        "actor_type": "machine",
    }


def test_member_directory_uses_verified_phone_alias_time_as_registration_time() -> None:
    client = _PagedClient(
        member_rows=[],
        alias_rows=[
            _phone_alias(
                1,
                source="phone_verification",
                phone="15558860001",
                created_at="2026-06-21T09:00:00+00:00",
                verified_at="2026-06-21T09:01:00+00:00",
            )
        ],
    )

    members = _directory(client).list_members(limit=10)

    assert len(members) == 1
    assert members[0]["created_at"] == "2026-06-21T09:01:00+00:00"


def test_member_directory_propagates_phone_alias_identity_metadata() -> None:
    client = _PagedClient(
        member_rows=[],
        alias_rows=[
            _phone_alias(
                1,
                source="phone_verification",
                phone="15558860001",
                metadata={
                    "account_kind": "eval_runner",
                    "actor_type": "machine",
                    "created_by": "eval_runner",
                    "is_internal_test": True,
                    "runner": "codex",
                    "eval_run_id": "codex-20260708",
                },
            )
        ],
    )

    members = _directory(client).list_members(limit=10)

    assert len(members) == 1
    assert members[0]["identity_metadata"] == {
        "account_kind": "eval_runner",
        "actor_type": "machine",
        "created_by": "eval_runner",
        "is_internal_test": True,
        "runner": "codex",
        "eval_run_id": "codex-20260708",
    }


def test_member_directory_does_not_count_backfill_alias_created_at_as_registration_time() -> None:
    client = _PagedClient(
        member_rows=[],
        alias_rows=[
            _phone_alias(
                1,
                source="phone_backfill",
                phone="15558860001",
                created_at="2026-06-21T09:00:00+00:00",
                verified_at="2026-06-21T09:01:00+00:00",
            )
        ],
    )

    members = _directory(client).list_members(limit=10)

    assert len(members) == 1
    assert members[0]["created_at"] == "1970-01-01T00:00:00+00:00"


def test_member_directory_does_not_read_dead_chat_conversation_columns() -> None:
    """B 断点防回归：Postgres chat_conversations 是死表（真实对话在 SQLite
    chat_history.db），v_members 的 chat 派生列全是空壳。目录读模型必须
    完全不读这些列——宁缺毋假；真实对话活跃由 member_console service 的
    _merge_session_activity_for_member_list 从 SQLite sessions 派生。"""
    dead_columns = (
        "first_chat_at",
        "last_chat_at",
        "total_conversations",
        "total_messages",
        "has_chat_history",
    )
    member = _member_row(1, phone="15558860001")
    member["wallet_updated_at"] = "2026-07-01T10:00:00+00:00"
    # 即使上游视图仍返回死列，也不得进入会员事实。
    member["last_chat_at"] = "2026-07-09T10:00:00+00:00"
    member["total_conversations"] = 99
    member["total_messages"] = 999
    member["has_chat_history"] = True
    client = _PagedClient(
        member_rows=[member],
        alias_rows=[_phone_alias(1, source="phone_verification", phone="15558860001")],
    )

    members = _directory(client).list_members(limit=10)

    v_members_calls = [call for call in client.calls if call["table"] == "v_members"]
    assert v_members_calls, "expected at least one v_members query"
    for call in v_members_calls:
        select = str(call.get("select") or "")
        order = str(call.get("order") or "")
        for column in dead_columns:
            assert column not in select, f"dead column {column} must not be selected"
            assert column not in order, f"dead column {column} must not drive ordering"

    assert len(members) == 1
    metrics = members[0]["member_directory_metrics"]
    for column in ("total_conversations", "total_messages", "has_chat_history"):
        assert column not in metrics, f"dead column {column} must not appear in payload"
    # last_active_at 不得吃死表的 last_chat_at；钱包时间是目录侧的保守回退，
    # 真实对话活跃由 service 层 SQLite 合并覆盖。
    assert members[0]["last_active_at"] == "2026-07-01T10:00:00+00:00"
