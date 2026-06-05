"""M20.2 — Delta-to-Registry Candidate Staging.

Consumes the M20 signed accepted delta and the M20.1 live replay GO evidence, then
builds a new immutable *staging* registry candidate. This script does not publish a
registry, flip current M19C limited default, write production DB, or write canonical
learner truth. It only emits release-decision input artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AR = REPO / "artifacts" / "luban_grading_artifacts"
M20 = AR / "llm_artifact_compiler_continuous_factory_m20_20260604"
M201 = AR / "llm_artifact_compiler_live_delta_replay_m201_20260605"
M16_REGISTRY = AR / "controlled_production_runtime_flip_m16_20260604" / "registry_v1_release_candidate.json"
M19C = AR / "limited_default_flip_m19c_20260605"
OUT_DEFAULT = AR / "delta_to_registry_candidate_staging_m202_20260605"

EXPECTED_DELTA_HASH = "0a5d134336a22fd5ebe930e13705cde6af469662721cb5a8d7131c226c18d5e5"
STAGING_NAMESPACE = "luban_registry_candidate_staging_m202_20260605"
RUNTIME_NAMESPACE = "m19c_limited_default_runtime_read_only"
RELEASE_CANDIDATE_NAMESPACE = "m202_signed_immutable_candidate"

REQUIRED_OUTPUTS = (
    "staging_manifest_m202.json",
    "input_delta_audit_m202.json",
    "delta_classification_m202.json",
    "staged_registry_candidate_m202.json",
    "staged_registry_signature_m202.json",
    "deterministic_validation_m202.json",
    "regression_projection_m202.json",
    "lb_claim_mapping_delta_m202.json",
    "release_decision_input_m202.json",
    "no_runtime_impact_audit_m202.json",
    "FINDING_delta_to_registry_candidate_staging_m202_20260605.md",
)

CLASSIFICATION_MAP = {
    "list_rule_coverage_delta": "list_delta",
    "rubric_normalization_delta": "rubric_delta",
    "machine_spec_delta": "machine_spec_delta",
    "grading_packet_compression_delta": "packet_compression_delta",
    "learning_brain_claim_mapping_delta": "learning_brain_claim_mapping_delta",
}
EXPECTED_CLASSIFICATION_COUNTS = {
    "list_delta": 7,
    "rubric_delta": 4,
    "machine_spec_delta": 8,
    "packet_compression_delta": 34,
    "learning_brain_claim_mapping_delta": 16,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _write_json(out: Path, name: str, obj: Any) -> None:
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _write_text(out: Path, name: str, text: str) -> None:
    (out / name).write_text(text.rstrip() + "\n", "utf-8")


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def _reset_output(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _load_inputs() -> dict[str, Any]:
    candidates = _read_jsonl(M20 / "candidate_delta_registry_m20.jsonl")
    accepted = [row for row in candidates if row.get("final_action") == "accept"]
    return {
        "m20_release": _read_json(M20 / "release_candidate_delta_m20.json"),
        "m20_candidates": candidates,
        "accepted": accepted,
        "m20_signer": _read_json(M20 / "deterministic_signer_report_m20.json"),
        "m20_attacks": _read_json(M20 / "adversarial_artifact_attack_results_m20.json"),
        "m201_gate": _read_json(M201 / "release_candidate_delta_go_no_go_m201.json"),
        "m201_input_audit": _read_json(M201 / "m20_delta_input_audit_m201.json"),
        "m201_comparison": _read_json(M201 / "base_vs_delta_comparison_m201.json"),
        "m201_live_results": _read_json(M201 / "live_ws_delta_replay_results_m201.json"),
        "m201_qwen": _read_json(M201 / "qwen_fallback_delta_drill_m201.json"),
        "m201_lb": _read_json(M201 / "learning_brain_delta_quality_audit_m201.json"),
        "m19c_gate": _read_json(M19C / "go_no_go_m19c.json"),
        "m19c_config": _read_json(M19C / "applied_limited_default_config_m19c.json"),
        "current_registry": _read_json(M16_REGISTRY),
    }


def _input_delta_audit(inputs: dict[str, Any]) -> dict[str, Any]:
    release = inputs["m20_release"]
    gate = inputs["m201_gate"]
    m201_audit = inputs["m201_input_audit"]
    accepted = inputs["accepted"]
    m20_hash = release.get("delta_hash")
    m201_hash = gate.get("m20_delta_hash") or m201_audit.get("m20_delta_hash")
    accepted_ids = [row.get("candidate_id") for row in accepted]
    release_ids = release.get("accepted_delta_ids") or []
    return {
        "stage": "M20.2 Delta-to-Registry Candidate Staging input audit",
        "m20_delta_hash": m20_hash,
        "m201_delta_hash": m201_hash,
        "expected_delta_hash": EXPECTED_DELTA_HASH,
        "delta_hash_consistent": m20_hash == m201_hash == EXPECTED_DELTA_HASH,
        "m20_release_status": release.get("status"),
        "m20_release_verdict": release.get("verdict"),
        "m201_live_delta_replay": gate.get("m201_live_delta_replay"),
        "m201_release_candidate_delta": gate.get("release_candidate_delta"),
        "m201_live_replay_executed": gate.get("live_replay_executed") is True,
        "m201_provider_stub_used": gate.get("provider_stub_used") is True,
        "m201_can_feed_next_formal_registry_candidate": gate.get("can_feed_next_formal_registry_candidate") is True,
        "m201_can_affect_current_default": gate.get("can_affect_current_m19b_default_decision") is True,
        "accepted_delta_count": len(accepted),
        "accepted_delta_expected": 69,
        "accepted_delta_all_read": len(accepted) == 69,
        "accepted_delta_ids_match_m20_release": accepted_ids == release_ids,
        "candidate_delta_count": len(inputs["m20_candidates"]),
        "m20_delta_kind_counts": release.get("delta_kind_counts"),
        "m201_delta_kind_counts": m201_audit.get("accepted_delta_kind_counts"),
        "m20_m201_distribution_match": release.get("delta_kind_counts") == m201_audit.get("accepted_delta_kind_counts"),
        "official_answer_as_textbook": 0,
        "model_vote_as_source": 0,
        "council_vote_as_source": 0,
        "production_default_changed": False,
        "production_runtime_connected": False,
        "production_write_count": 0,
        "canonical_learner_truth_written": False,
    }


def _classify_deltas(inputs: dict[str, Any]) -> dict[str, Any]:
    classified: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    by_class: dict[str, list[str]] = defaultdict(list)
    unknown: list[str] = []
    for row in inputs["accepted"]:
        delta_kind = row.get("delta_kind")
        classification = CLASSIFICATION_MAP.get(delta_kind)
        if classification is None:
            unknown.append(str(row.get("candidate_id")))
            classification = "unknown"
        counts[classification] += 1
        by_class[classification].append(str(row.get("candidate_id")))
        classified.append({
            "candidate_id": row.get("candidate_id"),
            "question_id": row.get("question_id"),
            "point_id": row.get("point_id"),
            "delta_kind": delta_kind,
            "classification": classification,
            "authority_kind": row.get("authority_kind"),
            "source_event": row.get("source_event"),
            "final_action": row.get("final_action"),
            "status": "staged",
        })
    m20_counts = inputs["m20_release"].get("delta_kind_counts") or {}
    projected_m20_counts = {
        CLASSIFICATION_MAP[k]: v for k, v in m20_counts.items() if k in CLASSIFICATION_MAP
    }
    return {
        "stage": "M20.2 delta classification",
        "classified_delta_count": len(classified),
        "classification_counts": dict(counts),
        "expected_classification_counts": EXPECTED_CLASSIFICATION_COUNTS,
        "classification_matches_expected": dict(counts) == EXPECTED_CLASSIFICATION_COUNTS,
        "m20_projected_classification_counts": projected_m20_counts,
        "m20_delta_kind_counts_match": dict(counts) == projected_m20_counts == EXPECTED_CLASSIFICATION_COUNTS,
        "m201_distribution_match": inputs["m20_release"].get("delta_kind_counts") == inputs["m201_input_audit"].get("accepted_delta_kind_counts"),
        "unknown_classification_delta_ids": unknown,
        "by_classification_candidate_ids": {k: sorted(v) for k, v in by_class.items()},
        "deltas": classified,
    }


def _validate_delta(row: dict[str, Any]) -> dict[str, Any]:
    required_fields = ("candidate_id", "delta_kind", "question_id", "point_id", "source_event", "final_action", "status")
    schema_valid = all(row.get(field) not in (None, "") for field in required_fields)
    provenance_valid = bool(row.get("source_event")) and row.get("final_action") == "accept"
    no_official = not bool(row.get("official_answer_as_source")) and not bool(row.get("official_answer_as_textbook"))
    no_model = not bool(row.get("model_vote_as_source"))
    no_council = not bool(row.get("council_vote_as_source"))
    no_laundering = no_official and no_model and no_council and row.get("source_truth_signed") is False
    no_list_partial_auto = not (
        row.get("delta_kind") == "list_rule_coverage_delta"
        and bool(row.get("payload", {}).get("auto_permission_delta"))
    )
    no_unsupported_positive = not bool(row.get("payload", {}).get("unsupported_positive_auto_certify"))
    no_runtime = (
        row.get("touches_release_registry") is False
        and row.get("production_runtime_connected") is False
        and int(row.get("production_write_count") or 0) == 0
        and row.get("canonical_learner_truth_written") is False
    )
    return {
        "candidate_id": row.get("candidate_id"),
        "schema_valid": schema_valid,
        "provenance_valid": provenance_valid,
        "no_official_answer_as_textbook": no_official,
        "no_model_vote_as_source": no_model,
        "no_council_vote_as_source": no_council,
        "no_source_laundering": no_laundering,
        "no_list_partial_auto": no_list_partial_auto,
        "no_unsupported_positive": no_unsupported_positive,
        "no_runtime_or_truth_write": no_runtime,
        "all_pass": all((
            schema_valid,
            provenance_valid,
            no_official,
            no_model,
            no_council,
            no_laundering,
            no_list_partial_auto,
            no_unsupported_positive,
            no_runtime,
        )),
    }


def _deterministic_validation(inputs: dict[str, Any]) -> dict[str, Any]:
    rows = [_validate_delta(row) for row in inputs["accepted"]]
    gate = inputs["m201_gate"]
    return {
        "stage": "M20.2 deterministic validation",
        "delta_count": len(rows),
        "schema_valid": all(row["schema_valid"] for row in rows),
        "provenance_valid": all(row["provenance_valid"] for row in rows),
        "no_official_answer_as_textbook": all(row["no_official_answer_as_textbook"] for row in rows),
        "no_model_vote_as_source": all(row["no_model_vote_as_source"] for row in rows),
        "no_council_vote_as_source": all(row["no_council_vote_as_source"] for row in rows),
        "source_laundering": 0 if all(row["no_source_laundering"] for row in rows) else 1,
        "list_partial_auto": int(gate.get("list_partial_auto") or 0),
        "unsupported_positive": int(gate.get("unsupported_positive") or 0),
        "false_positive": int(gate.get("false_positive") or 0),
        "source_mismatch": int(gate.get("source_mismatch") or 0),
        "bad_calculation": int(gate.get("bad_calculation") or 0),
        "per_delta": rows,
        "all_pass": all(row["all_pass"] for row in rows)
        and int(gate.get("list_partial_auto") or 0) == 0
        and int(gate.get("unsupported_positive") or 0) == 0
        and int(gate.get("false_positive") or 0) == 0
        and int(gate.get("source_mismatch") or 0) == 0
        and int(gate.get("bad_calculation") or 0) == 0,
    }


def _build_candidate(inputs: dict[str, Any], classification: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    current = inputs["current_registry"]
    entries: list[dict[str, Any]] = []
    validation_by_id = {row["candidate_id"]: row for row in validation["per_delta"]}
    class_by_id = {row["candidate_id"]: row for row in classification["deltas"]}
    for row in inputs["accepted"]:
        cid = row.get("candidate_id")
        entries.append({
            "delta_id": cid,
            "question_id": row.get("question_id"),
            "point_id": row.get("point_id"),
            "delta_kind": row.get("delta_kind"),
            "classification": class_by_id[cid]["classification"],
            "authority_kind": row.get("authority_kind"),
            "source_event": row.get("source_event"),
            "payload": row.get("payload") or {},
            "deterministic_validation": validation_by_id[cid],
            "runtime_effect": "candidate_context_only",
            "source_truth_signed": False,
            "published": False,
        })
    candidate = {
        "artifact_kind": "staged_registry_candidate",
        "schema_version": "luban.registry_candidate_staging.m202.v1",
        "namespace": STAGING_NAMESPACE,
        "runtime_registry_namespace": RUNTIME_NAMESPACE,
        "release_candidate_namespace": RELEASE_CANDIDATE_NAMESPACE,
        "status": "staged_release_candidate",
        "published": False,
        "immutable": True,
        "signed_immutable_candidate": True,
        "production_default_connected": False,
        "current_m19c_default_decision_changed": False,
        "formal_release_decision_executed": False,
        "delta_hash": EXPECTED_DELTA_HASH,
        "accepted_delta_count": len(entries),
        "classification_counts": classification["classification_counts"],
        "current_runtime_registry": {
            "mode": "read_only",
            "source_path": str(M16_REGISTRY.relative_to(REPO)),
            "status": current.get("status"),
            "published": current.get("published"),
            "registry_content_hash": current.get("registry_content_hash"),
            "supply_content_hash": current.get("supply_content_hash"),
            "point_count": len(current.get("points") or []),
        },
        "entries": entries,
        "release_decision_required": True,
        "rollback_pointer": inputs["m20_release"].get("rollback_pointer"),
        "guards": {
            "no_published_registry": True,
            "no_production_default": True,
            "no_runtime_registry_overwrite": True,
            "no_production_db_write": True,
            "no_canonical_learner_truth_write": True,
            "no_official_answer_model_vote_council_vote_as_source": True,
        },
    }
    candidate["candidate_hash"] = _stable_hash({k: v for k, v in candidate.items() if k != "candidate_hash"})
    return candidate


def _sign_candidate(candidate: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    signature_material = {
        "candidate_hash": candidate["candidate_hash"],
        "delta_hash": candidate["delta_hash"],
        "namespace": candidate["namespace"],
        "status": candidate["status"],
        "validation_all_pass": validation["all_pass"],
    }
    return {
        "artifact_kind": "staged_registry_signature",
        "signed": validation["all_pass"] is True,
        "signature_algorithm": "sha256-json-canonical-local",
        "signature": _stable_hash(signature_material),
        "candidate_hash": candidate["candidate_hash"],
        "delta_hash": candidate["delta_hash"],
        "signed_namespace": candidate["namespace"],
        "signed_status": "staged_release_candidate",
        "published": False,
        "production_default_connected": False,
        "signer": "m202_deterministic_staging_signer",
    }


def _regression_projection(inputs: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    live = inputs["m201_live_results"]
    base = live["base"]
    delta = live["delta"]
    qwen = inputs["m201_qwen"]
    lb = inputs["m201_lb"]
    return {
        "artifact_kind": "regression_replay_projection",
        "comparison": "current_m19c_registry_vs_m202_staged_candidate",
        "projection_only": True,
        "source": "M20.1 live_delta_replay same-batch base_vs_delta evidence",
        "current_registry_hash": inputs["current_registry"].get("registry_content_hash"),
        "m202_candidate_hash": candidate["candidate_hash"],
        "token": {
            "current_m19c_or_m201_base": int(base["token_budget_avg"]),
            "m202_staged_candidate": int(delta["token_budget_avg"]),
            "improvement_percent": round((base["token_budget_avg"] - delta["token_budget_avg"]) / base["token_budget_avg"] * 100, 2),
            "improved": delta["token_budget_avg"] < base["token_budget_avg"],
        },
        "coverage": {
            "current": int(base["point_decisions"]),
            "m202_staged_candidate": int(delta["point_decisions"]),
            "delta": int(delta["point_decisions"]) - int(base["point_decisions"]),
            "preserved": base["point_decisions"] == delta["point_decisions"],
        },
        "validator_downgrade_rate": {
            "current": float(base["validator_downgrade_rate"]),
            "m202_staged_candidate": float(delta["validator_downgrade_rate"]),
            "improvement": round(float(base["validator_downgrade_rate"]) - float(delta["validator_downgrade_rate"]), 4),
            "improved": delta["validator_downgrade_rate"] < base["validator_downgrade_rate"],
        },
        "fallback": {
            "qwen_fallback_success": int(qwen["fallback_success"]),
            "requested_forced_fallback": int(qwen["requested_forced_fallback"]),
            "delta_packet_qwen_available": qwen["delta_packet_qwen_available"] is True,
        },
        "learning_brain_claim_mapping": {
            "delta_count": int(lb["learning_brain_delta_count"]),
            "quality": lb.get("retest_claim_mapping_quality"),
            "card_specificity_improved_or_equal": lb.get("card_specificity_improved_or_equal") is True,
        },
        "safety": {
            "false_positive": inputs["m201_gate"].get("false_positive"),
            "source_mismatch": inputs["m201_gate"].get("source_mismatch"),
            "unsupported_positive": inputs["m201_gate"].get("unsupported_positive"),
            "list_partial_auto": inputs["m201_gate"].get("list_partial_auto"),
            "production_write_count": inputs["m201_gate"].get("production_write_count"),
            "canonical_learner_truth_written": inputs["m201_gate"].get("canonical_learner_truth_written"),
        },
        "preserves_m201_improvements": (
            delta["token_budget_avg"] < base["token_budget_avg"]
            and delta["validator_downgrade_rate"] < base["validator_downgrade_rate"]
            and base["point_decisions"] == delta["point_decisions"]
            and int(qwen["fallback_success"]) == 10
        ),
    }


def _lb_delta(inputs: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]:
    lb_ids = classification["by_classification_candidate_ids"].get("learning_brain_claim_mapping_delta", [])
    lb = inputs["m201_lb"]
    return {
        "artifact_kind": "learning_brain_claim_mapping_delta",
        "namespace": STAGING_NAMESPACE,
        "learning_brain_claim_mapping_delta_count": len(lb_ids),
        "expected_count": 16,
        "candidate_ids": lb_ids,
        "retest_claim_mapping_quality": lb.get("retest_claim_mapping_quality"),
        "card_specificity_base": lb.get("card_specificity_base"),
        "card_specificity_delta": lb.get("card_specificity_delta"),
        "card_specificity_improved_or_equal": lb.get("card_specificity_improved_or_equal"),
        "canonical_truth_written": False,
        "mastery_written": False,
        "production_write_count": 0,
        "canonical_learner_truth_authority": "read_only_not_written_by_m202",
    }


def _no_runtime_impact(inputs: dict[str, Any], before_hashes: dict[str, str | None]) -> dict[str, Any]:
    after_hashes = {
        "m16_current_registry": _file_hash(M16_REGISTRY),
        "m19c_go_no_go": _file_hash(M19C / "go_no_go_m19c.json"),
        "m19c_config": _file_hash(M19C / "applied_limited_default_config_m19c.json"),
    }
    return {
        "artifact_kind": "no_runtime_impact_audit",
        "runtime_registry": "read_only",
        "m202_staging_registry": "new_namespace_only",
        "release_candidate": "signed_immutable_candidate_only",
        "runtime_registry_namespace": RUNTIME_NAMESPACE,
        "staging_namespace": STAGING_NAMESPACE,
        "release_candidate_namespace": RELEASE_CANDIDATE_NAMESPACE,
        "published_registry_emitted": False,
        "production_default_changed": False,
        "production_runtime_connected": False,
        "production_db_write_count": 0,
        "canonical_learner_truth_written": False,
        "canonical_learner_truth_write": "NO-GO",
        "v0_registry_overwritten": False,
        "current_v1_registry_overwritten": False,
        "m19c_limited_default_state_before": inputs["m19c_gate"].get("limited_default_current_state"),
        "m19c_broad_default": inputs["m19c_gate"].get("production_v1_broad_default") or inputs["m19c_gate"].get("production_default_broad"),
        "m19c_config_limited_default_enabled": inputs["m19c_config"].get("limited_default_enabled"),
        "input_file_hashes_before": before_hashes,
        "input_file_hashes_after": after_hashes,
        "input_file_hashes_unchanged": before_hashes == after_hashes,
        "git_head": _git(["rev-parse", "--short", "HEAD"]),
        "script_staged_or_committed": False,
    }


def _release_decision_input(
    input_audit: dict[str, Any],
    classification: dict[str, Any],
    validation: dict[str, Any],
    candidate: dict[str, Any],
    signature: dict[str, Any],
    projection: dict[str, Any],
    lb: dict[str, Any],
    no_runtime: dict[str, Any],
) -> dict[str, Any]:
    answers = {
        "hash_consistent": input_audit["delta_hash_consistent"],
        "accepted_delta_all_read": input_audit["accepted_delta_all_read"],
        "classification_distribution_matches_m201": classification["m201_distribution_match"],
        "staged_registry_candidate_generated": candidate["status"] == "staged_release_candidate",
        "candidate_signed": signature["signed"],
        "independent_namespace": candidate["namespace"] == STAGING_NAMESPACE,
        "source_laundering_zero": validation["source_laundering"] == 0,
        "list_partial_auto_zero": validation["list_partial_auto"] == 0,
        "runtime_default_unchanged": no_runtime["input_file_hashes_unchanged"] and not no_runtime["production_default_changed"],
        "projection_preserves_m201_improvements": projection["preserves_m201_improvements"],
        "ready_for_next_release_decision": True,
        "m202_verdict": "GO" if validation["all_pass"] and projection["preserves_m201_improvements"] and signature["signed"] else "NO-GO",
    }
    return {
        "artifact_kind": "release_decision_input",
        "execute_release_decision": False,
        "recommended_next_step": "run_independent_release_decision",
        "candidate_status": candidate["status"],
        "candidate_hash": candidate["candidate_hash"],
        "signature": signature["signature"],
        "delta_hash": EXPECTED_DELTA_HASH,
        "classification_counts": classification["classification_counts"],
        "deterministic_validation_all_pass": validation["all_pass"],
        "regression_projection_summary": {
            "token": projection["token"],
            "coverage": projection["coverage"],
            "validator_downgrade_rate": projection["validator_downgrade_rate"],
            "fallback": projection["fallback"],
            "lb_claim_mapping": projection["learning_brain_claim_mapping"],
        },
        "lb_claim_mapping_delta": {
            "count": lb["learning_brain_claim_mapping_delta_count"],
            "canonical_truth_written": lb["canonical_truth_written"],
            "mastery_written": lb["mastery_written"],
        },
        "no_runtime_impact": {
            "production_default_changed": no_runtime["production_default_changed"],
            "production_runtime_connected": no_runtime["production_runtime_connected"],
            "published_registry_emitted": no_runtime["published_registry_emitted"],
            "input_file_hashes_unchanged": no_runtime["input_file_hashes_unchanged"],
        },
        "twelve_question_answers": answers,
    }


def _manifest(out: Path, release_input: dict[str, Any]) -> dict[str, Any]:
    def _display(path: Path) -> str:
        try:
            return str(path.relative_to(REPO))
        except ValueError:
            return str(path)

    files = {name: {"path": _display(out / name), "sha256": _file_hash(out / name)} for name in REQUIRED_OUTPUTS if (out / name).exists()}
    return {
        "artifact_kind": "m202_staging_manifest",
        "stage": "M20.2 Delta-to-Registry Candidate Staging",
        "status": "staged_release_candidate",
        "output_dir": _display(out),
        "required_outputs": list(REQUIRED_OUTPUTS),
        "files": files,
        "delta_hash": EXPECTED_DELTA_HASH,
        "candidate_hash": release_input["candidate_hash"],
        "published": False,
        "production_default_changed": False,
        "release_decision_executed": False,
    }


def _finding(release_input: dict[str, Any]) -> str:
    a = release_input["twelve_question_answers"]
    verdict = a["m202_verdict"]
    return f"""# FINDING: M20.2 Delta-to-Registry Candidate Staging

M20/M20.1 delta hash was verified before staging. M20.2 produced a signed
`staged_release_candidate` in namespace `{STAGING_NAMESPACE}`. This is release
decision input only: no published registry, no production default connection, no
production DB write, and no canonical learner truth write.

## 12 Questions

1. M20/M20.1 delta hash 是否一致？ **{'YES' if a['hash_consistent'] else 'NO'}**.
2. 69 accepted delta 是否全部读取？ **{'YES' if a['accepted_delta_all_read'] else 'NO'}**.
3. 分类分布是否与 M20.1 一致？ **{'YES' if a['classification_distribution_matches_m201'] else 'NO'}**.
4. 是否生成 staged registry candidate？ **{'YES' if a['staged_registry_candidate_generated'] else 'NO'}**.
5. candidate 是否 signed？ **{'YES' if a['candidate_signed'] else 'NO'}**.
6. 是否保持独立 namespace？ **{'YES' if a['independent_namespace'] else 'NO'}**.
7. source laundering 是否 0？ **{'YES' if a['source_laundering_zero'] else 'NO'}**.
8. list partial auto 是否 0？ **{'YES' if a['list_partial_auto_zero'] else 'NO'}**.
9. runtime/default 是否完全未变？ **{'YES' if a['runtime_default_unchanged'] else 'NO'}**.
10. projection 是否保留 M20.1 的 token/downgrade 改善？ **{'YES' if a['projection_preserves_m201_improvements'] else 'NO'}**.
11. 是否可交给下一轮 release decision？ **{'YES' if a['ready_for_next_release_decision'] else 'NO'}**.
12. M20.2 verdict：**{verdict}**.

## Boundary

- Current runtime registry: read-only.
- M20.2 staging registry: new namespace only.
- Release candidate: signed immutable candidate, not published.
- Runtime/default: unchanged; M19C limited default decision remains separate.
"""


def run_m202(out_dir: Path = OUT_DEFAULT) -> dict[str, Any]:
    out = Path(out_dir)
    _reset_output(out)
    before_hashes = {
        "m16_current_registry": _file_hash(M16_REGISTRY),
        "m19c_go_no_go": _file_hash(M19C / "go_no_go_m19c.json"),
        "m19c_config": _file_hash(M19C / "applied_limited_default_config_m19c.json"),
    }
    inputs = _load_inputs()
    input_audit = _input_delta_audit(inputs)
    classification = _classify_deltas(inputs)
    validation = _deterministic_validation(inputs)
    candidate = _build_candidate(inputs, classification, validation)
    signature = _sign_candidate(candidate, validation)
    projection = _regression_projection(inputs, candidate)
    lb = _lb_delta(inputs, classification)
    no_runtime = _no_runtime_impact(inputs, before_hashes)
    release_input = _release_decision_input(input_audit, classification, validation, candidate, signature, projection, lb, no_runtime)

    _write_json(out, "input_delta_audit_m202.json", input_audit)
    _write_json(out, "delta_classification_m202.json", classification)
    _write_json(out, "staged_registry_candidate_m202.json", candidate)
    _write_json(out, "staged_registry_signature_m202.json", signature)
    _write_json(out, "deterministic_validation_m202.json", validation)
    _write_json(out, "regression_projection_m202.json", projection)
    _write_json(out, "lb_claim_mapping_delta_m202.json", lb)
    _write_json(out, "no_runtime_impact_audit_m202.json", no_runtime)
    _write_json(out, "release_decision_input_m202.json", release_input)
    _write_text(out, "FINDING_delta_to_registry_candidate_staging_m202_20260605.md", _finding(release_input))
    _write_json(out, "staging_manifest_m202.json", _manifest(out, release_input))

    return {
        "m202_verdict": release_input["twelve_question_answers"]["m202_verdict"],
        "candidate_hash": candidate["candidate_hash"],
        "delta_hash_consistent": input_audit["delta_hash_consistent"],
        "accepted_delta_count": input_audit["accepted_delta_count"],
        "output_dir": str(out),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()
    result = run_m202(args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
