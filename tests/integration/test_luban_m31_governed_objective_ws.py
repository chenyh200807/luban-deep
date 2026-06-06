"""M31 integration: governed objective release-truth over the REAL /api/v1/ws.

Proves the full real chain: WS frame -> TurnRuntimeManager.start_turn -> runtime_only_keys allowlist
passthrough (the M31 flag would be Pydantic-rejected without the allowlist edit) -> ChatOrchestrator
-> DeepQuestionCapability -> ``_maybe_attach_m31_governed_objective`` -> governed signed bundle ->
CONTROLLED release-truth. Cohort hit, non-cohort blocked, flag-off legacy-only, legacy untouched.

Uses the REAL tracked governed bundle persisted by the M31 runner (a real in-bank objective qid).
Skips cleanly if that tracked bundle is absent (Step 0 not yet run in this checkout).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
import pytest

import deeptutor.api._secure_router as secure_router_mod
from deeptutor.services.construction_grading import objective_runtime_adapter as A
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

REPO = Path(__file__).resolve().parents[2]
_ws = importlib.util.spec_from_file_location(
    "ws_m31", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws)
_ws.loader.exec_module(ws)

KEY = "luban_grading_engine_m31_governed_objective"
_CUR = {"u": "qa_m31_ws"}


def _governed_sample():
    A._governed_index.cache_clear()
    verified, index, _cov = A._governed_index()
    if not verified or not index:
        return None
    qid = next(iter(index))
    return qid, str(index[qid].get("answer_key") or "")


_SAMPLE = _governed_sample()
pytestmark = pytest.mark.skipif(
    _SAMPLE is None, reason="M31 tracked governed bundle absent; run scripts/run_luban_m31_governed_objective_runtime_binding.py")


@pytest.fixture(autouse=True)
def _real_governed_cache():
    # other suites monkeypatch _GOVERNED_BUNDLE; clear so we load the REAL tracked bundle here.
    A._governed_index.cache_clear()
    yield
    A._governed_index.cache_clear()


def _client(tmp):
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
    ws._install_fakes(rt, user_id=_CUR["u"], write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["u"])
    return TestClient(ws._build_ws_app())


def _frame(answer, *, flag):
    qid = _SAMPLE[0]
    cfg = {"followup_question_context": {
        "question_id": qid, "question_type": "case",
        "question": "objective governed binding probe", "correct_answer": answer}}
    if flag:
        cfg["grading_engine_m31_governed_objective"] = True
    return {"type": "start_turn", "content": answer, "capability": "deep_question",
            "language": "zh", "config": cfg}


def _meta(c, *, flag, user, answer):
    _CUR["u"] = user
    return ws._receive_result(c, _frame(answer, flag=flag)).get("metadata") or {}


def test_cohort_governed_hit_is_release_truth():
    qid, key = _SAMPLE
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        for u in ("qa_x", "test_x", "operator_x"):
            md = _meta(c, flag=True, user=u, answer=key)
            gov = md.get(KEY)
            assert gov is not None, f"cohort {u} should get governed objective payload"
            assert gov["mode"] == "governed_objective_release_candidate"
            assert gov["release_truth"] is True
            assert gov["official_score_allowed"] is True
            assert gov["controlled_official"] is True
            assert gov["result"]["is_correct"] is True
            assert "construction_grading_result" in md  # legacy still present (append-only)


def test_non_cohort_real_student_blocked():
    _qid, key = _SAMPLE
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        for u in ("real_student_1", "student_42"):
            assert KEY not in _meta(c, flag=True, user=u, answer=key)


def test_flag_off_is_legacy_only():
    _qid, key = _SAMPLE
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = _meta(c, flag=False, user="qa_x", answer=key)
        assert KEY not in md
        assert "construction_grading_result" in md
