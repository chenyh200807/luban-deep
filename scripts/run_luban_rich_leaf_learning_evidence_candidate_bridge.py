#!/usr/bin/env python3
"""Project RichLeaf near-live shadow rows into review-only Learning Brain candidates.

This bridge proves shape compatibility with ``learner_memory_events.learning_evidence``
without writing memory, generating a PersonalizationContextPack, or promoting
candidate evidence into learner truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_NEAR_LIVE_SHADOW_AB = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_shadow_ab_20260612/near_live_shadow_ab.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_candidate_bridge_20260612/learning_evidence_candidate_bridge.json"
)
SCHEMA = "luban_rich_leaf_learning_evidence_candidate_bridge.v1"
SEMANTIC_NEAR_LIVE_SCHEMA = "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1"
V23_NEAR_LIVE_SCHEMA = "luban_rich_leaf_v23_near_live_shadow_ab.v1"
V23_RUNTIME_TOKEN_PACK_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _classification_blocks(payload: dict[str, Any], blockers: list[str], *, prefix: str = "near_live_shadow") -> None:
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"{prefix}_runtime_or_release_allowed:{key}")
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append(f"{prefix}_review_flags_invalid")
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    for key in ("canonical_truth_written", "official_score_allowed", "installed_runtime_supply", "release_truth_claimed"):
        if safety.get(key) is not False:
            blockers.append(f"{prefix}_safety_{key}")
    if safety.get("production_write_count") not in (0, False):
        blockers.append(f"{prefix}_safety_production_write_count_nonzero")


def _candidate_event(row: dict[str, Any]) -> dict[str, Any]:
    cited = [str(ref_id) for ref_id in row.get("cited_source_ref_ids") or [] if str(ref_id)]
    trace = {
        "case_id": str(row.get("case_id") or ""),
        "task": str(row.get("task") or ""),
        "artifact_id": str(row.get("artifact_id") or ""),
        "leaf_id": str(row.get("leaf_id") or ""),
        "field_id": str(row.get("field_id") or ""),
        "family": str(row.get("family") or ""),
        "cited_source_ref_ids": cited,
    }
    answer = row.get("answer") if isinstance(row.get("answer"), dict) else {}
    payload_for_id = {
        "trace": trace,
        "answerable": bool(row.get("answerable")),
        "term_hit": bool(row.get("term_hit")),
    }
    return {
        "schema_version": 1,
        "event_type": "learning_evidence",
        "memory_kind": "learning_evidence",
        "source": "rich_leaf_shadow_candidate",
        "source_feature": "rich_leaf_shadow_candidate",
        "candidate_event_id": _stable_id("rich_leaf_le_candidate", payload_for_id),
        "candidate_only": True,
        "preview_only": True,
        "claim_promotion_allowed": False,
        "mastery_raised": False,
        "canonical_truth_written": False,
        "question_id": trace["case_id"],
        "question_type": "rich_leaf_shadow_runtime_case",
        "score_awarded": None,
        "max_score": None,
        "score_ratio": None,
        "explanation": {
            "text": str(answer.get("text") or ""),
            "source": "rich_leaf_local_adapter",
        },
        "evidence_refs": [
            {
                "source": "rich_leaf_compiled_context_pack",
                "source_type": "compiled_source_ref",
                "ref": ref_id,
                "is_answer_key": False,
            }
            for ref_id in cited
        ],
        "rich_leaf_trace": trace,
        "quality": {
            "candidate_only": True,
            "authority": "rich_leaf_shadow_candidate",
            "writeback_eligible": False,
            "progress_countable": False,
            "truth_eligible": False,
            "stable_truth_eligible": False,
            "evidence_cap_reasons": ["rich_leaf_candidate_not_grading_truth"],
            "evidence_level": "preview_needs_retest",
        },
    }


def _source_ref_id(source_ref: dict[str, Any]) -> str:
    source_path = str(source_ref.get("source_path") or source_ref.get("record_id") or "").strip()
    span_hash = str(source_ref.get("span_hash") or source_ref.get("file_sha256") or "").strip()
    return "#".join(part for part in (source_path, span_hash) if part)


def _v23_candidate_event(row: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    source_ref_id = _source_ref_id(source_ref)
    compiled_context = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    trace = {
        "case_id": str(row.get("case_id") or ""),
        "task": "rich_leaf_v23_runtime_context",
        "artifact_id": str(unit.get("unit_id") or ""),
        "leaf_id": str(unit.get("leaf_id") or row.get("leaf_id") or ""),
        "field_id": "runtime_token_pack_v23",
        "family": "rich_leaf_runtime_token_pack",
        "cited_source_ref_ids": [source_ref_id] if source_ref_id else [],
    }
    payload_for_id = {
        "trace": trace,
        "source_ref": source_ref,
        "matches_expected": bool(row.get("matches_expected")),
    }
    return {
        "schema_version": 1,
        "event_type": "learning_evidence",
        "memory_kind": "learning_evidence",
        "source": "rich_leaf_v23_shadow_candidate",
        "source_feature": "rich_leaf_shadow_candidate",
        "candidate_event_id": _stable_id("rich_leaf_le_candidate", payload_for_id),
        "candidate_only": True,
        "preview_only": True,
        "claim_promotion_allowed": False,
        "mastery_raised": False,
        "canonical_truth_written": False,
        "question_id": trace["case_id"],
        "question_type": "rich_leaf_v23_shadow_runtime_case",
        "score_awarded": None,
        "max_score": None,
        "score_ratio": None,
        "explanation": {
            "text": "; ".join(
                str(item)
                for family in ("definitions", "rules", "procedures", "numeric_constraints", "exam_patterns", "teaching_cards")
                for item in (compiled_context.get(family) or [])[:1]
                if str(item).strip()
            )[:1000],
            "source": "rich_leaf_runtime_token_pack_v23",
        },
        "evidence_refs": [
            {
                "source": "rich_leaf_runtime_token_pack_v23",
                "source_type": "compiled_source_ref",
                "ref": source_ref_id,
                "source_ref": source_ref,
                "is_answer_key": False,
            }
        ]
        if source_ref_id
        else [],
        "rich_leaf_trace": trace,
        "quality": {
            "candidate_only": True,
            "authority": "rich_leaf_v23_shadow_candidate",
            "writeback_eligible": False,
            "progress_countable": False,
            "truth_eligible": False,
            "stable_truth_eligible": False,
            "evidence_cap_reasons": ["rich_leaf_candidate_not_grading_truth", "v23_near_live_proxy_only"],
            "evidence_level": "preview_needs_retest",
        },
    }


def _row_blockers(row: dict[str, Any]) -> list[str]:
    case_id = str(row.get("case_id") or "unknown")
    blockers: list[str] = []
    if row.get("arm") != "rich_leaf_local_adapter":
        blockers.append(f"candidate_row_wrong_arm:{case_id}")
    if row.get("answerable") is True and not row.get("cited_source_ref_ids"):
        blockers.append(f"candidate_row_without_cited_source_ref:{case_id}")
    for key in ("case_id", "task", "artifact_id", "leaf_id", "field_id", "family"):
        if not str(row.get(key) or "").strip():
            blockers.append(f"candidate_row_missing_{key}:{case_id}")
    if int(row.get("question_lane_citation_count") or 0) != 0:
        blockers.append(f"candidate_row_question_lane_citation:{case_id}")
    if row.get("fail_open") is not False:
        blockers.append(f"candidate_row_fail_open:{case_id}")
    return blockers


def _v23_row_blockers(row: dict[str, Any], unit: dict[str, Any] | None) -> list[str]:
    case_id = str(row.get("case_id") or "unknown")
    blockers: list[str] = []
    if row.get("arm") != "rich_leaf_v23_context":
        blockers.append(f"v23_candidate_row_wrong_arm:{case_id}")
    if row.get("answerable") is not True:
        blockers.append(f"v23_candidate_row_not_answerable:{case_id}")
    if row.get("matches_expected") is not True:
        blockers.append(f"v23_candidate_row_not_matching_expected:{case_id}")
    if row.get("evidence_cited") is not True:
        blockers.append(f"v23_candidate_row_without_evidence_citation:{case_id}")
    if row.get("fail_open") is not False:
        blockers.append(f"v23_candidate_row_fail_open:{case_id}")
    leaf_id = str(row.get("leaf_id") or "")
    if not leaf_id:
        blockers.append(f"v23_candidate_row_missing_leaf_id:{case_id}")
    if unit is None:
        blockers.append(f"v23_candidate_row_missing_runtime_unit:{case_id}:{leaf_id}")
        return blockers
    for key in ("unit_id", "leaf_id", "compiled_context"):
        if not unit.get(key):
            blockers.append(f"v23_runtime_unit_missing_{key}:{case_id}:{leaf_id}")
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    for key in ("source_path", "span_hash", "source_lane"):
        if not str(source_ref.get(key) or "").strip():
            blockers.append(f"v23_runtime_unit_missing_source_ref_{key}:{case_id}:{leaf_id}")
    for key in ("candidate_only", "review_only"):
        if unit.get(key) is not True:
            blockers.append(f"v23_runtime_unit_{key}_invalid:{case_id}:{leaf_id}")
    if unit.get("runtime_install_allowed") is not False or unit.get("production_default") is not False:
        blockers.append(f"v23_runtime_unit_runtime_or_default_allowed:{case_id}:{leaf_id}")
    return blockers


def _v23_units_by_leaf(runtime_token_pack_v23: dict[str, Any] | None, blockers: list[str]) -> dict[str, list[dict[str, Any]]]:
    if runtime_token_pack_v23 is None:
        blockers.append("v23_runtime_token_pack_missing")
        return {}
    if runtime_token_pack_v23.get("schema") != V23_RUNTIME_TOKEN_PACK_SCHEMA:
        blockers.append(f"v23_runtime_token_pack_schema_mismatch:{runtime_token_pack_v23.get('schema')}")
    if runtime_token_pack_v23.get("status") != "candidate_ready_for_shadow_ab_full_accounted":
        blockers.append(f"v23_runtime_token_pack_status_invalid:{runtime_token_pack_v23.get('status')}")
    if runtime_token_pack_v23.get("classification", {}).get("candidate_only") is not True:
        blockers.append("v23_runtime_token_pack_candidate_flag_invalid")
    _classification_blocks(runtime_token_pack_v23, blockers, prefix="v23_runtime_token_pack")
    units = [
        unit
        for unit in runtime_token_pack_v23.get("runtime_token_pack_units") or []
        if isinstance(unit, dict)
    ]
    by_leaf: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        by_leaf.setdefault(str(unit.get("leaf_id") or ""), []).append(unit)
    return by_leaf


def _run_v23_bridge(
    *,
    near_live_shadow_ab: dict[str, Any],
    runtime_token_pack_v23: dict[str, Any] | None,
    blockers: list[str],
) -> list[dict[str, Any]]:
    if near_live_shadow_ab.get("verdict") != "PASS_V23_NEAR_LIVE_SHADOW_AB":
        blockers.append(f"v23_near_live_shadow_not_pass:{near_live_shadow_ab.get('verdict')}")
    if near_live_shadow_ab.get("quality_claim_allowed") is not False:
        blockers.append("v23_near_live_shadow_quality_claim_allowed")
    if near_live_shadow_ab.get("verdict_ceiling") != "NEAR_LIVE_PROXY_ONLY":
        blockers.append(f"v23_near_live_shadow_bad_ceiling:{near_live_shadow_ab.get('verdict_ceiling')}")
    _classification_blocks(near_live_shadow_ab, blockers, prefix="v23_near_live_shadow")

    rows = [
        row
        for row in near_live_shadow_ab.get("rows") or []
        if isinstance(row, dict) and row.get("arm") == "rich_leaf_v23_context"
    ]
    if not rows:
        blockers.append("v23_no_rich_leaf_rows")
    units_by_leaf = _v23_units_by_leaf(runtime_token_pack_v23, blockers)
    leaf_offsets: dict[str, int] = {}
    candidate_events: list[dict[str, Any]] = []
    for row in rows:
        leaf_id = str(row.get("leaf_id") or "")
        leaf_units = units_by_leaf.get(leaf_id) or []
        offset = leaf_offsets.get(leaf_id, 0)
        unit = leaf_units[offset] if offset < len(leaf_units) else (leaf_units[-1] if leaf_units else None)
        leaf_offsets[leaf_id] = offset + 1
        row_blockers = _v23_row_blockers(row, unit)
        blockers.extend(row_blockers)
        if not row_blockers and unit is not None:
            candidate_events.append(_v23_candidate_event(row, unit))
    return candidate_events


def run_learning_evidence_candidate_bridge(
    *,
    near_live_shadow_ab: dict[str, Any],
    runtime_token_pack_v23: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    input_schema = near_live_shadow_ab.get("schema")
    rows: list[dict[str, Any]]
    if input_schema == SEMANTIC_NEAR_LIVE_SCHEMA:
        if near_live_shadow_ab.get("verdict") != "PASS":
            blockers.append(f"near_live_shadow_not_pass:{near_live_shadow_ab.get('verdict')}")
        if near_live_shadow_ab.get("quality_claim_allowed") is not False:
            blockers.append("near_live_shadow_quality_claim_allowed")
        _classification_blocks(near_live_shadow_ab, blockers)

        rows = [row for row in near_live_shadow_ab.get("local_adapter_rows") or [] if isinstance(row, dict)]
        if not rows:
            blockers.append("no_local_adapter_rows")

        candidate_events = []
        for row in rows:
            row_blockers = _row_blockers(row)
            blockers.extend(row_blockers)
            if not row_blockers:
                candidate_events.append(_candidate_event(row))
    elif input_schema == V23_NEAR_LIVE_SCHEMA:
        rows = [
            row
            for row in near_live_shadow_ab.get("rows") or []
            if isinstance(row, dict) and row.get("arm") == "rich_leaf_v23_context"
        ]
        candidate_events = _run_v23_bridge(
            near_live_shadow_ab=near_live_shadow_ab,
            runtime_token_pack_v23=runtime_token_pack_v23,
            blockers=blockers,
        )
    else:
        rows = []
        candidate_events = []
        blockers.append(f"near_live_shadow_schema_mismatch:{input_schema}")

    return {
        "schema": SCHEMA,
        "input_schema": input_schema,
        "verdict": "FAIL" if blockers else "PASS",
        "quality_claim_allowed": False,
        "execution_mode": "candidate_bridge",
        "summary": {
            "blocker_count": len(blockers),
            "source_shadow_case_count": int((near_live_shadow_ab.get("summary") or {}).get("shadow_case_count") or (near_live_shadow_ab.get("summary") or {}).get("case_count") or 0),
            "local_adapter_row_count": len(rows),
            "candidate_event_count": len(candidate_events),
            "learner_memory_write_count": 0,
            "provider_call_count": 0,
        },
        "learning_evidence_event_candidates": candidate_events,
        "blockers": blockers,
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
        "not_exercised": [
            "learner_memory_db_write",
            "learner_memory_event_id_assignment",
            "canonical_learner_truth_write",
            "personalization_context_pack_readback",
            "learner_claim_projection",
            "next_best_action_generation",
            "real_student_outcome",
            "governance_signoff",
            "production_default_decision",
        ],
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
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--near-live-shadow-ab", type=Path, default=DEFAULT_NEAR_LIVE_SHADOW_AB)
    parser.add_argument("--runtime-token-pack-v23", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = run_learning_evidence_candidate_bridge(
        near_live_shadow_ab=_read_json(args.near_live_shadow_ab),
        runtime_token_pack_v23=_read_json(args.runtime_token_pack_v23) if args.runtime_token_pack_v23 else None,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
