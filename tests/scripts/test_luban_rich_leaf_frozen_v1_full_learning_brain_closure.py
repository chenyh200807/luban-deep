from __future__ import annotations

from scripts.run_luban_rich_leaf_frozen_v1_full_learning_brain_closure import (
    build_frozen_v1_full_learning_brain_closure,
    check_live_evidence_consistency,
    reconcile_taxonomy_gaps,
)


def _safe_classification(**extra: object) -> dict:
    return {
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
        "release_truth_claimed": False,
        **extra,
    }


def _safe_safety(**extra: object) -> dict:
    return {
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "installed_runtime_supply": False,
        "production_write_count": 0,
        "release_truth_claimed": False,
        **extra,
    }


def _runtime_token_pack() -> dict:
    return {
        "schema": "luban_rich_leaf_runtime_token_pack.v2.3",
        "status": "candidate_ready_for_shadow_ab_full_accounted",
        "version": "v3.0_test",
        "runtime_token_pack_units": [
            {"unit_id": "u1", "leaf_id": "1A1-01"},
            {"unit_id": "u2", "leaf_id": "1A9-G01"},
        ],
        "summary": {"unit_count": 2, "evidence_leaf_count": 2, "unresolved_count": 0},
        "classification": _safe_classification(),
        "safety": _safe_safety(),
    }


def _near_live_ab(*, rich: float = 1.0, rag: float = 0.2) -> dict:
    return {
        "schema": "luban_rich_leaf_v23_near_live_shadow_ab.v1",
        "verdict": "PASS_V23_NEAR_LIVE_SHADOW_AB",
        "summary": {"case_count": 2, "provider_call_count": 0, "live_runtime_executed": False},
        "effect_table": [
            {"arm": "current_rag_proxy", "accuracy_rate": rag},
            {"arm": "rich_leaf_v23_context", "accuracy_rate": rich},
        ],
        "rerun_lineage": {"outcomes_inherited_from_v23_proxy": False},
        "classification": _safe_classification(),
        "safety": _safe_safety(),
    }


def _bridge() -> dict:
    return {
        "schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
        "verdict": "PASS",
        "summary": {"candidate_event_count": 2, "learner_memory_write_count": 0},
        "classification": _safe_classification(),
        "safety": _safe_safety(learner_memory_write_count=0, canonical_learner_truth_written=False),
    }


def _projection() -> dict:
    return {
        "schema": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
        "verdict": "PASS",
        "summary": {"top_claim_candidate_count": 2, "next_action_candidate_count": 1},
        "classification": _safe_classification(),
        "safety": _safe_safety(
            learner_memory_write_count=0,
            canonical_learner_truth_written=False,
            personalization_context_pack_readback_count=0,
            training_intent_write_count=0,
            next_best_action_write_count=0,
        ),
    }


def _sandbox_gate() -> dict:
    return {
        "schema": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
        "verdict": "PASS",
        "summary": {
            "candidate_event_count": 2,
            "sandbox_event_write_count": 2,
            "sandbox_readback_event_count": 2,
            "synthesis_observed_candidate_count": 0,
            "synthesis_compiled_object_count": 0,
            "synthesis_candidate_observation_count": 2,
        },
        "classification": _safe_classification(),
        "safety": _safe_safety(learner_memory_write_count=0, canonical_learner_truth_written=False),
    }


def _live_ab(*, rich: float = 0.94, rag: float = 0.47) -> dict:
    return {
        "schema": "luban_rich_leaf_frozen_v1_live_ab.v1",
        "verdict": "PASS_FROZEN_V1_LIVE_PROVIDER_SHADOW_AB",
        "quality_claim_allowed": False,
        "sample_seed": 20260613,
        "summary": {"sample_count": 100, "provider_call_count": 400, "total_tokens": 275476},
        "arms": [
            {"arm": "current_rag_projection_live", "accuracy_rate": rag},
            {"arm": "rich_leaf_context_live", "accuracy_rate": rich},
        ],
        "classification": _safe_classification(),
        "safety": _safe_safety(),
    }


def _residual_work_orders() -> dict:
    return {
        "schema": "luban_rich_leaf_frozen_v1_live_residual_work_orders.v1",
        "verdict": "PASS_FROZEN_V1_LIVE_RESIDUAL_WORK_ORDERS_READY",
        "summary": {"work_order_count": 17},
        "classification": _safe_classification(),
        "safety": _safe_safety(),
    }


def _v23_pack_with_gap() -> dict:
    return {
        "non_runtime_accounted_items": [
            {
                "item_id": "unresolved_accounting:abc",
                "parent_unit_id": "rtp2_p1",
                "classification": "taxonomy_gap_extension_candidate",
                "unresolved_reason": "上下文为工期费用优化与赶工费计算，候选叶子均不匹配。",
                "suggested_gap_family": "schedule",
            }
        ]
    }


def _v2_pack() -> dict:
    return {
        "runtime_token_pack_units": [
            {
                "unit_id": "rtp2_p1",
                "compiled_context": {"concepts": ["工期费用优化 赶工费 直接费 间接费 网络计划"]},
            }
        ]
    }


def _taxonomy() -> dict:
    return {
        "nodes_by_code": {
            "1A9-G01": {
                "code": "1A9-G01",
                "name": "工期费用优化与赶工费计算",
                "keywords": ["工期费用优化", "赶工费", "直接费", "间接费"],
            },
            "1A1-01": {"code": "1A1-01", "name": "普通叶", "keywords": ["普通"]},
        }
    }


def _build(**overrides: dict) -> dict:
    kwargs = {
        "runtime_token_pack": _runtime_token_pack(),
        "near_live_ab": _near_live_ab(),
        "bridge": _bridge(),
        "projection": _projection(),
        "sandbox_gate": _sandbox_gate(),
        "live_ab": _live_ab(),
        "live_residual_work_orders": _residual_work_orders(),
        "v23_runtime_token_pack": _v23_pack_with_gap(),
        "v2_runtime_token_pack": _v2_pack(),
        "taxonomy": _taxonomy(),
    }
    kwargs.update(overrides)
    return build_frozen_v1_full_learning_brain_closure(**kwargs)


def test_closure_weak_go_resolves_gap_and_live_not_exercised() -> None:
    report = _build()

    assert report["blockers"] == []
    assert report["verdict"] == "WEAK_GO_GRADING_TO_BRAIN_CANDIDATE__NO_GO_CANONICAL_LEARNER_TRUTH"
    assert "canonical_taxonomy_extension_for_23_gaps" not in report["not_exercised"]
    assert "live_provider_v23_four_arm_ab" not in report["not_exercised"]
    assert "compiler_feedback_from_live_residuals" not in report["not_exercised"]
    # Canonical learner truth lanes must remain not exercised.
    assert "canonical_learner_truth_write" in report["not_exercised"]
    assert "runtime_default_install" in report["not_exercised"]
    assert report["summary"]["leaf_scoped_runtime_units"] == 2
    assert report["summary"]["candidate_event_count"] == 2
    assert report["summary"]["gap_items_matched_in_v30_runtime"] == 1
    assert report["summary"]["gap_items_unresolved"] == 0
    assert report["gap_reconciliation"]["all_gaps_accounted"] is True
    assert report["live_evidence_consistency"]["conflict"] is False
    assert report["quality_claim_allowed"] is False


def test_live_conflict_blocks_closure() -> None:
    report = _build(live_ab=_live_ab(rich=0.30, rag=0.47))

    assert "live_evidence_conflict_with_near_live_rerun:reshoot_required" in report["blockers"]
    assert report["verdict"] == "FAIL_SAFETY_OR_CONTRACT"
    assert "live_provider_v23_four_arm_ab" in report["not_exercised"]


def test_inherited_outcomes_block_closure() -> None:
    stale = _near_live_ab()
    stale["rerun_lineage"] = {"outcomes_inherited_from_v23_proxy": True}
    report = _build(near_live_ab=stale)

    assert "near_live_ab:outcomes_not_recomputed_from_v30_context" in report["blockers"]


def test_gap_left_unmatched_keeps_not_exercised() -> None:
    taxonomy = {"nodes_by_code": {"1A1-01": {"code": "1A1-01", "name": "普通叶", "keywords": ["普通"]}}}
    report = _build(taxonomy=taxonomy)

    assert report["gap_reconciliation"]["all_gaps_accounted"] is False
    assert "canonical_taxonomy_extension_for_23_gaps" in report["not_exercised"]


def test_consistency_check_direction() -> None:
    consistent = check_live_evidence_consistency(near_live_ab=_near_live_ab(), live_ab=_live_ab())
    assert consistent["conflict"] is False
    flipped = check_live_evidence_consistency(
        near_live_ab=_near_live_ab(rich=0.1, rag=0.9), live_ab=_live_ab()
    )
    assert flipped["conflict"] is True


def test_reconcile_marks_non_knowledge_item() -> None:
    v23 = _v23_pack_with_gap()
    v23["non_runtime_accounted_items"][0]["unresolved_reason"] = "源文件为招投标章节的考情分析，备考策略。"
    v23["non_runtime_accounted_items"][0]["parent_unit_id"] = "missing"
    result = reconcile_taxonomy_gaps(
        v23_runtime_token_pack=v23,
        v2_runtime_token_pack=_v2_pack(),
        taxonomy=_taxonomy(),
        runtime_token_pack=_runtime_token_pack(),
    )
    assert result["rows"][0]["resolution"] == "non_knowledge_adjudicated_no_leaf_minted"
    assert result["all_gaps_accounted"] is True
