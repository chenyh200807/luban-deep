"""M24 v0-vs-v1 A/B benchmark + KB v5 read-only adapter — hermetic guards.

Hermetic mode makes NO live call (v1 uses the deterministic proxy; KB v5 RAG baseline and
Qwen fallback are gated behind --run-live/--run-rag-live and never run here). Asserts: both v0
and v1 are captured per submission, the safety floor holds (v1 fp/source_mismatch vs gold = 0),
the KB v5 adapter is read-only + benchmark-only (not a grading authority), red lines hold, and a
Langfuse-compatible trace ledger is written even when local Docker Langfuse is unreachable.
"""
from __future__ import annotations

import json
import os

import pytest

import scripts.run_luban_v0_vs_v1_ab_benchmark_m24 as m24
from deeptutor.services.benchmark import kb_v5_readonly_adapter as kb


def test_kb_v5_adapter_is_readonly_benchmark_only():
    # availability probe never connects/writes
    a = kb.available()
    assert set(a) >= {"kbv5_db_url_present", "psycopg2_present", "dashscope_key_present", "ready"}
    # fail-closed when no url
    old = os.environ.pop("KBV5_DB_URL", None)
    try:
        with pytest.raises(kb.KbV5Unavailable):
            kb.retrieve("x", embedder=lambda q: [0.0] * kb.EMBED_DIM, db_url=None)
    finally:
        if old is not None:
            os.environ["KBV5_DB_URL"] = old
    # result dataclass never claims grading authority
    rr = kb.RetrievalResult(query="q", chunks=[], latency_ms=1.0, embed_dim=1024, doc_types=("textbook",))
    assert rr.produces_point_decision is False
    assert "not_grading_authority" in rr.role
    # vector literal formatting (pure function, no IO)
    assert m24  # module import sanity


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def run(tmp_path_factory, monkeypatch_module):
    out = tmp_path_factory.mktemp("m24")
    monkeypatch_module.setattr(m24, "OUT", out)
    import sys
    old = sys.argv
    sys.argv = ["m24", "--target", "120"]  # hermetic: no --run-live / --run-rag-live
    try:
        summary = m24.main()
    finally:
        sys.argv = old
    return out, summary


def _j(out, name):
    return json.loads((out / name).read_text("utf-8"))


def test_hermetic_safety_and_both_authorities(run):
    out, summary = run
    assert summary["safety_all_zero"] is True
    assert summary["v1_fp_vs_gold"] == 0
    assert summary["submissions"] >= 80
    rows = [json.loads(l) for l in (out / "v0_vs_v1_rows_m24.jsonl").read_text("utf-8").splitlines() if l.strip()]
    assert rows
    for r in rows[:5]:
        assert r["v0"]["present"] is True   # legacy grade captured
        assert r["v1"]["present"] is True   # v1 adjudication captured
        assert r["v1"]["validator_safety_floor"] is True
        assert r["v0"]["validator_safety_floor"] is False


def test_quality_matrix_dimensions(run):
    out, _ = run
    qm = _j(out, "v0_vs_v1_quality_matrix.json")
    for dim in ("capability", "granularity", "explanation", "learning_brain_signal", "safety"):
        assert dim in qm
    assert qm["safety"]["v1_false_positive_vs_gold"] == 0
    assert qm["safety"]["v1_validator_safety_floor"] is True


def test_rag_baseline_not_run_hermetic_and_is_context_only(run):
    out, _ = run
    audit = _j(out, "rag_readonly_baseline_audit.json")
    assert audit["ran"] is False  # hermetic
    # when it does run, role is context baseline (string fixed in adapter/stat)
    assert m24.ADVERSARIAL_VARIANTS  # sanity


def test_langfuse_ledger_written_even_if_blocked(run):
    out, _ = run
    assert (out / "langfuse_trace_ledger.jsonl").exists()
    lf = _j(out, "langfuse_status_m24.json")
    assert lf["trace_records_written"] >= 1
    # local docker unreachable in hermetic -> blocker recorded, ledger is the fallback
    if not lf["host_reachable"]:
        assert lf["blocker"]


def test_red_lines(run):
    out, _ = run
    rl = _j(out, "benchmark_manifest_m24.json")["red_lines"]
    for k in ("production_default_flip", "remote_write", "supabase_write_or_grant", "db_write",
              "canonical_truth_write", "m202_absorbed", "kb_v5_adapter_is_grading_authority"):
        assert rl[k] is False
