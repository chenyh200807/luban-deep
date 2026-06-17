from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO
    / "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608"
)

MASTER_PLAN = "docs/plan/总控入口与当前作战图/2026-06-04-luban-grading-engine-master-control-plan.md"
G1_M19C_GO = (
    "artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/"
    "go_no_go_m19c.json"
)
G1_M19D_VERDICT = (
    "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/"
    "release_verdict_m19d.json"
)
G1_ROLLBACK = (
    "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/"
    "rollback_readiness_drill_m19d.json"
)
G1_SAFETY = (
    "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/"
    "safety_invariants_m19d.json"
)
G2_G1_PREFLIGHT = (
    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/"
    "G1_LIMITED_DEFAULT_PREFLIGHT.json"
)
G2_M19D_SOAK_METRICS = (
    "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/"
    "soak_metrics_m19d.json"
)
G2_M19E_EVIDENCE_LEDGER = (
    "artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_20260605/"
    "m19c_m19d_evidence_ledger_m19e.json"
)
G3_SIGNER_REPORT = (
    "artifacts/luban_grading_artifacts/"
    "llm_artifact_compiler_continuous_factory_m20_20260604/"
    "deterministic_signer_report_m20.json"
)
G3_STAGED_SIGNATURE = (
    "artifacts/luban_grading_artifacts/"
    "delta_to_registry_candidate_staging_m202_20260605/"
    "staged_registry_signature_m202.json"
)
G3_RELEASE_DECISION_INPUT = (
    "artifacts/luban_grading_artifacts/"
    "delta_to_registry_candidate_staging_m202_20260605/"
    "release_decision_input_m202.json"
)
G3_STAGED_CANDIDATE = (
    "artifacts/luban_grading_artifacts/"
    "delta_to_registry_candidate_staging_m202_20260605/"
    "staged_registry_candidate_m202.json"
)
G4_TRUTH_WRITE_GUARD = (
    "artifacts/luban_grading_artifacts/"
    "learning_brain_real_retest_canonical_gate_m18d_20260604/"
    "learning_brain_truth_write_guard_m18d.json"
)
G4_DRYRUN_CANDIDATES = (
    "artifacts/luban_grading_artifacts/"
    "learning_brain_real_retest_canonical_gate_m18d_20260604/"
    "canonical_write_dryrun_candidates_m18d.jsonl"
)
G4_REAL_RETEST_PROOFS = (
    "artifacts/luban_grading_artifacts/"
    "learning_brain_real_retest_canonical_gate_m18d_20260604/"
    "real_retest_proofs_m18d.jsonl"
)
G4_M32_RETEST_OUTCOME = (
    "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/"
    "retest_outcome_proof_m32.jsonl"
)
G4_TEACHER_BRIDGE = (
    "artifacts/luban_grading_artifacts/"
    "learning_brain_canonical_claim_gate_m13e_20260604/"
    "teacher_review_to_claim_bridge_m13e.jsonl"
)
G5_M19E_MANIFEST = (
    "artifacts/luban_grading_artifacts/"
    "remote_deployment_authorization_package_m19e_20260605/"
    "remote_deployment_manifest_m19e.json"
)
G5_M19E_NO_REMOTE_WRITE = (
    "artifacts/luban_grading_artifacts/"
    "remote_deployment_authorization_package_m19e_20260605/"
    "no_remote_write_attestation_m19e.json"
)
G5_M19E_PROPOSED_COMMANDS = (
    "artifacts/luban_grading_artifacts/"
    "remote_deployment_authorization_package_m19e_20260605/"
    "proposed_remote_commands_m19e.md"
)
G5_M19E_ROLLBACK = (
    "artifacts/luban_grading_artifacts/"
    "remote_deployment_authorization_package_m19e_20260605/"
    "rollback_commands_m19e.md"
)
G5_M19E_R_READINESS = (
    "artifacts/luban_grading_artifacts/"
    "remote_deployment_authorization_package_m19e_r_20260605/"
    "m19c_m19d_readiness_rollup_m19e_r.json"
)
G5_M19E_R_NO_REMOTE_WRITE = (
    "artifacts/luban_grading_artifacts/"
    "remote_deployment_authorization_package_m19e_r_20260605/"
    "no_remote_write_attestation_m19e_r.json"
)
G6_DEVTOOLS_E2E_SCRIPT = "scripts/run_wechat_learning_brain_devtools_e2e.py"
G6_HOME_DASHBOARD_TEST = (
    "tests/services/member_console/test_home_dashboard_learning_projection.py"
)
G6_AGENTS_CONTRACT = "AGENTS.md"


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "S1",
        "title": "first_case_answer",
        "status": "done",
        "proves": "Runtime grading emits point-level grading truth and learning evidence drafts.",
        "evidence_refs": [
            "tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py",
            "artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/grading_packet_schema_m17a.json",
            "artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/learning_brain_event_drafts_m17a.jsonl",
        ],
    },
    {
        "id": "S2",
        "title": "near_synonym_exact_required",
        "status": "done",
        "proves": "Exact-required near synonyms remain grader misses unless teacher-final promotes them.",
        "evidence_refs": [
            "tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py",
            "tests/scripts/test_luban_v0_vs_v1_ab_benchmark_m24.py",
            "artifacts/luban_grading_artifacts/v0_vs_v1_ab_benchmark_m24_20260605/v0_vs_v1_quality_matrix.json",
        ],
    },
    {
        "id": "S3",
        "title": "calculation_question",
        "status": "done",
        "proves": "Non-textbook/calculation authority is separated from open prompt scoring.",
        "evidence_refs": [
            "tests/scripts/test_luban_calculation_validator_poc.py",
            "tests/scripts/test_luban_non_textbook_rubric_authority_factory_m10.py",
            "deeptutor/services/construction_grading/runtime_supply/v1_limited_default/machine_checkable_case_specs_m10.jsonl",
        ],
    },
    {
        "id": "S4",
        "title": "list_rule",
        "status": "done",
        "proves": "List-rule scoring uses structured specs and validator policy, not loose semantic equivalence.",
        "evidence_refs": [
            "tests/scripts/test_luban_485_list_rule_policy.py",
            "deeptutor/services/construction_grading/runtime_supply/v1_limited_default/list_rule_structured_specs_m10.jsonl",
            "tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py",
        ],
    },
    {
        "id": "S5",
        "title": "question_stem_fact",
        "status": "done",
        "proves": "Question-stem/source facts are compiled into source-backed artifacts before runtime grading.",
        "evidence_refs": [
            "tests/scripts/test_luban_full_case_stem_source_acquisition_m14b.py",
            "tests/services/construction_grading/test_full_knowledge_compiler_m30.py",
            "artifacts/luban_grading_artifacts/full_knowledge_compiler_release_candidate_m30_20260606/source_context_release_candidate_m30.json",
        ],
    },
    {
        "id": "S6",
        "title": "external_norm",
        "status": "partial",
        "proves": "External norms are rescued into work orders/candidates, but publication remains gated.",
        "evidence_refs": [
            "tests/scripts/test_luban_external_standard_source_rescue_m13c.py",
            "deeptutor/services/construction_grading/runtime_supply/v1_limited_default/external_source_work_orders_m10.jsonl",
            "artifacts/luban_grading_artifacts/full_knowledge_compiler_release_candidate_m30_20260606/raw_evidence_inventory_m30.json",
        ],
    },
    {
        "id": "S7",
        "title": "high_risk_review_queue",
        "status": "done",
        "proves": "High-risk grader output is routed to review and does not silently become learner mastery.",
        "evidence_refs": [
            "tests/services/construction_grading/test_teacher_review_writeback.py",
            "artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/runtime_safety_report_m17a.json",
            "artifacts/luban_grading_artifacts/teacher_review_ops_hardening_m13d_20260604/review_queue_consolidated_m13d.jsonl",
        ],
    },
    {
        "id": "S8",
        "title": "teacher_review",
        "status": "done",
        "proves": "Teacher override/reject/confirm is the promotion arm into learner-facing evidence.",
        "evidence_refs": [
            "tests/services/construction_grading/test_teacher_review_writeback.py",
            "tests/api/test_learning_brain_teacher_review_writeback.py",
            "artifacts/luban_grading_artifacts/learning_brain_canonical_claim_gate_m13e_20260604/teacher_review_to_claim_bridge_m13e.jsonl",
        ],
    },
    {
        "id": "S9",
        "title": "student_retest",
        "status": "done",
        "proves": "Real retest proof can update long-term learner claims through the canonical gate.",
        "evidence_refs": [
            "tests/scripts/test_luban_learning_brain_real_retest_canonical_gate_m18d.py",
            "tests/scripts/test_luban_m32_grading_to_brain_waterproof_slice.py",
            "artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/real_retest_proofs_m18d.jsonl",
            "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/retest_outcome_proof_m32.jsonl",
        ],
    },
    {
        "id": "S10",
        "title": "provider_fallback",
        "status": "done",
        "proves": "DeepSeek primary, Qwen fallback, validator downgrade, and fail-closed behavior are covered.",
        "evidence_refs": [
            "tests/scripts/test_luban_runtime_llm_ai_council_scaleout_m17b_m18.py",
            "tests/scripts/test_luban_rag_baseline_and_fallback_closure_m22r.py",
            "artifacts/luban_grading_artifacts/runtime_llm_ai_council_scaleout_m17b_m18_20260604/qwen_fallback_drill_results.jsonl",
            "artifacts/luban_grading_artifacts/rag_vs_luban_v1_benchmark_closure_m22r_20260605/qwen_fallback_results_m22r.jsonl",
        ],
    },
    {
        "id": "S11",
        "title": "artifact_version_update",
        "status": "partial",
        "proves": "Candidate, signed release, and staged registry are separate; published registry needs authorization.",
        "evidence_refs": [
            "tests/scripts/test_luban_llm_artifact_compiler_continuous_factory_m20.py",
            "tests/scripts/test_luban_delta_to_registry_candidate_staging_m202.py",
            "artifacts/luban_grading_artifacts/llm_artifact_compiler_continuous_factory_m20_20260604/deterministic_signer_report_m20.json",
            "artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/staged_registry_candidate_m202.json",
        ],
    },
    {
        "id": "S12",
        "title": "rollback",
        "status": "done",
        "proves": "Runtime/default rollback and fail-closed drills exist without production writes.",
        "evidence_refs": [
            "tests/scripts/test_luban_limited_default_flip_m19c.py",
            "tests/scripts/test_luban_limited_default_soak_monitoring_m19d.py",
            "artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/rollback_drill_transcript_m19c.md",
            "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/rollback_readiness_drill_m19d.json",
        ],
    },
]


AUTHORIZATION_GATES: dict[str, dict[str, Any]] = {
    "G1_limited_production_default": {
        "title": "qa_operator_limited_default_flip",
        "current_state": "candidate_ready_not_executed",
        "recommended_next": True,
        "required_authorization": "explicit_user_authorization_for_limited_default",
        "allowed_scope_after_authorization": "qa_/operator_ cohort only",
        "promotion_path": "runtime_default_only_no_mastery_write",
        "without_authorization": "decision_package_only",
        "flip_mechanism": "env-gated limited default; keep broad default off",
        "rollback": "env kill switch / cohort rollback",
        "stop_conditions": [
            "false_positive > 0",
            "source_mismatch > 0",
            "fallback failclosed spike",
            "latency/cost crosses operator threshold",
        ],
        "evidence_refs": [
            "artifacts/luban_grading_artifacts/limited_default_flip_m19c_20260605/go_no_go_m19c.json",
            "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/release_verdict_m19d.json",
            "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/rollback_readiness_drill_m19d.json",
        ],
    },
    "G2_broad_production_default": {
        "title": "broad_default_flip",
        "current_state": "not_recommended",
        "recommended_next": False,
        "required_authorization": "separate_broad_default_authorization_after_limited_soak",
        "allowed_scope_after_authorization": "explicitly named cohort expansion only",
        "promotion_path": "runtime_default_only_no_mastery_write",
        "without_authorization": "decision_package_only",
        "flip_mechanism": "progressive cohort expansion after G1 evidence review",
        "rollback": "same kill switch plus registry/runtime pointer rollback",
        "stop_conditions": [
            "limited default evidence stale",
            "teacher review backlog exceeds operator capacity",
            "unsupported claim/generic fallback drift",
        ],
        "evidence_refs": [
            "artifacts/luban_grading_artifacts/limited_default_soak_monitoring_m19d_20260605/soak_metrics_m19d.json",
            "artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_20260605/m19c_m19d_evidence_ledger_m19e.json",
            MASTER_PLAN,
        ],
    },
    "G3_published_registry": {
        "title": "published_registry_promotion",
        "current_state": "staged_candidate_only",
        "recommended_next": False,
        "required_authorization": "explicit_registry_publish_authorization",
        "allowed_scope_after_authorization": "promote signed candidate to published registry",
        "promotion_path": "candidate_to_signed_to_published_registry",
        "without_authorization": "decision_package_only",
        "flip_mechanism": "publish only a signed hash/version bundle; never edit in place",
        "rollback": "version/hash supersession pointer rollback",
        "stop_conditions": [
            "missing deterministic signer report",
            "hash/schema mismatch",
            "runtime resolver cannot prove previous version rollback",
        ],
        "evidence_refs": [
            "artifacts/luban_grading_artifacts/llm_artifact_compiler_continuous_factory_m20_20260604/deterministic_signer_report_m20.json",
            "artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/staged_registry_signature_m202.json",
            "artifacts/luban_grading_artifacts/delta_to_registry_candidate_staging_m202_20260605/release_decision_input_m202.json",
        ],
    },
    "G4_canonical_learner_truth_write": {
        "title": "canonical_learner_truth_write",
        "current_state": "dryrun_candidate_only",
        "recommended_next": False,
        "required_authorization": "explicit_canonical_learner_truth_write_authorization",
        "allowed_scope_after_authorization": "teacher-final plus real retest promotion only",
        "promotion_path": "teacher_final_plus_real_retest_only",
        "without_authorization": "decision_package_only",
        "flip_mechanism": "append-only Learning Evidence Ledger write through learner authority",
        "rollback": "append compensating review/retest event; never rewrite history",
        "stop_conditions": [
            "shadow/candidate/simulated evidence attempts mastery promotion",
            "high-risk item lacks teacher-final",
            "real retest proof missing or stale",
        ],
        "evidence_refs": [
            "artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/learning_brain_truth_write_guard_m18d.json",
            "artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/canonical_write_dryrun_candidates_m18d.jsonl",
            "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/retest_outcome_proof_m32.jsonl",
            "tests/services/construction_grading/test_teacher_review_writeback.py",
        ],
    },
    "G5_remote_or_db_write": {
        "title": "remote_or_db_write",
        "current_state": "not_executed",
        "recommended_next": False,
        "required_authorization": "explicit_remote_or_db_write_authorization",
        "allowed_scope_after_authorization": "Aliyun writes only under /root/deeptutor; DB writes only named learner/grading tables",
        "promotion_path": "authorized_deploy_or_db_migration_only",
        "without_authorization": "decision_package_only",
        "flip_mechanism": "run deployment/write plan with exact target path and rollback command",
        "rollback": "predeclared rollback commands and DB compensation plan",
        "stop_conditions": [
            "target path outside /root/deeptutor",
            "secret/raw env dump required",
            "write target not named before execution",
        ],
        "evidence_refs": [
            "AGENTS.md",
            "artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_20260605/rollback_commands_m19e.md",
            "artifacts/luban_grading_artifacts/remote_deployment_authorization_package_m19e_r_20260605/m19c_m19d_readiness_rollup_m19e_r.json",
        ],
    },
    "G6_real_wechat_package_page_automation": {
        "title": "real_wechat_package_page_automation",
        "current_state": "verification_required",
        "recommended_next": False,
        "required_authorization": "devtools_or_manual_wechat_qa_window",
        "allowed_scope_after_authorization": "open yousenwebview project root and drive packageDeeptutor page flow",
        "promotion_path": "verification_evidence_only_no_mastery_write",
        "without_authorization": "decision_package_only",
        "flip_mechanism": "DevTools CLI auto or miniprogram automator against project root",
        "rollback": "not applicable; verification gate does not write product state",
        "stop_conditions": [
            "only /wechat-harness evidence is available",
            "project root is packageDeeptutor instead of yousenwebview",
            "login state is unknown but reported as pass",
        ],
        "evidence_refs": [
            "AGENTS.md",
            "scripts/run_wechat_learning_brain_devtools_e2e.py",
            "tests/services/member_console/test_home_dashboard_learning_projection.py",
        ],
    },
}


COMPLETION_REQUIREMENTS: list[dict[str, Any]] = [
    {
        "id": "R1",
        "title": "runtime_grading_point_level_result",
        "status": "done",
        "authority": "grading truth/artifact authority",
        "required_fields": [
            "point_id",
            "knowledge_point",
            "policy_type",
            "hit",
            "score",
            "max_score",
            "mistake_type",
            "evidence_span",
            "required_term",
            "high_risk_review",
        ],
        "evidence_refs": [
            "tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py",
            "tests/services/construction_grading/test_m32_grading_event_learning_evidence.py",
            "artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/grading_packet_schema_m17a.json",
            "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/grading_event_ledger_m32.jsonl",
        ],
    },
    {
        "id": "R2",
        "title": "grading_result_to_standard_learning_evidence_event",
        "status": "done",
        "authority": "Learning Evidence Ledger",
        "evidence_refs": [
            "tests/services/construction_grading/test_learning_evidence_payload.py",
            "tests/services/construction_grading/test_m32_grading_event_learning_evidence.py",
            "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/learning_evidence_ledger_m32.jsonl",
            "artifacts/luban_grading_artifacts/runtime_llm_adjudicator_m17a_20260604/learning_brain_event_drafts_m17a.jsonl",
        ],
    },
    {
        "id": "R3",
        "title": "learning_evidence_to_learner_claim_profile",
        "status": "done",
        "authority": "Learner Model synthesis",
        "evidence_refs": [
            "tests/services/learner_state/test_m32_waterproof_learning_synthesis.py",
            "tests/services/construction_grading/test_learning_brain_synthesis.py",
            "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/learner_claim_projection_m32.jsonl",
            "artifacts/luban_grading_artifacts/learning_brain_canonical_claim_gate_m13e_20260604/claim_gate_decision_matrix_m13e.json",
        ],
    },
    {
        "id": "R4",
        "title": "pcp_feedback_to_tone_diagnosis_next_action_retest",
        "status": "done",
        "authority": "PersonalizationContextPack read model",
        "pcp_role": "read_only_feedback_to_grading",
        "evidence_refs": [
            "tests/services/learner_state/test_personalization_context.py",
            "tests/services/learner_state/test_m32_waterproof_personalization_context.py",
            "tests/services/learner_state/test_m32_waterproof_next_best_action.py",
            "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/personalization_context_pack_m32.json",
            "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/next_best_action_m32.json",
        ],
    },
    {
        "id": "R5",
        "title": "teacher_final_override_reject_confirm_promotion_arm",
        "status": "done",
        "authority": "teacher-final review writeback",
        "promotion_path": "teacher_final_only",
        "evidence_refs": [
            "tests/services/construction_grading/test_teacher_review_writeback.py",
            "tests/api/test_learning_brain_teacher_review_writeback.py",
            "artifacts/luban_grading_artifacts/learning_brain_canonical_claim_gate_m13e_20260604/teacher_review_to_claim_bridge_m13e.jsonl",
            "artifacts/luban_grading_artifacts/teacher_review_ops_hardening_m13d_20260604/teacher_action_dryrun_m13d.jsonl",
        ],
    },
    {
        "id": "R6",
        "title": "real_retest_improvement_updates_profile",
        "status": "authorization_gated",
        "authority": "real retest proof plus learner claim gate",
        "promotion_path": "real_retest_only",
        "gate": "canonical_learner_truth_write",
        "reason": "real retest proof and dry-run promotion exist; production canonical learner-truth write still requires explicit authorization",
        "evidence_refs": [
            "tests/scripts/test_luban_learning_brain_real_retest_canonical_gate_m18d.py",
            "tests/services/learner_state/test_m32_waterproof_retest_outcome.py",
            "artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/real_retest_proofs_m18d.jsonl",
            "artifacts/luban_grading_artifacts/learning_brain_real_retest_canonical_gate_m18d_20260604/canonical_write_dryrun_candidates_m18d.jsonl",
            "artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/retest_outcome_proof_m32.jsonl",
        ],
    },
    {
        "id": "R7",
        "title": "learning_surfaces_use_same_learning_brain_authority",
        "status": "done",
        "authority": "Learning Brain read model",
        "empty_spin_prevented": True,
        "evidence_refs": [
            "tests/services/member_console/test_home_dashboard_learning_projection.py",
            "tests/services/learner_state/test_scoring_point_map_read_model.py",
            "tests/services/learner_state/test_learning_report_read_model.py",
            "deeptutor/services/learner_state/learning_report_read_model.py",
            "deeptutor/services/learner_state/scoring_point_map_read_model.py",
            "deeptutor/services/taxonomy/textbook_directory.py",
        ],
    },
]


def _rel_exists(path: str) -> bool:
    return (REPO / path).exists()


def _read_json_rel(path: str) -> dict[str, Any]:
    full_path = REPO / path
    if not full_path.exists():
        return {}
    return json.loads(full_path.read_text(encoding="utf-8"))


def _read_json_path(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl_rel(path: str) -> list[dict[str, Any]]:
    full_path = REPO / path
    if not full_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in full_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _current_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO,
        text=True,
    ).strip()


def _with_evidence_health(row: dict[str, Any]) -> dict[str, Any]:
    missing = [ref for ref in row["evidence_refs"] if not _rel_exists(ref)]
    return {
        **row,
        "evidence_ok": not missing,
        "missing_evidence_refs": missing,
    }


def build_matrix() -> dict[str, Any]:
    scenarios = [_with_evidence_health(row) for row in SCENARIOS]
    missing = {
        row["id"]: row["missing_evidence_refs"]
        for row in scenarios
        if row["missing_evidence_refs"]
    }

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "scope": "read_only_current_gap_audit",
        "quality_gates": {
            "fp": 0,
            "bad_certified": 0,
            "source_mismatch": 0,
            "legacy_equal": 1.0,
            "production_write": 0,
        },
        "single_authority": {
            "grading_truth_authority": (
                "signed grading artifacts + runtime packet builder + LLM adjudicator "
                "+ deterministic validator/gate"
            ),
            "learner_truth_authority": (
                "learning evidence ledger + teacher-final/real-retest promotion "
                "+ learner model synthesis + PersonalizationContextPack"
            ),
            "no_second_learner_memory": True,
            "shadow_candidate_never_mastery": True,
            "pcp_is_read_only_feedback": True,
        },
        "provider_and_gate_chain": {
            "primary_llm": "DeepSeek",
            "high_risk_fallback": "Qwen/council fallback plus validator fail-closed",
            "review_queue_required_for_high_risk": True,
            "teacher_final_required_for_mastery_promotion": True,
        },
        "artifact_layers": {
            "candidate": "compiler output / delta candidate",
            "signed_release": "deterministic signer report and hash/version bundle",
            "published_registry": "not advanced by this audit without authorization",
            "rollback": "limited default and soak rollback drills",
        },
        "remaining_gates": {
            "production_default": "gated_authorization_required",
            "canonical_learner_truth_write": "gated_authorization_required",
            "published_registry": "gated_authorization_required",
            "remote_or_db_write": "gated_authorization_required",
            "real_wechat_package_page_automation": "not_touched_by_this_read_only_audit",
        },
        "scenarios": scenarios,
        "missing_evidence": missing,
        "summary": {
            "done": sum(1 for row in scenarios if row["status"] == "done"),
            "partial": sum(1 for row in scenarios if row["status"] == "partial"),
            "blocker": sum(1 for row in scenarios if row["status"] == "blocker"),
            "evidence_missing_count": sum(
                len(row["missing_evidence_refs"]) for row in scenarios
            ),
        },
    }


def build_authorization_package() -> dict[str, Any]:
    gates: dict[str, dict[str, Any]] = {}
    for gate_id, gate in AUTHORIZATION_GATES.items():
        missing = [ref for ref in gate["evidence_refs"] if not _rel_exists(ref)]
        gates[gate_id] = {
            **gate,
            "evidence_ok": not missing,
            "missing_evidence_refs": missing,
        }

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "scope": "read_only_authorization_decision_package",
        "production_write_count": 0,
        "canonical_truth_written": False,
        "remote_write_count": 0,
        "published_registry_executed": False,
        "single_authority": {
            "no_second_grading_truth": True,
            "no_second_learner_truth": True,
            "grading_truth_source": "signed artifacts + runtime adjudicator + validator",
            "learner_truth_source": "Learning Evidence Ledger + Learner Model",
            "pcp_role": "read_only_feedback_context",
        },
        "execution_order": [
            "G1_limited_production_default",
            "G6_real_wechat_package_page_automation",
            "G3_published_registry",
            "G4_canonical_learner_truth_write",
            "G2_broad_production_default",
            "G5_remote_or_db_write",
        ],
        "gates": gates,
        "missing_evidence": {
            gate_id: gate["missing_evidence_refs"]
            for gate_id, gate in gates.items()
            if gate["missing_evidence_refs"]
        },
    }


def build_g1_limited_default_preflight() -> dict[str, Any]:
    m19c = _read_json_rel(G1_M19C_GO)
    m19d = _read_json_rel(G1_M19D_VERDICT)
    rollback = _read_json_rel(G1_ROLLBACK)
    safety = _read_json_rel(G1_SAFETY)

    evidence_ok = {
        G1_M19C_GO: bool(m19c),
        G1_M19D_VERDICT: bool(m19d),
        G1_ROLLBACK: bool(rollback),
        G1_SAFETY: bool(safety),
    }
    preconditions = {
        "m19c_limited_default_flip": m19c.get("m19c_limited_default_flip"),
        "m19d_soak_verdict": m19d.get("m19d_soak_verdict"),
        "rollback_readiness": rollback.get("all_pass") is True,
        "safety_invariants": safety.get("all_pass") is True,
        "rollback_works": safety.get("rollback_works") is True,
        "broad_default": m19d.get("broad_default") or m19c.get("production_default_broad"),
        "canonical_learner_truth_write": "NO-GO"
        if (
            m19c.get("canonical_truth_written") is False
            and m19d.get("canonical_truth_written") is False
            and safety.get("canonical_truth_written") is False
        )
        else "UNKNOWN",
    }
    no_write = {
        "production_write_count": max(
            int(m19c.get("production_write_count", 999)),
            int(m19d.get("production_write_count", 999)),
            int(safety.get("production_write_count", 999)),
        ),
        "canonical_truth_written": any(
            value is True
            for value in (
                m19c.get("canonical_truth_written"),
                m19d.get("canonical_truth_written"),
                safety.get("canonical_truth_written"),
            )
        ),
        "remote_write_count": 0 if m19c.get("remote_deployment_written") is False else 1,
        "published_registry_executed": m19c.get("formal_registry_emitted") is True,
    }
    ready = (
        all(evidence_ok.values())
        and preconditions["m19c_limited_default_flip"] == "GO"
        and preconditions["m19d_soak_verdict"] == "GO"
        and preconditions["rollback_readiness"] is True
        and preconditions["safety_invariants"] is True
        and preconditions["rollback_works"] is True
        and preconditions["broad_default"] == "NO-GO"
        and preconditions["canonical_learner_truth_write"] == "NO-GO"
        and no_write["production_write_count"] == 0
        and no_write["canonical_truth_written"] is False
        and no_write["remote_write_count"] == 0
        and no_write["published_registry_executed"] is False
    )

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "gate_id": "G1_limited_production_default",
        "scope": "read_only_pre_authorization_preflight",
        "verdict": "ready_for_user_authorization" if ready else "not_ready",
        "execution_mode": "read_only_no_flip",
        "without_authorization": "decision_package_only",
        "required_authorization": "explicit_user_authorization_for_limited_default",
        "allowed_scope_after_authorization": "qa_/operator_ cohort only",
        "promotion_path": "runtime_default_only_no_mastery_write",
        "preconditions": preconditions,
        "evidence_ok": evidence_ok,
        "missing_evidence_refs": [
            path for path, exists in evidence_ok.items() if not exists
        ],
        "single_authority": {
            "no_second_grading_truth": True,
            "no_second_learner_truth": True,
            "grading_truth_source": "existing limited-default runtime gate evidence",
            "learner_truth_source": "unchanged Learning Evidence Ledger / Learner Model",
            "pcp_role": "read_only_feedback_context",
        },
        **no_write,
        "stop_conditions": [
            "false_positive > 0",
            "bad_certified > 0",
            "source_mismatch > 0",
            "legacy_equal < 1.0",
            "teacher review backlog exceeds operator capacity",
            "any canonical learner truth write is requested by this gate",
        ],
        "evidence_refs": [
            G1_M19C_GO,
            G1_M19D_VERDICT,
            G1_ROLLBACK,
            G1_SAFETY,
        ],
    }


def build_g2_broad_default_preflight(
    g1_preflight: dict[str, Any],
) -> dict[str, Any]:
    m19c = _read_json_rel(G1_M19C_GO)
    m19d = _read_json_rel(G1_M19D_VERDICT)
    soak_metrics = _read_json_rel(G2_M19D_SOAK_METRICS)
    m19e_ledger = _read_json_rel(G2_M19E_EVIDENCE_LEDGER)

    evidence_ok = {
        G2_G1_PREFLIGHT: g1_preflight.get("verdict")
        == "ready_for_user_authorization",
        G1_M19C_GO: bool(m19c),
        G1_M19D_VERDICT: bool(m19d),
        G2_M19D_SOAK_METRICS: bool(soak_metrics),
        G2_M19E_EVIDENCE_LEDGER: bool(m19e_ledger),
    }
    preconditions = {
        "g1_ready_for_authorization": g1_preflight.get("verdict")
        == "ready_for_user_authorization",
        "limited_default_executed_by_this_package": False,
        "limited_default_current_state": m19c.get("limited_default_current_state"),
        "m19d_soak_verdict": m19d.get("m19d_soak_verdict"),
        "m19d_broad_default": m19d.get("broad_default"),
        "m19c_production_default_broad": m19c.get("production_default_broad"),
        "m19c_production_v1_broad_default": m19c.get(
            "production_v1_broad_default"
        ),
        "soak_false_positive_count": int(
            soak_metrics.get("false_positive_count", 999)
        ),
        "soak_source_mismatch_count": int(
            soak_metrics.get("source_mismatch_count", 999)
        ),
        "soak_bad_certified_count": int(
            soak_metrics.get("bad_certified_count", 999)
        ),
        "m19e_broad_default_remains_no_go": (
            "broad default and canonical learner truth write remain NO-GO"
            in str(m19e_ledger.get("canonical_statement", ""))
        ),
    }
    no_write = {
        "production_write_count": max(
            int(m19c.get("production_write_count", 999)),
            int(m19d.get("production_write_count", 999)),
            int(soak_metrics.get("production_write_count", 999)),
            int(m19e_ledger.get("m19c", {}).get("production_write_count", 999)),
            int(m19e_ledger.get("m19d", {}).get("production_write_count", 999)),
        ),
        "canonical_truth_written": any(
            value is True
            for value in (
                m19c.get("canonical_truth_written"),
                m19d.get("canonical_truth_written"),
                soak_metrics.get("canonical_truth_written"),
                m19e_ledger.get("m19c", {}).get("canonical_truth_written"),
                m19e_ledger.get("m19d", {}).get("canonical_truth_written"),
            )
        ),
        "remote_write_count": 0
        if m19c.get("remote_deployment_written") is False
        and m19e_ledger.get("m19c", {}).get("remote_deployment_written") is False
        else 1,
        "published_registry_executed": m19c.get("formal_registry_emitted") is True,
    }
    ready_for_broad_authorization = (
        all(evidence_ok.values())
        and preconditions["limited_default_executed_by_this_package"] is True
        and preconditions["m19d_broad_default"] == "GO"
        and preconditions["m19c_production_default_broad"] == "GO"
        and preconditions["m19c_production_v1_broad_default"] == "GO"
        and preconditions["soak_false_positive_count"] == 0
        and preconditions["soak_source_mismatch_count"] == 0
        and preconditions["soak_bad_certified_count"] == 0
        and no_write["production_write_count"] == 0
        and no_write["canonical_truth_written"] is False
        and no_write["remote_write_count"] == 0
        and no_write["published_registry_executed"] is False
    )
    blocking_reason = ""
    if preconditions["limited_default_executed_by_this_package"] is False:
        blocking_reason = (
            "G1 limited default must be explicitly authorized/executed and reviewed before broad default"
        )
    elif not ready_for_broad_authorization:
        blocking_reason = "broad default preconditions are not satisfied"

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "gate_id": "G2_broad_production_default",
        "scope": "read_only_pre_authorization_preflight",
        "verdict": "ready_for_user_authorization"
        if ready_for_broad_authorization
        else "not_ready_limited_default_not_executed",
        "blocking_reason": blocking_reason,
        "execution_mode": "read_only_no_broad_flip",
        "without_authorization": "decision_package_only",
        "required_authorization": (
            "separate_broad_default_authorization_after_limited_soak"
        ),
        "allowed_scope_after_authorization": (
            "explicitly named cohort expansion only"
        ),
        "promotion_path": "runtime_default_only_no_mastery_write",
        "preconditions": preconditions,
        "evidence_ok": evidence_ok,
        "missing_evidence_refs": [
            path for path, exists in evidence_ok.items() if not exists
        ],
        "single_authority": {
            "no_second_grading_truth": True,
            "no_second_learner_truth": True,
            "grading_truth_source": (
                "authorized limited-default runtime evidence before any broad flip"
            ),
            "learner_truth_source": (
                "unchanged Learning Evidence Ledger / Learner Model"
            ),
            "pcp_role": "read_only_feedback_context",
        },
        **no_write,
        "stop_conditions": [
            "G1 limited default not explicitly authorized/executed/reviewed",
            "false_positive > 0",
            "bad_certified > 0",
            "source_mismatch > 0",
            "teacher review backlog exceeds operator capacity",
            "unsupported claim or generic fallback drift appears",
            "any canonical learner truth write is requested by this gate",
        ],
        "evidence_refs": [
            G2_G1_PREFLIGHT,
            G1_M19C_GO,
            G1_M19D_VERDICT,
            G2_M19D_SOAK_METRICS,
            G2_M19E_EVIDENCE_LEDGER,
        ],
    }


def build_g3_published_registry_preflight() -> dict[str, Any]:
    signer = _read_json_rel(G3_SIGNER_REPORT)
    signature = _read_json_rel(G3_STAGED_SIGNATURE)
    decision = _read_json_rel(G3_RELEASE_DECISION_INPUT)
    candidate = _read_json_rel(G3_STAGED_CANDIDATE)
    entries = candidate.get("entries") or []

    evidence_ok = {
        G3_SIGNER_REPORT: bool(signer),
        G3_STAGED_SIGNATURE: bool(signature),
        G3_RELEASE_DECISION_INPUT: bool(decision),
        G3_STAGED_CANDIDATE: bool(candidate),
    }
    candidate_entries_count = len(entries)
    candidate_entries_published_count = sum(
        1 for row in entries if row.get("published") is True
    )
    candidate_hash_consistent = (
        bool(candidate.get("candidate_hash"))
        and candidate.get("candidate_hash") == signature.get("candidate_hash")
        and candidate.get("candidate_hash") == decision.get("candidate_hash")
    )
    delta_hash_consistent = (
        bool(signer.get("hash_version", {}).get("registry_hash"))
        and signer.get("hash_version", {}).get("registry_hash")
        == signature.get("delta_hash")
        and signature.get("delta_hash") == decision.get("delta_hash")
        and decision.get("delta_hash") == candidate.get("delta_hash")
    )
    preconditions = {
        "deterministic_signer_pass": signer.get("schema_validation_pass") is True
        and signer.get("source_boundary_validation_pass") is True
        and signer.get("release_candidate_delta_signed") is True,
        "staged_candidate_generated": candidate.get("artifact_kind")
        == "staged_registry_candidate",
        "staged_signature_signed": signature.get("signed") is True
        and signature.get("signed_status") == "staged_release_candidate",
        "execute_release_decision": decision.get("execute_release_decision") is True,
        "published_registry_emitted": decision.get("no_runtime_impact", {}).get(
            "published_registry_emitted"
        )
        is True,
        "candidate_hash_consistent": candidate_hash_consistent,
        "delta_hash_consistent": delta_hash_consistent,
        "candidate_entries_count": candidate_entries_count,
        "candidate_entries_published_count": candidate_entries_published_count,
        "deterministic_validation_all_pass": decision.get(
            "deterministic_validation_all_pass"
        )
        is True,
        "runtime_default_changed": decision.get("no_runtime_impact", {}).get(
            "production_default_changed"
        )
        is True,
    }
    no_write = {
        "production_write_count": int(signer.get("production_write_count", 999)),
        "canonical_truth_written": signer.get("canonical_learner_truth_written")
        is True
        or decision.get("lb_claim_mapping_delta", {}).get("canonical_truth_written")
        is True,
        "remote_write_count": 0,
        "published_registry_executed": signature.get("published") is True
        or decision.get("execute_release_decision") is True
        or decision.get("no_runtime_impact", {}).get("published_registry_emitted")
        is True,
    }
    ready_for_publish_authorization = (
        all(evidence_ok.values())
        and preconditions["deterministic_signer_pass"] is True
        and preconditions["staged_candidate_generated"] is True
        and preconditions["staged_signature_signed"] is True
        and preconditions["execute_release_decision"] is False
        and preconditions["published_registry_emitted"] is False
        and preconditions["candidate_hash_consistent"] is True
        and preconditions["delta_hash_consistent"] is True
        and candidate_entries_count > 0
        and candidate_entries_published_count == 0
        and preconditions["deterministic_validation_all_pass"] is True
        and decision.get("no_runtime_impact", {}).get("production_default_changed")
        is False
        and no_write["production_write_count"] == 0
        and no_write["canonical_truth_written"] is False
        and no_write["published_registry_executed"] is False
    )

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "gate_id": "G3_published_registry",
        "scope": "read_only_pre_authorization_preflight",
        "verdict": "ready_for_user_authorization"
        if ready_for_publish_authorization
        else "not_ready",
        "execution_mode": "read_only_no_publish",
        "without_authorization": "decision_package_only",
        "required_authorization": "explicit_registry_publish_authorization",
        "allowed_scope_after_authorization": (
            "promote signed staged candidate to published registry"
        ),
        "promotion_path": "candidate_to_signed_to_published_registry",
        "artifact_layers": {
            "candidate": candidate.get("artifact_kind") or "missing",
            "signed_release": signature.get("signed_status") or "missing",
            "published_registry": "not_published"
            if no_write["published_registry_executed"] is False
            else "published",
        },
        "preconditions": preconditions,
        "evidence_ok": evidence_ok,
        "missing_evidence_refs": [
            path for path, exists in evidence_ok.items() if not exists
        ],
        "single_authority": {
            "no_second_grading_truth": True,
            "no_second_learner_truth": True,
            "registry_truth_source": (
                "signed release artifact plus explicit publish gate only"
            ),
            "runtime_consumption": "manifest/hash/pointer only; never scan artifacts",
        },
        **no_write,
        "stop_conditions": [
            "hash or signature mismatch",
            "published registry emitted before explicit authorization",
            "production default changed by registry staging",
            "candidate entry has published=true before publish gate",
            "runtime resolver cannot prove rollback pointer",
        ],
        "evidence_refs": [
            G3_SIGNER_REPORT,
            G3_STAGED_SIGNATURE,
            G3_RELEASE_DECISION_INPUT,
            G3_STAGED_CANDIDATE,
        ],
    }


def build_g4_canonical_learner_truth_preflight() -> dict[str, Any]:
    guard = _read_json_rel(G4_TRUTH_WRITE_GUARD)
    dryrun_candidates = _read_jsonl_rel(G4_DRYRUN_CANDIDATES)
    real_retest_proofs = _read_jsonl_rel(G4_REAL_RETEST_PROOFS)
    m32_retest_outcomes = _read_jsonl_rel(G4_M32_RETEST_OUTCOME)
    teacher_bridge = _read_jsonl_rel(G4_TEACHER_BRIDGE)

    evidence_ok = {
        G4_TRUTH_WRITE_GUARD: bool(guard),
        G4_DRYRUN_CANDIDATES: bool(dryrun_candidates),
        G4_REAL_RETEST_PROOFS: bool(real_retest_proofs),
        G4_M32_RETEST_OUTCOME: bool(m32_retest_outcomes),
        G4_TEACHER_BRIDGE: bool(teacher_bridge),
    }
    real_retest_valid_count = sum(
        1
        for row in real_retest_proofs
        if row.get("proof_valid") is True
        and row.get("is_real_ws_proof") is True
        and row.get("is_simulation") is False
    )
    dryrun_candidate_count = sum(
        1
        for row in dryrun_candidates
        if row.get("disposition") == "canonical_write_dryrun_candidate"
        and row.get("canonical_truth_written") is False
        and row.get("production_write_performed") is False
        and row.get("promoted_to_canonical_mastery") is False
    )
    teacher_final_live_count = sum(
        1
        for row in teacher_bridge
        if row.get("canonical_write_allowed_now") is True
        and row.get("qa_simulated") is False
    ) + sum(1 for row in dryrun_candidates if row.get("teacher_reviewed") is True)
    teacher_final_simulated_count = sum(
        1 for row in teacher_bridge if row.get("qa_simulated") is True
    )
    requires_real_teacher_signoff_count = sum(
        1 for row in teacher_bridge if row.get("requires_real_teacher_signoff") is True
    )
    m32_counted_improvement_count = sum(
        1
        for row in m32_retest_outcomes
        if row.get("counted_as_improvement") is True and row.get("simulated") is False
    )
    shadow_or_simulated_promotion_attempted = any(
        row.get("promoted_to_canonical_mastery") is True
        or row.get("canonical_truth_written") is True
        or row.get("production_write_performed") is True
        for row in dryrun_candidates
    ) or any(
        row.get("counted_as_improvement") is True
        for row in m32_retest_outcomes
        if row.get("authority") in {"candidate_preview", "simulated"}
    )

    preconditions = {
        "truth_write_guard_present": bool(guard),
        "real_retest_valid_count": real_retest_valid_count,
        "dryrun_candidate_count": dryrun_candidate_count,
        "teacher_final_live_count": teacher_final_live_count,
        "teacher_final_simulated_count": teacher_final_simulated_count,
        "requires_real_teacher_signoff_count": requires_real_teacher_signoff_count,
        "m32_counted_improvement_count": m32_counted_improvement_count,
        "shadow_or_simulated_promotion_attempted": (
            shadow_or_simulated_promotion_attempted
        ),
        "pcp_unique_contract": guard.get("personalization_context_pack_unique_contract")
        is True,
        "second_memory_authority": guard.get("second_memory_authority") is True,
        "second_personalization_authority": (
            guard.get("second_personalization_authority") is True
        ),
    }
    no_write = {
        "production_write_count": int(guard.get("production_write_count", 999)),
        "canonical_truth_written": guard.get("canonical_truth_written") is True
        or guard.get("any_canonical_write") is True,
        "remote_write_count": 0,
        "published_registry_executed": False,
    }
    ready_for_write_authorization = (
        all(evidence_ok.values())
        and real_retest_valid_count > 0
        and dryrun_candidate_count > 0
        and teacher_final_live_count > 0
        and preconditions["pcp_unique_contract"] is True
        and preconditions["second_memory_authority"] is False
        and preconditions["second_personalization_authority"] is False
        and shadow_or_simulated_promotion_attempted is False
        and no_write["production_write_count"] == 0
        and no_write["canonical_truth_written"] is False
    )
    blocking_reason = ""
    if teacher_final_live_count == 0:
        blocking_reason = (
            "teacher-final live signoff is required before canonical learner truth write"
        )
    elif not ready_for_write_authorization:
        blocking_reason = "canonical learner truth write preconditions are not satisfied"

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "gate_id": "G4_canonical_learner_truth_write",
        "scope": "read_only_pre_authorization_preflight",
        "verdict": "ready_for_user_authorization"
        if ready_for_write_authorization
        else "not_ready_teacher_final_required",
        "blocking_reason": blocking_reason,
        "execution_mode": "read_only_no_write",
        "without_authorization": "decision_package_only",
        "required_authorization": (
            "explicit_canonical_learner_truth_write_authorization"
        ),
        "allowed_scope_after_authorization": (
            "teacher-final plus real retest promotion only"
        ),
        "promotion_path": "teacher_final_plus_real_retest_only",
        "preconditions": preconditions,
        "evidence_ok": evidence_ok,
        "missing_evidence_refs": [
            path for path, exists in evidence_ok.items() if not exists
        ],
        "single_authority": {
            "no_second_grading_truth": True,
            "no_second_learner_truth": True,
            "learner_truth_source": "Learning Evidence Ledger / Learner Model only",
            "write_authority": "LearnerStateService writeback pipeline only",
            "pcp_role": "read_only_feedback_context",
        },
        **no_write,
        "stop_conditions": [
            "teacher-final live signoff missing",
            "real retest proof missing or simulated",
            "shadow/candidate/simulated event attempts canonical mastery",
            "second learner memory or personalization authority appears",
            "production/canonical write occurs before authorization",
        ],
        "evidence_refs": [
            G4_TRUTH_WRITE_GUARD,
            G4_DRYRUN_CANDIDATES,
            G4_REAL_RETEST_PROOFS,
            G4_M32_RETEST_OUTCOME,
            G4_TEACHER_BRIDGE,
        ],
    }


def build_g5_remote_db_write_preflight() -> dict[str, Any]:
    manifest = _read_json_rel(G5_M19E_MANIFEST)
    no_remote_write = _read_json_rel(G5_M19E_NO_REMOTE_WRITE)
    readiness = _read_json_rel(G5_M19E_R_READINESS)
    no_remote_write_r = _read_json_rel(G5_M19E_R_NO_REMOTE_WRITE)

    evidence_ok = {
        G5_M19E_MANIFEST: bool(manifest),
        G5_M19E_NO_REMOTE_WRITE: bool(no_remote_write),
        G5_M19E_PROPOSED_COMMANDS: _rel_exists(G5_M19E_PROPOSED_COMMANDS),
        G5_M19E_ROLLBACK: _rel_exists(G5_M19E_ROLLBACK),
        G5_M19E_R_READINESS: bool(readiness),
        G5_M19E_R_NO_REMOTE_WRITE: bool(no_remote_write_r),
    }
    remote_root = manifest.get("target_remote_root_if_authorized")
    remote_roots = {
        remote_root,
        no_remote_write.get("remote_write_root_if_authorized"),
        no_remote_write_r.get("remote_write_root_if_authorized"),
    }
    remote_write_executed = (
        manifest.get("remote_write_executed") is True
        or manifest.get("deploy_or_restart_executed") is True
        or no_remote_write.get("deploy_or_restart_executed") is True
        or no_remote_write.get("no_ssh_executed") is False
        or no_remote_write.get("no_scp_or_rsync_executed") is False
        or no_remote_write_r.get("no_ssh_write_executed") is False
        or no_remote_write_r.get("no_deploy_executed") is False
        or no_remote_write_r.get("no_restart_executed") is False
    )
    db_write_executed = (
        manifest.get("production_db_write") != "NO-GO"
        or no_remote_write.get("production_db_written") is True
        or no_remote_write_r.get("production_db_written") is True
    )
    preconditions = {
        "m19e_authorization_package_present": bool(manifest),
        "m19e_r_readiness_rollup_present": bool(readiness),
        "no_remote_write_attestation_present": (
            no_remote_write.get("no_remote_write_attestation") is True
            and no_remote_write_r.get("no_remote_write") is True
        ),
        "remote_write_executed": remote_write_executed,
        "db_write_executed": db_write_executed,
        "remote_write_root_is_root_deeptutor": remote_roots == {"/root/deeptutor"},
        "outside_root_deeptutor_write_allowed": False,
    }
    no_write = {
        "production_write_count": max(
            int(readiness.get("m19c", {}).get("production_write_count", 999)),
            int(readiness.get("m19d", {}).get("production_write_count", 999)),
        ),
        "canonical_truth_written": any(
            value is True
            for value in (
                manifest.get("canonical_learner_truth_write") != "NO-GO",
                no_remote_write.get("canonical_truth_written"),
                no_remote_write_r.get("canonical_truth_written"),
                readiness.get("m19d", {}).get("canonical_truth_written"),
                readiness.get("m19c", {}).get("canonical_truth_write_enabled"),
            )
        ),
        "remote_write_count": 1 if remote_write_executed else 0,
        "db_write_count": 1 if db_write_executed else 0,
        "published_registry_executed": (
            manifest.get("formal_registry_emission") != "NO-GO"
            or no_remote_write.get("published_registry_emitted") is True
            or no_remote_write_r.get("published_registry_emitted") is True
        ),
    }

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "gate_id": "G5_remote_or_db_write",
        "scope": "read_only_pre_authorization_preflight",
        "verdict": "not_ready_explicit_authorization_required",
        "blocking_reason": (
            "remote/DB write requires explicit authorization with exact target path/table and rollback plan"
        ),
        "execution_mode": "read_only_no_remote_or_db_write",
        "without_authorization": "decision_package_only",
        "required_authorization": "explicit_remote_or_db_write_authorization",
        "allowed_scope_after_authorization": (
            "Aliyun writes only under /root/deeptutor; DB writes only named learner/grading tables"
        ),
        "promotion_path": "authorized_deploy_or_db_migration_only",
        "remote_write_root": remote_root,
        "preconditions": preconditions,
        "evidence_ok": evidence_ok,
        "missing_evidence_refs": [
            path for path, exists in evidence_ok.items() if not exists
        ],
        "single_authority": {
            "no_second_grading_truth": True,
            "no_second_learner_truth": True,
            "remote_write_boundary": (
                "/root/deeptutor only after explicit authorization"
            ),
            "learner_truth_source": "Learning Evidence Ledger / Learner Model only",
            "write_authority": "explicitly authorized deploy/DB plan only",
        },
        **no_write,
        "stop_conditions": [
            "target path outside /root/deeptutor",
            "exact target path/table is not named before execution",
            "rollback command or compensation plan is missing",
            "secret/raw env dump would be printed",
            "remote or DB write occurs before explicit authorization",
            "canonical learner truth write is bundled into remote/DB write",
        ],
        "evidence_refs": [
            G5_M19E_MANIFEST,
            G5_M19E_NO_REMOTE_WRITE,
            G5_M19E_PROPOSED_COMMANDS,
            G5_M19E_ROLLBACK,
            G5_M19E_R_READINESS,
            G5_M19E_R_NO_REMOTE_WRITE,
        ],
    }


def build_g6_real_wechat_package_preflight() -> dict[str, Any]:
    script_text = (REPO / G6_DEVTOOLS_E2E_SCRIPT).read_text(encoding="utf-8")
    evidence_ok = {
        G6_AGENTS_CONTRACT: _rel_exists(G6_AGENTS_CONTRACT),
        G6_DEVTOOLS_E2E_SCRIPT: _rel_exists(G6_DEVTOOLS_E2E_SCRIPT),
        G6_HOME_DASHBOARD_TEST: _rel_exists(G6_HOME_DASHBOARD_TEST),
    }
    devtools_project_root = "yousenwebview"
    target_subpackage = "packageDeeptutor"
    preconditions = {
        "devtools_e2e_script_present": evidence_ok[G6_DEVTOOLS_E2E_SCRIPT],
        "project_root_is_yousenwebview": (
            'DEFAULT_DEVTOOLS_PROJECT_PATH = PROJECT_ROOT / "yousenwebview"'
            in script_text
        ),
        "target_subpackage_is_packageDeeptutor": (
            'DEFAULT_DEVTOOLS_TARGET_SUBPACKAGE = "packageDeeptutor"'
            in script_text
        ),
        "true_package_page_automation_executed": False,
        "wechat_harness_not_counted_as_real": True,
        "devtools_login_or_open_not_counted_as_pass": True,
    }
    no_write = {
        "production_write_count": 0,
        "canonical_truth_written": False,
        "remote_write_count": 0,
        "published_registry_executed": False,
    }
    ready = (
        all(evidence_ok.values())
        and preconditions["true_package_page_automation_executed"] is True
    )

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "gate_id": "G6_real_wechat_package_page_automation",
        "scope": "read_only_pre_authorization_preflight",
        "verdict": "ready_for_user_authorization" if ready else "true_entry_pending",
        "blocking_reason": (
            "true WeChat package page automation evidence is required; /wechat-harness or DevTools login/open preflight is insufficient"
        ),
        "execution_mode": "read_only_no_devtools_launch",
        "without_authorization": "decision_package_only",
        "required_authorization": "devtools_or_manual_wechat_qa_window",
        "allowed_scope_after_authorization": (
            "open yousenwebview project root and drive packageDeeptutor page flow"
        ),
        "promotion_path": "verification_evidence_only_no_mastery_write",
        "devtools_project_root": devtools_project_root,
        "target_subpackage": target_subpackage,
        "auth_state": "unknown",
        "auth_mode": "none",
        "preconditions": preconditions,
        "evidence_classification": {
            "wechat_harness": "shadow_not_real_wechat_package",
            "devtools_islogin": "environment_preflight_only",
            "devtools_open_project": "project_preflight_only",
            "package_page_automation": "required_missing",
        },
        "evidence_ok": evidence_ok,
        "missing_evidence_refs": [
            path for path, exists in evidence_ok.items() if not exists
        ],
        "single_authority": {
            "no_second_grading_truth": True,
            "no_second_learner_truth": True,
            "real_entry_evidence_source": (
                "DevTools/miniprogram automation against yousenwebview project root plus packageDeeptutor page flow"
            ),
            "wechat_harness_role": "shadow QA only",
            "pcp_role": "read_only_feedback_context",
        },
        **no_write,
        "stop_conditions": [
            "only /wechat-harness evidence is available",
            "DevTools islogin/open is reported as scenario pass",
            "project root is packageDeeptutor instead of yousenwebview",
            "auth_state/auth_mode is unknown but reported as pass",
            "page-level automation result is missing",
            "any canonical learner truth write is requested by this gate",
        ],
        "evidence_refs": [
            G6_AGENTS_CONTRACT,
            G6_DEVTOOLS_E2E_SCRIPT,
            G6_HOME_DASHBOARD_TEST,
        ],
    }


def build_completion_audit() -> dict[str, Any]:
    requirements = [_with_evidence_health(row) for row in COMPLETION_REQUIREMENTS]
    statuses = {row["status"] for row in requirements}
    summary = {
        status: sum(1 for row in requirements if row["status"] == status)
        for status in sorted(statuses)
    }
    for status in ("done", "partial", "missing", "blocker", "authorization_gated"):
        summary.setdefault(status, 0)
    summary["evidence_missing_count"] = sum(
        len(row["missing_evidence_refs"]) for row in requirements
    )

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "scope": "explicit_objective_completion_audit",
        "requirements": requirements,
        "summary": summary,
        "single_authority": {
            "no_second_grading_truth": True,
            "no_second_learner_truth": True,
            "no_second_mastery": True,
            "grading_truth_source": "grading truth/artifact authority",
            "learner_truth_source": "Learning Evidence Ledger / Learner Model",
        },
        "missing_evidence": {
            row["id"]: row["missing_evidence_refs"]
            for row in requirements
            if row["missing_evidence_refs"]
        },
    }


def build_verification_closure(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not raw:
        return None

    commands = raw.get("commands") or []
    status = raw.get("status") or (
        "pass"
        if commands and all(command.get("exit_code") == 0 for command in commands)
        else "fail"
    )
    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "scope": "actual_verification_closure",
        "verified_commit": raw.get("verified_commit") or _current_commit(),
        "status": status,
        "command_count": len(commands),
        "commands": commands,
        "single_authority": {
            "verification_truth_source": "fresh local command output summarized in this closure",
            "does_not_write_grading_truth": True,
            "does_not_write_learner_truth": True,
        },
        "no_write": {
            "production_write_count": 0,
            "canonical_truth_written": False,
            "remote_write_count": 0,
            "published_registry_executed": False,
        },
    }


def build_final_acceptance_report(
    matrix: dict[str, Any],
    authorization_package: dict[str, Any],
    completion_audit: dict[str, Any],
    g1_preflight: dict[str, Any],
    g2_preflight: dict[str, Any],
    g3_preflight: dict[str, Any],
    g4_preflight: dict[str, Any],
    g5_preflight: dict[str, Any],
    g6_preflight: dict[str, Any],
    verification_closure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    remaining_gate_order = [
        "canonical_learner_truth_write",
        "production_default",
        "published_registry",
        "remote_or_db_write",
        "real_wechat_package_page_automation",
    ]
    remaining_gates = [
        gate for gate in remaining_gate_order if gate in matrix["remaining_gates"]
    ]
    artifacts = {
        "coverage_matrix": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/coverage_matrix.json"
        ),
        "completion_audit": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/completion_audit.json"
        ),
        "authorization_package": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/"
            "authorization_gate_decision_package.json"
        ),
        "g1_limited_default_preflight": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/"
            "G1_LIMITED_DEFAULT_PREFLIGHT.json"
        ),
        "g2_broad_default_preflight": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/"
            "G2_BROAD_DEFAULT_PREFLIGHT.json"
        ),
        "g3_published_registry_preflight": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/"
            "G3_PUBLISHED_REGISTRY_PREFLIGHT.json"
        ),
        "g4_canonical_learner_truth_preflight": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/"
            "G4_CANONICAL_LEARNER_TRUTH_PREFLIGHT.json"
        ),
        "g5_remote_db_write_preflight": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/"
            "G5_REMOTE_DB_WRITE_PREFLIGHT.json"
        ),
        "g6_real_wechat_package_preflight": (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/"
            "G6_REAL_WECHAT_PACKAGE_PREFLIGHT.json"
        ),
    }
    actual_verification = {
        "status": "not_recorded",
        "verified_commit": None,
        "command_count": 0,
        "artifact": None,
    }
    if verification_closure is not None:
        artifacts["verification_closure"] = (
            "artifacts/luban_grading_artifacts/"
            "grading_to_brain_current_gap_audit_20260608/"
            "VERIFICATION_CLOSURE_grading_to_brain.json"
        )
        actual_verification = {
            "status": verification_closure["status"],
            "verified_commit": verification_closure["verified_commit"],
            "command_count": verification_closure["command_count"],
            "artifact": artifacts["verification_closure"],
        }

    return {
        "schema_version": 1,
        "generated_by": "audit_luban_grading_to_brain_current_gap",
        "master_plan": MASTER_PLAN,
        "verdict": "not_complete_authorization_required",
        "verdict_reason": (
            "coverage and objective evidence are present, but canonical learner-truth "
            "write, production default, published registry, remote/DB write, and true "
            "wechat package-page evidence still require explicit authorization or QA."
        ),
        "current_commit": _current_commit(),
        "coverage_summary": matrix["summary"],
        "completion_summary": completion_audit["summary"],
        "quality_gates": matrix["quality_gates"],
        "remaining_authorization_gates": remaining_gates,
        "artifacts": artifacts,
        "actual_verification": actual_verification,
        "fresh_verification_commands": [
            {
                "command": (
                    "python -m pytest "
                    "tests/scripts/test_luban_grading_to_brain_current_gap_audit.py "
                    "tests/services/construction_grading/test_m32_grading_event_learning_evidence.py "
                    "tests/services/learner_state/test_m32_waterproof_learning_synthesis.py "
                    "tests/services/learner_state/test_m32_waterproof_personalization_context.py "
                    "tests/services/learner_state/test_m32_waterproof_next_best_action.py "
                    "tests/services/learner_state/test_m32_waterproof_retest_outcome.py "
                    "tests/services/member_console/test_home_dashboard_learning_projection.py -q"
                ),
                "expected_result": "pass",
            },
            {
                "command": (
                    "python scripts/check_contract_guard.py "
                    "scripts/audit_luban_grading_to_brain_current_gap.py "
                    "tests/scripts/test_luban_grading_to_brain_current_gap_audit.py "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/coverage_matrix.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/FINDING_grading_to_brain_current_gap_audit.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/authorization_gate_decision_package.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/AUTHORIZATION_GATES_grading_to_brain.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/completion_audit.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/COMPLETION_AUDIT_grading_to_brain.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/FINAL_ACCEPTANCE_REPORT_grading_to_brain.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/FINAL_ACCEPTANCE_REPORT_grading_to_brain.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G1_LIMITED_DEFAULT_PREFLIGHT.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G1_LIMITED_DEFAULT_PREFLIGHT.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G2_BROAD_DEFAULT_PREFLIGHT.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G2_BROAD_DEFAULT_PREFLIGHT.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G3_PUBLISHED_REGISTRY_PREFLIGHT.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G3_PUBLISHED_REGISTRY_PREFLIGHT.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G4_CANONICAL_LEARNER_TRUTH_PREFLIGHT.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G4_CANONICAL_LEARNER_TRUTH_PREFLIGHT.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G5_REMOTE_DB_WRITE_PREFLIGHT.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G5_REMOTE_DB_WRITE_PREFLIGHT.md "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G6_REAL_WECHAT_PACKAGE_PREFLIGHT.json "
                    "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608/G6_REAL_WECHAT_PACKAGE_PREFLIGHT.md"
                ),
                "expected_result": "pass",
            },
            {
                "command": "git diff --check",
                "expected_result": "pass",
            },
            {
                "command": "codegraph sync . && codegraph status .",
                "expected_result": "up_to_date",
            },
        ],
        "authorization_package_summary": {
            "recommended_next": [
                gate_id
                for gate_id, gate in authorization_package["gates"].items()
                if gate["recommended_next"]
            ],
            "g1_preflight_verdict": g1_preflight["verdict"],
            "g2_preflight_verdict": g2_preflight["verdict"],
            "g3_preflight_verdict": g3_preflight["verdict"],
            "g4_preflight_verdict": g4_preflight["verdict"],
            "g5_preflight_verdict": g5_preflight["verdict"],
            "g6_preflight_verdict": g6_preflight["verdict"],
            "no_write": {
                "production_write_count": authorization_package["production_write_count"],
                "canonical_truth_written": authorization_package[
                    "canonical_truth_written"
                ],
                "remote_write_count": authorization_package["remote_write_count"],
                "published_registry_executed": authorization_package[
                    "published_registry_executed"
                ],
            },
        },
    }


def write_g1_preflight_markdown(preflight: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# G1 Limited Default Preflight",
        "",
        f"- Gate: `{preflight['gate_id']}`",
        f"- Verdict: `{preflight['verdict']}`",
        f"- Scope: `{preflight['scope']}`",
        f"- Execution mode: `{preflight['execution_mode']}`",
        f"- Without authorization: `{preflight['without_authorization']}`",
        f"- Required authorization: `{preflight['required_authorization']}`",
        f"- Allowed scope after authorization: `{preflight['allowed_scope_after_authorization']}`",
        "",
        "This artifact does not flip production default, publish registry, write remote/DB state, or promote canonical learner truth.",
        "",
        "## No-Write Invariants",
        "",
        f"- production_write_count: `{preflight['production_write_count']}`",
        f"- canonical_truth_written: `{preflight['canonical_truth_written']}`",
        f"- remote_write_count: `{preflight['remote_write_count']}`",
        f"- published_registry_executed: `{preflight['published_registry_executed']}`",
        "",
        "## Preconditions",
        "",
    ]
    for key, value in preflight["preconditions"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Evidence", ""])
    for ref in preflight["evidence_refs"]:
        lines.append(f"- `{ref}`")

    lines.extend(
        [
            "",
            "## Stop Conditions",
            "",
        ]
    )
    for condition in preflight["stop_conditions"]:
        lines.append(f"- {condition}")

    lines.append("")
    (out_dir / "G1_LIMITED_DEFAULT_PREFLIGHT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_g2_preflight_markdown(preflight: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# G2 Broad Default Preflight",
        "",
        f"- Gate: `{preflight['gate_id']}`",
        f"- Verdict: `{preflight['verdict']}`",
        f"- Blocking reason: {preflight['blocking_reason']}",
        f"- Scope: `{preflight['scope']}`",
        f"- Execution mode: `{preflight['execution_mode']}`",
        f"- Without authorization: `{preflight['without_authorization']}`",
        f"- Required authorization: `{preflight['required_authorization']}`",
        f"- Allowed scope after authorization: `{preflight['allowed_scope_after_authorization']}`",
        f"- Promotion path: `{preflight['promotion_path']}`",
        "",
        "This artifact is a broad-default gate report only. It does not flip broad production default, write canonical learner truth, publish registry, or write remote/DB state.",
        "",
        "## No-Write Invariants",
        "",
        f"- production_write_count: `{preflight['production_write_count']}`",
        f"- canonical_truth_written: `{preflight['canonical_truth_written']}`",
        f"- remote_write_count: `{preflight['remote_write_count']}`",
        f"- published_registry_executed: `{preflight['published_registry_executed']}`",
        "",
        "## Preconditions",
        "",
    ]
    for key, value in preflight["preconditions"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Single Authority", ""])
    for key, value in preflight["single_authority"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Evidence", ""])
    for ref in preflight["evidence_refs"]:
        lines.append(f"- `{ref}`")

    lines.extend(["", "## Stop Conditions", ""])
    for condition in preflight["stop_conditions"]:
        lines.append(f"- {condition}")

    lines.append("")
    (out_dir / "G2_BROAD_DEFAULT_PREFLIGHT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_g3_preflight_markdown(preflight: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# G3 Published Registry Preflight",
        "",
        f"- Gate: `{preflight['gate_id']}`",
        f"- Verdict: `{preflight['verdict']}`",
        f"- Scope: `{preflight['scope']}`",
        f"- Execution mode: `{preflight['execution_mode']}`",
        f"- Without authorization: `{preflight['without_authorization']}`",
        f"- Required authorization: `{preflight['required_authorization']}`",
        f"- Promotion path: `{preflight['promotion_path']}`",
        "",
        "This artifact proves staged publish readiness only. It does not publish a registry.",
        "",
        "## Artifact Layers",
        "",
    ]
    for key, value in preflight["artifact_layers"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## No-Write Invariants", ""])
    lines.extend(
        [
            f"- production_write_count: `{preflight['production_write_count']}`",
            f"- canonical_truth_written: `{preflight['canonical_truth_written']}`",
            f"- remote_write_count: `{preflight['remote_write_count']}`",
            f"- published_registry_executed: `{preflight['published_registry_executed']}`",
            "",
            "## Preconditions",
            "",
        ]
    )
    for key, value in preflight["preconditions"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Single Authority", ""])
    for key, value in preflight["single_authority"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Evidence", ""])
    for ref in preflight["evidence_refs"]:
        lines.append(f"- `{ref}`")

    lines.extend(["", "## Stop Conditions", ""])
    for condition in preflight["stop_conditions"]:
        lines.append(f"- {condition}")

    lines.append("")
    (out_dir / "G3_PUBLISHED_REGISTRY_PREFLIGHT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_g4_preflight_markdown(preflight: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# G4 Canonical Learner Truth Preflight",
        "",
        f"- Gate: `{preflight['gate_id']}`",
        f"- Verdict: `{preflight['verdict']}`",
        f"- Blocking reason: {preflight['blocking_reason']}",
        f"- Scope: `{preflight['scope']}`",
        f"- Execution mode: `{preflight['execution_mode']}`",
        f"- Without authorization: `{preflight['without_authorization']}`",
        f"- Required authorization: `{preflight['required_authorization']}`",
        f"- Promotion path: `{preflight['promotion_path']}`",
        "",
        "This artifact proves the gate state only. It does not write canonical learner truth.",
        "",
        "## No-Write Invariants",
        "",
        f"- production_write_count: `{preflight['production_write_count']}`",
        f"- canonical_truth_written: `{preflight['canonical_truth_written']}`",
        f"- remote_write_count: `{preflight['remote_write_count']}`",
        f"- published_registry_executed: `{preflight['published_registry_executed']}`",
        "",
        "## Preconditions",
        "",
    ]
    for key, value in preflight["preconditions"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Single Authority", ""])
    for key, value in preflight["single_authority"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Evidence", ""])
    for ref in preflight["evidence_refs"]:
        lines.append(f"- `{ref}`")

    lines.extend(["", "## Stop Conditions", ""])
    for condition in preflight["stop_conditions"]:
        lines.append(f"- {condition}")

    lines.append("")
    (out_dir / "G4_CANONICAL_LEARNER_TRUTH_PREFLIGHT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_g5_preflight_markdown(preflight: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# G5 Remote / DB Write Preflight",
        "",
        f"- Gate: `{preflight['gate_id']}`",
        f"- Verdict: `{preflight['verdict']}`",
        f"- Blocking reason: {preflight['blocking_reason']}",
        f"- Scope: `{preflight['scope']}`",
        f"- Execution mode: `{preflight['execution_mode']}`",
        f"- Without authorization: `{preflight['without_authorization']}`",
        f"- Required authorization: `{preflight['required_authorization']}`",
        f"- Remote write root: `{preflight['remote_write_root']}`",
        f"- Promotion path: `{preflight['promotion_path']}`",
        "",
        "This artifact is a read-only pre-authorization gate. It does not run SSH, deploy, restart, publish a registry, write DB rows, or write canonical learner truth.",
        "",
        "## No-Write Invariants",
        "",
        f"- production_write_count: `{preflight['production_write_count']}`",
        f"- canonical_truth_written: `{preflight['canonical_truth_written']}`",
        f"- remote_write_count: `{preflight['remote_write_count']}`",
        f"- db_write_count: `{preflight['db_write_count']}`",
        f"- published_registry_executed: `{preflight['published_registry_executed']}`",
        "",
        "## Preconditions",
        "",
    ]
    for key, value in preflight["preconditions"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Single Authority", ""])
    for key, value in preflight["single_authority"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Evidence", ""])
    for ref in preflight["evidence_refs"]:
        lines.append(f"- `{ref}`")

    lines.extend(["", "## Stop Conditions", ""])
    for condition in preflight["stop_conditions"]:
        lines.append(f"- {condition}")

    lines.append("")
    (out_dir / "G5_REMOTE_DB_WRITE_PREFLIGHT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_g6_preflight_markdown(preflight: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# G6 Real WeChat Package Preflight",
        "",
        f"- Gate: `{preflight['gate_id']}`",
        f"- Verdict: `{preflight['verdict']}`",
        f"- Blocking reason: {preflight['blocking_reason']}",
        f"- Scope: `{preflight['scope']}`",
        f"- Execution mode: `{preflight['execution_mode']}`",
        f"- Without authorization: `{preflight['without_authorization']}`",
        f"- Required authorization: `{preflight['required_authorization']}`",
        f"- DevTools project root: `{preflight['devtools_project_root']}`",
        f"- Target subpackage: `{preflight['target_subpackage']}`",
        "",
        "This artifact does not launch DevTools, open the project, drive pages, or write product state. It only defines the evidence boundary for true WeChat package-page acceptance.",
        "",
        "## Evidence Classification",
        "",
    ]
    for key, value in preflight["evidence_classification"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## No-Write Invariants", ""])
    lines.extend(
        [
            f"- production_write_count: `{preflight['production_write_count']}`",
            f"- canonical_truth_written: `{preflight['canonical_truth_written']}`",
            f"- remote_write_count: `{preflight['remote_write_count']}`",
            f"- published_registry_executed: `{preflight['published_registry_executed']}`",
            "",
            "## Preconditions",
            "",
        ]
    )
    for key, value in preflight["preconditions"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Single Authority", ""])
    for key, value in preflight["single_authority"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Evidence", ""])
    for ref in preflight["evidence_refs"]:
        lines.append(f"- `{ref}`")

    lines.extend(["", "## Stop Conditions", ""])
    for condition in preflight["stop_conditions"]:
        lines.append(f"- {condition}")

    lines.append("")
    (out_dir / "G6_REAL_WECHAT_PACKAGE_PREFLIGHT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_verification_closure_markdown(
    closure: dict[str, Any],
    out_dir: Path,
) -> None:
    lines = [
        "# Grading-to-Brain Verification Closure",
        "",
        f"- Status: `{closure['status']}`",
        f"- Verified commit: `{closure['verified_commit']}`",
        f"- Command count: `{closure['command_count']}`",
        "",
        "This artifact records actual command results. It does not write grading truth, learner truth, production defaults, registry state, remote files, or DB rows.",
        "",
        "## Commands",
        "",
        "| Command | Exit Code | Observed Result |",
        "|---|---:|---|",
    ]
    for command in closure["commands"]:
        lines.append(
            "| "
            f"`{command['command']}` | {command['exit_code']} | "
            f"{command.get('observed_result', '')} |"
        )

    lines.extend(["", "## Single Authority", ""])
    for key, value in closure["single_authority"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## No-Write Invariants", ""])
    for key, value in closure["no_write"].items():
        lines.append(f"- {key}: `{value}`")

    lines.append("")
    (out_dir / "VERIFICATION_CLOSURE_grading_to_brain.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_markdown(matrix: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# Grading-to-Brain Current Gap Audit",
        "",
        f"- Master plan: `{matrix['master_plan']}`",
        f"- Scope: `{matrix['scope']}`",
        "- This audit is read-only: it does not write production state, DB rows, or canonical mastery.",
        "",
        "## Single Authority",
        "",
        f"- Grading truth: {matrix['single_authority']['grading_truth_authority']}",
        f"- Learner truth: {matrix['single_authority']['learner_truth_authority']}",
        "- Shadow/candidate/simulated outputs are evidence candidates only, never canonical mastery.",
        "",
        "## Scenario Matrix",
        "",
        "| ID | Scenario | Status | Evidence |",
        "|---|---|---:|---|",
    ]

    for row in matrix["scenarios"]:
        evidence = "<br>".join(f"`{ref}`" for ref in row["evidence_refs"])
        lines.append(
            f"| {row['id']} | {row['title']} | {row['status']} | {evidence} |"
        )

    lines.extend(
        [
            "",
            "## Quality Gates",
            "",
            "| Gate | Value |",
            "|---|---:|",
        ]
    )
    for key, value in matrix["quality_gates"].items():
        lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Remaining Authorization Gates",
            "",
            "| Gate | State |",
            "|---|---|",
        ]
    )
    for key, value in matrix["remaining_gates"].items():
        lines.append(f"| {key} | `{value}` |")

    lines.extend(
        [
            "",
            "## Verdict",
            "",
            (
                "The Grading-to-Brain implementation has evidence for all S1-S12 "
                "acceptance surfaces, with S6 and S11 still marked partial because "
                "external norm publication and published registry promotion remain "
                "authorization-gated. This artifact is a decision package, not a "
                "production promotion."
            ),
            "",
        ]
    )
    (out_dir / "FINDING_grading_to_brain_current_gap_audit.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_authorization_markdown(package: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# Grading-to-Brain Authorization Gates",
        "",
        f"- Master plan: `{package['master_plan']}`",
        f"- Scope: `{package['scope']}`",
        "- This package is read-only and executes no production, registry, learner-truth, remote, or DB write.",
        "",
        "## Single Authority",
        "",
        f"- Grading truth source: {package['single_authority']['grading_truth_source']}",
        f"- Learner truth source: {package['single_authority']['learner_truth_source']}",
        "- PersonalizationContextPack remains read-only feedback context.",
        "",
        "## Recommended Order",
        "",
    ]
    for gate_id in package["execution_order"]:
        lines.append(f"- `{gate_id}`")

    lines.extend(
        [
            "",
            "## Gate Table",
            "",
            "| Gate | Current State | Recommended Next | Required Authorization | Without Authorization | Evidence |",
            "|---|---|---:|---|---|---|",
        ]
    )
    for gate_id, gate in package["gates"].items():
        evidence = "<br>".join(f"`{ref}`" for ref in gate["evidence_refs"])
        lines.append(
            "| "
            f"{gate_id} | {gate['current_state']} | {gate['recommended_next']} | "
            f"{gate['required_authorization']} | `{gate['without_authorization']}` | "
            f"{evidence} |"
        )

    lines.extend(
        [
            "",
            "## Non-Negotiables",
            "",
            "- Do not promote shadow, candidate, simulated, or test-runner output to canonical mastery.",
            "- Do not publish registry versions without signed hash/version evidence and rollback pointer.",
            "- Do not write remote files outside `/root/deeptutor`.",
            "- Do not count `/wechat-harness` as true `packageDeeptutor` evidence.",
            "",
        ]
    )
    (out_dir / "AUTHORIZATION_GATES_grading_to_brain.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_completion_markdown(audit: dict[str, Any], out_dir: Path) -> None:
    lines = [
        "# Grading-to-Brain Completion Audit",
        "",
        f"- Master plan: `{audit['master_plan']}`",
        f"- Scope: `{audit['scope']}`",
        "- This audit maps the objective's seven explicit loop requirements to evidence.",
        "",
        "## Single Authority",
        "",
        f"- Grading truth: {audit['single_authority']['grading_truth_source']}",
        f"- Learner truth: {audit['single_authority']['learner_truth_source']}",
        "- No second mastery/profile/recommendation truth is introduced by this audit.",
        "",
        "## Requirement Matrix",
        "",
        "| ID | Requirement | Status | Authority | Evidence |",
        "|---|---|---:|---|---|",
    ]
    for row in audit["requirements"]:
        evidence = "<br>".join(f"`{ref}`" for ref in row["evidence_refs"])
        lines.append(
            f"| {row['id']} | {row['title']} | {row['status']} | "
            f"{row['authority']} | {evidence} |"
        )

    lines.extend(
        [
            "",
            "## Remaining Gate",
            "",
            (
                "R6 remains `authorization_gated`: real retest proof and dry-run "
                "promotion evidence exist, but production canonical learner-truth "
                "write still requires explicit authorization."
            ),
            "",
        ]
    )
    (out_dir / "COMPLETION_AUDIT_grading_to_brain.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def write_final_acceptance_markdown(
    report: dict[str, Any],
    out_dir: Path,
) -> None:
    lines = [
        "# Grading-to-Brain Final Acceptance Report",
        "",
        f"- Verdict: `{report['verdict']}`",
        f"- Current commit: `{report['current_commit']}`",
        f"- Reason: {report['verdict_reason']}",
        f"- Actual verification: `{report['actual_verification']['status']}`",
        "",
        "## Coverage",
        "",
        f"- S1-S12: {report['coverage_summary']}",
        f"- R1-R7: {report['completion_summary']}",
        f"- Quality gates: {report['quality_gates']}",
        "",
        "## Remaining Authorization Gates",
        "",
    ]
    for gate in report["remaining_authorization_gates"]:
        lines.append(f"- `{gate}`")

    lines.extend(
        [
            "",
            "## Fresh Verification Commands",
            "",
        ]
    )
    for command in report["fresh_verification_commands"]:
        lines.append(f"- `{command['command']}` -> `{command['expected_result']}`")

    lines.extend(["", "## Artifacts", ""])
    for name, path in report["artifacts"].items():
        lines.append(f"- {name}: `{path}`")

    lines.append("")
    (out_dir / "FINAL_ACCEPTANCE_REPORT_grading_to_brain.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verification-results", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    matrix = build_matrix()
    authorization_package = build_authorization_package()
    completion_audit = build_completion_audit()
    g1_preflight = build_g1_limited_default_preflight()
    g2_preflight = build_g2_broad_default_preflight(g1_preflight)
    g3_preflight = build_g3_published_registry_preflight()
    g4_preflight = build_g4_canonical_learner_truth_preflight()
    g5_preflight = build_g5_remote_db_write_preflight()
    g6_preflight = build_g6_real_wechat_package_preflight()
    verification_closure = build_verification_closure(
        _read_json_path(args.verification_results)
    )
    final_report = build_final_acceptance_report(
        matrix,
        authorization_package,
        completion_audit,
        g1_preflight,
        g2_preflight,
        g3_preflight,
        g4_preflight,
        g5_preflight,
        g6_preflight,
        verification_closure,
    )
    (out_dir / "coverage_matrix.json").write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "authorization_gate_decision_package.json").write_text(
        json.dumps(
            authorization_package,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "completion_audit.json").write_text(
        json.dumps(
            completion_audit,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "G1_LIMITED_DEFAULT_PREFLIGHT.json").write_text(
        json.dumps(
            g1_preflight,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "G2_BROAD_DEFAULT_PREFLIGHT.json").write_text(
        json.dumps(
            g2_preflight,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "G3_PUBLISHED_REGISTRY_PREFLIGHT.json").write_text(
        json.dumps(
            g3_preflight,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "G4_CANONICAL_LEARNER_TRUTH_PREFLIGHT.json").write_text(
        json.dumps(
            g4_preflight,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "G5_REMOTE_DB_WRITE_PREFLIGHT.json").write_text(
        json.dumps(
            g5_preflight,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "G6_REAL_WECHAT_PACKAGE_PREFLIGHT.json").write_text(
        json.dumps(
            g6_preflight,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if verification_closure is not None:
        (out_dir / "VERIFICATION_CLOSURE_grading_to_brain.json").write_text(
            json.dumps(
                verification_closure,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    (out_dir / "FINAL_ACCEPTANCE_REPORT_grading_to_brain.json").write_text(
        json.dumps(
            final_report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_markdown(matrix, out_dir)
    write_authorization_markdown(authorization_package, out_dir)
    write_completion_markdown(completion_audit, out_dir)
    write_g1_preflight_markdown(g1_preflight, out_dir)
    write_g2_preflight_markdown(g2_preflight, out_dir)
    write_g3_preflight_markdown(g3_preflight, out_dir)
    write_g4_preflight_markdown(g4_preflight, out_dir)
    write_g5_preflight_markdown(g5_preflight, out_dir)
    write_g6_preflight_markdown(g6_preflight, out_dir)
    if verification_closure is not None:
        write_verification_closure_markdown(verification_closure, out_dir)
    write_final_acceptance_markdown(final_report, out_dir)

    missing = {
        "coverage_matrix": matrix["missing_evidence"],
        "authorization_package": authorization_package["missing_evidence"],
        "completion_audit": completion_audit["missing_evidence"],
        "g1_preflight": g1_preflight["missing_evidence_refs"],
        "g2_preflight": g2_preflight["missing_evidence_refs"],
        "g3_preflight": g3_preflight["missing_evidence_refs"],
        "g4_preflight": g4_preflight["missing_evidence_refs"],
        "g5_preflight": g5_preflight["missing_evidence_refs"],
        "g6_preflight": g6_preflight["missing_evidence_refs"],
    }
    missing = {key: value for key, value in missing.items() if value}
    if missing:
        print(json.dumps(missing, indent=2, sort_keys=True))
        return 1
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
