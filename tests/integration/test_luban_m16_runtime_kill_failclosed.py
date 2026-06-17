"""M16 integration: controlled-runtime kill switch + malformed-registry fail-closed over real WS."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl

REPO = Path(__file__).resolve().parents[2]
_ws = importlib.util.spec_from_file_location("ws_m16k", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)

_CUR = {"u": "qa_m16_kill"}
ANS = "工期为 25 个月，合理。"


def _client(tmp):
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
    ws._install_fakes(rt, user_id=_CUR["u"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["u"])
    return TestClient(ws._build_ws_app())


def _frame():
    return {"type": "start_turn", "content": ANS, "capability": "deep_question", "language": "zh",
            "config": {"grading_engine_v1_controlled_runtime": True,
                       "followup_question_context": {"question_id": "M2-2015-30-01", "question_type": "case", "question": "q", "correct_answer": ANS}}}


def test_kill_switch_blocks_controlled_runtime(monkeypatch):
    monkeypatch.setenv("LUBAN_V1_CONTROLLED_RUNTIME_ENABLED", "false")
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        ctrl = (ws._receive_result(c, _frame()).get("metadata") or {}).get("luban_grading_engine_v1_controlled_runtime")
    assert ctrl is not None and ctrl["shadow_status"] == "killed_by_switch"
    assert "point_results" not in ctrl


def test_malformed_registry_fails_closed_in_runtime():
    orig = bsl.load_release_candidate_registry

    def _boom(*a, **k):
        raise bsl.ReleaseCandidateUnavailable("test")

    bsl.load_release_candidate_registry = _boom
    bsl.build_controlled_runtime_payload.__globals__["load_release_candidate_registry"] = _boom
    try:
        with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
            md = ws._receive_result(c, _frame()).get("metadata") or {}
    finally:
        bsl.load_release_candidate_registry = orig
        bsl.build_controlled_runtime_payload.__globals__["load_release_candidate_registry"] = orig
    ctrl = md.get("luban_grading_engine_v1_controlled_runtime")
    assert ctrl["shadow_status"] == "release_candidate_registry_unavailable"
    assert "luban" not in str((md.get("construction_grading_result") or {}).get("authority") or "")
    assert "point_results" not in ctrl


def test_kill_switch_absent_allows_when_registry_ok(monkeypatch):
    monkeypatch.delenv("LUBAN_V1_CONTROLLED_RUNTIME_ENABLED", raising=False)
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        ctrl = (ws._receive_result(c, _frame()).get("metadata") or {}).get("luban_grading_engine_v1_controlled_runtime")
    assert ctrl is not None and ctrl.get("mode") == "controlled_runtime_candidate"
