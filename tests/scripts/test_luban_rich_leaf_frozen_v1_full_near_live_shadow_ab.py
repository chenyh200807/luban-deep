from __future__ import annotations

import json

from scripts.run_luban_rich_leaf_frozen_v1_full_near_live_shadow_ab import (
    run_frozen_v1_full_near_live_shadow_ab,
)


def _unit(unit_id: str, leaf_id: str, *, concept: str, keyword: str) -> dict:
    return {
        "unit_id": unit_id,
        "leaf_id": leaf_id,
        "leaf_name_path": f"根 > 分支 > {concept[:4]}",
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
        "confidence": "high",
        "source_ref": {
            "source_path": "教材/示例.json",
            "span_hash": "deadbeef",
            "source_lane": "textbook",
        },
        "compiled_context": {
            "concepts": [concept],
            "rules": [
                json.dumps(
                    {"id": "R1", "description": concept, "source_refs": ["ref1"]},
                    ensure_ascii=False,
                )
            ],
            "exam_patterns": [
                json.dumps(
                    {
                        "id": "EP1",
                        "description": f"{keyword}是什么？",
                        "grading_keywords": [keyword],
                        "source_refs": ["ref1"],
                    },
                    ensure_ascii=False,
                )
            ],
            "teaching_cards": [
                json.dumps({"id": "TC1", "title": concept[:6], "content": concept}, ensure_ascii=False)
            ],
        },
    }


def _pack(units: list[dict]) -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "version": "v3.0_test",
        "runtime_token_pack_units": units,
        "summary": {"unit_count": len(units)},
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def test_recomputed_outcomes_pass_with_four_arms() -> None:
    pack = _pack(
        [
            _unit("u1", "1A1-01", concept="建筑物由结构体系围护体系设备体系组成", keyword="结构体系"),
            _unit("u2", "1A1-02", concept="混凝土强度等级按立方体抗压强度标准值划分", keyword="强度等级"),
        ]
    )
    report = run_frozen_v1_full_near_live_shadow_ab(runtime_token_pack=pack)

    assert report["verdict"] == "PASS_V23_NEAR_LIVE_SHADOW_AB"
    assert report["schema"] == "luban_rich_leaf_v23_near_live_shadow_ab.v1"
    assert report["summary"]["case_count"] == 2
    assert report["summary"]["arm_count"] == 4
    arms = {row["arm"] for row in report["rows"]}
    assert arms == {
        "current_rag_proxy",
        "legacy_keyword_projection",
        "rich_leaf_v23_context",
        "artifact_first_guard_proxy",
    }
    assert report["summary"]["rich_leaf_accuracy_rate"] == 1.0
    # Bridge contract: every rich row answerable + matched + cited, no fail-open.
    rich_rows = [row for row in report["rows"] if row["arm"] == "rich_leaf_v23_context"]
    assert all(
        row["answerable"] and row["matches_expected"] and row["evidence_cited"] and not row["fail_open"]
        for row in rich_rows
    )
    # The honest gap is closed: outcomes are recomputed, not inherited.
    assert report["rerun_lineage"]["outcomes_inherited_from_v23_proxy"] is False
    assert (
        report["rerun_lineage"]["closes_not_exercised"]
        == "frozen_axis_near_live_rerun_with_recompiled_context"
    )
    assert report["summary"]["provider_call_count"] == 0
    assert report["quality_claim_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_unit_without_knowledge_text_blocks_verdict() -> None:
    broken = _unit("u1", "1A1-01", concept="占位", keyword="占位")
    broken["compiled_context"] = {"concepts": [], "exam_patterns": []}
    pack = _pack([broken])

    report = run_frozen_v1_full_near_live_shadow_ab(runtime_token_pack=pack)

    assert report["verdict"] == "FAIL_FROZEN_V1_NEAR_LIVE_SHADOW_AB"
    assert any(blocker.startswith("unit_without_knowledge_text") for blocker in report["blockers"])


def test_runtime_install_flag_blocks_verdict() -> None:
    pack = _pack([_unit("u1", "1A1-01", concept="建筑物由结构体系组成", keyword="结构体系")])
    pack["classification"]["runtime_install_allowed"] = True

    report = run_frozen_v1_full_near_live_shadow_ab(runtime_token_pack=pack)

    assert report["verdict"] == "FAIL_FROZEN_V1_NEAR_LIVE_SHADOW_AB"
    assert "runtime_token_pack:classification.runtime_install_allowed_not_false" in report["blockers"]
