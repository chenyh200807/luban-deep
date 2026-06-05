"""Integration guard for the M12A EvidenceCompiler attack discipline.

calculation / logic specs must survive a false-positive attack before they auto;
list_rule must be full coverage (denominator == len(item_set), coverage == 1.0);
question_stem_fact must never claim textbook authority and never production-auto.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_luban_production_authority_partition_m12a as m12a

pytestmark = pytest.mark.skipif(
    not (m12a.M10 / "machine_checkable_case_specs_m10.jsonl").exists(),
    reason="M10 specs absent",
)


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("m12a_attacks")
    m12a.run_m12a(out_dir=d)
    return d


def test_machine_specs_pass_false_positive_attack(out):
    rows = _jsonl(out / "machine_spec_evidence_m12a.jsonl")
    assert rows
    for r in rows:
        attack = r["spec_attack"]
        assert attack["exact_hit_accepted"] is True
        assert attack["false_positive"] == 0
        assert attack["passes_attack"] is True
        # off-by-one / contradiction must be rejected
        v = attack["vectors"]
        assert v.get("contradiction") is False
        if "numeric_off_by_one" in v:
            assert v["numeric_off_by_one"] is False
        # only specs that pass the attack become auto-eligible
        assert r["production_gate_status"] == "beta_shadow_auto"


def test_list_rule_full_coverage_only(out):
    rows = _jsonl(out / "list_rule_full_coverage_evidence_m12a.jsonl")
    assert rows
    for r in rows:
        if r["production_gate_status"] == "beta_shadow_auto":
            assert r["full_coverage"] is True
            assert r["spec_attack"]["vectors"]["partial"] is False
            assert r["spec_attack"]["vectors"]["denominator_mismatch"] is False


def test_no_list_rule_partial_anchor_is_auto(out):
    rows = _jsonl(out / "list_rule_full_coverage_evidence_m12a.jsonl")
    partial_auto = [r for r in rows
                    if not r.get("full_coverage") and r["production_gate_status"] == "beta_shadow_auto"]
    assert partial_auto == []


def test_question_stem_fact_never_textbook_and_never_production_auto(out):
    rows = _jsonl(out / "question_stem_fact_evidence_m12a.jsonl")
    assert rows
    for r in rows:
        assert r["source_is_textbook"] is False
        assert r["source_is_question_stem"] is True
        assert r["evidence_kind"] == "question_stem_span"
        assert r["production_gate_status"] == "shadow_only"   # never production-auto on its own
        # pending verification must be honestly recorded, not faked as verified
        if r["evidence_span"] is None:
            assert r["stem_span_verification"] == "pending_full_case_event_text"


def test_external_and_review_points_are_never_auto(out):
    for name in ("external_source_work_orders_m12a.jsonl", "review_only_packets_m12a.jsonl"):
        for r in _jsonl(out / name):
            assert r["auto_cert_policy"] == "no_auto"
            assert r["production_gate_status"] != "beta_shadow_auto"
