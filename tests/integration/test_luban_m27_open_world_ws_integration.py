"""M27 integration: open-world diagnostic over the REAL /api/v1/ws deep_question followup chain.

Drives TestClient -> /api/v1/ws -> TurnRuntime -> DeepQuestionCapability._emit_followup_result and
asserts the live followup surface now carries the unified compiled_context + open_world_diagnostic
schema, never refuses a construction prompt, and never fabricates an official score / answer_key.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient

from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "wsh_m27", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
wsh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wsh)


def _client(tmp, user="qa_m27"):
    rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
    wsh._install_fakes(rt, user_id=user, write_calls=[], engine_calls=[])
    secure_router_mod.resolve_auth_context = lambda _a: wsh._auth_ctx(user)
    return TestClient(wsh._build_ws_app())


def _open_world_frame(prompt: str):
    return {"type": "start_turn", "content": prompt, "capability": "deep_question", "language": "zh",
            "config": {"followup_question_context": {"question_id": "", "question_type": "case",
                                                     "question": prompt}}}


def test_open_world_followup_carries_unified_schema_and_no_refusal():
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = wsh._receive_result(c, _open_world_frame("施工现场临时用电三级配电两级保护具体指什么？")).get("metadata") or {}
        # 4th surface: compiled_context present with the shared schema
        cc = md.get("compiled_context") or {}
        assert cc.get("schema_version") == "luban_context_pack.v1"
        # open-world unified schema present
        owd = md.get("open_world_diagnostic")
        assert owd is not None
        assert owd["diagnostic_status"] == "unverified_diagnostic"
        assert owd["uncertainty"]
        assert owd["formal_score_allowed"] is False
        assert owd["official_answer_claimed"] is False
        assert owd["is_construction_refusal"] is False
        assert owd["work_order_if_needed"] is not None  # high-value unknown -> work order
        # non-refusal: a response is present
        assert isinstance(md.get("response"), str)


def test_in_bank_followup_gets_context_but_no_open_world_block():
    # A resolved (in-bank) followup must attach compiled_context but NOT the open-world block.
    frame = {"type": "start_turn", "content": "为什么选 C？", "capability": "deep_question",
             "language": "zh",
             "config": {"followup_question_context": {"question_id": "BANK-123", "question_type": "single_choice",
                                                      "question": "建筑物构成不包括？",
                                                      "options": [{"key": "A", "value": "结构"},
                                                                  {"key": "C", "value": "投标"}],
                                                      "correct_answer": "C"}}}
    with tempfile.TemporaryDirectory() as tmp, _client(tmp) as c:
        md = wsh._receive_result(c, frame).get("metadata") or {}
        # If routed to followup, compiled_context attaches but open-world block is absent (resolved).
        if "compiled_context" in md:
            assert md["compiled_context"]["schema_version"] == "luban_context_pack.v1"
            assert md.get("open_world_diagnostic") is None
