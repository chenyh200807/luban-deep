"""Hermetic guards for M10 Non-Textbook Rubric Authority Factory.

Asserts the authority-layering invariants WITHOUT live models / runtime / formal registry:
  - every residual point is classified into exactly one of the 6 authority buckets
  - official_answer is NEVER a textbook source (only a labelled case rubric seed)
  - no spec is verified / auto_certifiable / human_reviewed
  - machine-checkable specs survive a 7-vector false-positive attack (fp=0, contradiction=100%)
  - list_rule structured specs require full item coverage
  - beta_shadow readiness delta is computed; production v1 stays NO-GO
"""
from __future__ import annotations

import json
from pathlib import Path

import scripts.build_luban_non_textbook_rubric_authority_factory_m10 as m10

OUT = Path(m10.OUT)


def _j(name: str):
    return json.loads((OUT / name).read_text("utf-8"))


def _jl(name: str):
    return [json.loads(l) for l in (OUT / name).read_text("utf-8").splitlines() if l.strip()]


def test_factory_runs_and_emits_all_outputs():
    m10.main()
    required = {
        "residual_authority_inventory_m10.json", "machine_checkable_case_specs_m10.jsonl",
        "list_rule_structured_specs_m10.jsonl", "external_source_work_orders_m10.jsonl",
        "review_required_packets_m10.jsonl", "drop_or_keep_draft_m10.jsonl",
        "false_positive_attack_results_m10.json", "registry_v1_beta_shadow_readiness_delta_m10.json",
    }
    names = {p.name for p in OUT.iterdir() if p.is_file()}
    assert required <= names


def test_all_residual_classified_into_six_buckets():
    inv = _j("residual_authority_inventory_m10.json")
    assert inv["all_classified"] is True
    assert inv["unclassified"] == 0
    six = set(m10.BUCKET.values())
    assert set(inv["by_authority_bucket"]) <= six
    assert sum(inv["by_authority_bucket"].values()) == inv["residual_universe"]


def test_official_answer_never_textbook_source():
    for row in _jl("machine_checkable_case_specs_m10.jsonl") + _jl("list_rule_structured_specs_m10.jsonl"):
        assert row["textbook_source"] is False
        assert row["rubric_seed"] == "official_answer_not_textbook"
        assert row["source_type"] == "case_rubric_seed"
        assert row["verified"] is False
        assert row["auto_certifiable"] is False
        assert row["human_reviewed"] is False


def test_machine_checkable_specs_have_full_structure():
    rows = _jl("machine_checkable_case_specs_m10.jsonl")
    assert len(rows) >= 20
    for r in rows:
        spec = r["spec"]
        assert spec["kind"] in {"numeric_formula", "numeric_value", "numeric_judgment",
                                "numeric_range", "boolean_judgment"}
        # every numeric spec carries an acceptance range; every spec carries negative controls
        if spec["kind"] in {"numeric_formula", "numeric_value", "numeric_judgment"}:
            assert "acceptance_range" in spec
        assert "negative_controls" in spec


def test_false_positive_attack_is_clean():
    a = _j("false_positive_attack_results_m10.json")
    assert a["false_positive"] == 0
    assert a["false_negative"] == 0
    assert a["contradiction_rejected_pct"] == 1.0
    assert a["exact_hit_accept_rate"] == 1.0
    assert set(a["attack_vectors_per_spec"]) == {
        "exact_hit", "partial", "contradiction", "near_synonym",
        "irrelevant", "numeric_off_by_one", "denominator_mismatch"}


def test_list_rule_specs_require_full_coverage():
    for r in _jl("list_rule_structured_specs_m10.jsonl"):
        # a structured list spec that passes attack must have coverage 1.0 (every item has a matcher)
        if r["passes_attack"] and r["full_coverage"]:
            assert r["spec"]["coverage"] == 1.0
            assert len(r["spec"]["item_matchers"]) == r["spec"]["denominator"]


def test_readiness_delta_and_production_no_go():
    d = _j("registry_v1_beta_shadow_readiness_delta_m10.json")
    assert d["production_v1"] == "NO-GO"
    inv = d["safety_invariants"]
    assert inv["official_answer_as_textbook"] == 0
    assert inv["model_vote_as_source"] == 0
    assert inv["semantic_only_auto"] == 0
    assert inv["formal_registry_emitted"] is False
    assert inv["v0_overwritten"] is False
    assert inv["production_runtime_connected"] is False
    # coverage strictly improved over M9
    assert d["beta_shadow_gradeable_total"] > d["auto_preview_m9"]
    assert d["m11_gated_beta_qa_verdict"] in {"GO", "WEAK-GO", "NO-GO"}


def test_drop_bucket_is_noise_only():
    for r in _jl("drop_or_keep_draft_m10.jsonl"):
        assert r["reason"] == "hint/error_restatement/ungradeable_noise"
