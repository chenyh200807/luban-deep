"""M3.5 rubric normalization invariants. Regenerates into tmp from M5 blocked points.
Skips if M5 authority absent."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_luban_blocked_point_rubric_normalization_m35 import (
    M5_DIR,
    M7_COUNCIL_DIR,
    M7_REPAIR_DIR,
    REQUIRED_OUTPUTS,
    build_m35,
)

pytestmark = pytest.mark.skipif(
    not (M5_DIR / "authority_adjudication.json").exists(), reason="M5 authority absent")


@pytest.fixture(scope="module")
def m35(tmp_path_factory):
    out = tmp_path_factory.mktemp("m35")
    return build_m35(out), out


def _jsonl(p):
    return [json.loads(x) for x in Path(p).read_text("utf-8").splitlines() if x.strip()]


def test_all_blocked_points_have_final_action(m35):
    r, out = m35
    backlog = json.loads((out / "unified_blocked_point_backlog.json").read_text("utf-8"))
    assert backlog["input_counts"]["m7_source_repair_blocked_points"] == 125
    assert backlog["input_counts"]["m7_council_blocked_points"] == 19
    assert backlog["priority_counts"]["P0"] == 19
    assert backlog["priority_counts"]["P1"] > 0
    assert backlog["deduped_count"] <= 144
    inv = json.loads((out / "blocked_point_normalization_inventory.json").read_text("utf-8"))
    assert all(p.get("final_action") for p in inv["points"])  # none unclassified
    assert sum(r["actions"].values()) == inv["count"]
    assert inv["count"] == backlog["deduped_count"]


def test_required_outputs_exist(m35):
    _r, out = m35
    for name in REQUIRED_OUTPUTS:
        assert (out / name).exists(), name


def test_no_official_answer_upgraded_to_textbook(m35):
    r, out = m35
    for c in _jsonl(out / "normalized_rubric_candidates.jsonl"):
        assert c["source_status"] == "candidate_unverified"  # never verified_textbook
        assert c["verified"] is False
        assert c["structure_from"].endswith("not_source")


def test_no_normalized_point_is_auto_certifiable(m35):
    r, out = m35
    for c in _jsonl(out / "normalized_rubric_candidates.jsonl"):
        assert c["runtime_auto_certifiable"] is False
        assert c["human_reviewed"] is False
    for s in _jsonl(out / "split_point_proposals.jsonl"):
        assert s["runtime_auto_certifiable"] is False
        assert s["verified"] is False


def test_required_terms_coverage_improved_for_exact_required(m35):
    r, _ = m35
    cov = r["coverage"]
    # normalization recovered required_terms for exact_required (was 0 pre-normalization)
    assert cov["exact_required_with_required_terms"] > 0


def test_list_rule_has_denominator_and_item_set(m35):
    r, out = m35
    for c in _jsonl(out / "normalized_rubric_candidates.jsonl"):
        if c["policy_type"] == "list_rule" and c["list_spec"]:
            assert c["list_spec"]["denominator"] == len(c["list_spec"]["item_set"])
            assert c["list_spec"]["item_set"]
            assert c["m7_hard_gate"]["list_rule_coverage_ready"] is True


def test_calculation_ready_points_have_machine_checkable_spec(m35):
    r, out = m35
    for c in _jsonl(out / "normalized_rubric_candidates.jsonl"):
        if c["policy_type"] == "calculation" and c["final_action"] == "normalized_ready_for_source_hunt":
            assert c["calculation_spec"] and c["calculation_spec"]["machine_checkable"]


def test_semantic_and_figure_kept_draft_not_ready(m35):
    r, out = m35
    for c in _jsonl(out / "normalized_rubric_candidates.jsonl"):
        if c["policy_type"] in ("semantic_allowed", "figure_label"):
            assert c["final_action"] != "normalized_ready_for_source_hunt"


def test_every_point_has_source_hunt_query_terms_or_external(m35):
    r, out = m35
    qt = {(q["question_id"], q["point_id"]) for q in _jsonl(out / "source_hunt_query_terms.jsonl")}
    inv = json.loads((out / "blocked_point_normalization_inventory.json").read_text("utf-8"))
    for p in inv["points"]:
        if p["final_action"] in ("normalized_ready_for_source_hunt", "split_into_multiple_points"):
            assert (p["question_id"], p["point_id"]) in qt  # ready/split points carry search terms


def test_m7_rerun_readiness_verdict(m35):
    r, _ = m35
    rd = r["readiness"]
    assert rd["verdict"] in ("GO", "WEAK-GO", "NO-GO")
    if rd["normalized_ready_for_source_hunt"] > 0:
        assert rd["m7_rerun_ready"] is True


def test_p0_council_blocked_points_are_all_accounted_for(m35):
    _r, out = m35
    backlog = json.loads((out / "unified_blocked_point_backlog.json").read_text("utf-8"))
    p0 = [p for p in backlog["points"] if p["priority"] == "P0"]
    assert len(p0) == 19
    assert {p["council_action"] for p in p0} <= {
        "split_point",
        "require_external_source",
        "rewrite_point",
        "drop_point",
        "keep_draft",
    }
    assert all(p["final_action"] for p in p0)


def test_compiler_hard_gate_report_blocks_unsafe_actions(m35):
    _r, out = m35
    report = json.loads((out / "compiler_hard_gate_compatibility_report.json").read_text("utf-8"))
    assert report["m7_compatible"] is True
    assert report["normalized_points_auto_certifiable"] == 0
    assert report["official_answer_upgraded_to_textbook_source"] == 0
    assert report["human_reviewed_true_count"] == 0
    assert report["list_rule_requires_coverage_1_0"] is True


def test_no_formal_registry_emitted(m35):
    r, out = m35
    manifest = json.loads((out / "normalization_workflow_manifest.json").read_text("utf-8"))
    assert manifest["formal_registry_emitted"] is False
    assert manifest["official_answer_is_source_authority"] is False
    assert not (out / "registry_v1.json").exists()
