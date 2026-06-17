"""M22R RAG baseline recovery + Qwen fallback closure — hermetic guards.

Hermetic mode makes NO live call (no Supabase, no Qwen). It checks: the real RAG path
is Supabase (not a local-KB assumption), no official_answer / second authority / remote
write, the double-provider failure fails closed with legacy intact, and the verdict
gate is safety-driven. Live RAG/Qwen are gated behind --run-rag-live / --run-live and
never exercised here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_rag_baseline_and_fallback_closure_m22r as m22r
from deeptutor.services.construction_grading import beta_shadow_loader as bsl


def test_rag_queries_exclude_official_answer():
    supply = bsl.load_beta_supply()
    queries = m22r._rag_queries(supply)
    assert queries, "no RAG queries built"
    # all M14B-origin queries must come from non-official-answer candidates (the builder filters them)
    raw = [json.loads(l) for l in m22r.M14B.read_text("utf-8").splitlines() if l.strip()]
    official = {(r.get("candidate_excerpt") or "")[:120] for r in raw if r.get("official_answer_as_stem_source")}
    for q in queries:
        if q["origin"] == "m14b_case_stem":
            assert q["query"] not in official


def test_force_fallback_then_double_fail_providers():
    # forced-fallback raises on primary, delegates to fallback
    calls = []
    def orig(role, system, user, env):
        calls.append(role); return "[]"
    prov = m22r._force_fallback_provider(orig)
    with pytest.raises(m22r.adj.AdjudicatorUnavailable):
        prov("primary", "s", "u", {})
    assert prov("fallback", "s", "u", {}) == "[]"
    # double-fail raises on any role
    with pytest.raises(m22r.adj.AdjudicatorUnavailable):
        m22r._double_fail_provider("primary", "s", "u", {})
    with pytest.raises(m22r.adj.AdjudicatorUnavailable):
        m22r._double_fail_provider("fallback", "s", "u", {})


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def run(tmp_path_factory, monkeypatch_module):
    out = tmp_path_factory.mktemp("m22r")
    monkeypatch_module.setattr(m22r, "OUT", out)
    import sys
    old = sys.argv
    sys.argv = ["m22r", "--fallback-target", "50"]  # hermetic: no --run-live / --run-rag-live
    try:
        summary = m22r.main()
    finally:
        sys.argv = old
    return out, summary


def _j(out, name):
    return json.loads((out / name).read_text("utf-8"))


def test_hermetic_safety_all_zero_and_failclosed(run):
    out, summary = run
    assert summary["safety_all_zero"] is True
    assert summary["double_provider_failclosed"] is True  # deterministic dual-fail check runs hermetic
    v = _j(out, "corrected_m22_verdict_m22r.json")
    for k in ("qwen_false_positive", "qwen_source_mismatch", "qwen_bad_certified",
              "rag_official_answer_indexed", "rag_second_authority_created", "double_fail_fail_open"):
        assert v["safety"][k] == 0


def test_required_artifacts_exist(run):
    out, _ = run
    for name in ("rag_baseline_recovery_audit_m22r.json", "recovered_rag_results_m22r.jsonl",
                 "qwen_fallback_results_m22r.jsonl", "deepseek_vs_qwen_comparison_m22r.csv",
                 "corrected_quality_metrics_m22r.json", "corrected_latency_cost_metrics_m22r.json",
                 "adversarial_rag_and_fallback_report_m22r.json", "corrected_m22_verdict_m22r.json",
                 "FINDING_rag_vs_luban_v1_benchmark_closure_m22r_20260605.md"):
        assert (out / name).exists(), name


def test_rag_path_is_supabase_not_local_assumption(run):
    out, _ = run
    audit = _j(out, "rag_baseline_recovery_audit_m22r.json")
    assert "Supabase" in audit["real_rag_path"]
    assert audit["official_answer_used_as_source"] is False
    assert audit["second_rag_authority_created"] is False
    assert audit["remote_write_or_schema_deploy"] is False


def test_no_runtime_pollution_redlines(run):
    out, _ = run
    v = _j(out, "corrected_m22_verdict_m22r.json")
    assert v["production_default_changed"] is False
    assert v["remote_write"] is False
    assert v["registry_published"] is False
    assert v["m202_absorbed"] is False
