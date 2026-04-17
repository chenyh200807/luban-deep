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
