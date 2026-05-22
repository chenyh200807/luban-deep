"""Batch A Task 3: minimal expert-owned learning graph seed.

Layered on top of ``construction_taxonomy.py`` (which holds node_id →
label) and ``docs/qa/2026-05-22-rubric-coverage-baseline.md`` (which
recorded the high-coverage clusters from Supabase). This module adds two
things the label authority doesn't carry:

1. **child_concepts** — free-text sub-labels (e.g. "甲乙丙级耐火极限",
   "专家论证") that map back to a canonical ``parent_node_id``. The UI
   uses them as render hints; ``parent_node_id`` is what evidence
   payloads cite.
2. **typed edges** — `easy_confuse` between concepts students commonly
   mix up, `prerequisite` between施工 sequence steps.

Hard rules from the plan:

- Only real ``questions_bank.node_code`` literals (1A4XXXXX, 7-8 chars).
- No automatic graph construction; no full textbook graph.
- Expert-owned: every node carries an ``exam_weight`` derived from the
  measured baseline so downstream prescription can prioritize coverage.

The seed is intentionally small (≤ 25 nodes for Phase -1). Growth lives
in a follow-up — every PR that adds nodes must update the seed AND a
review checklist signed by 教研 + 数据.
"""
from __future__ import annotations

from typing import Any, Iterable

from deeptutor.services.taxonomy.construction_taxonomy import display_taxonomy_label


def _node(
    node_id: str,
    *,
    exam_weight: float,
    child_concepts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "label": display_taxonomy_label(node_id, fallback=node_id),
        "node_type": "knowledge_point",
        "exam_weight": exam_weight,
        "child_concepts": [
            {"label": child["label"], "parent_node_id": node_id}
            for child in (child_concepts or [])
            if child.get("label")
        ],
    }


# ─── Cluster: 建筑材料 ─────────────────────────────────────────────────────
# Plan-required seed: 1A412010 / 1A412020 / 1A412030. The functional
# materials node gets explicit child concepts because防水/防火/保温 are
# distinct memorization-heavy sub-topics with frequent 易混 数值.
_NODES_BUILDING_MATERIALS = [
    _node("1A412010", exam_weight=0.85),  # 结构工程材料
    _node("1A412020", exam_weight=0.65),  # 装饰装修工程材料
    _node(
        "1A412030",
        exam_weight=0.80,
        child_concepts=[
            {"label": "建筑防水材料的特性与应用"},
            {"label": "建筑防火材料的特性与应用"},
            {"label": "建筑保温、隔热材料的特性与应用"},
        ],
    ),
]

# ─── Cluster: 施工技术 ─────────────────────────────────────────────────────
# Five施工 sequence steps with prerequisite chain. These are the highest
# weight nodes for case-study items per the rubric coverage baseline.
_NODES_CONSTRUCTION_TECH = [
    _node("1A413020", exam_weight=0.70),  # 土石方工程施工
    _node("1A413030", exam_weight=0.85),  # 地基与基础工程施工
    _node("1A413040", exam_weight=0.95),  # 主体结构工程施工
    _node("1A413050", exam_weight=0.75),  # 屋面与防水工程施工
    _node("1A413060", exam_weight=0.65),  # 装饰装修工程施工
]

# ─── Cluster: 管理实务 ─────────────────────────────────────────────────────
# Four management areas; 安全管理 (危大工程) gets explicit child concepts
# because the case_study items repeatedly fail at专项方案 / 专家论证 /
# 监测预警 triplet (per the 教研 grading map).
_NODES_MANAGEMENT_PRACTICE = [
    _node("1A432000", exam_weight=0.75),  # 工程招标投标与合同管理
    _node("1A433000", exam_weight=0.80),  # 施工进度管理
    _node("1A434000", exam_weight=0.80),  # 施工质量管理
    _node(
        "1A436000",
        exam_weight=0.90,
        child_concepts=[
            {"label": "危大工程清单"},
            {"label": "专项施工方案"},
            {"label": "专家论证"},
            {"label": "监测预警与应急处置"},
        ],
    ),
]


# ─── Edges ────────────────────────────────────────────────────────────────
# Two relation types in scope for Phase -1:
#   - easy_confuse: 易混知识点 (UI shows alongside the weak point)
#   - prerequisite: 施工序列 (Batch B's transfer ability dimension uses it)
def _edge(from_id: str, to_id: str, relation: str) -> dict[str, str]:
    return {"from": from_id, "to": to_id, "relation": relation}


_EDGES: tuple[dict[str, str], ...] = (
    # 建筑材料簇 — 三个材料类节点之间互混
    _edge("1A412010", "1A412020", "easy_confuse"),
    _edge("1A412020", "1A412010", "easy_confuse"),
    _edge("1A412020", "1A412030", "easy_confuse"),
    _edge("1A412030", "1A412020", "easy_confuse"),
    # 施工技术簇 — 单向先决关系
    _edge("1A413020", "1A413030", "prerequisite"),
    _edge("1A413030", "1A413040", "prerequisite"),
    _edge("1A413040", "1A413050", "prerequisite"),
    _edge("1A413050", "1A413060", "prerequisite"),
    # 管理实务簇 — 合同/进度跨考、质量/安全跨考
    _edge("1A432000", "1A433000", "easy_confuse"),
    _edge("1A433000", "1A432000", "easy_confuse"),
    _edge("1A434000", "1A436000", "easy_confuse"),
    _edge("1A436000", "1A434000", "easy_confuse"),
)


_CLUSTERS: tuple[dict[str, Any], ...] = (
    {
        "name": "建筑材料",
        "summary": "结构 / 装饰装修 / 功能材料三类的概念区分与数值记忆",
        "node_ids": [node["node_id"] for node in _NODES_BUILDING_MATERIALS],
    },
    {
        "name": "施工技术",
        "summary": "土石方 → 地基 → 主体 → 屋面 → 装饰的施工序列与质量验收要点",
        "node_ids": [node["node_id"] for node in _NODES_CONSTRUCTION_TECH],
    },
    {
        "name": "管理实务",
        "summary": "合同/索赔、进度、质量、安全四类管理实务，安全侧重危大工程",
        "node_ids": [node["node_id"] for node in _NODES_MANAGEMENT_PRACTICE],
    },
)


_GRAPH: dict[str, dict[str, Any]] = {
    node["node_id"]: node
    for cluster_nodes in (
        _NODES_BUILDING_MATERIALS,
        _NODES_CONSTRUCTION_TECH,
        _NODES_MANAGEMENT_PRACTICE,
    )
    for node in cluster_nodes
}


def get_learning_graph_node(node_id: Any) -> dict[str, Any] | None:
    """Return the seeded node payload for ``node_id`` or ``None`` if unseeded."""
    normalized = str(node_id or "").strip()
    if not normalized:
        return None
    found = _GRAPH.get(normalized)
    return dict(found) if found else None  # return a copy so callers can't mutate


def is_known_learning_graph_node(node_id: Any) -> bool:
    """Cheap membership test used by evidence / contract guards."""
    return bool(node_id) and str(node_id).strip() in _GRAPH


def related_learning_graph_edges(
    node_id: Any,
    *,
    relation: str | None = None,
) -> list[dict[str, str]]:
    """Return outbound edges from ``node_id``.

    When ``relation`` is provided, edges are filtered to that relation
    type. The returned list is a fresh list so callers cannot mutate
    the seed.
    """
    normalized = str(node_id or "").strip()
    if not normalized:
        return []
    out: list[dict[str, str]] = []
    for edge in _EDGES:
        if edge["from"] != normalized:
            continue
        if relation is not None and edge["relation"] != relation:
            continue
        out.append(dict(edge))
    return out


def list_learning_graph_clusters() -> list[dict[str, Any]]:
    """Documented high-value clusters. Returns fresh copies."""
    return [
        {**cluster, "node_ids": list(cluster["node_ids"])}
        for cluster in _CLUSTERS
    ]


def iter_known_node_ids() -> Iterable[str]:
    """Read-only view of every seeded node_id (for contract-guard scans)."""
    return tuple(_GRAPH.keys())


__all__ = [
    "get_learning_graph_node",
    "is_known_learning_graph_node",
    "iter_known_node_ids",
    "list_learning_graph_clusters",
    "related_learning_graph_edges",
]
