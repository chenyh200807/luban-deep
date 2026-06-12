"""RichLeaf workbench stage contracts.

This is the single schema registry for Nexus-like RichLeaf compiler workbench
outputs. It defines candidate-stage interoperability only; it does not grant
runtime default, release truth, official score, or learner memory write
authority.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RichLeafWorkbenchStageContract:
    name: str
    schema: str
    order: int
    claim_ceiling: str = "candidate_workbench_only"
    runtime_install_allowed: bool = False
    production_write_allowed: bool = False


RICH_LEAF_WORKBENCH_STAGE_CONTRACTS: tuple[RichLeafWorkbenchStageContract, ...] = (
    RichLeafWorkbenchStageContract("sample", "luban_rich_leaf_phase1_sample_manifest.v1", 10),
    RichLeafWorkbenchStageContract("skeleton", "luban_rich_leaf_skeleton_batch.v1", 20),
    RichLeafWorkbenchStageContract("source_gap", "luban_rich_leaf_source_gap_candidates.v1", 30),
    RichLeafWorkbenchStageContract("patches", "luban_rich_leaf_candidate_patch_batch.v1", 40),
    RichLeafWorkbenchStageContract("patch_audit", "luban_rich_leaf_patch_evidence_audit.v1", 50),
    RichLeafWorkbenchStageContract("rejected_feedback", "luban_rich_leaf_rejected_patch_feedback.v1", 60),
    RichLeafWorkbenchStageContract("semantic_packets", "luban_rich_leaf_semantic_audit_packets.v1", 70),
    RichLeafWorkbenchStageContract("source_evidence", "luban_rich_leaf_source_evidence_agent.v1", 80),
    RichLeafWorkbenchStageContract("semantic_queue", "luban_rich_leaf_semantic_audit_queue.v1", 90),
    RichLeafWorkbenchStageContract("review_shards", "luban_rich_leaf_semantic_review_shards.v1", 100),
    RichLeafWorkbenchStageContract("review_suggestions", "luban_rich_leaf_semantic_review_suggestions.v1", 110),
    RichLeafWorkbenchStageContract(
        "decision_validation", "luban_rich_leaf_semantic_review_decision_validation.v1", 120
    ),
    RichLeafWorkbenchStageContract("semantic_record", "luban_rich_leaf_semantic_evidence_audit_record.v1", 130),
    RichLeafWorkbenchStageContract("reviewed_candidates", "luban_rich_leaf_reviewed_candidate_batch.v1", 140),
    RichLeafWorkbenchStageContract(
        "runtime_supply_candidate", "luban_rich_leaf_runtime_supply_candidate_bundle.v1", 150
    ),
    RichLeafWorkbenchStageContract("runtime_supply_regression", "luban_rich_leaf_runtime_supply_regression.v1", 160),
    RichLeafWorkbenchStageContract("field_candidates", "luban_rich_leaf_field_candidate_batch.v1", 170),
    RichLeafWorkbenchStageContract("artifact_candidates", "luban_rich_leaf_artifact_candidate_batch.v1", 180),
    RichLeafWorkbenchStageContract("field_promotion_review", "luban_rich_leaf_field_promotion_review.v1", 190),
    RichLeafWorkbenchStageContract("context_pack_smoke", "luban_rich_leaf_context_pack_smoke.v1", 200),
    RichLeafWorkbenchStageContract(
        "fail_open_guard_diagnostic", "luban_rich_leaf_fail_open_guard_diagnostic.v1", 210
    ),
    RichLeafWorkbenchStageContract("context_pack_projection_ab", "luban_rich_leaf_context_pack_projection_ab.v1", 220),
    RichLeafWorkbenchStageContract("semantic_runtime_offline_ab", "luban_rich_leaf_semantic_runtime_offline_ab.v1", 230),
    RichLeafWorkbenchStageContract("semantic_runtime_nearline_ab", "luban_rich_leaf_semantic_runtime_nearline_ab.v1", 240),
    RichLeafWorkbenchStageContract(
        "semantic_runtime_live_ab_preflight", "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1", 250
    ),
    RichLeafWorkbenchStageContract(
        "semantic_runtime_live_ab", "luban_rich_leaf_semantic_runtime_live_ab.v1", 260, "live_shadow_only"
    ),
    RichLeafWorkbenchStageContract(
        "semantic_runtime_near_live_smoke", "luban_rich_leaf_semantic_runtime_near_live_smoke.v1", 270
    ),
    RichLeafWorkbenchStageContract(
        "semantic_runtime_near_live_shadow_ab", "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1", 280
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_work_orders", "luban_rich_leaf_shadow_residual_work_orders.v1", 285
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_review_packets", "luban_rich_leaf_shadow_residual_review_packets.v1", 286
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_review_decision_validation",
        "luban_rich_leaf_shadow_residual_review_decision_validation.v1",
        287,
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_review_decision_seed",
        "luban_rich_leaf_shadow_residual_review_decision_seed.v1",
        288,
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_review_decisions",
        "luban_rich_leaf_shadow_residual_review_decisions.v1",
        289,
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_audit_record",
        "luban_rich_leaf_shadow_residual_audit_record.v1",
        290,
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_guard_patch_plan",
        "luban_rich_leaf_shadow_residual_guard_patch_plan.v1",
        291,
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_guard_review_packets",
        "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
        292,
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_guard_review_decisions",
        "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
        293,
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_guard_review_decision_validation",
        "luban_rich_leaf_shadow_residual_guard_review_decision_validation.v1",
        294,
    ),
    RichLeafWorkbenchStageContract(
        "shadow_residual_guard_audit_record",
        "luban_rich_leaf_shadow_residual_guard_audit_record.v1",
        295,
    ),
    RichLeafWorkbenchStageContract(
        "learning_evidence_candidate_bridge", "luban_rich_leaf_learning_evidence_candidate_bridge.v1", 296
    ),
    RichLeafWorkbenchStageContract("pcp_nba_candidate_projection", "luban_rich_leaf_pcp_nba_candidate_projection.v1", 300),
    RichLeafWorkbenchStageContract(
        "test_learner_sandbox_readback_gate", "luban_rich_leaf_test_learner_sandbox_readback_gate.v1", 310
    ),
    RichLeafWorkbenchStageContract(
        "authorized_writeback_preflight", "luban_rich_leaf_authorized_writeback_preflight.v1", 320
    ),
    RichLeafWorkbenchStageContract(
        "test_learner_writeback_authorization_package",
        "luban_rich_leaf_test_learner_writeback_authorization_package.v1",
        330,
    ),
    RichLeafWorkbenchStageContract(
        "test_learner_writeback_dry_run_manifest",
        "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1",
        340,
    ),
    RichLeafWorkbenchStageContract(
        "test_learner_writeback_execution_gate",
        "luban_rich_leaf_test_learner_writeback_execution_gate.v1",
        350,
    ),
    RichLeafWorkbenchStageContract(
        "learning_evidence_current_standard_compat_audit",
        "luban_rich_leaf_learning_evidence_current_standard_compat_audit.v1",
        355,
    ),
    RichLeafWorkbenchStageContract(
        "external_source_closure",
        "luban_rich_leaf_external_source_closure.v1",
        357,
    ),
    RichLeafWorkbenchStageContract("weak", "luban_rich_leaf_weak_source_refinement.v1", 360),
)

RICH_LEAF_WORKBENCH_STAGE_SCHEMAS: dict[str, str] = {
    contract.name: contract.schema for contract in RICH_LEAF_WORKBENCH_STAGE_CONTRACTS
}


def ordered_rich_leaf_workbench_stage_names() -> list[str]:
    return [contract.name for contract in sorted(RICH_LEAF_WORKBENCH_STAGE_CONTRACTS, key=lambda item: item.order)]


def get_rich_leaf_workbench_schema(stage_name: str) -> str:
    try:
        return RICH_LEAF_WORKBENCH_STAGE_SCHEMAS[stage_name]
    except KeyError as exc:
        raise KeyError(f"unknown RichLeaf workbench stage: {stage_name}") from exc
