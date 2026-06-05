"""M16 integration: controlled_runtime_candidate over the REAL /api/v1/ws — cohort hit, non-cohort
blocked, flag off legacy-only, mode promoted from beta_shadow."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl

REPO = Path(__file__).resolve().parents[2]
_ws = importlib.util.spec_from_file_location("ws_m16t", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)

_CUR = {"u": "qa_m16_ws"}
ANS = "工期为 25 个月，合理。"


def _client(tmp):
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
    ws._install_fakes(rt, user_id=_CUR["u"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["u"])
    return TestClient(ws._build_ws_app())


def _frame(flag):
    cfg = {"followup_question_context": {"question_id": "M2-2015-30-01", "question_type": "case", "question": "q", "correct_answer": ANS}}
    if flag:
        cfg["grading_engine_v1_controlled_runtime"] = True
    return {"type": "start_turn", "content": ANS, "capability": "deep_question", "language": "zh", "config": cfg}


def _meta(c, flag, user):
    _CUR["u"] = user
    return ws._receive_result(c, _frame(flag)).get("metadata") or {}


def test_registry_present_for_runtime():
    # the controlled hook needs a loadable release_candidate registry
    assert bsl.load_release_candidate_registry()["status"] == "release_candidate"


def test_controlled_cohort_hit_and_mode_promoted():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        for u in ("qa_x", "test_x", "operator_x"):
            md = _meta(c, True, u)
            ctrl = md.get("luban_grading_engine_v1_controlled_runtime")
            assert ctrl is not None, f"cohort {u} should get controlled runtime"
            assert ctrl["mode"] == "controlled_runtime_candidate"
            assert ctrl["registry_status"] == "release_candidate"
            assert ctrl["production_default"] == "off"
            assert ctrl["production_runtime_connected"] is False


def test_non_cohort_real_student_blocked():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        for u in ("real_student_1", "student_42"):
            assert "luban_grading_engine_v1_controlled_runtime" not in _meta(c, True, u)


def test_flag_off_is_legacy_only():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = _meta(c, False, "qa_x")
        assert "luban_grading_engine_v1_controlled_runtime" not in md
        assert "construction_grading_result" in md
