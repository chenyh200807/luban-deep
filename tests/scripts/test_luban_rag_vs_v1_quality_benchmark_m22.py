"""M22 RAG-vs-Luban-v1 quality benchmark — hermetic guards.

These tests run the benchmark in its HERMETIC mode (line C uses a deterministic
LLM-proxy; NO live DeepSeek/Qwen call). They assert the safety floor (fp /
source_mismatch / bad_certified / list-partial-auto / unsupported-positive all 0),
the 4-line structure, honest line-A downgrade, and that the M20.2 delta is never
absorbed into runtime. Live quality is a separate --run-live concern, never tested.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_rag_vs_v1_quality_benchmark_m22 as m22
from deeptutor.services.construction_grading import beta_shadow_loader as bsl


@pytest.fixture(scope="module")
def supply_registry():
    return bsl.load_beta_supply(), bsl.load_release_candidate_registry()


def test_sample_builder_covers_types_and_gold(supply_registry):
    supply, registry = supply_registry
    samples = m22._build_samples(supply, registry, target=210)
    assert len(samples) >= 100
    # every sample has a final gold per counted point (no unknown)
    for s in samples:
        assert s["counted_point_ids"]
        for pid in s["counted_point_ids"]:
            assert pid in s["gold"]
            assert isinstance(s["gold"][pid]["gold_auto_eligible"], bool)
    # at least 3 of the 4 registry-counted question types present
    types = {s["gold"][p]["question_type"] for s in samples for p in s["counted_point_ids"]}
    assert len({"教材知识", "案例判断", "综合review", "索赔工期费用计算"} & types) >= 3


def test_boolean_gold_is_polarity_truth_not_subset(supply_registry):
    """Regression for the boolean_judgment gold-attribution fix: a boolean point is gold-eligible
    iff the answer asserts the correct polarity (shared evidence), not iff it was in the subset."""
    supply, registry = supply_registry
    samples = m22._build_samples(supply, registry, target=210)
    # find a boolean point in a partial variant whose answer asserts the negative judgment
    found = False
    for s in samples:
        for pid in s["counted_point_ids"]:
            spec = supply.machine_specs.get((s["question_id"], pid), {}).get("spec", {})
            if spec.get("kind") == "boolean_judgment":
                expect = bsl._extract_judgment(s["answer"]) == spec.get("expected_bool")
                assert s["gold"][pid]["gold_auto_eligible"] == expect
                found = True
    assert found, "no boolean_judgment point exercised"


@pytest.fixture(scope="module")
def run(tmp_path_factory, monkeypatch_module):
    out = tmp_path_factory.mktemp("m22")
    monkeypatch_module.setattr(m22, "OUT", out)
    summary = _run_main(["--target", "210"])
    return out, summary


def _run_main(argv):
    import sys
    old = sys.argv
    sys.argv = ["m22"] + argv
    try:
        return m22.main()
    finally:
        sys.argv = old


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


def _j(out: Path, name: str):
    return json.loads((out / name).read_text("utf-8"))


def test_hermetic_run_safety_all_zero(run):
    out, summary = run
    assert summary["safety_all_zero"] is True
    s = summary["safety"]
    for k in ("false_positive_B", "false_positive_C", "bad_certified_B", "bad_certified_C",
              "source_mismatch_C", "list_partial_auto", "unsupported_positive",
              "teacher_only_leak", "source_laundering_auto"):
        assert s[k] == 0, (k, s[k])


def test_scale_and_point_decisions(run):
    out, summary = run
    assert summary["submissions"] >= 100
    assert summary["point_decisions_B"] >= 300
    assert summary["line_c_mode"] == "deterministic_proxy_pipeline_only"  # hermetic: no live


def test_all_required_artifacts_exist(run):
    out, _ = run
    for name in ("benchmark_manifest_m22.json", "sample_inventory_m22.jsonl",
                 "baseline_rag_results_m22.jsonl", "deterministic_m16_results_m22.jsonl",
                 "runtime_llm_v1_results_m22.jsonl", "delta_candidate_m202_results_m22.jsonl",
                 "paired_comparison_matrix_m22.csv", "quality_metrics_m22.json",
                 "latency_cost_metrics_m22.json", "answer_quality_examples_m22.md",
                 "adversarial_verification_m22.json", "council_review_m22.jsonl",
                 "decision_report_m22.md"):
        assert (out / name).exists(), name


def test_line_a_rag_honestly_downgraded(run):
    out, _ = run
    audit = _j(out, "missing_input_audit_m22.json")["line_A_old_rag"]
    assert audit["fabricated_retrieval_metrics"] is False
    rows = [json.loads(l) for l in (out / "baseline_rag_results_m22.jsonl").read_text("utf-8").splitlines() if l.strip()]
    assert rows and all(r["produces_point_decisions"] is False for r in rows)
    assert all(r["validator_gated"] is False for r in rows)


def test_m202_delta_never_absorbed_into_runtime(run):
    out, _ = run
    summary = _j(out, "delta_candidate_summary_m22.json")
    assert summary["absorbed_into_runtime"] is False
    assert "candidate_context_only" in summary["runtime_effect_all"]
    rows = [json.loads(l) for l in (out / "delta_candidate_m202_results_m22.jsonl").read_text("utf-8").splitlines() if l.strip()]
    assert all(r["produces_point_decisions"] is False for r in rows)
    # projected token saving is non-negative and reported honestly
    assert summary["packet_tokens_saved_pct"] >= 0


def test_manifest_red_lines(run):
    out, _ = run
    rl = _j(out, "benchmark_manifest_m22.json")["red_lines"]
    for k in ("production_default_flip", "remote_write", "db_write", "canonical_truth_write",
              "published_registry", "m202_absorbed_into_runtime", "model_or_council_vote_as_source"):
        assert rl[k] is False
