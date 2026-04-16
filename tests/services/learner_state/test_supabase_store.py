from __future__ import annotations

import asyncio
import json

import httpx

from deeptutor.services.learner_state.supabase_store import LearnerStateSupabaseClient, LearnerStateSupabaseCoreStore


def _make_client(requests: list[dict[str, object]], state: dict[str, object]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "json": json.loads(body) if body else None,
            }
        )

        table = request.url.path.rsplit("/", 1)[-1]
        params = dict(request.url.params)
        if request.method == "GET":
            if table == "user_profiles":
                user_id = str(params.get("user_id", "")).replace("eq.", "")
                row = dict(state["user_profiles"].get(user_id, {}))
                return httpx.Response(200, json=[row] if row else [], request=request)
            if table == "user_stats":
                user_id = str(params.get("user_id", "")).replace("eq.", "")
                row = dict(state["user_stats"].get(user_id, {}))
                return httpx.Response(200, json=[row] if row else [], request=request)
            if table == "user_goals":
                user_id = str(params.get("user_id", "")).replace("eq.", "")
                rows = [
                    dict(row)
                    for row in state["user_goals"]
                    if str(row.get("user_id", "")).strip() == user_id
                ]
                rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
                return httpx.Response(200, json=rows, request=request)

        if request.method == "POST":
            payload = json.loads(body or "[]")
            row = dict(payload[0] if isinstance(payload, list) and payload else payload)
            if table == "user_profiles":
                state["user_profiles"][row["user_id"]] = row
            elif table == "user_stats":
                state["user_stats"][row["user_id"]] = row
            elif table == "user_goals":
                goals = state["user_goals"]
                if row.get("id") in (None, ""):
                    numeric_ids = [
                        int(item.get("id", 0) or 0)
                        for item in goals
                        if str(item.get("id", "")).strip().isdigit()
                    ]
                    row["id"] = max(numeric_ids + [0]) + 1
                goals[:] = [item for item in goals if str(item.get("id", "")).strip() != str(row.get("id", "")).strip()]
                goals.append(row)
            return httpx.Response(200, json=[row], request=request)

        if request.method == "DELETE" and table == "user_goals":
            goal_id = str(params.get("id", "")).replace("eq.", "")
            state["user_goals"][:] = [row for row in state["user_goals"] if str(row.get("id", "")).strip() != goal_id]
            return httpx.Response(200, json=[], request=request)

        return httpx.Response(400, json={"error": "unsupported"}, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.supabase.co")


def test_profile_read_write_and_merge_uses_user_id_filter() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {
            "student_demo": {
                "user_id": "student_demo",
                "summary": "基础画像",
                "attributes": {"tier": "vip"},
                "last_updated": "2026-04-15T10:00:00+08:00",
            }
        },
        "user_stats": {},
        "user_goals": [],
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        profile = await store.read_profile("student_demo")
        assert profile["summary"] == "基础画像"

        updated = await store.merge_profile("student_demo", {"attributes": {"tier": "gold"}, "summary": "更新画像"})
        assert updated["attributes"]["tier"] == "gold"
        assert updated["summary"] == "更新画像"

    asyncio.run(_run())
    assert requests[0]["path"] == "/rest/v1/user_profiles"
    assert requests[0]["params"]["user_id"] == "eq.student_demo"
    assert requests[0]["params"]["limit"] == "1"
    assert requests[2]["path"] == "/rest/v1/user_profiles"
    assert requests[2]["params"]["on_conflict"] == "user_id"
    assert state["user_profiles"]["student_demo"]["summary"] == "更新画像"

    asyncio.run(transport_client.aclose())


def test_stats_read_write_and_merge_uses_user_id_filter() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {},
        "user_stats": {
            "student_demo": {
                "user_id": "student_demo",
                "mastery_level": 2,
                "total_attempts": 10,
                "error_count": 3,
            }
        },
        "user_goals": [],
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        stats = await store.read_stats("student_demo")
        assert stats["mastery_level"] == 2

        updated = await store.merge_stats("student_demo", {"mastery_level": 3, "last_practiced_at": "2026-04-15"})
        assert updated["mastery_level"] == 3
        assert updated["last_practiced_at"] == "2026-04-15"

    asyncio.run(_run())
    assert requests[0]["path"] == "/rest/v1/user_stats"
    assert requests[0]["params"]["user_id"] == "eq.student_demo"
    assert requests[2]["path"] == "/rest/v1/user_stats"
    assert requests[2]["params"]["on_conflict"] == "user_id"
    assert state["user_stats"]["student_demo"]["mastery_level"] == 3
    assert state["user_stats"]["student_demo"]["tag"] == ""

    asyncio.run(transport_client.aclose())


def test_goals_list_upsert_and_delete_use_goal_primary_key() -> None:
    requests: list[dict[str, object]] = []
    state = {
        "user_profiles": {},
        "user_stats": {},
        "user_goals": [
            {
                "id": "goal_2",
                "user_id": "student_demo",
                "goal_type": "review",
                "title": "复习承载力",
                "created_at": "2026-04-15T10:20:00+08:00",
            },
            {
                "id": "goal_1",
                "user_id": "student_demo",
                "goal_type": "study",
                "title": "学习沉降控制",
                "created_at": "2026-04-15T10:10:00+08:00",
            },
        ],
    }
    transport_client = _make_client(requests, state)
    client = LearnerStateSupabaseClient(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=transport_client,
    )
    store = LearnerStateSupabaseCoreStore(client=client)

    async def _run() -> None:
        goals = await store.read_goals("student_demo")
        assert [goal["id"] for goal in goals] == ["goal_2", "goal_1"]

        saved = await store.upsert_goal(
            {
                "user_id": "student_demo",
                "goal_type": "study",
                "title": "完成本周案例题",
                "target_node_codes": ["node_a"],
            }
        )
        assert saved["user_id"] == "student_demo"
        assert saved["title"] == "完成本周案例题"
        await store.delete_goal(saved["id"])

    asyncio.run(_run())
    assert requests[0]["path"] == "/rest/v1/user_goals"
    assert requests[0]["params"]["user_id"] == "eq.student_demo"
    assert requests[0]["params"]["order"] == "created_at.desc"
    assert requests[1]["path"] == "/rest/v1/user_goals"
    assert requests[1]["params"]["on_conflict"] == "id"
    assert requests[2]["path"] == "/rest/v1/user_goals"
    assert requests[2]["params"]["id"].startswith("eq.")
    assert len(state["user_goals"]) == 2

    asyncio.run(transport_client.aclose())
