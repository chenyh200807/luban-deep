"""Scoring-point enrichment compile (v3.1.1 -> v3.2 candidate pack).

Hard constraint under test: 采分点 + required_terms 必须带教材原文溯源 —
no textbook provenance, no point (M35 migration requires a textbook quote +
chunk_id; chunk-derived candidates require every required_term to appear
verbatim in the chunk's content_markdown)."""
from __future__ import annotations

import json
from typing import Any

from scripts.run_luban_rich_leaf_scoring_point_compile import (
    attach_scoring_points,
    derive_chunk_scoring_points,
    load_m35_scoring_points,
)

CHUNK_TEXT = "施工总进度计划的内容包括：编制说明，施工总进度计划表（图），资源需要量及供应平衡表等。"


def _golden() -> dict[str, Any]:
    return {
        "cases": [
            {
                "case_id": "Q1",
                "question_node": "1A433000",
                "gold_scoring_points": [
                    {"point_id": "P1", "label": "列举施工总进度计划内容", "max_score": 5},
                    {"point_id": "P2", "label": "无教材溯源的点", "max_score": 2},
                ],
            }
        ]
    }


def _typed_rows() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "Q1",
            "point_id": "P1",
            "typed_policy": {
                "policy_type": "list_rule",
                "required_terms": ["编制说明", "资源需要量及供应平衡表"],
                "evidence_policy": {
                    "source_authority": "textbook",
                    "chunk_id": "1A433000_059_0089",
                    "textbook_quote": "施工总进度计划表（图",
                },
            },
        },
        # P2: no textbook evidence -> must NOT become a scoring point
        {"case_id": "Q1", "point_id": "P2", "typed_policy": {"policy_type": "semantic_allowed"}},
    ]


def _chunk(chunk_id: str = "1A433000_059_0089") -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "content_markdown": CHUNK_TEXT,
        "assessment": {
            "generated_question": "施工总进度计划应包含哪些内容？",
            "grading_keywords": ["编制说明", "不在原文中的术语"],
        },
        "knowledge_cards": [
            {
                "card_title": "施工总进度计划内容",
                "card_content": "编制说明、计划表（图）、资源平衡表。",
                "keywords": ["资源需要量及供应平衡表", "幻觉关键词"],
                "key_numbers": [],
            },
            # card with zero in-text terms -> dropped (no provenance, no point)
            {"card_title": "无溯源卡", "card_content": "x", "keywords": ["完全不存在"], "key_numbers": []},
        ],
    }


def _pack() -> dict[str, Any]:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "version": "v3.1.1_frozen_v11_quarantine_annotated",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "safety": {
            "official_score_allowed": False,
            "canonical_truth_written": False,
            "release_truth_claimed": False,
        },
        "quarantine": {"quarantine_candidate_unit_ids": []},
        "runtime_token_pack_units": [
            {
                "unit_id": "u1",
                "leaf_id": "1A433000-B017",
                "leaf_name_path": "路径 > 施工总进度计划",
                "compiled_context": {"concepts": ["c"], "rules": [], "exam_patterns": [], "teaching_cards": []},
                "source_lane": "source_truth",
                "source_ref": {"chunk_id": "1A433000_059_0089", "source_lane": "textbook"},
            },
            {
                "unit_id": "u2",
                "leaf_id": "1A999000-B001",
                "leaf_name_path": "路径 > 无关叶",
                "compiled_context": {"concepts": ["c"], "rules": [], "exam_patterns": [], "teaching_cards": []},
                "source_lane": "source_truth",
                "source_ref": {"chunk_id": "no_such_chunk", "source_lane": "textbook"},
            },
        ],
    }


def test_m35_migration_requires_textbook_provenance() -> None:
    by_chunk, accounting = load_m35_scoring_points(_golden(), _typed_rows())
    assert set(by_chunk) == {"1A433000_059_0089"}
    points = by_chunk["1A433000_059_0089"]
    assert len(points) == 1
    point = points[0]
    assert point["source"] == "m35_artifact"
    assert point["point_id"] == "m35:Q1:P1"
    assert point["required_terms"] == ["编制说明", "资源需要量及供应平衡表"]
    assert point["max_score"] == 5
    assert point["provenance"]["source_authority"] == "textbook"
    assert point["provenance"]["quote"] == "施工总进度计划表（图"
    assert accounting["skipped_no_textbook_provenance"] == 1


def test_derived_points_drop_terms_not_verbatim_in_chunk() -> None:
    points = derive_chunk_scoring_points(_chunk())
    sources = [p["source"] for p in points]
    assert sources == ["chunk_assessment", "knowledge_card"]
    assessment = points[0]
    assert assessment["required_terms"] == ["编制说明"]  # 不在原文中的术语 dropped
    assert assessment["provenance"]["chunk_id"] == "1A433000_059_0089"
    assert "编制说明" in assessment["provenance"]["quote"]
    card = points[1]
    assert card["required_terms"] == ["资源需要量及供应平衡表"]  # 幻觉关键词 dropped
    # 无溯源卡 has zero in-text terms -> no point at all
    assert all("无溯源卡" not in str(p.get("statement")) for p in points)


def test_derived_points_empty_when_nothing_traces() -> None:
    chunk = {
        "chunk_id": "c1",
        "content_markdown": "完全无关的文本。",
        "assessment": {"generated_question": "问题？", "grading_keywords": ["不存在"]},
        "knowledge_cards": [],
    }
    assert derive_chunk_scoring_points(chunk) == []


def test_attach_builds_v32_without_mutating_original() -> None:
    pack = _pack()
    original = json.loads(json.dumps(pack))
    by_chunk, _ = load_m35_scoring_points(_golden(), _typed_rows())
    chunk_lookup = {"1A433000_059_0089": _chunk()}
    new_pack, stats = attach_scoring_points(
        pack, m35_by_chunk=by_chunk, chunk_lookup=chunk_lookup, pack_version="v3.2_test"
    )
    assert pack == original  # immutability
    assert new_pack["version"] == "v3.2_test"
    assert new_pack["schema"] == pack["schema"]
    units = {u["unit_id"]: u for u in new_pack["runtime_token_pack_units"]}
    sp = units["u1"]["compiled_context"]["scoring_points"]
    assert [p["source"] for p in sp] == ["m35_artifact", "chunk_assessment", "knowledge_card"]
    # m35 quote verified against the mapped chunk text
    assert sp[0]["provenance"]["quote_verified"] is True
    # unit with no mapped chunk and no m35 points gets NO scoring_points key
    assert "scoring_points" not in units["u2"]["compiled_context"]
    assert stats["units_with_scoring_points"] == 1
    assert stats["points_by_source"] == {"m35_artifact": 1, "chunk_assessment": 1, "knowledge_card": 1}
    assert stats["m35_points_attached"] == 1
    # candidate-only discipline is preserved on the new pack
    assert new_pack["safety"]["official_score_allowed"] is False
    summary = new_pack["scoring_points_summary"]
    assert summary["units_with_scoring_points"] == 1
