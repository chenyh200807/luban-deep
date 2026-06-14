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
    SCHEMA_ID as PGO_OBJECT_SCHEMA_ID,
    validate_grading_contract,
)
from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash
from deeptutor.services.source_compiler.scoring_point_asset_compiler import normalize_for_match

SCHEMA_VERSION = "luban_case_rubric_scored_pgo.v1"
NAMESPACE = "case_rubric_scored_pgo"
STATUS = "release_candidate"
SCORE_AUTHORITY = "official_total_x_verdict_coverage"
FACTORY_CANDIDATE_SCHEMA = "luban_full_factory_candidate.v1"


def _factory_point_id(question_id: str, ordinal: int, slice_text: str) -> str:
    seed = f"{question_id}|S01|P{ordinal:02d}|{normalize_for_match(slice_text)[:24]}"
    return "sp_" + source_span_hash(seed)[:20]


def _official_answer_from_pgo_object(obj: dict[str, Any]) -> str:
    parts: list[str] = []
    for sub in obj.get("sub_questions") or []:
        text = str(sub.get("official_sub_answer_verbatim") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _normalize_with_offsets(text: str) -> tuple[str, list[tuple[int, int]]]:
    chars: list[str] = []
    offsets: list[tuple[int, int]] = []
    for idx, ch in enumerate(text):
        normalized = normalize_for_match(ch)
        if not normalized:
            continue
        for norm_ch in normalized:
            chars.append(norm_ch)
            offsets.append((idx, idx + 1))
    return "".join(chars), offsets


def _canonical_official_substring(segment_text: str, official_answer: str) -> str | None:
    text = str(segment_text or "").strip()
    if not text:
        return None
    if text in official_answer:
        return text
    needle = normalize_for_match(text)
    if not needle:
        return None
    haystack, offsets = _normalize_with_offsets(official_answer)
    start = haystack.find(needle)
    if start < 0:
        return None
    end = start + len(needle)
    if haystack.find(needle, start + 1) >= 0:
        return None
    original_start = offsets[start][0]
    original_end = offsets[end - 1][1]
    return official_answer[original_start:original_end].strip()


def _factory_sub_type(case: dict[str, Any], segment: dict[str, Any]) -> str:
    point_type = str(case.get("point_type") or "").strip()
    if point_type in {"calculation", "flaw_correction", "exceptions"}:
        return point_type
    if point_type == "list" or segment.get("is_list_item") is True:
        return "enumeration"
    return "free_text_point"


def _factory_classification_is_review_only(factory: dict[str, Any]) -> bool:
    classification = (factory.get("summary") or {}).get("classification") or {}
    return (
        classification.get("candidate_only") is True and classification.get("review_only") is True
    )


def build_grading_contracts_from_factory_candidate(
    factory: dict[str, Any], pgo_objects: list[dict[str, Any]]
) -> dict[str, Any]:
    """Turn a reviewed factory segmentation candidate into grading contracts.

    The factory may propose segmentation granularity, but it does not become score
    authority. Every segment is re-checked as a verbatim substring of the canonical
    per-question grading object, point ids are deterministically minted from that
    official slice, and per-point scores stay null.
    """
    objects_by_qid = {
        str(obj.get("question_id") or ""): obj
        for obj in pgo_objects
        if isinstance(obj, dict) and obj.get("schema_id") == PGO_OBJECT_SCHEMA_ID
    }
    contracts: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    summary = factory.get("summary") or {}
    if summary.get("schema") != FACTORY_CANDIDATE_SCHEMA:
        return {
            "contracts": [],
            "rejected": [{"question_id": "", "blockers": ["factory_schema_mismatch"]}],
            "summary": {
                "source_schema": summary.get("schema"),
                "accepted_count": 0,
                "rejected_count": 1,
            },
        }
    if not _factory_classification_is_review_only(factory):
        return {
            "contracts": [],
            "rejected": [{"question_id": "", "blockers": ["factory_candidate_not_review_only"]}],
            "summary": {
                "source_schema": FACTORY_CANDIDATE_SCHEMA,
                "accepted_count": 0,
                "rejected_count": 1,
            },
        }

    resolution_lanes: set[str] = set()
    for case in factory.get("cases") or []:
        if not isinstance(case, dict):
            continue
        qid = str(case.get("question_id") or "")
        blockers: list[str] = []
        obj = objects_by_qid.get(qid)
        if not qid:
            blockers.append("missing_question_id")
        if obj is None:
            blockers.append("pgo_object_missing")
        if case.get("final_mnm_ok") is not True:
            blockers.append("factory_must_not_mint_not_clean")
        segments = [s for s in case.get("segments") or [] if isinstance(s, dict)]
        if not segments:
            blockers.append("no_factory_segments")
        if blockers:
            rejected.append({"question_id": qid, "blockers": blockers})
            continue

        assert obj is not None  # narrowed by blockers above
        official_answer = _official_answer_from_pgo_object(obj)
        scoring_points: list[dict[str, Any]] = []
        for ordinal, segment in enumerate(segments, start=1):
            raw_text = str(segment.get("text") or "").strip()
            if not raw_text:
                blockers.append(f"empty_segment:{ordinal}")
                continue
            text = _canonical_official_substring(raw_text, official_answer)
            if text is None:
                blockers.append(f"segment_not_verbatim:{ordinal}")
                continue
            if text not in official_answer:
                blockers.append(f"segment_not_verbatim:{ordinal}")
                continue
            scoring_points.append(
                {
                    "point_id": _factory_point_id(qid, ordinal, text),
                    "sub_no": 1,
                    "sub_type": _factory_sub_type(case, segment),
                    "official_slice": text,
                    "authority_source": A_OFFICIAL,
                    "span_hash": source_span_hash(text),
                    "score": None,
                    "score_authority": PENDING_SCORE_AUTHORITY,
                    "exact_term_required": segment.get("exact_term_required") is True,
                    "factory_resolution": case.get("resolution"),
                    "factory_resolution_lane": case.get("resolution_lane"),
                    "factory_point_type": case.get("point_type"),
                }
            )
        if blockers:
            rejected.append({"question_id": qid, "blockers": blockers})
            continue

        lane = str(case.get("resolution_lane") or "").strip()
        if lane:
            resolution_lanes.add(lane)
        contract = {
            "contract_schema": GRADING_CONTRACT_SCHEMA_ID,
            "source_schema": PGO_OBJECT_SCHEMA_ID,
            "question_id": qid,
            "stem": obj.get("stem"),
            "official_total_score": obj.get("official_total_score"),
            "official_total_score_authority": obj.get("official_total_score_authority"),
            "per_point_score_authority": obj.get("per_point_score_authority")
            or PENDING_SCORE_AUTHORITY,
            "scoring_points": scoring_points,
            "supporting_citations": [],
            "g2_role": {
                "official_decides_correctness": True,
                "rich_leaf_role": "supporting_only",
            },
            "official_score_allowed": False,
            "canonical_write_allowed": False,
            "factory_provenance": {
                "schema": FACTORY_CANDIDATE_SCHEMA,
                "case_file": case.get("case_file"),
                "resolution": case.get("resolution"),
                "resolution_lanes": [lane] if lane else [],
                "point_type": case.get("point_type"),
            },
            "output_contract": {
                "must_emit_one_verdict_per_point_id": True,
                "verdict_enum": ["hit", "partial", "miss", "contradiction"],
                "score_pct_must_be_consistent_with_verdicts": True,
            },
        }
        contract_blockers = validate_grading_contract(contract)
        if contract_blockers:
            rejected.append({"question_id": qid, "blockers": contract_blockers})
            continue
        contracts.append(contract)

    return {
        "contracts": contracts,
        "rejected": rejected,
        "summary": {
            "source_schema": FACTORY_CANDIDATE_SCHEMA,
            "accepted_count": len(contracts),
            "rejected_count": len(rejected),
            "resolution_lanes": sorted(resolution_lanes),
        },
    }


def _record_from_runtime_point(contract: dict[str, Any], point: dict[str, Any]) -> dict[str, Any]:
    text = str(point.get("official_slice") or point.get("knowledge_point") or "")
    return {
        "qid": str(contract.get("question_id") or ""),
        "point_id": str(point.get("point_id") or ""),
        "source_schema": contract.get("source_schema"),
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
        "official_total_score_authority": contract.get("official_total_score_authority")
        or A_OFFICIAL,
        "score_authority": SCORE_AUTHORITY,
        "per_point_score_authority": contract.get("per_point_score_authority")
        or PENDING_SCORE_AUTHORITY,
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
    source_schemas: set[str] = set()
    factory_resolution_lanes: set[str] = set()
    for contract in contracts:
        qid = str(contract.get("question_id") or "")
        blockers = validate_grading_contract(contract)
        if blockers:
            rejected.append({"question_id": qid, "blockers": blockers})
            continue
        source_schema = str(contract.get("source_schema") or "").strip()
        if source_schema:
            source_schemas.add(source_schema)
        source_points_by_id = {
            str(sp.get("point_id") or ""): sp
            for sp in contract.get("scoring_points") or []
            if isinstance(sp, dict)
        }
        for point in runtime_points_from_grading_contract(contract):
            rec = _record_from_runtime_point(contract, point)
            if not rec["qid"] or not rec["point_id"] or not rec["text"]:
                rejected.append(
                    {"question_id": qid, "blockers": ["record_missing_identity_or_text"]}
                )
                continue
            source_point = source_points_by_id.get(str(rec["point_id"]) or "") or {}
            for key in (
                "exact_term_required",
                "factory_resolution",
                "factory_resolution_lane",
                "factory_point_type",
            ):
                if key in source_point and source_point.get(key) is not None:
                    rec[key] = source_point.get(key)
            lane = str(source_point.get("factory_resolution_lane") or "").strip()
            if lane:
                factory_resolution_lanes.add(lane)
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
        "source_schemas": sorted(source_schemas),
        "factory_resolution_lanes": sorted(factory_resolution_lanes),
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
    "build_grading_contracts_from_factory_candidate",
    "build_pgo_runtime_supply",
    "build_pgo_runtime_supply_pointer",
    "validate_pgo_runtime_supply",
    "write_pgo_runtime_supply",
]
