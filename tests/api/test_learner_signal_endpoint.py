"""学员信号写端点 handler 级测试（不起 HTTP 栈）。

证明：owner-scope 取鉴权 user_id、source_feature=learner_signal 守编译器纯净、
非法 signal_type 返回 400。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.api.routers import learner_signal as ls_router


def _patch_service(monkeypatch, captured: dict):
    class _Svc:
        def append_memory_event(self, user_id, *, source_feature, source_id, memory_kind,
                                payload_json, source_bot_id=None, dedupe_key=None):
            captured.update(
                user_id=user_id, source_feature=source_feature,
                memory_kind=memory_kind, payload_json=payload_json,
            )
            return SimpleNamespace(event_id="evt_1")

    monkeypatch.setattr(ls_router, "get_learner_state_service", lambda: _Svc())


@pytest.mark.unit
def test_post_learner_signal_creates_event(monkeypatch):
    captured: dict = {}
    _patch_service(monkeypatch, captured)
    body = ls_router.LearnerSignalRequest(
        signal_type="subjective_focus", concept_id="k_fang", concept_label="防水工程",
    )
    out = asyncio.run(ls_router.post_learner_signal(body, current_user=SimpleNamespace(user_id="u1")))
    assert out["ok"] is True and out["event_id"] == "evt_1"
    assert captured["user_id"] == "u1"                          # owner-scope 用鉴权 user_id
    assert captured["source_feature"] == "learner_signal"       # 守编译器纯净
    assert captured["memory_kind"] == "learning_evidence"       # 骑既有白名单
    assert captured["payload_json"]["learning_signal_type"] == "subjective_focus"


@pytest.mark.unit
def test_post_learner_signal_rejects_bad_type(monkeypatch):
    _patch_service(monkeypatch, {})
    body = ls_router.LearnerSignalRequest(signal_type="mastery_hack", concept_id="k")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(ls_router.post_learner_signal(body, current_user=SimpleNamespace(user_id="u1")))
    assert exc.value.status_code == 400
