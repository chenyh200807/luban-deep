from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO
    / "artifacts/luban_grading_artifacts/grading_to_brain_current_gap_audit_20260608"
)

MASTER_PLAN = "docs/plan/2026-06-04-luban-grading-engine-master-control-plan.md"


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


def _rel_exists(path: str) -> bool:
    return (REPO / path).exists()


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    matrix = build_matrix()
    authorization_package = build_authorization_package()
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
    write_markdown(matrix, out_dir)
    write_authorization_markdown(authorization_package, out_dir)

    missing = {
        "coverage_matrix": matrix["missing_evidence"],
        "authorization_package": authorization_package["missing_evidence"],
    }
    missing = {key: value for key, value in missing.items() if value}
    if missing:
        print(json.dumps(missing, indent=2, sort_keys=True))
        return 1
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
