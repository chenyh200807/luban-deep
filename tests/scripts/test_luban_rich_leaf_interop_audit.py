from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _valid_artifacts(tmp_path: Path) -> dict[str, Path]:
    sample = tmp_path / "sample_manifest.json"
    skeleton = tmp_path / "rich_leaf_skeleton_candidates.json"
    source_gap = tmp_path / "source_gap_candidates.json"
    patches = tmp_path / "candidate_patches.json"
    patch_audit = tmp_path / "patch_evidence_audit.json"
    rejected_feedback = tmp_path / "rejected_patch_feedback_work_orders.json"
    semantic_packets = tmp_path / "semantic_audit_packets.json"
    source_evidence = tmp_path / "source_evidence_agent_candidates.json"
    semantic_queue = tmp_path / "semantic_audit_queue.json"
    semantic_record = tmp_path / "semantic_evidence_audit_record.json"
    review_shards = tmp_path / "semantic_review_shards_manifest.json"
    review_suggestions = tmp_path / "semantic_review_suggestions.json"
    decision_validation = tmp_path / "semantic_review_decision_validation.json"
    reviewed_candidates = tmp_path / "reviewed_rich_leaf_candidates.json"
    runtime_supply_candidate = tmp_path / "rich_leaf_runtime_supply_candidate.json"
    runtime_supply_regression = tmp_path / "runtime_supply_regression.json"
    field_candidates = tmp_path / "rich_leaf_field_candidates.json"
    artifact_candidates = tmp_path / "rich_leaf_artifact_candidates.json"
    field_promotion_review = tmp_path / "field_promotion_review.json"
    context_pack_smoke = tmp_path / "context_pack_smoke.json"
    fail_open_guard_diagnostic = tmp_path / "fail_open_guard_diagnostic.json"
    context_pack_projection_ab = tmp_path / "context_pack_projection_ab.json"
    semantic_runtime_offline_ab = tmp_path / "semantic_runtime_offline_ab.json"
    semantic_runtime_nearline_ab = tmp_path / "semantic_runtime_nearline_ab.json"
    semantic_runtime_live_ab_preflight = tmp_path / "live_ab_preflight.json"
    semantic_runtime_live_ab = tmp_path / "semantic_runtime_live_ab.json"
    semantic_runtime_near_live_smoke = tmp_path / "near_live_smoke.json"
    semantic_runtime_near_live_shadow_ab = tmp_path / "near_live_shadow_ab.json"
    shadow_residual_work_orders = tmp_path / "shadow_residual_work_orders.json"
    shadow_residual_review_packets = tmp_path / "shadow_residual_review_packets.json"
    shadow_residual_review_decision_validation = tmp_path / "shadow_residual_review_decision_validation.json"
    shadow_residual_review_decision_seed = tmp_path / "shadow_residual_review_decision_seed.json"
    shadow_residual_review_decisions = tmp_path / "ai_council_shadow_review_decisions.json"
    shadow_residual_audit_record = tmp_path / "shadow_residual_audit_record.json"
    shadow_residual_guard_patch_plan = tmp_path / "shadow_residual_guard_patch_plan.json"
    shadow_residual_guard_review_packets = tmp_path / "shadow_residual_guard_review_packets.json"
    shadow_residual_guard_review_decisions = tmp_path / "shadow_residual_guard_review_decisions.json"
    shadow_residual_guard_review_decision_validation = tmp_path / "shadow_residual_guard_review_decision_validation.json"
    shadow_residual_guard_audit_record = tmp_path / "shadow_residual_guard_audit_record.json"
    learning_evidence_candidate_bridge = tmp_path / "learning_evidence_candidate_bridge.json"
    pcp_nba_candidate_projection = tmp_path / "pcp_nba_candidate_projection.json"
    test_learner_sandbox_readback_gate = tmp_path / "test_learner_sandbox_readback_gate.json"
    authorized_writeback_preflight = tmp_path / "authorized_writeback_preflight.json"
    test_learner_writeback_authorization_package = tmp_path / "test_learner_writeback_authorization_package.json"
    test_learner_writeback_dry_run_manifest = tmp_path / "test_learner_writeback_dry_run_manifest.json"
    test_learner_writeback_execution_gate = tmp_path / "test_learner_writeback_execution_gate.json"
    learning_evidence_current_standard_compat_audit = tmp_path / "current_standard_compat_audit.json"
    external_source_closure = tmp_path / "external_source_closure.json"
    weak = tmp_path / "weak_source_refinement_work_orders.json"
    _write_json(
        sample,
        {
            "schema": "luban_rich_leaf_phase1_sample_manifest.v1",
            "selected_leaves": [{"leaf_id": "L1"}],
            "classification": {"candidate_only": True, "review_required": True},
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        skeleton,
        {
            "schema": "luban_rich_leaf_skeleton_batch.v1",
            "rich_leaf_artifacts": [{"leaf_id": "L1", "artifact_id": "A1", "candidate_status": "candidate"}],
            "classification": {"candidate_only": True, "review_required": True},
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        source_gap,
        {
            "schema": "luban_rich_leaf_source_gap_candidates.v1",
            "classification": {"candidate_only": True, "review_only": True},
            "source_gap_candidates": [
                {
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "missing_lane": "textbook",
                    "status": "strong_candidate_sources_found",
                    "candidates": [
                        {
                            "source_lane": "textbook",
                            "source_path": "教材原文/source.json",
                            "record_id": "TB1",
                            "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                            "candidate_only": True,
                            "install_allowed": False,
                        }
                    ],
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        patches,
        {
            "schema": "luban_rich_leaf_candidate_patch_batch.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "patches_apply_allowed": False,
                "runtime_install_allowed": False,
            },
            "candidate_patches": [
                {
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "missing_lane": "textbook",
                    "candidate_only": True,
                    "review_status": "pending_review",
                    "apply_allowed": False,
                    "runtime_install_allowed": False,
                    "source_ref_candidate": {
                        "source_lane": "textbook",
                        "path": "教材原文/source.json",
                        "record_id": "TB1",
                    },
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        weak,
        {
            "schema": "luban_rich_leaf_weak_source_refinement.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "work_orders_apply_allowed": False,
                "runtime_install_allowed": False,
            },
            "leaf_work_orders": [],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        rejected_feedback,
        {
            "schema": "luban_rich_leaf_rejected_patch_feedback.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "work_orders_apply_allowed": False,
                "runtime_install_allowed": False,
            },
            "rejected_patch_work_orders": [
                {
                    "patch_id": "P_BAD",
                    "leaf_id": "L2",
                    "artifact_id": "A2",
                    "missing_lane": "lecture",
                    "source_lane": "lecture",
                    "status": "rejected_patch_feedback",
                    "source_ref_candidate_reusable": False,
                    "promotion_allowed": False,
                    "runtime_install_allowed": False,
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        semantic_packets,
        {
            "schema": "luban_rich_leaf_semantic_audit_packets.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_verdict_recorded": False,
                "runtime_install_allowed": False,
            },
            "semantic_audit_packets": [
                {
                    "packet_id": "semantic_audit:P1",
                    "patch_id": "P1",
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "missing_lane": "textbook",
                    "review_status": "semantic_review_pending",
                    "semantic_verdict_recorded": False,
                    "allowed_decisions": ["accept_source_ref_candidate", "reject_wrong_leaf_source"],
                    "apply_allowed": False,
                    "runtime_install_allowed": False,
                    "candidate_only": True,
                    "source_ref_candidate": {
                        "source_lane": "textbook",
                        "record_id": "TB1",
                        "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                    },
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        source_evidence,
        {
            "schema": "luban_rich_leaf_source_evidence_agent.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_verdict_recorded": False,
                "runtime_install_allowed": False,
            },
            "source_corpus": {
                "docs_root": "/tmp/docs2026",
                "record_count": 2,
                "record_count_by_lane": {"question": 1, "textbook": 1},
            },
            "source_evidence_work_orders": [
                {
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "missing_lane": "textbook",
                    "status": "source_candidates_found",
                    "candidate_sources": [
                        {
                            "source_lane": "textbook",
                            "source_path": "2026教材/book.json",
                            "record_id": "TB1",
                            "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                            "span_hash": "hash1",
                            "support_candidate": True,
                            "candidate_only": True,
                            "install_allowed": False,
                            "runtime_install_allowed": False,
                        }
                    ],
                    "question_context_candidates": [
                        {
                            "source_lane": "question",
                            "source_path": "题库/exam.json",
                            "record_id": "Q1",
                            "span": "建筑设计程序案例题。",
                            "span_hash": "hash2",
                            "support_candidate": False,
                            "candidate_only": True,
                            "install_allowed": False,
                            "runtime_install_allowed": False,
                        }
                    ],
                    "review_status": "source_evidence_review_pending",
                    "candidate_only": True,
                    "review_only": True,
                    "promotion_allowed": False,
                    "runtime_install_allowed": False,
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        patch_audit,
        {
            "schema": "luban_rich_leaf_patch_evidence_audit.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "audit_apply_allowed": False,
                "runtime_install_allowed": False,
            },
            "patch_audits": [
                {
                    "patch_id": "P1",
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "missing_lane": "textbook",
                    "source_lane": "textbook",
                    "audit_decision": "machine_precheck_pass",
                    "review_status": "machine_precheck_only",
                    "apply_allowed": False,
                    "runtime_install_allowed": False,
                    "candidate_only": True,
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        semantic_queue,
        {
            "schema": "luban_rich_leaf_semantic_audit_queue.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_verdict_recorded": False,
                "runtime_install_allowed": False,
            },
            "semantic_audit_queue": [
                {
                    "audit_item_id": "audit_queue:patch:P1",
                    "audit_source_type": "patch_semantic_packet",
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "missing_lane": "textbook",
                    "source_candidate": {
                        "source_lane": "textbook",
                        "source_path": "教材原文/source.json",
                        "record_id": "TB1",
                        "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                        "span_hash": "hash1",
                        "support_candidate": True,
                        "candidate_only": True,
                        "install_allowed": False,
                        "runtime_install_allowed": False,
                    },
                    "question_context_candidates": [],
                    "allowed_decisions": ["accept_source_ref_candidate", "reject_wrong_leaf_source"],
                    "review_status": "semantic_review_pending",
                    "semantic_verdict_recorded": False,
                    "candidate_only": True,
                    "review_only": True,
                    "apply_allowed": False,
                    "runtime_install_allowed": False,
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        semantic_record,
        {
            "schema": "luban_rich_leaf_semantic_evidence_audit_record.v1",
            "classification": {
                "review_only": True,
                "semantic_verdict_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "audit_item_count": 1,
                "decision_record_count": 0,
                "not_exercised_count": 1,
                "invalid_decision_count": 0,
            },
            "invalid_decisions": [],
            "semantic_evidence_audit_records": [
                {
                    "audit_item_id": "audit_queue:patch:P1",
                    "audit_source_type": "patch_semantic_packet",
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "missing_lane": "textbook",
                    "review_decision_status": "not_exercised",
                    "decision": None,
                    "source_candidate": {
                        "source_lane": "textbook",
                        "source_path": "教材原文/source.json",
                        "record_id": "TB1",
                        "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                        "span_hash": "hash1",
                        "support_candidate": True,
                    },
                    "question_context_candidates": [],
                    "candidate_only": True,
                    "review_only": True,
                    "runtime_install_allowed": False,
                    "release_truth_claimed": False,
                    "official_score_allowed": False,
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        review_shards,
        {
            "schema": "luban_rich_leaf_semantic_review_shards.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "decisions_recorded": False,
                "runtime_install_allowed": False,
            },
            "summary": {"audit_item_count": 1, "shard_count": 1, "shard_size": 25},
            "shards": [{"shard_id": "semantic_review_shard_000", "path": "semantic_review_shard_000.json", "audit_item_count": 1}],
            "decision_output_schema": {
                "schema": "luban_rich_leaf_semantic_audit_decisions.v1",
                "allowed_decisions": [
                    "accept_source_ref_candidate",
                    "reject_wrong_leaf_source",
                    "needs_external_source",
                    "needs_leaf_split_or_retaxonomy",
                ],
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        review_suggestions,
        {
            "schema": "luban_rich_leaf_semantic_review_suggestions.v1",
            "classification": {
                "review_only": True,
                "suggestion_only": True,
                "decisions_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "audit_item_count": 1,
                "suggestion_count": 1,
                "suggested_accept_count": 0,
                "suggested_reject_count": 1,
                "manual_review_count": 0,
            },
            "suggestions": [
                {
                    "audit_item_id": "audit_queue:patch:P1",
                    "audit_source_type": "patch_semantic_packet",
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "missing_lane": "textbook",
                    "terminal_leaf": "建筑设计程序",
                    "suggested_decision": "reject_wrong_leaf_source",
                    "suggestion_confidence": "low",
                    "reason_codes": ["matched_terms_do_not_cover_terminal_leaf"],
                    "reviewer_must_confirm": True,
                    "decision_recorded": False,
                    "runtime_install_allowed": False,
                    "release_truth_claimed": False,
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        decision_validation,
        {
            "schema": "luban_rich_leaf_semantic_review_decision_validation.v1",
            "review_shards_schema": "luban_rich_leaf_semantic_review_shards.v1",
            "verdict": "INCOMPLETE",
            "classification": {
                "review_only": True,
                "decisions_recorded": False,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "audit_item_count": 1,
                "decision_count": 0,
                "missing_decision_count": 1,
                "invalid_decision_count": 0,
                "duplicate_decision_count": 0,
                "orphan_decision_count": 0,
            },
            "missing_audit_item_ids": ["audit_queue:patch:P1"],
            "invalid_decisions": [],
            "duplicate_decisions": [],
            "orphan_decisions": [],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        reviewed_candidates,
        {
            "schema": "luban_rich_leaf_reviewed_candidate_batch.v1",
            "semantic_evidence_audit_record_schema": "luban_rich_leaf_semantic_evidence_audit_record.v1",
            "classification": {
                "review_only": True,
                "candidate_only": True,
                "runtime_install_allowed": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "audit_record_count": 1,
                "accepted_source_ref_count": 0,
                "reviewed_candidate_count": 0,
                "not_accepted_count": 1,
            },
            "reviewed_candidates": [],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        runtime_supply_candidate,
        {
            "schema": "luban_rich_leaf_runtime_supply_candidate_bundle.v1",
            "version": "v_rich_leaf_runtime_supply_candidate_test",
            "status": "no_reviewed_candidates",
            "reviewed_candidate_schema": "luban_rich_leaf_reviewed_candidate_batch.v1",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "runtime_supply_candidate": True,
                "regression_required": True,
                "install_allowed": False,
                "runtime_install_allowed": False,
                "production_default": False,
                "canonical_pointer_written": False,
            },
            "summary": {
                "reviewed_candidate_count": 0,
                "supply_unit_count": 0,
                "rejected_candidate_count": 0,
            },
            "manifest": {
                "bundle_hash": "hash1",
                "hash_algorithm": "sha256",
                "included_file": "rich_leaf_runtime_supply_candidate.json",
                "source_artifact_schema": "luban_rich_leaf_reviewed_candidate_batch.v1",
            },
            "supply_units": [],
            "rejected_candidates": [],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        runtime_supply_regression,
        {
            "schema": "luban_rich_leaf_runtime_supply_regression.v1",
            "input_schema": "luban_rich_leaf_runtime_supply_candidate_bundle.v1",
            "input_version": "v_rich_leaf_runtime_supply_candidate_test",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "runtime_supply_regression": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "input_supply_unit_count": 0,
                "blocker_count": 0,
                "task_projection_count": 5,
                "grading_projected_unit_count": 0,
                "rag_answer_projected_unit_count": 0,
                "tutoring_projected_unit_count": 0,
                "next_action_projected_unit_count": 0,
            },
            "blockers": [],
            "task_projections": [
                {
                    "task": "grading",
                    "allowed_fields": ["source_refs"],
                    "allowed_source_lanes": ["textbook", "standard", "lecture", "question"],
                    "projected_unit_count": 0,
                    "projected_lane_counts": {},
                    "excluded_lane_counts": {},
                    "exclusion_reasons": {},
                    "projected_units": [],
                },
                {
                    "task": "tutoring",
                    "allowed_fields": ["source_refs"],
                    "allowed_source_lanes": ["textbook", "standard", "lecture"],
                    "projected_unit_count": 0,
                    "projected_lane_counts": {},
                    "excluded_lane_counts": {},
                    "exclusion_reasons": {},
                    "projected_units": [],
                },
                {
                    "task": "rag_answer",
                    "allowed_fields": ["source_refs"],
                    "allowed_source_lanes": ["textbook", "standard", "lecture"],
                    "projected_unit_count": 0,
                    "projected_lane_counts": {},
                    "excluded_lane_counts": {},
                    "exclusion_reasons": {},
                    "projected_units": [],
                },
                {
                    "task": "next_action",
                    "allowed_fields": ["teaching_cards", "exam_patterns", "common_mistakes", "learner_memory_event_templates"],
                    "allowed_source_lanes": [],
                    "projected_unit_count": 0,
                    "projected_lane_counts": {},
                    "excluded_lane_counts": {},
                    "exclusion_reasons": {},
                    "projected_units": [],
                },
                {
                    "task": "review",
                    "allowed_fields": ["all_candidate_fields"],
                    "allowed_source_lanes": ["textbook", "standard", "lecture", "question"],
                    "projected_unit_count": 0,
                    "projected_lane_counts": {},
                    "excluded_lane_counts": {},
                    "exclusion_reasons": {},
                    "projected_units": [],
                },
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        field_candidates,
        {
            "schema": "luban_rich_leaf_field_candidate_batch.v1",
            "reviewed_candidate_schema": "luban_rich_leaf_reviewed_candidate_batch.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "rich_field_candidate_batch": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "reviewed_candidate_count": 1,
                "generated_field_candidate_count": 1,
                "source_backed_knowledge_candidate_count": 1,
                "question_lane_exam_pattern_count": 0,
                "skipped_candidate_count": 0,
                "field_family_counts": {"rules": 1},
            },
            "field_candidates": [
                {
                    "field_candidate_id": "FC1",
                    "family": "rules",
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "derived_from_candidate_id": "RC1",
                    "claim_status": "candidate_only",
                    "candidate_only": True,
                    "review_only": True,
                    "runtime_install_allowed": False,
                    "release_truth_claimed": False,
                    "source_ref_trace": {
                        "source_lane": "textbook",
                        "source_path": "教材原文/source.json",
                        "record_id": "TB1",
                        "span": "施工单位应建立安全生产制度。",
                        "span_hash": "hash1",
                    },
                }
            ],
            "skipped_candidates": [],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        artifact_candidates,
        {
            "schema": "luban_rich_leaf_artifact_candidate_batch.v1",
            "field_candidate_schema": "luban_rich_leaf_field_candidate_batch.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "rich_leaf_artifact_candidate_batch": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "input_field_candidate_count": 1,
                "artifact_candidate_count": 1,
                "validation_failure_count": 0,
                "skipped_field_candidate_count": 0,
                "field_family_counts": {"rules": 1},
            },
            "rich_leaf_artifact_candidates": [
                {
                    "artifact_id": "A1:rich_leaf_candidate",
                    "leaf_id": "L1",
                    "bundle_version": "v_test",
                    "candidate_status": "reviewed_candidate",
                    "source_refs": [
                        {
                            "source_ref_id": "src_1",
                            "source_registry_id": "rich_leaf_reviewed_source_refs",
                            "source_dataset_id": "docs2026_textbook",
                            "source_version": "2026.0",
                            "extractor_version": "rich_leaf_field_candidate_compiler.v1",
                            "source_lane": "textbook",
                            "path": "教材原文/source.json",
                            "record_id": "TB1",
                            "span": "施工单位应建立安全生产制度。",
                            "span_hash": "0b12507ebdb6b0c49aa201a52af05a7d57b58fc68dcfaf15edbd3e4af99f344f",
                        }
                    ],
                    "definitions": [],
                    "rules": [
                        {
                            "field_id": "FC1",
                            "claim_status": "candidate_only",
                            "source_ref_ids": ["src_1"],
                            "statement": "施工单位应建立安全生产制度。",
                        }
                    ],
                    "procedures": [],
                    "numeric_constraints": [],
                    "negative_evidence": [],
                    "teaching_cards": [],
                    "rubric_link_index": [],
                    "common_mistakes": {"observed_mistakes": [], "hypothesized_mistakes": []},
                    "exam_patterns": [],
                    "learner_memory_event_templates": [],
                }
            ],
            "validation_reports": [{"leaf_id": "L1", "artifact_id": "A1:rich_leaf_candidate", "ok": True, "blockers": []}],
            "skipped_field_candidates": [],
            "blockers": [],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        field_promotion_review,
        {
            "schema": "luban_rich_leaf_field_promotion_review.v1",
            "input_schema": "luban_rich_leaf_artifact_candidate_batch.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "field_promotion_review": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "input_artifact_candidate_count": 1,
                "promoted_artifact_candidate_count": 1,
                "promotion_decision_count": 1,
                "source_backed_field_count": 1,
                "assessment_evidence_field_count": 0,
                "still_candidate_only_field_count": 0,
                "validation_failure_count": 0,
            },
            "promoted_rich_leaf_artifact_candidates": [
                {
                    "artifact_id": "A1:rich_leaf_candidate",
                    "leaf_id": "L1",
                    "bundle_version": "v_test",
                    "candidate_status": "reviewed_candidate",
                    "source_refs": [
                        {
                            "source_ref_id": "src_1",
                            "source_registry_id": "rich_leaf_reviewed_source_refs",
                            "source_dataset_id": "docs2026_textbook",
                            "source_version": "2026.0",
                            "extractor_version": "rich_leaf_field_candidate_compiler.v1",
                            "source_lane": "textbook",
                            "path": "教材原文/source.json",
                            "record_id": "TB1",
                            "span": "施工单位应建立安全生产制度。",
                            "span_hash": "0b12507ebdb6b0c49aa201a52af05a7d57b58fc68dcfaf15edbd3e4af99f344f",
                        }
                    ],
                    "definitions": [],
                    "rules": [
                        {
                            "field_id": "FC1",
                            "claim_status": "source_backed",
                            "candidate_only": False,
                            "review_only": True,
                            "source_ref_ids": ["src_1"],
                            "statement": "施工单位应建立安全生产制度。",
                        }
                    ],
                    "procedures": [],
                    "numeric_constraints": [],
                    "negative_evidence": [],
                    "teaching_cards": [],
                    "rubric_link_index": [],
                    "common_mistakes": {"observed_mistakes": [], "hypothesized_mistakes": []},
                    "exam_patterns": [],
                    "learner_memory_event_templates": [],
                }
            ],
            "promotion_decisions": [
                {
                    "artifact_id": "A1:rich_leaf_candidate",
                    "leaf_id": "L1",
                    "field_id": "FC1",
                    "family": "rules",
                    "from_status": "candidate_only",
                    "to_status": "source_backed",
                    "source_lanes": ["textbook"],
                    "rationale": "source_lane_supports_knowledge_field",
                    "runtime_install_allowed": False,
                    "release_truth_claimed": False,
                }
            ],
            "validation_reports": [{"leaf_id": "L1", "artifact_id": "A1:rich_leaf_candidate", "ok": True, "blockers": []}],
            "blockers": [],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        context_pack_smoke,
        {
            "schema": "luban_rich_leaf_context_pack_smoke.v1",
            "input_schema": "luban_rich_leaf_field_promotion_review.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "context_pack_smoke": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "input_promoted_artifact_count": 1,
                "task_pack_count": 5,
                "blocker_count": 0,
                "knowledge_task_question_lane_source_ref_count": 0,
            },
            "compiled_context_packs": [
                {
                    "task": task,
                    "field_count": 1 if task in {"grading", "tutoring", "rag_answer", "review"} else 0,
                    "source_ref_count": 1 if task in {"grading", "tutoring", "rag_answer"} else 0,
                    "source_ref_lanes": ["textbook"] if task in {"grading", "tutoring", "rag_answer"} else [],
                    "consumed_field_ids": ["FC1"] if task in {"grading", "tutoring", "rag_answer", "review"} else [],
                    "stripped_candidate_field_ids": [],
                    "rejected_field_ids": [],
                    "fail_closed_reasons": [],
                    "pack_hash": f"hash_{task}",
                    "canonical_write_allowed": False,
                    "production_write_count": 0,
                    "official_score_allowed": False,
                }
                for task in ("grading", "tutoring", "rag_answer", "next_action", "review")
            ],
            "blockers": [],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        fail_open_guard_diagnostic,
        {
            "schema": "luban_rich_leaf_fail_open_guard_diagnostic.v1",
            "input_schemas": {
                "field_promotion_review": "luban_rich_leaf_field_promotion_review.v1",
                "context_pack_smoke": "luban_rich_leaf_context_pack_smoke.v1",
            },
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "fail_open_guard_diagnostic": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
            },
            "summary": {
                "input_promoted_artifact_count": 1,
                "negative_evidence_candidate_count": 0,
                "review_candidate_field_count": 0,
                "top_leaf_count": 0,
                "blocker_count": 0,
            },
            "leaf_diagnostics": [],
            "blockers": [],
            "not_exercised": [
                "runtime_fail_open_reduction",
                "production_runtime_enforcement",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        context_pack_projection_ab,
        {
            "schema": "luban_rich_leaf_context_pack_projection_ab.v1",
            "input_schemas": {
                "artifact_candidates": "luban_rich_leaf_artifact_candidate_batch.v1",
                "field_promotion_review": "luban_rich_leaf_field_promotion_review.v1",
            },
            "verdict": "PASS",
            "verdict_ceiling": "PROJECTION_ONLY",
            "quality_claim_allowed": False,
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "context_pack_projection_ab": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "control_artifact_count": 1,
                "treatment_artifact_count": 1,
                "task_count": 5,
                "improved_task_count": 3,
                "knowledge_task_question_lane_leak_count": 0,
                "blocker_count": 0,
            },
            "effect_table": [
                {
                    "task": task,
                    "control_field_count": 0,
                    "treatment_field_count": 1 if task in {"grading", "tutoring", "rag_answer"} else 0,
                    "field_count_delta": 1 if task in {"grading", "tutoring", "rag_answer"} else 0,
                    "control_source_ref_count": 0,
                    "treatment_source_ref_count": 1 if task in {"grading", "tutoring", "rag_answer"} else 0,
                    "source_ref_count_delta": 1 if task in {"grading", "tutoring", "rag_answer"} else 0,
                    "control_source_ref_lanes": [],
                    "treatment_source_ref_lanes": ["textbook"] if task in {"grading", "tutoring", "rag_answer"} else [],
                    "control_token_proxy": 0,
                    "treatment_token_proxy": 100 if task in {"grading", "tutoring", "rag_answer"} else 0,
                    "token_proxy_delta": 100 if task in {"grading", "tutoring", "rag_answer"} else 0,
                    "knowledge_task_question_lane_leak": False,
                }
                for task in ("grading", "tutoring", "rag_answer", "next_action", "review")
            ],
            "blockers": [],
            "not_exercised": [
                "live_runtime_accuracy",
                "live_runtime_latency",
                "live_runtime_token_usage",
                "llm_judge_semantic_quality",
                "learner_outcome_gain",
                "production_default_decision",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        semantic_runtime_offline_ab,
        {
            "schema": "luban_rich_leaf_semantic_runtime_offline_ab.v1",
            "input_schema": "luban_rich_leaf_field_promotion_review.v1",
            "verdict": "PASS",
            "verdict_ceiling": "OFFLINE_ADAPTER_ONLY",
            "quality_claim_allowed": False,
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_runtime_offline_ab": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "eval_case_count": 1,
                "arm_count": 2,
                "blocker_count": 0,
                "treatment_answerable_rate": 1.0,
                "treatment_evidence_citation_rate": 1.0,
                "treatment_fail_open_rate": 0.0,
            },
            "effect_table": [
                {
                    "arm": "baseline_empty_context",
                    "sample_count": 1,
                    "answerable_rate": 0.0,
                    "abstention_rate": 1.0,
                    "term_hit_rate": 0.0,
                    "evidence_citation_rate": 0.0,
                    "fail_open_rate": 0.0,
                    "mean_token_proxy": 10.0,
                    "mean_latency_ms_proxy": 0.0,
                },
                {
                    "arm": "rich_leaf_promoted_context",
                    "sample_count": 1,
                    "answerable_rate": 1.0,
                    "abstention_rate": 0.0,
                    "term_hit_rate": 1.0,
                    "evidence_citation_rate": 1.0,
                    "fail_open_rate": 0.0,
                    "mean_token_proxy": 30.0,
                    "mean_latency_ms_proxy": 1.0,
                },
            ],
            "local_adapter_rows": [
                {
                    "arm": "rich_leaf_local_adapter",
                    "case_id": "near_live_shadow_0001",
                    "task": "rag_answer",
                    "artifact_id": "A1:rich_leaf_candidate",
                    "leaf_id": "L1",
                    "field_id": "FC1",
                    "family": "rules",
                    "answerable": True,
                    "term_hit": True,
                    "citation_count": 1,
                    "cited_source_ref_ids": ["src_1"],
                    "expected_source_ref_ids": ["src_1"],
                    "question_lane_citation_count": 0,
                    "fail_open": False,
                    "token_proxy": 30,
                    "latency_ms_local_proxy": 1,
                    "answer": {
                        "text": "施工单位应建立安全生产制度。",
                        "cited_source_ref_ids": ["src_1"],
                    },
                }
            ],
            "sample_rows": [],
            "blockers": [],
            "not_exercised": [
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
                "production_rag_retrieval",
                "learner_outcome_gain",
                "production_default_decision",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        semantic_runtime_nearline_ab,
        {
            "schema": "luban_rich_leaf_semantic_runtime_nearline_ab.v1",
            "input_schema": "luban_rich_leaf_field_promotion_review.v1",
            "verdict": "PASS",
            "verdict_ceiling": "NEARLINE_RETRIEVAL_PROJECTION",
            "quality_claim_allowed": False,
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_runtime_nearline_ab": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "eval_case_count": 1,
                "arm_count": 3,
                "blocker_count": 0,
                "current_rag_answerable_rate": 1.0,
                "current_rag_mean_token_proxy": 60.0,
                "treatment_answerable_rate": 1.0,
                "treatment_evidence_citation_rate": 1.0,
                "treatment_fail_open_rate": 0.0,
                "treatment_mean_token_proxy": 30.0,
                "treatment_token_proxy_delta_vs_current_rag": -30.0,
            },
            "effect_table": [
                {
                    "arm": "baseline_empty_context",
                    "sample_count": 1,
                    "answerable_rate": 0.0,
                    "abstention_rate": 1.0,
                    "term_hit_rate": 0.0,
                    "evidence_citation_rate": 0.0,
                    "fail_open_rate": 0.0,
                    "question_lane_citation_rate": 0.0,
                    "mean_token_proxy": 10.0,
                    "mean_latency_ms_proxy": 0.0,
                },
                {
                    "arm": "current_rag_lexical_retrieval",
                    "sample_count": 1,
                    "answerable_rate": 1.0,
                    "abstention_rate": 0.0,
                    "term_hit_rate": 1.0,
                    "evidence_citation_rate": 1.0,
                    "fail_open_rate": 0.0,
                    "question_lane_citation_rate": 0.0,
                    "mean_token_proxy": 60.0,
                    "mean_latency_ms_proxy": 4.0,
                },
                {
                    "arm": "rich_leaf_promoted_context",
                    "sample_count": 1,
                    "answerable_rate": 1.0,
                    "abstention_rate": 0.0,
                    "term_hit_rate": 1.0,
                    "evidence_citation_rate": 1.0,
                    "fail_open_rate": 0.0,
                    "question_lane_citation_rate": 0.0,
                    "mean_token_proxy": 30.0,
                    "mean_latency_ms_proxy": 1.0,
                },
            ],
            "sample_rows": [],
            "blockers": [],
            "not_exercised": [
                "production_rag_retrieval",
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
                "learner_outcome_gain",
                "production_default_decision",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        semantic_runtime_live_ab_preflight,
        {
            "schema": "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1",
            "input_schemas": {
                "field_promotion_review": "luban_rich_leaf_field_promotion_review.v1",
                "nearline_ab": "luban_rich_leaf_semantic_runtime_nearline_ab.v1",
            },
            "verdict": "READY_FOR_LIVE_RUNTIME_AB",
            "verdict_ceiling": "PREFLIGHT_ONLY",
            "quality_claim_allowed": False,
            "execution_mode": "preflight_only",
            "cohort_scope": "local_artifact_preflight",
            "auth_mode": "none",
            "runtime_entry": {
                "entrypoint": "not_exercised",
                "runtime_exercised": False,
                "runtime_trace_ids": [],
            },
            "provider_call_policy": {
                "provider_calls_allowed": False,
                "provider_call_count": 0,
                "models": [],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_recorded": False,
            },
            "source_bundle": {
                "field_promotion_schema": "luban_rich_leaf_field_promotion_review.v1",
                "nearline_schema": "luban_rich_leaf_semantic_runtime_nearline_ab.v1",
                "nearline_verdict_ceiling": "NEARLINE_RETRIEVAL_PROJECTION",
                "runtime_supply_candidate_id": None,
                "bundle_version": None,
                "manifest_hash": None,
                "pack_hash": None,
            },
            "evidence_validation": {
                "citation_rate": 1.0,
                "fail_open_rate": 0.0,
                "question_lane_citation_rate": 0.0,
                "wrong_path_rate": None,
                "span_hash_validation_exercised": False,
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_runtime_live_ab_preflight": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "blocker_count": 0,
                "promoted_artifact_candidate_count": 1,
                "source_backed_field_count": 1,
                "nearline_eval_case_count": 1,
                "nearline_current_rag_answerable_rate": 1.0,
                "nearline_treatment_answerable_rate": 1.0,
                "nearline_treatment_fail_open_rate": 0.0,
                "nearline_treatment_token_proxy_delta_vs_current_rag": -30.0,
                "live_runtime_executed": False,
                "provider_call_count": 0,
            },
            "planned_arms": [
                "current_rag_runtime",
                "legacy_runtime_or_projection",
                "rich_leaf_promoted_context",
                "artifact_first_llm_judge",
            ],
            "planned_metrics": [
                "accuracy_or_answerable_rate",
                "token_usage",
                "latency_ms",
                "evidence_citation_rate",
                "fail_open_rate",
                "high_risk_or_abstention_rate",
            ],
            "blockers": [],
            "not_exercised_by_layer": {
                "review_not_exercised": [],
                "runtime_not_exercised": [
                    "production_rag_retrieval",
                    "legacy_runtime_live_path",
                    "live_llm_semantic_judgment",
                    "live_runtime_latency",
                    "live_runtime_token_usage",
                ],
                "release_not_exercised": [
                    "production_default_decision",
                    "release_truth_governance",
                ],
            },
            "not_exercised": [
                "production_rag_retrieval",
                "legacy_runtime_live_path",
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
                "learner_outcome_gain",
                "production_default_decision",
                "release_truth_governance",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        semantic_runtime_live_ab,
        {
            "schema": "luban_rich_leaf_semantic_runtime_live_ab.v1",
            "input_schemas": {
                "live_ab_preflight": "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1",
            },
            "verdict": "BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED",
            "verdict_ceiling": "LIVE_RUNTIME_NOT_EXERCISED",
            "quality_claim_allowed": False,
            "execution_mode": "live_runtime_ab_blocked",
            "cohort_scope": "not_exercised_without_provider_authorization",
            "auth_mode": "none",
            "runtime_entry": {
                "entrypoint": "not_exercised",
                "runtime_exercised": False,
                "runtime_trace_ids": [],
            },
            "provider_call_policy": {
                "provider_calls_allowed": False,
                "provider_call_count": 0,
                "models": [],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_recorded": False,
            },
            "arms": [
                {
                    "arm": "current_rag_runtime",
                    "status": "not_exercised",
                    "sample_count": 0,
                    "provider_call_count": 0,
                    "quality_claim_allowed": False,
                },
                {
                    "arm": "legacy_runtime_or_projection",
                    "status": "not_exercised",
                    "sample_count": 0,
                    "provider_call_count": 0,
                    "quality_claim_allowed": False,
                },
                {
                    "arm": "rich_leaf_promoted_context",
                    "status": "not_exercised",
                    "sample_count": 0,
                    "provider_call_count": 0,
                    "quality_claim_allowed": False,
                },
                {
                    "arm": "artifact_first_llm_judge",
                    "status": "not_exercised",
                    "sample_count": 0,
                    "provider_call_count": 0,
                    "quality_claim_allowed": False,
                },
            ],
            "summary": {
                "blocker_count": 1,
                "planned_arm_count": 4,
                "live_case_count": 0,
                "live_runtime_executed": False,
                "provider_call_count": 0,
                "preflight_promoted_artifact_candidate_count": 1,
                "preflight_source_backed_field_count": 1,
                "preflight_nearline_eval_case_count": 1,
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_runtime_live_ab": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "blockers": ["provider_authorization_missing"],
            "not_exercised_by_layer": {
                "runtime_not_exercised": [
                    "production_rag_retrieval",
                    "legacy_runtime_live_path",
                    "live_llm_semantic_judgment",
                    "live_runtime_latency",
                    "live_runtime_token_usage",
                ],
                "release_not_exercised": [
                    "production_default_decision",
                    "release_truth_governance",
                ],
            },
            "not_exercised": [
                "production_rag_retrieval",
                "legacy_runtime_live_path",
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
                "learner_outcome_gain",
                "production_default_decision",
                "release_truth_governance",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        semantic_runtime_near_live_smoke,
        {
            "schema": "luban_rich_leaf_semantic_runtime_near_live_smoke.v1",
            "input_schemas": {
                "field_promotion_review": "luban_rich_leaf_field_promotion_review.v1",
                "live_ab_preflight": "luban_rich_leaf_semantic_runtime_live_ab_preflight.v1",
            },
            "verdict": "PASS",
            "verdict_ceiling": "NEAR_LIVE_LOCAL_ADAPTER_ONLY",
            "quality_claim_allowed": False,
            "execution_mode": "near_live_runtime",
            "cohort_scope": "local_fixture",
            "auth_mode": "none",
            "runtime_entry": {
                "entrypoint": "local_compiled_context_adapter",
                "runtime_exercised": True,
                "runtime_trace_ids": ["near_live_0001"],
            },
            "provider_call_policy": {
                "provider_calls_allowed": False,
                "provider_call_count": 0,
                "models": [],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_recorded": False,
            },
            "summary": {
                "blocker_count": 0,
                "smoke_case_count": 1,
                "answerable_rate": 1.0,
                "evidence_citation_rate": 1.0,
                "term_hit_rate": 1.0,
                "fail_open_rate": 0.0,
                "question_lane_citation_rate": 0.0,
                "live_runtime_executed": False,
                "provider_call_count": 0,
            },
            "evidence_validation": {
                "citation_rate": 1.0,
                "fail_open_rate": 0.0,
                "question_lane_citation_rate": 0.0,
                "span_hash_validation_exercised": False,
            },
            "smoke_rows": [
                {
                    "case_id": "near_live_0001",
                    "task": "rag_answer",
                    "field_id": "FC1",
                    "runtime_answer": {
                        "answer_text": "施工单位应建立安全生产制度。",
                        "cited_source_ref_ids": ["src_1"],
                        "abstained": False,
                    },
                    "answerable": True,
                    "term_hit": True,
                    "citation_count": 1,
                    "question_lane_citation_count": 0,
                    "fail_open": False,
                    "latency_ms_local_adapter_proxy": 1,
                }
            ],
            "blockers": [],
            "not_exercised_by_layer": {
                "review_not_exercised": [],
                "runtime_not_exercised": [
                    "production_rag_retrieval",
                    "legacy_runtime_live_path",
                    "live_llm_semantic_judgment",
                    "live_runtime_latency",
                    "live_runtime_token_usage",
                ],
                "release_not_exercised": [
                    "production_default_decision",
                    "release_truth_governance",
                ],
            },
            "not_exercised": [
                "production_rag_retrieval",
                "legacy_runtime_live_path",
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
                "learner_outcome_gain",
                "production_default_decision",
                "release_truth_governance",
            ],
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_runtime_near_live_smoke": True,
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
        },
    )
    _write_json(
        semantic_runtime_near_live_shadow_ab,
        {
            "schema": "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1",
            "input_schemas": {
                "field_promotion_review": "luban_rich_leaf_field_promotion_review.v1",
                "near_live_smoke": "luban_rich_leaf_semantic_runtime_near_live_smoke.v1",
            },
            "verdict": "PASS",
            "verdict_ceiling": "NEAR_LIVE_SHADOW_LOCAL_ADAPTER_ONLY",
            "quality_claim_allowed": False,
            "execution_mode": "near_live_shadow",
            "cohort_scope": "local_fixture",
            "auth_mode": "none",
            "runtime_entry": {
                "entrypoint": "local_compiled_context_adapter",
                "runtime_exercised": True,
                "runtime_trace_ids": ["near_live_shadow_0001"],
            },
            "provider_call_policy": {
                "provider_calls_allowed": False,
                "provider_call_count": 0,
                "models": [],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_recorded": False,
            },
            "summary": {
                "blocker_count": 0,
                "shadow_case_count": 1,
                "top_k": 2,
                "current_rag_answerable_rate": 1.0,
                "current_rag_mean_token_proxy": 60.0,
                "local_adapter_answerable_rate": 1.0,
                "local_adapter_evidence_citation_rate": 1.0,
                "local_adapter_fail_open_rate": 0.0,
                "local_adapter_question_lane_citation_rate": 0.0,
                "local_adapter_mean_token_proxy": 30.0,
                "local_adapter_token_delta_vs_rag_proxy": -30.0,
                "live_runtime_executed": False,
                "provider_call_count": 0,
            },
            "effect_table": [
                {
                    "arm": "current_rag_lexical_proxy",
                    "sample_count": 1,
                    "answerable_rate": 1.0,
                    "term_hit_rate": 1.0,
                    "evidence_citation_rate": 1.0,
                    "fail_open_rate": 0.0,
                    "question_lane_citation_rate": 0.0,
                    "mean_token_proxy": 60.0,
                    "mean_latency_ms_local_proxy": 4.0,
                },
                {
                    "arm": "rich_leaf_local_adapter",
                    "sample_count": 1,
                    "answerable_rate": 1.0,
                    "term_hit_rate": 1.0,
                    "evidence_citation_rate": 1.0,
                    "fail_open_rate": 0.0,
                    "question_lane_citation_rate": 0.0,
                    "mean_token_proxy": 30.0,
                    "mean_latency_ms_local_proxy": 1.0,
                },
            ],
            "sample_rows": [],
            "blockers": [],
            "not_exercised_by_layer": {
                "review_not_exercised": [],
                "runtime_not_exercised": [
                    "production_rag_retrieval",
                    "legacy_runtime_live_path",
                    "live_llm_semantic_judgment",
                    "live_runtime_latency",
                    "live_runtime_token_usage",
                ],
                "release_not_exercised": [
                    "production_default_decision",
                    "release_truth_governance",
                ],
            },
            "not_exercised": [
                "production_rag_retrieval",
                "legacy_runtime_live_path",
                "live_llm_semantic_judgment",
                "live_runtime_latency",
                "live_runtime_token_usage",
                "learner_outcome_gain",
                "production_default_decision",
                "release_truth_governance",
            ],
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "semantic_runtime_near_live_shadow_ab": True,
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
        },
    )
    _write_json(
        shadow_residual_work_orders,
        {
            "schema": "luban_rich_leaf_shadow_residual_work_orders.v1",
            "input_schemas": {
                "near_live_shadow_ab": "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1",
                "fail_open_guard_diagnostic": "luban_rich_leaf_fail_open_guard_diagnostic.v1",
            },
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_work_orders": True,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
            },
            "summary": {
                "runtime_residual_case_count": 0,
                "runtime_residual_work_order_count": 0,
                "guard_review_work_order_count": 0,
                "non_joinable_residual_count": 0,
                "work_order_count": 0,
                "blocker_count": 0,
            },
            "compiler_work_orders": [],
            "non_joinable_residuals": [],
            "blockers": [],
            "not_exercised": [
                "compiler_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "quality_claim",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_review_packets,
        {
            "schema": "luban_rich_leaf_shadow_residual_review_packets.v1",
            "input_schema": "luban_rich_leaf_shadow_residual_work_orders.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_review_packets": True,
                "decisions_recorded": False,
                "patch_generation_allowed": False,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
            },
            "summary": {
                "input_work_order_count": 0,
                "review_packet_count": 0,
                "non_joinable_residual_count": 0,
                "blocker_count": 0,
            },
            "review_packets": [],
            "non_joinable_residuals": [],
            "blockers": [],
            "not_exercised": [
                "semantic_decision_recording",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_review_decision_validation,
        {
            "schema": "luban_rich_leaf_shadow_residual_review_decision_validation.v1",
            "input_schema": "luban_rich_leaf_shadow_residual_review_packets.v1",
            "verdict": "INCOMPLETE",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_review_decision_validation": True,
                "decisions_recorded": False,
                "patch_generation_allowed": False,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
            },
            "summary": {
                "packet_count": 0,
                "decision_count": 0,
                "missing_decision_count": 0,
                "invalid_decision_count": 0,
                "duplicate_decision_count": 0,
                "stale_decision_count": 0,
                "blocker_count": 0,
            },
            "missing_packet_ids": [],
            "invalid_decisions": [],
            "duplicate_decisions": [],
            "stale_decisions_ignored": [],
            "blockers": [],
            "not_exercised": [
                "audit_record_ingestion",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_review_decision_seed,
        {
            "schema": "luban_rich_leaf_shadow_residual_review_decision_seed.v1",
            "input_schemas": {
                "review_packets": "luban_rich_leaf_shadow_residual_review_packets.v1",
                "decision_validation": "luban_rich_leaf_shadow_residual_review_decision_validation.v1",
            },
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_review_decision_seed": True,
                "suggestion_only": True,
                "decisions_recorded": False,
                "patch_generation_allowed": False,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
            },
            "summary": {
                "packet_count": 0,
                "missing_packet_count": 0,
                "seed_suggestion_count": 0,
                "blocker_count": 0,
            },
            "decision_seed_suggestions": [],
            "blockers": [],
            "not_exercised": [
                "decision_recording",
                "decision_validation_replay",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_review_decisions,
        {
            "schema": "luban_rich_leaf_shadow_residual_review_decisions.v1",
            "input_schemas": {
                "review_packets": "luban_rich_leaf_shadow_residual_review_packets.v1",
                "decision_seed": "luban_rich_leaf_shadow_residual_review_decision_seed.v1",
            },
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "ai_council_shadow_only": True,
                "decisions_recorded": False,
                "patch_generation_allowed": False,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
            },
            "summary": {
                "packet_count": 0,
                "seed_suggestion_count": 0,
                "decision_count": 0,
                "blocker_count": 0,
            },
            "decisions": [],
            "blockers": [],
            "not_exercised": [
                "human_reviewer_signoff",
                "governance_signoff",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_audit_record,
        {
            "schema": "luban_rich_leaf_shadow_residual_audit_record.v1",
            "input_schemas": {
                "review_packets": "luban_rich_leaf_shadow_residual_review_packets.v1",
                "review_decisions": "luban_rich_leaf_shadow_residual_review_decisions.v1",
                "decision_validation": "luban_rich_leaf_shadow_residual_review_decision_validation.v1",
            },
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_audit_record": True,
                "ai_council_shadow_only": True,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
            "summary": {
                "packet_count": 0,
                "decision_count": 0,
                "audit_record_count": 0,
                "blocker_count": 0,
                "guard_review_required_count": 0,
                "source_ref_reaudit_required_count": 0,
                "leaf_retaxonomy_required_count": 0,
                "dismissed_after_shadow_review_count": 0,
            },
            "shadow_residual_audit_records": [],
            "blockers": [],
            "not_exercised": [
                "human_reviewer_signoff",
                "governance_signoff",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_guard_patch_plan,
        {
            "schema": "luban_rich_leaf_shadow_residual_guard_patch_plan.v1",
            "input_schema": "luban_rich_leaf_shadow_residual_audit_record.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_guard_patch_plan": True,
                "ai_council_shadow_only": True,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
            "summary": {
                "audit_record_count": 0,
                "guard_plan_item_count": 0,
                "source_ref_reaudit_required_count": 0,
                "leaf_retaxonomy_required_count": 0,
                "dismissed_after_shadow_review_count": 0,
                "blocker_count": 0,
            },
            "guard_plan_items": [],
            "blockers": [],
            "not_exercised": [
                "human_reviewer_signoff",
                "governance_signoff",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "runtime_install",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_guard_review_packets,
        {
            "schema": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
            "input_schema": "luban_rich_leaf_shadow_residual_guard_patch_plan.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_guard_review_packets": True,
                "ai_council_shadow_only": True,
                "decisions_recorded": False,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
            "summary": {
                "guard_plan_item_count": 0,
                "guard_review_packet_count": 0,
                "decision_count": 0,
                "blocker_count": 0,
            },
            "guard_review_packets": [],
            "blockers": [],
            "not_exercised": [
                "human_reviewer_decision",
                "governance_signoff",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "runtime_install",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_guard_review_decisions,
        {
            "schema": "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
            "input_schema": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_guard_review_decisions": True,
                "ai_council_shadow_only": True,
                "decisions_recorded": True,
                "human_reviewer_signoff": False,
                "governance_signoff": False,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
            "summary": {
                "guard_review_packet_count": 0,
                "decision_count": 0,
                "blocker_count": 0,
            },
            "decisions": [],
            "blockers": [],
            "not_exercised": [
                "human_reviewer_signoff",
                "governance_signoff",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "runtime_install",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_guard_review_decision_validation,
        {
            "schema": "luban_rich_leaf_shadow_residual_guard_review_decision_validation.v1",
            "input_schema": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_guard_review_decision_validation": True,
                "decisions_recorded": False,
                "human_reviewer_signoff": False,
                "governance_signoff": False,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
            "summary": {
                "guard_review_packet_count": 0,
                "decision_count": 0,
                "missing_decision_count": 0,
                "invalid_decision_count": 0,
                "duplicate_decision_count": 0,
                "stale_decision_count": 0,
                "blocker_count": 0,
            },
            "missing_guard_review_packet_ids": [],
            "invalid_decisions": [],
            "duplicate_decisions": [],
            "stale_decisions_ignored": [],
            "blockers": [],
            "not_exercised": [
                "audit_record_ingestion",
                "human_reviewer_signoff",
                "governance_signoff",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        shadow_residual_guard_audit_record,
        {
            "schema": "luban_rich_leaf_shadow_residual_guard_audit_record.v1",
            "input_schemas": {
                "guard_review_packets": "luban_rich_leaf_shadow_residual_guard_review_packets.v1",
                "guard_review_decisions": "luban_rich_leaf_shadow_residual_guard_review_decisions.v1",
                "guard_review_decision_validation": "luban_rich_leaf_shadow_residual_guard_review_decision_validation.v1",
            },
            "verdict": "PASS",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "shadow_residual_guard_audit_record": True,
                "ai_council_shadow_only": True,
                "human_reviewer_signoff": False,
                "governance_signoff": False,
                "patch_generation_allowed": False,
                "source_ref_mutation_allowed": False,
                "runtime_install_allowed": False,
                "runtime_guard_enforcement_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
                "learner_memory_write_allowed": False,
            },
            "summary": {
                "guard_review_packet_count": 0,
                "decision_count": 0,
                "audit_record_count": 0,
                "confirm_guard_patch_candidate_count": 0,
                "request_guard_scope_narrowing_count": 0,
                "request_source_ref_reaudit_count": 0,
                "reject_guard_not_needed_count": 0,
                "blocker_count": 0,
            },
            "shadow_residual_guard_audit_records": [],
            "blockers": [],
            "not_exercised": [
                "human_reviewer_signoff",
                "governance_signoff",
                "candidate_patch_generation",
                "source_ref_mutation",
                "runtime_guard_enforcement",
                "runtime_install",
                "learner_memory_writeback",
            ],
            "safety": {
                "canonical_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    _write_json(
        learning_evidence_candidate_bridge,
        {
            "schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
            "input_schema": "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1",
            "verdict": "PASS",
            "quality_claim_allowed": False,
            "execution_mode": "candidate_bridge",
            "summary": {
                "blocker_count": 0,
                "source_shadow_case_count": 1,
                "local_adapter_row_count": 1,
                "candidate_event_count": 1,
                "learner_memory_write_count": 0,
                "provider_call_count": 0,
            },
            "learning_evidence_event_candidates": [
                {
                    "event_type": "learning_evidence",
                    "memory_kind": "learning_evidence",
                    "source_feature": "rich_leaf_shadow_candidate",
                    "candidate_only": True,
                    "preview_only": True,
                    "claim_promotion_allowed": False,
                    "mastery_raised": False,
                    "canonical_truth_written": False,
                    "quality": {
                        "candidate_only": True,
                        "authority": "rich_leaf_shadow_candidate",
                        "writeback_eligible": False,
                        "progress_countable": False,
                        "truth_eligible": False,
                        "stable_truth_eligible": False,
                        "evidence_level": "preview_needs_retest",
                    },
                    "rich_leaf_trace": {
                        "case_id": "near_live_shadow_0001",
                        "task": "rag_answer",
                        "artifact_id": "A1:rich_leaf_candidate",
                        "leaf_id": "L1",
                        "field_id": "FC1",
                        "family": "rules",
                        "cited_source_ref_ids": ["src_1"],
                    },
                }
            ],
            "not_exercised_by_layer": {
                "memory_not_exercised": [
                    "learner_memory_db_write",
                    "learner_memory_event_id_assignment",
                    "canonical_learner_truth_write",
                ],
                "learning_brain_not_exercised": [
                    "personalization_context_pack_readback",
                    "learner_claim_projection",
                    "next_best_action_generation",
                    "real_student_outcome",
                ],
                "release_not_exercised": ["governance_signoff", "production_default_decision"],
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "learning_evidence_candidate_bridge": True,
                "learner_memory_write_allowed": False,
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
                "learner_memory_write_count": 0,
                "canonical_learner_truth_written": False,
            },
        },
    )
    _write_json(
        pcp_nba_candidate_projection,
        {
            "schema": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
            "input_schema": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
            "verdict": "PASS",
            "quality_claim_allowed": False,
            "execution_mode": "dry_run_candidate_projection",
            "summary": {
                "blocker_count": 0,
                "candidate_event_count": 1,
                "valid_candidate_event_count": 1,
                "top_claim_candidate_count": 1,
                "next_action_candidate_count": 1,
                "learner_memory_write_count": 0,
                "pcp_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
                "provider_call_count": 0,
            },
            "personalization_context_pack_candidate": {
                "schema_version": 1,
                "source": "PersonalizationContextPackCandidate",
                "candidate_only": True,
                "readback_verified": False,
                "personalization_level": "generic_candidate",
                "authority": {
                    "evidence": "learning_evidence_candidate_bridge",
                    "claims": "candidate_projection_not_learning_synthesis",
                    "prescription": "not_exercised_training_intent",
                },
                "top_claim_candidates": [
                    {
                        "claim_id": "rich_leaf_claim_candidate_1",
                        "claim_status": "candidate_preview",
                        "candidate_only": True,
                        "truth_eligible": False,
                        "concept_id": "L1",
                        "label": "L1/FC1",
                        "artifact_id": "A1:rich_leaf_candidate",
                        "field_id": "FC1",
                        "family": "rules",
                        "evidence_refs": ["rich_leaf_le_candidate_1"],
                        "source_ref_ids": ["src_1"],
                    }
                ],
                "next_action_candidates": [
                    {
                        "action_id": "rich_leaf_next_action_candidate_1",
                        "candidate_only": True,
                        "source": "rich_leaf_pcp_nba_candidate_projection",
                        "prescription_authority": "not_exercised_training_intent",
                        "status": "candidate_not_prescription",
                        "rank": 1,
                        "personalization_level": "generic_candidate",
                        "target": "L1/FC1",
                        "evidence_refs": ["rich_leaf_le_candidate_1"],
                        "retest_target": None,
                    }
                ],
            },
            "next_action_candidates": [
                {
                    "action_id": "rich_leaf_next_action_candidate_1",
                    "candidate_only": True,
                    "source": "rich_leaf_pcp_nba_candidate_projection",
                    "prescription_authority": "not_exercised_training_intent",
                    "status": "candidate_not_prescription",
                    "rank": 1,
                    "personalization_level": "generic_candidate",
                    "target": "L1/FC1",
                    "evidence_refs": ["rich_leaf_le_candidate_1"],
                    "retest_target": None,
                }
            ],
            "blockers": [],
            "not_exercised_by_layer": {
                "memory_not_exercised": ["learner_memory_db_write", "canonical_learner_truth_write"],
                "learning_brain_not_exercised": [
                    "learning_synthesis",
                    "personalization_context_pack_readback",
                    "training_intent_creation",
                    "next_best_action_generation",
                    "retest_delta",
                ],
                "release_not_exercised": ["governance_signoff", "production_default_decision"],
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "pcp_nba_candidate_projection": True,
                "learner_memory_write_allowed": False,
                "personalization_context_pack_readback_allowed": False,
                "next_best_action_write_allowed": False,
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
                "learner_memory_write_count": 0,
                "canonical_learner_truth_written": False,
                "personalization_context_pack_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
            },
        },
    )
    _write_json(
        test_learner_sandbox_readback_gate,
        {
            "schema": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
            "input_schemas": {
                "learning_evidence_candidate_bridge": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
                "pcp_nba_candidate_projection": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
            },
            "verdict": "PASS",
            "quality_claim_allowed": False,
            "execution_mode": "artifact_only_sandbox_readback",
            "sandbox": {
                "sandbox_user_id": "rich_leaf_sandbox_learner",
                "sandbox_events_path": "sandbox_memory_events.jsonl",
                "write_scope": "artifact_only",
            },
            "summary": {
                "blocker_count": 0,
                "candidate_event_count": 1,
                "valid_candidate_event_count": 1,
                "sandbox_event_write_count": 1,
                "sandbox_readback_event_count": 1,
                "synthesis_observed_candidate_count": 0,
                "synthesis_compiled_object_count": 0,
                "learner_memory_write_count": 0,
                "production_write_count": 0,
                "provider_call_count": 0,
            },
            "blockers": [],
            "not_exercised_by_layer": {
                "memory_not_exercised": [
                    "learner_state_service_append_memory_event",
                    "learner_memory_db_write",
                    "learner_memory_outbox_enqueue",
                    "canonical_learner_truth_write",
                ],
                "learning_brain_not_exercised": [
                    "production_learning_synthesis",
                    "personalization_context_pack_readback",
                    "training_intent_creation",
                    "next_best_action_generation",
                ],
                "release_not_exercised": ["governance_signoff", "production_default_decision"],
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "test_learner_sandbox_readback_gate": True,
                "sandbox_write_scope": "artifact_only",
                "learner_memory_write_allowed": False,
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
                "learner_memory_write_count": 0,
                "canonical_learner_truth_written": False,
                "personalization_context_pack_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
            },
        },
    )
    _write_json(
        authorized_writeback_preflight,
        {
            "schema": "luban_rich_leaf_authorized_writeback_preflight.v1",
            "input_schemas": {
                "test_learner_sandbox_readback_gate": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
                "pcp_nba_candidate_projection": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
            },
            "verdict": "READY_FOR_AUTHORIZATION_REVIEW",
            "quality_claim_allowed": False,
            "execution_mode": "authorization_preflight_only",
            "authorization": {
                "explicit_user_authorization_required": True,
                "test_learner_writeback_authorized": False,
                "allowed_write_scope": "none_without_authorization",
                "canonical_truth_authorized": False,
                "production_db_authorized": False,
            },
            "writeback_plan_candidate": {
                "target_memory_kind": "learning_evidence",
                "target_source_feature": "rich_leaf_authorized_test_writeback",
                "target_user_scope": "test_learner_only_after_explicit_authorization",
                "max_candidate_event_count": 1,
                "canonical_truth_after_writeback": "still_forbidden_without_separate_authorization",
            },
            "summary": {
                "blocker_count": 0,
                "candidate_event_count": 1,
                "sandbox_readback_event_count": 1,
                "top_claim_candidate_count": 1,
                "next_action_candidate_count": 1,
                "writeback_executed": False,
                "learner_memory_write_count": 0,
                "canonical_truth_write_count": 0,
                "production_write_count": 0,
                "provider_call_count": 0,
            },
            "missing_authorizations": [
                "explicit_user_authorization",
                "test_learner_identity_scope",
                "teacher_final_or_governance_review",
                "rollback_plan_for_test_learner_writeback",
                "separate_canonical_truth_authorization",
            ],
            "blockers": [],
            "not_exercised_by_layer": {
                "memory_not_exercised": [
                    "learner_state_service_append_memory_event",
                    "learner_memory_db_write",
                    "learner_memory_outbox_enqueue",
                    "supabase_learner_memory_events_write",
                ],
                "learning_brain_not_exercised": [
                    "production_learning_synthesis",
                    "personalization_context_pack_readback",
                    "training_intent_creation",
                    "next_best_action_generation",
                    "canonical_truth_write",
                ],
                "release_not_exercised": ["governance_signoff", "production_default_decision"],
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "authorized_writeback_preflight": True,
                "test_learner_writeback_allowed": False,
                "learner_memory_write_allowed": False,
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
                "learner_memory_write_count": 0,
                "canonical_learner_truth_written": False,
                "personalization_context_pack_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
            },
        },
    )
    _write_json(
        test_learner_writeback_authorization_package,
        {
            "schema": "luban_rich_leaf_test_learner_writeback_authorization_package.v1",
            "input_schemas": {
                "authorized_writeback_preflight": "luban_rich_leaf_authorized_writeback_preflight.v1",
            },
            "verdict": "READY_FOR_USER_AUTHORIZATION_DECISION",
            "quality_claim_allowed": False,
            "execution_mode": "authorization_package_only",
            "authorization_decision": {
                "explicit_user_authorization_required": True,
                "user_authorization_recorded": False,
                "test_learner_writeback_authorized": False,
                "allowed_write_scope": "none_without_signed_authorization",
                "canonical_truth_authorized": False,
                "production_db_authorized": False,
            },
            "candidate_scope": {
                "target_memory_kind": "learning_evidence",
                "target_source_feature": "rich_leaf_authorized_test_writeback",
                "target_user_scope": "test_learner_only_after_explicit_authorization",
                "max_candidate_event_count": 1,
                "top_claim_candidate_count": 1,
                "next_action_candidate_count": 1,
            },
            "rollback_plan": {
                "plan_status": "draft_review_required",
                "pre_write_snapshot_required": True,
                "delete_by_source_feature_required": True,
                "rollback_artifacts": [
                    "pre_write_learner_memory_snapshot",
                    "write_batch_manifest",
                    "post_write_readback_report",
                ],
            },
            "summary": {
                "blocker_count": 0,
                "candidate_event_count": 1,
                "writeback_executed": False,
                "learner_memory_write_count": 0,
                "canonical_truth_write_count": 0,
                "production_write_count": 0,
                "provider_call_count": 0,
            },
            "missing_authorizations": [
                "signed_user_authorization_record",
                "concrete_test_learner_id",
                "teacher_final_or_governance_review",
                "approved_rollback_plan",
                "separate_canonical_truth_authorization",
            ],
            "blockers": [],
            "not_exercised_by_layer": {
                "memory_not_exercised": [
                    "learner_state_service_append_memory_event",
                    "learner_memory_db_write",
                    "learner_memory_outbox_enqueue",
                ],
                "learning_brain_not_exercised": [
                    "production_learning_synthesis",
                    "personalization_context_pack_readback",
                    "training_intent_creation",
                    "next_best_action_generation",
                ],
                "release_not_exercised": ["canonical_truth_write", "production_default_decision"],
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "test_learner_writeback_authorization_package": True,
                "test_learner_writeback_allowed": False,
                "learner_memory_write_allowed": False,
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
                "learner_memory_write_count": 0,
                "canonical_learner_truth_written": False,
                "personalization_context_pack_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
            },
        },
    )
    _write_json(
        test_learner_writeback_dry_run_manifest,
        {
            "schema": "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1",
            "input_schemas": {
                "test_learner_sandbox_readback_gate": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
                "test_learner_writeback_authorization_package": "luban_rich_leaf_test_learner_writeback_authorization_package.v1",
            },
            "verdict": "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION",
            "quality_claim_allowed": False,
            "execution_mode": "dry_run_manifest_only",
            "target_scope": {
                "target_user_id": "not_bound_without_authorization",
                "target_memory_kind": "learning_evidence",
                "target_source_feature": "rich_leaf_authorized_test_writeback",
                "target_user_scope": "test_learner_only_after_explicit_authorization",
            },
            "write_batch_candidate": {
                "batch_id": "rich_leaf_writeback_dry_run_batch_1",
                "event_count": 1,
                "idempotency_key_count": 1,
                "write_allowed": False,
            },
            "rollback_selector": {
                "target_user_id": "not_bound_without_authorization",
                "source_feature": "rich_leaf_authorized_test_writeback",
                "batch_id": "rich_leaf_writeback_dry_run_batch_1",
                "rollback_allowed": False,
            },
            "event_write_candidates": [
                {
                    "planned_event_id": "rich_leaf_writeback_dry_run_event_1",
                    "source_event_id": "rich_leaf_le_candidate_1",
                    "target_user_id": "not_bound_without_authorization",
                    "source_feature": "rich_leaf_authorized_test_writeback",
                    "memory_kind": "learning_evidence",
                    "idempotency_key": "rich_leaf_writeback_dry_run_idempotency_1",
                    "write_allowed": False,
                    "payload_json": {
                        "candidate_event_id": "rich_leaf_le_candidate_1",
                        "candidate_only": True,
                        "quality": {
                            "writeback_eligible": False,
                            "progress_countable": False,
                            "truth_eligible": False,
                            "stable_truth_eligible": False,
                        },
                    },
                }
            ],
            "summary": {
                "blocker_count": 0,
                "candidate_event_count": 1,
                "planned_event_count": 1,
                "writeback_executed": False,
                "learner_memory_write_count": 0,
                "canonical_truth_write_count": 0,
                "production_write_count": 0,
                "provider_call_count": 0,
            },
            "blockers": [],
            "not_exercised_by_layer": {
                "memory_not_exercised": [
                    "learner_state_service_append_memory_event",
                    "learner_memory_db_write",
                    "learner_memory_outbox_enqueue",
                    "canonical_learner_truth_write",
                ],
                "learning_brain_not_exercised": [
                    "production_learning_synthesis",
                    "personalization_context_pack_readback",
                    "training_intent_creation",
                    "next_best_action_generation",
                ],
                "release_not_exercised": ["canonical_truth_write", "production_default_decision"],
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "test_learner_writeback_dry_run_manifest": True,
                "test_learner_writeback_allowed": False,
                "learner_memory_write_allowed": False,
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
                "learner_memory_write_count": 0,
                "canonical_learner_truth_written": False,
                "personalization_context_pack_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
            },
        },
    )
    _write_json(
        test_learner_writeback_execution_gate,
        {
            "schema": "luban_rich_leaf_test_learner_writeback_execution_gate.v1",
            "input_schemas": {
                "test_learner_writeback_dry_run_manifest": "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1",
            },
            "verdict": "BLOCKED_PENDING_SIGNED_AUTHORIZATION",
            "quality_claim_allowed": False,
            "execution_mode": "execution_gate_only",
            "execution_decision": {
                "writeback_allowed": False,
                "writeback_executed": False,
                "target_user_id_bound": False,
                "signed_authorization_recorded": False,
                "rollback_plan_approved": False,
            },
            "blocking_reasons": [
                "signed_user_authorization_missing",
                "target_user_unbound",
                "rollback_plan_not_approved",
            ],
            "summary": {
                "blocker_count": 0,
                "dry_run_planned_event_count": 1,
                "writeback_executed": False,
                "learner_memory_write_count": 0,
                "canonical_truth_write_count": 0,
                "production_write_count": 0,
                "provider_call_count": 0,
            },
            "blockers": [],
            "not_exercised_by_layer": {
                "memory_not_exercised": [
                    "learner_state_service_append_memory_event",
                    "learner_memory_db_write",
                    "learner_memory_outbox_enqueue",
                    "canonical_learner_truth_write",
                ],
                "learning_brain_not_exercised": [
                    "production_learning_synthesis",
                    "personalization_context_pack_readback",
                    "training_intent_creation",
                    "next_best_action_generation",
                ],
                "release_not_exercised": ["canonical_truth_write", "production_default_decision"],
            },
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "test_learner_writeback_execution_gate": True,
                "test_learner_writeback_allowed": False,
                "learner_memory_write_allowed": False,
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
                "learner_memory_write_count": 0,
                "canonical_learner_truth_written": False,
                "personalization_context_pack_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
            },
        },
    )
    _write_json(
        learning_evidence_current_standard_compat_audit,
        {
            "schema": "luban_rich_leaf_learning_evidence_current_standard_compat_audit.v1",
            "input_schemas": {
                "learning_evidence_candidate_bridge": "luban_rich_leaf_learning_evidence_candidate_bridge.v1",
                "pcp_nba_candidate_projection": "luban_rich_leaf_pcp_nba_candidate_projection.v1",
                "test_learner_sandbox_readback_gate": "luban_rich_leaf_test_learner_sandbox_readback_gate.v1",
                "test_learner_writeback_dry_run_manifest": "luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1",
                "test_learner_writeback_execution_gate": "luban_rich_leaf_test_learner_writeback_execution_gate.v1",
            },
            "verdict": "PASS",
            "quality_claim_allowed": False,
            "execution_mode": "current_standard_compat_audit_only",
            "classification": {
                "candidate_only": True,
                "review_only": True,
                "learning_evidence_current_standard_compat_audit": True,
                "current_standard_readback_verified": False,
                "learner_memory_write_allowed": False,
                "personalization_context_pack_readback_allowed": False,
                "next_best_action_write_allowed": False,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
            },
            "summary": {
                "candidate_event_count": 1,
                "not_current_standard_payload_count": 1,
                "standard_accepted_source_feature_count": 0,
                "current_standard_readback_verified": False,
                "pcp_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
                "sandbox_synthesis_observed_candidate_count": 0,
                "sandbox_synthesis_compiled_object_count": 0,
                "dry_run_planned_event_count": 1,
                "execution_gate_dry_run_planned_event_count": 1,
                "learner_memory_write_count": 0,
                "canonical_truth_write_count": 0,
                "production_write_count": 0,
                "blocker_count": 0,
            },
            "candidate_event_compat_findings": [
                {
                    "candidate_event_id": "rich_leaf_le_candidate_1",
                    "source_feature": "rich_leaf_shadow_candidate",
                    "current_standard_payload": False,
                    "current_standard_readback_verified": False,
                    "writeback_eligible": False,
                    "candidate_only": True,
                    "incompatibility_reasons": [
                        "source_feature_not_accepted",
                        "candidate_only",
                        "writeback_eligible_false",
                    ],
                }
            ],
            "pcp_nba_compat_finding": {
                "current_standard_pcp": False,
                "current_standard_readback_verified": False,
                "pcp_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
            },
            "sandbox_compat_finding": {
                "sandbox_write_scope": "artifact_only",
                "synthesis_observed_candidate_count": 0,
                "synthesis_compiled_object_count": 0,
                "current_standard_synthesis_consumed_candidate": False,
            },
            "dry_run_manifest_finding": {
                "target_user_id_bound": False,
                "write_allowed": False,
                "planned_event_count": 1,
                "writeback_executed": False,
            },
            "execution_gate_finding": {
                "writeback_allowed": False,
                "writeback_executed": False,
                "target_user_id_bound": False,
                "signed_authorization_recorded": False,
                "dry_run_planned_event_count": 1,
            },
            "blockers": [],
            "not_exercised": [
                "learner_memory_db_write",
                "canonical_learner_truth_write",
                "learning_synthesis_current_standard_consumption",
                "personalization_context_pack_readback",
                "training_intent_creation",
                "next_best_action_generation",
                "test_learner_writeback",
                "production_db_write",
            ],
            "safety": {
                "canonical_truth_written": False,
                "canonical_learner_truth_written": False,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
                "learner_memory_write_count": 0,
                "personalization_context_pack_readback_count": 0,
                "training_intent_write_count": 0,
                "next_best_action_write_count": 0,
            },
        },
    )
    _write_json(
        external_source_closure,
        {
            "schema": "luban_rich_leaf_external_source_closure.v1",
            "input_schemas": {
                "semantic_evidence_audit_record": "luban_rich_leaf_semantic_evidence_audit_record.v1"
            },
            "verdict": "PASS",
            "classification": {
                "review_only": True,
                "candidate_only": True,
                "external_source_closure": True,
                "source_truth_claimed": False,
                "runtime_install_allowed": False,
                "production_default": False,
                "release_truth_claimed": False,
                "quality_claim_allowed": False,
            },
            "summary": {
                "needs_external_source_count": 1,
                "closures_with_candidates": 0,
                "external_source_required_count": 1,
                "closure_candidate_count": 0,
                "question_context_candidate_count": 1,
                "source_truth_write_count": 0,
                "runtime_install_count": 0,
                "blocker_count": 0,
            },
            "external_source_closures": [
                {
                    "audit_item_id": "audit-1",
                    "leaf_id": "L1",
                    "artifact_id": "A1",
                    "field": "rules",
                    "missing_lane": "standard",
                    "terms": ["工程预付款"],
                    "status": "external_source_required",
                    "candidate_sources": [],
                    "question_context_candidates": [
                        {
                            "source_lane": "question",
                            "source_path": "题库/case.md",
                            "record_id": "Q1",
                            "support_candidate": False,
                            "candidate_only": True,
                            "install_allowed": False,
                            "runtime_install_allowed": False,
                        }
                    ],
                    "candidate_only": True,
                    "review_only": True,
                    "source_truth_claimed": False,
                    "promotion_allowed": False,
                    "runtime_install_allowed": False,
                }
            ],
            "safety": {
                "canonical_truth_written": False,
                "source_truth_write_count": 0,
                "official_score_allowed": False,
                "installed_runtime_supply": False,
                "production_write_count": 0,
                "release_truth_claimed": False,
            },
        },
    )
    return {
        "sample": sample,
        "skeleton": skeleton,
        "source_gap": source_gap,
        "patches": patches,
        "patch_audit": patch_audit,
        "rejected_feedback": rejected_feedback,
        "semantic_packets": semantic_packets,
        "source_evidence": source_evidence,
        "semantic_queue": semantic_queue,
        "semantic_record": semantic_record,
        "review_shards": review_shards,
        "review_suggestions": review_suggestions,
        "decision_validation": decision_validation,
        "reviewed_candidates": reviewed_candidates,
        "runtime_supply_candidate": runtime_supply_candidate,
        "runtime_supply_regression": runtime_supply_regression,
        "field_candidates": field_candidates,
        "artifact_candidates": artifact_candidates,
        "field_promotion_review": field_promotion_review,
        "context_pack_smoke": context_pack_smoke,
        "fail_open_guard_diagnostic": fail_open_guard_diagnostic,
        "context_pack_projection_ab": context_pack_projection_ab,
        "semantic_runtime_offline_ab": semantic_runtime_offline_ab,
        "semantic_runtime_nearline_ab": semantic_runtime_nearline_ab,
        "semantic_runtime_live_ab_preflight": semantic_runtime_live_ab_preflight,
        "semantic_runtime_live_ab": semantic_runtime_live_ab,
        "semantic_runtime_near_live_smoke": semantic_runtime_near_live_smoke,
        "semantic_runtime_near_live_shadow_ab": semantic_runtime_near_live_shadow_ab,
        "shadow_residual_work_orders": shadow_residual_work_orders,
        "shadow_residual_review_packets": shadow_residual_review_packets,
        "shadow_residual_review_decision_validation": shadow_residual_review_decision_validation,
        "shadow_residual_review_decision_seed": shadow_residual_review_decision_seed,
        "shadow_residual_review_decisions": shadow_residual_review_decisions,
        "shadow_residual_audit_record": shadow_residual_audit_record,
        "shadow_residual_guard_patch_plan": shadow_residual_guard_patch_plan,
        "shadow_residual_guard_review_packets": shadow_residual_guard_review_packets,
        "shadow_residual_guard_review_decisions": shadow_residual_guard_review_decisions,
        "shadow_residual_guard_review_decision_validation": shadow_residual_guard_review_decision_validation,
        "shadow_residual_guard_audit_record": shadow_residual_guard_audit_record,
        "learning_evidence_candidate_bridge": learning_evidence_candidate_bridge,
        "pcp_nba_candidate_projection": pcp_nba_candidate_projection,
        "test_learner_sandbox_readback_gate": test_learner_sandbox_readback_gate,
        "authorized_writeback_preflight": authorized_writeback_preflight,
        "test_learner_writeback_authorization_package": test_learner_writeback_authorization_package,
        "test_learner_writeback_dry_run_manifest": test_learner_writeback_dry_run_manifest,
        "test_learner_writeback_execution_gate": test_learner_writeback_execution_gate,
        "learning_evidence_current_standard_compat_audit": learning_evidence_current_standard_compat_audit,
        "external_source_closure": external_source_closure,
        "weak": weak,
    }


def test_interop_audit_accepts_valid_review_only_batch(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop
    from deeptutor.services.construction_grading.rich_leaf_workbench_contracts import RICH_LEAF_WORKBENCH_STAGE_SCHEMAS

    paths = _valid_artifacts(tmp_path)
    report = audit_interop(**paths)

    assert report["verdict"] == "PASS"
    assert report["summary"]["blocker_count"] == 0
    assert report["summary"]["warning_count"] == 0
    assert report["summary"]["artifact_count"] == 49
    assert report["summary"]["artifact_count"] == len(RICH_LEAF_WORKBENCH_STAGE_SCHEMAS)


def test_interop_audit_blocks_polluted_patch_support_lane(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    patches = json.loads(paths["patches"].read_text("utf-8"))
    patches["candidate_patches"][0]["source_ref_candidate"]["path"] = "ZL864 MCQ Import practice book"
    _write_json(paths["patches"], patches)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("polluted_patch_support_lane" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_fail_open_guard_quality_claim(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    diagnostic = json.loads(paths["fail_open_guard_diagnostic"].read_text("utf-8"))
    diagnostic["classification"]["quality_claim_allowed"] = True
    _write_json(paths["fail_open_guard_diagnostic"], diagnostic)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "fail_open_guard_diagnostic_authority_allowed:quality_claim_allowed" in report["blockers"]


def test_interop_audit_blocks_question_source_evidence_as_support_candidate(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    source_evidence = json.loads(paths["source_evidence"].read_text("utf-8"))
    candidate = source_evidence["source_evidence_work_orders"][0]["candidate_sources"][0]
    candidate["source_lane"] = "question"
    candidate["source_path"] = "题库/exam.json"
    _write_json(paths["source_evidence"], source_evidence)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("source_evidence_question_support_candidate" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_source_evidence_unknown_corpus_lanes(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    source_evidence = json.loads(paths["source_evidence"].read_text("utf-8"))
    source_evidence["source_corpus"]["record_count_by_lane"]["residual"] = 1
    _write_json(paths["source_evidence"], source_evidence)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "source_evidence_unknown_corpus_lane:residual" in report["blockers"]


def test_interop_audit_blocks_semantic_queue_recorded_verdict(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    semantic_queue = json.loads(paths["semantic_queue"].read_text("utf-8"))
    semantic_queue["semantic_audit_queue"][0]["semantic_verdict_recorded"] = True
    _write_json(paths["semantic_queue"], semantic_queue)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("semantic_queue_verdict_recorded" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_semantic_record_runtime_install(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    semantic_record = json.loads(paths["semantic_record"].read_text("utf-8"))
    semantic_record["semantic_evidence_audit_records"][0]["runtime_install_allowed"] = True
    _write_json(paths["semantic_record"], semantic_record)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("semantic_record_runtime_or_release_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_review_shards_recorded_decisions(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    review_shards = json.loads(paths["review_shards"].read_text("utf-8"))
    review_shards["classification"]["decisions_recorded"] = True
    _write_json(paths["review_shards"], review_shards)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("review_shards_decisions_or_runtime_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_review_suggestion_recorded_decision(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    suggestions = json.loads(paths["review_suggestions"].read_text("utf-8"))
    suggestions["classification"]["decisions_recorded"] = True
    suggestions["suggestions"][0]["decision_recorded"] = True
    _write_json(paths["review_suggestions"], suggestions)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("review_suggestion_decision_recorded" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_failed_decision_validation(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    validation = json.loads(paths["decision_validation"].read_text("utf-8"))
    validation["verdict"] = "FAIL"
    validation["summary"]["invalid_decision_count"] = 1
    _write_json(paths["decision_validation"], validation)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("decision_validation_failed_or_invalid" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_live_ab_quality_claim_or_provider_calls(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    live_ab = json.loads(paths["semantic_runtime_live_ab"].read_text("utf-8"))
    live_ab["quality_claim_allowed"] = True
    live_ab["summary"]["provider_call_count"] = 1
    live_ab["provider_call_policy"]["provider_call_count"] = 1
    live_ab["arms"][0]["provider_call_count"] = 1
    _write_json(paths["semantic_runtime_live_ab"], live_ab)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("semantic_runtime_live_ab_quality_claim_allowed" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_live_ab_provider_calls_present" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_reviewed_candidate_runtime_install(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    reviewed = json.loads(paths["reviewed_candidates"].read_text("utf-8"))
    reviewed["reviewed_candidates"].append(
        {
            "candidate_id": "RC1",
            "candidate_status": "reviewed_candidate",
            "leaf_id": "L1",
            "artifact_id": "A1",
            "missing_lane": "textbook",
            "audit_item_id": "audit_queue:patch:P1",
            "field_patch": {
                "field": "source_refs",
                "operation": "add_source_ref",
                "source_ref": {
                    "source_lane": "textbook",
                    "source_path": "教材原文/source.json",
                    "record_id": "TB1",
                    "span": "建筑设计程序包括方案设计、初步设计和施工图设计。",
                    "span_hash": "hash1",
                    "support_candidate": True,
                },
            },
            "review_authority": {"decision": "accept_source_ref_candidate"},
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": True,
            "release_truth_claimed": False,
            "official_score_allowed": False,
        }
    )
    reviewed["summary"]["accepted_source_ref_count"] = 1
    reviewed["summary"]["reviewed_candidate_count"] = 1
    reviewed["summary"]["not_accepted_count"] = 0
    _write_json(paths["reviewed_candidates"], reviewed)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("reviewed_candidate_runtime_or_release_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_runtime_supply_candidate_install_or_default(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    candidate = json.loads(paths["runtime_supply_candidate"].read_text("utf-8"))
    candidate["classification"]["runtime_install_allowed"] = True
    candidate["classification"]["production_default"] = True
    _write_json(paths["runtime_supply_candidate"], candidate)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("runtime_supply_candidate_install_or_default_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_failed_runtime_supply_regression(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    regression = json.loads(paths["runtime_supply_regression"].read_text("utf-8"))
    regression["verdict"] = "FAIL"
    regression["summary"]["blocker_count"] = 1
    regression["blockers"] = ["classification_runtime_install_allowed"]
    _write_json(paths["runtime_supply_regression"], regression)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("runtime_supply_regression_failed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_question_lane_knowledge_field_candidate(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    fields = json.loads(paths["field_candidates"].read_text("utf-8"))
    fields["field_candidates"][0]["family"] = "rules"
    fields["field_candidates"][0]["source_ref_trace"]["source_lane"] = "question"
    _write_json(paths["field_candidates"], fields)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("field_candidate_question_lane_knowledge_field" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_invalid_rich_leaf_artifact_candidate(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    artifacts = json.loads(paths["artifact_candidates"].read_text("utf-8"))
    artifacts["rich_leaf_artifact_candidates"][0]["official_score_allowed"] = True
    _write_json(paths["artifact_candidates"], artifacts)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("artifact_candidate_validation_failed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_question_lane_source_backed_promotion(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    promotion = json.loads(paths["field_promotion_review"].read_text("utf-8"))
    artifact = promotion["promoted_rich_leaf_artifact_candidates"][0]
    artifact["source_refs"][0]["source_lane"] = "question"
    artifact["source_refs"][0]["source_dataset_id"] = "docs2026_question"
    promotion["promotion_decisions"][0]["source_lanes"] = ["question"]
    _write_json(paths["field_promotion_review"], promotion)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("field_promotion_review_bad_source_backed_promotion" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_context_pack_question_lane_knowledge_leak(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    smoke = json.loads(paths["context_pack_smoke"].read_text("utf-8"))
    smoke["compiled_context_packs"][2]["source_ref_lanes"] = ["question"]
    smoke["summary"]["knowledge_task_question_lane_source_ref_count"] = 1
    _write_json(paths["context_pack_smoke"], smoke)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("context_pack_smoke_question_lane_knowledge_leak" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_projection_ab_quality_claim_or_leak(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    ab = json.loads(paths["context_pack_projection_ab"].read_text("utf-8"))
    ab["quality_claim_allowed"] = True
    ab["effect_table"][2]["treatment_source_ref_lanes"] = ["question"]
    ab["summary"]["knowledge_task_question_lane_leak_count"] = 1
    _write_json(paths["context_pack_projection_ab"], ab)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("context_pack_projection_ab_quality_claim_allowed" in blocker for blocker in report["blockers"])
    assert any("context_pack_projection_ab_question_lane_knowledge_leak" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_semantic_runtime_offline_quality_claim_or_fail_open(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    ab = json.loads(paths["semantic_runtime_offline_ab"].read_text("utf-8"))
    ab["quality_claim_allowed"] = True
    ab["summary"]["treatment_fail_open_rate"] = 0.5
    ab["effect_table"][1]["fail_open_rate"] = 0.5
    _write_json(paths["semantic_runtime_offline_ab"], ab)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("semantic_runtime_offline_ab_quality_claim_allowed" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_offline_ab_treatment_fail_open" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_semantic_runtime_nearline_quality_claim_or_fail_open(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    ab = json.loads(paths["semantic_runtime_nearline_ab"].read_text("utf-8"))
    ab["quality_claim_allowed"] = True
    ab["summary"]["treatment_fail_open_rate"] = 0.5
    ab["effect_table"][2]["fail_open_rate"] = 0.5
    _write_json(paths["semantic_runtime_nearline_ab"], ab)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("semantic_runtime_nearline_ab_quality_claim_allowed" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_nearline_ab_treatment_fail_open" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_live_ab_preflight_quality_claim_or_provider_calls(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    preflight = json.loads(paths["semantic_runtime_live_ab_preflight"].read_text("utf-8"))
    preflight["quality_claim_allowed"] = True
    preflight["summary"]["provider_call_count"] = 1
    preflight["summary"]["live_runtime_executed"] = True
    _write_json(paths["semantic_runtime_live_ab_preflight"], preflight)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("semantic_runtime_live_ab_preflight_quality_claim_allowed" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_live_ab_preflight_provider_calls_present" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_live_ab_preflight_live_runtime_executed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_near_live_smoke_quality_claim_or_question_lane(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    smoke = json.loads(paths["semantic_runtime_near_live_smoke"].read_text("utf-8"))
    smoke["quality_claim_allowed"] = True
    smoke["runtime_entry"]["runtime_exercised"] = False
    smoke["summary"]["question_lane_citation_rate"] = 0.5
    smoke["evidence_validation"]["question_lane_citation_rate"] = 0.5
    _write_json(paths["semantic_runtime_near_live_smoke"], smoke)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("semantic_runtime_near_live_smoke_quality_claim_allowed" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_near_live_smoke_runtime_not_exercised" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_near_live_smoke_question_lane_citation" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_near_live_shadow_quality_claim_or_fail_open(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    shadow = json.loads(paths["semantic_runtime_near_live_shadow_ab"].read_text("utf-8"))
    shadow["quality_claim_allowed"] = True
    shadow["summary"]["local_adapter_fail_open_rate"] = 0.5
    shadow["summary"]["provider_call_count"] = 1
    _write_json(paths["semantic_runtime_near_live_shadow_ab"], shadow)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("semantic_runtime_near_live_shadow_ab_quality_claim_allowed" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_near_live_shadow_ab_local_adapter_fail_open" in blocker for blocker in report["blockers"])
    assert any("semantic_runtime_near_live_shadow_ab_provider_calls_present" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_shadow_residual_work_order_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    work_orders = json.loads(paths["shadow_residual_work_orders"].read_text("utf-8"))
    work_orders["classification"]["quality_claim_allowed"] = True
    work_orders["compiler_work_orders"].append(
        {
            "work_order_id": "WO_BAD",
            "leaf_id": "L1",
            "trigger_reason": "local_adapter_runtime_residual",
            "priority": "high",
            "action": "review_source_refs_and_pack_guard_for_leaf",
            "candidate_only": True,
            "review_only": True,
            "apply_allowed": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        }
    )
    work_orders["summary"]["work_order_count"] = 1
    _write_json(paths["shadow_residual_work_orders"], work_orders)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_work_orders_authority_allowed:quality_claim_allowed" in report["blockers"]
    assert "shadow_residual_work_order_authority_allowed:L1" in report["blockers"]


def test_interop_audit_blocks_shadow_residual_review_packet_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    packets = json.loads(paths["shadow_residual_review_packets"].read_text("utf-8"))
    packets["classification"]["patch_generation_allowed"] = True
    packets["review_packets"].append(
        {
            "packet_id": "shadow_residual_review_packet:WO_BAD",
            "work_order_id": "WO_BAD",
            "leaf_id": "L1",
            "trigger_reason": "local_adapter_runtime_residual",
            "priority": "high",
            "review_scope": "runtime_residual_source_ref_review",
            "work_order_trace": {},
            "review_questions": [],
            "allowed_decisions": ["confirm_guard_needed"],
            "decision_recorded": True,
            "patch_generation_allowed": True,
            "apply_allowed": False,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
            "candidate_only": True,
            "review_only": True,
        }
    )
    packets["summary"]["review_packet_count"] = 1
    _write_json(paths["shadow_residual_review_packets"], packets)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_review_packets_authority_allowed:patch_generation_allowed" in report["blockers"]
    assert "shadow_residual_review_packet_decision_recorded:shadow_residual_review_packet:WO_BAD" in report["blockers"]
    assert "shadow_residual_review_packet_authority_allowed:shadow_residual_review_packet:WO_BAD" in report["blockers"]


def test_interop_audit_blocks_shadow_residual_review_decision_validation_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    validation = json.loads(paths["shadow_residual_review_decision_validation"].read_text("utf-8"))
    validation["classification"]["patch_generation_allowed"] = True
    validation["summary"]["invalid_decision_count"] = 1
    _write_json(paths["shadow_residual_review_decision_validation"], validation)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_review_decision_validation_authority_allowed:patch_generation_allowed" in report["blockers"]
    assert "shadow_residual_review_decision_validation_invalid_decision_count:1" in report["blockers"]


def test_interop_audit_blocks_shadow_residual_review_decision_seed_as_recorded_decision(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    seed = json.loads(paths["shadow_residual_review_decision_seed"].read_text("utf-8"))
    seed["classification"]["decisions_recorded"] = True
    seed["decision_seed_suggestions"] = [
        {
            "seed_id": "shadow_residual_decision_seed:P1",
            "packet_id": "P1",
            "suggested_decision": "confirm_guard_needed",
            "reviewer_must_confirm": True,
            "decision_recorded": True,
            "patch_generation_allowed": False,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        }
    ]
    seed["summary"]["seed_suggestion_count"] = 1
    _write_json(paths["shadow_residual_review_decision_seed"], seed)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_review_decision_seed_authority_allowed:decisions_recorded" in report["blockers"]
    assert (
        "shadow_residual_review_decision_seed_confirmation_or_decision_invalid:shadow_residual_decision_seed:P1"
        in report["blockers"]
    )


def test_interop_audit_blocks_shadow_residual_review_decision_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    decisions = json.loads(paths["shadow_residual_review_decisions"].read_text("utf-8"))
    decisions["classification"]["patch_generation_allowed"] = True
    decisions["decisions"] = [
        {
            "packet_id": "shadow_residual_review_packet:WO_1",
            "decision": "confirm_guard_needed",
            "reviewer_role": "ai_council_shadow_reviewer",
            "reviewer_id": "codex_ai_council_shadow_v1",
            "rationale": "Trace supports the selected residual review action.",
            "confidence": "medium",
            "decision_recorded": True,
            "shadow_only": True,
            "patch_generation_allowed": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        }
    ]
    decisions["summary"]["decision_count"] = 1
    _write_json(paths["shadow_residual_review_decisions"], decisions)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_review_decisions_authority_allowed:patch_generation_allowed" in report["blockers"]
    assert any("shadow_residual_review_decision_authority_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_shadow_residual_audit_record_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    audit_record = json.loads(paths["shadow_residual_audit_record"].read_text("utf-8"))
    audit_record["classification"]["runtime_guard_enforcement_allowed"] = True
    audit_record["shadow_residual_audit_records"] = [
        {
            "audit_record_id": "shadow_residual_audit_record:P1",
            "packet_id": "P1",
            "work_order_id": "WO1",
            "leaf_id": "L1",
            "decision": "confirm_guard_needed",
            "next_compiler_action": "guard_review_required",
            "shadow_only": True,
            "candidate_only": True,
            "review_only": True,
            "patch_generation_allowed": False,
            "source_ref_mutation_allowed": False,
            "runtime_install_allowed": False,
            "runtime_guard_enforcement_allowed": True,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
            "learner_memory_write_allowed": False,
        }
    ]
    audit_record["summary"]["audit_record_count"] = 1
    audit_record["summary"]["guard_review_required_count"] = 1
    _write_json(paths["shadow_residual_audit_record"], audit_record)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_audit_record_authority_allowed:runtime_guard_enforcement_allowed" in report["blockers"]
    assert any("shadow_residual_audit_record_entry_authority_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_shadow_residual_guard_patch_plan_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    guard_plan = json.loads(paths["shadow_residual_guard_patch_plan"].read_text("utf-8"))
    guard_plan["classification"]["runtime_guard_enforcement_allowed"] = True
    guard_plan["guard_plan_items"] = [
        {
            "guard_plan_item_id": "shadow_residual_guard_plan:AR1",
            "audit_record_id": "AR1",
            "packet_id": "P1",
            "work_order_id": "WO1",
            "leaf_id": "L1",
            "planned_guard_action": "block_positive_context_until_source_ref_reviewed",
            "plan_status": "review_required",
            "reason_codes": ["negative_evidence_conflict"],
            "source_lanes": ["textbook"],
            "record_ids": ["R1"],
            "field_ids": ["F1"],
            "artifact_ids": ["A1"],
            "residual_case_ids": ["case-1"],
            "tasks": ["rag_answer"],
            "candidate_only": True,
            "review_only": True,
            "patch_generation_allowed": False,
            "source_ref_mutation_allowed": False,
            "runtime_install_allowed": False,
            "runtime_guard_enforcement_allowed": True,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
            "learner_memory_write_allowed": False,
        }
    ]
    guard_plan["summary"]["guard_plan_item_count"] = 1
    _write_json(paths["shadow_residual_guard_patch_plan"], guard_plan)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_guard_patch_plan_authority_allowed:runtime_guard_enforcement_allowed" in report["blockers"]
    assert any("shadow_residual_guard_patch_plan_item_authority_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_shadow_residual_guard_review_packets_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    guard_packets = json.loads(paths["shadow_residual_guard_review_packets"].read_text("utf-8"))
    guard_packets["classification"]["decisions_recorded"] = True
    guard_packets["classification"]["patch_generation_allowed"] = True
    guard_packets["guard_review_packets"] = [
        {
            "guard_review_packet_id": "shadow_residual_guard_review_packet:GP1",
            "guard_plan_item_id": "GP1",
            "audit_record_id": "AR1",
            "packet_id": "P1",
            "work_order_id": "WO1",
            "leaf_id": "L1",
            "review_scope": "runtime_guard_candidate_review",
            "planned_guard_action": "block_positive_context_until_source_ref_reviewed",
            "allowed_decisions": [
                "confirm_guard_patch_candidate",
                "request_guard_scope_narrowing",
                "request_source_ref_reaudit",
                "reject_guard_not_needed",
            ],
            "review_questions": ["question"],
            "evidence_trace": {
                "record_ids": ["R1"],
                "source_lanes": ["textbook"],
                "reason_codes": ["negative_evidence_conflict"],
                "field_ids": ["F1"],
                "artifact_ids": ["A1"],
                "residual_case_ids": [],
                "tasks": ["rag_answer"],
                "guard_evidence_count": 1,
            },
            "decision_recorded": True,
            "candidate_only": True,
            "review_only": True,
            "patch_generation_allowed": True,
            "source_ref_mutation_allowed": False,
            "runtime_install_allowed": False,
            "runtime_guard_enforcement_allowed": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
            "learner_memory_write_allowed": False,
        }
    ]
    guard_packets["summary"]["guard_review_packet_count"] = 1
    guard_packets["summary"]["decision_count"] = 1
    _write_json(paths["shadow_residual_guard_review_packets"], guard_packets)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_guard_review_packets_decisions_recorded" in report["blockers"]
    assert "shadow_residual_guard_review_packets_authority_allowed:patch_generation_allowed" in report["blockers"]
    assert any("shadow_residual_guard_review_packet_decision_recorded" in blocker for blocker in report["blockers"])
    assert any("shadow_residual_guard_review_packet_authority_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_shadow_residual_guard_review_decisions_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    decisions = json.loads(paths["shadow_residual_guard_review_decisions"].read_text("utf-8"))
    decisions["classification"]["runtime_guard_enforcement_allowed"] = True
    decisions["decisions"] = [
        {
            "decision_id": "shadow_residual_guard_review_decision:P1",
            "guard_review_packet_id": "P1",
            "guard_plan_item_id": "GP1",
            "audit_record_id": "AR1",
            "packet_id": "P0",
            "work_order_id": "WO1",
            "leaf_id": "L1",
            "decision": "confirm_guard_patch_candidate",
            "decision_recorded": True,
            "reviewer_role": "ai_council_shadow_guard_reviewer",
            "reviewer_id": "codex_ai_council_shadow_guard_v1",
            "shadow_only": True,
            "human_reviewer_signoff": False,
            "governance_signoff": False,
            "evidence_trace": {
                "record_ids": ["R1"],
                "source_lanes": ["textbook"],
                "reason_codes": ["negative_evidence_conflict"],
            },
            "candidate_only": True,
            "review_only": True,
            "patch_generation_allowed": False,
            "source_ref_mutation_allowed": False,
            "runtime_install_allowed": False,
            "runtime_guard_enforcement_allowed": True,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
            "learner_memory_write_allowed": False,
        }
    ]
    decisions["summary"]["decision_count"] = 1
    decisions["summary"]["guard_review_packet_count"] = 1
    _write_json(paths["shadow_residual_guard_review_decisions"], decisions)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_guard_review_decisions_authority_allowed:runtime_guard_enforcement_allowed" in report["blockers"]
    assert any("shadow_residual_guard_review_decision_authority_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_shadow_residual_guard_review_decision_validation_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    validation = json.loads(paths["shadow_residual_guard_review_decision_validation"].read_text("utf-8"))
    validation["classification"]["runtime_guard_enforcement_allowed"] = True
    validation["summary"]["invalid_decision_count"] = 1
    validation["invalid_decisions"] = [{"reason": "authority_drift"}]
    _write_json(paths["shadow_residual_guard_review_decision_validation"], validation)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_guard_review_decision_validation_authority_allowed:runtime_guard_enforcement_allowed" in report["blockers"]
    assert "shadow_residual_guard_review_decision_validation_failed_or_invalid" in report["blockers"]


def test_interop_audit_blocks_shadow_residual_guard_audit_record_authority_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    audit_record = json.loads(paths["shadow_residual_guard_audit_record"].read_text("utf-8"))
    audit_record["classification"]["runtime_guard_enforcement_allowed"] = True
    _write_json(paths["shadow_residual_guard_audit_record"], audit_record)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "shadow_residual_guard_audit_record_authority_allowed:runtime_guard_enforcement_allowed" in report["blockers"]


def test_interop_audit_blocks_learning_evidence_bridge_write_authority(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    bridge = json.loads(paths["learning_evidence_candidate_bridge"].read_text("utf-8"))
    bridge["classification"]["learner_memory_write_allowed"] = True
    bridge["safety"]["learner_memory_write_count"] = 1
    bridge["learning_evidence_event_candidates"][0]["claim_promotion_allowed"] = True
    _write_json(paths["learning_evidence_candidate_bridge"], bridge)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("learning_evidence_candidate_bridge_memory_write_allowed" in blocker for blocker in report["blockers"])
    assert any("learning_evidence_candidate_bridge_learner_memory_write_count" in blocker for blocker in report["blockers"])
    assert any("learning_evidence_candidate_claim_promotion_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_pcp_nba_projection_readback_or_action_write(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    projection = json.loads(paths["pcp_nba_candidate_projection"].read_text("utf-8"))
    projection["classification"]["personalization_context_pack_readback_allowed"] = True
    projection["classification"]["next_best_action_write_allowed"] = True
    projection["safety"]["next_best_action_write_count"] = 1
    projection["personalization_context_pack_candidate"]["readback_verified"] = True
    projection["next_action_candidates"][0]["prescription_authority"] = "training_intent"
    _write_json(paths["pcp_nba_candidate_projection"], projection)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("pcp_nba_candidate_projection_pcp_readback_allowed" in blocker for blocker in report["blockers"])
    assert any("pcp_nba_candidate_projection_next_action_write_allowed" in blocker for blocker in report["blockers"])
    assert any("pcp_nba_candidate_projection_next_best_action_write_count" in blocker for blocker in report["blockers"])
    assert any("pcp_nba_candidate_projection_pcp_readback_verified" in blocker for blocker in report["blockers"])
    assert any("pcp_nba_candidate_projection_action_prescription_authority" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_test_learner_sandbox_truth_leak(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    gate = json.loads(paths["test_learner_sandbox_readback_gate"].read_text("utf-8"))
    gate["summary"]["synthesis_observed_candidate_count"] = 1
    gate["summary"]["learner_memory_write_count"] = 1
    gate["classification"]["learner_memory_write_allowed"] = True
    gate["safety"]["canonical_learner_truth_written"] = True
    _write_json(paths["test_learner_sandbox_readback_gate"], gate)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("test_learner_sandbox_synthesis_observed_candidate_count" in blocker for blocker in report["blockers"])
    assert any("test_learner_sandbox_learner_memory_write_count" in blocker for blocker in report["blockers"])
    assert any("test_learner_sandbox_memory_write_allowed" in blocker for blocker in report["blockers"])
    assert any("test_learner_sandbox_canonical_learner_truth_written" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_authorized_writeback_preflight_execution(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    preflight = json.loads(paths["authorized_writeback_preflight"].read_text("utf-8"))
    preflight["authorization"]["test_learner_writeback_authorized"] = True
    preflight["authorization"]["allowed_write_scope"] = "test_learner"
    preflight["summary"]["writeback_executed"] = True
    preflight["summary"]["learner_memory_write_count"] = 1
    preflight["classification"]["test_learner_writeback_allowed"] = True
    _write_json(paths["authorized_writeback_preflight"], preflight)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("authorized_writeback_preflight_writeback_authorized" in blocker for blocker in report["blockers"])
    assert any("authorized_writeback_preflight_bad_allowed_scope" in blocker for blocker in report["blockers"])
    assert any("authorized_writeback_preflight_writeback_executed" in blocker for blocker in report["blockers"])
    assert any("authorized_writeback_preflight_learner_memory_write_count" in blocker for blocker in report["blockers"])
    assert any("authorized_writeback_preflight_writeback_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_authorization_package_write_authority_or_count_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    package = json.loads(paths["test_learner_writeback_authorization_package"].read_text("utf-8"))
    package["authorization_decision"]["user_authorization_recorded"] = True
    package["authorization_decision"]["test_learner_writeback_authorized"] = True
    package["authorization_decision"]["allowed_write_scope"] = "test_learner"
    package["candidate_scope"]["max_candidate_event_count"] = 99
    package["rollback_plan"]["plan_status"] = "approved"
    package["summary"]["writeback_executed"] = True
    package["summary"]["learner_memory_write_count"] = 1
    package["classification"]["test_learner_writeback_allowed"] = True
    _write_json(paths["test_learner_writeback_authorization_package"], package)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("test_learner_writeback_authorization_package_user_authorization_recorded" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_authorization_package_writeback_authorized" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_authorization_package_bad_allowed_scope" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_authorization_package_bad_rollback_status" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_authorization_package_writeback_executed" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_authorization_package_learner_memory_write_count" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_authorization_package_writeback_allowed" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_authorization_package_candidate_count_drift" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_dry_run_manifest_write_or_count_drift(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    manifest = json.loads(paths["test_learner_writeback_dry_run_manifest"].read_text("utf-8"))
    manifest["target_scope"]["target_user_id"] = "real_test_learner"
    manifest["write_batch_candidate"]["write_allowed"] = True
    manifest["write_batch_candidate"]["event_count"] = 99
    manifest["event_write_candidates"][0]["write_allowed"] = True
    manifest["summary"]["writeback_executed"] = True
    manifest["summary"]["learner_memory_write_count"] = 1
    manifest["classification"]["learner_memory_write_allowed"] = True
    _write_json(paths["test_learner_writeback_dry_run_manifest"], manifest)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("test_learner_writeback_dry_run_manifest_bound_target_user" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_dry_run_manifest_write_allowed" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_dry_run_manifest_event_count_drift" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_dry_run_manifest_event_write_allowed" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_dry_run_manifest_writeback_executed" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_dry_run_manifest_learner_memory_write_count" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_dry_run_manifest_authority_allowed:learner_memory_write_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_execution_gate_write_authority(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    gate = json.loads(paths["test_learner_writeback_execution_gate"].read_text("utf-8"))
    gate["verdict"] = "PASS"
    gate["execution_decision"]["writeback_allowed"] = True
    gate["execution_decision"]["writeback_executed"] = True
    gate["execution_decision"]["target_user_id_bound"] = True
    gate["summary"]["writeback_executed"] = True
    gate["summary"]["learner_memory_write_count"] = 1
    gate["classification"]["learner_memory_write_allowed"] = True
    _write_json(paths["test_learner_writeback_execution_gate"], gate)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert any("test_learner_writeback_execution_gate_bad_verdict" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_execution_gate_writeback_allowed" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_execution_gate_writeback_executed" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_execution_gate_target_user_bound" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_execution_gate_learner_memory_write_count" in blocker for blocker in report["blockers"])
    assert any("test_learner_writeback_execution_gate_authority_allowed:learner_memory_write_allowed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_current_standard_compat_audit_readback_claim(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    audit = json.loads(paths["learning_evidence_current_standard_compat_audit"].read_text("utf-8"))
    audit["classification"]["current_standard_readback_verified"] = True
    audit["summary"]["current_standard_readback_verified"] = True
    audit["summary"]["standard_accepted_source_feature_count"] = 1
    audit["candidate_event_compat_findings"][0]["current_standard_payload"] = True
    _write_json(paths["learning_evidence_current_standard_compat_audit"], audit)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "learning_evidence_current_standard_compat_audit_readback_claimed" in report["blockers"]
    assert "learning_evidence_current_standard_compat_audit_summary_readback_claimed" in report["blockers"]
    assert "learning_evidence_current_standard_compat_audit_standard_source_feature_claimed" in report["blockers"]
    assert any("learning_evidence_current_standard_compat_finding_claimed" in blocker for blocker in report["blockers"])


def test_interop_audit_blocks_external_source_closure_source_truth_or_question_support(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import audit_interop

    paths = _valid_artifacts(tmp_path)
    closure = json.loads(paths["external_source_closure"].read_text("utf-8"))
    closure["classification"]["source_truth_claimed"] = True
    closure["summary"]["source_truth_write_count"] = 1
    closure["external_source_closures"][0]["source_truth_claimed"] = True
    closure["external_source_closures"][0]["candidate_sources"] = [
        {
            "source_lane": "question",
            "source_path": "题库/case.md",
            "record_id": "Q-bad",
            "support_candidate": True,
            "candidate_only": True,
            "install_allowed": False,
            "runtime_install_allowed": False,
        }
    ]
    _write_json(paths["external_source_closure"], closure)

    report = audit_interop(**paths)

    assert report["verdict"] == "FAIL"
    assert "external_source_closure_authority_allowed:source_truth_claimed" in report["blockers"]
    assert "external_source_closure_source_truth_written" in report["blockers"]
    assert any("external_source_closure_bad_support_candidate" in blocker for blocker in report["blockers"])


def test_cli_writes_interop_audit_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_interop_audit import main

    paths = _valid_artifacts(tmp_path)
    output = tmp_path / "interop_audit.json"
    exit_code = main(
        [
            "--sample",
            str(paths["sample"]),
            "--skeleton",
            str(paths["skeleton"]),
            "--source-gap",
            str(paths["source_gap"]),
            "--patches",
            str(paths["patches"]),
            "--patch-audit",
            str(paths["patch_audit"]),
            "--rejected-feedback",
            str(paths["rejected_feedback"]),
            "--semantic-packets",
            str(paths["semantic_packets"]),
            "--source-evidence",
            str(paths["source_evidence"]),
            "--semantic-queue",
            str(paths["semantic_queue"]),
            "--semantic-record",
            str(paths["semantic_record"]),
            "--review-shards",
            str(paths["review_shards"]),
            "--review-suggestions",
            str(paths["review_suggestions"]),
            "--decision-validation",
            str(paths["decision_validation"]),
            "--reviewed-candidates",
            str(paths["reviewed_candidates"]),
            "--runtime-supply-candidate",
            str(paths["runtime_supply_candidate"]),
            "--runtime-supply-regression",
            str(paths["runtime_supply_regression"]),
            "--field-candidates",
            str(paths["field_candidates"]),
            "--artifact-candidates",
            str(paths["artifact_candidates"]),
            "--field-promotion-review",
            str(paths["field_promotion_review"]),
            "--context-pack-smoke",
            str(paths["context_pack_smoke"]),
            "--fail-open-guard-diagnostic",
            str(paths["fail_open_guard_diagnostic"]),
            "--context-pack-projection-ab",
            str(paths["context_pack_projection_ab"]),
            "--semantic-runtime-offline-ab",
            str(paths["semantic_runtime_offline_ab"]),
            "--semantic-runtime-nearline-ab",
            str(paths["semantic_runtime_nearline_ab"]),
            "--semantic-runtime-live-ab-preflight",
            str(paths["semantic_runtime_live_ab_preflight"]),
            "--semantic-runtime-near-live-smoke",
            str(paths["semantic_runtime_near_live_smoke"]),
            "--semantic-runtime-near-live-shadow-ab",
            str(paths["semantic_runtime_near_live_shadow_ab"]),
            "--shadow-residual-work-orders",
            str(paths["shadow_residual_work_orders"]),
            "--shadow-residual-review-packets",
            str(paths["shadow_residual_review_packets"]),
            "--shadow-residual-review-decision-validation",
            str(paths["shadow_residual_review_decision_validation"]),
            "--shadow-residual-review-decision-seed",
            str(paths["shadow_residual_review_decision_seed"]),
            "--shadow-residual-review-decisions",
            str(paths["shadow_residual_review_decisions"]),
            "--shadow-residual-audit-record",
            str(paths["shadow_residual_audit_record"]),
            "--shadow-residual-guard-patch-plan",
            str(paths["shadow_residual_guard_patch_plan"]),
            "--shadow-residual-guard-review-packets",
            str(paths["shadow_residual_guard_review_packets"]),
            "--shadow-residual-guard-review-decisions",
            str(paths["shadow_residual_guard_review_decisions"]),
            "--shadow-residual-guard-review-decision-validation",
            str(paths["shadow_residual_guard_review_decision_validation"]),
            "--shadow-residual-guard-audit-record",
            str(paths["shadow_residual_guard_audit_record"]),
            "--learning-evidence-candidate-bridge",
            str(paths["learning_evidence_candidate_bridge"]),
            "--pcp-nba-candidate-projection",
            str(paths["pcp_nba_candidate_projection"]),
            "--test-learner-sandbox-readback-gate",
            str(paths["test_learner_sandbox_readback_gate"]),
            "--authorized-writeback-preflight",
            str(paths["authorized_writeback_preflight"]),
            "--test-learner-writeback-authorization-package",
            str(paths["test_learner_writeback_authorization_package"]),
            "--test-learner-writeback-dry-run-manifest",
            str(paths["test_learner_writeback_dry_run_manifest"]),
            "--test-learner-writeback-execution-gate",
            str(paths["test_learner_writeback_execution_gate"]),
            "--learning-evidence-current-standard-compat-audit",
            str(paths["learning_evidence_current_standard_compat_audit"]),
            "--external-source-closure",
            str(paths["external_source_closure"]),
            "--weak",
            str(paths["weak"]),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text("utf-8"))
    assert report["verdict"] == "PASS"
