"""M17A integration: LLM adjudication over the REAL /api/v1/ws path (fake provider injected for
determinism) — cohort hit, flag-off legacy, non-cohort blocked, kill switch, provider fail-closed,
append-only, validator floor keeps fp=0."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import pytest

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl
from deeptutor.services.construction_grading import runtime_llm_adjudicator as adj

REPO = Path(__file__).resolve().parents[2]
_ws = importlib.util.spec_from_file_location("ws_m17at", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)

_CUR = {"u": "qa_m17a_ws"}
ANS = "工期为 25 个月，合理。"


@pytest.fixture(autouse=True)
def _fake_provider(monkeypatch):
    # deterministic fake: LLM marks every point 'partial' (never auto) — validator-safe, no live call
    def fake(role, system, user, env):
        payload = json.loads(user)
        return json.dumps([{"point_id": p["point_id"], "disposition": "partial",
                            "evidence_span": "25", "confidence": 0.7, "reasoning_summary": "fake"} for p in payload["points"]], ensure_ascii=False)
    monkeypatch.setattr(adj, "_default_provider", fake)


def _client(tmp):
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
    ws._install_fakes(rt, user_id=_CUR["u"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["u"])
    return TestClient(ws._build_ws_app())


def _frame(flag):
    cfg = {"followup_question_context": {"question_id": "M2-2015-30-01", "question_type": "case", "question": "q", "correct_answer": ANS}}
    if flag:
        cfg["grading_engine_v1_llm_adjudication"] = True
    return {"type": "start_turn", "content": ANS, "capability": "deep_question", "language": "zh", "config": cfg}


def _meta(c, flag, user):
    _CUR["u"] = user
    return ws._receive_result(c, _frame(flag)).get("metadata") or {}


def test_cohort_llm_adjudication_appended():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        for u in ("qa_x", "test_x", "operator_x"):
            md = _meta(c, True, u)
            a = md.get("luban_grading_engine_v1_llm_adjudication")
            assert a is not None and a["mode"] == "llm_adjudication_candidate"
            assert a["registry_status"] == "release_candidate"
            assert a["model_used"] == adj.FALLBACK_MODEL or a["model_used"] == adj.PRIMARY_MODEL
            assert a["false_positive"] == 0


def test_flag_off_legacy_only():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = _meta(c, False, "qa_x")
        assert "luban_grading_engine_v1_llm_adjudication" not in md
        assert "construction_grading_result" in md


def test_non_cohort_blocked():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        assert "luban_grading_engine_v1_llm_adjudication" not in _meta(c, True, "real_student_1")


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("LUBAN_V1_LLM_ADJUDICATOR_ENABLED", "false")
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        a = _meta(c, True, "qa_x").get("luban_grading_engine_v1_llm_adjudication")
    assert a is not None and a["shadow_status"] == "killed_by_switch"


def test_legacy_append_only():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        off = _meta(c, False, "qa_x")
        on = _meta(c, True, "qa_x")
    assert off.get("construction_grading_result") == on.get("construction_grading_result")
    assert "luban" not in str((on.get("construction_grading_result") or {}).get("authority") or "")


def test_provider_failclosed_keeps_legacy(monkeypatch):
    def boom(role, system, user, env):
        raise RuntimeError("provider down")
    monkeypatch.setattr(adj, "_default_provider", boom)
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = _meta(c, True, "qa_x")
    a = md.get("luban_grading_engine_v1_llm_adjudication")
    # both providers fail -> adjudicator fail-closed; every point needs_review, never auto; legacy intact
    assert a is not None
    assert a.get("adjudicator_failclosed") is True or a.get("auto_shadow_count") == 0
    assert "luban" not in str((md.get("construction_grading_result") or {}).get("authority") or "")
