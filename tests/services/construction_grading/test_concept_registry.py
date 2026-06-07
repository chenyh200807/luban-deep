"""Concept registry v2 — stable identity, structural-conflict guard, provenance, collision hard-block.

Hermetic, deterministic. Hardened after adversarial review.
"""
from __future__ import annotations

from deeptutor.services.construction_grading import concept_registry as CR


def _nodes():
    return [
        # same path + same parent, enriched twice -> confirmed_same merge, keyword union w/ provenance
        {"code": "X-01", "name": "按用途分类", "parent": "X", "name_path": "建筑 > 分类 > 按用途分类",
         "keywords": ["民用", "工业"], "level": 5},
        {"code": "X-01", "name": "按用途分类", "parent": "X", "name_path": "建筑 > 分类 > 按用途分类",
         "keywords": ["民用", "农业"], "level": 5},
        # SAME code X-01, different name_path -> separate concept (disambiguated)
        {"code": "X-01", "name": "按高度分类", "parent": "X", "name_path": "建筑 > 分类 > 按高度分类",
         "keywords": ["高层"], "level": 5},
        # SAME name_path but DIFFERENT parent -> NOT auto-merged, both flagged structural_conflict
        {"code": "A-09", "name": "防水层施工", "parent": "屋面", "name_path": "施工 > 防水层施工",
         "keywords": ["卷材"], "level": 5},
        {"code": "B-04", "name": "防水层施工", "parent": "地下", "name_path": "施工 > 防水层施工",
         "keywords": ["涂膜"], "level": 5},
    ]


def test_confirmed_merge_unions_keywords_and_keeps_source_nodes():
    reg = CR.compile_registry(_nodes())
    # find the 按用途分类 concept
    c = next(x for x in reg["concepts"].values() if x["canonical_path"].endswith("按用途分类"))
    assert c["equivalence_status"] == CR.STATUS_CONFIRMED
    assert {k["text"] for k in c["keywords"]} == {"民用", "工业", "农业"}
    assert len(c["source_nodes"]) == 2 and all("raw_name_path" in s for s in c["source_nodes"])


def test_same_path_different_parent_not_merged_flagged_conflict():
    reg = CR.compile_registry(_nodes())
    wp = [x for x in reg["concepts"].values() if x["canonical_path"].endswith("防水层施工")]
    assert len(wp) == 2  # NOT merged — two structural positions kept separate
    assert all(x["equivalence_status"] == CR.STATUS_STRUCTURAL_CONFLICT for x in wp)
    assert {x["parent"] for x in wp} == {"屋面", "地下"}


def test_collided_code_hard_block():
    reg = CR.compile_registry(_nodes())
    assert isinstance(reg["alias_index"]["X-01"], list)  # spans >1 concept
    # no name_path -> refuse to single-resolve
    assert CR.resolve_alias(reg, "X-01") == ""
    # with name_path -> disambiguated
    assert CR.resolve_alias(reg, "X-01", "建筑 > 分类 > 按高度分类") == \
        next(x["concept_id"] for x in reg["concepts"].values() if x["canonical_path"].endswith("按高度分类"))


def test_concept_id_stable_across_recompile_with_prior():
    reg1 = CR.compile_registry(_nodes())
    # simulate a textbook revision: rename a leaf's display name (path/ parent unchanged) -> id must hold
    nodes2 = [dict(n) for n in _nodes()]
    # add a brand-new node; existing concepts must keep their ids via prior match
    nodes2.append({"code": "Z-01", "name": "新增", "parent": "X", "name_path": "建筑 > 分类 > 新增概念",
                   "keywords": ["x"], "level": 5})
    reg2 = CR.compile_registry(nodes2, prior=reg1)
    # every concept that existed in reg1 keeps its concept_id (keyed by path+parent, the concept group)
    fp1 = {(c["canonical_path"], c["parent"]): cid for cid, c in reg1["concepts"].items()}
    for cid, c in reg2["concepts"].items():
        k = (c["canonical_path"], c["parent"])
        if k in fp1:
            assert fp1[k] == cid  # durable id preserved across recompile
    assert reg2["manifest"]["concept_count"] == reg1["manifest"]["concept_count"] + 1


def test_deterministic():
    assert CR.compile_registry(_nodes())["manifest"]["content_hash"] == \
        CR.compile_registry(_nodes())["manifest"]["content_hash"]


def test_long_id_and_publish_gate():
    reg = CR.compile_registry(_nodes())
    # 16-hex (64-bit) ids, collision-safe
    assert all(len(cid) == 18 for cid in reg["concepts"])  # "c_" + 16 hex
    m = reg["manifest"]
    g = m["gates"]
    # has structural_conflict + collided code -> NOT learner-key-safe; topology snapshot always safe
    assert m["unresolved_adjudications"] >= 1
    assert g["topology_snapshot_safe"] is True
    assert g["learner_state_durable_key_safe"] is False
    assert g["cross_release_semantic_identity_safe"] is False  # fingerprint is topology-derived


def test_apply_adjudications_merge_migrates_and_clears_gate():
    reg = CR.compile_registry(_nodes())
    wp = [c["concept_id"] for c in reg["concepts"].values()
          if c["canonical_path"].endswith("防水层施工")]
    assert len(wp) == 2
    winner = sorted(wp)[0]
    out = CR.apply_adjudications(reg, [{
        "concept_ids": wp, "action": CR.ADJ_MERGE, "canonical_concept_id": winner,
        "reviewer": "expert_1", "reason": "同一防水层施工概念"}])
    # loser re-points to winner + migration edge produced
    loser = [c for c in wp if c != winner][0]
    assert out["concepts"][loser]["lineage"]["canonical_concept_id"] == winner
    assert out["concepts"][loser]["lifecycle"]["status"] == "merged"
    assert any(e["from"] == loser and e["to"] == winner for e in out["migration_edges"])
    # LLM/expert adjudication resolves conflicts -> retrieval/compilation open...
    g = out["manifest"]["gates"]
    assert out["manifest"]["unresolved_adjudications"] == 0
    assert g["retrieval_safe"] is True and g["compilation_safe"] is True
    # ...but learner_state durable key still requires human approval + zero legacy alias collisions
    assert g["learner_state_durable_key_safe"] is False  # no collisions here, but reviewer is not human


def test_human_approval_required_for_learner_key():
    # a human-approved merge with NO collided codes -> learner_state durable key gate can open
    nodes = [
        {"code": "P-1", "name": "概念A", "parent": "屋面", "name_path": "施工 > 概念A", "keywords": ["a"], "level": 5},
        {"code": "P-2", "name": "概念A", "parent": "地下", "name_path": "施工 > 概念A", "keywords": ["b"], "level": 5},
    ]
    reg = CR.compile_registry(nodes)
    ids = [c["concept_id"] for c in reg["concepts"].values()]
    out = CR.apply_adjudications(reg, [{
        "concept_ids": ids, "action": CR.ADJ_MERGE, "canonical_concept_id": sorted(ids)[0],
        "reviewer": "human_expert_1", "reason": "同一概念"}])
    g = out["manifest"]["gates"]
    assert g["human_adjudicated_merge_split_safe"] is True
    assert g["legacy_alias_migration_safe"] is True   # P-1/P-2 distinct codes, no collision
    assert g["learner_state_durable_key_safe"] is True  # human + no collision + resolved
