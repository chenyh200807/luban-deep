"""R8 解药 / R6 挖空 路由端点测试（错因银行「解药位」+ 实务闯关半写接线）。

handler 级：旗标关 = 空投影/404 同形（fail-closed）；旗标开 = 透传 runtime
投影；runtime 抛 LessonNotAvailable → 404（详情页据此保持「解药整理中」占位）。
TestClient 级：真 HTTP 栈覆盖挂载 + 鉴权拒绝 + 旗标 fail-closed（不泄漏存在性）。

runtime 投影的正确性（signed+sha 双闸、error_code 查找）由
tests/services/luban_lesson/test_antidotes.py / test_cloze.py 覆盖；本文件只钉
路由接线（旗标门、异常→404、vm head-note 形状透传），职责不重叠。
"""
from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import luban_lesson as ll_router
from deeptutor.services.luban_lesson import LessonNotAvailable


def _invoke(coro_or_val):
    return asyncio.run(coro_or_val) if asyncio.iscoroutine(coro_or_val) else coro_or_val


def _user():
    return SimpleNamespace(user_id="u1")


# ---------------------------------------------------------------------------
# 旗标门（fail-closed）：关 = 空投影 / 404，路由形状稳定。
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_antidote_library_flag_off_empty_projection(monkeypatch):
    monkeypatch.setattr(ll_router, "_review_module_enabled", lambda: False)
    out = _invoke(ll_router.antidote_library(_=_user()))
    assert out == {"total": 0, "packs": [], "enabled": False}


@pytest.mark.unit
def test_antidote_detail_flag_off_404(monkeypatch):
    monkeypatch.setattr(ll_router, "_review_module_enabled", lambda: False)
    with pytest.raises(HTTPException) as exc:
        _invoke(ll_router.antidote_detail("F16", "E03", _=_user()))
    assert exc.value.status_code == 404


@pytest.mark.unit
def test_cloze_deck_flag_off_404(monkeypatch):
    monkeypatch.setattr(ll_router, "_review_module_enabled", lambda: False)
    with pytest.raises(HTTPException) as exc:
        _invoke(ll_router.cloze_deck("A01", _=_user()))
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# 旗标开：透传 runtime 投影 / 缺供给 → 404（错因银行保持占位）。
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_antidote_library_flag_on_projects(monkeypatch):
    monkeypatch.setattr(ll_router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(
        ll_router, "build_antidote_library",
        lambda: {"total": 3, "packs": [{"pack_id": "F16", "antidote_count": 3}]},
    )
    out = _invoke(ll_router.antidote_library(_=_user()))
    assert out["total"] == 3 and out["enabled"] is True
    assert out["packs"][0]["pack_id"] == "F16"


@pytest.mark.unit
def test_antidote_detail_flag_on_returns_vm_head_note_shape(monkeypatch):
    monkeypatch.setattr(ll_router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(
        ll_router, "build_antidote",
        lambda pid, code: {
            "pack_id": pid, "error_code": code,
            "mental_model": "先落采分词，再展开论证。",
            "textbook_ref": "建设工程施工管理 P128",
        },
    )
    out = _invoke(ll_router.antidote_detail("f16", "E03", _=_user()))
    # errorbank vm head-note 钉死形状：{mental_model, textbook_ref}
    assert set(out) >= {"mental_model", "textbook_ref"}
    assert out["mental_model"] and out["textbook_ref"]


@pytest.mark.unit
def test_antidote_detail_not_available_maps_to_404(monkeypatch):
    monkeypatch.setattr(ll_router, "_review_module_enabled", lambda: True)

    def _raise(pid, code):
        raise LessonNotAvailable(pid)

    monkeypatch.setattr(ll_router, "build_antidote", _raise)
    with pytest.raises(HTTPException) as exc:
        _invoke(ll_router.antidote_detail("F16", "E99", _=_user()))
    assert exc.value.status_code == 404


@pytest.mark.unit
def test_cloze_deck_flag_on_projects(monkeypatch):
    monkeypatch.setattr(ll_router, "_review_module_enabled", lambda: True)
    monkeypatch.setattr(
        ll_router, "build_cloze",
        lambda pid: {"pack_id": pid, "recall_prompt": "默写", "skeleton_sentences": []},
    )
    out = _invoke(ll_router.cloze_deck("a01", _=_user()))
    assert out["pack_id"] == "a01" and "skeleton_sentences" in out


# ---------------------------------------------------------------------------
# TestClient 级：挂载 + 鉴权拒绝 + 旗标 fail-closed（真 HTTP 栈）。
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_antidote_http_requires_auth_and_flag_gated(monkeypatch):
    # 鉴权走真 get_current_user（secure_router 默认鉴权），只 stub token 后端。
    auth_module = importlib.import_module("deeptutor.api.dependencies.auth")

    class _FakeMemberConsoleService:
        def verify_access_token(self, token: str):
            return {"uid": "student_http", "provider": "test"} if token == "student-token" else None

        def is_admin_user(self, user_id: str) -> bool:
            return False

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberConsoleService())
    # 旗标关：签名存在也不泄漏 —— detail 一律 404，library 空投影。
    monkeypatch.setattr(ll_router, "_review_module_enabled", lambda: False)

    app = FastAPI()
    app.include_router(ll_router.router, prefix="/api/v1/luban", tags=["luban_lesson"])
    with TestClient(app) as client:
        # 未认证 → 401/403（不许绕过鉴权）。
        assert client.get("/api/v1/luban/antidotes/F16/E03").status_code in (401, 403)

        headers = {"Authorization": "Bearer student-token"}
        # 认证 + 旗标关 → detail 404 同形（fail-closed 占位）。
        assert client.get("/api/v1/luban/antidotes/F16/E03", headers=headers).status_code == 404
        # library 旗标关 → 空投影稳定形状（不 404）。
        lib = client.get("/api/v1/luban/antidotes", headers=headers)
        assert lib.status_code == 200
        assert lib.json()["enabled"] is False and lib.json()["total"] == 0
