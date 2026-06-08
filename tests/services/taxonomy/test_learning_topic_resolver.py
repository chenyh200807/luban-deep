from __future__ import annotations

import tomllib
from pathlib import Path

from deeptutor.services.taxonomy.learning_topic_resolver import (
    canonical_learning_topic_label,
    compile_taxonomy_payload,
    normalize_learning_topic_text,
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


def test_resolver_falls_to_canonical_concept_when_classifier_misses() -> None:
    # CANONICAL CLASSIFIER: a non-canonical free phrase ('专家论证程序') is not a valid option, so it is
    # NOT emitted; the recommendation falls to the canonical concept anchor (1A432000) instead.
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
    assert resolved.taxonomy_code == "1A432000"
    assert resolved.label == "工程招标投标与合同管理"
    assert resolved.source == "taxonomy_code"


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


def test_resolver_classifier_accepts_only_canonical_option() -> None:
    # The classifier must PICK a canonical chapter/section name. A real option name -> recommended (canonical
    # name + code); a free phrase not in the option list -> NOT recommended.
    canonical = resolve_learning_topic_from_payload(
        {"question_stem": "雨季施工混凝土养护出错。", "simple_explanation": "季节性施工。"},
        llm_topic_inferer=lambda _p, _c: "屋面与防水工程施工",   # a real canonical section name
    )
    assert canonical is not None
    assert canonical.label == "屋面与防水工程施工"
    assert canonical.taxonomy_code == "1A413"
    assert canonical.source == "canonical_classified"

    off_taxonomy = resolve_learning_topic_from_payload(
        {"question_stem": "雨季施工混凝土养护出错。", "simple_explanation": "季节性施工。"},
        llm_topic_inferer=lambda _p, _c: "雨季混凝土养护",       # not a canonical option -> dropped
    )
    assert off_taxonomy is None


def test_resolver_drops_non_canonical_evidence_label() -> None:
    # a raw evidence label that isn't a canonical option ('防水工程') and no classifier hit -> recommend
    # nothing (never fuzzy-guess which 防水 node, never emit off-taxonomy free text).
    resolved = resolve_learning_topic_from_payload(
        {"knowledge_points": ["防水工程"]},
        llm_topic_inferer=lambda _payload, _candidates: "",
    )

    assert resolved is None


def test_normalize_learning_topic_text_filters_noise_but_keeps_real_exam_topics() -> None:
    assert normalize_learning_topic_text("施工现场临时用电") == "施工现场临时用电"
    assert normalize_learning_topic_text("防水工程") == "防水工程"
    assert normalize_learning_topic_text("专家论证程序") == "专家论证程序"

    assert normalize_learning_topic_text("讲义封底 扫码领取免费资料") == ""
    assert normalize_learning_topic_text("一级建造师建筑实务知识点归纳") == ""
    assert normalize_learning_topic_text("关注公众号领取课程二维码") == ""
    assert normalize_learning_topic_text("本题为") == ""
    assert normalize_learning_topic_text("施工现场布置塔吊时应考虑的因素还有哪些？") == ""
    assert normalize_learning_topic_text("什么是流水施工？") == ""
    assert normalize_learning_topic_text("指出钢结构施工高处作业安全防护方案中的不妥之处，并写出正确做法。") == ""


def test_canonical_learning_topic_label_is_the_cross_surface_topic_authority() -> None:
    assert canonical_learning_topic_label("流水施工") == "施工进度管理"
    assert canonical_learning_topic_label("防水工程") == "屋面与防水工程施工"
    assert canonical_learning_topic_label("施工现场布置塔吊时应考虑的因素还有哪些？") == ""
    assert canonical_learning_topic_label("专家论证程序") == ""


def test_normalize_learning_topic_text_filters_noise_but_keeps_real_exam_topics() -> None:
    assert normalize_learning_topic_text("施工现场临时用电") == "施工现场临时用电"
    assert normalize_learning_topic_text("防水工程") == "防水工程"
    assert normalize_learning_topic_text("专家论证程序") == "专家论证程序"

    assert normalize_learning_topic_text("讲义封底 扫码领取免费资料") == ""
    assert normalize_learning_topic_text("一级建造师建筑实务知识点归纳") == ""
    assert normalize_learning_topic_text("关注公众号领取课程二维码") == ""


def test_compiled_taxonomy_artifact_is_packaged() -> None:
    pyproject = tomllib.loads((Path(__file__).parents[3] / "pyproject.toml").read_text())

    package_data = pyproject["tool"]["setuptools"]["package-data"]

    assert "compiled/*.json" in package_data["deeptutor.services.taxonomy"]


def test_normalize_learning_topic_text_drops_non_textbook_noise():
    # The chat/home recommended-topic label authority must drop non-textbook noise (it feeds the
    # conversation page's recommended prompts).
    from deeptutor.services.taxonomy.learning_topic_resolver import normalize_learning_topic_text

    assert normalize_learning_topic_text("讲义封底免费听课资源") == ""
    assert normalize_learning_topic_text("扫码领取课程资料") == ""
    # real topics survive
    assert normalize_learning_topic_text("施工现场临时用电") == "施工现场临时用电"
    assert normalize_learning_topic_text("建设工程项目资源管理") == "建设工程项目资源管理"


def test_recommended_topic_drops_non_textbook_garbage_keeps_real_topics():
    # STANDING REQUIREMENT (no garbage in recommendations): non-textbook noise / book-title / meta-title
    # phrasings must NEVER be recommended, even when the LLM emits them; real exam topics still pass.
    from deeptutor.services.taxonomy.learning_topic_resolver import resolve_learning_topic_from_payload

    payload = {"question_stem": "雨季施工混凝土养护", "simple_explanation": "结合季节性施工判断。"}

    for junk in ["一级建造师建筑实务学习主题归纳", "讲义封底免费听课资源", "扫码领取课程资料",
                 "建筑实务知识点归纳", "学习方法与思维导图"]:
        assert resolve_learning_topic_from_payload(payload, llm_topic_inferer=lambda *_a, **_k: junk) is None

    # only an exact canonical chapter/section option is recommended (true canonical allowlist)
    out = resolve_learning_topic_from_payload(
        payload, llm_topic_inferer=lambda *_a, **_k: "工程招标投标与合同管理")
    assert out is not None and out.label == "工程招标投标与合同管理" and out.taxonomy_code


def test_resolver_branch1_miss_does_not_call_llm_twice() -> None:
    # Regression guard for the double-LLM-call bug (R3-HIGH):
    # When next_training_signal.focus is set (branch 1) and the LLM returns a non-canonical
    # pick, resolve_learning_topic_from_payload must return None immediately — it must NOT
    # fall through to branch 2 and call llm_topic_inferer a second time.
    call_count = [0]

    def counting_inferer(payload: dict, candidates: list) -> str:
        call_count[0] += 1
        return "非canonical自由文本"  # always off-canonical → _classify_to_canonical_option → None

    result = resolve_learning_topic_from_payload(
        {
            "next_training_signal": {"focus": "专家论证程序"},
            "question_stem": "关于工程专家论证程序的题目。",
        },
        llm_topic_inferer=counting_inferer,
    )
    assert result is None
    assert call_count[0] == 1, f"LLM called {call_count[0]} times; expected exactly 1"
