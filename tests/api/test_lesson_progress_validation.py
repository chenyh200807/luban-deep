"""病E（端点输入边界）：lesson-progress 写端点的输入约束。

- pack_id/card_sha 带长度上限（Pydantic Field，schema 级拒绝）；
- pack_id 必须在 manifest 全集（list_all_pack_ids）内，未知 pack → 400
  ——防任意串灌进 append-only 账本变成永久垃圾证据；
- 端点保持同步 def（病B-1 回归钉）。
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from pydantic import ValidationError

from deeptutor.api.routers import lesson_progress as lp_router


def _patch_service(monkeypatch, captured: dict):
    class _Svc:
        def append_memory_event(self, user_id, *, source_feature, source_id, memory_kind,
                                payload_json, source_bot_id=None, dedupe_key=None):
            captured.update(payload_json=payload_json)
            return SimpleNamespace(event_id="evt_1")

    monkeypatch.setattr(lp_router, "get_learner_state_service", lambda: _Svc())


@pytest.mark.unit
def test_endpoint_is_sync_def_for_threadpool_execution():
    # 病B-1：同步账本 I/O 必须走线程池，端点禁 async def。
    assert not inspect.iscoroutinefunction(lp_router.post_lesson_progress)


@pytest.mark.unit
def test_request_model_rejects_oversized_fields():
    with pytest.raises(ValidationError):
        lp_router.LessonProgressRequest(pack_id="P" * 65, watched_stage="lesson")
    with pytest.raises(ValidationError):
        lp_router.LessonProgressRequest(
            pack_id="N01", watched_stage="lesson", card_sha="s" * 129
        )
    with pytest.raises(ValidationError):
        lp_router.LessonProgressRequest(pack_id="", watched_stage="lesson")


@pytest.mark.unit
def test_unknown_pack_id_returns_400(monkeypatch):
    captured: dict = {}
    _patch_service(monkeypatch, captured)
    monkeypatch.setattr(lp_router, "list_all_pack_ids", lambda: ["N01", "S05"])
    body = lp_router.LessonProgressRequest(pack_id="ZZ_NOT_A_PACK", watched_stage="lesson")
    with pytest.raises(HTTPException) as exc:
        lp_router.post_lesson_progress(body, current_user=SimpleNamespace(user_id="u1"))
    assert exc.value.status_code == 400
    assert not captured  # 未知 pack 绝不落账本


@pytest.mark.unit
def test_known_pack_id_passes_registry_check(monkeypatch):
    captured: dict = {}
    _patch_service(monkeypatch, captured)
    monkeypatch.setattr(lp_router, "list_all_pack_ids", lambda: ["N01", "S05"])
    body = lp_router.LessonProgressRequest(pack_id="N01", watched_stage="lesson")
    out = lp_router.post_lesson_progress(body, current_user=SimpleNamespace(user_id="u1"))
    assert out["ok"] is True
    assert captured["payload_json"]["pack_id"] == "N01"
