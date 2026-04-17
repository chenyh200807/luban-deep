from __future__ import annotations

import importlib

import pytest

pytest.importorskip("fastapi")

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient
from deeptutor.api.dependencies import AuthContext, get_current_user

router = importlib.import_module("deeptutor.api.routers.tutor_state").router


def _ctx(user_id: str, *, is_admin: bool = False) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        provider="test",
        token="test-token",
        claims={"uid": user_id},
        is_admin=is_admin,
    )


def _build_app(*, is_admin: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/tutor-state")
    app.dependency_overrides[get_current_user] = lambda: _ctx("student_demo", is_admin=is_admin)
    return app


def _make_snapshot():
    return type(
        "Snapshot",
        (),
        {
            "user_id": "student_demo",
            "profile": "## 身份信息\n- 学员ID：student_demo",
            "persona": "## 角色定位\n- 你是该学员的专属 TutorBot。",
            "memory": "## 当前主线\n- 当前聚焦：地基基础承载力",
            "profile_updated_at": "2026-04-14T12:00:00+08:00",
            "persona_updated_at": "2026-04-14T12:01:00+08:00",
            "memory_updated_at": "2026-04-14T12:02:00+08:00",
        },
    )()


def test_tutor_state_router_returns_user_snapshot(monkeypatch) -> None:
    class FakeTutorStateService:
        def read_snapshot(self, user_id: str):
            assert user_id == "student_demo"
            return _make_snapshot()

    monkeypatch.setattr(
        "deeptutor.api.routers.tutor_state.get_user_tutor_state_service",
        lambda: FakeTutorStateService(),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/tutor-state/student_demo")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "student_demo"
    assert "专属 TutorBot" in body["persona"]
    assert "地基基础承载力" in body["memory"]


def test_tutor_state_router_returns_rendered_context(monkeypatch) -> None:
    class FakeTutorStateService:
        def build_context(self, user_id: str, *, language: str = "zh", max_chars: int = 5000):
            assert user_id == "student_demo"
            assert language == "en"
            assert max_chars == 2400
            return "## Dedicated Tutor Context\n### Student Profile\n- user: student_demo"

    monkeypatch.setattr(
        "deeptutor.api.routers.tutor_state.get_user_tutor_state_service",
        lambda: FakeTutorStateService(),
    )

    with TestClient(_build_app()) as client:
        response = client.get("/api/v1/tutor-state/student_demo/context?language=en&max_chars=2400")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "user_id": "student_demo",
        "language": "en",
        "max_chars": 2400,
        "context": "## Dedicated Tutor Context\n### Student Profile\n- user: student_demo",
    }


def test_tutor_state_router_rejects_other_user() -> None:
    app = _build_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/tutor-state/student_other")

    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


def test_tutor_state_router_exposes_heartbeat_and_overlay_views(monkeypatch) -> None:
    class FakeLearnerStateService:
        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 5
            assert include_arbitration is False
            return [
                {
                    "event_id": "hb_1",
                    "memory_kind": "heartbeat_delivery",
                    "source_bot_id": "review-bot",
                    "payload_json": {"status": "sent"},
                    "created_at": "2026-04-16T10:00:00+08:00",
                }
            ]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 3
            return [
                {
                    "event_id": "arb_1",
                    "source_bot_id": "review-bot",
                    "payload_json": {"winner_bot_id": "review-bot"},
                    "created_at": "2026-04-16T10:01:00+08:00",
                }
            ]

    class FakeOverlayService:
        def list_user_overlays(self, user_id: str, *, limit: int | None = None):
            assert user_id == "student_demo"
            assert limit == 10
            return [
                {
                    "bot_id": "review-bot",
                    "user_id": "student_demo",
                    "version": 4,
                    "effective_overlay": {"local_focus": {"topic": "防火间距"}},
                    "created_at": "2026-04-15T09:00:00+08:00",
                    "updated_at": "2026-04-16T09:30:00+08:00",
                    "event_count": 2,
                }
            ]

        def read_overlay(self, bot_id: str, user_id: str):
            assert bot_id == "review-bot"
            assert user_id == "student_demo"
            return {
                "bot_id": bot_id,
                "user_id": user_id,
                "version": 4,
                "effective_overlay": {"local_focus": {"topic": "防火间距"}},
                "promotion_candidates": [{"candidate_id": "cand_1"}],
            }

        def list_overlay_events(self, bot_id: str, user_id: str, *, limit: int | None = None, event_type: str | None = None):
            assert bot_id == "review-bot"
            assert user_id == "student_demo"
            assert limit == 6
            assert event_type == "overlay_patch"
            return [{"event_id": "evt_1", "event_type": "overlay_patch"}]

        def list_overlay_audit(self, bot_id: str, user_id: str, *, limit: int | None = None):
            assert bot_id == "review-bot"
            assert user_id == "student_demo"
            assert limit == 4
            return [{"event_id": "audit_1", "event_type": "overlay_promotion_apply"}]

    monkeypatch.setattr(
        "deeptutor.api.routers.tutor_state.get_learner_state_service",
        lambda: FakeLearnerStateService(),
    )
    monkeypatch.setattr(
        "deeptutor.api.routers.tutor_state.get_bot_learner_overlay_service",
        lambda: FakeOverlayService(),
    )

    with TestClient(_build_app()) as client:
        heartbeat_response = client.get(
            "/api/v1/tutor-state/student_demo/heartbeat-history?limit=5&include_arbitration=false"
        )
        arbitration_response = client.get("/api/v1/tutor-state/student_demo/heartbeat-arbitration?limit=3")
        overlays_response = client.get("/api/v1/tutor-state/student_demo/overlays?limit=10")
        overlay_response = client.get("/api/v1/tutor-state/student_demo/overlay/review-bot")
        events_response = client.get(
            "/api/v1/tutor-state/student_demo/overlay/review-bot/events?limit=6&event_type=overlay_patch"
        )
        audit_response = client.get("/api/v1/tutor-state/student_demo/overlay/review-bot/audit?limit=4")

    assert heartbeat_response.status_code == 200
    assert heartbeat_response.json()["items"][0]["memory_kind"] == "heartbeat_delivery"
    assert arbitration_response.status_code == 200
    assert arbitration_response.json()["items"][0]["payload_json"]["winner_bot_id"] == "review-bot"
    assert overlays_response.status_code == 200
    assert overlays_response.json()["items"][0]["bot_id"] == "review-bot"
    assert overlay_response.status_code == 200
    assert overlay_response.json()["promotion_candidates"][0]["candidate_id"] == "cand_1"
    assert events_response.status_code == 200
    assert events_response.json()["items"][0]["event_type"] == "overlay_patch"
    assert audit_response.status_code == 200
    assert audit_response.json()["items"][0]["event_type"] == "overlay_promotion_apply"


def test_tutor_state_router_admin_can_patch_overlay_and_manage_promotions(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeLearnerStateService:
        pass

    class FakeOverlayService:
        def patch_overlay(self, bot_id: str, user_id: str, patch: dict[str, object], *, source_feature: str, source_id: str):
            calls["patch"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "patch": patch,
                "source_feature": source_feature,
                "source_id": source_id,
            }
            return {"ok": True, "bot_id": bot_id, "user_id": user_id}

        def apply_promotions(
            self,
            bot_id: str,
            user_id: str,
            *,
            learner_state_service,
            min_confidence: float = 0.7,
            max_candidates: int = 10,
        ):
            calls["apply"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "learner_state_service": learner_state_service,
                "min_confidence": min_confidence,
                "max_candidates": max_candidates,
            }
            return {"applied": [{"candidate_id": "cand_1"}]}

        def ack_promotions(self, bot_id: str, user_id: str, candidate_ids, *, reason: str = ""):
            calls["ack"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "candidate_ids": list(candidate_ids),
                "reason": reason,
            }
            return {"affected_count": len(candidate_ids)}

        def drop_promotions(self, bot_id: str, user_id: str, candidate_ids, *, reason: str = ""):
            calls["drop"] = {
                "bot_id": bot_id,
                "user_id": user_id,
                "candidate_ids": list(candidate_ids),
                "reason": reason,
            }
            return {"affected_count": len(candidate_ids)}

    fake_learner_state_service = FakeLearnerStateService()
    monkeypatch.setattr(
        "deeptutor.api.routers.tutor_state.get_learner_state_service",
        lambda: fake_learner_state_service,
    )
    monkeypatch.setattr(
        "deeptutor.api.routers.tutor_state.get_bot_learner_overlay_service",
        lambda: FakeOverlayService(),
    )

    with TestClient(_build_app(is_admin=True)) as client:
        patch_response = client.patch(
            "/api/v1/tutor-state/student_demo/overlay/review-bot",
            json={"operations": [{"op": "merge", "field": "heartbeat_override", "value": {"suppress": True}}]},
        )
        apply_response = client.post(
            "/api/v1/tutor-state/student_demo/overlay/review-bot/promotions/apply",
            json={"min_confidence": 0.8, "max_candidates": 5},
        )
        ack_response = client.post(
            "/api/v1/tutor-state/student_demo/overlay/review-bot/promotions/ack",
            json={"candidate_ids": ["cand_1"], "reason": "operator_confirmed"},
        )
        drop_response = client.post(
            "/api/v1/tutor-state/student_demo/overlay/review-bot/promotions/drop",
            json={"candidate_ids": ["cand_2"], "reason": "noise"},
        )

    assert patch_response.status_code == 200
    assert calls["patch"]["source_feature"] == "admin_overlay"
    assert calls["patch"]["source_id"] == "student_demo"
    assert calls["patch"]["patch"]["operations"][0]["field"] == "heartbeat_override"
    assert apply_response.status_code == 200
    assert calls["apply"]["learner_state_service"] is fake_learner_state_service
    assert calls["apply"]["min_confidence"] == 0.8
    assert calls["apply"]["max_candidates"] == 5
    assert ack_response.status_code == 200
    assert calls["ack"]["candidate_ids"] == ["cand_1"]
    assert calls["ack"]["reason"] == "operator_confirmed"
    assert drop_response.status_code == 200
    assert calls["drop"]["candidate_ids"] == ["cand_2"]
    assert calls["drop"]["reason"] == "noise"


def test_tutor_state_router_rejects_overlay_patch_without_admin() -> None:
    with TestClient(_build_app()) as client:
        response = client.patch(
            "/api/v1/tutor-state/student_demo/overlay/review-bot",
            json={"operations": [{"op": "clear", "field": "local_focus"}]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"
