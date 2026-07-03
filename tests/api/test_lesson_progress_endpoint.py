"""lesson-progress 写端点 handler 级测试（不起 HTTP 栈）。

证明：owner-scope 取鉴权 user_id、source_feature=luban_lesson 守编译器纯净、
progress_countable=false 防污染、非法 watched_stage 返回 400。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
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


@pytest.mark.unit
def test_post_lesson_progress_creates_exposed_evidence(monkeypatch):
    captured: dict = {}
    _patch_service(monkeypatch, captured)
    body = lp_router.LessonProgressRequest(pack_id="N01", watched_stage="lesson", card_sha="sha256:x")
    out = asyncio.run(lp_router.post_lesson_progress(body, current_user=SimpleNamespace(user_id="u1")))
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
        asyncio.run(lp_router.post_lesson_progress(body, current_user=SimpleNamespace(user_id="u1")))
    assert exc.value.status_code == 400
