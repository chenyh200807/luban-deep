"""lesson-progress 写端点测试。

handler 级：owner-scope 取鉴权 user_id、source_feature=luban_lesson 守编译器纯净、
progress_countable=false 防污染、非法 watched_stage 返回 400。
TestClient 级（评审项 7）：真 HTTP 栈一条测试同时覆盖挂载 + 鉴权拒绝 +
依赖接线（事件落真账本）。
"""
from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import lesson_progress as lp_router


def _patch_service(monkeypatch, captured: dict):
    class _Svc:
        def append_memory_event(self, user_id, *, source_feature, source_id, memory_kind,
                                payload_json, source_bot_id=None, dedupe_key=None):
            captured.update(
                user_id=user_id, source_feature=source_feature,
                memory_kind=memory_kind, payload_json=payload_json,
                dedupe_key=dedupe_key,
            )
            return SimpleNamespace(event_id="evt_1")

    monkeypatch.setattr(lp_router, "get_learner_state_service", lambda: _Svc())


def _invoke(body, *, user_id: str = "u1"):
    # 兼容 handler 由 async def 改 def（并行融合改造中）：协程则跑事件循环。
    result = lp_router.post_lesson_progress(body, current_user=SimpleNamespace(user_id=user_id))
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


@pytest.mark.unit
def test_post_lesson_progress_creates_exposed_evidence(monkeypatch):
    captured: dict = {}
    _patch_service(monkeypatch, captured)
    body = lp_router.LessonProgressRequest(pack_id="N01", watched_stage="lesson", card_sha="sha256:x")
    out = _invoke(body)
    assert out["ok"] is True and out["event_id"] == "evt_1"
    assert captured["user_id"] == "u1"                            # owner-scope 用鉴权 user_id
    assert captured["source_feature"] == "luban_lesson"           # 守编译器白名单之外
    assert captured["memory_kind"] == "learning_evidence"
    payload = captured["payload_json"]
    assert payload["event_type"] == "learning_evidence"           # contract 硬要求
    assert payload["evidence_level"] == "exposed"
    assert payload["quality"] == {"progress_countable": False}    # M0：看动画不算掌握
    assert captured["dedupe_key"].startswith("lesson_viewed:u1:N01:lesson:")


@pytest.mark.unit
def test_post_lesson_progress_rejects_bad_stage(monkeypatch):
    _patch_service(monkeypatch, {})
    body = lp_router.LessonProgressRequest(pack_id="N01", watched_stage="binge")
    with pytest.raises(HTTPException) as exc:
        _invoke(body)
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# TestClient 级（评审项 7）：挂载 + 鉴权 + 账本接线，不再绕过 HTTP 栈。
# ---------------------------------------------------------------------------


class _LedgerPathServiceStub:
    def __init__(self, root):
        self._root = root

    @property
    def project_root(self):
        return self._root

    def get_user_root(self):
        return self._root

    def get_learner_state_root(self):
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self):
        return self._root / "runtime" / "outbox.db"

    def get_guide_dir(self):
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _DisabledCoreStore:
    is_configured = False


@pytest.mark.unit
def test_lesson_progress_http_requires_auth_and_writes_real_ledger(tmp_path, monkeypatch):
    from deeptutor.services.learner_state.service import LearnerStateService

    # 真账本（tmp_path 存储）——依赖接线不靠 captured dict 自证。
    service = LearnerStateService(
        path_service=_LedgerPathServiceStub(tmp_path),
        member_service=object(),
        core_store=_DisabledCoreStore(),
    )
    monkeypatch.setattr(lp_router, "get_learner_state_service", lambda: service)

    # 鉴权走真 get_current_user（secure_router 默认鉴权），只 stub token 校验后端
    # ——按 tests/api/test_auth_dependency.py 既有范式。
    auth_module = importlib.import_module("deeptutor.api.dependencies.auth")

    class _FakeMemberConsoleService:
        def verify_access_token(self, token: str):
            if token != "student-token":
                return None
            return {"uid": "student_http", "provider": "test"}

        def is_admin_user(self, user_id: str) -> bool:
            return False

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberConsoleService())

    # 与 deeptutor/api/main.py 同前缀挂载（挂载路径回归）。
    app = FastAPI()
    app.include_router(lp_router.router, prefix="/api/v1/lesson-progress", tags=["lesson_progress"])

    body = {"pack_id": "A01", "watched_stage": "lesson", "card_sha": "sha256:x"}
    with TestClient(app) as client:
        # 未认证 → 401/403（secure_router 默认鉴权不许绕过）。
        anonymous = client.post("/api/v1/lesson-progress/progress", json=body)
        assert anonymous.status_code in (401, 403)

        authed = client.post(
            "/api/v1/lesson-progress/progress",
            json=body,
            headers={"Authorization": "Bearer student-token"},
        )
    assert authed.status_code == 200
    payload = authed.json()
    assert payload["ok"] is True and payload["event_id"]

    # 未认证请求绝不落账本；认证请求恰好 1 条学-evidence。
    events = service.list_memory_events("student_http", limit=None)
    assert len(events) == 1
    event = events[0]
    assert event.event_id == payload["event_id"]
    assert event.source_feature == "luban_lesson"
    assert event.payload_json["pack_id"] == "A01"
    assert event.payload_json["quality"] == {"progress_countable": False}
