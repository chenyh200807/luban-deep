"""Tests for Registry v1 M3 structuring — textbook-only verify-on-write, no fabrication."""
from __future__ import annotations

import json

import pytest

from scripts import run_luban_case_rubric_structuring_m3 as m3
from scripts.luban_case_rubric_schema import validate_audit_packet


@pytest.fixture(scope="module")
def m3_run():
    if not m3.BOOK_DIR.exists():
        pytest.skip("2026 textbook corpus not available in this environment")
    m3.main()
    return m3.OUT_DIR


def _load(out, name):
    return json.loads((out / name).read_text("utf-8"))


def test_official_answer_only_is_weak_not_textbook_verified(m3_run):
    rows = _load(m3_run, "textbook_verify_on_write.json")
    for r in rows:
        if r["anchor_status"] != "verified":
            # non-verified points must not carry a textbook source_ref
            assert r["selected_source_ref"] is None


def test_textbook_verified_requires_chunk_quote_and_match(m3_run):
    rows = _load(m3_run, "textbook_verify_on_write.json")
    verified = [r for r in rows if r["anchor_status"] == "verified"]
    for r in verified:
        sr = r["selected_source_ref"]
        assert sr and sr["source_type"] == "textbook"
        assert sr["chunk_id"] and sr["textbook_quote"] and sr["verified"] is True
        assert r["auto_certifiable"] is True


def test_node_code_unresolved_not_hard_filled(m3_run):
    res = _load(m3_run, "node_code_resolution.json")
    for r in res:
        if r["resolution_source"] == "unresolved":
            assert r["resolved_node_code"] == ""
            assert r["confidence"] == 0.0


def test_generated_audit_packets_pass_a1_validator(m3_run):
    pkts = list((m3_run / "audit_packets_structured").glob("*.json"))
    assert pkts
    for f in pkts:
        packet = json.loads(f.read_text("utf-8"))
        assert validate_audit_packet(packet) == []
        for sp in packet["scoring_points"]:
            if sp["auto_certifiable"]:
                tb = [r for r in sp["source_refs"] if r.get("source_type") == "textbook" and r.get("verified")]
                assert tb and tb[0]["match_method"] == "verbatim"
            else:
                # weak/official-answer-only points are never auto-certifiable
                assert sp["source_status"] == "missing_or_weak"


def test_no_formal_registry_emitted(m3_run):
    impact = _load(m3_run, "registry_impact_simulation_m3.json")
    assert impact["registry_emitted"] is False
    assert not (m3_run / "question_grading_registry.json").exists()
    assert not (m3_run / "question_grading_artifacts.jsonl").exists()


def test_llm_jury_unavailable_not_fabricated(m3_run):
    ja = _load(m3_run, "jury_availability.json")
    assert ja["votes_fabricated"] is False
    assert ja["reviewer_type"] == "llm_jury"
    assert ja["available_models"] == []


def test_no_mcq_in_structuring(m3_run):
    # candidates come from case_study only; verify no choice/选择 leaked into scoring points
    pts = _load(m3_run, "scoring_point_candidates.json")
    blob = json.dumps(pts, ensure_ascii=False)
    assert "single_choice" not in blob and "multiple_choice" not in blob
