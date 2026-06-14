"""Build the Stage 5 PGO case-rubric runtime supply.

This module is deterministic packaging only. It consumes validated
``luban_per_question_grading_contract.v1`` objects and emits the separate
``case_rubric_scored_pgo`` bank slot that ``rubric_grader_v1`` can hash-pin.
It never mints per-point scores and never flips production default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex
from deeptutor.services.construction_grading.per_question_grading_judge import (
    runtime_points_from_grading_contract,
)
from deeptutor.services.construction_grading.per_question_grading_object import (
    A_OFFICIAL,
    GRADING_CONTRACT_SCHEMA_ID,
    PENDING_SCORE_AUTHORITY,
    validate_grading_contract,
)

SCHEMA_VERSION = "luban_case_rubric_scored_pgo.v1"
NAMESPACE = "case_rubric_scored_pgo"
STATUS = "release_candidate"
SCORE_AUTHORITY = "official_total_x_verdict_coverage"


def _record_from_runtime_point(contract: dict[str, Any], point: dict[str, Any]) -> dict[str, Any]:
    text = str(point.get("official_slice") or point.get("knowledge_point") or "")
    return {
        "qid": str(contract.get("question_id") or ""),
        "point_id": str(point.get("point_id") or ""),
        "text": text,
        "official_slice": text,
        "score": None,
        "max_score": None,
        "policy": point.get("policy_type") or "qualitative",
        "policy_type": point.get("policy_type") or "qualitative",
        "sub_type": point.get("sub_type") or "free_text_point",
        "required_terms": list(point.get("required_terms") or []),
        "term_authority": point.get("term_authority") or "none",
        "official_total_score": float(contract.get("official_total_score") or 0.0),
        "official_total_score_authority": contract.get("official_total_score_authority") or A_OFFICIAL,
        "score_authority": SCORE_AUTHORITY,
        "per_point_score_authority": contract.get("per_point_score_authority") or PENDING_SCORE_AUTHORITY,
        "answer_key_authority": "exam_reference_answer",
        "official_score_allowed": False,
        "canonical_write_allowed": False,
    }


def build_pgo_runtime_supply(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    """Build an unsigned production-default-off PGO bank bundle from contracts.

    Invalid contracts are listed in ``rejected`` and never laundered into records.
    The returned bundle is a release candidate; installing it under runtime_supply is
    a separate explicit action, and default slot remains ``legacy`` until env flip.
    """
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    by_policy: dict[str, int] = {}
    for contract in contracts:
        qid = str(contract.get("question_id") or "")
        blockers = validate_grading_contract(contract)
        if blockers:
            rejected.append({"question_id": qid, "blockers": blockers})
            continue
        for point in runtime_points_from_grading_contract(contract):
            rec = _record_from_runtime_point(contract, point)
            if not rec["qid"] or not rec["point_id"] or not rec["text"]:
                rejected.append({"question_id": qid, "blockers": ["record_missing_identity_or_text"]})
                continue
            by_policy[rec["policy"]] = by_policy.get(rec["policy"], 0) + 1
            records.append(rec)
    records.sort(key=lambda r: (r["qid"], r["point_id"]))
    content_hash = _sha256_hex(records)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": NAMESPACE,
        "lane": NAMESPACE,
        "status": STATUS,
        "published": False,
        "production_default": "off",
        "question_count": len({r["qid"] for r in records}),
        "scoring_point_count": len(records),
        "by_policy": dict(sorted(by_policy.items())),
        "rejected_count": len(rejected),
        "answer_key_authority": "exam_reference_answer",
        "official_total_score_authority": A_OFFICIAL,
        "score_authority": SCORE_AUTHORITY,
        "per_point_score_authority": PENDING_SCORE_AUTHORITY,
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, NAMESPACE, STATUS]),
        "rollback_pointer": "LUBAN_CASE_RUBRIC_BANK_SLOT=legacy",
    }
    return {"manifest": manifest, "records": records, "rejected": rejected}


def build_pgo_runtime_supply_pointer(bundle: dict[str, Any]) -> dict[str, Any]:
    manifest = bundle.get("manifest") or {}
    return {
        "namespace": NAMESPACE,
        "status": manifest.get("status") or STATUS,
        "published": False,
        "expected_content_hash": manifest.get("content_hash") or "",
        "rollback_pointer": "LUBAN_CASE_RUBRIC_BANK_SLOT=legacy",
    }


def validate_pgo_runtime_supply(bundle: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    manifest = bundle.get("manifest") or {}
    records = bundle.get("records") or []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        blockers.append("schema_version_mismatch")
    if manifest.get("namespace") != NAMESPACE:
        blockers.append("namespace_mismatch")
    if manifest.get("status") != STATUS:
        blockers.append("status_must_be_release_candidate")
    if manifest.get("published") is not False:
        blockers.append("published_must_be_false")
    if manifest.get("production_default") != "off":
        blockers.append("production_default_must_be_off")
    if not records:
        blockers.append("no_records")
    if _sha256_hex(records) != manifest.get("content_hash"):
        blockers.append("content_hash_mismatch")
    if manifest.get("signature") != _sha256_hex([manifest.get("content_hash"), NAMESPACE, STATUS]):
        blockers.append("signature_mismatch")
    for record in records:
        point_id = str(record.get("point_id") or "")
        if record.get("score") is not None or record.get("max_score") is not None:
            blockers.append(f"record_minted_score:{point_id}")
        if record.get("score_authority") != SCORE_AUTHORITY:
            blockers.append(f"record_score_authority_mismatch:{point_id}")
        if record.get("official_score_allowed") is not False:
            blockers.append(f"record_official_score_allowed:{point_id}")
        if record.get("canonical_write_allowed") is not False:
            blockers.append(f"record_canonical_write_allowed:{point_id}")
        if not record.get("official_total_score"):
            blockers.append(f"record_missing_official_total_score:{point_id}")
    return blockers


def write_pgo_runtime_supply(bundle: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    """Write bundle + canonical pointer to a target directory after validation."""
    blockers = validate_pgo_runtime_supply(bundle)
    if blockers:
        raise ValueError(f"invalid PGO runtime supply: {blockers}")
    out_dir.mkdir(parents=True, exist_ok=True)
    bank_path = out_dir / "case_rubric_scored_pgo.json"
    pointer_path = out_dir / "canonical_pointer.json"
    bank_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer_path.write_text(
        json.dumps(build_pgo_runtime_supply_pointer(bundle), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"bank": bank_path, "pointer": pointer_path}


__all__ = [
    "SCHEMA_VERSION",
    "NAMESPACE",
    "SCORE_AUTHORITY",
    "build_pgo_runtime_supply",
    "build_pgo_runtime_supply_pointer",
    "validate_pgo_runtime_supply",
    "write_pgo_runtime_supply",
]
