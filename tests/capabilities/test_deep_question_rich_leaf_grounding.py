"""deep_question grading-grounding renderer: rich_leaf_context is additive and fail-open.

Contract-guard registered (capability domain): packs WITHOUT the rich_leaf_context key must render
byte-identically to the legacy four-source grounding; packs WITH it render the rich block first;
malformed rich payloads degrade silently to the legacy rendering.
"""
from __future__ import annotations

import copy

import deeptutor.capabilities.deep_question as dq


def _legacy_pack() -> dict:
    return {
        "authority": "luban_general_knowledge_context",
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,
        "leaf_name_path": "建筑工程技术 > 建筑高度分类",
        "sources": {
            "textbook": [{"text_preview": "建筑高度大于27m的住宅为高层住宅", "provenance": "2026教材"}],
            "standard": [{"text_preview": "民用建筑设计统一标准 GB50352", "provenance": "规范"}],
            "lecture": [],
            "question": [],
        },
    }


def _rich_block() -> dict:
    return {
        "authority": "luban_rich_leaf_context",
        "leaf_id": "1A411011-B054",
        "leaf_name_path": "建筑工程技术 > 建筑设计 > 建筑物的构成",
        "official_score_allowed": False,
        "compiled_context": {
            "concepts": ["### 建筑物的构成\n\n建筑物由结构体系、围护体系和设备体系组成。"],
            "rules": ['{"id": "R1", "description": "三大体系组成。", "severity": "informative"}'],
            "exam_patterns": ['{"id": "EP1", "description": "三大构成体系？", "grading_keywords": ["结构体系"]}'],
            "teaching_cards": ['{"id": "TC1", "title": "三大体系", "content": "结构、围护、设备。"}'],
        },
    }


def test_pack_without_rich_key_renders_byte_identical_legacy_grounding() -> None:
    pack = _legacy_pack()
    text = dq._format_general_knowledge_grounding(pack)
    assert "建筑高度大于27m" in text and "GB50352" in text
    assert "富叶" not in text and "rich_leaf" not in text


def test_rich_leaf_context_renders_first_and_keeps_non_official_marker() -> None:
    pack = _legacy_pack()
    pack["rich_leaf_context"] = _rich_block()
    text = dq._format_general_knowledge_grounding(pack)
    assert "富叶编译上下文" in text
    assert "不得作为官方判分依据" in text
    assert text.index("富叶编译上下文") < text.index("建筑高度大于27m")  # rich block precedes source items
    assert "结构体系" in text and "教学卡" in text


def test_malformed_rich_key_fails_open_to_legacy_rendering() -> None:
    base = dq._format_general_knowledge_grounding(_legacy_pack())
    for bad in ("garbage", 42, {"compiled_context": "nope"}, {"compiled_context": {}}):
        pack = _legacy_pack()
        pack["rich_leaf_context"] = copy.deepcopy(bad)
        assert dq._format_general_knowledge_grounding(pack) == base


def test_rich_leaf_contexts_list_renders_multi_blocks_primary_first() -> None:
    primary = _rich_block()
    supplement = copy.deepcopy(_rich_block())
    supplement["leaf_id"] = "1A411011-B099"
    supplement["leaf_name_path"] = "建筑工程技术 > 防水工程 > 屋面防水"
    pack = _legacy_pack()
    pack["rich_leaf_contexts"] = [primary, supplement]
    text = dq._format_general_knowledge_grounding(pack)
    assert text.count("富叶编译上下文") == 2
    assert text.index("1A411011-B054") < text.index("1A411011-B099")  # primary block first
    assert text.index("1A411011-B099") < text.index("建筑高度大于27m")  # all rich blocks precede source items


def test_malformed_rich_contexts_list_fails_open_to_legacy_rendering() -> None:
    base = dq._format_general_knowledge_grounding(_legacy_pack())
    for bad in ("garbage", 42, ["garbage", 42], [{"compiled_context": {}}], []):
        pack = _legacy_pack()
        pack["rich_leaf_contexts"] = copy.deepcopy(bad)
        assert dq._format_general_knowledge_grounding(pack) == base
