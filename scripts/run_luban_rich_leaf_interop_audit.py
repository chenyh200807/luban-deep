#!/usr/bin/env python3
"""Audit RichLeaf workbench artifacts against the interoperability standard."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.rich_leaf_artifacts import validate_rich_leaf_artifact
from deeptutor.services.construction_grading.rich_leaf_workbench_contracts import RICH_LEAF_WORKBENCH_STAGE_SCHEMAS


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE = REPO / "artifacts/luban_grading_artifacts/rich_leaf_phase1_sampler_20260611/sample_manifest.json"
DEFAULT_SKELETON = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_skeleton_candidates_20260611/rich_leaf_skeleton_candidates.json"
)
DEFAULT_SOURCE_GAP = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_source_gap_candidates_20260611/source_gap_candidates.json"
)
DEFAULT_PATCHES = REPO / "artifacts/luban_grading_artifacts/rich_leaf_candidate_patches_20260611/candidate_patches.json"
DEFAULT_PATCH_AUDIT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_patch_evidence_audit_20260611/patch_evidence_audit.json"
)
DEFAULT_REJECTED_FEEDBACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_rejected_patch_feedback_20260612/rejected_patch_feedback_work_orders.json"
)
DEFAULT_SEMANTIC_PACKETS = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_packets_20260612/semantic_audit_packets.json"
)
DEFAULT_SOURCE_EVIDENCE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_source_evidence_agent_20260612/source_evidence_agent_candidates.json"
)
DEFAULT_SEMANTIC_QUEUE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_queue_20260612/semantic_audit_queue.json"
)
DEFAULT_SEMANTIC_RECORD = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_evidence_audit_record_20260612/semantic_evidence_audit_record.json"
)
DEFAULT_REVIEW_SHARDS = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_shards_20260612/semantic_review_shards_manifest.json"
)
DEFAULT_REVIEW_SUGGESTIONS = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_suggestions_20260612/semantic_review_suggestions.json"
)
DEFAULT_DECISION_VALIDATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decision_validation_20260612/semantic_review_decision_validation.json"
)
DEFAULT_REVIEWED_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_reviewed_candidates_20260612/reviewed_rich_leaf_candidates.json"
)
DEFAULT_RUNTIME_SUPPLY_CANDIDATE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_runtime_supply_candidate_20260612/rich_leaf_runtime_supply_candidate.json"
)
DEFAULT_RUNTIME_SUPPLY_REGRESSION = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_runtime_supply_regression_20260612/runtime_supply_regression.json"
)
DEFAULT_FIELD_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_candidates_20260612/rich_leaf_field_candidates.json"
)
DEFAULT_ARTIFACT_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_artifact_candidates_20260612/rich_leaf_artifact_candidates.json"
)
DEFAULT_FIELD_PROMOTION_REVIEW = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json"
)
DEFAULT_CONTEXT_PACK_SMOKE = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_context_pack_smoke_20260612/context_pack_smoke.json"
)
DEFAULT_FAIL_OPEN_GUARD_DIAGNOSTIC = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_fail_open_guard_diagnostic_20260612/fail_open_guard_diagnostic.json"
)
DEFAULT_CONTEXT_PACK_PROJECTION_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_context_pack_projection_ab_20260612/context_pack_projection_ab.json"
)
DEFAULT_SEMANTIC_RUNTIME_OFFLINE_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_offline_ab_20260612/semantic_runtime_offline_ab.json"
)
DEFAULT_SEMANTIC_RUNTIME_NEARLINE_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_nearline_ab_20260612/semantic_runtime_nearline_ab.json"
)
DEFAULT_SEMANTIC_RUNTIME_LIVE_AB_PREFLIGHT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_live_ab_preflight_20260612/live_ab_preflight.json"
)
DEFAULT_SEMANTIC_RUNTIME_LIVE_AB = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_live_ab_20260612/semantic_runtime_live_ab.json"
)
DEFAULT_SEMANTIC_RUNTIME_NEAR_LIVE_SMOKE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_smoke_20260612/near_live_smoke.json"
)
DEFAULT_SEMANTIC_RUNTIME_NEAR_LIVE_SHADOW_AB = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_shadow_ab_20260612/near_live_shadow_ab.json"
)
DEFAULT_SHADOW_RESIDUAL_WORK_ORDERS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_work_orders_20260612/shadow_residual_work_orders.json"
)
DEFAULT_SHADOW_RESIDUAL_REVIEW_PACKETS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_packets_20260612/shadow_residual_review_packets.json"
)
DEFAULT_SHADOW_RESIDUAL_REVIEW_DECISION_VALIDATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_validation_20260612/shadow_residual_review_decision_validation.json"
)
DEFAULT_SHADOW_RESIDUAL_REVIEW_DECISION_SEED = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_seed_20260612/shadow_residual_review_decision_seed.json"
)
DEFAULT_SHADOW_RESIDUAL_REVIEW_DECISIONS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decisions_20260612/ai_council_shadow_review_decisions.json"
)
DEFAULT_SHADOW_RESIDUAL_AUDIT_RECORD = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_audit_record_20260612/shadow_residual_audit_record.json"
)
DEFAULT_SHADOW_RESIDUAL_GUARD_PATCH_PLAN = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_patch_plan_20260612/shadow_residual_guard_patch_plan.json"
)
DEFAULT_SHADOW_RESIDUAL_GUARD_REVIEW_PACKETS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_packets_20260612/shadow_residual_guard_review_packets.json"
)
DEFAULT_SHADOW_RESIDUAL_GUARD_REVIEW_DECISIONS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_decisions_20260612/shadow_residual_guard_review_decisions.json"
)
DEFAULT_SHADOW_RESIDUAL_GUARD_REVIEW_DECISION_VALIDATION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_decision_validation_20260612/shadow_residual_guard_review_decision_validation.json"
)
DEFAULT_SHADOW_RESIDUAL_GUARD_AUDIT_RECORD = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_audit_record_20260612/shadow_residual_guard_audit_record.json"
)
DEFAULT_LEARNING_EVIDENCE_CANDIDATE_BRIDGE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_candidate_bridge_20260612/learning_evidence_candidate_bridge.json"
)
DEFAULT_PCP_NBA_CANDIDATE_PROJECTION = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_pcp_nba_candidate_projection_20260612/pcp_nba_candidate_projection.json"
)
DEFAULT_TEST_LEARNER_SANDBOX_READBACK_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_sandbox_readback_gate_20260612/test_learner_sandbox_readback_gate.json"
)
DEFAULT_AUTHORIZED_WRITEBACK_PREFLIGHT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_authorized_writeback_preflight_20260612/authorized_writeback_preflight.json"
)
DEFAULT_TEST_LEARNER_WRITEBACK_AUTHORIZATION_PACKAGE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_authorization_package_20260612/test_learner_writeback_authorization_package.json"
)
DEFAULT_TEST_LEARNER_WRITEBACK_DRY_RUN_MANIFEST = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_dry_run_manifest_20260612/test_learner_writeback_dry_run_manifest.json"
)
DEFAULT_TEST_LEARNER_WRITEBACK_EXECUTION_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_execution_gate_20260612/test_learner_writeback_execution_gate.json"
)
DEFAULT_LEARNING_EVIDENCE_CURRENT_STANDARD_COMPAT_AUDIT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_current_standard_compat_audit_20260612/current_standard_compat_audit.json"
)
DEFAULT_EXTERNAL_SOURCE_CLOSURE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_external_source_closure_20260612/external_source_closure.json"
)
DEFAULT_WEAK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_weak_source_refinement_20260611/weak_source_refinement_work_orders.json"
)
DEFAULT_OUTPUT = REPO / "artifacts/luban_grading_artifacts/rich_leaf_interop_audit_20260611/interop_audit.json"

EXPECTED_SCHEMAS = RICH_LEAF_WORKBENCH_STAGE_SCHEMAS
KNOWLEDGE_FIELD_FAMILIES = {
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "negative_evidence",
    "teaching_cards",
}
SOURCE_BACKED_LANES = {"textbook", "standard", "lecture"}
VALID_SOURCE_CORPUS_LANES = {"textbook", "standard", "lecture", "question"}
SOURCE_BACKED_PROMOTION_FAMILIES = {
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "teaching_cards",
}
ALLOWED_SEMANTIC_RECORD_DECISIONS = {
    "accept_source_ref_candidate",
    "reject_wrong_leaf_source",
    "needs_external_source",
    "needs_leaf_split_or_retaxonomy",
}
POLLUTION_MARKERS = (
    "真题",
    "答案解析",
    "学生答卷",
    "按学生答卷",
    "必刷",
    "千题",
    "题斩",
    "考证宝典",
    "mcq",
    "practice",
    "exercise",
    "question_data",
    "correct_answer",
)
FALSEY_SAFETY_KEYS = {
    "canonical_truth_written",
    "official_score_allowed",
    "installed_runtime_supply",
    "release_truth_claimed",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _has_pollution_marker(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).lower()
    return any(marker in text for marker in POLLUTION_MARKERS)


def _check_schema(name: str, payload: dict[str, Any], blockers: list[str]) -> None:
    expected = EXPECTED_SCHEMAS[name]
    if payload.get("schema") != expected:
        blockers.append(f"schema_mismatch:{name}:{payload.get('schema')}!={expected}")


def _check_safety(name: str, payload: dict[str, Any], blockers: list[str]) -> None:
    safety = payload.get("safety")
    if not isinstance(safety, dict):
        blockers.append(f"safety_missing:{name}")
        return
    for key in FALSEY_SAFETY_KEYS:
        if safety.get(key) is not False:
            blockers.append(f"safety_flag_not_false:{name}:{key}")
    if safety.get("production_write_count") not in (0, False):
        blockers.append(f"safety_production_write_count_nonzero:{name}")


def _check_review_only(name: str, payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification")
    if isinstance(classification, dict):
        for key in ("patches_apply_allowed", "work_orders_apply_allowed", "runtime_install_allowed"):
            if classification.get(key) is True:
                blockers.append(f"classification_apply_or_runtime_allowed:{name}:{key}")
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).lower()
    for marker in (
        '"apply_allowed": true',
        '"runtime_install_allowed": true',
        '"promotion_allowed": true',
        '"install_allowed": true',
    ):
        if marker in blob:
            blockers.append(f"truth_or_runtime_marker_present:{name}:{marker}")


def _check_source_gap(payload: dict[str, Any], blockers: list[str], warnings: list[str]) -> None:
    for row in payload.get("source_gap_candidates") or []:
        if not isinstance(row, dict):
            continue
        leaf_id = row.get("leaf_id")
        missing_lane = row.get("missing_lane")
        if not leaf_id or not missing_lane or not row.get("artifact_id"):
            blockers.append(f"source_gap_missing_join_key:{leaf_id}:{missing_lane}")
        for candidate in row.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            source_lane = candidate.get("source_lane")
            if source_lane != missing_lane:
                blockers.append(f"source_gap_lane_mismatch:{leaf_id}:{missing_lane}:{source_lane}")
            if candidate.get("candidate_only") is not True or candidate.get("install_allowed") is not False:
                blockers.append(f"source_gap_candidate_flags_invalid:{leaf_id}:{missing_lane}")
            if source_lane != "question" and _has_pollution_marker(
                {
                    "source_path": candidate.get("source_path"),
                    "record_id": candidate.get("record_id"),
                    "provenance": candidate.get("provenance"),
                    "snippet": candidate.get("snippet"),
                }
            ):
                blockers.append(f"polluted_source_gap_support_lane:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if not candidate.get("record_id") or not candidate.get("span"):
                warnings.append(f"source_gap_candidate_missing_trace_detail:{leaf_id}:{missing_lane}")


def _check_patches(payload: dict[str, Any], blockers: list[str]) -> None:
    for patch in payload.get("candidate_patches") or []:
        if not isinstance(patch, dict):
            continue
        leaf_id = patch.get("leaf_id")
        missing_lane = patch.get("missing_lane")
        source_ref = patch.get("source_ref_candidate") if isinstance(patch.get("source_ref_candidate"), dict) else {}
        source_lane = source_ref.get("source_lane")
        if not leaf_id or not missing_lane or not patch.get("artifact_id"):
            blockers.append(f"patch_missing_join_key:{leaf_id}:{missing_lane}")
        if patch.get("candidate_only") is not True or patch.get("review_status") != "pending_review":
            blockers.append(f"patch_review_flags_invalid:{leaf_id}:{missing_lane}")
        if patch.get("apply_allowed") is not False or patch.get("runtime_install_allowed") is not False:
            blockers.append(f"patch_apply_or_runtime_allowed:{leaf_id}:{missing_lane}")
        if source_lane != missing_lane:
            blockers.append(f"patch_lane_mismatch:{leaf_id}:{missing_lane}:{source_lane}")
        if source_lane != "question" and _has_pollution_marker(
            {
                "path": source_ref.get("path"),
                "record_id": source_ref.get("record_id"),
                "provenance": source_ref.get("provenance"),
                "snippet": (patch.get("review_packet") or {}).get("snippet")
                if isinstance(patch.get("review_packet"), dict)
                else None,
            }
        ):
            blockers.append(f"polluted_patch_support_lane:{leaf_id}:{missing_lane}:{source_ref.get('record_id')}")


def _check_patch_audit(payload: dict[str, Any], blockers: list[str]) -> None:
    allowed_decisions = {"machine_precheck_pass", "machine_reject", "needs_semantic_review"}
    for audit in payload.get("patch_audits") or []:
        if not isinstance(audit, dict):
            continue
        leaf_id = audit.get("leaf_id")
        missing_lane = audit.get("missing_lane")
        if not leaf_id or not missing_lane or not audit.get("artifact_id") or not audit.get("patch_id"):
            blockers.append(f"patch_audit_missing_join_key:{leaf_id}:{missing_lane}")
        if audit.get("audit_decision") not in allowed_decisions:
            blockers.append(f"patch_audit_unknown_decision:{leaf_id}:{missing_lane}:{audit.get('audit_decision')}")
        if audit.get("review_status") != "machine_precheck_only":
            blockers.append(f"patch_audit_review_status_invalid:{leaf_id}:{missing_lane}")
        if audit.get("apply_allowed") is not False or audit.get("runtime_install_allowed") is not False:
            blockers.append(f"patch_audit_apply_or_runtime_allowed:{leaf_id}:{missing_lane}")
        if audit.get("candidate_only") is not True:
            blockers.append(f"patch_audit_candidate_flag_invalid:{leaf_id}:{missing_lane}")


def _check_rejected_feedback(payload: dict[str, Any], blockers: list[str]) -> None:
    for order in payload.get("rejected_patch_work_orders") or []:
        if not isinstance(order, dict):
            continue
        leaf_id = order.get("leaf_id")
        missing_lane = order.get("missing_lane")
        if not leaf_id or not missing_lane or not order.get("artifact_id") or not order.get("patch_id"):
            blockers.append(f"rejected_feedback_missing_join_key:{leaf_id}:{missing_lane}")
        if order.get("status") != "rejected_patch_feedback":
            blockers.append(f"rejected_feedback_status_invalid:{leaf_id}:{missing_lane}")
        if order.get("source_ref_candidate_reusable") is not False:
            blockers.append(f"rejected_feedback_source_ref_reusable:{leaf_id}:{missing_lane}")
        if order.get("promotion_allowed") is not False or order.get("runtime_install_allowed") is not False:
            blockers.append(f"rejected_feedback_promotion_or_runtime_allowed:{leaf_id}:{missing_lane}")


def _check_semantic_packets(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("semantic_verdict_recorded") is not False:
        blockers.append("semantic_packets_classification_verdict_recorded")
    for packet in payload.get("semantic_audit_packets") or []:
        if not isinstance(packet, dict):
            continue
        leaf_id = packet.get("leaf_id")
        missing_lane = packet.get("missing_lane")
        if not leaf_id or not missing_lane or not packet.get("artifact_id") or not packet.get("patch_id"):
            blockers.append(f"semantic_packet_missing_join_key:{leaf_id}:{missing_lane}")
        if packet.get("review_status") != "semantic_review_pending":
            blockers.append(f"semantic_packet_review_status_invalid:{leaf_id}:{missing_lane}")
        if packet.get("semantic_verdict_recorded") is not False:
            blockers.append(f"semantic_packet_verdict_recorded:{leaf_id}:{missing_lane}")
        if packet.get("apply_allowed") is not False or packet.get("runtime_install_allowed") is not False:
            blockers.append(f"semantic_packet_apply_or_runtime_allowed:{leaf_id}:{missing_lane}")
        if packet.get("candidate_only") is not True:
            blockers.append(f"semantic_packet_candidate_flag_invalid:{leaf_id}:{missing_lane}")
        source_ref = packet.get("source_ref_candidate") if isinstance(packet.get("source_ref_candidate"), dict) else {}
        if not source_ref.get("record_id") or not source_ref.get("span"):
            blockers.append(f"semantic_packet_missing_source_trace:{leaf_id}:{missing_lane}")


def _check_source_evidence(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("semantic_verdict_recorded") is not False:
        blockers.append("source_evidence_classification_verdict_recorded")
    source_corpus = payload.get("source_corpus") if isinstance(payload.get("source_corpus"), dict) else {}
    record_count_by_lane = source_corpus.get("record_count_by_lane") if isinstance(source_corpus.get("record_count_by_lane"), dict) else {}
    for lane in record_count_by_lane:
        if lane not in VALID_SOURCE_CORPUS_LANES:
            blockers.append(f"source_evidence_unknown_corpus_lane:{lane}")
    for order in payload.get("source_evidence_work_orders") or []:
        if not isinstance(order, dict):
            continue
        leaf_id = order.get("leaf_id")
        missing_lane = order.get("missing_lane")
        if not leaf_id or not missing_lane or not order.get("artifact_id"):
            blockers.append(f"source_evidence_missing_join_key:{leaf_id}:{missing_lane}")
        if order.get("review_status") != "source_evidence_review_pending":
            blockers.append(f"source_evidence_review_status_invalid:{leaf_id}:{missing_lane}")
        if order.get("candidate_only") is not True or order.get("review_only") is not True:
            blockers.append(f"source_evidence_review_flags_invalid:{leaf_id}:{missing_lane}")
        if order.get("promotion_allowed") is not False or order.get("runtime_install_allowed") is not False:
            blockers.append(f"source_evidence_promotion_or_runtime_allowed:{leaf_id}:{missing_lane}")
        for candidate in order.get("candidate_sources") or []:
            if not isinstance(candidate, dict):
                continue
            source_lane = candidate.get("source_lane")
            if source_lane == "question" and missing_lane != "question" and candidate.get("support_candidate") is True:
                blockers.append(f"source_evidence_question_support_candidate:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if source_lane != missing_lane:
                blockers.append(f"source_evidence_lane_mismatch:{leaf_id}:{missing_lane}:{source_lane}")
            if candidate.get("support_candidate") is not True:
                blockers.append(f"source_evidence_support_flag_invalid:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if candidate.get("candidate_only") is not True:
                blockers.append(f"source_evidence_candidate_flag_invalid:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if candidate.get("install_allowed") is not False or candidate.get("runtime_install_allowed") is not False:
                blockers.append(f"source_evidence_install_or_runtime_allowed:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if not candidate.get("record_id") or not candidate.get("span") or not candidate.get("span_hash"):
                blockers.append(f"source_evidence_missing_source_trace:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if source_lane != "question" and _has_pollution_marker(
                {
                    "source_path": candidate.get("source_path"),
                    "record_id": candidate.get("record_id"),
                    "span": candidate.get("span"),
                }
            ):
                blockers.append(f"polluted_source_evidence_support_lane:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
        for candidate in order.get("question_context_candidates") or []:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("source_lane") != "question":
                blockers.append(f"source_evidence_question_context_lane_invalid:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if candidate.get("support_candidate") is not False:
                blockers.append(f"source_evidence_question_context_support_true:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if candidate.get("install_allowed") is not False or candidate.get("runtime_install_allowed") is not False:
                blockers.append(f"source_evidence_question_context_install_allowed:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")


def _check_semantic_queue(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("semantic_verdict_recorded") is not False:
        blockers.append("semantic_queue_classification_verdict_recorded")
    for item in payload.get("semantic_audit_queue") or []:
        if not isinstance(item, dict):
            continue
        leaf_id = item.get("leaf_id")
        missing_lane = item.get("missing_lane")
        if not item.get("audit_item_id") or not item.get("audit_source_type"):
            blockers.append(f"semantic_queue_missing_item_id:{leaf_id}:{missing_lane}")
        if not leaf_id or not missing_lane or not item.get("artifact_id"):
            blockers.append(f"semantic_queue_missing_join_key:{leaf_id}:{missing_lane}")
        if item.get("review_status") != "semantic_review_pending":
            blockers.append(f"semantic_queue_review_status_invalid:{leaf_id}:{missing_lane}")
        if item.get("semantic_verdict_recorded") is not False:
            blockers.append(f"semantic_queue_verdict_recorded:{leaf_id}:{missing_lane}")
        if item.get("candidate_only") is not True or item.get("review_only") is not True:
            blockers.append(f"semantic_queue_review_flags_invalid:{leaf_id}:{missing_lane}")
        if item.get("apply_allowed") is not False or item.get("runtime_install_allowed") is not False:
            blockers.append(f"semantic_queue_apply_or_runtime_allowed:{leaf_id}:{missing_lane}")
        source_candidate = item.get("source_candidate")
        if source_candidate is not None:
            if not isinstance(source_candidate, dict):
                blockers.append(f"semantic_queue_source_candidate_invalid:{leaf_id}:{missing_lane}")
                continue
            source_lane = source_candidate.get("source_lane")
            if source_lane == "question" and missing_lane != "question" and source_candidate.get("support_candidate") is True:
                blockers.append(f"semantic_queue_question_support_candidate:{leaf_id}:{missing_lane}:{source_candidate.get('record_id')}")
            if source_lane != missing_lane:
                blockers.append(f"semantic_queue_lane_mismatch:{leaf_id}:{missing_lane}:{source_lane}")
            if source_candidate.get("support_candidate") is not True:
                blockers.append(f"semantic_queue_support_flag_invalid:{leaf_id}:{missing_lane}:{source_candidate.get('record_id')}")
            if source_candidate.get("install_allowed") is not False or source_candidate.get("runtime_install_allowed") is not False:
                blockers.append(f"semantic_queue_source_install_or_runtime_allowed:{leaf_id}:{missing_lane}:{source_candidate.get('record_id')}")
            if not source_candidate.get("record_id") or not source_candidate.get("span"):
                blockers.append(f"semantic_queue_missing_source_trace:{leaf_id}:{missing_lane}:{source_candidate.get('record_id')}")
            if source_lane != "question" and _has_pollution_marker(
                {
                    "source_path": source_candidate.get("source_path"),
                    "record_id": source_candidate.get("record_id"),
                    "span": source_candidate.get("span"),
                }
            ):
                blockers.append(f"polluted_semantic_queue_support_lane:{leaf_id}:{missing_lane}:{source_candidate.get('record_id')}")
        for candidate in item.get("question_context_candidates") or []:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("support_candidate") is not False:
                blockers.append(f"semantic_queue_question_context_support_true:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")
            if candidate.get("install_allowed") is not False or candidate.get("runtime_install_allowed") is not False:
                blockers.append(f"semantic_queue_question_context_install_allowed:{leaf_id}:{missing_lane}:{candidate.get('record_id')}")


def _check_semantic_record(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("runtime_install_allowed") is not False or classification.get("release_truth_claimed") is not False:
        blockers.append("semantic_record_classification_runtime_or_release_allowed")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("invalid_decision_count") not in (0, False):
        blockers.append("semantic_record_invalid_decisions_present")
    for record in payload.get("semantic_evidence_audit_records") or []:
        if not isinstance(record, dict):
            continue
        leaf_id = record.get("leaf_id")
        missing_lane = record.get("missing_lane")
        if not record.get("audit_item_id") or not record.get("audit_source_type"):
            blockers.append(f"semantic_record_missing_item_id:{leaf_id}:{missing_lane}")
        if not leaf_id or not missing_lane or not record.get("artifact_id"):
            blockers.append(f"semantic_record_missing_join_key:{leaf_id}:{missing_lane}")
        if record.get("review_decision_status") not in {"not_exercised", "recorded"}:
            blockers.append(f"semantic_record_invalid_decision_status:{leaf_id}:{missing_lane}:{record.get('review_decision_status')}")
        if record.get("review_decision_status") == "recorded" and record.get("decision") not in ALLOWED_SEMANTIC_RECORD_DECISIONS:
            blockers.append(f"semantic_record_invalid_decision:{leaf_id}:{missing_lane}:{record.get('decision')}")
        if record.get("review_decision_status") == "not_exercised" and record.get("decision") is not None:
            blockers.append(f"semantic_record_not_exercised_has_decision:{leaf_id}:{missing_lane}")
        if record.get("runtime_install_allowed") is not False or record.get("release_truth_claimed") is not False:
            blockers.append(f"semantic_record_runtime_or_release_allowed:{leaf_id}:{missing_lane}")
        if record.get("official_score_allowed") is not False:
            blockers.append(f"semantic_record_official_score_allowed:{leaf_id}:{missing_lane}")
        source_candidate = record.get("source_candidate")
        if isinstance(source_candidate, dict):
            source_lane = source_candidate.get("source_lane")
            if source_lane == "question" and missing_lane != "question" and source_candidate.get("support_candidate") is True:
                blockers.append(f"semantic_record_question_support_candidate:{leaf_id}:{missing_lane}:{source_candidate.get('record_id')}")
            if source_lane is not None and source_lane != missing_lane:
                blockers.append(f"semantic_record_lane_mismatch:{leaf_id}:{missing_lane}:{source_lane}")
            if not source_candidate.get("record_id") or not source_candidate.get("span"):
                blockers.append(f"semantic_record_missing_source_trace:{leaf_id}:{missing_lane}:{source_candidate.get('record_id')}")


def _check_review_shards(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("decisions_recorded") is not False or classification.get("runtime_install_allowed") is not False:
        blockers.append("review_shards_decisions_or_runtime_allowed")
    decision_schema = payload.get("decision_output_schema") if isinstance(payload.get("decision_output_schema"), dict) else {}
    if decision_schema.get("schema") != "luban_rich_leaf_semantic_audit_decisions.v1":
        blockers.append("review_shards_decision_schema_invalid")
    if decision_schema.get("runtime_install_allowed") is not False or decision_schema.get("release_truth_claimed") is not False:
        blockers.append("review_shards_decision_schema_runtime_or_release_allowed")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    shards = payload.get("shards") if isinstance(payload.get("shards"), list) else []
    if summary.get("shard_count") != len(shards):
        blockers.append("review_shards_count_mismatch")
    for shard in shards:
        if not isinstance(shard, dict):
            blockers.append("review_shards_entry_not_object")
            continue
        if not shard.get("shard_id") or not shard.get("path"):
            blockers.append("review_shards_missing_trace")
        if not isinstance(shard.get("audit_item_count"), int):
            blockers.append(f"review_shards_invalid_item_count:{shard.get('shard_id')}")


def _check_review_suggestions(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("suggestion_only") is not True or classification.get("review_only") is not True:
        blockers.append("review_suggestions_classification_invalid")
    if (
        classification.get("decisions_recorded") is not False
        or classification.get("runtime_install_allowed") is not False
        or classification.get("release_truth_claimed") is not False
    ):
        blockers.append("review_suggestion_decision_recorded")
    allowed = {
        "accept_source_ref_candidate",
        "reject_wrong_leaf_source",
        "needs_external_source",
        "needs_leaf_split_or_retaxonomy",
        "manual_review_required",
    }
    suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("suggestion_count") != len(suggestions):
        blockers.append("review_suggestions_count_mismatch")
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            blockers.append("review_suggestion_not_object")
            continue
        leaf_id = suggestion.get("leaf_id")
        missing_lane = suggestion.get("missing_lane")
        if not suggestion.get("audit_item_id") or not leaf_id or not suggestion.get("artifact_id") or not missing_lane:
            blockers.append(f"review_suggestion_missing_join_key:{leaf_id}:{missing_lane}")
        if suggestion.get("suggested_decision") not in allowed:
            blockers.append(f"review_suggestion_unknown_decision:{leaf_id}:{missing_lane}:{suggestion.get('suggested_decision')}")
        if suggestion.get("decision_recorded") is not False:
            blockers.append(f"review_suggestion_decision_recorded:{leaf_id}:{missing_lane}")
        if suggestion.get("runtime_install_allowed") is not False or suggestion.get("release_truth_claimed") is not False:
            blockers.append(f"review_suggestion_runtime_or_release_allowed:{leaf_id}:{missing_lane}")
        if suggestion.get("reviewer_must_confirm") is not True:
            blockers.append(f"review_suggestion_confirmation_not_required:{leaf_id}:{missing_lane}")


def _check_decision_validation(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("runtime_install_allowed") is not False or classification.get("release_truth_claimed") is not False:
        blockers.append("decision_validation_runtime_or_release_allowed")
    verdict = payload.get("verdict")
    if verdict not in {"PASS", "INCOMPLETE"}:
        blockers.append(f"decision_validation_bad_verdict:{verdict}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("invalid_decision_count") not in (0, False) or summary.get("orphan_decision_count") not in (0, False):
        blockers.append("decision_validation_failed_or_invalid")
    if summary.get("duplicate_decision_count") not in (0, False):
        blockers.append("decision_validation_duplicate_decisions")


def _check_reviewed_candidates(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("runtime_install_allowed") is not False or classification.get("release_truth_claimed") is not False:
        blockers.append("reviewed_candidates_classification_runtime_or_release_allowed")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    candidates = payload.get("reviewed_candidates") if isinstance(payload.get("reviewed_candidates"), list) else []
    if summary.get("reviewed_candidate_count") != len(candidates):
        blockers.append("reviewed_candidates_count_mismatch")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            blockers.append("reviewed_candidate_entry_not_object")
            continue
        leaf_id = candidate.get("leaf_id")
        missing_lane = candidate.get("missing_lane")
        if candidate.get("candidate_status") != "reviewed_candidate":
            blockers.append(f"reviewed_candidate_status_invalid:{leaf_id}:{missing_lane}")
        if not candidate.get("candidate_id") or not candidate.get("audit_item_id"):
            blockers.append(f"reviewed_candidate_missing_trace:{leaf_id}:{missing_lane}")
        if not leaf_id or not missing_lane or not candidate.get("artifact_id"):
            blockers.append(f"reviewed_candidate_missing_join_key:{leaf_id}:{missing_lane}")
        if candidate.get("candidate_only") is not True or candidate.get("review_only") is not True:
            blockers.append(f"reviewed_candidate_flags_invalid:{leaf_id}:{missing_lane}")
        if (
            candidate.get("runtime_install_allowed") is not False
            or candidate.get("release_truth_claimed") is not False
            or candidate.get("official_score_allowed") is not False
        ):
            blockers.append(f"reviewed_candidate_runtime_or_release_allowed:{leaf_id}:{missing_lane}")
        patch = candidate.get("field_patch") if isinstance(candidate.get("field_patch"), dict) else {}
        source_ref = patch.get("source_ref") if isinstance(patch.get("source_ref"), dict) else {}
        source_lane = source_ref.get("source_lane")
        if patch.get("field") != "source_refs" or patch.get("operation") != "add_source_ref":
            blockers.append(f"reviewed_candidate_patch_invalid:{leaf_id}:{missing_lane}")
        if source_lane == "question" and missing_lane != "question" and source_ref.get("support_candidate") is True:
            blockers.append(f"reviewed_candidate_question_support_candidate:{leaf_id}:{missing_lane}:{source_ref.get('record_id')}")
        if source_lane != missing_lane:
            blockers.append(f"reviewed_candidate_lane_mismatch:{leaf_id}:{missing_lane}:{source_lane}")
        if not source_ref.get("record_id") or not source_ref.get("span") or not source_ref.get("span_hash"):
            blockers.append(f"reviewed_candidate_missing_source_trace:{leaf_id}:{missing_lane}:{source_ref.get('record_id')}")
        if source_lane != "question" and _has_pollution_marker(
            {
                "source_path": source_ref.get("source_path"),
                "record_id": source_ref.get("record_id"),
                "span": source_ref.get("span"),
            }
        ):
            blockers.append(f"polluted_reviewed_candidate_support_lane:{leaf_id}:{missing_lane}:{source_ref.get('record_id')}")


def _check_runtime_supply_candidate(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("install_allowed", "runtime_install_allowed", "production_default", "canonical_pointer_written"):
        if classification.get(key) is not False:
            blockers.append(f"runtime_supply_candidate_install_or_default_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("runtime_supply_candidate_review_flags_invalid")
    if classification.get("runtime_supply_candidate") is not True or classification.get("regression_required") is not True:
        blockers.append("runtime_supply_candidate_classification_invalid")
    status = payload.get("status")
    if status not in {"no_reviewed_candidates", "no_valid_supply_units", "candidate_ready_for_regression"}:
        blockers.append(f"runtime_supply_candidate_status_invalid:{status}")
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    if not manifest.get("bundle_hash") or manifest.get("hash_algorithm") != "sha256":
        blockers.append("runtime_supply_candidate_manifest_hash_invalid")
    units = payload.get("supply_units") if isinstance(payload.get("supply_units"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("supply_unit_count") != len(units):
        blockers.append("runtime_supply_candidate_unit_count_mismatch")
    for unit in units:
        if not isinstance(unit, dict):
            blockers.append("runtime_supply_candidate_unit_not_object")
            continue
        leaf_id = unit.get("leaf_id")
        missing_lane = unit.get("missing_lane")
        source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
        if not unit.get("unit_id") or not leaf_id or not unit.get("artifact_id") or not missing_lane:
            blockers.append(f"runtime_supply_candidate_unit_missing_join_key:{leaf_id}:{missing_lane}")
        if unit.get("candidate_only") is not True or unit.get("review_only") is not True:
            blockers.append(f"runtime_supply_candidate_unit_flags_invalid:{leaf_id}:{missing_lane}")
        if unit.get("install_allowed") is not False or unit.get("runtime_install_allowed") is not False:
            blockers.append(f"runtime_supply_candidate_unit_install_allowed:{leaf_id}:{missing_lane}")
        source_lane = source_ref.get("source_lane")
        if source_lane == "question" and missing_lane != "question":
            blockers.append(f"runtime_supply_candidate_question_support_candidate:{leaf_id}:{missing_lane}:{source_ref.get('record_id')}")
        if source_lane != missing_lane:
            blockers.append(f"runtime_supply_candidate_lane_mismatch:{leaf_id}:{missing_lane}:{source_lane}")
        if not source_ref.get("record_id") or not source_ref.get("span") or not source_ref.get("span_hash"):
            blockers.append(f"runtime_supply_candidate_missing_source_trace:{leaf_id}:{missing_lane}:{source_ref.get('record_id')}")


def _check_runtime_supply_regression(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"runtime_supply_regression_failed:{payload.get('verdict')}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"runtime_supply_regression_blockers_present:{summary.get('blocker_count')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"runtime_supply_regression_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("runtime_supply_regression_review_flags_invalid")
    if classification.get("runtime_supply_regression") is not True:
        blockers.append("runtime_supply_regression_classification_invalid")
    projections = payload.get("task_projections") if isinstance(payload.get("task_projections"), list) else []
    task_names = {projection.get("task") for projection in projections if isinstance(projection, dict)}
    for required_task in ("grading", "tutoring", "rag_answer", "next_action", "review"):
        if required_task not in task_names:
            blockers.append(f"runtime_supply_regression_missing_task_projection:{required_task}")
    for projection in projections:
        if not isinstance(projection, dict):
            blockers.append("runtime_supply_regression_projection_not_object")
            continue
        if projection.get("task") == "next_action" and projection.get("projected_unit_count") not in (0, False):
            blockers.append("runtime_supply_regression_next_action_source_ref_leak")


def _check_field_candidates(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"field_candidates_failed:{payload.get('verdict')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"field_candidates_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("field_candidates_review_flags_invalid")
    if classification.get("rich_field_candidate_batch") is not True:
        blockers.append("field_candidates_classification_invalid")
    field_candidates = payload.get("field_candidates") if isinstance(payload.get("field_candidates"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("generated_field_candidate_count") != len(field_candidates):
        blockers.append("field_candidates_count_mismatch")
    for field in field_candidates:
        if not isinstance(field, dict):
            blockers.append("field_candidate_not_object")
            continue
        field_id = field.get("field_candidate_id")
        family = field.get("family")
        trace = field.get("source_ref_trace") if isinstance(field.get("source_ref_trace"), dict) else {}
        if not field_id or not family or not field.get("leaf_id") or not field.get("artifact_id"):
            blockers.append(f"field_candidate_missing_join_key:{field_id}:{family}")
        if field.get("candidate_only") is not True or field.get("review_only") is not True:
            blockers.append(f"field_candidate_review_flags_invalid:{field_id}")
        if field.get("runtime_install_allowed") is not False or field.get("release_truth_claimed") is not False:
            blockers.append(f"field_candidate_runtime_or_release_allowed:{field_id}")
        if field.get("claim_status") != "candidate_only":
            blockers.append(f"field_candidate_claim_status_not_candidate_only:{field_id}")
        if not trace.get("source_lane") or not trace.get("record_id") or not trace.get("span") or not trace.get("span_hash"):
            blockers.append(f"field_candidate_source_trace_missing:{field_id}")
        if trace.get("source_lane") == "question" and family in KNOWLEDGE_FIELD_FAMILIES:
            blockers.append(f"field_candidate_question_lane_knowledge_field:{field_id}:{family}")
        if family == "exam_patterns" and trace.get("source_lane") != "question":
            blockers.append(f"field_candidate_exam_pattern_not_question_lane:{field_id}")


def _check_artifact_candidates(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"artifact_candidates_failed:{payload.get('verdict')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"artifact_candidates_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("artifact_candidates_review_flags_invalid")
    if classification.get("rich_leaf_artifact_candidate_batch") is not True:
        blockers.append("artifact_candidates_classification_invalid")
    artifacts = payload.get("rich_leaf_artifact_candidates") if isinstance(payload.get("rich_leaf_artifact_candidates"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("artifact_candidate_count") != len(artifacts):
        blockers.append("artifact_candidates_count_mismatch")
    if summary.get("validation_failure_count") not in (0, False):
        blockers.append(f"artifact_candidates_validation_failures_present:{summary.get('validation_failure_count')}")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            blockers.append("artifact_candidate_not_object")
            continue
        artifact_id = artifact.get("artifact_id")
        report = validate_rich_leaf_artifact(artifact)
        if not report.ok:
            blockers.append(f"artifact_candidate_validation_failed:{artifact_id}:{'|'.join(report.blockers)}")
        if artifact.get("candidate_status") not in {"candidate", "reviewed_candidate"}:
            blockers.append(f"artifact_candidate_status_not_candidate:{artifact_id}:{artifact.get('candidate_status')}")
        for key in ("official_score_allowed", "canonical_truth_written", "controlled_default"):
            if artifact.get(key) is True:
                blockers.append(f"artifact_candidate_truth_or_default_flag:{artifact_id}:{key}")


def _source_ref_lanes_for_field(artifact: dict[str, Any], field: dict[str, Any]) -> set[str]:
    refs = {
        str(ref.get("source_ref_id")): ref
        for ref in artifact.get("source_refs") or []
        if isinstance(ref, dict) and ref.get("source_ref_id")
    }
    lanes: set[str] = set()
    for ref_id in field.get("source_ref_ids") or []:
        ref = refs.get(str(ref_id))
        if isinstance(ref, dict) and ref.get("source_lane"):
            lanes.add(str(ref["source_lane"]))
    return lanes


def _check_field_promotion_review(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"field_promotion_review_failed:{payload.get('verdict')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"field_promotion_review_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("field_promotion_review_review_flags_invalid")
    if classification.get("field_promotion_review") is not True:
        blockers.append("field_promotion_review_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    artifacts = (
        payload.get("promoted_rich_leaf_artifact_candidates")
        if isinstance(payload.get("promoted_rich_leaf_artifact_candidates"), list)
        else []
    )
    decisions = payload.get("promotion_decisions") if isinstance(payload.get("promotion_decisions"), list) else []
    if summary.get("promoted_artifact_candidate_count") != len(artifacts):
        blockers.append("field_promotion_review_artifact_count_mismatch")
    if summary.get("promotion_decision_count") != len(decisions):
        blockers.append("field_promotion_review_decision_count_mismatch")
    if summary.get("validation_failure_count") not in (0, False):
        blockers.append(f"field_promotion_review_validation_failures_present:{summary.get('validation_failure_count')}")
    for decision in decisions:
        if not isinstance(decision, dict):
            blockers.append("field_promotion_review_decision_not_object")
            continue
        decision_id = f"{decision.get('artifact_id')}:{decision.get('field_id')}"
        if decision.get("runtime_install_allowed") is not False or decision.get("release_truth_claimed") is not False:
            blockers.append(f"field_promotion_review_decision_runtime_or_release_allowed:{decision_id}")
        to_status = decision.get("to_status")
        family = decision.get("family")
        lanes = set(decision.get("source_lanes") or [])
        if to_status == "source_backed":
            if family not in SOURCE_BACKED_PROMOTION_FAMILIES or not lanes or not lanes <= SOURCE_BACKED_LANES:
                blockers.append(f"field_promotion_review_bad_source_backed_promotion:{decision_id}:{family}:{sorted(lanes)}")
        elif to_status == "assessment_evidence":
            if family != "exam_patterns" or lanes != {"question"}:
                blockers.append(f"field_promotion_review_bad_assessment_evidence_promotion:{decision_id}:{family}:{sorted(lanes)}")
        elif to_status != "candidate_only":
            blockers.append(f"field_promotion_review_unknown_to_status:{decision_id}:{to_status}")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            blockers.append("field_promotion_review_artifact_not_object")
            continue
        artifact_id = artifact.get("artifact_id")
        report = validate_rich_leaf_artifact(artifact)
        if not report.ok:
            blockers.append(f"field_promotion_review_artifact_validation_failed:{artifact_id}:{'|'.join(report.blockers)}")
        if artifact.get("candidate_status") not in {"candidate", "reviewed_candidate"}:
            blockers.append(f"field_promotion_review_status_not_candidate:{artifact_id}:{artifact.get('candidate_status')}")
        for family in KNOWLEDGE_FIELD_FAMILIES:
            for field in artifact.get(family) or []:
                if not isinstance(field, dict):
                    continue
                lanes = _source_ref_lanes_for_field(artifact, field)
                if "question" in lanes and field.get("claim_status") == "source_backed":
                    blockers.append(f"field_promotion_review_question_lane_source_backed_knowledge:{artifact_id}:{family}:{field.get('field_id')}")
        for field in artifact.get("exam_patterns") or []:
            if not isinstance(field, dict):
                continue
            if field.get("claim_status") == "source_backed":
                blockers.append(f"field_promotion_review_exam_pattern_source_backed:{artifact_id}:{field.get('field_id')}")
            if field.get("claim_status") == "assessment_evidence" and field.get("knowledge_source_allowed") is not False:
                blockers.append(f"field_promotion_review_exam_pattern_knowledge_allowed:{artifact_id}:{field.get('field_id')}")


def _check_context_pack_smoke(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"context_pack_smoke_failed:{payload.get('verdict')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"context_pack_smoke_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("context_pack_smoke_review_flags_invalid")
    if classification.get("context_pack_smoke") is not True:
        blockers.append("context_pack_smoke_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    packs = payload.get("compiled_context_packs") if isinstance(payload.get("compiled_context_packs"), list) else []
    if summary.get("task_pack_count") != len(packs):
        blockers.append("context_pack_smoke_pack_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"context_pack_smoke_blockers_present:{summary.get('blocker_count')}")
    if summary.get("knowledge_task_question_lane_source_ref_count") not in (0, False):
        blockers.append("context_pack_smoke_question_lane_knowledge_leak")
    task_names = {pack.get("task") for pack in packs if isinstance(pack, dict)}
    for required_task in ("grading", "tutoring", "rag_answer", "next_action", "review"):
        if required_task not in task_names:
            blockers.append(f"context_pack_smoke_missing_task:{required_task}")
    for pack in packs:
        if not isinstance(pack, dict):
            blockers.append("context_pack_smoke_pack_not_object")
            continue
        task = pack.get("task")
        if pack.get("canonical_write_allowed") is not False or pack.get("official_score_allowed") is not False:
            blockers.append(f"context_pack_smoke_write_or_score_allowed:{task}")
        if pack.get("production_write_count") not in (0, False):
            blockers.append(f"context_pack_smoke_production_write_count_nonzero:{task}")
        if task in {"grading", "tutoring", "rag_answer"} and "question" in set(pack.get("source_ref_lanes") or []):
            blockers.append(f"context_pack_smoke_question_lane_source_ref_in_knowledge_task:{task}")
        if pack.get("fail_closed_reasons"):
            blockers.append(f"context_pack_smoke_fail_closed:{task}")


def _check_fail_open_guard_diagnostic(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"fail_open_guard_diagnostic_failed:{payload.get('verdict')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("fail_open_guard_diagnostic_review_flags_invalid")
    if classification.get("fail_open_guard_diagnostic") is not True:
        blockers.append("fail_open_guard_diagnostic_classification_invalid")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed", "quality_claim_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"fail_open_guard_diagnostic_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    diagnostics = payload.get("leaf_diagnostics") if isinstance(payload.get("leaf_diagnostics"), list) else []
    if summary.get("top_leaf_count") != len(diagnostics):
        blockers.append("fail_open_guard_diagnostic_leaf_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"fail_open_guard_diagnostic_blockers_present:{summary.get('blocker_count')}")
    negative_count = int(summary.get("negative_evidence_candidate_count") or 0)
    if negative_count and int(summary.get("review_candidate_field_count") or 0) <= 0:
        blockers.append("fail_open_guard_diagnostic_negative_evidence_hidden")
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            blockers.append("fail_open_guard_diagnostic_entry_not_object")
            continue
        leaf_id = diagnostic.get("leaf_id")
        if not leaf_id:
            blockers.append("fail_open_guard_diagnostic_missing_leaf_id")
        if int(diagnostic.get("negative_evidence_count") or 0) <= 0:
            blockers.append(f"fail_open_guard_diagnostic_empty_leaf:{leaf_id}")
        if diagnostic.get("guard_suggestion") != "block_positive_context_until_source_ref_reviewed":
            blockers.append(f"fail_open_guard_diagnostic_unknown_guard:{leaf_id}:{diagnostic.get('guard_suggestion')}")


def _check_context_pack_projection_ab(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"context_pack_projection_ab_failed:{payload.get('verdict')}")
    if payload.get("verdict_ceiling") != "PROJECTION_ONLY":
        blockers.append(f"context_pack_projection_ab_bad_ceiling:{payload.get('verdict_ceiling')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("context_pack_projection_ab_quality_claim_allowed")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"context_pack_projection_ab_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("context_pack_projection_ab_review_flags_invalid")
    if classification.get("context_pack_projection_ab") is not True:
        blockers.append("context_pack_projection_ab_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    table = payload.get("effect_table") if isinstance(payload.get("effect_table"), list) else []
    if summary.get("task_count") != len(table):
        blockers.append("context_pack_projection_ab_task_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"context_pack_projection_ab_blockers_present:{summary.get('blocker_count')}")
    if summary.get("improved_task_count", 0) <= 0:
        blockers.append("context_pack_projection_ab_no_improved_tasks")
    if summary.get("knowledge_task_question_lane_leak_count") not in (0, False):
        blockers.append("context_pack_projection_ab_question_lane_knowledge_leak")
    tasks = {row.get("task") for row in table if isinstance(row, dict)}
    for required_task in ("grading", "tutoring", "rag_answer", "next_action", "review"):
        if required_task not in tasks:
            blockers.append(f"context_pack_projection_ab_missing_task:{required_task}")
    for row in table:
        if not isinstance(row, dict):
            blockers.append("context_pack_projection_ab_row_not_object")
            continue
        task = row.get("task")
        if row.get("field_count_delta", 0) < 0:
            blockers.append(f"context_pack_projection_ab_negative_field_delta:{task}")
        if task in {"grading", "tutoring", "rag_answer"}:
            if row.get("knowledge_task_question_lane_leak") is not False:
                blockers.append(f"context_pack_projection_ab_row_question_lane_leak:{task}")
            if "question" in set(row.get("treatment_source_ref_lanes") or []):
                blockers.append(f"context_pack_projection_ab_question_lane_source_ref_in_knowledge_task:{task}")
    not_exercised = set(payload.get("not_exercised") or [])
    for required in ("live_runtime_accuracy", "live_runtime_latency", "live_runtime_token_usage", "llm_judge_semantic_quality"):
        if required not in not_exercised:
            blockers.append(f"context_pack_projection_ab_missing_not_exercised:{required}")


def _check_semantic_runtime_offline_ab(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"semantic_runtime_offline_ab_failed:{payload.get('verdict')}")
    if payload.get("verdict_ceiling") != "OFFLINE_ADAPTER_ONLY":
        blockers.append(f"semantic_runtime_offline_ab_bad_ceiling:{payload.get('verdict_ceiling')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("semantic_runtime_offline_ab_quality_claim_allowed")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"semantic_runtime_offline_ab_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("semantic_runtime_offline_ab_review_flags_invalid")
    if classification.get("semantic_runtime_offline_ab") is not True:
        blockers.append("semantic_runtime_offline_ab_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    table = payload.get("effect_table") if isinstance(payload.get("effect_table"), list) else []
    if summary.get("arm_count") != len(table):
        blockers.append("semantic_runtime_offline_ab_arm_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"semantic_runtime_offline_ab_blockers_present:{summary.get('blocker_count')}")
    if summary.get("eval_case_count", 0) <= 0:
        blockers.append("semantic_runtime_offline_ab_no_eval_cases")
    if float(summary.get("treatment_fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_offline_ab_treatment_fail_open")
    if float(summary.get("treatment_evidence_citation_rate") or 0.0) <= 0.0:
        blockers.append("semantic_runtime_offline_ab_no_treatment_citations")
    arms = {row.get("arm"): row for row in table if isinstance(row, dict)}
    for required_arm in ("baseline_empty_context", "rich_leaf_promoted_context"):
        if required_arm not in arms:
            blockers.append(f"semantic_runtime_offline_ab_missing_arm:{required_arm}")
    treatment = arms.get("rich_leaf_promoted_context") or {}
    if float(treatment.get("fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_offline_ab_treatment_row_fail_open")
    if float(treatment.get("evidence_citation_rate") or 0.0) <= 0.0:
        blockers.append("semantic_runtime_offline_ab_treatment_row_no_citations")
    baseline = arms.get("baseline_empty_context") or {}
    if float(baseline.get("fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_offline_ab_baseline_fail_open")
    not_exercised = set(payload.get("not_exercised") or [])
    for required in ("live_llm_semantic_judgment", "live_runtime_latency", "live_runtime_token_usage", "production_rag_retrieval"):
        if required not in not_exercised:
            blockers.append(f"semantic_runtime_offline_ab_missing_not_exercised:{required}")


def _check_semantic_runtime_nearline_ab(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"semantic_runtime_nearline_ab_failed:{payload.get('verdict')}")
    if payload.get("verdict_ceiling") != "NEARLINE_RETRIEVAL_PROJECTION":
        blockers.append(f"semantic_runtime_nearline_ab_bad_ceiling:{payload.get('verdict_ceiling')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("semantic_runtime_nearline_ab_quality_claim_allowed")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"semantic_runtime_nearline_ab_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("semantic_runtime_nearline_ab_review_flags_invalid")
    if classification.get("semantic_runtime_nearline_ab") is not True:
        blockers.append("semantic_runtime_nearline_ab_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    table = payload.get("effect_table") if isinstance(payload.get("effect_table"), list) else []
    if summary.get("arm_count") != len(table):
        blockers.append("semantic_runtime_nearline_ab_arm_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"semantic_runtime_nearline_ab_blockers_present:{summary.get('blocker_count')}")
    if summary.get("eval_case_count", 0) <= 0:
        blockers.append("semantic_runtime_nearline_ab_no_eval_cases")
    if float(summary.get("treatment_fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_nearline_ab_treatment_fail_open")
    if float(summary.get("treatment_evidence_citation_rate") or 0.0) <= 0.0:
        blockers.append("semantic_runtime_nearline_ab_no_treatment_citations")
    if float(summary.get("treatment_token_proxy_delta_vs_current_rag") or 0.0) > 0.0:
        blockers.append("semantic_runtime_nearline_ab_treatment_token_proxy_regression")
    arms = {row.get("arm"): row for row in table if isinstance(row, dict)}
    for required_arm in ("baseline_empty_context", "current_rag_lexical_retrieval", "rich_leaf_promoted_context"):
        if required_arm not in arms:
            blockers.append(f"semantic_runtime_nearline_ab_missing_arm:{required_arm}")
    treatment = arms.get("rich_leaf_promoted_context") or {}
    if float(treatment.get("fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_nearline_ab_treatment_row_fail_open")
    if float(treatment.get("evidence_citation_rate") or 0.0) <= 0.0:
        blockers.append("semantic_runtime_nearline_ab_treatment_row_no_citations")
    if float(treatment.get("question_lane_citation_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_nearline_ab_treatment_question_lane_citation")
    baseline = arms.get("baseline_empty_context") or {}
    if float(baseline.get("fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_nearline_ab_baseline_fail_open")
    not_exercised = set(payload.get("not_exercised") or [])
    for required in ("production_rag_retrieval", "live_llm_semantic_judgment", "live_runtime_latency", "live_runtime_token_usage"):
        if required not in not_exercised:
            blockers.append(f"semantic_runtime_nearline_ab_missing_not_exercised:{required}")


def _check_semantic_runtime_live_ab_preflight(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "READY_FOR_LIVE_RUNTIME_AB":
        blockers.append(f"semantic_runtime_live_ab_preflight_not_ready:{payload.get('verdict')}")
    if payload.get("verdict_ceiling") != "PREFLIGHT_ONLY":
        blockers.append(f"semantic_runtime_live_ab_preflight_bad_ceiling:{payload.get('verdict_ceiling')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("semantic_runtime_live_ab_preflight_quality_claim_allowed")
    if payload.get("execution_mode") != "preflight_only":
        blockers.append(f"semantic_runtime_live_ab_preflight_bad_execution_mode:{payload.get('execution_mode')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"semantic_runtime_live_ab_preflight_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("semantic_runtime_live_ab_preflight_review_flags_invalid")
    if classification.get("semantic_runtime_live_ab_preflight") is not True:
        blockers.append("semantic_runtime_live_ab_preflight_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"semantic_runtime_live_ab_preflight_blockers_present:{summary.get('blocker_count')}")
    if summary.get("live_runtime_executed") is not False:
        blockers.append("semantic_runtime_live_ab_preflight_live_runtime_executed")
    if int(summary.get("provider_call_count") or 0) != 0:
        blockers.append("semantic_runtime_live_ab_preflight_provider_calls_present")
    if int(summary.get("nearline_eval_case_count") or 0) <= 0:
        blockers.append("semantic_runtime_live_ab_preflight_no_nearline_eval_cases")
    if float(summary.get("nearline_treatment_fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_live_ab_preflight_nearline_fail_open")
    runtime_entry = payload.get("runtime_entry") if isinstance(payload.get("runtime_entry"), dict) else {}
    if runtime_entry.get("runtime_exercised") is not False or runtime_entry.get("entrypoint") != "not_exercised":
        blockers.append("semantic_runtime_live_ab_preflight_runtime_entry_exercised")
    provider_policy = payload.get("provider_call_policy") if isinstance(payload.get("provider_call_policy"), dict) else {}
    if provider_policy.get("provider_calls_allowed") is not False or int(provider_policy.get("provider_call_count") or 0) != 0:
        blockers.append("semantic_runtime_live_ab_preflight_provider_policy_allows_calls")
    evidence = payload.get("evidence_validation") if isinstance(payload.get("evidence_validation"), dict) else {}
    if float(evidence.get("fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_live_ab_preflight_evidence_fail_open")
    if float(evidence.get("question_lane_citation_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_live_ab_preflight_question_lane_citation")
    source_bundle = payload.get("source_bundle") if isinstance(payload.get("source_bundle"), dict) else {}
    if source_bundle.get("nearline_verdict_ceiling") != "NEARLINE_RETRIEVAL_PROJECTION":
        blockers.append("semantic_runtime_live_ab_preflight_bad_source_bundle_nearline_ceiling")
    planned_arms = set(payload.get("planned_arms") or [])
    for arm in ("current_rag_runtime", "legacy_runtime_or_projection", "rich_leaf_promoted_context", "artifact_first_llm_judge"):
        if arm not in planned_arms:
            blockers.append(f"semantic_runtime_live_ab_preflight_missing_planned_arm:{arm}")
    by_layer = payload.get("not_exercised_by_layer") if isinstance(payload.get("not_exercised_by_layer"), dict) else {}
    runtime_not_exercised = set(by_layer.get("runtime_not_exercised") or [])
    release_not_exercised = set(by_layer.get("release_not_exercised") or [])
    for required in ("production_rag_retrieval", "live_llm_semantic_judgment", "live_runtime_latency", "live_runtime_token_usage"):
        if required not in runtime_not_exercised:
            blockers.append(f"semantic_runtime_live_ab_preflight_missing_runtime_not_exercised:{required}")
    for required in ("production_default_decision", "release_truth_governance"):
        if required not in release_not_exercised:
            blockers.append(f"semantic_runtime_live_ab_preflight_missing_release_not_exercised:{required}")


def _check_semantic_runtime_live_ab(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") not in {
        "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED",
        "NO_GO_LIVE_PREFLIGHT_INVALID",
        "NO_GO_LIVE_RUNTIME_NOT_EXERCISED",
    }:
        blockers.append(f"semantic_runtime_live_ab_bad_verdict:{payload.get('verdict')}")
    if payload.get("verdict_ceiling") != "LIVE_RUNTIME_NOT_EXERCISED":
        blockers.append(f"semantic_runtime_live_ab_bad_ceiling:{payload.get('verdict_ceiling')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("semantic_runtime_live_ab_quality_claim_allowed")
    if payload.get("execution_mode") not in {"live_runtime_ab_blocked", "live_runtime_ab_not_exercised"}:
        blockers.append(f"semantic_runtime_live_ab_bad_execution_mode:{payload.get('execution_mode')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"semantic_runtime_live_ab_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("semantic_runtime_live_ab_review_flags_invalid")
    if classification.get("semantic_runtime_live_ab") is not True:
        blockers.append("semantic_runtime_live_ab_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("live_runtime_executed") is not False:
        blockers.append("semantic_runtime_live_ab_live_runtime_executed")
    if int(summary.get("provider_call_count") or 0) != 0:
        blockers.append("semantic_runtime_live_ab_provider_calls_present")
    if int(summary.get("live_case_count") or 0) != 0:
        blockers.append("semantic_runtime_live_ab_live_cases_present")
    runtime_entry = payload.get("runtime_entry") if isinstance(payload.get("runtime_entry"), dict) else {}
    if runtime_entry.get("runtime_exercised") is not False or runtime_entry.get("entrypoint") != "not_exercised":
        blockers.append("semantic_runtime_live_ab_runtime_entry_exercised")
    provider_policy = payload.get("provider_call_policy") if isinstance(payload.get("provider_call_policy"), dict) else {}
    if provider_policy.get("provider_calls_allowed") is not False or int(provider_policy.get("provider_call_count") or 0) != 0:
        blockers.append("semantic_runtime_live_ab_provider_policy_allows_calls")
    arms = payload.get("arms") if isinstance(payload.get("arms"), list) else []
    planned_arms = {"current_rag_runtime", "legacy_runtime_or_projection", "rich_leaf_promoted_context", "artifact_first_llm_judge"}
    seen_arms = {str(arm.get("arm")) for arm in arms if isinstance(arm, dict)}
    for arm in sorted(planned_arms - seen_arms):
        blockers.append(f"semantic_runtime_live_ab_missing_arm:{arm}")
    for arm in arms:
        if not isinstance(arm, dict):
            blockers.append("semantic_runtime_live_ab_arm_not_object")
            continue
        if arm.get("status") != "not_exercised":
            blockers.append(f"semantic_runtime_live_ab_arm_exercised:{arm.get('arm')}:{arm.get('status')}")
        if int(arm.get("provider_call_count") or 0) != 0:
            blockers.append(f"semantic_runtime_live_ab_arm_provider_calls:{arm.get('arm')}")
        if arm.get("quality_claim_allowed") is not False:
            blockers.append(f"semantic_runtime_live_ab_arm_quality_claim:{arm.get('arm')}")
    by_layer = payload.get("not_exercised_by_layer") if isinstance(payload.get("not_exercised_by_layer"), dict) else {}
    runtime_not_exercised = set(by_layer.get("runtime_not_exercised") or [])
    for required in ("production_rag_retrieval", "legacy_runtime_live_path", "live_llm_semantic_judgment", "live_runtime_latency", "live_runtime_token_usage"):
        if required not in runtime_not_exercised:
            blockers.append(f"semantic_runtime_live_ab_missing_runtime_not_exercised:{required}")


def _check_semantic_runtime_near_live_smoke(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"semantic_runtime_near_live_smoke_failed:{payload.get('verdict')}")
    if payload.get("verdict_ceiling") != "NEAR_LIVE_LOCAL_ADAPTER_ONLY":
        blockers.append(f"semantic_runtime_near_live_smoke_bad_ceiling:{payload.get('verdict_ceiling')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("semantic_runtime_near_live_smoke_quality_claim_allowed")
    if payload.get("execution_mode") != "near_live_runtime":
        blockers.append(f"semantic_runtime_near_live_smoke_bad_execution_mode:{payload.get('execution_mode')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"semantic_runtime_near_live_smoke_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("semantic_runtime_near_live_smoke_review_flags_invalid")
    if classification.get("semantic_runtime_near_live_smoke") is not True:
        blockers.append("semantic_runtime_near_live_smoke_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"semantic_runtime_near_live_smoke_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("smoke_case_count") or 0) <= 0:
        blockers.append("semantic_runtime_near_live_smoke_no_cases")
    if float(summary.get("answerable_rate") or 0.0) <= 0.0:
        blockers.append("semantic_runtime_near_live_smoke_no_answerable_cases")
    if float(summary.get("evidence_citation_rate") or 0.0) <= 0.0:
        blockers.append("semantic_runtime_near_live_smoke_no_citations")
    if float(summary.get("fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_near_live_smoke_fail_open")
    if float(summary.get("question_lane_citation_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_near_live_smoke_question_lane_citation")
    if summary.get("live_runtime_executed") is not False:
        blockers.append("semantic_runtime_near_live_smoke_live_runtime_executed")
    if int(summary.get("provider_call_count") or 0) != 0:
        blockers.append("semantic_runtime_near_live_smoke_provider_calls_present")
    runtime_entry = payload.get("runtime_entry") if isinstance(payload.get("runtime_entry"), dict) else {}
    if runtime_entry.get("entrypoint") != "local_compiled_context_adapter":
        blockers.append(f"semantic_runtime_near_live_smoke_bad_runtime_entry:{runtime_entry.get('entrypoint')}")
    if runtime_entry.get("runtime_exercised") is not True:
        blockers.append("semantic_runtime_near_live_smoke_runtime_not_exercised")
    provider_policy = payload.get("provider_call_policy") if isinstance(payload.get("provider_call_policy"), dict) else {}
    if provider_policy.get("provider_calls_allowed") is not False or int(provider_policy.get("provider_call_count") or 0) != 0:
        blockers.append("semantic_runtime_near_live_smoke_provider_policy_allows_calls")
    evidence = payload.get("evidence_validation") if isinstance(payload.get("evidence_validation"), dict) else {}
    if float(evidence.get("fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_near_live_smoke_evidence_fail_open")
    if float(evidence.get("question_lane_citation_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_near_live_smoke_evidence_question_lane_citation")
    rows = payload.get("smoke_rows") if isinstance(payload.get("smoke_rows"), list) else []
    if int(summary.get("smoke_case_count") or 0) != len(rows):
        blockers.append("semantic_runtime_near_live_smoke_row_count_mismatch")
    for row in rows:
        if not isinstance(row, dict):
            blockers.append("semantic_runtime_near_live_smoke_row_not_object")
            continue
        answer = row.get("runtime_answer") if isinstance(row.get("runtime_answer"), dict) else {}
        if row.get("answerable") is True and not answer.get("cited_source_ref_ids"):
            blockers.append(f"semantic_runtime_near_live_smoke_answer_without_citation:{row.get('case_id')}")
        if int(row.get("question_lane_citation_count") or 0) != 0:
            blockers.append(f"semantic_runtime_near_live_smoke_row_question_lane_citation:{row.get('case_id')}")
    by_layer = payload.get("not_exercised_by_layer") if isinstance(payload.get("not_exercised_by_layer"), dict) else {}
    runtime_not_exercised = set(by_layer.get("runtime_not_exercised") or [])
    release_not_exercised = set(by_layer.get("release_not_exercised") or [])
    for required in ("production_rag_retrieval", "live_llm_semantic_judgment", "live_runtime_latency", "live_runtime_token_usage"):
        if required not in runtime_not_exercised:
            blockers.append(f"semantic_runtime_near_live_smoke_missing_runtime_not_exercised:{required}")
    for required in ("production_default_decision", "release_truth_governance"):
        if required not in release_not_exercised:
            blockers.append(f"semantic_runtime_near_live_smoke_missing_release_not_exercised:{required}")


def _check_semantic_runtime_near_live_shadow_ab(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"semantic_runtime_near_live_shadow_ab_failed:{payload.get('verdict')}")
    if payload.get("verdict_ceiling") != "NEAR_LIVE_SHADOW_LOCAL_ADAPTER_ONLY":
        blockers.append(f"semantic_runtime_near_live_shadow_ab_bad_ceiling:{payload.get('verdict_ceiling')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("semantic_runtime_near_live_shadow_ab_quality_claim_allowed")
    if payload.get("execution_mode") != "near_live_shadow":
        blockers.append(f"semantic_runtime_near_live_shadow_ab_bad_execution_mode:{payload.get('execution_mode')}")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"semantic_runtime_near_live_shadow_ab_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("semantic_runtime_near_live_shadow_ab_review_flags_invalid")
    if classification.get("semantic_runtime_near_live_shadow_ab") is not True:
        blockers.append("semantic_runtime_near_live_shadow_ab_classification_invalid")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"semantic_runtime_near_live_shadow_ab_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("shadow_case_count") or 0) <= 0:
        blockers.append("semantic_runtime_near_live_shadow_ab_no_cases")
    if float(summary.get("local_adapter_answerable_rate") or 0.0) < float(summary.get("current_rag_answerable_rate") or 0.0):
        blockers.append("semantic_runtime_near_live_shadow_ab_local_adapter_below_rag_proxy")
    if float(summary.get("local_adapter_evidence_citation_rate") or 0.0) <= 0.0:
        blockers.append("semantic_runtime_near_live_shadow_ab_no_local_adapter_citations")
    if float(summary.get("local_adapter_fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_near_live_shadow_ab_local_adapter_fail_open")
    if float(summary.get("local_adapter_question_lane_citation_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_near_live_shadow_ab_question_lane_citation")
    if float(summary.get("local_adapter_token_delta_vs_rag_proxy") or 0.0) > 0.0:
        blockers.append("semantic_runtime_near_live_shadow_ab_token_proxy_regression")
    if summary.get("live_runtime_executed") is not False:
        blockers.append("semantic_runtime_near_live_shadow_ab_live_runtime_executed")
    if int(summary.get("provider_call_count") or 0) != 0:
        blockers.append("semantic_runtime_near_live_shadow_ab_provider_calls_present")
    runtime_entry = payload.get("runtime_entry") if isinstance(payload.get("runtime_entry"), dict) else {}
    if runtime_entry.get("entrypoint") != "local_compiled_context_adapter":
        blockers.append(f"semantic_runtime_near_live_shadow_ab_bad_runtime_entry:{runtime_entry.get('entrypoint')}")
    if runtime_entry.get("runtime_exercised") is not True:
        blockers.append("semantic_runtime_near_live_shadow_ab_runtime_not_exercised")
    provider_policy = payload.get("provider_call_policy") if isinstance(payload.get("provider_call_policy"), dict) else {}
    if provider_policy.get("provider_calls_allowed") is not False or int(provider_policy.get("provider_call_count") or 0) != 0:
        blockers.append("semantic_runtime_near_live_shadow_ab_provider_policy_allows_calls")
    table = payload.get("effect_table") if isinstance(payload.get("effect_table"), list) else []
    arms = {row.get("arm"): row for row in table if isinstance(row, dict)}
    for arm in ("current_rag_lexical_proxy", "rich_leaf_local_adapter"):
        if arm not in arms:
            blockers.append(f"semantic_runtime_near_live_shadow_ab_missing_arm:{arm}")
    adapter = arms.get("rich_leaf_local_adapter") or {}
    if float(adapter.get("fail_open_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_near_live_shadow_ab_adapter_row_fail_open")
    if float(adapter.get("question_lane_citation_rate") or 0.0) != 0.0:
        blockers.append("semantic_runtime_near_live_shadow_ab_adapter_row_question_lane")
    by_layer = payload.get("not_exercised_by_layer") if isinstance(payload.get("not_exercised_by_layer"), dict) else {}
    runtime_not_exercised = set(by_layer.get("runtime_not_exercised") or [])
    release_not_exercised = set(by_layer.get("release_not_exercised") or [])
    for required in ("production_rag_retrieval", "live_llm_semantic_judgment", "live_runtime_latency", "live_runtime_token_usage"):
        if required not in runtime_not_exercised:
            blockers.append(f"semantic_runtime_near_live_shadow_ab_missing_runtime_not_exercised:{required}")
    for required in ("production_default_decision", "release_truth_governance"):
        if required not in release_not_exercised:
            blockers.append(f"semantic_runtime_near_live_shadow_ab_missing_release_not_exercised:{required}")


def _check_shadow_residual_work_orders(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_work_orders_failed:{payload.get('verdict')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_work_orders_review_flags_invalid")
    if classification.get("shadow_residual_work_orders") is not True:
        blockers.append("shadow_residual_work_orders_classification_invalid")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed", "quality_claim_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_work_orders_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    orders = payload.get("compiler_work_orders") if isinstance(payload.get("compiler_work_orders"), list) else []
    non_joinable = payload.get("non_joinable_residuals") if isinstance(payload.get("non_joinable_residuals"), list) else []
    if summary.get("work_order_count") != len(orders):
        blockers.append("shadow_residual_work_orders_count_mismatch")
    if summary.get("non_joinable_residual_count") != len(non_joinable):
        blockers.append("shadow_residual_work_orders_non_joinable_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"shadow_residual_work_orders_blockers_present:{summary.get('blocker_count')}")
    for order in orders:
        if not isinstance(order, dict):
            blockers.append("shadow_residual_work_order_not_object")
            continue
        leaf_id = order.get("leaf_id")
        if not order.get("work_order_id") or not leaf_id:
            blockers.append(f"shadow_residual_work_order_missing_join_key:{leaf_id}")
        if order.get("trigger_reason") not in {
            "local_adapter_runtime_residual",
            "preventive_negative_evidence_guard_review",
        }:
            blockers.append(f"shadow_residual_work_order_bad_trigger:{leaf_id}:{order.get('trigger_reason')}")
        if order.get("candidate_only") is not True or order.get("review_only") is not True:
            blockers.append(f"shadow_residual_work_order_review_flags_invalid:{leaf_id}")
        if (
            order.get("apply_allowed") is not False
            or order.get("runtime_install_allowed") is not False
            or order.get("release_truth_claimed") is not False
        ):
            blockers.append(f"shadow_residual_work_order_authority_allowed:{leaf_id}")
    for residual in non_joinable:
        if not isinstance(residual, dict):
            blockers.append("shadow_residual_non_joinable_not_object")
            continue
        if residual.get("join_blocker") != "missing_leaf_id":
            blockers.append(f"shadow_residual_non_joinable_bad_reason:{residual.get('case_id')}:{residual.get('join_blocker')}")


def _check_shadow_residual_review_packets(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_review_packets_failed:{payload.get('verdict')}")
    if payload.get("input_schema") != "luban_rich_leaf_shadow_residual_work_orders.v1":
        blockers.append(f"shadow_residual_review_packets_bad_input_schema:{payload.get('input_schema')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_review_packets_review_flags_invalid")
    if classification.get("shadow_residual_review_packets") is not True:
        blockers.append("shadow_residual_review_packets_classification_invalid")
    for key in (
        "decisions_recorded",
        "patch_generation_allowed",
        "runtime_install_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_review_packets_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    packets = payload.get("review_packets") if isinstance(payload.get("review_packets"), list) else []
    if summary.get("review_packet_count") != len(packets):
        blockers.append("shadow_residual_review_packets_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"shadow_residual_review_packets_blockers_present:{summary.get('blocker_count')}")
    for packet in packets:
        if not isinstance(packet, dict):
            blockers.append("shadow_residual_review_packet_not_object")
            continue
        packet_id = packet.get("packet_id")
        leaf_id = packet.get("leaf_id")
        if not packet_id or not packet.get("work_order_id") or not leaf_id:
            blockers.append(f"shadow_residual_review_packet_missing_join_key:{packet_id}:{leaf_id}")
        if packet.get("review_scope") not in {
            "runtime_residual_source_ref_review",
            "preventive_negative_evidence_guard_review",
        }:
            blockers.append(f"shadow_residual_review_packet_bad_scope:{packet_id}:{packet.get('review_scope')}")
        if packet.get("decision_recorded") is not False:
            blockers.append(f"shadow_residual_review_packet_decision_recorded:{packet_id}")
        if (
            packet.get("patch_generation_allowed") is not False
            or packet.get("apply_allowed") is not False
            or packet.get("runtime_install_allowed") is not False
            or packet.get("release_truth_claimed") is not False
        ):
            blockers.append(f"shadow_residual_review_packet_authority_allowed:{packet_id}")
        if packet.get("candidate_only") is not True or packet.get("review_only") is not True:
            blockers.append(f"shadow_residual_review_packet_review_flags_invalid:{packet_id}")


def _check_shadow_residual_review_decision_validation(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    verdict = payload.get("verdict")
    if verdict not in {"PASS", "INCOMPLETE"}:
        blockers.append(f"shadow_residual_review_decision_validation_bad_verdict:{verdict}")
    if payload.get("input_schema") != "luban_rich_leaf_shadow_residual_review_packets.v1":
        blockers.append(f"shadow_residual_review_decision_validation_bad_input_schema:{payload.get('input_schema')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_review_decision_validation_review_flags_invalid")
    if classification.get("shadow_residual_review_decision_validation") is not True:
        blockers.append("shadow_residual_review_decision_validation_classification_invalid")
    for key in ("patch_generation_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed", "quality_claim_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_review_decision_validation_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for key in ("invalid_decision_count", "duplicate_decision_count", "blocker_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"shadow_residual_review_decision_validation_{key}:{summary.get(key)}")
    if int(summary.get("decision_count") or 0) and classification.get("decisions_recorded") is not True:
        blockers.append("shadow_residual_review_decision_validation_decision_count_without_record_flag")


def _check_shadow_residual_review_decision_seed(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_review_decision_seed_failed:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("review_packets") != "luban_rich_leaf_shadow_residual_review_packets.v1":
        blockers.append("shadow_residual_review_decision_seed_bad_review_packets_schema")
    if input_schemas.get("decision_validation") != "luban_rich_leaf_shadow_residual_review_decision_validation.v1":
        blockers.append("shadow_residual_review_decision_seed_bad_decision_validation_schema")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_review_decision_seed_review_flags_invalid")
    if classification.get("shadow_residual_review_decision_seed") is not True:
        blockers.append("shadow_residual_review_decision_seed_classification_invalid")
    if classification.get("suggestion_only") is not True:
        blockers.append("shadow_residual_review_decision_seed_not_suggestion_only")
    for key in ("decisions_recorded", "patch_generation_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed", "quality_claim_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_review_decision_seed_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    suggestions = payload.get("decision_seed_suggestions") if isinstance(payload.get("decision_seed_suggestions"), list) else []
    if summary.get("seed_suggestion_count") != len(suggestions):
        blockers.append("shadow_residual_review_decision_seed_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"shadow_residual_review_decision_seed_blockers_present:{summary.get('blocker_count')}")
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            blockers.append("shadow_residual_review_decision_seed_entry_not_object")
            continue
        seed_id = suggestion.get("seed_id")
        if not seed_id or not suggestion.get("packet_id"):
            blockers.append(f"shadow_residual_review_decision_seed_missing_join_key:{seed_id}")
        if suggestion.get("reviewer_must_confirm") is not True or suggestion.get("decision_recorded") is not False:
            blockers.append(f"shadow_residual_review_decision_seed_confirmation_or_decision_invalid:{seed_id}")
        if (
            suggestion.get("patch_generation_allowed") is not False
            or suggestion.get("runtime_install_allowed") is not False
            or suggestion.get("release_truth_claimed") is not False
        ):
            blockers.append(f"shadow_residual_review_decision_seed_authority_allowed_entry:{seed_id}")


def _check_shadow_residual_review_decisions(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_review_decisions_failed:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("review_packets") != "luban_rich_leaf_shadow_residual_review_packets.v1":
        blockers.append("shadow_residual_review_decisions_bad_review_packets_schema")
    if input_schemas.get("decision_seed") != "luban_rich_leaf_shadow_residual_review_decision_seed.v1":
        blockers.append("shadow_residual_review_decisions_bad_decision_seed_schema")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_review_decisions_review_flags_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("shadow_residual_review_decisions_shadow_flag_invalid")
    for key in ("patch_generation_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed", "quality_claim_allowed"):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_review_decisions_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    if summary.get("decision_count") != len(decisions):
        blockers.append("shadow_residual_review_decisions_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"shadow_residual_review_decisions_blockers_present:{summary.get('blocker_count')}")
    if bool(decisions) != bool(classification.get("decisions_recorded")):
        blockers.append("shadow_residual_review_decisions_record_flag_mismatch")
    for decision in decisions:
        if not isinstance(decision, dict):
            blockers.append("shadow_residual_review_decision_entry_not_object")
            continue
        packet_id = decision.get("packet_id")
        if not packet_id or not decision.get("decision"):
            blockers.append(f"shadow_residual_review_decision_missing_join_key:{packet_id}")
        if decision.get("reviewer_role") != "ai_council_shadow_reviewer" or not decision.get("reviewer_id"):
            blockers.append(f"shadow_residual_review_decision_reviewer_invalid:{packet_id}")
        if not decision.get("rationale") or decision.get("confidence") not in {"low", "medium", "high"}:
            blockers.append(f"shadow_residual_review_decision_rationale_or_confidence_invalid:{packet_id}")
        if decision.get("decision_recorded") is not True or decision.get("shadow_only") is not True:
            blockers.append(f"shadow_residual_review_decision_record_or_shadow_flag_invalid:{packet_id}")
        if (
            decision.get("patch_generation_allowed") is not False
            or decision.get("runtime_install_allowed") is not False
            or decision.get("release_truth_claimed") is not False
        ):
            blockers.append(f"shadow_residual_review_decision_authority_allowed:{packet_id}")


def _check_shadow_residual_review_decision_validation_alignment(
    decisions_payload: dict[str, Any], validation_payload: dict[str, Any], blockers: list[str]
) -> None:
    decisions_summary = decisions_payload.get("summary") if isinstance(decisions_payload.get("summary"), dict) else {}
    validation_summary = validation_payload.get("summary") if isinstance(validation_payload.get("summary"), dict) else {}
    decision_count = int(decisions_summary.get("decision_count") or 0)
    if decision_count and validation_payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_review_decisions_validation_not_pass:{validation_payload.get('verdict')}")
    if decision_count and int(validation_summary.get("decision_count") or 0) != decision_count:
        blockers.append(
            f"shadow_residual_review_decisions_validation_count_mismatch:{decision_count}:{validation_summary.get('decision_count')}"
        )
    if decision_count and int(validation_summary.get("missing_decision_count") or 0) != 0:
        blockers.append(
            f"shadow_residual_review_decisions_validation_missing:{validation_summary.get('missing_decision_count')}"
        )


def _check_shadow_residual_audit_record(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_audit_record_failed:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("review_packets") != "luban_rich_leaf_shadow_residual_review_packets.v1":
        blockers.append("shadow_residual_audit_record_bad_review_packets_schema")
    if input_schemas.get("review_decisions") != "luban_rich_leaf_shadow_residual_review_decisions.v1":
        blockers.append("shadow_residual_audit_record_bad_review_decisions_schema")
    if input_schemas.get("decision_validation") != "luban_rich_leaf_shadow_residual_review_decision_validation.v1":
        blockers.append("shadow_residual_audit_record_bad_decision_validation_schema")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_audit_record_review_flags_invalid")
    if classification.get("shadow_residual_audit_record") is not True:
        blockers.append("shadow_residual_audit_record_classification_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("shadow_residual_audit_record_shadow_flag_invalid")
    for key in (
        "patch_generation_allowed",
        "source_ref_mutation_allowed",
        "runtime_install_allowed",
        "runtime_guard_enforcement_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
        "learner_memory_write_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_audit_record_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    records = payload.get("shadow_residual_audit_records") if isinstance(payload.get("shadow_residual_audit_records"), list) else []
    if summary.get("audit_record_count") != len(records):
        blockers.append("shadow_residual_audit_record_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"shadow_residual_audit_record_blockers_present:{summary.get('blocker_count')}")
    action_fields = {
        "guard_review_required_count": "guard_review_required",
        "source_ref_reaudit_required_count": "source_ref_reaudit_required",
        "leaf_retaxonomy_required_count": "leaf_retaxonomy_required",
        "dismissed_after_shadow_review_count": "dismissed_after_shadow_review",
    }
    for summary_key, action in action_fields.items():
        if int(summary.get(summary_key) or 0) != sum(
            1 for record in records if isinstance(record, dict) and record.get("next_compiler_action") == action
        ):
            blockers.append(f"shadow_residual_audit_record_action_count_mismatch:{summary_key}")
    for record in records:
        if not isinstance(record, dict):
            blockers.append("shadow_residual_audit_record_entry_not_object")
            continue
        record_id = record.get("audit_record_id")
        if not record_id or not record.get("packet_id") or not record.get("work_order_id") or not record.get("leaf_id"):
            blockers.append(f"shadow_residual_audit_record_missing_join_key:{record_id}")
        if record.get("next_compiler_action") not in {
            "guard_review_required",
            "source_ref_reaudit_required",
            "leaf_retaxonomy_required",
            "dismissed_after_shadow_review",
        }:
            blockers.append(f"shadow_residual_audit_record_unknown_action:{record_id}:{record.get('next_compiler_action')}")
        if record.get("candidate_only") is not True or record.get("review_only") is not True or record.get("shadow_only") is not True:
            blockers.append(f"shadow_residual_audit_record_flags_invalid:{record_id}")
        for key in (
            "patch_generation_allowed",
            "source_ref_mutation_allowed",
            "runtime_install_allowed",
            "runtime_guard_enforcement_allowed",
            "release_truth_claimed",
            "quality_claim_allowed",
            "learner_memory_write_allowed",
        ):
            if record.get(key) is not False:
                blockers.append(f"shadow_residual_audit_record_entry_authority_allowed:{record_id}:{key}")


def _check_shadow_residual_guard_patch_plan(
    payload: dict[str, Any], blockers: list[str], *, shadow_residual_audit_record: dict[str, Any]
) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_guard_patch_plan_failed:{payload.get('verdict')}")
    if payload.get("input_schema") != "luban_rich_leaf_shadow_residual_audit_record.v1":
        blockers.append(f"shadow_residual_guard_patch_plan_bad_input_schema:{payload.get('input_schema')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_guard_patch_plan_review_flags_invalid")
    if classification.get("shadow_residual_guard_patch_plan") is not True:
        blockers.append("shadow_residual_guard_patch_plan_classification_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("shadow_residual_guard_patch_plan_shadow_flag_invalid")
    for key in (
        "patch_generation_allowed",
        "source_ref_mutation_allowed",
        "runtime_install_allowed",
        "runtime_guard_enforcement_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
        "learner_memory_write_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_guard_patch_plan_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    items = payload.get("guard_plan_items") if isinstance(payload.get("guard_plan_items"), list) else []
    if summary.get("guard_plan_item_count") != len(items):
        blockers.append("shadow_residual_guard_patch_plan_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"shadow_residual_guard_patch_plan_blockers_present:{summary.get('blocker_count')}")
    audit_records = (
        shadow_residual_audit_record.get("shadow_residual_audit_records")
        if isinstance(shadow_residual_audit_record.get("shadow_residual_audit_records"), list)
        else []
    )
    guard_required_ids = {
        record.get("audit_record_id")
        for record in audit_records
        if isinstance(record, dict) and record.get("next_compiler_action") == "guard_review_required"
    }
    item_audit_ids = {item.get("audit_record_id") for item in items if isinstance(item, dict)}
    if item_audit_ids != guard_required_ids:
        blockers.append(
            f"shadow_residual_guard_patch_plan_audit_alignment_mismatch:{len(item_audit_ids)}:{len(guard_required_ids)}"
        )
    if int(summary.get("audit_record_count") or 0) != len(audit_records):
        blockers.append("shadow_residual_guard_patch_plan_audit_record_count_mismatch")
    for item in items:
        if not isinstance(item, dict):
            blockers.append("shadow_residual_guard_patch_plan_item_not_object")
            continue
        item_id = item.get("guard_plan_item_id")
        if not item_id or not item.get("audit_record_id") or not item.get("packet_id") or not item.get("work_order_id") or not item.get("leaf_id"):
            blockers.append(f"shadow_residual_guard_patch_plan_missing_join_key:{item_id}")
        if item.get("planned_guard_action") != "block_positive_context_until_source_ref_reviewed":
            blockers.append(f"shadow_residual_guard_patch_plan_unknown_action:{item_id}:{item.get('planned_guard_action')}")
        if item.get("plan_status") != "review_required":
            blockers.append(f"shadow_residual_guard_patch_plan_status_invalid:{item_id}:{item.get('plan_status')}")
        if item.get("candidate_only") is not True or item.get("review_only") is not True:
            blockers.append(f"shadow_residual_guard_patch_plan_flags_invalid:{item_id}")
        for key in (
            "patch_generation_allowed",
            "source_ref_mutation_allowed",
            "runtime_install_allowed",
            "runtime_guard_enforcement_allowed",
            "release_truth_claimed",
            "quality_claim_allowed",
            "learner_memory_write_allowed",
        ):
            if item.get(key) is not False:
                blockers.append(f"shadow_residual_guard_patch_plan_item_authority_allowed:{item_id}:{key}")


def _check_shadow_residual_guard_review_packets(
    payload: dict[str, Any], blockers: list[str], *, shadow_residual_guard_patch_plan: dict[str, Any]
) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_guard_review_packets_failed:{payload.get('verdict')}")
    if payload.get("input_schema") != "luban_rich_leaf_shadow_residual_guard_patch_plan.v1":
        blockers.append(f"shadow_residual_guard_review_packets_bad_input_schema:{payload.get('input_schema')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_guard_review_packets_review_flags_invalid")
    if classification.get("shadow_residual_guard_review_packets") is not True:
        blockers.append("shadow_residual_guard_review_packets_classification_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("shadow_residual_guard_review_packets_shadow_flag_invalid")
    if classification.get("decisions_recorded") is not False:
        blockers.append("shadow_residual_guard_review_packets_decisions_recorded")
    for key in (
        "patch_generation_allowed",
        "source_ref_mutation_allowed",
        "runtime_install_allowed",
        "runtime_guard_enforcement_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
        "learner_memory_write_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_guard_review_packets_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    packets = payload.get("guard_review_packets") if isinstance(payload.get("guard_review_packets"), list) else []
    if summary.get("guard_review_packet_count") != len(packets):
        blockers.append("shadow_residual_guard_review_packets_count_mismatch")
    if summary.get("decision_count") not in (0, False):
        blockers.append(f"shadow_residual_guard_review_packets_decision_count_nonzero:{summary.get('decision_count')}")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"shadow_residual_guard_review_packets_blockers_present:{summary.get('blocker_count')}")

    plan_items = (
        shadow_residual_guard_patch_plan.get("guard_plan_items")
        if isinstance(shadow_residual_guard_patch_plan.get("guard_plan_items"), list)
        else []
    )
    plan_item_ids = {item.get("guard_plan_item_id") for item in plan_items if isinstance(item, dict)}
    packet_plan_ids = {packet.get("guard_plan_item_id") for packet in packets if isinstance(packet, dict)}
    if packet_plan_ids != plan_item_ids:
        blockers.append(f"shadow_residual_guard_review_packets_plan_alignment_mismatch:{len(packet_plan_ids)}:{len(plan_item_ids)}")
    if int(summary.get("guard_plan_item_count") or 0) != len(plan_items):
        blockers.append("shadow_residual_guard_review_packets_plan_item_count_mismatch")

    allowed = {
        "confirm_guard_patch_candidate",
        "request_guard_scope_narrowing",
        "request_source_ref_reaudit",
        "reject_guard_not_needed",
    }
    for packet in packets:
        if not isinstance(packet, dict):
            blockers.append("shadow_residual_guard_review_packet_not_object")
            continue
        packet_id = packet.get("guard_review_packet_id")
        if not packet_id or not packet.get("guard_plan_item_id") or not packet.get("audit_record_id") or not packet.get("work_order_id") or not packet.get("leaf_id"):
            blockers.append(f"shadow_residual_guard_review_packet_missing_join_key:{packet_id}")
        if packet.get("review_scope") != "runtime_guard_candidate_review":
            blockers.append(f"shadow_residual_guard_review_packet_scope_invalid:{packet_id}:{packet.get('review_scope')}")
        if packet.get("planned_guard_action") != "block_positive_context_until_source_ref_reviewed":
            blockers.append(f"shadow_residual_guard_review_packet_unknown_guard:{packet_id}:{packet.get('planned_guard_action')}")
        if set(packet.get("allowed_decisions") or []) != allowed:
            blockers.append(f"shadow_residual_guard_review_packet_allowed_decisions_invalid:{packet_id}")
        if packet.get("decision_recorded") is not False:
            blockers.append(f"shadow_residual_guard_review_packet_decision_recorded:{packet_id}")
        if packet.get("candidate_only") is not True or packet.get("review_only") is not True:
            blockers.append(f"shadow_residual_guard_review_packet_flags_invalid:{packet_id}")
        trace = packet.get("evidence_trace") if isinstance(packet.get("evidence_trace"), dict) else {}
        if not trace.get("record_ids") or not trace.get("source_lanes") or not trace.get("reason_codes"):
            blockers.append(f"shadow_residual_guard_review_packet_trace_missing:{packet_id}")
        for key in (
            "patch_generation_allowed",
            "source_ref_mutation_allowed",
            "runtime_install_allowed",
            "runtime_guard_enforcement_allowed",
            "release_truth_claimed",
            "quality_claim_allowed",
            "learner_memory_write_allowed",
        ):
            if packet.get(key) is not False:
                blockers.append(f"shadow_residual_guard_review_packet_authority_allowed:{packet_id}:{key}")


def _check_shadow_residual_guard_review_decisions(
    payload: dict[str, Any], blockers: list[str], *, shadow_residual_guard_review_packets: dict[str, Any]
) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_guard_review_decisions_failed:{payload.get('verdict')}")
    if payload.get("input_schema") != "luban_rich_leaf_shadow_residual_guard_review_packets.v1":
        blockers.append(f"shadow_residual_guard_review_decisions_bad_input_schema:{payload.get('input_schema')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_guard_review_decisions_review_flags_invalid")
    if classification.get("shadow_residual_guard_review_decisions") is not True:
        blockers.append("shadow_residual_guard_review_decisions_classification_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("shadow_residual_guard_review_decisions_shadow_flag_invalid")
    if classification.get("decisions_recorded") is not True:
        blockers.append("shadow_residual_guard_review_decisions_not_recorded")
    if classification.get("human_reviewer_signoff") is not False or classification.get("governance_signoff") is not False:
        blockers.append("shadow_residual_guard_review_decisions_signoff_claimed")
    for key in (
        "patch_generation_allowed",
        "source_ref_mutation_allowed",
        "runtime_install_allowed",
        "runtime_guard_enforcement_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
        "learner_memory_write_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_guard_review_decisions_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    if summary.get("decision_count") != len(decisions):
        blockers.append("shadow_residual_guard_review_decisions_count_mismatch")
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"shadow_residual_guard_review_decisions_blockers_present:{summary.get('blocker_count')}")

    packets = (
        shadow_residual_guard_review_packets.get("guard_review_packets")
        if isinstance(shadow_residual_guard_review_packets.get("guard_review_packets"), list)
        else []
    )
    packet_ids = {packet.get("guard_review_packet_id") for packet in packets if isinstance(packet, dict)}
    decision_packet_ids = {decision.get("guard_review_packet_id") for decision in decisions if isinstance(decision, dict)}
    if decision_packet_ids != packet_ids:
        blockers.append(f"shadow_residual_guard_review_decisions_packet_alignment_mismatch:{len(decision_packet_ids)}:{len(packet_ids)}")
    if int(summary.get("guard_review_packet_count") or 0) != len(packets):
        blockers.append("shadow_residual_guard_review_decisions_packet_count_mismatch")

    allowed = {
        "confirm_guard_patch_candidate",
        "request_guard_scope_narrowing",
        "request_source_ref_reaudit",
        "reject_guard_not_needed",
    }
    for decision in decisions:
        if not isinstance(decision, dict):
            blockers.append("shadow_residual_guard_review_decision_not_object")
            continue
        decision_id = decision.get("decision_id")
        if not decision_id or not decision.get("guard_review_packet_id") or not decision.get("guard_plan_item_id") or not decision.get("work_order_id") or not decision.get("leaf_id"):
            blockers.append(f"shadow_residual_guard_review_decision_missing_join_key:{decision_id}")
        if decision.get("decision") not in allowed:
            blockers.append(f"shadow_residual_guard_review_decision_unknown:{decision_id}:{decision.get('decision')}")
        if decision.get("decision_recorded") is not True or decision.get("shadow_only") is not True:
            blockers.append(f"shadow_residual_guard_review_decision_flags_invalid:{decision_id}")
        if decision.get("human_reviewer_signoff") is not False or decision.get("governance_signoff") is not False:
            blockers.append(f"shadow_residual_guard_review_decision_signoff_claimed:{decision_id}")
        trace = decision.get("evidence_trace") if isinstance(decision.get("evidence_trace"), dict) else {}
        if not trace.get("record_ids") or not trace.get("source_lanes") or not trace.get("reason_codes"):
            blockers.append(f"shadow_residual_guard_review_decision_trace_missing:{decision_id}")
        for key in (
            "patch_generation_allowed",
            "source_ref_mutation_allowed",
            "runtime_install_allowed",
            "runtime_guard_enforcement_allowed",
            "release_truth_claimed",
            "quality_claim_allowed",
            "learner_memory_write_allowed",
        ):
            if decision.get(key) is not False:
                blockers.append(f"shadow_residual_guard_review_decision_authority_allowed:{decision_id}:{key}")


def _check_shadow_residual_guard_review_decision_validation(
    payload: dict[str, Any], blockers: list[str], *, shadow_residual_guard_review_decisions: dict[str, Any]
) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_guard_review_decision_validation_failed:{payload.get('verdict')}")
    if payload.get("input_schema") != "luban_rich_leaf_shadow_residual_guard_review_packets.v1":
        blockers.append(f"shadow_residual_guard_review_decision_validation_bad_input_schema:{payload.get('input_schema')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_guard_review_decision_validation_review_flags_invalid")
    if classification.get("shadow_residual_guard_review_decision_validation") is not True:
        blockers.append("shadow_residual_guard_review_decision_validation_classification_invalid")
    if classification.get("human_reviewer_signoff") is not False or classification.get("governance_signoff") is not False:
        blockers.append("shadow_residual_guard_review_decision_validation_signoff_claimed")
    for key in (
        "patch_generation_allowed",
        "source_ref_mutation_allowed",
        "runtime_install_allowed",
        "runtime_guard_enforcement_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
        "learner_memory_write_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_guard_review_decision_validation_authority_allowed:{key}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for key in ("missing_decision_count", "invalid_decision_count", "duplicate_decision_count", "stale_decision_count", "blocker_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"shadow_residual_guard_review_decision_validation_failed_or_invalid" if key != "blocker_count" else f"shadow_residual_guard_review_decision_validation_blockers_present:{summary.get(key)}")
            break
    decisions_summary = (
        shadow_residual_guard_review_decisions.get("summary")
        if isinstance(shadow_residual_guard_review_decisions.get("summary"), dict)
        else {}
    )
    if int(summary.get("decision_count") or 0) != int(decisions_summary.get("decision_count") or 0):
        blockers.append(
            f"shadow_residual_guard_review_decision_validation_decision_count_mismatch:{summary.get('decision_count')}:{decisions_summary.get('decision_count')}"
        )
    if int(summary.get("guard_review_packet_count") or 0) != int(decisions_summary.get("guard_review_packet_count") or 0):
        blockers.append(
            "shadow_residual_guard_review_decision_validation_packet_count_mismatch"
        )


def _check_shadow_residual_guard_audit_record(
    payload: dict[str, Any],
    blockers: list[str],
    *,
    shadow_residual_guard_review_decisions: dict[str, Any],
    shadow_residual_guard_review_decision_validation: dict[str, Any],
) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"shadow_residual_guard_audit_record_failed:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    expected_input_schemas = {
        "guard_review_packets": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
        "guard_review_decisions": "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
        "guard_review_decision_validation": "luban_rich_leaf_shadow_residual_guard_review_decision_validation.v1",
    }
    for key, expected in expected_input_schemas.items():
        if input_schemas.get(key) != expected:
            blockers.append(f"shadow_residual_guard_audit_record_bad_input_schema:{key}:{input_schemas.get(key)}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("shadow_residual_guard_audit_record_review_flags_invalid")
    if classification.get("shadow_residual_guard_audit_record") is not True:
        blockers.append("shadow_residual_guard_audit_record_classification_invalid")
    if classification.get("ai_council_shadow_only") is not True:
        blockers.append("shadow_residual_guard_audit_record_shadow_flag_invalid")
    if classification.get("human_reviewer_signoff") is not False or classification.get("governance_signoff") is not False:
        blockers.append("shadow_residual_guard_audit_record_signoff_claimed")
    for key in (
        "patch_generation_allowed",
        "source_ref_mutation_allowed",
        "runtime_install_allowed",
        "runtime_guard_enforcement_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
        "learner_memory_write_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"shadow_residual_guard_audit_record_authority_allowed:{key}")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"shadow_residual_guard_audit_record_blockers_present:{summary.get('blocker_count')}")
    validation_summary = (
        shadow_residual_guard_review_decision_validation.get("summary")
        if isinstance(shadow_residual_guard_review_decision_validation.get("summary"), dict)
        else {}
    )
    decisions_summary = (
        shadow_residual_guard_review_decisions.get("summary")
        if isinstance(shadow_residual_guard_review_decisions.get("summary"), dict)
        else {}
    )
    if int(summary.get("guard_review_packet_count") or 0) != int(validation_summary.get("guard_review_packet_count") or 0):
        blockers.append("shadow_residual_guard_audit_record_packet_count_mismatch")
    if int(summary.get("decision_count") or 0) != int(decisions_summary.get("decision_count") or 0):
        blockers.append("shadow_residual_guard_audit_record_decision_count_mismatch")
    if int(summary.get("audit_record_count") or 0) != int(summary.get("decision_count") or 0):
        blockers.append("shadow_residual_guard_audit_record_audit_decision_count_mismatch")

    records = (
        payload.get("shadow_residual_guard_audit_records")
        if isinstance(payload.get("shadow_residual_guard_audit_records"), list)
        else []
    )
    if int(summary.get("audit_record_count") or 0) != len(records):
        blockers.append("shadow_residual_guard_audit_record_count_mismatch")

    expected_actions = {
        "confirm_guard_patch_candidate": "guard_patch_candidate_review_required",
        "request_guard_scope_narrowing": "guard_scope_narrowing_required",
        "request_source_ref_reaudit": "source_ref_reaudit_required",
        "reject_guard_not_needed": "dismissed_after_guard_review",
    }
    decision_ids = {
        decision.get("decision_id")
        for decision in shadow_residual_guard_review_decisions.get("decisions") or []
        if isinstance(decision, dict)
    }
    for record in records:
        if not isinstance(record, dict):
            blockers.append("shadow_residual_guard_audit_record_entry_not_object")
            continue
        record_id = record.get("guard_audit_record_id")
        decision_id = record.get("decision_id")
        if not record_id or not decision_id or not record.get("guard_review_packet_id") or not record.get("leaf_id") or not record.get("work_order_id"):
            blockers.append(f"shadow_residual_guard_audit_record_missing_join_key:{record_id}")
        if decision_id not in decision_ids:
            blockers.append(f"shadow_residual_guard_audit_record_unknown_decision:{record_id}:{decision_id}")
        expected_action = expected_actions.get(record.get("decision"))
        if record.get("next_compiler_action") != expected_action:
            blockers.append(f"shadow_residual_guard_audit_record_bad_action:{record_id}:{record.get('next_compiler_action')}")
        if record.get("candidate_only") is not True or record.get("review_only") is not True or record.get("shadow_only") is not True:
            blockers.append(f"shadow_residual_guard_audit_record_flags_invalid:{record_id}")
        trace = record.get("evidence_trace") if isinstance(record.get("evidence_trace"), dict) else {}
        if not trace.get("record_ids") or not trace.get("source_lanes") or not trace.get("reason_codes"):
            blockers.append(f"shadow_residual_guard_audit_record_trace_missing:{record_id}")
        for key in (
            "patch_generation_allowed",
            "source_ref_mutation_allowed",
            "runtime_install_allowed",
            "runtime_guard_enforcement_allowed",
            "release_truth_claimed",
            "quality_claim_allowed",
            "learner_memory_write_allowed",
        ):
            if record.get(key) is not False:
                blockers.append(f"shadow_residual_guard_audit_record_authority_allowed:{record_id}:{key}")


def _check_learning_evidence_candidate_bridge(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"learning_evidence_candidate_bridge_failed:{payload.get('verdict')}")
    if payload.get("input_schema") != "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1":
        blockers.append(f"learning_evidence_candidate_bridge_bad_input_schema:{payload.get('input_schema')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("learning_evidence_candidate_bridge_quality_claim_allowed")
    if payload.get("execution_mode") != "candidate_bridge":
        blockers.append(f"learning_evidence_candidate_bridge_bad_execution_mode:{payload.get('execution_mode')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("learning_evidence_candidate_bridge_review_flags_invalid")
    if classification.get("learning_evidence_candidate_bridge") is not True:
        blockers.append("learning_evidence_candidate_bridge_classification_invalid")
    for key in ("learner_memory_write_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"learning_evidence_candidate_bridge_memory_write_allowed" if key == "learner_memory_write_allowed" else f"learning_evidence_candidate_bridge_runtime_or_release_allowed:{key}")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if safety.get("learner_memory_write_count") not in (0, False):
        blockers.append("learning_evidence_candidate_bridge_learner_memory_write_count")
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("learning_evidence_candidate_bridge_canonical_learner_truth_written")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"learning_evidence_candidate_bridge_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("learning_evidence_candidate_bridge_no_candidate_events")
    if int(summary.get("learner_memory_write_count") or 0) != 0:
        blockers.append("learning_evidence_candidate_bridge_summary_learner_memory_write_count")
    if int(summary.get("provider_call_count") or 0) != 0:
        blockers.append("learning_evidence_candidate_bridge_provider_calls_present")

    by_layer = payload.get("not_exercised_by_layer") if isinstance(payload.get("not_exercised_by_layer"), dict) else {}
    memory_not_exercised = set(by_layer.get("memory_not_exercised") or [])
    learning_not_exercised = set(by_layer.get("learning_brain_not_exercised") or [])
    for required in ("learner_memory_db_write", "learner_memory_event_id_assignment", "canonical_learner_truth_write"):
        if required not in memory_not_exercised:
            blockers.append(f"learning_evidence_candidate_bridge_missing_memory_not_exercised:{required}")
    for required in ("personalization_context_pack_readback", "learner_claim_projection", "next_best_action_generation", "real_student_outcome"):
        if required not in learning_not_exercised:
            blockers.append(f"learning_evidence_candidate_bridge_missing_learning_brain_not_exercised:{required}")

    events = payload.get("learning_evidence_event_candidates") if isinstance(payload.get("learning_evidence_event_candidates"), list) else []
    for event in events:
        if not isinstance(event, dict):
            blockers.append("learning_evidence_candidate_not_object")
            continue
        if event.get("event_type") != "learning_evidence" or event.get("memory_kind") != "learning_evidence":
            blockers.append("learning_evidence_candidate_bad_event_semantics")
        if event.get("source_feature") != "rich_leaf_shadow_candidate":
            blockers.append(f"learning_evidence_candidate_bad_source_feature:{event.get('source_feature')}")
        for key in ("candidate_only", "preview_only"):
            if event.get(key) is not True:
                blockers.append(f"learning_evidence_candidate_missing_candidate_flag:{key}")
        for key in ("claim_promotion_allowed", "mastery_raised", "canonical_truth_written"):
            if event.get(key) is not False:
                blockers.append(f"learning_evidence_candidate_{key}")
        quality = event.get("quality") if isinstance(event.get("quality"), dict) else {}
        for key in ("writeback_eligible", "progress_countable", "truth_eligible", "stable_truth_eligible"):
            if quality.get(key) is not False:
                blockers.append(f"learning_evidence_candidate_quality_{key}")
        trace = event.get("rich_leaf_trace") if isinstance(event.get("rich_leaf_trace"), dict) else {}
        for key in ("case_id", "task", "artifact_id", "leaf_id", "field_id", "family"):
            if not str(trace.get(key) or "").strip():
                blockers.append(f"learning_evidence_candidate_missing_trace:{key}")
        if not trace.get("cited_source_ref_ids"):
            blockers.append("learning_evidence_candidate_missing_cited_source_refs")


def _check_pcp_nba_candidate_projection(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"pcp_nba_candidate_projection_failed:{payload.get('verdict')}")
    if payload.get("input_schema") != "luban_rich_leaf_learning_evidence_candidate_bridge.v1":
        blockers.append(f"pcp_nba_candidate_projection_bad_input_schema:{payload.get('input_schema')}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("pcp_nba_candidate_projection_quality_claim_allowed")
    if payload.get("execution_mode") != "dry_run_candidate_projection":
        blockers.append(f"pcp_nba_candidate_projection_bad_execution_mode:{payload.get('execution_mode')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("pcp_nba_candidate_projection_review_flags_invalid")
    if classification.get("pcp_nba_candidate_projection") is not True:
        blockers.append("pcp_nba_candidate_projection_classification_invalid")
    for key in ("learner_memory_write_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"pcp_nba_candidate_projection_authority_allowed:{key}")
    if classification.get("personalization_context_pack_readback_allowed") is not False:
        blockers.append("pcp_nba_candidate_projection_pcp_readback_allowed")
    if classification.get("next_best_action_write_allowed") is not False:
        blockers.append("pcp_nba_candidate_projection_next_action_write_allowed")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in (
        "learner_memory_write_count",
        "personalization_context_pack_readback_count",
        "training_intent_write_count",
        "next_best_action_write_count",
    ):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"pcp_nba_candidate_projection_{key}")
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("pcp_nba_candidate_projection_canonical_learner_truth_written")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"pcp_nba_candidate_projection_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("pcp_nba_candidate_projection_no_candidate_events")
    if int(summary.get("top_claim_candidate_count") or 0) <= 0:
        blockers.append("pcp_nba_candidate_projection_no_claim_candidates")
    if int(summary.get("next_action_candidate_count") or 0) <= 0:
        blockers.append("pcp_nba_candidate_projection_no_action_candidates")
    for key in ("learner_memory_write_count", "pcp_readback_count", "training_intent_write_count", "next_best_action_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"pcp_nba_candidate_projection_summary_{key}")

    pcp = payload.get("personalization_context_pack_candidate") if isinstance(payload.get("personalization_context_pack_candidate"), dict) else {}
    if pcp.get("source") != "PersonalizationContextPackCandidate":
        blockers.append(f"pcp_nba_candidate_projection_bad_pcp_source:{pcp.get('source')}")
    if pcp.get("candidate_only") is not True:
        blockers.append("pcp_nba_candidate_projection_pcp_not_candidate")
    if pcp.get("readback_verified") is not False:
        blockers.append("pcp_nba_candidate_projection_pcp_readback_verified")
    authority = pcp.get("authority") if isinstance(pcp.get("authority"), dict) else {}
    if authority.get("evidence") != "learning_evidence_candidate_bridge":
        blockers.append("pcp_nba_candidate_projection_bad_evidence_authority")
    if authority.get("claims") != "candidate_projection_not_learning_synthesis":
        blockers.append("pcp_nba_candidate_projection_bad_claims_authority")
    if authority.get("prescription") != "not_exercised_training_intent":
        blockers.append("pcp_nba_candidate_projection_bad_prescription_authority")
    for claim in pcp.get("top_claim_candidates") or []:
        if not isinstance(claim, dict):
            blockers.append("pcp_nba_candidate_projection_claim_not_object")
            continue
        if claim.get("candidate_only") is not True or claim.get("claim_status") != "candidate_preview":
            blockers.append("pcp_nba_candidate_projection_claim_not_candidate_preview")
        if claim.get("truth_eligible") is not False:
            blockers.append("pcp_nba_candidate_projection_claim_truth_eligible")
        if not claim.get("evidence_refs"):
            blockers.append("pcp_nba_candidate_projection_claim_missing_evidence_refs")

    for action in payload.get("next_action_candidates") or []:
        if not isinstance(action, dict):
            blockers.append("pcp_nba_candidate_projection_action_not_object")
            continue
        if action.get("candidate_only") is not True:
            blockers.append("pcp_nba_candidate_projection_action_not_candidate")
        if action.get("prescription_authority") != "not_exercised_training_intent":
            blockers.append("pcp_nba_candidate_projection_action_prescription_authority")
        if action.get("status") != "candidate_not_prescription":
            blockers.append("pcp_nba_candidate_projection_action_status")

    by_layer = payload.get("not_exercised_by_layer") if isinstance(payload.get("not_exercised_by_layer"), dict) else {}
    learning_not_exercised = set(by_layer.get("learning_brain_not_exercised") or [])
    for required in (
        "learning_synthesis",
        "personalization_context_pack_readback",
        "training_intent_creation",
        "next_best_action_generation",
        "retest_delta",
    ):
        if required not in learning_not_exercised:
            blockers.append(f"pcp_nba_candidate_projection_missing_learning_brain_not_exercised:{required}")


def _check_test_learner_sandbox_readback_gate(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"test_learner_sandbox_failed:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("learning_evidence_candidate_bridge") != "luban_rich_leaf_learning_evidence_candidate_bridge.v1":
        blockers.append("test_learner_sandbox_bad_bridge_input_schema")
    if input_schemas.get("pcp_nba_candidate_projection") != "luban_rich_leaf_pcp_nba_candidate_projection.v1":
        blockers.append("test_learner_sandbox_bad_projection_input_schema")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("test_learner_sandbox_quality_claim_allowed")
    if payload.get("execution_mode") != "artifact_only_sandbox_readback":
        blockers.append(f"test_learner_sandbox_bad_execution_mode:{payload.get('execution_mode')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("test_learner_sandbox_review_flags_invalid")
    if classification.get("test_learner_sandbox_readback_gate") is not True:
        blockers.append("test_learner_sandbox_classification_invalid")
    if classification.get("sandbox_write_scope") != "artifact_only":
        blockers.append("test_learner_sandbox_bad_write_scope")
    for key in ("learner_memory_write_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append("test_learner_sandbox_memory_write_allowed" if key == "learner_memory_write_allowed" else f"test_learner_sandbox_authority_allowed:{key}")

    sandbox = payload.get("sandbox") if isinstance(payload.get("sandbox"), dict) else {}
    if sandbox.get("write_scope") != "artifact_only":
        blockers.append("test_learner_sandbox_payload_bad_write_scope")
    if not str(sandbox.get("sandbox_user_id") or "").startswith("rich_leaf_sandbox_"):
        blockers.append("test_learner_sandbox_bad_user_scope")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"test_learner_sandbox_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("test_learner_sandbox_no_candidate_events")
    if int(summary.get("sandbox_event_write_count") or 0) <= 0:
        blockers.append("test_learner_sandbox_no_artifact_write")
    if int(summary.get("sandbox_readback_event_count") or 0) <= 0:
        blockers.append("test_learner_sandbox_no_readback")
    if int(summary.get("synthesis_observed_candidate_count") or 0) != 0:
        blockers.append("test_learner_sandbox_synthesis_observed_candidate_count")
    if int(summary.get("synthesis_compiled_object_count") or 0) != 0:
        blockers.append("test_learner_sandbox_synthesis_compiled_object_count")
    for key in ("learner_memory_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"test_learner_sandbox_{key}")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("learner_memory_write_count", "personalization_context_pack_readback_count", "training_intent_write_count", "next_best_action_write_count"):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"test_learner_sandbox_safety_{key}")
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("test_learner_sandbox_canonical_learner_truth_written")

    by_layer = payload.get("not_exercised_by_layer") if isinstance(payload.get("not_exercised_by_layer"), dict) else {}
    memory_not_exercised = set(by_layer.get("memory_not_exercised") or [])
    for required in ("learner_state_service_append_memory_event", "learner_memory_db_write", "learner_memory_outbox_enqueue", "canonical_learner_truth_write"):
        if required not in memory_not_exercised:
            blockers.append(f"test_learner_sandbox_missing_memory_not_exercised:{required}")


def _check_authorized_writeback_preflight(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "READY_FOR_AUTHORIZATION_REVIEW":
        blockers.append(f"authorized_writeback_preflight_bad_verdict:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("test_learner_sandbox_readback_gate") != "luban_rich_leaf_test_learner_sandbox_readback_gate.v1":
        blockers.append("authorized_writeback_preflight_bad_sandbox_input_schema")
    if input_schemas.get("pcp_nba_candidate_projection") != "luban_rich_leaf_pcp_nba_candidate_projection.v1":
        blockers.append("authorized_writeback_preflight_bad_projection_input_schema")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("authorized_writeback_preflight_quality_claim_allowed")
    if payload.get("execution_mode") != "authorization_preflight_only":
        blockers.append(f"authorized_writeback_preflight_bad_execution_mode:{payload.get('execution_mode')}")

    auth = payload.get("authorization") if isinstance(payload.get("authorization"), dict) else {}
    if auth.get("explicit_user_authorization_required") is not True:
        blockers.append("authorized_writeback_preflight_missing_explicit_authorization_requirement")
    if auth.get("test_learner_writeback_authorized") is not False:
        blockers.append("authorized_writeback_preflight_writeback_authorized")
    if auth.get("allowed_write_scope") != "none_without_authorization":
        blockers.append("authorized_writeback_preflight_bad_allowed_scope")
    if auth.get("canonical_truth_authorized") is not False:
        blockers.append("authorized_writeback_preflight_canonical_truth_authorized")
    if auth.get("production_db_authorized") is not False:
        blockers.append("authorized_writeback_preflight_production_db_authorized")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"authorized_writeback_preflight_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("authorized_writeback_preflight_no_candidate_events")
    if int(summary.get("sandbox_readback_event_count") or 0) <= 0:
        blockers.append("authorized_writeback_preflight_no_sandbox_readback")
    if summary.get("writeback_executed") is not False:
        blockers.append("authorized_writeback_preflight_writeback_executed")
    for key in ("learner_memory_write_count", "canonical_truth_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"authorized_writeback_preflight_{key}")

    missing = set(payload.get("missing_authorizations") or [])
    for required in (
        "explicit_user_authorization",
        "test_learner_identity_scope",
        "teacher_final_or_governance_review",
        "rollback_plan_for_test_learner_writeback",
        "separate_canonical_truth_authorization",
    ):
        if required not in missing:
            blockers.append(f"authorized_writeback_preflight_missing_authorization:{required}")

    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("authorized_writeback_preflight_review_flags_invalid")
    if classification.get("authorized_writeback_preflight") is not True:
        blockers.append("authorized_writeback_preflight_classification_invalid")
    if classification.get("test_learner_writeback_allowed") is not False:
        blockers.append("authorized_writeback_preflight_writeback_allowed")
    for key in ("learner_memory_write_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"authorized_writeback_preflight_authority_allowed:{key}")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("learner_memory_write_count", "personalization_context_pack_readback_count", "training_intent_write_count", "next_best_action_write_count"):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"authorized_writeback_preflight_safety_{key}")
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("authorized_writeback_preflight_canonical_learner_truth_written")


def _check_test_learner_writeback_authorization_package(
    payload: dict[str, Any], blockers: list[str], *, authorized_writeback_preflight: dict[str, Any] | None = None
) -> None:
    if payload.get("verdict") != "READY_FOR_USER_AUTHORIZATION_DECISION":
        blockers.append(f"test_learner_writeback_authorization_package_bad_verdict:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("authorized_writeback_preflight") != "luban_rich_leaf_authorized_writeback_preflight.v1":
        blockers.append("test_learner_writeback_authorization_package_bad_preflight_input_schema")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("test_learner_writeback_authorization_package_quality_claim_allowed")
    if payload.get("execution_mode") != "authorization_package_only":
        blockers.append(f"test_learner_writeback_authorization_package_bad_execution_mode:{payload.get('execution_mode')}")

    decision = payload.get("authorization_decision") if isinstance(payload.get("authorization_decision"), dict) else {}
    if decision.get("explicit_user_authorization_required") is not True:
        blockers.append("test_learner_writeback_authorization_package_missing_explicit_auth_requirement")
    if decision.get("user_authorization_recorded") is not False:
        blockers.append("test_learner_writeback_authorization_package_user_authorization_recorded")
    if decision.get("test_learner_writeback_authorized") is not False:
        blockers.append("test_learner_writeback_authorization_package_writeback_authorized")
    if decision.get("allowed_write_scope") != "none_without_signed_authorization":
        blockers.append("test_learner_writeback_authorization_package_bad_allowed_scope")
    if decision.get("canonical_truth_authorized") is not False:
        blockers.append("test_learner_writeback_authorization_package_canonical_truth_authorized")
    if decision.get("production_db_authorized") is not False:
        blockers.append("test_learner_writeback_authorization_package_production_db_authorized")

    scope = payload.get("candidate_scope") if isinstance(payload.get("candidate_scope"), dict) else {}
    if scope.get("target_memory_kind") != "learning_evidence":
        blockers.append("test_learner_writeback_authorization_package_bad_memory_kind")
    if scope.get("target_source_feature") != "rich_leaf_authorized_test_writeback":
        blockers.append("test_learner_writeback_authorization_package_bad_source_feature")
    if scope.get("target_user_scope") != "test_learner_only_after_explicit_authorization":
        blockers.append("test_learner_writeback_authorization_package_bad_user_scope")
    if int(scope.get("max_candidate_event_count") or 0) <= 0:
        blockers.append("test_learner_writeback_authorization_package_no_candidate_scope")
    if authorized_writeback_preflight is not None:
        preflight_summary = (
            authorized_writeback_preflight.get("summary")
            if isinstance(authorized_writeback_preflight.get("summary"), dict)
            else {}
        )
        preflight_plan = (
            authorized_writeback_preflight.get("writeback_plan_candidate")
            if isinstance(authorized_writeback_preflight.get("writeback_plan_candidate"), dict)
            else {}
        )
        expected_count = int(preflight_plan.get("max_candidate_event_count") or preflight_summary.get("candidate_event_count") or 0)
        if int(scope.get("max_candidate_event_count") or 0) != expected_count:
            blockers.append("test_learner_writeback_authorization_package_candidate_count_drift")

    rollback = payload.get("rollback_plan") if isinstance(payload.get("rollback_plan"), dict) else {}
    if rollback.get("plan_status") != "draft_review_required":
        blockers.append("test_learner_writeback_authorization_package_bad_rollback_status")
    if rollback.get("pre_write_snapshot_required") is not True:
        blockers.append("test_learner_writeback_authorization_package_missing_snapshot_requirement")
    if rollback.get("delete_by_source_feature_required") is not True:
        blockers.append("test_learner_writeback_authorization_package_missing_delete_by_source_feature")
    rollback_artifacts = set(rollback.get("rollback_artifacts") or [])
    for required in ("pre_write_learner_memory_snapshot", "write_batch_manifest", "post_write_readback_report"):
        if required not in rollback_artifacts:
            blockers.append(f"test_learner_writeback_authorization_package_missing_rollback_artifact:{required}")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"test_learner_writeback_authorization_package_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("test_learner_writeback_authorization_package_no_candidate_events")
    if summary.get("writeback_executed") is not False:
        blockers.append("test_learner_writeback_authorization_package_writeback_executed")
    for key in ("learner_memory_write_count", "canonical_truth_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"test_learner_writeback_authorization_package_{key}")

    missing = set(payload.get("missing_authorizations") or [])
    for required in (
        "signed_user_authorization_record",
        "concrete_test_learner_id",
        "teacher_final_or_governance_review",
        "approved_rollback_plan",
        "separate_canonical_truth_authorization",
    ):
        if required not in missing:
            blockers.append(f"test_learner_writeback_authorization_package_missing_authorization:{required}")

    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("test_learner_writeback_authorization_package_review_flags_invalid")
    if classification.get("test_learner_writeback_authorization_package") is not True:
        blockers.append("test_learner_writeback_authorization_package_classification_invalid")
    if classification.get("test_learner_writeback_allowed") is not False:
        blockers.append("test_learner_writeback_authorization_package_writeback_allowed")
    for key in ("learner_memory_write_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"test_learner_writeback_authorization_package_authority_allowed:{key}")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("learner_memory_write_count", "personalization_context_pack_readback_count", "training_intent_write_count", "next_best_action_write_count"):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"test_learner_writeback_authorization_package_safety_{key}")
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("test_learner_writeback_authorization_package_canonical_learner_truth_written")


def _check_test_learner_writeback_dry_run_manifest(
    payload: dict[str, Any],
    blockers: list[str],
    *,
    test_learner_sandbox_readback_gate: dict[str, Any] | None = None,
    test_learner_writeback_authorization_package: dict[str, Any] | None = None,
) -> None:
    if payload.get("verdict") != "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION":
        blockers.append(f"test_learner_writeback_dry_run_manifest_bad_verdict:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("test_learner_sandbox_readback_gate") != "luban_rich_leaf_test_learner_sandbox_readback_gate.v1":
        blockers.append("test_learner_writeback_dry_run_manifest_bad_sandbox_input_schema")
    if (
        input_schemas.get("test_learner_writeback_authorization_package")
        != "luban_rich_leaf_test_learner_writeback_authorization_package.v1"
    ):
        blockers.append("test_learner_writeback_dry_run_manifest_bad_authorization_package_input_schema")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("test_learner_writeback_dry_run_manifest_quality_claim_allowed")
    if payload.get("execution_mode") != "dry_run_manifest_only":
        blockers.append(f"test_learner_writeback_dry_run_manifest_bad_execution_mode:{payload.get('execution_mode')}")

    target = payload.get("target_scope") if isinstance(payload.get("target_scope"), dict) else {}
    if target.get("target_user_id") != "not_bound_without_authorization":
        blockers.append("test_learner_writeback_dry_run_manifest_bound_target_user")
    if target.get("target_memory_kind") != "learning_evidence":
        blockers.append("test_learner_writeback_dry_run_manifest_bad_memory_kind")
    if target.get("target_source_feature") != "rich_leaf_authorized_test_writeback":
        blockers.append("test_learner_writeback_dry_run_manifest_bad_source_feature")

    batch = payload.get("write_batch_candidate") if isinstance(payload.get("write_batch_candidate"), dict) else {}
    if batch.get("write_allowed") is not False:
        blockers.append("test_learner_writeback_dry_run_manifest_write_allowed")
    if int(batch.get("event_count") or 0) <= 0:
        blockers.append("test_learner_writeback_dry_run_manifest_no_events")
    if int(batch.get("idempotency_key_count") or 0) != int(batch.get("event_count") or 0):
        blockers.append("test_learner_writeback_dry_run_manifest_bad_idempotency_count")

    rollback = payload.get("rollback_selector") if isinstance(payload.get("rollback_selector"), dict) else {}
    if rollback.get("rollback_allowed") is not False:
        blockers.append("test_learner_writeback_dry_run_manifest_rollback_allowed")
    if rollback.get("target_user_id") != "not_bound_without_authorization":
        blockers.append("test_learner_writeback_dry_run_manifest_rollback_bound_user")
    if rollback.get("source_feature") != "rich_leaf_authorized_test_writeback":
        blockers.append("test_learner_writeback_dry_run_manifest_bad_rollback_source_feature")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"test_learner_writeback_dry_run_manifest_blockers_present:{summary.get('blocker_count')}")
    if summary.get("writeback_executed") is not False:
        blockers.append("test_learner_writeback_dry_run_manifest_writeback_executed")
    for key in ("learner_memory_write_count", "canonical_truth_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"test_learner_writeback_dry_run_manifest_{key}")

    if test_learner_sandbox_readback_gate is not None:
        sandbox_summary = (
            test_learner_sandbox_readback_gate.get("summary")
            if isinstance(test_learner_sandbox_readback_gate.get("summary"), dict)
            else {}
        )
        expected_count = int(sandbox_summary.get("sandbox_readback_event_count") or 0)
        if int(batch.get("event_count") or 0) != expected_count:
            blockers.append("test_learner_writeback_dry_run_manifest_event_count_drift")
        if int(summary.get("planned_event_count") or 0) != expected_count:
            blockers.append("test_learner_writeback_dry_run_manifest_planned_event_count_drift")
    if test_learner_writeback_authorization_package is not None:
        scope = (
            test_learner_writeback_authorization_package.get("candidate_scope")
            if isinstance(test_learner_writeback_authorization_package.get("candidate_scope"), dict)
            else {}
        )
        if int(batch.get("event_count") or 0) != int(scope.get("max_candidate_event_count") or 0):
            blockers.append("test_learner_writeback_dry_run_manifest_authorization_count_drift")

    event_candidates = payload.get("event_write_candidates") if isinstance(payload.get("event_write_candidates"), list) else []
    if len(event_candidates) != int(batch.get("event_count") or 0):
        blockers.append("test_learner_writeback_dry_run_manifest_event_candidate_count_mismatch")
    idempotency_keys: set[str] = set()
    for row in event_candidates:
        if not isinstance(row, dict):
            blockers.append("test_learner_writeback_dry_run_manifest_bad_event_candidate")
            continue
        if row.get("target_user_id") != "not_bound_without_authorization":
            blockers.append("test_learner_writeback_dry_run_manifest_event_bound_user")
        if row.get("source_feature") != "rich_leaf_authorized_test_writeback":
            blockers.append("test_learner_writeback_dry_run_manifest_event_bad_source_feature")
        if row.get("write_allowed") is not False:
            blockers.append("test_learner_writeback_dry_run_manifest_event_write_allowed")
        if row.get("memory_kind") != "learning_evidence":
            blockers.append("test_learner_writeback_dry_run_manifest_event_bad_memory_kind")
        key = str(row.get("idempotency_key") or "")
        if not key:
            blockers.append("test_learner_writeback_dry_run_manifest_event_missing_idempotency_key")
        idempotency_keys.add(key)
        payload_json = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
        quality = payload_json.get("quality") if isinstance(payload_json.get("quality"), dict) else {}
        for quality_key in ("writeback_eligible", "progress_countable", "truth_eligible", "stable_truth_eligible"):
            if quality.get(quality_key) is not False:
                blockers.append(f"test_learner_writeback_dry_run_manifest_event_quality_{quality_key}")
    if len(idempotency_keys) != len(event_candidates):
        blockers.append("test_learner_writeback_dry_run_manifest_duplicate_idempotency_keys")

    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("test_learner_writeback_dry_run_manifest_review_flags_invalid")
    if classification.get("test_learner_writeback_dry_run_manifest") is not True:
        blockers.append("test_learner_writeback_dry_run_manifest_classification_invalid")
    for key in ("test_learner_writeback_allowed", "learner_memory_write_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"test_learner_writeback_dry_run_manifest_authority_allowed:{key}")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("learner_memory_write_count", "personalization_context_pack_readback_count", "training_intent_write_count", "next_best_action_write_count"):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"test_learner_writeback_dry_run_manifest_safety_{key}")
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("test_learner_writeback_dry_run_manifest_canonical_learner_truth_written")


def _check_test_learner_writeback_execution_gate(
    payload: dict[str, Any],
    blockers: list[str],
    *,
    test_learner_writeback_dry_run_manifest: dict[str, Any] | None = None,
) -> None:
    if payload.get("verdict") != "BLOCKED_PENDING_SIGNED_AUTHORIZATION":
        blockers.append(f"test_learner_writeback_execution_gate_bad_verdict:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("test_learner_writeback_dry_run_manifest") != "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1":
        blockers.append("test_learner_writeback_execution_gate_bad_dry_run_input_schema")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("test_learner_writeback_execution_gate_quality_claim_allowed")
    if payload.get("execution_mode") != "execution_gate_only":
        blockers.append(f"test_learner_writeback_execution_gate_bad_execution_mode:{payload.get('execution_mode')}")

    decision = payload.get("execution_decision") if isinstance(payload.get("execution_decision"), dict) else {}
    if decision.get("writeback_allowed") is not False:
        blockers.append("test_learner_writeback_execution_gate_writeback_allowed")
    if decision.get("writeback_executed") is not False:
        blockers.append("test_learner_writeback_execution_gate_writeback_executed")
    if decision.get("target_user_id_bound") is not False:
        blockers.append("test_learner_writeback_execution_gate_target_user_bound")
    if decision.get("signed_authorization_recorded") is not False:
        blockers.append("test_learner_writeback_execution_gate_signed_authorization_recorded")
    if decision.get("rollback_plan_approved") is not False:
        blockers.append("test_learner_writeback_execution_gate_rollback_plan_approved")

    reasons = set(payload.get("blocking_reasons") or [])
    for required in ("signed_user_authorization_missing", "target_user_unbound", "rollback_plan_not_approved"):
        if required not in reasons:
            blockers.append(f"test_learner_writeback_execution_gate_missing_blocking_reason:{required}")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("blocker_count") not in (0, False):
        blockers.append(f"test_learner_writeback_execution_gate_blockers_present:{summary.get('blocker_count')}")
    if summary.get("writeback_executed") is not False:
        blockers.append("test_learner_writeback_execution_gate_summary_writeback_executed")
    for key in ("learner_memory_write_count", "canonical_truth_write_count", "production_write_count", "provider_call_count"):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"test_learner_writeback_execution_gate_{key}")
    if test_learner_writeback_dry_run_manifest is not None:
        dry_summary = (
            test_learner_writeback_dry_run_manifest.get("summary")
            if isinstance(test_learner_writeback_dry_run_manifest.get("summary"), dict)
            else {}
        )
        if int(summary.get("dry_run_planned_event_count") or 0) != int(dry_summary.get("planned_event_count") or 0):
            blockers.append("test_learner_writeback_execution_gate_planned_event_count_drift")

    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("test_learner_writeback_execution_gate_review_flags_invalid")
    if classification.get("test_learner_writeback_execution_gate") is not True:
        blockers.append("test_learner_writeback_execution_gate_classification_invalid")
    for key in ("test_learner_writeback_allowed", "learner_memory_write_allowed", "runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"test_learner_writeback_execution_gate_authority_allowed:{key}")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("learner_memory_write_count", "personalization_context_pack_readback_count", "training_intent_write_count", "next_best_action_write_count"):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"test_learner_writeback_execution_gate_safety_{key}")
    if safety.get("canonical_learner_truth_written") is not False:
        blockers.append("test_learner_writeback_execution_gate_canonical_learner_truth_written")


def _check_learning_evidence_current_standard_compat_audit(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"learning_evidence_current_standard_compat_audit_failed:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    expected = {
        "learning_evidence_candidate_bridge": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
        "pcp_nba_candidate_projection": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
        "test_learner_sandbox_readback_gate": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
        "test_learner_writeback_dry_run_manifest": "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1",
        "test_learner_writeback_execution_gate": "luban_rich_leaf_test_learner_writeback_execution_gate.v1",
    }
    for key, schema in expected.items():
        if input_schemas.get(key) != schema:
            blockers.append(f"learning_evidence_current_standard_compat_audit_bad_input_schema:{key}:{input_schemas.get(key)}")
    if payload.get("quality_claim_allowed") is not False:
        blockers.append("learning_evidence_current_standard_compat_audit_quality_claim_allowed")
    if payload.get("execution_mode") != "current_standard_compat_audit_only":
        blockers.append(f"learning_evidence_current_standard_compat_audit_bad_execution_mode:{payload.get('execution_mode')}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("learning_evidence_current_standard_compat_audit_review_flags_invalid")
    if classification.get("learning_evidence_current_standard_compat_audit") is not True:
        blockers.append("learning_evidence_current_standard_compat_audit_classification_invalid")
    if classification.get("current_standard_readback_verified") is not False:
        blockers.append("learning_evidence_current_standard_compat_audit_readback_claimed")
    for key in (
        "learner_memory_write_allowed",
        "personalization_context_pack_readback_allowed",
        "next_best_action_write_allowed",
        "runtime_install_allowed",
        "production_default",
        "release_truth_claimed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"learning_evidence_current_standard_compat_audit_authority_allowed:{key}")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"learning_evidence_current_standard_compat_audit_blockers_present:{summary.get('blocker_count')}")
    if summary.get("current_standard_readback_verified") is not False:
        blockers.append("learning_evidence_current_standard_compat_audit_summary_readback_claimed")
    if int(summary.get("candidate_event_count") or 0) <= 0:
        blockers.append("learning_evidence_current_standard_compat_audit_no_candidate_events")
    if int(summary.get("not_current_standard_payload_count") or 0) != int(summary.get("candidate_event_count") or 0):
        blockers.append("learning_evidence_current_standard_compat_audit_payload_count_mismatch")
    if int(summary.get("standard_accepted_source_feature_count") or 0) != 0:
        blockers.append("learning_evidence_current_standard_compat_audit_standard_source_feature_claimed")
    for key in (
        "pcp_readback_count",
        "training_intent_write_count",
        "next_best_action_write_count",
        "sandbox_synthesis_observed_candidate_count",
        "sandbox_synthesis_compiled_object_count",
        "learner_memory_write_count",
        "canonical_truth_write_count",
        "production_write_count",
    ):
        if int(summary.get(key) or 0) != 0:
            blockers.append(f"learning_evidence_current_standard_compat_audit_{key}")

    findings = (
        payload.get("candidate_event_compat_findings")
        if isinstance(payload.get("candidate_event_compat_findings"), list)
        else []
    )
    if len(findings) != int(summary.get("candidate_event_count") or 0):
        blockers.append("learning_evidence_current_standard_compat_audit_finding_count_mismatch")
    for finding in findings:
        if not isinstance(finding, dict):
            blockers.append("learning_evidence_current_standard_compat_finding_not_object")
            continue
        event_id = finding.get("candidate_event_id")
        if finding.get("current_standard_payload") is not False or finding.get("current_standard_readback_verified") is not False:
            blockers.append(f"learning_evidence_current_standard_compat_finding_claimed:{event_id}")
        reasons = set(finding.get("incompatibility_reasons") or [])
        for required in ("source_feature_not_accepted", "candidate_only", "writeback_eligible_false"):
            if required not in reasons:
                blockers.append(f"learning_evidence_current_standard_compat_finding_missing_reason:{event_id}:{required}")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in (
        "canonical_truth_written",
        "canonical_learner_truth_written",
        "official_score_allowed",
        "installed_runtime_supply",
        "release_truth_claimed",
    ):
        if safety.get(key) is not False:
            blockers.append(f"learning_evidence_current_standard_compat_audit_safety_{key}")
    for key in (
        "production_write_count",
        "learner_memory_write_count",
        "personalization_context_pack_readback_count",
        "training_intent_write_count",
        "next_best_action_write_count",
    ):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"learning_evidence_current_standard_compat_audit_safety_{key}")


def _check_external_source_closure(payload: dict[str, Any], blockers: list[str]) -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    if payload.get("verdict") != "PASS":
        blockers.append(f"external_source_closure_failed:{payload.get('verdict')}")
    input_schemas = payload.get("input_schemas") if isinstance(payload.get("input_schemas"), dict) else {}
    if input_schemas.get("semantic_evidence_audit_record") != "luban_rich_leaf_semantic_evidence_audit_record.v1":
        blockers.append(
            "external_source_closure_bad_input_schema:"
            f"{input_schemas.get('semantic_evidence_audit_record')}"
        )
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("external_source_closure_review_flags_invalid")
    if classification.get("external_source_closure") is not True:
        blockers.append("external_source_closure_classification_invalid")
    for key in (
        "source_truth_claimed",
        "runtime_install_allowed",
        "production_default",
        "release_truth_claimed",
        "quality_claim_allowed",
    ):
        if classification.get(key) is not False:
            blockers.append(f"external_source_closure_authority_allowed:{key}")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("blocker_count") or 0) != 0:
        blockers.append(f"external_source_closure_blockers_present:{summary.get('blocker_count')}")
    if int(summary.get("source_truth_write_count") or 0) != 0:
        blockers.append("external_source_closure_source_truth_written")
    if int(summary.get("runtime_install_count") or 0) != 0:
        blockers.append("external_source_closure_runtime_installed")
    needs_count = int(summary.get("needs_external_source_count") or 0)
    closures = payload.get("external_source_closures") if isinstance(payload.get("external_source_closures"), list) else []
    if len(closures) != needs_count:
        blockers.append("external_source_closure_count_mismatch")
    for closure in closures:
        if not isinstance(closure, dict):
            blockers.append("external_source_closure_item_not_object")
            continue
        audit_item_id = closure.get("audit_item_id")
        if closure.get("candidate_only") is not True or closure.get("review_only") is not True:
            blockers.append(f"external_source_closure_item_review_flags_invalid:{audit_item_id}")
        for key in ("source_truth_claimed", "promotion_allowed", "runtime_install_allowed"):
            if closure.get(key) is not False:
                blockers.append(f"external_source_closure_item_authority_allowed:{audit_item_id}:{key}")
        if closure.get("status") not in {"candidate_sources_found", "external_source_required"}:
            blockers.append(f"external_source_closure_bad_status:{audit_item_id}:{closure.get('status')}")
        for candidate in closure.get("candidate_sources") or []:
            if not isinstance(candidate, dict):
                blockers.append(f"external_source_closure_candidate_not_object:{audit_item_id}")
                continue
            if candidate.get("source_lane") == "question" or candidate.get("support_candidate") is not True:
                blockers.append(f"external_source_closure_bad_support_candidate:{audit_item_id}")
            if candidate.get("install_allowed") is not False or candidate.get("runtime_install_allowed") is not False:
                blockers.append(f"external_source_closure_candidate_install_allowed:{audit_item_id}")
        for candidate in closure.get("question_context_candidates") or []:
            if not isinstance(candidate, dict):
                blockers.append(f"external_source_closure_question_context_not_object:{audit_item_id}")
                continue
            if candidate.get("source_lane") != "question" or candidate.get("support_candidate") is not False:
                blockers.append(f"external_source_closure_bad_question_context:{audit_item_id}")

    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in (
        "canonical_truth_written",
        "official_score_allowed",
        "installed_runtime_supply",
        "release_truth_claimed",
    ):
        if safety.get(key) is not False:
            blockers.append(f"external_source_closure_safety_{key}")
    for key in ("source_truth_write_count", "production_write_count"):
        if int(safety.get(key) or 0) != 0:
            blockers.append(f"external_source_closure_safety_{key}")


def _check_weak(payload: dict[str, Any], blockers: list[str]) -> None:
    for order in payload.get("leaf_work_orders") or []:
        if not isinstance(order, dict):
            continue
        if order.get("promotion_allowed") is not False or order.get("runtime_install_allowed") is not False:
            blockers.append(f"weak_leaf_promotion_or_runtime_allowed:{order.get('leaf_id')}")
        for lane_order in order.get("lane_work_orders") or []:
            if not isinstance(lane_order, dict):
                continue
            if lane_order.get("promotion_allowed") is not False or lane_order.get("runtime_install_allowed") is not False:
                blockers.append(f"weak_lane_promotion_or_runtime_allowed:{order.get('leaf_id')}:{lane_order.get('missing_lane')}")


def audit_interop(
    *,
    sample: Path,
    skeleton: Path,
    source_gap: Path,
    patches: Path,
    patch_audit: Path,
    rejected_feedback: Path,
    semantic_packets: Path,
    source_evidence: Path,
    semantic_queue: Path,
    semantic_record: Path,
    review_shards: Path,
    review_suggestions: Path,
    decision_validation: Path,
    reviewed_candidates: Path,
    runtime_supply_candidate: Path,
    runtime_supply_regression: Path,
    field_candidates: Path,
    artifact_candidates: Path,
    field_promotion_review: Path,
    context_pack_smoke: Path,
    fail_open_guard_diagnostic: Path,
    context_pack_projection_ab: Path,
    semantic_runtime_offline_ab: Path,
    semantic_runtime_nearline_ab: Path,
    semantic_runtime_live_ab_preflight: Path,
    semantic_runtime_live_ab: Path,
    semantic_runtime_near_live_smoke: Path,
    semantic_runtime_near_live_shadow_ab: Path,
    shadow_residual_work_orders: Path,
    shadow_residual_review_packets: Path,
    shadow_residual_review_decision_validation: Path,
    shadow_residual_review_decision_seed: Path,
    shadow_residual_review_decisions: Path,
    shadow_residual_audit_record: Path,
    shadow_residual_guard_patch_plan: Path,
    shadow_residual_guard_review_packets: Path,
    shadow_residual_guard_review_decisions: Path,
    shadow_residual_guard_review_decision_validation: Path,
    shadow_residual_guard_audit_record: Path,
    learning_evidence_candidate_bridge: Path,
    pcp_nba_candidate_projection: Path,
    test_learner_sandbox_readback_gate: Path,
    authorized_writeback_preflight: Path,
    test_learner_writeback_authorization_package: Path,
    test_learner_writeback_dry_run_manifest: Path,
    test_learner_writeback_execution_gate: Path,
    learning_evidence_current_standard_compat_audit: Path,
    external_source_closure: Path,
    weak: Path,
) -> dict[str, Any]:
    payloads = {
        "sample": _read_json(sample),
        "skeleton": _read_json(skeleton),
        "source_gap": _read_json(source_gap),
        "patches": _read_json(patches),
        "patch_audit": _read_json(patch_audit),
        "rejected_feedback": _read_json(rejected_feedback),
        "semantic_packets": _read_json(semantic_packets),
        "source_evidence": _read_json(source_evidence),
        "semantic_queue": _read_json(semantic_queue),
        "semantic_record": _read_json(semantic_record),
        "review_shards": _read_json(review_shards),
        "review_suggestions": _read_json(review_suggestions),
        "decision_validation": _read_json(decision_validation),
        "reviewed_candidates": _read_json(reviewed_candidates),
        "runtime_supply_candidate": _read_json(runtime_supply_candidate),
        "runtime_supply_regression": _read_json(runtime_supply_regression),
        "field_candidates": _read_json(field_candidates),
        "artifact_candidates": _read_json(artifact_candidates),
        "field_promotion_review": _read_json(field_promotion_review),
        "context_pack_smoke": _read_json(context_pack_smoke),
        "fail_open_guard_diagnostic": _read_json(fail_open_guard_diagnostic),
        "context_pack_projection_ab": _read_json(context_pack_projection_ab),
        "semantic_runtime_offline_ab": _read_json(semantic_runtime_offline_ab),
        "semantic_runtime_nearline_ab": _read_json(semantic_runtime_nearline_ab),
        "semantic_runtime_live_ab_preflight": _read_json(semantic_runtime_live_ab_preflight),
        "semantic_runtime_live_ab": _read_json(semantic_runtime_live_ab),
        "semantic_runtime_near_live_smoke": _read_json(semantic_runtime_near_live_smoke),
        "semantic_runtime_near_live_shadow_ab": _read_json(semantic_runtime_near_live_shadow_ab),
        "shadow_residual_work_orders": _read_json(shadow_residual_work_orders),
        "shadow_residual_review_packets": _read_json(shadow_residual_review_packets),
        "shadow_residual_review_decision_validation": _read_json(shadow_residual_review_decision_validation),
        "shadow_residual_review_decision_seed": _read_json(shadow_residual_review_decision_seed),
        "shadow_residual_review_decisions": _read_json(shadow_residual_review_decisions),
        "shadow_residual_audit_record": _read_json(shadow_residual_audit_record),
        "shadow_residual_guard_patch_plan": _read_json(shadow_residual_guard_patch_plan),
        "shadow_residual_guard_review_packets": _read_json(shadow_residual_guard_review_packets),
        "shadow_residual_guard_review_decisions": _read_json(shadow_residual_guard_review_decisions),
        "shadow_residual_guard_review_decision_validation": _read_json(shadow_residual_guard_review_decision_validation),
        "shadow_residual_guard_audit_record": _read_json(shadow_residual_guard_audit_record),
        "learning_evidence_candidate_bridge": _read_json(learning_evidence_candidate_bridge),
        "pcp_nba_candidate_projection": _read_json(pcp_nba_candidate_projection),
        "test_learner_sandbox_readback_gate": _read_json(test_learner_sandbox_readback_gate),
        "authorized_writeback_preflight": _read_json(authorized_writeback_preflight),
        "test_learner_writeback_authorization_package": _read_json(test_learner_writeback_authorization_package),
        "test_learner_writeback_dry_run_manifest": _read_json(test_learner_writeback_dry_run_manifest),
        "test_learner_writeback_execution_gate": _read_json(test_learner_writeback_execution_gate),
        "learning_evidence_current_standard_compat_audit": _read_json(learning_evidence_current_standard_compat_audit),
        "external_source_closure": _read_json(external_source_closure),
        "weak": _read_json(weak),
    }
    blockers: list[str] = []
    warnings: list[str] = []
    for name, payload in payloads.items():
        _check_schema(name, payload, blockers)
        _check_safety(name, payload, blockers)
        _check_review_only(name, payload, blockers)
    _check_source_gap(payloads["source_gap"], blockers, warnings)
    _check_patches(payloads["patches"], blockers)
    _check_patch_audit(payloads["patch_audit"], blockers)
    _check_rejected_feedback(payloads["rejected_feedback"], blockers)
    _check_semantic_packets(payloads["semantic_packets"], blockers)
    _check_source_evidence(payloads["source_evidence"], blockers)
    _check_semantic_queue(payloads["semantic_queue"], blockers)
    _check_semantic_record(payloads["semantic_record"], blockers)
    _check_review_shards(payloads["review_shards"], blockers)
    _check_review_suggestions(payloads["review_suggestions"], blockers)
    _check_decision_validation(payloads["decision_validation"], blockers)
    _check_reviewed_candidates(payloads["reviewed_candidates"], blockers)
    _check_runtime_supply_candidate(payloads["runtime_supply_candidate"], blockers)
    _check_runtime_supply_regression(payloads["runtime_supply_regression"], blockers)
    _check_field_candidates(payloads["field_candidates"], blockers)
    _check_artifact_candidates(payloads["artifact_candidates"], blockers)
    _check_field_promotion_review(payloads["field_promotion_review"], blockers)
    _check_context_pack_smoke(payloads["context_pack_smoke"], blockers)
    _check_fail_open_guard_diagnostic(payloads["fail_open_guard_diagnostic"], blockers)
    _check_context_pack_projection_ab(payloads["context_pack_projection_ab"], blockers)
    _check_semantic_runtime_offline_ab(payloads["semantic_runtime_offline_ab"], blockers)
    _check_semantic_runtime_nearline_ab(payloads["semantic_runtime_nearline_ab"], blockers)
    _check_semantic_runtime_live_ab_preflight(payloads["semantic_runtime_live_ab_preflight"], blockers)
    _check_semantic_runtime_live_ab(payloads["semantic_runtime_live_ab"], blockers)
    _check_semantic_runtime_near_live_smoke(payloads["semantic_runtime_near_live_smoke"], blockers)
    _check_semantic_runtime_near_live_shadow_ab(payloads["semantic_runtime_near_live_shadow_ab"], blockers)
    _check_shadow_residual_work_orders(payloads["shadow_residual_work_orders"], blockers)
    _check_shadow_residual_review_packets(payloads["shadow_residual_review_packets"], blockers)
    _check_shadow_residual_review_decision_validation(
        payloads["shadow_residual_review_decision_validation"], blockers
    )
    _check_shadow_residual_review_decision_seed(payloads["shadow_residual_review_decision_seed"], blockers)
    _check_shadow_residual_review_decisions(payloads["shadow_residual_review_decisions"], blockers)
    _check_shadow_residual_review_decision_validation_alignment(
        payloads["shadow_residual_review_decisions"],
        payloads["shadow_residual_review_decision_validation"],
        blockers,
    )
    _check_shadow_residual_audit_record(payloads["shadow_residual_audit_record"], blockers)
    _check_shadow_residual_guard_patch_plan(
        payloads["shadow_residual_guard_patch_plan"],
        blockers,
        shadow_residual_audit_record=payloads["shadow_residual_audit_record"],
    )
    _check_shadow_residual_guard_review_packets(
        payloads["shadow_residual_guard_review_packets"],
        blockers,
        shadow_residual_guard_patch_plan=payloads["shadow_residual_guard_patch_plan"],
    )
    _check_shadow_residual_guard_review_decisions(
        payloads["shadow_residual_guard_review_decisions"],
        blockers,
        shadow_residual_guard_review_packets=payloads["shadow_residual_guard_review_packets"],
    )
    _check_shadow_residual_guard_review_decision_validation(
        payloads["shadow_residual_guard_review_decision_validation"],
        blockers,
        shadow_residual_guard_review_decisions=payloads["shadow_residual_guard_review_decisions"],
    )
    _check_shadow_residual_guard_audit_record(
        payloads["shadow_residual_guard_audit_record"],
        blockers,
        shadow_residual_guard_review_decisions=payloads["shadow_residual_guard_review_decisions"],
        shadow_residual_guard_review_decision_validation=payloads["shadow_residual_guard_review_decision_validation"],
    )
    _check_learning_evidence_candidate_bridge(payloads["learning_evidence_candidate_bridge"], blockers)
    _check_pcp_nba_candidate_projection(payloads["pcp_nba_candidate_projection"], blockers)
    _check_test_learner_sandbox_readback_gate(payloads["test_learner_sandbox_readback_gate"], blockers)
    _check_authorized_writeback_preflight(payloads["authorized_writeback_preflight"], blockers)
    _check_test_learner_writeback_authorization_package(
        payloads["test_learner_writeback_authorization_package"],
        blockers,
        authorized_writeback_preflight=payloads["authorized_writeback_preflight"],
    )
    _check_test_learner_writeback_dry_run_manifest(
        payloads["test_learner_writeback_dry_run_manifest"],
        blockers,
        test_learner_sandbox_readback_gate=payloads["test_learner_sandbox_readback_gate"],
        test_learner_writeback_authorization_package=payloads["test_learner_writeback_authorization_package"],
    )
    _check_test_learner_writeback_execution_gate(
        payloads["test_learner_writeback_execution_gate"],
        blockers,
        test_learner_writeback_dry_run_manifest=payloads["test_learner_writeback_dry_run_manifest"],
    )
    _check_learning_evidence_current_standard_compat_audit(
        payloads["learning_evidence_current_standard_compat_audit"],
        blockers,
    )
    _check_external_source_closure(payloads["external_source_closure"], blockers)
    _check_weak(payloads["weak"], blockers)
    return {
        "schema": "luban_rich_leaf_interop_audit.v1",
        "standard_doc": "docs/qa/2026-06-11-luban-rich-leaf-interoperability-standard.md",
        "verdict": "FAIL" if blockers else "PASS",
        "summary": {
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "artifact_count": len(payloads),
        },
        "blockers": blockers,
        "warnings": warnings,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--skeleton", type=Path, default=DEFAULT_SKELETON)
    parser.add_argument("--source-gap", type=Path, default=DEFAULT_SOURCE_GAP)
    parser.add_argument("--patches", type=Path, default=DEFAULT_PATCHES)
    parser.add_argument("--patch-audit", type=Path, default=DEFAULT_PATCH_AUDIT)
    parser.add_argument("--rejected-feedback", type=Path, default=DEFAULT_REJECTED_FEEDBACK)
    parser.add_argument("--semantic-packets", type=Path, default=DEFAULT_SEMANTIC_PACKETS)
    parser.add_argument("--source-evidence", type=Path, default=DEFAULT_SOURCE_EVIDENCE)
    parser.add_argument("--semantic-queue", type=Path, default=DEFAULT_SEMANTIC_QUEUE)
    parser.add_argument("--semantic-record", type=Path, default=DEFAULT_SEMANTIC_RECORD)
    parser.add_argument("--review-shards", type=Path, default=DEFAULT_REVIEW_SHARDS)
    parser.add_argument("--review-suggestions", type=Path, default=DEFAULT_REVIEW_SUGGESTIONS)
    parser.add_argument("--decision-validation", type=Path, default=DEFAULT_DECISION_VALIDATION)
    parser.add_argument("--reviewed-candidates", type=Path, default=DEFAULT_REVIEWED_CANDIDATES)
    parser.add_argument("--runtime-supply-candidate", type=Path, default=DEFAULT_RUNTIME_SUPPLY_CANDIDATE)
    parser.add_argument("--runtime-supply-regression", type=Path, default=DEFAULT_RUNTIME_SUPPLY_REGRESSION)
    parser.add_argument("--field-candidates", type=Path, default=DEFAULT_FIELD_CANDIDATES)
    parser.add_argument("--artifact-candidates", type=Path, default=DEFAULT_ARTIFACT_CANDIDATES)
    parser.add_argument("--field-promotion-review", type=Path, default=DEFAULT_FIELD_PROMOTION_REVIEW)
    parser.add_argument("--context-pack-smoke", type=Path, default=DEFAULT_CONTEXT_PACK_SMOKE)
    parser.add_argument("--fail-open-guard-diagnostic", type=Path, default=DEFAULT_FAIL_OPEN_GUARD_DIAGNOSTIC)
    parser.add_argument("--context-pack-projection-ab", type=Path, default=DEFAULT_CONTEXT_PACK_PROJECTION_AB)
    parser.add_argument("--semantic-runtime-offline-ab", type=Path, default=DEFAULT_SEMANTIC_RUNTIME_OFFLINE_AB)
    parser.add_argument("--semantic-runtime-nearline-ab", type=Path, default=DEFAULT_SEMANTIC_RUNTIME_NEARLINE_AB)
    parser.add_argument("--semantic-runtime-live-ab-preflight", type=Path, default=DEFAULT_SEMANTIC_RUNTIME_LIVE_AB_PREFLIGHT)
    parser.add_argument("--semantic-runtime-live-ab", type=Path, default=DEFAULT_SEMANTIC_RUNTIME_LIVE_AB)
    parser.add_argument("--semantic-runtime-near-live-smoke", type=Path, default=DEFAULT_SEMANTIC_RUNTIME_NEAR_LIVE_SMOKE)
    parser.add_argument("--semantic-runtime-near-live-shadow-ab", type=Path, default=DEFAULT_SEMANTIC_RUNTIME_NEAR_LIVE_SHADOW_AB)
    parser.add_argument("--shadow-residual-work-orders", type=Path, default=DEFAULT_SHADOW_RESIDUAL_WORK_ORDERS)
    parser.add_argument("--shadow-residual-review-packets", type=Path, default=DEFAULT_SHADOW_RESIDUAL_REVIEW_PACKETS)
    parser.add_argument(
        "--shadow-residual-review-decision-validation",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_REVIEW_DECISION_VALIDATION,
    )
    parser.add_argument(
        "--shadow-residual-review-decision-seed",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_REVIEW_DECISION_SEED,
    )
    parser.add_argument(
        "--shadow-residual-review-decisions",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_REVIEW_DECISIONS,
    )
    parser.add_argument(
        "--shadow-residual-audit-record",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_AUDIT_RECORD,
    )
    parser.add_argument(
        "--shadow-residual-guard-patch-plan",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_GUARD_PATCH_PLAN,
    )
    parser.add_argument(
        "--shadow-residual-guard-review-packets",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_GUARD_REVIEW_PACKETS,
    )
    parser.add_argument(
        "--shadow-residual-guard-review-decisions",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_GUARD_REVIEW_DECISIONS,
    )
    parser.add_argument(
        "--shadow-residual-guard-review-decision-validation",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_GUARD_REVIEW_DECISION_VALIDATION,
    )
    parser.add_argument(
        "--shadow-residual-guard-audit-record",
        type=Path,
        default=DEFAULT_SHADOW_RESIDUAL_GUARD_AUDIT_RECORD,
    )
    parser.add_argument("--learning-evidence-candidate-bridge", type=Path, default=DEFAULT_LEARNING_EVIDENCE_CANDIDATE_BRIDGE)
    parser.add_argument("--pcp-nba-candidate-projection", type=Path, default=DEFAULT_PCP_NBA_CANDIDATE_PROJECTION)
    parser.add_argument("--test-learner-sandbox-readback-gate", type=Path, default=DEFAULT_TEST_LEARNER_SANDBOX_READBACK_GATE)
    parser.add_argument("--authorized-writeback-preflight", type=Path, default=DEFAULT_AUTHORIZED_WRITEBACK_PREFLIGHT)
    parser.add_argument(
        "--test-learner-writeback-authorization-package",
        type=Path,
        default=DEFAULT_TEST_LEARNER_WRITEBACK_AUTHORIZATION_PACKAGE,
    )
    parser.add_argument(
        "--test-learner-writeback-dry-run-manifest",
        type=Path,
        default=DEFAULT_TEST_LEARNER_WRITEBACK_DRY_RUN_MANIFEST,
    )
    parser.add_argument(
        "--test-learner-writeback-execution-gate",
        type=Path,
        default=DEFAULT_TEST_LEARNER_WRITEBACK_EXECUTION_GATE,
    )
    parser.add_argument(
        "--learning-evidence-current-standard-compat-audit",
        type=Path,
        default=DEFAULT_LEARNING_EVIDENCE_CURRENT_STANDARD_COMPAT_AUDIT,
    )
    parser.add_argument(
        "--external-source-closure",
        type=Path,
        default=DEFAULT_EXTERNAL_SOURCE_CLOSURE,
    )
    parser.add_argument("--weak", type=Path, default=DEFAULT_WEAK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = audit_interop(
        sample=args.sample,
        skeleton=args.skeleton,
        source_gap=args.source_gap,
        patches=args.patches,
        patch_audit=args.patch_audit,
        rejected_feedback=args.rejected_feedback,
        semantic_packets=args.semantic_packets,
        source_evidence=args.source_evidence,
        semantic_queue=args.semantic_queue,
        semantic_record=args.semantic_record,
        review_shards=args.review_shards,
        review_suggestions=args.review_suggestions,
        decision_validation=args.decision_validation,
        reviewed_candidates=args.reviewed_candidates,
        runtime_supply_candidate=args.runtime_supply_candidate,
        runtime_supply_regression=args.runtime_supply_regression,
        field_candidates=args.field_candidates,
        artifact_candidates=args.artifact_candidates,
        field_promotion_review=args.field_promotion_review,
        context_pack_smoke=args.context_pack_smoke,
        fail_open_guard_diagnostic=args.fail_open_guard_diagnostic,
        context_pack_projection_ab=args.context_pack_projection_ab,
        semantic_runtime_offline_ab=args.semantic_runtime_offline_ab,
        semantic_runtime_nearline_ab=args.semantic_runtime_nearline_ab,
        semantic_runtime_live_ab_preflight=args.semantic_runtime_live_ab_preflight,
        semantic_runtime_live_ab=args.semantic_runtime_live_ab,
        semantic_runtime_near_live_smoke=args.semantic_runtime_near_live_smoke,
        semantic_runtime_near_live_shadow_ab=args.semantic_runtime_near_live_shadow_ab,
        shadow_residual_work_orders=args.shadow_residual_work_orders,
        shadow_residual_review_packets=args.shadow_residual_review_packets,
        shadow_residual_review_decision_validation=args.shadow_residual_review_decision_validation,
        shadow_residual_review_decision_seed=args.shadow_residual_review_decision_seed,
        shadow_residual_review_decisions=args.shadow_residual_review_decisions,
        shadow_residual_audit_record=args.shadow_residual_audit_record,
        shadow_residual_guard_patch_plan=args.shadow_residual_guard_patch_plan,
        shadow_residual_guard_review_packets=args.shadow_residual_guard_review_packets,
        shadow_residual_guard_review_decisions=args.shadow_residual_guard_review_decisions,
        shadow_residual_guard_review_decision_validation=args.shadow_residual_guard_review_decision_validation,
        shadow_residual_guard_audit_record=args.shadow_residual_guard_audit_record,
        learning_evidence_candidate_bridge=args.learning_evidence_candidate_bridge,
        pcp_nba_candidate_projection=args.pcp_nba_candidate_projection,
        test_learner_sandbox_readback_gate=args.test_learner_sandbox_readback_gate,
        authorized_writeback_preflight=args.authorized_writeback_preflight,
        test_learner_writeback_authorization_package=args.test_learner_writeback_authorization_package,
        test_learner_writeback_dry_run_manifest=args.test_learner_writeback_dry_run_manifest,
        test_learner_writeback_execution_gate=args.test_learner_writeback_execution_gate,
        learning_evidence_current_standard_compat_audit=args.learning_evidence_current_standard_compat_audit,
        external_source_closure=args.external_source_closure,
        weak=args.weak,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
