#!/usr/bin/env python3
"""Build an unsigned L5 authorization package for KnowQL/Nexus/GBrain.

This is a local review artifact only. It prepares the exact forms a human or
governance owner would sign later, but it never records a signature and never
grants write, publish, env mutation, or remote authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_L4_READINESS = (
    REPO
    / "artifacts/luban_grading_artifacts/knowql_nexus_l4_1_authorization_readiness_20260615T152027Z"
    / "authorization_readiness.json"
)
DEFAULT_PRODUCTION_DEFAULT_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/knowql_nexus_l4_1_authorization_readiness_20260615T152027Z"
    / "l5_production_default_gate.json"
)
DEFAULT_CANONICAL_TRUTH_GATE = (
    REPO
    / "artifacts/luban_grading_artifacts/knowql_nexus_l4_1_authorization_readiness_20260615T152027Z"
    / "l5_canonical_truth_gate.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/knowql_nexus_l5_signed_authorization_package_unsigned"
    / "signed_authorization_package.json"
)
DEFAULT_MARKDOWN_OUTPUT = DEFAULT_OUTPUT.with_suffix(".md")
SCHEMA = "knowql_nexus_l5_signed_authorization_package.v1"
PRODUCTION_AUTHORIZATION_SCHEMA = "knowql_nexus_l5_production_default_authorization.v1"
CANONICAL_AUTHORIZATION_SCHEMA = "knowql_nexus_l5_canonical_truth_authorization.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _content_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safety_blockers(*, l4_readiness: dict[str, Any], production_default_gate: dict[str, Any], canonical_truth_gate: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if l4_readiness.get("schema") != "knowql_nexus_l4_authorization_readiness.v1":
        blockers.append(f"l4_readiness_schema_mismatch:{l4_readiness.get('schema')}")
    if production_default_gate.get("schema") != "knowql_nexus_l5_production_default_gate.v1":
        blockers.append(f"production_default_gate_schema_mismatch:{production_default_gate.get('schema')}")
    if canonical_truth_gate.get("schema") != "knowql_nexus_l5_canonical_truth_gate.v1":
        blockers.append(f"canonical_truth_gate_schema_mismatch:{canonical_truth_gate.get('schema')}")
    if l4_readiness.get("live_readback_status") != "L4_LIVE_READBACK_READY":
        blockers.append("l4_live_readback_not_ready")
    production_blockers = set(l4_readiness.get("production_blockers") or [])
    for blocker in ("stage5_human_gold_over_credit_blocker", "stage5_canary_not_ready"):
        if blocker in production_blockers:
            blockers.append(blocker)
    for source_name, summary in (
        ("l4", _as_dict(l4_readiness, "summary")),
        ("production_default_gate", _as_dict(production_default_gate, "safety")),
        ("canonical_truth_gate", _as_dict(canonical_truth_gate, "safety")),
    ):
        for field in (
            "production_write_count",
            "official_score_write_count",
            "canonical_truth_write_count",
            "learner_memory_write_count",
            "remote_write_count",
        ):
            if _to_int(summary.get(field)) != 0:
                blockers.append(f"{source_name}_{field}_nonzero")
    return sorted(set(blockers))


def _production_default_form(*, l4_readiness: dict[str, Any], production_default_gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": PRODUCTION_AUTHORIZATION_SCHEMA,
        "form_status": "unsigned",
        "authorization_decision": {
            "signed_authorization": False,
            "production_default_authorized": False,
            "rollback_kill_switch_verified": False,
            "published_registry_authorized": False,
            "official_score_authorized": False,
            "env_mutation_authorized": False,
            "remote_write_authorized": False,
        },
        "required_signer_roles": [
            "product_owner",
            "grading_quality_owner",
            "release_owner",
        ],
        "evidence_binding": {
            "l4_readiness_sha256": _content_hash(l4_readiness),
            "production_default_gate_sha256": _content_hash(production_default_gate),
        },
        "scope": {
            "allowed_initial_scope_after_signature": "explicitly_named_cohort_only",
            "broad_default_after_signature": False,
            "official_score_after_signature": False,
            "published_registry_after_signature": False,
        },
    }


def _canonical_truth_form(*, l4_readiness: dict[str, Any], canonical_truth_gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": CANONICAL_AUTHORIZATION_SCHEMA,
        "form_status": "unsigned",
        "authorization_decision": {
            "signed_authorization": False,
            "canonical_truth_authorized": False,
            "teacher_final_or_certified_policy_verified": False,
            "same_point_real_retest_verified": False,
            "stable_learner_claim_verified": False,
            "claim_id_readback_verified": False,
            "learner_memory_event_write_authorized": False,
            "read_model_write_authorized": False,
            "remote_write_authorized": False,
        },
        "required_signer_roles": [
            "learning_brain_owner",
            "grading_quality_owner",
            "privacy_or_data_governance_owner",
        ],
        "evidence_binding": {
            "l4_readiness_sha256": _content_hash(l4_readiness),
            "canonical_truth_gate_sha256": _content_hash(canonical_truth_gate),
        },
        "scope": {
            "allowed_initial_scope_after_signature": "same_point_verified_retest_claim_only",
            "preview_or_simulated_evidence_allowed": False,
            "broad_learner_profile_promotion_after_signature": False,
        },
    }


def build_signed_authorization_package(
    *,
    l4_readiness: dict[str, Any],
    production_default_gate: dict[str, Any],
    canonical_truth_gate: dict[str, Any],
) -> dict[str, Any]:
    blockers = _safety_blockers(
        l4_readiness=l4_readiness,
        production_default_gate=production_default_gate,
        canonical_truth_gate=canonical_truth_gate,
    )
    verdict = "BLOCKED_BEFORE_SIGNATURE" if blockers else "READY_FOR_HUMAN_SIGNATURE"
    production_form = _production_default_form(
        l4_readiness=l4_readiness,
        production_default_gate=production_default_gate,
    )
    canonical_form = _canonical_truth_form(
        l4_readiness=l4_readiness,
        canonical_truth_gate=canonical_truth_gate,
    )
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "blockers": blockers,
        "authorization_forms": {
            "production_default": production_form,
            "canonical_truth": canonical_form,
        },
        "source_binding": {
            "l4_readiness_sha256": _content_hash(l4_readiness),
            "production_default_gate_sha256": _content_hash(production_default_gate),
            "canonical_truth_gate_sha256": _content_hash(canonical_truth_gate),
            "source_manifest": l4_readiness.get("source_manifest") or {},
            "deployment_probe": l4_readiness.get("deployment_probe") or {},
        },
        "blocked_actions": [
            "production_default_flip",
            "env_mutation",
            "official_score_write",
            "published_registry_write",
            "canonical_truth_write",
            "learner_memory_event_write",
            "read_model_write",
            "remote_write",
        ],
        "not_exercised": [
            "signature_capture",
            "production_default_flip",
            "canonical_truth_write",
            "env_mutation",
            "remote_write",
            "db_write",
            "publish",
        ],
        "safety": {
            "production_write_count": 0,
            "official_score_write_count": 0,
            "canonical_truth_write_count": 0,
            "learner_memory_write_count": 0,
            "remote_write_count": 0,
        },
        "classification": {
            "authorization_package_only": True,
            "unsigned": True,
            "no_write": True,
            "production_authorized": False,
            "canonical_truth_authorized": False,
        },
    }


def render_markdown(package: dict[str, Any]) -> str:
    production = _as_dict(_as_dict(package, "authorization_forms"), "production_default")
    canonical = _as_dict(_as_dict(package, "authorization_forms"), "canonical_truth")
    production_decision = _as_dict(production, "authorization_decision")
    canonical_decision = _as_dict(canonical, "authorization_decision")
    blockers = package.get("blockers") or []
    blocker_lines = "\n".join(f"- {blocker}" for blocker in blockers) if blockers else "- none"
    return (
        "# KnowQL/Nexus/GBrain L5 Signed Authorization Package\n\n"
        f"verdict={package.get('verdict')}\n\n"
        "## Blockers\n"
        f"{blocker_lines}\n\n"
        "## Production Default Form\n"
        f"- signed_authorization={str(production_decision.get('signed_authorization')).lower()}\n"
        f"- production_default_authorized={str(production_decision.get('production_default_authorized')).lower()}\n"
        f"- published_registry_authorized={str(production_decision.get('published_registry_authorized')).lower()}\n"
        f"- official_score_authorized={str(production_decision.get('official_score_authorized')).lower()}\n"
        f"- remote_write_authorized={str(production_decision.get('remote_write_authorized')).lower()}\n\n"
        "## Canonical Truth Form\n"
        f"- signed_authorization={str(canonical_decision.get('signed_authorization')).lower()}\n"
        f"- canonical_truth_authorized={str(canonical_decision.get('canonical_truth_authorized')).lower()}\n"
        f"- learner_memory_event_write_authorized={str(canonical_decision.get('learner_memory_event_write_authorized')).lower()}\n"
        f"- read_model_write_authorized={str(canonical_decision.get('read_model_write_authorized')).lower()}\n"
        f"- remote_write_authorized={str(canonical_decision.get('remote_write_authorized')).lower()}\n\n"
        "## No-Write Attestation\n"
        "- env mutation=false\n"
        "- db write=false\n"
        "- publish=false\n"
        "- remote write=false\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l4-readiness", type=Path, default=DEFAULT_L4_READINESS)
    parser.add_argument("--production-default-gate", type=Path, default=DEFAULT_PRODUCTION_DEFAULT_GATE)
    parser.add_argument("--canonical-truth-gate", type=Path, default=DEFAULT_CANONICAL_TRUTH_GATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    args = parser.parse_args(argv)
    package = build_signed_authorization_package(
        l4_readiness=_read_json(args.l4_readiness),
        production_default_gate=_read_json(args.production_default_gate),
        canonical_truth_gate=_read_json(args.canonical_truth_gate),
    )
    _write_text(args.output, json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text(args.markdown_output, render_markdown(package))
    print(
        json.dumps(
            {
                "out": str(args.output),
                "markdown": str(args.markdown_output),
                "verdict": package["verdict"],
                "blockers": package["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
