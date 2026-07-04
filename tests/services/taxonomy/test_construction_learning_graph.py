"""Batch A Task 3: minimal expert learning graph seed.

The plan asks for an expert-owned small graph that drives the V3-aligned
node_code namespace (1A4XXXXX). The graph is layered on top of the
existing ``construction_taxonomy.py`` label authority — taxonomy maps
node_id → label; this graph adds child_concepts and typed edges.

Hard rules from the plan:

- Use only real ``questions_bank.node_code`` literals (e.g. ``1A412010``,
  ``1A422000``, ``1A436000``); never invent dotted sub-codes like
  ``1A421000.fire_door.rating``.
- ``child_concept_label`` may exist as a free-text sub-concept but the
  canonical ``knowledge_node_id`` MUST resolve to a seeded node.
- No full-textbook graph; no automatic graph construction.
"""
from __future__ import annotations

import pytest

from deeptutor.services.taxonomy.construction_learning_graph import (
    get_learning_graph_node,
    is_known_learning_graph_node,
    list_learning_graph_clusters,
    related_learning_graph_edges,
)


def test_learning_graph_exposes_high_value_material_nodes() -> None:
    """Plan's literal failing test (adapted to real node_code namespace):
    a known node returns label / node_type / exam_weight and has at least
    one easy_confuse edge."""
    node = get_learning_graph_node("1A412010")

    assert isinstance(node, dict), "seeded node must resolve to a dict"
    assert node["label"]  # non-empty, sourced from construction_taxonomy
    assert node["node_type"] == "knowledge_point"
    assert isinstance(node["exam_weight"], (int, float))
    assert node["exam_weight"] > 0

    edges = related_learning_graph_edges("1A412010", relation="easy_confuse")
    assert any(edge["to"] == "1A412020" for edge in edges), (
        f"1A412010 must have an easy_confuse edge to 1A412020 (材料类相互混淆); got {edges}"
    )


def test_unknown_node_returns_none() -> None:
    """Unseeded codes resolve to None; consumers can treat as 'not in seed'."""
    assert get_learning_graph_node("1A999999") is None
    assert get_learning_graph_node("") is None
    assert get_learning_graph_node(None) is None  # type: ignore[arg-type]


def test_is_known_learning_graph_node_helper() -> None:
    """Helper used by downstream guards (evidence normalizer, contract
    guard) to validate ``knowledge_node_id`` references."""
    assert is_known_learning_graph_node("1A412010") is True
    assert is_known_learning_graph_node("1A999999") is False
    assert is_known_learning_graph_node("") is False
    assert is_known_learning_graph_node(None) is False  # type: ignore[arg-type]


def test_related_edges_filter_by_relation() -> None:
    """``relation`` argument filters edges; omitting it returns all."""
    all_edges = related_learning_graph_edges("1A412010")
    typed_edges = related_learning_graph_edges("1A412010", relation="easy_confuse")
    assert len(all_edges) >= len(typed_edges)
    for edge in typed_edges:
        assert edge["relation"] == "easy_confuse"


def test_each_node_has_child_concepts_when_seed_specifies_them() -> None:
    """Children are free-text labels (e.g. '甲乙丙级耐火极限') but their
    parent knowledge_node_id MUST resolve to a seeded node. This is the
    invariant evidence-time validators rely on."""
    # 1A412030 (建筑功能材料) and 1A436000 (施工安全管理) are the two nodes
    # the seed explicitly enriches with child concepts (防水/防火/保温 and
    # 危大工程/专项方案/专家论证 respectively). Both must produce at least
    # one resolvable child.
    for node_id in ("1A412030", "1A436000"):
        node = get_learning_graph_node(node_id)
        assert node is not None, f"{node_id} must be seeded"
        children = node.get("child_concepts") or []
        assert children, f"{node_id} must seed at least one child_concept"
        for child in children:
            assert isinstance(child, dict)
            assert child.get("label"), f"child of {node_id} must have a label"
            # parent_node_id self-reference (the resolvable canonical id)
            assert is_known_learning_graph_node(child.get("parent_node_id") or node_id)


def test_clusters_listed_with_documented_node_ids() -> None:
    """Three high-value clusters documented in the plan baseline:
    建筑材料 / 施工技术 / 管理实务."""
    clusters = list_learning_graph_clusters()
    cluster_names = {cluster["name"] for cluster in clusters}

    assert {"建筑材料", "施工技术", "管理实务"}.issubset(cluster_names), cluster_names

    for cluster in clusters:
        # Every node_id in a cluster must be seeded (no dangling references).
        for node_id in cluster["node_ids"]:
            assert is_known_learning_graph_node(node_id), (
                f"cluster {cluster['name']!r} references unseeded {node_id}"
            )


def test_no_invented_dotted_node_ids_in_seed() -> None:
    """Defensive: every seeded node_id matches the canonical 1A4 7-8 char
    namespace. Reject any invented dotted sub-code that does not appear
    in the production questions_bank.node_code column."""
    import re

    pattern = re.compile(r"^1A4\d{4,5}$")
    clusters = list_learning_graph_clusters()
    seen: set[str] = set()
    for cluster in clusters:
        for node_id in cluster["node_ids"]:
            seen.add(node_id)
    for node_id in seen:
        assert pattern.match(node_id), f"{node_id!r} is not a valid 1A4XXXX(X) node_code"
        # And it must actually resolve.
        node = get_learning_graph_node(node_id)
        assert node is not None, f"{node_id} listed in cluster but not seeded"


def test_seed_remains_small_under_phase_minus1_scope() -> None:
    """Phase -1 release condition: 'no full textbook graph'. The seed
    intentionally caps at a few clusters; if this number explodes,
    someone is sneaking in a wider graph and should escalate."""
    clusters = list_learning_graph_clusters()
    total_nodes = sum(len(c["node_ids"]) for c in clusters)
    assert total_nodes <= 25, f"seed has {total_nodes} nodes — bigger than Phase -1 scope allows"


def test_pack_prerequisite_edges_carry_evidence_and_pending_review() -> None:
    # §4-2:禁全量 DAG——只登记有 jury/教研证据的边;教研确认前必须标 pending。
    from deeptutor.services.taxonomy.construction_learning_graph import (
        list_pack_prerequisite_edges,
        pack_prerequisites,
    )

    edges = list_pack_prerequisite_edges()
    assert len(edges) == 3  # N01→N02 / N01→N04 / N01→K01,一条不多
    for edge in edges:
        assert edge["relation"] == "prerequisite"
        assert edge["evidence"], f"edge {edge} missing data signature"
        assert edge["pending_review"] is True
    assert pack_prerequisites("K01") == ["N01"]
    assert pack_prerequisites("N02") == ["N01"]
    assert pack_prerequisites("N04") == ["N01"]
    assert pack_prerequisites("A01") == []


def test_order_packs_with_prerequisites_is_stable_and_lock_free() -> None:
    from deeptutor.services.taxonomy.construction_learning_graph import (
        order_packs_with_prerequisites,
    )

    # 章序陷阱:K01 在 N01 前,两者都未学 → N01 提到 K01 前;其余序稳定。
    ordered = order_packs_with_prerequisites(
        ["A01", "K01", "L01", "N01"],
        unlearned_pack_ids={"A01", "K01", "L01", "N01"},
    )
    assert ordered.index("N01") < ordered.index("K01")
    assert ordered[0] == "A01"  # 无关站不受扰动
    assert set(ordered) == {"A01", "K01", "L01", "N01"}  # 不是锁:不移除任何站

    # 前置已学 → 不重排。
    ordered = order_packs_with_prerequisites(
        ["K01", "N01"],
        unlearned_pack_ids={"K01"},
    )
    assert ordered == ["K01", "N01"]
