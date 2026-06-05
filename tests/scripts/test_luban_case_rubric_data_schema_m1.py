"""Tests for the case-rubric audit-packet schema v0 (M1) verify-on-write gate."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.luban_case_rubric_schema import (
    is_valid_audit_packet,
    validate_audit_packet,
    verify_textbook_anchor,
)

PACKETS = Path("artifacts/luban_grading_artifacts/case_rubric_data_schema_m1_20260604")


def _published():
    return json.loads((PACKETS / "sample_audit_packet_published.json").read_text("utf-8"))


def _draft():
    return json.loads((PACKETS / "sample_audit_packet_draft_or_blocked.json").read_text("utf-8"))


def test_published_sample_has_verified_textbook_anchor_and_validates():
    p = _published()
    assert p["artifact_status"] == "published"
    assert is_valid_audit_packet(p), validate_audit_packet(p)
    # at least one auto-certifiable point, each backed by a verified textbook anchor
    autos = [sp for sp in p["scoring_points"] if sp["auto_certifiable"]]
    assert autos
    for sp in autos:
        assert any(verify_textbook_anchor(r) for r in sp["source_refs"])


def test_draft_sample_has_no_auto_certifiable_point():
    d = _draft()
    assert d["artifact_status"] in {"draft", "blocked"}
    assert is_valid_audit_packet(d), validate_audit_packet(d)
    assert all(not sp["auto_certifiable"] for sp in d["scoring_points"])


def test_official_answer_only_is_not_verified():
    anchor = {"source_type": "official_answer", "chunk_id": "", "textbook_quote": "应组织专家论证", "verified": True}
    assert verify_textbook_anchor(anchor) is False


def test_missing_chunk_or_quote_is_not_verified():
    assert verify_textbook_anchor({"source_type": "textbook", "chunk_id": "", "textbook_quote": "x", "verified": True, "match_method": "verbatim"}) is False
    assert verify_textbook_anchor({"source_type": "textbook", "chunk_id": "1A4_001", "textbook_quote": "", "verified": True, "match_method": "verbatim"}) is False


def test_semantic_match_is_not_verified():
    # only verbatim is accepted; near/semantic never升 verified.
    anchor = {"source_type": "textbook", "chunk_id": "1A4_001", "textbook_quote": "近义", "verified": True, "match_method": "semantic"}
    assert verify_textbook_anchor(anchor) is False


def test_auto_without_verified_textbook_is_a_violation():
    bad = {
        "schema_version": "luban_case_rubric_audit_packet.v0",
        "question_id": "Q-BAD", "question_text": "x", "official_answer": "x", "node_code": "1A4",
        "source_exam": "test", "rubric_candidates": [], "textbook_anchor_evidence": [],
        "teacher_review_status": "reviewed", "artifact_status": "published",
        "scoring_points": [{"point_id": "P1", "policy_type": "exact_required", "max_score": 2,
                            "required_terms": ["专项施工方案"],
                            "source_refs": [{"source_type": "official_answer", "chunk_id": "", "textbook_quote": "x", "verified": True}],
                            "auto_certifiable": True}],
        "quality_gate": {}, "provenance": {},
    }
    violations = validate_audit_packet(bad)
    assert any(v.startswith("auto_without_verified_textbook") for v in violations)


def test_schema_fields_present_in_samples():
    for packet in (_published(), _draft()):
        for f in ("question_id", "official_answer", "node_code", "rubric_candidates",
                  "textbook_anchor_evidence", "teacher_review_status", "artifact_status",
                  "scoring_points", "quality_gate", "provenance"):
            assert f in packet
