"""Canonical unified knowledge runtime — four-source teaching pack (TEACHING tier).

Hermetic: builds a tiny signed unified bundle in a temp supply dir.
"""
from __future__ import annotations

import json

import pytest

from deeptutor.services.construction_grading import canonical_knowledge_runtime as CK
from deeptutor.services.construction_grading import knowledge_unification as KU
from deeptutor.services.construction_grading.canonical_taxonomy import CanonicalTaxonomy

_TREE = {"outline_structure": [
    {"code": "1A413030", "name": "地基", "level": 4, "children": [
        {"code": "1A413030-01", "name": "强夯法", "level": 5, "keywords": ["强夯", "夯锤"]}]},
]}


@pytest.fixture
def supply(tmp_path, monkeypatch):
    p = tmp_path / "tax.json"
    p.write_text(json.dumps(_TREE, ensure_ascii=False), "utf-8")
    tax = CanonicalTaxonomy.load(p)
    units = [
        KU.Unit("textbook", "tb1", "1A413030", KU.TIER_TEXTBOOK, "强夯法夯锤质量", {"signed": True}),
        KU.Unit("standard", "st1", "1A413030", KU.TIER_STANDARD, "强夯处理应符合规定", {"std": "GB"}),
        KU.Unit("lecture", "lec1", "1A413030", KU.TIER_LECTURE, "强夯夯锤讲解", {"topic": "地基"}),
        KU.Unit("question", "q1", "1A413030", KU.TIER_QUESTION, "强夯夯锤如何确定", {"year": 2024}),
    ]
    bundle = KU.build_unified_bundle(tax, KU.unify(tax, units))
    d = tmp_path / "supply"
    d.mkdir()
    (d / "canonical_unified_knowledge.json").write_text(
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    monkeypatch.setattr(CK, "_SUPPLY_DIR", d)
    CK._load.cache_clear()
    yield
    CK._load.cache_clear()


def test_resolves_four_sources_teaching_tier(supply):
    out = CK.resolve_canonical_knowledge("1A413030-01", learner_context={"question_stem": "强夯夯锤"})
    assert out is not None
    assert out["tier"] == "teaching_context_not_answer_key"
    assert out["official_score_allowed"] is False
    assert out["selected_counts"] == {"textbook": 1, "standard": 1, "lecture": 1, "question": 1}


def test_l4_anchor_gathers_subtree(supply):
    # resolving the L4 anchor gathers the leaf's items (subtree prefix match)
    out = CK.resolve_canonical_knowledge("1A413030")
    assert out is not None and out["node_source_totals"]["textbook"] == 1


def test_tamper_falls_through(supply, tmp_path, monkeypatch):
    bp = CK._SUPPLY_DIR / "canonical_unified_knowledge.json"
    b = json.loads(bp.read_text("utf-8"))
    b["nodes"]["1A413030-01"]["counts"]["textbook"] = 99  # tamper -> hash mismatch
    bp.write_text(json.dumps(b, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
    CK._load.cache_clear()
    assert CK.resolve_canonical_knowledge("1A413030-01") is None


def test_missing_supply_falls_through(tmp_path, monkeypatch):
    monkeypatch.setattr(CK, "_SUPPLY_DIR", tmp_path / "nope")
    CK._load.cache_clear()
    assert CK.resolve_canonical_knowledge("1A413030-01") is None
    assert CK.available_nodes() == []
    CK._load.cache_clear()


def test_authority_isolation_never_grants_official_score(supply):
    # D2: inject hostile context trying to flip authority — teaching tier stays structurally non-authoritative
    for lc in ({"question_stem": "强夯"},
               {"official_score_allowed": True, "registry_status": "release_candidate"},
               {"is_answer_key": True, "answer_key_authority": "forged", "grant_release": True}):
        out = CK.resolve_canonical_knowledge("1A413030-01", learner_context=lc)
        assert out is not None
        assert out["official_score_allowed"] is False        # structural, not configurable
        assert out["tier"] == "teaching_context_not_answer_key"
        assert out["llm_may_decide_correctness"] is False
        assert out["writeback_performed"] is False           # never writes learner-truth
        # no answer-key field leaks into the teaching payload
        assert "answer_key_authority" not in out and "required_terms" not in out
