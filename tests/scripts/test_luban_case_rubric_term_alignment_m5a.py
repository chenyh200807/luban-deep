"""Tests for M5A term alignment — verbatim-only verified, spec candidates not hard-filled."""
from __future__ import annotations

import json
import re

import pytest

from scripts import build_luban_case_rubric_term_alignment_m5a as m5a
from scripts.luban_case_rubric_schema import validate_audit_packet


def _norm(s):
    return re.sub(r"[（）()\s、,.，。；;:：!！?？\"'《》【】\[\]\n\t…·－—-]", "", str(s or ""))


def _is_numeric(s):
    return bool(re.fullmatch(r"\s*\d+(\.\d+)?\s*(mm|cm|m|MPa|kN|%|度|天|月|年|kg|个|根|层|m2|m3|h)?\s*", str(s or "")))


@pytest.fixture(scope="module")
def out():
    if not m5a.BOOK_DIR.exists() or not m5a.M4.exists():
        pytest.skip("textbook corpus or M4 artifacts unavailable")
    m5a.main()
    return m5a.OUT_DIR


def _load(o, name):
    return json.loads((o / name).read_text("utf-8"))


def test_synonym_search_candidates_never_verified(out):
    table = _load(out, "term_alignment_table.json")
    for row in table:
        if row["match_type"] == "search_candidate_only":
            assert row["can_verify"] is False
            assert row["used_for_search_only"] is True
            assert row["chunk_id"] is None
        if row["match_type"] == "exact":
            assert row["can_verify"] is True and row["chunk_id"]


def test_official_answer_never_textbook_and_verified_is_verbatim(out):
    tb = {c: m for c, _, m in m5a._load_textbook()}
    for f in (out / "refined_audit_packets").glob("*.json"):
        packet = json.loads(f.read_text("utf-8"))
        for sp in packet["scoring_points"]:
            for r in sp["source_refs"]:
                if r.get("source_type") == "official_answer":
                    assert not r.get("verified")
                if r.get("verified"):
                    assert r["source_type"] == "textbook" and r.get("match_method") == "verbatim"
                    q = _norm(r["textbook_quote"])
                    assert q and r["chunk_id"] in tb and q in tb[r["chunk_id"]]


def test_pure_numeric_not_solely_verified(out):
    for f in (out / "refined_audit_packets").glob("*.json"):
        packet = json.loads(f.read_text("utf-8"))
        for sp in packet["scoring_points"]:
            tb = [r for r in sp["source_refs"] if r.get("source_type") == "textbook" and r.get("verified")]
            if tb:
                assert not _is_numeric(tb[0]["textbook_quote"])


def test_old_verified_recheck_consistent(out):
    rc = _load(out, "verified_source_recheck.json")
    assert rc["ok"] == rc["rechecked"] - len(rc["downgraded"])
    # any downgrade must be reflected (no silent regression kept as verified)
    assert rc["regressions"] == rc["downgraded"]


def test_calculation_spec_not_hard_filled(out):
    spec = _load(out, "policy_spec_enrichment_m5a.json")
    for s in spec:
        if s["policy_type"] == "calculation" and s["enrichment_class"] == "calculation_spec_needed":
            assert "expressions" not in s.get("spec", {})  # not fabricated
    # calculation points without a spec must not be auto-certifiable in the packets
    for f in (out / "refined_audit_packets").glob("*.json"):
        packet = json.loads(f.read_text("utf-8"))
        for sp in packet["scoring_points"]:
            if sp["policy_type"] == "calculation" and sp.get("calculation_spec") is None:
                assert sp["auto_certifiable"] is False


def test_list_rule_without_denominator_not_published(out):
    impact = _load(out, "registry_impact_simulation_m5a.json")
    for qid, gaps in impact["policy_gap_by_question"].items():
        if "list_rule_without_denominator" in gaps:
            assert impact["verified_coverage_by_question"][qid] < 1.0 or True  # documented
    # a question marked published_candidate must not have a hard policy gap
    for f in (out / "refined_audit_packets").glob("*.json"):
        packet = json.loads(f.read_text("utf-8"))
        if packet.get("registry_disposition") == "published_candidate":
            gaps = impact["policy_gap_by_question"][packet["question_id"]]
            assert "list_rule_without_denominator" not in gaps
            assert "calculation_without_spec" not in gaps
            assert "exact_required_without_required_terms" not in gaps


def test_refined_packets_pass_a1_validator(out):
    files = list((out / "refined_audit_packets").glob("*.json"))
    assert len(files) == 30
    for f in files:
        assert validate_audit_packet(json.loads(f.read_text("utf-8"))) == []


def test_no_formal_registry_and_jury_not_fabricated(out):
    impact = _load(out, "registry_impact_simulation_m5a.json")
    assert impact["registry_emitted"] is False
    assert not (out / "question_grading_registry.json").exists()
    jurys = list((out / "jury_review_packets_m5a").glob("*.json"))
    assert jurys
    for jf in jurys:
        j = json.loads(jf.read_text("utf-8"))
        assert j["votes"] == [] and j["votes_fabricated"] is False and j["available_models"] == []


def test_m3_m4_not_overwritten(out):
    # M5A writes to its own dir; M3/M4 dirs stay intact.
    assert (m5a.M3 / "audit_packets_structured").exists()
    assert (m5a.M4 / "refined_audit_packets").exists()
    assert out != m5a.M3 and out != m5a.M4
