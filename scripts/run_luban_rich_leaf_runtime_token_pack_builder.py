#!/usr/bin/env python3
"""Build a thin RuntimeTokenPack from a RichLeaf runtime supply candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_SUPPLY_CANDIDATE = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_supply_candidate_materialized_20260612/rich_leaf_runtime_supply_candidate.json"
)
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v1_20260612/runtime_token_pack.json"
)
SCHEMA = "luban_rich_leaf_runtime_token_pack.v1"
INPUT_SCHEMA = "luban_rich_leaf_runtime_supply_candidate_bundle.v1"
VERSION = "v_runtime_token_pack_20260612"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _excerpt(span: str, max_chars: int) -> str:
    compact = _compact(span)
    if len(compact) <= max_chars:
        return compact
    sentence = re.split(r"[。；;]", compact, maxsplit=1)[0].strip()
    if sentence and len(sentence) <= max_chars:
        return sentence
    return compact[: max(0, max_chars - 1)].rstrip() + "…"


def _input_blockers(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != INPUT_SCHEMA:
        blockers.append(f"input_schema_mismatch:{payload.get('schema')}")
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if classification.get("candidate_only") is not True or classification.get("review_only") is not True:
        blockers.append("input_candidate_review_flags_invalid")
    if classification.get("runtime_install_allowed") is not False:
        blockers.append("input_runtime_install_allowed")
    if classification.get("production_default") is not False:
        blockers.append("input_production_default")
    if classification.get("canonical_pointer_written") is not False:
        blockers.append("input_canonical_pointer_written")
    if safety.get("production_write_count", 0) not in (0, None):
        blockers.append("input_production_write_count_nonzero")
    if safety.get("release_truth_claimed") is not False:
        blockers.append("input_release_truth_claimed")
    return blockers


def _unit_blocker(unit: dict[str, Any]) -> str | None:
    unit_id = str(unit.get("unit_id") or "unknown")
    if unit.get("candidate_only") is not True or unit.get("review_only") is not True:
        return f"unit_candidate_review_flags_invalid:{unit_id}"
    if unit.get("install_allowed") is not False or unit.get("runtime_install_allowed") is not False:
        return f"unit_runtime_install_allowed:{unit_id}"
    if unit.get("production_default") is not False:
        return f"unit_production_default:{unit_id}"
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    for key in ("source_lane", "source_path", "record_id", "span", "span_hash"):
        if not source_ref.get(key):
            return f"unit_source_ref_missing_{key}:{unit_id}"
    if source_ref.get("source_lane") != unit.get("missing_lane"):
        return f"unit_lane_mismatch:{unit_id}"
    return None


def _token_pack_unit(unit: dict[str, Any], max_excerpt_chars: int) -> dict[str, Any]:
    source_ref = unit["source_ref"]
    excerpt = _excerpt(str(source_ref.get("span") or ""), max_excerpt_chars)
    provenance = unit.get("provenance") if isinstance(unit.get("provenance"), dict) else {}
    return {
        "unit_id": unit.get("unit_id"),
        "leaf_id": unit.get("leaf_id"),
        "artifact_id": unit.get("artifact_id"),
        "missing_lane": unit.get("missing_lane"),
        "source_ref": {
            "source_lane": source_ref.get("source_lane"),
            "source_path": source_ref.get("source_path"),
            "record_id": source_ref.get("record_id"),
            "span_hash": source_ref.get("span_hash"),
            "excerpt": excerpt,
            "excerpt_char_count": len(excerpt),
            "full_span_omitted": True,
            "support_candidate": source_ref.get("support_candidate") is True,
        },
        "provenance": {
            "candidate_id": provenance.get("candidate_id"),
            "audit_item_id": provenance.get("audit_item_id"),
            "review_decision": provenance.get("review_decision"),
            "reviewer_role": provenance.get("reviewer_role"),
        },
        "authority_pointer": {
            "source_span_hash": source_ref.get("span_hash"),
            "runtime_supply_unit_id": unit.get("unit_id"),
            "full_artifact_required_for_release": True,
        },
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
    }


def build_runtime_token_pack(*, runtime_supply_candidate: dict[str, Any], max_excerpt_chars: int = 360) -> dict[str, Any]:
    blockers = _input_blockers(runtime_supply_candidate)
    raw_units = [
        unit
        for unit in runtime_supply_candidate.get("supply_units") or []
        if isinstance(unit, dict)
    ]
    unit_blockers = [_unit_blocker(unit) for unit in raw_units]
    blockers.extend(blocker for blocker in unit_blockers if blocker)
    units = [] if blockers else [_token_pack_unit(unit, max_excerpt_chars) for unit in raw_units]
    full_lengths = [
        len(_compact(str((unit.get("source_ref") or {}).get("span") or "")))
        for unit in raw_units
        if isinstance(unit.get("source_ref"), dict)
    ]
    excerpt_lengths = [len(str((unit.get("source_ref") or {}).get("excerpt") or "")) for unit in units]
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "input_schema": runtime_supply_candidate.get("schema"),
        "input_version": runtime_supply_candidate.get("version"),
        "status": "candidate_ready_for_streaming_ab" if units and not blockers else "blocked",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_token_pack": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
            "quality_claim_allowed": False,
        },
        "summary": {
            "input_supply_unit_count": len(raw_units),
            "token_pack_unit_count": len(units),
            "blocker_count": len(blockers),
            "max_excerpt_chars": max_excerpt_chars,
            "mean_full_span_char_count": round(mean(full_lengths), 2) if full_lengths else 0.0,
            "mean_excerpt_char_count": round(mean(excerpt_lengths), 2) if excerpt_lengths else 0.0,
        },
        "manifest": {
            "bundle_hash": _sha256(units),
            "hash_algorithm": "sha256",
            "derived_from": runtime_supply_candidate.get("version"),
            "full_span_storage": "omitted_from_runtime_token_pack",
        },
        "runtime_token_pack_units": units,
        "blockers": blockers,
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
    parser.add_argument("--runtime-supply-candidate", type=Path, default=DEFAULT_RUNTIME_SUPPLY_CANDIDATE)
    parser.add_argument("--max-excerpt-chars", type=int, default=360)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_runtime_token_pack(
        runtime_supply_candidate=_read_json(args.runtime_supply_candidate),
        max_excerpt_chars=args.max_excerpt_chars,
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "status": report["status"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["summary"]["blocker_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
