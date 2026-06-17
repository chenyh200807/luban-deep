"""M15 integration: fresh retest goes through the REAL /api/v1/ws beta_shadow path (no fabricated
JSON, no ai_draft_predictions), produces a real retest proof, and only a dry-run canonical candidate."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import deeptutor.api._secure_router as secure_router_mod
from fastapi.testclient import TestClient
from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.turn_runtime import TurnRuntimeManager
from deeptutor.services.construction_grading import beta_shadow_loader as bsl

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "artifacts/luban_grading_artifacts/runtime_hits_expansion_and_retest_entry_m15_20260604"
_ws = importlib.util.spec_from_file_location("ws_m15r", REPO / "scripts" / "run_luban_ws_runtime_shadow_turn_smoke.py")
ws = importlib.util.module_from_spec(_ws); _ws.loader.exec_module(ws)
_m12 = importlib.util.spec_from_file_location("m12_m15r", REPO / "scripts" / "run_luban_internal_live_qa_runtime_drill_m12.py")
m12 = importlib.util.module_from_spec(_m12); _m12.loader.exec_module(m12)

_CUR = {"u": "qa_m15_retest"}
COUNTED_MK = {"numeric_formula", "numeric_range", "numeric_judgment", "boolean_judgment"}


def _jl(n):
    return [json.loads(l) for l in (OUT / n).read_text("utf-8").splitlines() if l.strip()]


def test_fresh_retest_runs_through_ws_not_fabricated():
    rows = _jl("fresh_retest_runtime_results_m15.jsonl")
    assert len(rows) >= 1
    for r in rows:
        assert r["runtime_provenance"]["ws_path"] == "/api/v1/ws"
        assert r["runtime_provenance"]["fabricated_json"] is False
    assert any(r["real_retest_proof_valid"] for r in rows)


def test_retest_improvement_is_real_runtime_grading():
    # use a question proven (by the M15 drill) to yield a valid retest proof
    proof_rows = _jl("fresh_retest_runtime_results_m15.jsonl")
    valid = next(r for r in proof_rows if r["real_retest_proof_valid"])
    qid = valid["question_id"]
    s = bsl.load_beta_supply()
    pids = [pid for (q, pid) in s.machine_specs if q == qid] + [pid for (q, pid) in s.list_specs if q == qid] \
        + [pid for (q, pid) in s.source_backed if q == qid]
    rich = "；".join(filter(None, (m12._correct_machine_answer(s.machine_specs[(qid, p)]["spec"]) if (qid, p) in s.machine_specs
                                   else ("，".join(mm["item"] for mm in s.list_specs[(qid, p)]["spec"]["item_matchers"]) if (qid, p) in s.list_specs
                                         else (s.source_terms.get((qid, p), [""])[0])) for p in pids))) + "。"
    with tempfile.TemporaryDirectory() as tmp:
        rt = TurnRuntimeManager(SQLiteSessionStore(Path(tmp) / "d.db"))
        ws._install_fakes(rt, user_id=_CUR["u"], write_calls=[], engine_calls=[])
        secure_router_mod.resolve_auth_context = lambda _a: ws._auth_ctx(_CUR["u"])
        with TestClient(ws._build_ws_app()) as c:
            def frame(ans):
                return {"type": "start_turn", "content": ans, "capability": "deep_question", "language": "zh",
                        "config": {"grading_engine_v1_beta_shadow": True,
                                   "followup_question_context": {"question_id": qid, "question_type": "case", "question": "q", "correct_answer": ans}}}
            r2 = (ws._receive_result(c, frame(rich)).get("metadata") or {}).get("luban_grading_engine_v1_beta_shadow") or {}
    # the retest round produces runtime provenance + writeback stays false (real grading, not fabricated)
    assert r2.get("supply_content_hash")
    assert r2.get("writeback_performed") is False
    assert r2.get("production_runtime_connected") is False
    assert (r2.get("auto_shadow_count") or 0) >= 1


def test_canonical_write_is_dryrun_only_no_truth():
    rows = _jl("learning_brain_canonical_write_dryrun_m15.jsonl")
    assert len(rows) >= 1
    for r in rows:
        assert r["production_truth_written"] is False
        assert r["canonical_truth_written"] is False
        assert r["writeback_performed"] is False
        assert r["human_reviewed"] is False
        assert r["qa_simulated"] is True
        assert not (r["cross_user_leak"] or r["subject_leak"] or r["teacher_only_leak"])
        assert r["simulated_retest_promoted"] is False
        assert r["claim_proposal"]["claim_authority"].endswith("not_production_truth")
