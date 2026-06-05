"""Hermetic guards for M5D AI Expert Council Source Court.

Asserts the honesty + hard-gate invariants WITHOUT calling any model or touching runtime:
  - no fabricated votes / no human authority / no formal registry
  - source authority gate dominates model votes (a model 'accept' cannot publish a source_gap)
  - the engine's pure functions behave deterministically
"""
from __future__ import annotations

import json
from pathlib import Path

import scripts.build_luban_case_rubric_source_court_m5d as sc

OUT = Path(sc.OUT)


def test_meta_and_error_restatement_detector():
    assert sc._is_meta_or_error_restatement("( 注：只需写出题目上缺少的即可)")
    assert sc._is_meta_or_error_restatement("不妥之处一：材料加工场地布置在场外")
    assert not sc._is_meta_or_error_restatement("施工现场宜考虑设置两个以上大门")


def test_source_verdict_partial_list_is_not_exact_match():
    tb_norm = ["编制说明在此出现"]  # only one of several terms present
    point = {
        "policy_type": "list_rule",
        "label": "施工总进度计划的内容包括：编制说明，资源",
        "list_spec": {"denominator": 6, "terms": ["编制说明", "施工总进度计划表", "分期", "分批", "实施工程的开", "资源"]},
        "source_refs": [{"source_type": "textbook", "chunk_id": "c1", "textbook_quote": "编制说明", "verified": True, "match_method": "verbatim"}],
    }
    v = sc._source_verdict(point, tb_norm)
    assert v["source_status"] == "textbook_partial_coverage"
    assert v["coverage"] < 1.0


def test_aggregator_source_gate_overrides_model_accepts():
    # Even with 4/4 accepts, a source_gap point can never be published.
    src = {"source_status": "source_gap", "verified_textbook_anchors": 0, "coverage": 0.0, "list": None}
    votes = {"a": "accept", "b": "accept", "c": "accept", "d": "accept"}
    d = sc._council_decision(src, votes, "exact_required")
    assert d["council_action"] == "require_external_source"
    assert d["point_publishable"] is False


def test_aggregator_partial_list_always_splits():
    src = {"source_status": "textbook_partial_coverage", "coverage": 0.16,
           "list": {"denominator": 6, "verified_term_hits": 1}, "verified_textbook_anchors": 1}
    d = sc._council_decision(src, {"a": "accept", "b": "accept", "c": "accept", "d": "accept"}, "list_rule")
    assert d["council_action"] == "split_point"
    assert d["point_publishable"] is False


def test_exact_match_needs_three_accepts_to_approve():
    src = {"source_status": "textbook_exact_match", "verified_textbook_anchors": 1, "coverage": 1.0, "list": None}
    approve = sc._council_decision(src, {"a": "accept", "b": "accept", "c": "accept", "d": "revise"}, "exact_required")
    draft = sc._council_decision(src, {"a": "accept", "b": "accept", "c": "reject", "d": "revise"}, "exact_required")
    assert approve["council_action"] == "approve_with_repaired_anchor" and approve["point_publishable"]
    assert draft["council_action"] == "keep_draft" and not draft["point_publishable"]


def test_opus_votes_are_genuine_not_fabricated_and_cover_25_points():
    data = json.loads(sc.OPUS_VOTES.read_text("utf-8"))
    assert data["votes_fabricated"] is False
    assert data["model"] == "opus48"
    assert data["reviewer_type"] == "ai_expert_council_member"
    assert len(data["votes"]) == 25
    for v in data["votes"]:
        assert v["judge_action"] in {"accept", "split", "rewrite", "drop", "require_external_source"}
        assert v["rationale"].strip()


def test_emitted_results_have_honesty_fields_and_zero_publish():
    results = json.loads((OUT / "source_anchor_dispute_council_results.json").read_text("utf-8"))
    assert len(results) == 9
    for r in results:
        assert r["final_authority"] == "ai_expert_council_final"
        assert r["source_authority"] == "textbook_exact_match"
        assert r["human_reviewed"] is False
        assert r["votes_fabricated"] is False
        # any unresolved source dispute => not publish
        if r["council_final_status"] == "council_approved":
            assert all(p["council_action"] == "approve_with_repaired_anchor" for p in r["point_decisions"])
    summary = json.loads((OUT / "source_court_summary_m5d.json").read_text("utf-8"))
    assert summary["new_live_api_calls"] == 0
    assert summary["reused_live_jury_votes"] == 33
    assert summary["formal_registry_emitted"] is False
    assert summary["council_approved"] == 0


def test_no_sanctioned_cache_and_no_registry_files_in_output():
    names = {p.name for p in OUT.rglob("*")}
    assert not any("registry" in n and n.endswith(".json") and "policy" not in n for n in names)
    blob = json.dumps([json.loads(p.read_text("utf-8")) for p in OUT.glob("*.json")], ensure_ascii=False)
    assert "sanctioned_cache_used\": true" not in blob.lower().replace(" ", "")
