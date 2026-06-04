"""M12 integration: v1 beta_shadow over the REAL ``/api/v1/ws`` path (TestClient).

Drives the production wire (TurnRuntimeManager -> ChatOrchestrator -> DeepQuestionCapability ->
_maybe_attach_v1_beta_shadow) — NOT the hook directly — to prove the runtime contract:
flag off legacy-only, flag on append-only, kill switch, non-qa blocked, legacy never overwritten,
duplicate idempotent, Learning Brain preview-only. External providers/DB are deterministic fixtures.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl

_spec = importlib.util.spec_from_file_location(
    "ws_smoke_m12", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

_CUR = {"user": "qa_m12_ws"}
_QID = "M2-2015-30-01"
_ANSWER = "工期为 25 个月，合理。"


@pytest.fixture(scope="module")
def client():
    tmp = tempfile.mkdtemp(prefix="luban-m12-ws-")
    runtime = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "m12.db"))
    ws._install_fakes(runtime, user_id=_CUR["user"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["user"])
    with TestClient(ws._build_ws_app()) as c:
        yield c


def _frame(flag: bool):
    cfg: dict[str, Any] = {"followup_question_context": {
        "question_id": _QID, "question_type": "case", "question": "q", "correct_answer": _ANSWER}}
    if flag:
        cfg["grading_engine_v1_beta_shadow"] = True
    return {"type": "start_turn", "content": _ANSWER, "capability": "deep_question", "language": "zh", "config": cfg}


def _meta(client, flag, user="qa_m12_ws"):
    _CUR["user"] = user
    return (ws._receive_result(client, _frame(flag)).get("metadata") or {})


def test_ws_flag_off_is_legacy_only(client):
    m = _meta(client, flag=False)
    assert "luban_grading_engine_v1_beta_shadow" not in m
    assert "construction_grading_result" in m


def test_ws_flag_on_appends_beta(client):
    m = _meta(client, flag=True)
    beta = m.get("luban_grading_engine_v1_beta_shadow")
    assert beta is not None
    assert beta["authority"] == "luban_grading_engine_v1_beta_shadow"
    assert beta["not_production_grade"] is True
    assert beta["writeback_performed"] is False


def test_ws_legacy_never_overwritten(client):
    off = _meta(client, flag=False).get("construction_grading_result")
    on = _meta(client, flag=True).get("construction_grading_result")
    assert off == on
    # the real legacy grading authority is "construction_grading"; beta never replaces it
    assert "luban" not in str(on.get("authority") or "")


def test_ws_kill_switch(client, monkeypatch):
    monkeypatch.setenv("LUBAN_V1_BETA_SHADOW_ENABLED", "false")
    beta = _meta(client, flag=True).get("luban_grading_engine_v1_beta_shadow")
    assert beta is not None and beta["shadow_status"] == "killed_by_switch"
    assert "point_results" not in beta


def test_ws_non_qa_blocked(client):
    m = _meta(client, flag=True, user="real_student_777")
    assert "luban_grading_engine_v1_beta_shadow" not in m


def test_ws_duplicate_idempotent(client):
    a = _meta(client, flag=True).get("luban_grading_engine_v1_beta_shadow")
    b = _meta(client, flag=True).get("luban_grading_engine_v1_beta_shadow")
    assert a.get("point_results") == b.get("point_results")
    assert a.get("auto_shadow_count") == b.get("auto_shadow_count")


def test_ws_learning_brain_preview_only(client):
    beta = _meta(client, flag=True).get("luban_grading_engine_v1_beta_shadow")
    lb = beta["learning_brain_preview"]
    assert lb["writeback_performed"] is False
    assert lb["production_user_written"] is False
    assert beta["teacher_review_queue_item"]["qa_simulated"] is True


def test_ws_artifact_failclosed(client):
    # bulletproof save/restore (the module-scoped client references the live module global)
    orig = bsl.load_beta_supply

    def _boom(*a, **k):
        raise bsl.BetaSupplyUnavailable("drill")

    bsl.load_beta_supply = _boom
    bsl.build_beta_shadow_payload.__globals__["load_beta_supply"] = _boom
    try:
        m = _meta(client, flag=True)
        beta = m.get("luban_grading_engine_v1_beta_shadow")
        assert beta["shadow_status"] == "beta_supply_unavailable"
        assert "luban" not in str(m["construction_grading_result"].get("authority") or "")
    finally:
        bsl.load_beta_supply = orig
        bsl.build_beta_shadow_payload.__globals__["load_beta_supply"] = orig
