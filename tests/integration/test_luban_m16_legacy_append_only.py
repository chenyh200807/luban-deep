"""M16 integration: controlled runtime is append-only — legacy construction_grading_result byte-identical
flag-off vs flag-on; rollback (drop flag) returns legacy-only; production default OFF."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import deeptutor.api._secure_router as secure_router_mod
import deeptutor.capabilities.deep_question as dq
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "artifacts/luban_grading_artifacts/controlled_production_runtime_flip_m16_20260604"
_ws = importlib.util.spec_from_file_location("ws_m16l", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)

_CUR = {"u": "qa_m16_legacy"}
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


def test_legacy_byte_identical_and_append_only():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        off = ws._receive_result(c, _frame(False)).get("metadata") or {}
        on = ws._receive_result(c, _frame(True)).get("metadata") or {}
    assert "luban_grading_engine_v1_controlled_runtime" not in off
    assert "luban_grading_engine_v1_controlled_runtime" in on
    assert off.get("construction_grading_result") == on.get("construction_grading_result")
    assert "luban" not in str((on.get("construction_grading_result") or {}).get("authority") or "")


def test_rollback_drops_to_legacy_only():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        rolled = ws._receive_result(c, _frame(False)).get("metadata") or {}
    assert "luban_grading_engine_v1_controlled_runtime" not in rolled
    assert "construction_grading_result" in rolled


def test_production_default_off_no_flag_no_controlled():
    # no flag at all -> no controlled key (production default OFF)
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = ws._receive_result(c, _frame(False)).get("metadata") or {}
    assert "luban_grading_engine_v1_controlled_runtime" not in md
    # and the helper default cohort excludes real students
    assert dq._v1_controlled_runtime_cohort_member("real_99") is False
    assert dq._v1_controlled_runtime_cohort_member("operator_1") is True


def test_artifact_append_only_audit_clean():
    a = json.loads((OUT / "legacy_append_only_audit_m16.json").read_text("utf-8"))
    assert a["legacy_equal_rate"] == 1.0
    assert a["legacy_overwritten"] is False
    assert a["controlled_is_append_only"] is True
    assert a["production_write_count"] == 0
