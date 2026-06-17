"""M34 Task 3: general knowledge teaching packs render into non-official grounding text."""
from __future__ import annotations

import deeptutor.capabilities.deep_question as dq


def test_grounding_text_includes_four_sources_and_non_official_marker() -> None:
    pack = {
        "authority": "luban_general_knowledge_context",
        "tier": "teaching_context_not_answer_key",
        "official_score_allowed": False,
        "leaf_name_path": "建筑工程技术 > 建筑高度分类",
        "sources": {
            "textbook": [{"text_preview": "建筑高度大于27m的住宅为高层住宅", "provenance": "2026教材"}],
            "standard": [{"text_preview": "民用建筑设计统一标准 GB50352", "provenance": "规范"}],
            "lecture": [{"text_preview": "讲义：高度界定要点", "provenance": "讲义"}],
            "question": [{"text_preview": "真题：判断高层住宅", "provenance": "真题"}],
        },
    }
    text = dq._format_general_knowledge_grounding(pack)
    assert "建筑高度大于27m" in text
    assert "GB50352" in text
    assert "讲义" in text
    assert "真题" in text
    assert ("非官方" in text) or ("teaching" in text.lower()) or ("不得作为官方" in text)


def test_grounding_text_empty_pack_returns_empty() -> None:
    assert dq._format_general_knowledge_grounding(None) == ""
    assert dq._format_general_knowledge_grounding({"sources": {}}) == ""
