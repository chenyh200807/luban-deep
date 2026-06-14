from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext, get_current_user

router = importlib.import_module("deeptutor.api.routers.member").router


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/member")
    return app


def _ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=is_admin,
    )


def test_member_dashboard_requires_admin() -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo", is_admin=False)

    with TestClient(app) as client:
        response = client.get("/api/v1/member/dashboard")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_member_dashboard_allows_admin() -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo", is_admin=True)

    with TestClient(app) as client:
        response = client.get("/api/v1/member/dashboard")

    assert response.status_code == 200
    assert "total_count" in response.json()


def test_member_360_exposes_learner_state_overlay_and_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {
                "get_member_360": staticmethod(
                    lambda user_id: {
                        "user_id": user_id,
                        "display_name": "陈同学",
                        "learner_state": {"summary": "正在复习地基基础。"},
                        "heartbeat": {"history": [{"event_id": "hb_1"}]},
                        "bot_overlays": [{"bot_id": "review-bot", "version": 3}],
                    }
                )
            },
        )(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/member/student_demo/360")

    assert response.status_code == 200
    body = response.json()
    assert body["learner_state"]["summary"] == "正在复习地基基础。"
    assert body["heartbeat"]["history"][0]["event_id"] == "hb_1"
    assert body["bot_overlays"][0]["bot_id"] == "review-bot"


def test_member_conversations_exposes_metadata_only(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    calls: list[dict[str, object]] = []

    def _list_member_conversations(user_id: str, **kwargs: object) -> dict[str, object]:
        calls.append({"user_id": user_id, **kwargs})
        return {
            "user_id": user_id,
            "items": [
                {
                    "session_id": "tb_student_demo",
                    "title": "地基基础答疑",
                    "message_count": 2,
                    "last_message": "怎么复习",
                }
            ],
            "total": 1,
        }

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {"list_member_conversations": staticmethod(_list_member_conversations)},
        )(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/member/student_demo/conversations?limit=10&message_limit=6")

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["session_id"] == "tb_student_demo"
    assert "messages" not in body["items"][0]
    assert calls == [
        {
            "user_id": "student_demo",
            "limit": 10,
            "message_limit": 6,
            "q": "",
            "source": "",
            "capability": "",
            "sort": "updated_at",
            "order": "desc",
        }
    ]


def test_member_router_exposes_learner_state_overlay_and_heartbeat_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {
                "get_member_learner_state_panel": staticmethod(
                    lambda user_id, limit=20: {
                        "user_id": user_id,
                        "heartbeat_jobs": [{"job_id": "job_1"}],
                        "bot_overlays": [{"bot_id": "review-bot"}],
                    }
                ),
                "list_member_heartbeat_jobs": staticmethod(
                    lambda user_id: {"user_id": user_id, "items": [{"job_id": "job_1", "status": "active"}], "total": 1}
                ),
                "pause_member_heartbeat_job": staticmethod(
                    lambda user_id, job_id, operator="admin": {"user_id": user_id, "job_id": job_id, "status": "paused"}
                ),
                "resume_member_heartbeat_job": staticmethod(
                    lambda user_id, job_id, operator="admin": {"user_id": user_id, "job_id": job_id, "status": "active"}
                ),
                "get_member_overlay": staticmethod(
                    lambda user_id, bot_id: {"user_id": user_id, "bot_id": bot_id, "version": 4}
                ),
                "get_member_overlay_events": staticmethod(
                    lambda user_id, bot_id, limit=20, event_type=None: {
                        "user_id": user_id,
                        "bot_id": bot_id,
                        "items": [{"event_id": "evt_1", "event_type": "overlay_patch"}],
                    }
                ),
                "get_member_overlay_audit": staticmethod(
                    lambda user_id, bot_id, limit=20: {
                        "user_id": user_id,
                        "bot_id": bot_id,
                        "items": [{"event_id": "audit_1"}],
                    }
                ),
                "patch_member_overlay": staticmethod(
                    lambda user_id, bot_id, operations, operator="admin": {
                        "user_id": user_id,
                        "bot_id": bot_id,
                        "version": 5,
                        "operations": operations,
                    }
                ),
                "apply_member_overlay_promotions": staticmethod(
                    lambda user_id, bot_id, operator="admin", min_confidence=0.7, max_candidates=10: {
                        "acked_ids": ["cand_1"],
                        "dropped_ids": [],
                    }
                ),
                "ack_member_overlay_promotions": staticmethod(
                    lambda user_id, bot_id, candidate_ids, operator="admin", reason="": {
                        "affected_count": len(candidate_ids),
                        "reason": reason,
                    }
                ),
                "drop_member_overlay_promotions": staticmethod(
                    lambda user_id, bot_id, candidate_ids, operator="admin", reason="": {
                        "affected_count": len(candidate_ids),
                        "reason": reason,
                    }
                ),
            },
        )(),
    )

    with TestClient(app) as client:
        panel = client.get("/api/v1/member/student_demo/learner-state?limit=5")
        jobs = client.get("/api/v1/member/student_demo/heartbeat-jobs")
        paused = client.post("/api/v1/member/student_demo/heartbeat-jobs/job_1/pause")
        resumed = client.post("/api/v1/member/student_demo/heartbeat-jobs/job_1/resume")
        overlay = client.get("/api/v1/member/student_demo/overlays/review-bot")
        events = client.get("/api/v1/member/student_demo/overlays/review-bot/events?limit=5")
        audit = client.get("/api/v1/member/student_demo/overlays/review-bot/audit?limit=5")
        patched = client.patch(
            "/api/v1/member/student_demo/overlays/review-bot",
            json={"operations": [{"op": "merge", "field": "heartbeat_override", "value": {"suppress": True}}]},
        )
        applied = client.post(
            "/api/v1/member/student_demo/overlays/review-bot/promotions/apply",
            json={"min_confidence": 0.8, "max_candidates": 3},
        )
        acked = client.post(
            "/api/v1/member/student_demo/overlays/review-bot/promotions/ack",
            json={"candidate_ids": ["cand_1"], "reason": "confirmed"},
        )
        dropped = client.post(
            "/api/v1/member/student_demo/overlays/review-bot/promotions/drop",
            json={"candidate_ids": ["cand_2"], "reason": "noise"},
        )

    assert panel.status_code == 200
    assert panel.json()["heartbeat_jobs"][0]["job_id"] == "job_1"
    assert jobs.status_code == 200
    assert jobs.json()["items"][0]["status"] == "active"
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert overlay.status_code == 200
    assert overlay.json()["bot_id"] == "review-bot"
    assert events.status_code == 200
    assert events.json()["items"][0]["event_id"] == "evt_1"
    assert audit.status_code == 200
    assert audit.json()["items"][0]["event_id"] == "audit_1"
    assert patched.status_code == 200
    assert patched.json()["version"] == 5
    assert applied.status_code == 200
    assert applied.json()["acked_ids"] == ["cand_1"]
    assert acked.status_code == 200
    assert acked.json()["affected_count"] == 1
    assert dropped.status_code == 200
    assert dropped.json()["affected_count"] == 1


def test_member_router_exposes_batch_and_audit_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {
                "batch_update_members": staticmethod(
                    lambda **kwargs: {"action": kwargs["action"], "success_count": 2, "failure_count": 0, "items": []}
                ),
                "get_audit_log": staticmethod(
                    lambda **kwargs: {
                        "items": [{"id": "audit_1", "action": "grant"}],
                        "page": 1,
                        "page_size": 20,
                        "pages": 1,
                        "total": 1,
                    }
                ),
                "export_members_csv": staticmethod(
                    lambda **kwargs: {"filename": "members.csv", "content": "user_id,display_name\\nu1,陈同学\\n"}
                ),
            },
        )(),
    )

    with TestClient(app) as client:
        batch = client.post(
            "/api/v1/member/batch",
            json={"user_ids": ["u1", "u2"], "action": "grant", "days": 30, "tier": "vip", "reason": "batch"},
        )
        audit = client.get("/api/v1/member/audit-log?page=1&page_size=20&action=grant")
        exported = client.get("/api/v1/member/export?status=active&tier=vip")

    assert batch.status_code == 200
    assert batch.json()["success_count"] == 2
    assert audit.status_code == 200
    assert audit.json()["items"][0]["id"] == "audit_1"
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")


def test_member_router_manual_purchase_requires_idempotency_and_forwards_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    calls: list[dict[str, object]] = []

    def _manual_membership_purchase(**kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {
            "member": {"user_id": kwargs["user_id"], "tier": "vip"},
            "package": {"id": kwargs["package_id"], "label": "VIP"},
            "amount_cny": 198,
            "points": 9000,
            "purchase_id": "manual_membership_1",
            "ledger_event_id": "ledger_manual_1",
            "audit_id": "audit_manual_1",
            "deduped": False,
        }

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type("FakeMemberService", (), {"manual_membership_purchase": staticmethod(_manual_membership_purchase)})(),
    )

    with TestClient(app) as client:
        missing_key = client.post(
            "/api/v1/member/manual-purchase",
            json={"user_id": "u1", "package_id": "vip", "days": 365},
        )
        created = client.post(
            "/api/v1/member/manual-purchase",
            headers={"X-Idempotency-Key": "manual-purchase-1"},
            json={
                "user_id": "u1",
                "package_id": "vip",
                "days": 365,
                "reason": "线下收款",
                "phone": "13800138000",
                "display_name": "张同学",
            },
        )

    assert missing_key.status_code == 400
    assert created.status_code == 200
    assert created.json()["ledger_event_id"] == "ledger_manual_1"
    assert calls == [
        {
            "user_id": "u1",
            "package_id": "vip",
            "days": 365,
            "operator": "admin_demo",
            "reason": "线下收款",
            "idempotency_key": "manual-purchase-1",
            "phone": "13800138000",
            "display_name": "张同学",
            "amount_cny": None,
        }
    ]


def test_member_router_package_management_requires_idempotency_and_forwards_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    calls: list[dict[str, object]] = []

    def _list_membership_packages() -> list[dict[str, object]]:
        calls.append({"action": "list"})
        return [{"id": "svip", "label": "SVIP", "tier": "svip", "points": 28000}]

    def _upsert_membership_package(*, package_id: str, **kwargs: object) -> dict[str, object]:
        calls.append({"action": "upsert", "package_id": package_id, **kwargs})
        return {"id": package_id, "label": kwargs["label"], "tier": kwargs["tier"], "points": kwargs["points"]}

    def _remove_membership_package(package_id: str, **kwargs: object) -> dict[str, object]:
        calls.append({"action": "delete", "package_id": package_id, **kwargs})
        return {"id": package_id, "label": "SVIP Plus"}

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {
                "list_membership_packages": staticmethod(_list_membership_packages),
                "upsert_membership_package": staticmethod(_upsert_membership_package),
                "remove_membership_package": staticmethod(_remove_membership_package),
            },
        )(),
    )

    with TestClient(app) as client:
        listed = client.get("/api/v1/member/packages")
        missing_key = client.put(
            "/api/v1/member/packages/svip_plus",
            json={"label": "SVIP Plus", "tier": "svip", "points": 36000, "turns": 1800, "price": "698"},
        )
        saved = client.put(
            "/api/v1/member/packages/svip_plus",
            headers={"X-Idempotency-Key": "package-upsert-1"},
            json={
                "label": "SVIP Plus",
                "tier": "svip",
                "points": 36000,
                "turns": 1800,
                "price": "698",
                "status": "active",
                "reason": "新增高阶套餐",
            },
        )
        deleted = client.delete(
            "/api/v1/member/packages/svip_plus?reason=%E4%B8%8B%E6%9E%B6",
            headers={"X-Idempotency-Key": "package-delete-1"},
        )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == "svip"
    assert missing_key.status_code == 400
    assert saved.status_code == 200
    assert saved.json()["id"] == "svip_plus"
    assert deleted.status_code == 200
    assert calls == [
        {"action": "list"},
        {
            "action": "upsert",
            "package_id": "svip_plus",
            "label": "SVIP Plus",
            "tier": "svip",
            "points": 36000,
            "turns": 1800,
            "price": "698",
            "original_price": "",
            "badge": "",
            "per": "",
            "desc": "",
            "status": "active",
            "operator": "admin_demo",
            "reason": "新增高阶套餐",
            "idempotency_key": "package-upsert-1",
        },
        {
            "action": "delete",
            "package_id": "svip_plus",
            "operator": "admin_demo",
            "reason": "下架",
            "idempotency_key": "package-delete-1",
        },
    ]


def test_member_router_records_ops_action_result(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    calls: list[dict[str, object]] = []

    def _record_ops_action_result(user_id: str, **kwargs: object) -> dict[str, object]:
        calls.append({"user_id": user_id, **kwargs})
        return {
            "status": kwargs["status"],
            "result": kwargs["result"],
            "action_title": kwargs["action_title"],
            "next_follow_up_at": kwargs["next_follow_up_at"],
            "note": {"id": "note_ops_1", "channel": "ops_action"},
        }

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {"record_ops_action_result": staticmethod(_record_ops_action_result)},
        )(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/member/student_demo/ops-actions",
            json={
                "status": "done",
                "result": "已回访，确认续费",
                "action_title": "即将到期会员",
                "next_follow_up_at": "2026-04-26",
            },
        )

    assert response.status_code == 200
    assert response.json()["note"]["channel"] == "ops_action"
    assert calls == [
        {
            "user_id": "student_demo",
            "status": "done",
            "result": "已回访，确认续费",
            "action_title": "即将到期会员",
            "next_follow_up_at": "2026-04-26",
            "operator": "admin_demo",
        }
    ]


def test_member_router_records_conversation_view(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round 4 S1: view-audit must forward operator + reason + idempotency_key
    to the service. X-Idempotency-Key header is mandatory; missing header
    returns 400 (see test_member_router_view_audit_requires_idempotency_key).
    """
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    calls: list[dict[str, object]] = []

    def _record_conversation_view(user_id: str, session_id: str, **kwargs: object) -> dict[str, object]:
        calls.append({"user_id": user_id, "session_id": session_id, **kwargs})
        return {
            "session_id": session_id,
            "title": "地基基础答疑",
            "message_count": 2,
            "audit_id": "audit_x",
            "messages": [{"id": "m1", "role": "user", "content": "怎么复习"}],
        }

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {"record_conversation_view": staticmethod(_record_conversation_view)},
        )(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/member/student_demo/conversations/tb_student_demo/view-audit",
            headers={"X-Idempotency-Key": "abc-123"},
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == "tb_student_demo"
    assert response.json()["messages"][0]["content"] == "怎么复习"
    assert calls == [
        {
            "user_id": "student_demo",
            "session_id": "tb_student_demo",
            "operator": "admin_demo",
            "reason": None,
            "idempotency_key": "abc-123",
        }
    ]


def test_member_router_view_audit_requires_idempotency_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round 4 S1: missing X-Idempotency-Key on a write must 400 before reaching
    the service. This converts useAuditedAction's header from placebo to enforced
    contract — flaky retries cannot bypass dedup because the second leg without
    a key is rejected at the edge.
    """
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    calls: list[dict[str, object]] = []

    def _record_conversation_view(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append({"args": args, "kwargs": kwargs})
        return {"session_id": "x"}

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {"record_conversation_view": staticmethod(_record_conversation_view)},
        )(),
    )

    with TestClient(app) as client:
        # No X-Idempotency-Key header → must reject.
        no_header = client.post(
            "/api/v1/member/student_demo/conversations/tb_student_demo/view-audit",
        )
        # Empty key is treated the same as missing.
        empty_header = client.post(
            "/api/v1/member/student_demo/conversations/tb_student_demo/view-audit",
            headers={"X-Idempotency-Key": ""},
        )

    assert no_header.status_code == 400
    assert empty_header.status_code == 400
    assert calls == [], "service must NOT be called when header missing/empty"


def test_member_router_view_audit_rejects_malformed_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round 5 M1: X-Idempotency-Key must conform to a tight UUID-ish pattern
    so it cannot be used to inflate the audit_idempotency_keys index with
    multi-MB blobs or to inject the composite-key separator ':' that would
    collide with another action's dedup entry."""
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    calls: list[dict[str, object]] = []

    def _record_conversation_view(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append({"args": args, "kwargs": kwargs})
        return {"session_id": "x"}

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {"record_conversation_view": staticmethod(_record_conversation_view)},
        )(),
    )

    # httpx rejects non-ASCII headers client-side, so we only test cases that
    # actually reach the router. Non-ASCII is blocked one layer earlier.
    bad_keys = [
        "with:colon-injection",  # separator injection
        "x" * 129,  # too long
        "has spaces",  # whitespace
        "with/slash",  # URL char
        "with+plus",  # disallowed char
    ]
    with TestClient(app) as client:
        for bad in bad_keys:
            resp = client.post(
                "/api/v1/member/student_demo/conversations/tb_student_demo/view-audit",
                headers={"X-Idempotency-Key": bad},
            )
            assert resp.status_code == 400, f"malformed key {bad!r} should be 400"
    assert calls == [], "service must NOT be called for any malformed key"


def test_member_router_view_audit_strips_newline_in_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round 5 M2: reason coming through query (%0a) or body must not carry
    newline / CR into audit_log — otherwise log aggregators that parse JSON
    line-by-line could be broken or fed forged entries."""
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    received_reason: list[object] = []

    def _record_conversation_view(*_args: object, **kwargs: object) -> dict[str, object]:
        received_reason.append(kwargs.get("reason"))
        return {"session_id": "x", "audit_id": "audit_x"}

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {"record_conversation_view": staticmethod(_record_conversation_view)},
        )(),
    )

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/member/student_demo/conversations/tb_student_demo/view-audit"
            "?reason=complaint%0afake-line",
            headers={"X-Idempotency-Key": "abc-123"},
        )
    assert resp.status_code == 200
    assert received_reason == ["complaint fake-line"], (
        f"newline must be stripped before reaching service; got {received_reason!r}"
    )


def test_member_list_forwards_operational_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    captured: dict[str, object] = {}

    def fake_list_members(**kwargs):
        captured.update(kwargs)
        return {"items": [], "page": 1, "page_size": 20, "pages": 0, "total": 0, "filters": kwargs}

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type("FakeMemberService", (), {"list_members": staticmethod(fake_list_members)})(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/member/list"
            "?status=expiring_soon"
            "&tier=vip"
            "&expire_within_days=7"
            "&active_within_days=3"
            "&has_heartbeat_job=true"
            "&has_overlay_candidates=false"
        )

    assert response.status_code == 200
    assert captured["status"] == "expiring_soon"
    assert captured["tier"] == "vip"
    assert captured["expire_within_days"] == 7
    assert captured["active_within_days"] == 3
    assert captured["has_heartbeat_job"] is True
    assert captured["has_overlay_candidates"] is False


def test_member_conversations_forwards_workspace_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_app()
    app.dependency_overrides[get_current_user] = lambda: _ctx("admin_demo", is_admin=True)
    captured: dict[str, object] = {}

    def fake_list_member_conversations(user_id: str, **kwargs: object) -> dict[str, object]:
        captured["user_id"] = user_id
        captured.update(kwargs)
        return {"user_id": user_id, "items": [], "total": 0}

    monkeypatch.setattr(
        "deeptutor.api.routers.member.service",
        type(
            "FakeMemberService",
            (),
            {"list_member_conversations": staticmethod(fake_list_member_conversations)},
        )(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/member/student_demo/conversations"
            "?q=退款"
            "&source=web"
            "&capability=deep_question"
            "&sort=message_count"
            "&order=desc"
            "&limit=30"
            "&message_limit=8"
        )

    assert response.status_code == 200
    assert captured == {
        "user_id": "student_demo",
        "limit": 30,
        "message_limit": 8,
        "q": "退款",
        "source": "web",
        "capability": "deep_question",
        "sort": "message_count",
        "order": "desc",
    }
