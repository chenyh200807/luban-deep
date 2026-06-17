"""Phase 3.2 — 卡片 PATCH/DELETE + 乐观并发（stale version → 409）。

不新增 cards writer endpoint（PRD 禁止）；在既有 notebook router 内加 PATCH/DELETE。
OptimisticConcurrencyError → 409；KeyError → 404；delete = 软删 archived_at。
handler 级测试（不起 HTTP 栈）。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from deeptutor.api.routers import notebook as nb_router
from deeptutor.services.notebook_card.store import OptimisticConcurrencyError


def _patch_card_service(monkeypatch, svc):
    monkeypatch.setattr(nb_router, "get_notebook_card_service", lambda: svc)


@pytest.mark.unit
def test_patch_card_stale_version_returns_409(monkeypatch):
    class _Svc:
        async def update_card(self, **_k):
            raise OptimisticConcurrencyError("stale")

    _patch_card_service(monkeypatch, _Svc())
    body = nb_router.CardPatchRequest(expected_version=1, patch={"title": "new"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(nb_router.update_notebook_card("note_1", body, current_user=SimpleNamespace(user_id="u1")))
    assert exc.value.status_code == 409


@pytest.mark.unit
def test_patch_card_normal_bumps_version(monkeypatch):
    class _Svc:
        async def update_card(self, *, user_id, note_id, expected_version, patch):
            return {"note_id": note_id, "version": expected_version + 1, **patch}

    _patch_card_service(monkeypatch, _Svc())
    body = nb_router.CardPatchRequest(expected_version=1, patch={"title": "new"})
    out = asyncio.run(nb_router.update_notebook_card("note_1", body, current_user=SimpleNamespace(user_id="u1")))
    assert out["success"] is True
    assert out["card"]["version"] == 2 and out["card"]["title"] == "new"


@pytest.mark.unit
def test_patch_card_missing_returns_404(monkeypatch):
    class _Svc:
        async def update_card(self, **_k):
            raise KeyError("not found")

    _patch_card_service(monkeypatch, _Svc())
    body = nb_router.CardPatchRequest(expected_version=1, patch={})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(nb_router.update_notebook_card("note_1", body, current_user=SimpleNamespace(user_id="u1")))
    assert exc.value.status_code == 404


@pytest.mark.unit
def test_delete_card_soft_deletes(monkeypatch):
    calls = {}

    class _Svc:
        async def delete_card(self, *, user_id, note_id, expected_version):
            calls.update(user_id=user_id, note_id=note_id, version=expected_version)
            return {"note_id": note_id, "archived_at": "2026-05-31T00:00:00+08:00", "version": expected_version + 1}

    _patch_card_service(monkeypatch, _Svc())
    out = asyncio.run(nb_router.delete_notebook_card("note_1", expected_version=1, current_user=SimpleNamespace(user_id="u1")))
    assert out["success"] is True
    assert calls["note_id"] == "note_1" and out["card"]["archived_at"]


@pytest.mark.unit
def test_delete_card_stale_version_returns_409(monkeypatch):
    class _Svc:
        async def delete_card(self, **_k):
            raise OptimisticConcurrencyError("stale")

    _patch_card_service(monkeypatch, _Svc())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(nb_router.delete_notebook_card("note_1", expected_version=1, current_user=SimpleNamespace(user_id="u1")))
    assert exc.value.status_code == 409
