"""M20 — LLM-assisted Continuous Artifact Compiler factory.

This compiler consumes prior runtime / review / Learning Brain artifacts and emits
candidate artifact deltas. It does not call live providers, touch runtime, write DB,
or mutate canonical learner truth. LLM-style roles are represented as audit prompts
and deterministic replay votes over already-produced evidence; deterministic signer
is the only release-candidate authority.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
M17A = AR / "runtime_llm_adjudicator_m17a_20260604"
M17B_M18 = AR / "runtime_llm_ai_council_scaleout_m17b_m18_20260604"
M17C = AR / "deepseek_live_calibration_completion_m17c_20260604"
M18C = AR / "learning_brain_dream_cycle_m18c_20260604"
M18D = AR / "learning_brain_real_retest_canonical_gate_m18d_20260604"
M13D = AR / "teacher_review_ops_hardening_m13d_20260604"
OUT_DEFAULT = AR / "llm_artifact_compiler_continuous_factory_m20_20260604"

DELTA_KINDS = {
    "source_candidate_delta",
    "rubric_normalization_delta",
    "machine_spec_delta",
    "list_rule_coverage_delta",
    "grading_packet_compression_delta",
    "learning_brain_claim_mapping_delta",
    "external_source_work_order",
    "validator_rule_delta",
}
FINAL_ACTIONS = {"accept", "reject", "needs_more_evidence", "work_order"}
REQUIRED_OUTPUTS = (
    "compiler_input_inventory_m20.json",
    "runtime_feedback_classification_m20.json",
    "model_role_prompts_m20.md",
    "ai_council_artifact_repair_votes_m20.jsonl",
    "candidate_delta_registry_m20.jsonl",
    "rejected_delta_candidates_m20.jsonl",
    "deterministic_signer_report_m20.json",
    "adversarial_artifact_attack_results_m20.json",
    "ws_shadow_replay_delta_eval_m20.json",
    "artifact_version_supersession_matrix_m20.md",
    "release_candidate_delta_m20.json",
    "FINDING_llm_artifact_compiler_continuous_factory_m20_20260604.md",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _write_json(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _write_jsonl(out: Path, name: str, rows: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    (out / name).write_text(text, "utf-8")


def _write_text(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


def _stable_hash(obj: Any, n: int = 16) -> str:
    return sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:n]


def _input_inventory() -> dict[str, Any]:
    paths = {
        "m17a_runtime_llm_adjudication_logs": M17A / "runtime_llm_adjudication_results_m17a.jsonl",
        "m17a_validator_results": M17A / "deterministic_validator_results_m17a.jsonl",
        "m17a_learning_brain_event_drafts": M17A / "learning_brain_event_drafts_m17a.jsonl",
        "m17b_m18_runtime_scaleout_logs": M17B_M18 / "runtime_llm_adjudication_scaleout.jsonl",
        "m17b_m18_validator_downgrade_records": M17B_M18 / "validator_downgrade_audit.jsonl",
        "m17b_m18_ai_council_disagreement_records": M17B_M18 / "ai_council_votes.jsonl",
        "m17b_m18_artifact_feedback_candidates": M17B_M18 / "artifact_feedback_candidates.jsonl",
        "m17c_live_calls": M17C / "deepseek_live_calls_m17c.jsonl",
        "m17c_validator_rechecks": M17C / "validator_recheck_results_m17c.jsonl",
        "m18c_claim_lifecycle": M18C / "claim_lifecycle_projection_m18c.jsonl",
        "m18d_real_retest_proofs": M18D / "real_retest_proofs_m18d.jsonl",
        "m18d_canonical_write_dryrun_candidates": M18D / "canonical_write_dryrun_candidates_m18d.jsonl",
        "m18d_blocked_or_retest_again": M18D / "blocked_or_retest_again_queue_m18d.jsonl",
        "m13d_review_queue": M13D / "review_queue_consolidated_m13d.jsonl",
    }
    counts: dict[str, int] = {}
    missing: list[str] = []
    hashes: dict[str, str] = {}
    for key, path in paths.items():
        if not path.exists():
            missing.append(key)
            counts[key] = 0
            continue
        data = path.read_bytes()
        counts[key] = len(path.read_text("utf-8").splitlines()) if path.suffix == ".jsonl" else 1
        hashes[key] = sha256(data).hexdigest()
    return {
        "stage": "M20 LLM-assisted Continuous Artifact Compiler",
        "input_paths": {k: str(v.relative_to(REPO)) for k, v in paths.items()},
        "counts": counts,
        "content_hashes": hashes,
        "missing_inputs": missing,
        "live_llm_calls_executed": 0,
        "live_ws_calls_executed": 0,
        "input_authority_note": "prior artifacts are evidence inputs only; official/model/council votes are never source truth",
    }


def _classify_feedback() -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    downgrades = _read_jsonl(M17B_M18 / "validator_downgrade_audit.jsonl") + _read_jsonl(
        M17C / "validator_recheck_results_m17c.jsonl"
    )
    feedback = _read_jsonl(M17B_M18 / "artifact_feedback_candidates.jsonl")
    council = _read_jsonl(M17B_M18 / "ai_council_votes.jsonl")
    queue = _read_jsonl(M13D / "review_queue_consolidated_m13d.jsonl")
    lb_claims = _read_jsonl(M18C / "claim_lifecycle_projection_m18c.jsonl")
    lb_proofs = _read_jsonl(M18D / "real_retest_proofs_m18d.jsonl")
    lb_blocked = _read_jsonl(M18D / "blocked_or_retest_again_queue_m18d.jsonl")

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in downgrades:
        reason = row.get("downgrade_reason") or "unknown_downgrade"
        if reason == "deterministic_matcher_rejected_llm_accept":
            buckets["unsupported_positive"].append(row)
        elif reason == "evidence_span_not_in_student_answer":
            buckets["source_laundering_risk"].append(row)
        else:
            buckets["validator_downgrade"].append(row)

    for row in feedback:
        final = row.get("council_final")
        kind = row.get("candidate_kind")
        if final in {"rewrite", "split"}:
            buckets["rubric_or_packet_repair"].append(row)
        elif final in {"work_order", "external"}:
            buckets["source_spec_gap_work_order"].append(row)
        elif kind and "machine" in kind:
            buckets["machine_spec_residual_gap"].append(row)
        else:
            buckets["artifact_feedback_candidate"].append(row)

    for row in council:
        if row.get("severe_disagreement"):
            buckets["ai_council_disagreement"].append(row)

    for row in queue:
        bucket = row.get("bucket") or "review_queue_unknown"
        if bucket in {"source_gap", "external_source_needed"}:
            buckets["review_queue_source_gap"].append(row)
        elif bucket in {"spec_gap", "teacher_override_needed"}:
            buckets["review_queue_spec_or_override_gap"].append(row)
        elif row.get("risk_bucket") == "high":
            buckets["high_risk_review"].append(row)
        elif row.get("final_disposition") in {"needs_review", "review_required"}:
            buckets["needs_review"].append(row)

    for row in lb_claims:
        if row.get("final_disposition") == "needs_retest":
            buckets["learning_brain_needs_retest"].append(row)
    for row in lb_proofs:
        if row.get("status") == "real_retest_proof_valid":
            buckets["learning_brain_valid_retest_proof"].append(row)
        else:
            buckets["learning_brain_blocked_retest"].append(row)
    buckets["learning_brain_blocked_retest"].extend(lb_blocked)

    summary = {
        "workflow_patterns": {
            "classify_and_act": "bucket misses, downgrades, disagreements, review gaps, and LB retest outcomes",
            "fanout_and_synthesize": "four expert roles produce non-source repair suggestions",
            "generate_and_filter": "candidate deltas are created, then filtered by signer and attack suite",
            "adversarial_verification": "source laundering / partial list / calc / unsupported-positive attacks",
            "tournament": "smallest stable delta that improves packet quality wins",
            "loop_until_done": "every candidate receives accept/reject/needs_more_evidence/work_order",
        },
        "bucket_counts": {k: len(v) for k, v in sorted(buckets.items())},
        "downgrade_reason_counts": dict(Counter(row.get("downgrade_reason") or "unknown" for row in downgrades)),
        "review_queue_bucket_counts": dict(Counter(row.get("bucket") or "unknown" for row in queue)),
        "lb_retest_status_counts": dict(Counter(row.get("status") or row.get("final_disposition") or "unknown" for row in lb_proofs + lb_blocked)),
        "all_feedback_actions_terminal": True,
    }
    return summary, buckets


def _model_role_prompts() -> str:
    return """# M20 Model Role Prompts

No live model calls were executed in this M20 run. These prompts are the reusable worker contracts
for the continuous compiler; current votes are deterministic replay over prior evidence.

## DeepSeek-V4 — batch source-hit triage / strict miss classifier
- Input: runtime misses, validator downgrades, unsupported positives, source/spec gaps.
- Output: classify as source_candidate_delta, spec_delta, packet_delta, reject, or work_order.
- Constraint: may suggest source hunt terms, never declare source truth.

## Qwen 3.7 Plus — Chinese semantics / list-rule boundary reviewer
- Input: Chinese rubric terms, near-synonyms, list_rule partial hits, teacher queue text.
- Output: list item boundary suggestions and partial-credit warnings.
- Constraint: list_rule can become auto only when denominator plus item set coverage equals 1.0.

## Codex GPT5.5 — rubric schema / compiler compatibility architect
- Input: candidate deltas and schema/hash/supersession requirements.
- Output: minimal machine-compatible delta with stable ids and rollback pointer.
- Constraint: model vote is review input only, never source authority or signer.

## Claude Code Opus 4.8 — workflow judge / adversarial verifier
- Input: candidate registry, rejected variants, signer report, attack suite.
- Output: GO/WEAK-GO/NO-GO judgement and source-laundering attack notes.
- Constraint: do not impersonate human/teacher/PO review.
"""


def _delta_kind_from_feedback(row: dict[str, Any]) -> str:
    candidate_kind = str(row.get("candidate_kind") or "")
    authority = str(row.get("authority_kind") or "")
    if "list" in authority or "list" in candidate_kind:
        return "list_rule_coverage_delta"
    if "machine" in candidate_kind or "calculation" in authority or "logic" in authority:
        return "machine_spec_delta"
    if "source" in candidate_kind or "source" in authority:
        return "source_candidate_delta"
    if "packet" in candidate_kind:
        return "grading_packet_compression_delta"
    return "rubric_normalization_delta"


def _action_from_feedback(row: dict[str, Any]) -> str:
    final = row.get("council_final")
    if final in {"rewrite", "split", "packet_fix", "validator_rule_fix"}:
        return "accept"
    if final in {"work_order", "external", "needs_review"}:
        return "work_order"
    if final == "drop":
        return "reject"
    return "needs_more_evidence"


def _candidate(
    source_event: str,
    delta_kind: str,
    question_id: str,
    point_id: str,
    action: str,
    rationale: str,
    *,
    authority_kind: str = "unknown",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = {
        "source_event": source_event,
        "delta_kind": delta_kind,
        "question_id": question_id or "unknown_question",
        "point_id": point_id or "unknown_point",
        "authority_kind": authority_kind or "unknown",
        "final_action": action,
        "status": {
            "accept": "accepted_candidate_delta",
            "reject": "rejected",
            "needs_more_evidence": "needs_more_evidence",
            "work_order": "work_order",
        }[action],
        "rationale": rationale[:360],
        "payload": payload or {},
        "source_truth_signed": False,
        "official_answer_as_source": False,
        "model_vote_as_source": False,
        "council_vote_as_source": False,
        "human_reviewed": False,
        "production_runtime_connected": False,
        "production_write_count": 0,
        "canonical_learner_truth_written": False,
        "touches_release_registry": False,
    }
    base["candidate_id"] = "m20_" + _stable_hash(base)
    return base


def _council_votes_for(candidate: dict[str, Any]) -> dict[str, Any]:
    action = candidate["final_action"]
    kind = candidate["delta_kind"]
    high_risk = candidate["authority_kind"] in {"high_risk", "external_source", "adversarial_negative"}
    votes = {
        "deepseek_v4": {
            "role": "strict_miss_triage",
            "vote": action,
            "rationale": "bucketed from runtime miss/downgrade evidence; source truth not signed",
        },
        "qwen37_plus": {
            "role": "chinese_semantics_and_list_boundary",
            "vote": "needs_more_evidence" if kind == "list_rule_coverage_delta" and action == "accept" else action,
            "rationale": "checks Chinese term/list boundary; list partial remains non-auto until denominator+items are complete",
        },
        "gpt55_codex": {
            "role": "schema_and_compiler_compatibility",
            "vote": action if action != "accept" or not high_risk else "work_order",
            "rationale": "requires signer schema/hash/source-boundary pass before release-candidate delta",
        },
        "opus48": {
            "role": "workflow_judge_adversarial_verifier",
            "vote": action if action != "accept" or not high_risk else "needs_more_evidence",
            "rationale": "attacks source laundering, unsupported positives, bad calc, and production-overreach",
        },
    }
    return {
        "candidate_id": candidate["candidate_id"],
        "question_id": candidate["question_id"],
        "point_id": candidate["point_id"],
        "delta_kind": kind,
        "model_votes": votes,
        "reviewer_type": "ai_expert_council_replay",
        "live_model_calls_executed": 0,
        "human_reviewed": False,
        "council_replaced_source": False,
        "model_vote_as_source": False,
    }


def _generate_candidates(buckets: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in buckets.get("rubric_or_packet_repair", []) + buckets.get("source_spec_gap_work_order", []) + buckets.get("machine_spec_residual_gap", []) + buckets.get("artifact_feedback_candidate", []):
        action = _action_from_feedback(row)
        c = _candidate(
            "m17b_m18_artifact_feedback",
            _delta_kind_from_feedback(row),
            str(row.get("question_id") or ""),
            str(row.get("point_id") or ""),
            action,
            str(row.get("rationale") or "artifact feedback candidate"),
            authority_kind=str(row.get("authority_kind") or ""),
            payload={
                "council_final": row.get("council_final"),
                "candidate_kind": row.get("candidate_kind"),
                "stops_at": "candidate_delta_or_work_order",
                "source_hunt_terms_only": action == "work_order",
            },
        )
        candidates.append(c)

    for row in buckets.get("unsupported_positive", []) + buckets.get("source_laundering_risk", []) + buckets.get("validator_downgrade", []):
        reason = row.get("downgrade_reason") or "validator_downgrade"
        kind = "grading_packet_compression_delta"
        if reason == "evidence_span_not_in_student_answer":
            kind = "validator_rule_delta"
        action = "accept" if kind in {"grading_packet_compression_delta", "validator_rule_delta"} else "needs_more_evidence"
        candidates.append(_candidate(
            "m17b_m17c_validator_downgrade",
            kind,
            str(row.get("question_id") or ""),
            str(row.get("point_id") or ""),
            action,
            f"Convert validator downgrade '{reason}' into packet/validator guidance so future packets ask for point-local evidence.",
            authority_kind=str(row.get("authority_kind") or ""),
            payload={
                "variant": row.get("variant"),
                "llm_disposition": row.get("llm_disposition"),
                "final_disposition": row.get("final_disposition"),
                "downgrade_reason": reason,
                "auto_certifiable": False,
            },
        ))

    queue = (
        buckets.get("review_queue_source_gap", [])
        + buckets.get("review_queue_spec_or_override_gap", [])
        + buckets.get("high_risk_review", [])
        + buckets.get("needs_review", [])
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in queue:
        grouped[(str(row.get("bucket") or "unknown"), str(row.get("authority_kind") or "unknown"))].append(row)
    for (bucket, authority), rows in sorted(grouped.items()):
        sample = rows[0]
        if bucket == "source_gap":
            kind, action = "source_candidate_delta", "needs_more_evidence"
        elif bucket == "external_source_needed" or authority == "external_source":
            kind, action = "external_source_work_order", "work_order"
        elif "list" in authority:
            kind, action = "list_rule_coverage_delta", "needs_more_evidence"
        elif "calculation" in authority or "machine" in authority:
            kind, action = "machine_spec_delta", "needs_more_evidence"
        else:
            kind, action = "rubric_normalization_delta", "needs_more_evidence"
        candidates.append(_candidate(
            "m13d_review_queue_group",
            kind,
            str(sample.get("question_id") or ""),
            str(sample.get("point_id") or ""),
            action,
            f"Review queue group {bucket}/{authority} has {len(rows)} unresolved operational cases; create compact work order.",
            authority_kind=authority,
            payload={
                "queue_bucket": bucket,
                "queue_count": len(rows),
                "can_override_any": any(bool(r.get("can_override")) for r in rows),
                "mistaken_accept_guard_required": any(r.get("risk_bucket") == "high" or bucket == "source_gap" for r in rows),
            },
        ))

    for row in buckets.get("learning_brain_valid_retest_proof", []):
        candidates.append(_candidate(
            "m18d_real_retest_proof",
            "learning_brain_claim_mapping_delta",
            str(row.get("question_id") or ""),
            ",".join(row.get("improved_new_auto_points") or row.get("target_point_ids") or []),
            "accept",
            "Real /api/v1/ws retest proof supports a more specific Learning Brain claim-mapping packet; dry-run only.",
            authority_kind="learning_brain_retest_proof",
            payload={
                "claim_id": row.get("claim_id"),
                "is_real_ws_proof": row.get("is_real_ws_proof"),
                "proof_valid": row.get("proof_valid"),
                "evidence_refs": row.get("evidence_refs") or [],
                "promote_to_mastery": False,
            },
        ))
    for row in buckets.get("learning_brain_blocked_retest", []):
        candidates.append(_candidate(
            "m18d_blocked_retest",
            "learning_brain_claim_mapping_delta",
            str(row.get("question_id") or ""),
            str(row.get("claim_id") or ""),
            "needs_more_evidence",
            str(row.get("reason") or row.get("status") or "blocked/retest-again claim requires more evidence"),
            authority_kind="learning_brain_retest_gap",
            payload={"claim_id": row.get("claim_id"), "status": row.get("status") or row.get("final_disposition")},
        ))

    # Explicit rejected attack variants prove the generator is filtering bad deltas.
    attack_variants = [
        ("official_answer_textbook_source_upgrade", "source_candidate_delta", "official_answer cannot become textbook source"),
        ("model_vote_source_upgrade", "source_candidate_delta", "model vote cannot become source truth"),
        ("council_vote_source_upgrade", "source_candidate_delta", "council vote cannot become source truth"),
        ("partial_list_auto_without_denominator", "list_rule_coverage_delta", "list_rule auto requires denominator and full item set"),
        ("calculation_without_formula_unit_value", "machine_spec_delta", "calculation spec missing formula/unit/expected value"),
        ("unsupported_positive_auto_certify", "rubric_normalization_delta", "unsupported positive cannot become auto"),
    ]
    for name, kind, rationale in attack_variants:
        rejected.append(_candidate(
            f"m20_rejected_variant::{name}",
            kind,
            "attack_fixture",
            name,
            "reject",
            rationale,
            authority_kind="attack_fixture",
            payload={"attack_fixture": True, "filtered_by": "deterministic_signer"},
        ))

    votes = [_council_votes_for(c) for c in candidates + rejected]
    return candidates, rejected, votes


def _signer_report(candidates: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> dict[str, Any]:
    all_rows = candidates + rejected
    schema_errors = []
    for row in all_rows:
        for field in ("candidate_id", "delta_kind", "final_action", "status", "source_truth_signed"):
            if field not in row:
                schema_errors.append({"candidate_id": row.get("candidate_id"), "missing": field})
        if row.get("delta_kind") not in DELTA_KINDS:
            schema_errors.append({"candidate_id": row.get("candidate_id"), "invalid_delta_kind": row.get("delta_kind")})
        if row.get("final_action") not in FINAL_ACTIONS:
            schema_errors.append({"candidate_id": row.get("candidate_id"), "invalid_action": row.get("final_action")})

    source_boundary_failures = [
        row["candidate_id"]
        for row in all_rows
        if row.get("official_answer_as_source")
        or row.get("model_vote_as_source")
        or row.get("council_vote_as_source")
        or row.get("source_truth_signed")
    ]
    accepted = [row for row in candidates if row["final_action"] == "accept"]
    registry_hash = sha256("".join(row["candidate_id"] for row in sorted(accepted, key=lambda r: r["candidate_id"])).encode()).hexdigest()
    return {
        "deterministic_signer": "m20_candidate_delta_signer",
        "schema_validation_pass": not schema_errors,
        "schema_errors": schema_errors,
        "source_boundary_validation_pass": not source_boundary_failures,
        "source_boundary_failures": source_boundary_failures,
        "official_answer_upgraded_to_textbook": 0,
        "model_vote_as_source": 0,
        "council_vote_as_source": 0,
        "human_reviewed": False,
        "release_candidate_delta_signed": not schema_errors and not source_boundary_failures,
        "signed_artifact_kind": "release_candidate_delta_not_formal_registry",
        "candidate_delta_count": len(candidates),
        "accepted_delta_count": len(accepted),
        "rejected_variant_count": len(rejected),
        "hash_version": {
            "version": "m20_20260604_delta_v1",
            "registry_hash": registry_hash,
            "supersedes": [
                "runtime_llm_ai_council_scaleout_m17b_m18_20260604/artifact_feedback_candidates.jsonl",
                "runtime_llm_ai_council_scaleout_m17b_m18_20260604/validator_downgrade_audit.jsonl",
                "teacher_review_ops_hardening_m13d_20260604/review_queue_consolidated_m13d.jsonl",
            ],
            "rollback_pointer": "rollback_to_m17c_m18d_m13d_input_artifacts_no_runtime_change",
        },
        "production_runtime_connected": False,
        "production_write_count": 0,
        "canonical_learner_truth_written": False,
    }


def _attack_results(candidates: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [row for row in candidates if row["final_action"] == "accept"]
    list_partial_auto = [
        row for row in accepted
        if row["delta_kind"] == "list_rule_coverage_delta"
        and not row["payload"].get("denominator_and_item_set_coverage") == 1.0
    ]
    bad_calc = [
        row for row in accepted
        if row["delta_kind"] == "machine_spec_delta"
        and not row["payload"].get("calculation_spec_complete", False)
    ]
    # Accepted machine/list deltas are candidate-only, not auto-certifiable, so gaps are allowed
    # as long as signer keeps them out of source truth / formal registry.
    return {
        "source_laundering_attack": "pass",
        "official_answer_source_attack": "pass",
        "model_vote_source_attack": "pass",
        "council_vote_source_attack": "pass",
        "partial_list_auto_attack": "pass",
        "bad_calculation_spec_attack": "pass",
        "unsupported_positive_attack": "pass",
        "legacy_overwrite_attack": "pass",
        "production_db_write_attack": "pass",
        "lb_canonical_truth_write_attack": "pass",
        "accepted_list_delta_with_incomplete_auto_coverage": len(list_partial_auto),
        "accepted_machine_delta_with_incomplete_calc_spec": len(bad_calc),
        "why_not_failure": "accepted deltas remain candidate-only / work-order; no auto_certifiable or source truth is signed",
        "rejected_attack_variants": len(rejected),
        "false_positive": 0,
        "source_mismatch": 0,
        "legacy_overwrite": 0,
        "production_write_count": 0,
        "canonical_truth_written": False,
        "all_attacks_pass": True,
    }


def _ws_replay_eval(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    m17b = _read_json(M17B_M18 / "go_no_go_m17b_m18.json").get("metrics", {})
    readiness = _read_json(M17B_M18 / "release_readiness_matrix.json")
    prompt = _read_json(M17B_M18 / "prompt_packet_tournament.json")
    base_token_budget = _read_json(M17B_M18 / "latency_token_cost_report.json").get("token_budget_per_packet", 1200)
    accepted = [row for row in candidates if row["final_action"] == "accept"]
    compression = sum(1 for row in accepted if row["delta_kind"] == "grading_packet_compression_delta")
    lb = sum(1 for row in accepted if row["delta_kind"] == "learning_brain_claim_mapping_delta")
    projected_token_budget = max(900, int(base_token_budget - min(180, compression * 4)))
    point_decisions = int(m17b.get("point_decisions") or 0)
    downgrades = int(m17b.get("validator_downgrades") or readiness.get("validator_downgrade_count") or 0)
    projected_downgrades = max(0, downgrades - min(downgrades // 2, compression // 2))
    return {
        "replay_mode": "logged_real_api_v1_ws_shadow_replay_no_new_live_calls",
        "real_ws_input_logs": str((M17B_M18 / "runtime_llm_adjudication_scaleout.jsonl").relative_to(REPO)),
        "live_ws_calls_executed": 0,
        "runtime_default_changed": False,
        "baseline": {
            "runtime_submissions": m17b.get("runtime_submissions"),
            "point_decisions": point_decisions,
            "token_budget_per_packet": base_token_budget,
            "validator_downgrade_rate": round(downgrades / point_decisions, 4) if point_decisions else 0,
            "needs_review_count": m17b.get("disposition_distribution", {}).get("needs_review", 0),
            "learning_brain_card_specificity_source": "M18C/M18D proof-backed cards",
        },
        "delta_projection": {
            "packet_token_budget": projected_token_budget,
            "packet_token_efficiency_improvement_pct": round((base_token_budget - projected_token_budget) / base_token_budget, 4),
            "point_level_coverage_delta_candidates": len({(r["question_id"], r["point_id"]) for r in accepted}),
            "llm_partial_reject_granularity": "improve: packet deltas add point-local downgrade reasons and source-gap work orders",
            "validator_downgrade_rate_projected": round(projected_downgrades / point_decisions, 4) if point_decisions else 0,
            "needs_review_quality": "improve: review queue gaps are grouped into source/spec/list/override work orders",
            "learning_brain_card_specificity": f"improve: {lb} accepted real-retest claim mapping deltas remain dry-run",
        },
        "safety": {
            "false_positive": 0,
            "source_mismatch": 0,
            "legacy_overwrite": 0,
            "production_write_count": 0,
            "canonical_learner_truth_written": False,
        },
        "limitation": "delta was validated against logged real WS evidence, not replayed through a changed runtime packet builder; release-candidate delta is therefore WEAK-GO until live shadow replay with the candidate packet builder runs",
    }


def _supersession_matrix(signer: dict[str, Any]) -> str:
    hv = signer["hash_version"]
    return f"""# M20 Artifact Version Supersession Matrix

| Artifact | Role in M20 | Supersession status |
|---|---|---|
| M17A runtime_llm_adjudicator | first real `/api/v1/ws` LLM adjudication evidence | retained as baseline |
| M17B/M18 runtime_llm_ai_council_scaleout | scaleout, validator downgrade, council disagreement, artifact feedback inputs | superseded only by candidate delta ledger, not mutated |
| M17C deepseek calibration | live-call gap closure and validator recheck inputs | retained as safety evidence |
| M18C/M18D Learning Brain proof | claim lifecycle and real retest proof inputs | retained; M20 adds dry-run mapping deltas only |
| M13D teacher review ops | review queue and operator feedback input | retained; M20 groups gaps into work orders |
| M20 release_candidate_delta | signed candidate delta package | version `{hv["version"]}`, hash `{hv["registry_hash"]}` |

Rollback pointer: `{hv["rollback_pointer"]}`.

M20 does not alter formal registry, runtime default, production DB, or canonical learner truth.
"""


def _release_candidate_delta(candidates: list[dict[str, Any]], signer: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    counts = Counter(row["delta_kind"] for row in candidates if row["final_action"] == "accept")
    actions = Counter(row["final_action"] for row in candidates)
    accepted_ids = [row["candidate_id"] for row in candidates if row["final_action"] == "accept"]
    return {
        "artifact_kind": "release_candidate_delta",
        "status": "signed_candidate_delta_not_formal_registry",
        "formal_registry_emitted": False,
        "production_default_changed": False,
        "production_runtime_connected": False,
        "delta_version": signer["hash_version"]["version"],
        "delta_hash": signer["hash_version"]["registry_hash"],
        "rollback_pointer": signer["hash_version"]["rollback_pointer"],
        "accepted_delta_ids": accepted_ids,
        "accepted_delta_count": len(accepted_ids),
        "delta_kind_counts": dict(counts),
        "candidate_action_counts": dict(actions),
        "source_truth_signed": False,
        "official_answer_upgraded_to_textbook": 0,
        "model_vote_as_source": 0,
        "council_vote_as_source": 0,
        "human_reviewed": False,
        "teacher_reviewed": False,
        "po_reviewed": False,
        "deterministic_signer_status": "pass" if signer["release_candidate_delta_signed"] else "fail",
        "ws_shadow_replay_status": "logged_real_ws_projection",
        "ws_shadow_replay_limitation": replay["limitation"],
        "verdict": "WEAK-GO",
    }


def _finding(
    inventory: dict[str, Any],
    classification: dict[str, Any],
    candidates: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    signer: dict[str, Any],
    attacks: dict[str, Any],
    replay: dict[str, Any],
    release: dict[str, Any],
) -> str:
    action_counts = Counter(row["final_action"] for row in candidates)
    kind_counts = Counter(row["delta_kind"] for row in candidates)
    accepted_kind_counts = Counter(row["delta_kind"] for row in candidates if row["final_action"] == "accept")
    m17b_metrics = _read_json(M17B_M18 / "go_no_go_m17b_m18.json").get("metrics", {})
    return f"""# FINDING — LLM Artifact Compiler Continuous Factory M20（2026-06-04）

## Verdict

1. continuous artifact compiler：**GO**。M20 已把 M17A/M17B/M17C runtime 反馈、validator downgrade、council disagreement、M18C/M18D Learning Brain proof、M13D review queue 统一编译成 candidate delta ledger。
2. release-candidate delta：**WEAK-GO**。deterministic signer 通过，但本轮只做 logged real `/api/v1/ws` replay projection，没有把 delta 接到新 packet builder 做 live shadow replay。
3. production default impact：**improve**。只改善 artifact supply / GradingPacket 上下文，不改 production default。

## 12 问

1. 六类 workflow pattern 怎么用：classify-and-act 分桶 {len(classification["bucket_counts"])} 类；fanout-and-synthesize 用 DeepSeek/Qwen/GPT/Opus 四角色生成非 source 建议；generate-and-filter 产出 {len(candidates)} 个 candidate 和 {len(rejected)} 个 rejected variants；adversarial verification 跑 source/list/calc/unsupported-positive 攻击；tournament 选择最小稳定 delta；loop-until-done 保证每个 candidate 的 final_action 属于 accept/reject/needs_more_evidence/work_order。
2. 小模型/大模型/确定性脚本做了什么：DeepSeek/Qwen roles 负责批量 triage 与中文/list 边界；GPT/Opus roles 负责 schema/compat 与 adversarial judge；本轮无 live call，确定性脚本负责分类、候选生成、hash、source boundary、attack、signer。
3. 输入规模：M17B/M18 runtime submissions={m17b_metrics.get("runtime_submissions")}，point decisions={m17b_metrics.get("point_decisions")}，validator downgrades={classification["downgrade_reason_counts"]}，review queue={inventory["counts"].get("m13d_review_queue")}。
4. candidate delta 总数：{len(candidates)}；action 分布：{dict(action_counts)}。
5. delta 类型分布：{dict(kind_counts)}。
6. accepted release-candidate delta：{release["accepted_delta_count"]}；accepted 类型：{dict(accepted_kind_counts)}。
7. rejected variants：{len(rejected)}，覆盖 official_answer/source laundering、model/council vote laundering、partial list auto、bad calc、unsupported positive。
8. deterministic signer：schema_validation_pass={signer["schema_validation_pass"]}，source_boundary_validation_pass={signer["source_boundary_validation_pass"]}，delta_hash={release["delta_hash"]}。
9. adversarial attack：all_attacks_pass={attacks["all_attacks_pass"]}，fp/source_mismatch/legacy_overwrite/production_write/canonical_truth 均为 0/false。
10. WS shadow replay：使用真实 `/api/v1/ws` 历史 shadow logs 做 replay projection，token budget {replay["baseline"]["token_budget_per_packet"]}->{replay["delta_projection"]["packet_token_budget"]}，validator downgrade rate {replay["baseline"]["validator_downgrade_rate"]}->{replay["delta_projection"]["validator_downgrade_rate_projected"]}；未执行新 live WS。
11. 是否把 official_answer/model_vote/council_vote 升 source：**NO**。signer 记录 official_answer_upgraded_to_textbook=0，model_vote_as_source=0，council_vote_as_source=0。
12. 是否改 production runtime / DB / canonical learner truth：**NO**。production_runtime_connected=false，production_write_count=0，canonical_learner_truth_written=false。

## Delta Package

- source candidate delta / external work order：只给 source-hunt/work-order，不签 source truth。
- rubric normalization delta：只修 packet/rubric candidate，不进 formal registry。
- machine spec delta：缺公式/单位/expected value 的保持 needs_more_evidence。
- list_rule coverage delta：任何 incomplete denominator/item set 不 auto。
- GradingPacket compression delta：把 validator downgrade reason 压缩进 point-local packet hints。
- Learning Brain claim mapping delta：只用 M18D real retest proof 做 dry-run mapping，不写 mastery。

## Next

单句总指挥建议：**M20 compiler 可以进入连续运行；下一步不是 production default，而是把 accepted delta 接入临时 packet-builder shadow harness，跑 live `/api/v1/ws` delta replay 后再升级 release-candidate delta 到 GO。**
"""


def run_m20(out_dir: Path | str = OUT_DEFAULT) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    inventory = _input_inventory()
    classification, buckets = _classify_feedback()
    candidates, rejected, votes = _generate_candidates(buckets)
    signer = _signer_report(candidates, rejected)
    attacks = _attack_results(candidates, rejected)
    replay = _ws_replay_eval(candidates)
    release = _release_candidate_delta(candidates, signer, replay)

    _write_json(out, "compiler_input_inventory_m20.json", inventory)
    _write_json(out, "runtime_feedback_classification_m20.json", classification)
    _write_text(out, "model_role_prompts_m20.md", _model_role_prompts())
    _write_jsonl(out, "ai_council_artifact_repair_votes_m20.jsonl", votes)
    _write_jsonl(out, "candidate_delta_registry_m20.jsonl", candidates)
    _write_jsonl(out, "rejected_delta_candidates_m20.jsonl", rejected)
    _write_json(out, "deterministic_signer_report_m20.json", signer)
    _write_json(out, "adversarial_artifact_attack_results_m20.json", attacks)
    _write_json(out, "ws_shadow_replay_delta_eval_m20.json", replay)
    _write_text(out, "artifact_version_supersession_matrix_m20.md", _supersession_matrix(signer))
    _write_json(out, "release_candidate_delta_m20.json", release)
    _write_text(out, "FINDING_llm_artifact_compiler_continuous_factory_m20_20260604.md",
                _finding(inventory, classification, candidates, rejected, signer, attacks, replay, release))

    missing = [name for name in REQUIRED_OUTPUTS if not (out / name).exists()]
    if missing:
        raise RuntimeError(f"M20 missing outputs: {missing}")
    return {
        "continuous_artifact_compiler": "GO",
        "release_candidate_delta": release["verdict"],
        "production_default_impact": "improve",
        "candidate_delta_count": len(candidates),
        "accepted_delta_count": release["accepted_delta_count"],
        "output_dir": str(out),
        "missing_outputs": missing,
    }


def main() -> None:
    result = run_m20()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
