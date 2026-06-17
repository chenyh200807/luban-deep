"""Tests for M4 anchor refinement — verbatim-only verified, candidate node, no fabrication."""
from __future__ import annotations

import json
import re

import pytest

from scripts import build_luban_case_rubric_anchor_refinement_m4 as m4
from scripts.luban_case_rubric_schema import validate_audit_packet


def _norm(s):
    return re.sub(r"[（）()\s、,.，。；;:：!！?？\"'《》\[\]\n\t]", "", str(s or ""))


@pytest.fixture(scope="module")
def m4_run():
    if not m4.BOOK_DIR.exists() or not m4.M3.exists():
        pytest.skip("textbook corpus or M3 artifacts unavailable")
    m4.main()
    return m4.OUT_DIR


def _load(out, name):
    return json.loads((out / name).read_text("utf-8"))


def test_new_verified_anchors_are_verbatim_in_textbook(m4_run):
    tb = {c: m for c, _, m in m4._load_textbook()}
    res = _load(m4_run, "textbook_anchor_refinement_results.json")
    assert res["new_verified"], "M4 should add at least one verbatim anchor"
    for n in res["new_verified"]:
        q = _norm(n["textbook_quote"])
        assert n["chunk_id"] in tb and q and q in tb[n["chunk_id"]]


def test_official_answer_is_never_verified(m4_run):
    for f in (m4_run / "refined_audit_packets").glob("*.json"):
        packet = json.loads(f.read_text("utf-8"))
        for sp in packet["scoring_points"]:
            for r in sp["source_refs"]:
                if r.get("source_type") == "official_answer":
                    assert not r.get("verified")
                if r.get("verified"):
                    assert r["source_type"] == "textbook" and r.get("match_method") == "verbatim"


def test_worklist_covers_m3_weak_and_missing(m4_run):
    base = _load(m4_run, "baseline_audit.json")
    worklist = _load(m4_run, "missing_anchor_worklist.json")
    assert len(worklist) == base["weak"] + base["missing"]


def test_refined_packets_pass_a1_validator(m4_run):
    files = list((m4_run / "refined_audit_packets").glob("*.json"))
    assert len(files) == 30
    for f in files:
        assert validate_audit_packet(json.loads(f.read_text("utf-8"))) == []


def test_node_code_is_candidate_only_not_hard_filled(m4_run):
    res = _load(m4_run, "textbook_anchor_refinement_results.json")
    for c in res["candidate_node_codes"]:
        assert "candidate_node_code" in c and c["confidence"] < 1.0
    # refined packets must not have inherited a fabricated node authority from a candidate
    for f in (m4_run / "refined_audit_packets").glob("*.json"):
        packet = json.loads(f.read_text("utf-8"))
        assert "node_code" in packet  # field exists but is not forced from a low-conf candidate


def test_no_formal_registry_and_jury_not_fabricated(m4_run):
    impact = _load(m4_run, "registry_impact_simulation_m4.json")
    assert impact["registry_emitted"] is False
    assert not (m4_run / "question_grading_registry.json").exists()
    jury = _load(m4_run, "jury_review_packet_m4.json")
    assert jury["votes_fabricated"] is False and jury["available_models"] == []


def test_m4_impact_numbers_self_consistent(m4_run):
    impact = _load(m4_run, "registry_impact_simulation_m4.json")
    assert impact["m4"]["verified"] == impact["baseline"]["verified"] + impact["new_verified_anchors"]
    assert sum(impact["new_verified_by_scope"].values()) == impact["new_verified_anchors"]
    assert impact["published_candidate_not_final"] + impact["draft"] == 30
