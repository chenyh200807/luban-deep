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

from deeptutor.services.taxonomy.construction_taxonomy import student_facing_label


def _node(
    node_id: str,
    *,
    exam_weight: float,
    child_concepts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        # single authority: canonical Chinese name or '' — never the raw node code (a learner-facing label)
        "label": student_facing_label(node_id),
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


# ─── Pack-level prerequisite edges（融合计划 §4-2，2026-07-03）─────────────
# 深 pack（60-slot 注册表 pack_id）级前置边——node_code 边之外的第二种承载，
# 同属本模块唯一 authority（教研拥有；禁全量 DAG：只登记有 jury/教研证据的边）。
# 语义：from = 前置站，to = 后继站。**不设前置锁**：边只影响学序排序
# （未学前置 A 时不把 B 排到 A 前），可跳站不变（v3.2 §5.1）。
# 每条边必须带数据签名（pack jury 记录 file:line）；教研确认前标
# pending_review=True——排序生效但对外理由文案不得声称教研已定。
_PACK_PREREQUISITE_EDGES: tuple[dict[str, Any], ...] = (
    {
        "from": "N01",
        "to": "N02",
        "relation": "prerequisite",
        "evidence": "60-slot registry slot 8→49：双代号网络计划关键线路/时间参数是 N 簇后续定量站的基础锚（1A433000-B041 复用）",
        "pending_review": True,
    },
    {
        "from": "N01",
        "to": "N04",
        "relation": "prerequisite",
        "evidence": "60-slot registry slot 50：时标网络计划与前锋线判断以 1A433000-B041 关键线路为辅锚（N 簇同链）",
        "pending_review": True,
    },
    {
        "from": "N01",
        "to": "K01",
        "relation": "prerequisite",
        "evidence": "K01_索赔成立与计算.md jury #5：网络计划定量求解=判索赔（工期臂）前置工具层能力（🔴高可信·回真源核）",
        "pending_review": True,
    },
)


def pack_prerequisites(pack_id: Any) -> list[str]:
    """返回 ``pack_id`` 的前置 pack 列表（登记序）。未登记 → []。"""
    normalized = str(pack_id or "").strip()
    if not normalized:
        return []
    return [
        edge["from"]
        for edge in _PACK_PREREQUISITE_EDGES
        if edge["to"] == normalized and edge["relation"] == "prerequisite"
    ]


def list_pack_prerequisite_edges() -> list[dict[str, Any]]:
    """全部 pack 级前置边（fresh copies，含证据签名与 pending_review）。"""
    return [dict(edge) for edge in _PACK_PREREQUISITE_EDGES]


def order_packs_with_prerequisites(
    ordered_pack_ids: list[str],
    *,
    unlearned_pack_ids: set[str],
) -> list[str]:
    """学序的前置过滤（融合计划 §4-2）：稳定重排——当后继 B 已在序列中、
    其未学前置 A 出现在 B 之后时，把 A 提到 B 前。**不是锁**：不移除任何
    站、不阻止直接访问；只消章序陷阱（如 K01 章节序先于其前置 N01）。"""
    ordered = [str(item or "").strip() for item in ordered_pack_ids if str(item or "").strip()]
    result: list[str] = []
    for pack_id in ordered:
        insert_at = len(result)
        if pack_id in unlearned_pack_ids:
            dependents = [
                index
                for index, placed in enumerate(result)
                if placed in unlearned_pack_ids and pack_id in pack_prerequisites(placed)
            ]
            if dependents:
                insert_at = min(dependents)
        result.insert(insert_at, pack_id)
    return result


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
    "list_pack_prerequisite_edges",
    "order_packs_with_prerequisites",
    "pack_prerequisites",
    "related_learning_graph_edges",
]
