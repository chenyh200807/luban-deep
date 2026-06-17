"""M4 — published-candidate quality audit invariants.

Regenerates the M4 audit into a temp dir from the M3 packets + 2026 textbook, then asserts
the verify-on-write recheck + published-gate discipline. Skips if upstream M3 artifacts /
2026 textbook are absent (CI without the external corpus)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_luban_case_rubric_quality_m4 import build_m4, _recheck_source_ref, M3_DIR
from scripts.run_luban_case_rubric_structuring_m3 import _load_textbook, _norm, BOOK_DIR

pytestmark = pytest.mark.skipif(
    not (M3_DIR / "audit_packets_structured").exists() or not BOOK_DIR.exists(),
    reason="M3 packets or 2026 textbook corpus not available",
)


@pytest.fixture(scope="module")
def m4(tmp_path_factory):
    out = tmp_path_factory.mktemp("m4")
    return build_m4(out), out


def test_no_formal_registry_emitted(m4):
    r, out = m4
    assert r["sim"]["registry_emitted"] is False
    assert not (out / "registry_v1.json").exists()
    assert not (out / "question_grading_registry.json").exists()
    assert (out / "registry_v1_draft_simulation.json").exists()


def test_verified_source_recheck_requires_verbatim_content_markdown(m4):
    r, _ = m4
    tb = {cid: md for cid, _n, md in _load_textbook() if cid}
    # a fabricated chunk_id must fail recheck
    ok, reason = _recheck_source_ref({"source_type": "textbook", "chunk_id": "NOT_A_REAL_CHUNK", "textbook_quote": "x"}, tb)
    assert ok is False and reason == "chunk_id_not_in_2026_textbook"
    # a non-verbatim quote against a real chunk must fail
    real_cid = next(iter(tb))
    ok2, reason2 = _recheck_source_ref(
        {"source_type": "textbook", "chunk_id": real_cid, "textbook_quote": "这是一段绝不可能逐字出现的杜撰文本zzz"}, tb)
    assert ok2 is False and reason2 == "quote_not_verbatim_in_content_markdown"


def test_exam_explanation_source_type_cannot_pass_recheck(m4):
    r, _ = m4
    tb = {cid: md for cid, _n, md in _load_textbook() if cid}
    ok, reason = _recheck_source_ref(
        {"source_type": "official_answer", "chunk_id": "whatever", "textbook_quote": "whatever"}, tb)
    assert ok is False and reason == "not_textbook_source_type"


def test_calculation_without_spec_not_published(m4):
    r, _ = m4
    for q in r["quality"]:
        if "calculation_without_spec" in q["blockers"]:
            assert q["can_enter_registry_published"] is False


def test_list_rule_without_denominator_not_published(m4):
    r, _ = m4
    for q in r["quality"]:
        if any(b.startswith("list_rule_without_denominator") for b in q["blockers"]):
            assert q["can_enter_registry_published"] is False


def test_insufficient_or_high_missing_not_published(m4):
    r, _ = m4
    for q in r["quality"]:
        if q["missing_point_risk"] == "high":
            assert q["can_enter_registry_published"] is False
        if any(b.startswith("insufficient_verified_source_coverage") for b in q["blockers"]):
            assert q["can_enter_registry_published"] is False


def test_published_candidate_requires_surviving_verified_anchor(m4):
    r, _ = m4
    for q in r["quality"]:
        if q["can_enter_registry_published"]:
            assert q["source_ref_integrity"] == "pass"
            assert q["policy_completeness"] == "pass"


def test_jury_packets_have_no_fabricated_votes(m4):
    r, out = m4
    pkts = list((out / "jury_review_packets").glob("*.json"))
    assert pkts
    for f in pkts:
        d = json.loads(f.read_text("utf-8"))
        assert d["votes"] == []
        assert d["votes_fabricated"] is False
