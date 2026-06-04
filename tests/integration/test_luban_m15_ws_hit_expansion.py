"""M15 integration: a counted authority-backed point genuinely auto-certifies over the REAL /api/v1/ws
with a rich answer, and a spec-wrong answer never does (target-point FP=0)."""
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
_ws = importlib.util.spec_from_file_location("ws_m15t", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)
_m12 = importlib.util.spec_from_file_location("m12_m15t", REPO / "scripts" / "run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12); _m12.loader.exec_module(m12)

_CUR = {"u": "qa_m15_ws"}
COUNTED_MK = {"numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment"}


def _client(tmp):
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
    ws._install_fakes(rt, user_id=_CUR["u"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["u"])
    return TestClient(ws._build_ws_app())


def _frame(qid, ans):
    return {"type": "start_turn", "content": ans, "capability": "deep_question", "language": "zh",
            "config": {"grading_engine_v1_beta_shadow": True,
                       "followup_question_context": {"question_id": qid, "question_type": "case", "question": "q", "correct_answer": ans}}}


def _auto(meta, pid):
    beta = meta.get("luban_grading_engine_v1_beta_shadow") or {}
    return any(p["point_id"] == pid and p.get("auto_shadow")
               and p.get("path") == "machine_checkable_spec_path" for p in beta.get("point_results", []))


def test_counted_machine_point_autos_with_correct_answer_and_rejects_wrong():
    s = bsl.load_beta_supply()
    candidates = [(k, v) for k, v in s.machine_specs.items() if v["spec"].get("kind") in COUNTED_MK]
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        # find a counted machine point whose question genuinely grades + autos on its correct answer
        proven = None
        for (qid, pid), row in candidates:
            ok = (ws._receive_result(c, _frame(qid, m12._correct_machine_answer(row["spec"]))).get("metadata") or {})
            if _auto(ok, pid):
                bad = (ws._receive_result(c, _frame(qid, m12._wrong_machine_answer(row["spec"]))).get("metadata") or {})
                proven = (qid, pid, _auto(bad, pid))
                break
        assert proven is not None, "expected at least one counted machine point to auto on its correct answer"
        assert proven[2] is False  # the spec-wrong answer never auto-certifies that same point (FP=0)


def test_legacy_never_overwritten_on_rich_answer():
    s = bsl.load_beta_supply()
    qid = next(iter(s.machine_specs))[0]
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        off = (ws._receive_result(c, {"type": "start_turn", "content": "x", "capability": "deep_question",
               "language": "zh", "config": {"followup_question_context": {"question_id": qid, "question_type": "case", "question": "q", "correct_answer": "x"}}}).get("metadata") or {})
        on = (ws._receive_result(c, _frame(qid, "工期 25 个月，合理")).get("metadata") or {})
    assert "luban_grading_engine_v1_beta_shadow" not in off
    assert "luban" not in str((on.get("construction_grading_result") or {}).get("authority") or "")
