"""System-level compiled knowledge service facade.

The service may reuse construction-grading canonical bundles, but callers should
not have to import a grading namespace to get compiled teaching context.

Anti-pollution guard tests below are hermetic: they inject a controlled
taxonomy index + compiled bundle so they pin the guard MECHANISM
(strict-path veto / source-path conflict / detached stop), not whatever the
live canonical taxonomy happens to contain. The live axis is frozen and
evolves through gap-fold revisions; queries that used to be "wrong path"
can become correct paths, which must not break these guards' tests.
"""
from __future__ import annotations

from typing import Any

import pytest


_HERMETIC_LEAVES = [
    # path contains 质量验收 but NOT the strict term 分部工程 (wrong sibling)
    {
        "code": "2-1-5",
        "name_path": "施工质量管理->单位工程质量验收程序",
        "keywords": [],
    },
    # makes the strict term 分部工程 satisfiable via keywords, path lacks it
    {
        "code": "2-1-6",
        "name_path": "施工质量管理->验收组织职责",
        "keywords": ["分部工程"],
    },
    # alias-only wrong sibling for 地下防水等级 queries（屋面 ≠ 地下）
    {
        "code": "3-4-1",
        "name_path": "防水工程->屋面防水工程施工",
        "keywords": [],
    },
    # wrong sibling for 幕墙防火 queries
    {
        "code": "4-2-2",
        "name_path": "消防工程->防火分区与耐火等级",
        "keywords": [],
    },
    # detached candidate: path legitimately matches 绿色施工 queries but the
    # compiler source-alignment repair has detached it
    {
        "code": "5-3-1",
        "name_path": "绿色施工与环境保护->绿色施工四节一环保",
        "keywords": [],
    },
    # clean control leaf: correct path + aligned sources, must keep resolving
    {
        "code": "6-1-9",
        "name_path": "脚手架工程->连墙件设置要求",
        "keywords": [],
    },
]

_HERMETIC_NAME_PATHS = {leaf["code"]: leaf["name_path"] for leaf in _HERMETIC_LEAVES}

_HERMETIC_BUNDLE = {
    "nodes": {
        # source-only acceptance match: sources talk about 分部工程质量验收,
        # but the node path is the wrong sibling
        "2-1-5": {
            "sources": {
                "textbook": [
                    {"text_preview": "分部工程质量验收由总监理工程师组织施工单位项目负责人等进行"}
                ],
                "standard": [
                    {"text_preview": "分部工程质量验收合格规定：所含分项工程质量验收均应合格"}
                ],
            }
        },
        "3-4-1": {
            "sources": {
                "textbook": [
                    {"text_preview": "地下防水等级一级不允许渗水，二级不允许漏水"}
                ],
                "standard": [
                    {"text_preview": "地下工程防水等级分为四级"}
                ],
            }
        },
        "4-2-2": {
            "sources": {
                "textbook": [
                    {"text_preview": "建筑幕墙防火封堵应采用防火封堵材料在每层楼板外沿处封堵"}
                ],
                "standard": [
                    {"text_preview": "建筑幕墙与每层楼板隔墙处的缝隙应进行防火封堵"}
                ],
            }
        },
        "5-3-1": {
            "sources": {
                "textbook": [
                    {"text_preview": "绿色施工四节一环保：节材节水节能节地和环境保护"}
                ],
                "standard": [
                    {"text_preview": "绿色施工导则规定四节一环保要求"}
                ],
            }
        },
        "6-1-9": {
            "sources": {
                "textbook": [
                    {"text_preview": "脚手架连墙件设置应靠近主节点，偏离主节点的距离不应大于300mm"}
                ],
                "standard": [
                    {"text_preview": "脚手架连墙件应从底层第一步纵向水平杆处开始设置"}
                ],
            }
        },
    }
}

_HERMETIC_DETACHED = {"5-3-1"}


@pytest.fixture
def hermetic_compiled_axis(monkeypatch: pytest.MonkeyPatch):
    """Inject a frozen mini taxonomy + bundle under the real guard logic."""
    from deeptutor.services.compiled_knowledge import general_knowledge
    from deeptutor.services.construction_grading import canonical_resolution as cr
    from deeptutor.services.construction_grading import canonical_knowledge_runtime as ckr

    monkeypatch.setattr(cr, "_index", lambda: {"leaves": list(_HERMETIC_LEAVES)})
    monkeypatch.setattr(cr, "name_path", lambda code: _HERMETIC_NAME_PATHS.get(str(code or ""), ""))
    monkeypatch.setattr(cr, "to_canonical", lambda _text: None)

    monkeypatch.setattr(ckr, "_load", lambda: _HERMETIC_BUNDLE)
    monkeypatch.setattr(
        ckr,
        "source_items_for_node",
        lambda bundle, code, source_key: list(
            (((bundle.get("nodes") or {}).get(str(code or "")) or {}).get("sources") or {}).get(source_key) or []
        ),
    )
    monkeypatch.setattr(
        ckr,
        "is_general_compiled_context_detached",
        lambda code: str(code or "") in _HERMETIC_DETACHED,
    )

    def _resolve_canonical_knowledge(anchor: str, *, learner_context: Any = None, per_source: int = 6):
        node = (_HERMETIC_BUNDLE["nodes"]).get(str(anchor or ""))
        if not node:
            return None
        return {
            "tier": "teaching_context_not_answer_key",
            "canonical_taxonomy_version": "FINAL_CLEANED_TAXONOMY2026",
            "sources": dict(node.get("sources") or {}),
            "selected_counts": {},
            "graph_neighbors": {},
            "remediation": None,
        }

    monkeypatch.setattr(ckr, "resolve_canonical_knowledge", _resolve_canonical_knowledge)
    return general_knowledge


def test_system_compiled_knowledge_service_resolves_teaching_context() -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge

    out = general_knowledge.resolve_general_knowledge_context(
        "施工合同索赔成立条件是什么？"
    )

    assert out is not None
    assert out["authority"] == "luban_general_knowledge_context"
    assert out["tier"] == "teaching_context_not_answer_key"
    assert out["official_score_allowed"] is False
    assert out["llm_may_decide_correctness"] is False
    assert "索赔" in out["leaf_name_path"]
    assert out["query_plan"]["policy"] == "compiled_query_plan_v1"


def test_top_k_query_plan_does_not_require_single_winner(monkeypatch) -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge

    monkeypatch.setattr(general_knowledge._CR, "to_canonical", lambda _text: None)

    out = general_knowledge.resolve_general_knowledge_context("施工合同索赔成立条件是什么？")

    assert out is not None
    assert "索赔" in out["leaf_name_path"]
    assert out["query_plan"]["initial_leaf"] is None


def test_strict_primary_path_terms_reject_source_only_acceptance_match(
    hermetic_compiled_axis,
) -> None:
    """A wrong-sibling 质量验收 leaf whose SOURCES mention 分部工程 must be vetoed:
    source-only matches cannot satisfy a satisfiable strict path term."""
    general_knowledge = hermetic_compiled_axis

    plan = general_knowledge.build_general_knowledge_query_plan("分部工程质量验收谁组织？")

    assert any(
        "primary_path_mismatch" in candidate.get("negative_evidence", [])
        for candidate in plan["candidates"]
        if "质量验收" in candidate.get("leaf_name_path", "")
        and "分部工程" not in candidate.get("leaf_name_path", "")
    )
    assert general_knowledge.resolve_general_knowledge_context("分部工程质量验收谁组织？") is None


def test_compiler_source_alignment_repairs_fail_open_known_wrong_path_shadow_cases(
    hermetic_compiled_axis,
) -> None:
    """When the compiled axis has no correct path for a query, juicy wrong-sibling
    sources must NOT take over: the service fails open (None) so RAG stays authority."""
    general_knowledge = hermetic_compiled_axis

    wrong_path_queries = [
        "建筑幕墙防火封堵有什么要求？",
        "地下防水等级一级和二级有什么区别？",
        "施工组织设计谁审批？",
        "冬期施工混凝土养护怎么做？",
    ]

    for query in wrong_path_queries:
        assert general_knowledge.resolve_general_knowledge_context(query) is None, query


def test_compiler_detached_candidate_stops_before_wrong_sibling_takeover(
    hermetic_compiled_axis,
) -> None:
    """A path-matching candidate detached by compiler source-alignment repair must
    stop resolution entirely (no sibling takeover), while clean leaves keep resolving."""
    general_knowledge = hermetic_compiled_axis

    plan = general_knowledge.build_general_knowledge_query_plan("绿色施工四节一环保分别是什么？")

    assert plan["detached_candidate_count"] > 0
    assert general_knowledge.resolve_general_knowledge_context("绿色施工四节一环保分别是什么？") is None
    assert general_knowledge.resolve_general_knowledge_context("脚手架连墙件设置有什么要求？") is not None


def test_legacy_construction_grading_import_stays_compatible() -> None:
    from deeptutor.services.compiled_knowledge import general_knowledge
    from deeptutor.services.construction_grading import general_knowledge_context

    assert (
        general_knowledge_context.resolve_general_knowledge_context
        is general_knowledge.resolve_general_knowledge_context
    )
    assert (
        general_knowledge_context.build_general_knowledge_query_plan
        is general_knowledge.build_general_knowledge_query_plan
    )
