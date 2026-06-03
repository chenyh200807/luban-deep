from __future__ import annotations

import tomllib
from pathlib import Path

from deeptutor.services.taxonomy.learning_topic_resolver import (
    compile_taxonomy_payload,
    resolve_learning_topic_from_payload,
)


def test_compile_taxonomy_payload_flattens_final_cleaned_outline() -> None:
    compiled = compile_taxonomy_payload(
        {
            "meta": {"version": "test"},
            "outline_structure": [
                {
                    "code": "1A413000",
                    "name": "建筑工程施工技术",
                    "level": 2,
                    "children": [
                        {
                            "code": "1A413050",
                            "name": "屋面与防水工程施工",
                            "level": 3,
                            "keywords": ["防水", "屋面"],
                            "children": [
                                {
                                    "code": "1A413053",
                                    "name": "地下室防水工程施工",
                                    "level": 4,
                                    "keywords": ["地下室防水"],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        source_path="fixture/FINAL_CLEANED_TAXONOMY2026.json",
        content_sha256="sha",
    )

    assert compiled["source"]["path"] == "fixture/FINAL_CLEANED_TAXONOMY2026.json"
    assert compiled["source"]["stats"] == {
        "total_nodes": 3,
        "coded_nodes": 3,
        "leaf_nodes": 1,
        "unique_codes": 3,
        "duplicate_code_rows": 0,
    }
    assert compiled["nodes_by_code"]["1A413053"]["name"] == "地下室防水工程施工"
    assert compiled["nodes_by_code"]["1A413053"]["path_names"] == [
        "建筑工程施工技术",
        "屋面与防水工程施工",
        "地下室防水工程施工",
    ]


def test_compile_taxonomy_payload_does_not_index_duplicate_codes_as_authority() -> None:
    compiled = compile_taxonomy_payload(
        {
            "outline_structure": [
                {"code": "1A411011-01", "name": "按建筑用途分类"},
                {"code": "1A411011-01", "name": "按建筑高度分类"},
            ],
        },
        source_path="fixture/FINAL_CLEANED_TAXONOMY2026.json",
        content_sha256="sha",
    )

    assert "1A411011-01" not in compiled["nodes_by_code"]
    assert compiled["duplicate_codes"] == ["1A411011-01"]
    assert compiled["ambiguous_codes"] == ["1A411011-01"]
    assert compiled["nodes_by_id"]["1A411011-01#1"]["name"] == "按建筑用途分类"
    assert compiled["nodes_by_id"]["1A411011-01#2"]["name"] == "按建筑高度分类"


def test_resolver_uses_compiled_taxonomy_code_before_free_text() -> None:
    resolved = resolve_learning_topic_from_payload(
        {
            "concept": {"label": "这题"},
            "knowledge_points": ["这题"],
            "learning_state_ref": "knowledge:1A413053",
        }
    )

    assert resolved is not None
    assert resolved.label == "地下室防水工程施工"
    assert resolved.source == "taxonomy_code"
    assert resolved.taxonomy_code == "1A413053"
    assert resolved.confidence == "high"


def test_resolver_preserves_lowercase_taxonomy_leaf_code_suffix() -> None:
    resolved = resolve_learning_topic_from_payload({"learning_state_ref": "knowledge:1a411011-02-d"})

    assert resolved is not None
    assert resolved.label == "建筑高度计算方法"
    assert resolved.source == "taxonomy_code"
    assert resolved.taxonomy_code == "1A411011-02-d"


def test_resolver_does_not_resolve_ambiguous_duplicate_taxonomy_code() -> None:
    resolved = resolve_learning_topic_from_payload({"learning_state_ref": "knowledge:1A411011-01"})

    assert resolved is None


def test_resolver_prefers_specific_focus_over_broad_concept_code() -> None:
    resolved = resolve_learning_topic_from_payload(
        {
            "next_training_signal": {
                "concept": "1A432000",
                "focus": "专家论证程序",
            },
        },
        llm_topic_inferer=lambda _payload, _candidates: "专家论证程序",
    )

    assert resolved is not None
    assert resolved.label == "专家论证程序"
    assert resolved.source == "llm_inferred"
    assert resolved.taxonomy_code == ""


def test_resolver_falls_back_to_concept_code_when_focus_is_deictic() -> None:
    resolved = resolve_learning_topic_from_payload(
        {
            "next_training_signal": {
                "concept": "1A432000",
                "focus": "这题",
            },
        },
        llm_topic_inferer=lambda _payload, _candidates: "不应调用",
    )

    assert resolved is not None
    assert resolved.label == "工程招标投标与合同管理"
    assert resolved.source == "taxonomy_code"
    assert resolved.taxonomy_code == "1A432000"


def test_resolver_does_not_high_confidence_map_ambiguous_text_label() -> None:
    resolved = resolve_learning_topic_from_payload(
        {"knowledge_points": ["施工成本管理"]},
        llm_topic_inferer=None,
    )

    assert resolved is None


def test_resolver_can_resolve_duplicate_taxonomy_node_by_canonical_id() -> None:
    resolved = resolve_learning_topic_from_payload({"taxonomy_id": "1A411011-01#1"})

    assert resolved is not None
    assert resolved.label == "按建筑用途分类"
    assert resolved.source == "taxonomy_id"
    assert resolved.taxonomy_code == "1A411011-01"


def test_resolver_rejects_deictic_labels_without_confirmed_topic() -> None:
    resolved = resolve_learning_topic_from_payload(
        {
            "next_training_signal": {"focus": "这题"},
            "concept": {"label": "本题"},
            "error": {"label": "这道题"},
        }
    )

    assert resolved is None


def test_resolver_does_not_remap_structured_label_to_coarse_topic_by_keyword() -> None:
    resolved = resolve_learning_topic_from_payload({"knowledge_points": ["招投标与合同"]})

    assert resolved is None


def test_resolver_does_not_promote_topic_catalog_label_as_taxonomy_authority() -> None:
    resolved = resolve_learning_topic_from_payload({"knowledge_points": ["防水工程"]})

    assert resolved is None


def test_resolver_allows_llm_inferred_topic_when_taxonomy_misses() -> None:
    calls: list[dict[str, object]] = []

    def inferer(payload: dict[str, object], candidates: list[str]) -> str:
        calls.append({"payload": payload, "candidates": candidates})
        return "雨季混凝土养护"

    resolved = resolve_learning_topic_from_payload(
        {
            "question_stem": "雨季施工时，混凝土浇筑后养护措施选择错误。",
            "simple_explanation": "应结合雨季施工和混凝土养护要求判断。",
        },
        llm_topic_inferer=inferer,
    )

    assert resolved is not None
    assert resolved.label == "雨季混凝土养护"
    assert resolved.source == "llm_inferred"
    assert resolved.confidence == "low"
    assert calls


def test_resolver_can_use_sanitized_evidence_as_low_confidence_personalized_focus_after_llm_miss() -> None:
    resolved = resolve_learning_topic_from_payload(
        {"knowledge_points": ["防水工程"]},
        llm_topic_inferer=lambda _payload, _candidates: "",
    )

    assert resolved is not None
    assert resolved.label == "防水工程"
    assert resolved.source == "evidence_inferred"
    assert resolved.confidence == "low"
    assert resolved.taxonomy_code == ""


def test_compiled_taxonomy_artifact_is_packaged() -> None:
    pyproject = tomllib.loads((Path(__file__).parents[3] / "pyproject.toml").read_text())

    package_data = pyproject["tool"]["setuptools"]["package-data"]

    assert "compiled/*.json" in package_data["deeptutor.services.taxonomy"]
