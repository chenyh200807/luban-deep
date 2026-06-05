"""Hermetic guards for M7 council-hardened Registry v1 candidate compiler.

Proves the compiler hard gates WITHOUT live LLM / production runtime / DB:
  - list_rule partial anchor can NEVER auto-certify
  - approve_with_repaired_anchor must pass independent exact-match re-verification
  - split/rewrite/drop/require_external/keep_draft are all blocked from auto
  - ai_expert_council_final never substitutes for textbook source authority
  - the candidate preview does NOT unlock auto-certification at the runtime gate
  - v0 is not overwritten / deleted / superseded; no formal registry emitted
"""
from __future__ import annotations

import json
from pathlib import Path

import scripts.build_luban_registry_v1_council_hardened_candidate_m7 as m7

OUT = Path(m7.OUT)


def _j(name: str):
    return json.loads((OUT / name).read_text("utf-8"))


def test_all_25_m5d_points_read_and_classified():
    audit = _j("m5d_council_input_audit.json")
    assert audit["total_points_read"] == 25
    assert audit["all_points_classified"] is True
    assert audit["human_reviewed_any"] is False
    assert audit["final_authority_seen"] == ["ai_expert_council_final"]


def test_list_rule_partial_anchor_never_auto():
    cov = _j("list_rule_coverage_audit.json")
    assert cov["list_rule_point_count"] >= 1
    assert cov["auto_eligible_by_full_coverage_count"] == 0
    assert cov["partial_coverage_auto_blocked"] is True
    for p in cov["points"]:
        if p["coverage"] < 1.0:
            assert p["auto_eligible_by_coverage"] is False


def test_approve_points_require_reverification():
    rv = _j("repaired_anchor_reverification.json")
    assert rv["approve_points_total"] == 6
    # every compiled-auto point must have passed an independent verbatim recheck
    for p in rv["points"]:
        if p["compiled_auto_certifiable"]:
            assert p["reverification_passed"] is True
            assert p["verified_textbook_anchor_count"] >= 1
            assert all(a["verbatim_recheck_hit"] for a in p["reverified_anchors"])


def test_non_approve_actions_all_blocked_from_auto():
    blocked = _j("blocked_by_council_action.json")
    actions = set(blocked["by_action"])
    assert actions <= {"split_point", "rewrite_point", "require_external_source", "drop_point", "keep_draft"}
    # nothing auto in the artifacts carries a non-approve action
    arts = [json.loads(l) for l in (OUT / "hardened_candidate_artifacts_preview.jsonl").read_text("utf-8").splitlines() if l.strip()]
    for a in arts:
        for s in a["scoring_points"]:
            if s["auto_certifiable"]:
                assert s["council_action"] == "approve_with_repaired_anchor"
                assert s["source_authority"] == "textbook_exact_match"


def test_council_final_does_not_substitute_source_authority():
    arts = [json.loads(l) for l in (OUT / "hardened_candidate_artifacts_preview.jsonl").read_text("utf-8").splitlines() if l.strip()]
    for a in arts:
        assert a["final_authority"] == "ai_expert_council_final"
        assert a["human_reviewed"] is False
        for s in a["scoring_points"]:
            assert s["source_authority"] in {"textbook_exact_match", "source_gap"}
            # a council 'approve' alone (no textbook exact match) can never be auto
            if s["source_authority"] == "source_gap":
                assert s["auto_certifiable"] is False


def test_runtime_gate_dry_run_unlocks_nothing():
    rt = _j("runtime_gate_dry_run_results.json")
    assert rt["production_runtime_connected"] is False
    assert rt["formal_runtime_connected"] is False
    assert rt["summary"]["artifact_auto_certification_allowed_count"] == 0
    assert rt["summary"]["point_auto_certified_after_gate_count"] == 0
    # candidate preview status is never 'published'
    for q in rt["questions"]:
        assert q["artifact_status"] != "published"


def test_candidate_preview_counts_and_no_formal_registry():
    preview = _j("hardened_candidate_registry_preview.json")
    assert preview["formal_registry_emitted"] is False
    assert preview["production_runtime_connected"] is False
    assert preview["question_count"] == 9
    assert preview["point_count"] == 25
    assert preview["auto_certifiable_point_count"] == 6
    names = {p.name for p in OUT.iterdir() if p.is_file()}
    forbidden = {"registry_v1.json", "question_grading_registry_v1.json", "question_grading_artifacts_v1.jsonl"}
    assert not (forbidden & names)


def test_v0_integrity_preserved():
    v0 = _j("v0_integrity_audit.json")
    assert v0["v0_overwritten_by_m7"] is False
    assert v0["v0_deleted_by_m7"] is False
    assert v0["v0_superseded"] is False
    assert v0["v0_exists"] is True


def test_required_output_files_present():
    required = {
        "compiler_hard_gate_rules.json", "m5d_council_input_audit.json",
        "repaired_anchor_reverification.json", "list_rule_coverage_audit.json",
        "hardened_candidate_registry_preview.json", "hardened_candidate_artifacts_preview.jsonl",
        "blocked_by_council_action.json", "runtime_gate_dry_run_results.json",
        "v0_integrity_audit.json", "FINDING_registry_v1_council_hardened_candidate_m7_20260604.md",
    }
    names = {p.name for p in OUT.iterdir() if p.is_file()}
    assert required <= names
