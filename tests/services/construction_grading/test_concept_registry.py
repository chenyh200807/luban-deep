"""Concept registry — source-root identity fix (frozen concept_id, merge-with-provenance, disambiguation).

Hermetic, deterministic.
"""
from __future__ import annotations

from deeptutor.services.construction_grading import concept_registry as CR


def _nodes():
    return [
        # same name_path twice (enriched twice) -> MERGE, keyword union with provenance
        {"code": "X-01", "name": "按用途分类", "parent": "X", "name_path": "建筑 > 分类 > 按用途分类",
         "keywords": ["民用", "工业"], "level": 5},
        {"code": "X-01", "name": "按用途分类", "parent": "X", "name_path": "建筑 > 分类 > 按用途分类",
         "keywords": ["民用", "农业"], "level": 5},
        # SAME code X-01 but different name_path -> SEPARATE concept (collision disambiguated)
        {"code": "X-01", "name": "按高度分类", "parent": "X", "name_path": "建筑 > 分类 > 按高度分类",
         "keywords": ["高层"], "level": 5},
    ]


def test_merge_same_path_unions_keywords_with_provenance():
    reg = CR.compile_registry(_nodes())
    cid = CR.concept_id_for("建筑 > 分类 > 按用途分类")
    c = reg["concepts"][cid]
    kw = {k["text"] for k in c["keywords"]}
    assert kw == {"民用", "工业", "农业"}            # unioned
    assert all("source_code" in k for k in c["keywords"])  # provenance kept
    assert len(c["merged_from"]) == 2                # two enriched copies merged


def test_same_code_different_path_stay_separate():
    reg = CR.compile_registry(_nodes())
    use = CR.concept_id_for("建筑 > 分类 > 按用途分类")
    height = CR.concept_id_for("建筑 > 分类 > 按高度分类")
    assert use != height                              # disambiguated -> two concepts
    assert reg["manifest"]["concept_count"] == 2
    # the colliding code X-01 maps to BOTH -> recorded as a list (never silently one)
    assert isinstance(reg["alias_index"]["X-01"], list)


def test_resolve_alias_disambiguates_by_path():
    reg = CR.compile_registry(_nodes())
    cid = CR.resolve_alias(reg, "X-01", "建筑 > 分类 > 按高度分类")
    assert cid == CR.concept_id_for("建筑 > 分类 > 按高度分类")
    # collided code without name_path -> refuses to guess
    assert CR.resolve_alias(reg, "X-01") == ""


def test_concept_id_frozen_and_deterministic():
    # cosmetic whitespace doesn't change identity; recompile is byte-stable
    assert CR.concept_id_for("a > b > c") == CR.concept_id_for("a>b>c ")
    r1 = CR.compile_registry(_nodes())["manifest"]["content_hash"]
    r2 = CR.compile_registry(_nodes())["manifest"]["content_hash"]
    assert r1 == r2
