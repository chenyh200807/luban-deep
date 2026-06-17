#!/usr/bin/env python3
"""Audit older Luban compiler artifacts against current RichLeaf reuse rules."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_legacy_compilation_quality_audit_20260612/legacy_quality_audit.json"
)
SCHEMA = "luban_rich_leaf_legacy_compilation_quality_audit.v1"
SAFETY_FALSE_KEYS = (
    "canonical_truth_written",
    "official_score_allowed",
    "installed_runtime_supply",
    "release_truth_claimed",
    "canonical_learner_truth_written",
)
COUNT_ZERO_KEYS = (
    "production_write_count",
    "learner_memory_write_count",
    "canonical_truth_write_count",
    "canonical_learner_truth_write_count",
)
AUTHORITY_TRUE_KEYS = (
    "runtime_install_allowed",
    "production_default",
    "release_truth_claimed",
    "quality_claim_allowed",
    "official_score_allowed",
)
RELEASE_KEYS = (
    "release_candidate",
    "signed_release_candidate",
    "controlled_default",
    "production_default",
    "official_score_allowed",
    "quality_claim_allowed",
    "release_truth_claimed",
)


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _walk_values(payload: Any) -> list[Any]:
    values = [payload]
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(_walk_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_walk_values(item))
    return values


def _dict_values(payloads: list[Any]) -> list[dict[str, Any]]:
    return [item for payload in payloads for item in _walk_values(payload) if isinstance(item, dict)]


def _has_source_ref_shape(dicts: list[dict[str, Any]]) -> bool:
    for item in dicts:
        source_refs = item.get("source_refs")
        if isinstance(source_refs, list) and source_refs:
            for ref in source_refs:
                if isinstance(ref, dict) and (ref.get("span_hash") or (ref.get("path") and ref.get("span"))):
                    return True
        if item.get("source_ref_id") and item.get("span_hash"):
            return True
    return False


def _has_modern_candidate_boundary(dicts: list[dict[str, Any]]) -> bool:
    for item in dicts:
        if (
            item.get("candidate_only") is True
            and item.get("review_only") is True
            and item.get("runtime_install_allowed") is False
            and item.get("release_truth_claimed") is False
        ):
            return True
        classification = item.get("classification")
        if isinstance(classification, dict) and classification.get("candidate_only") is True and classification.get("review_only") is True:
            return True
    return False


def _release_or_default_claims(dicts: list[dict[str, Any]]) -> list[str]:
    claims: list[str] = []
    for item in dicts:
        for key in RELEASE_KEYS:
            if item.get(key) is True:
                claims.append(key)
        status_blob = " ".join(str(item.get(key) or "") for key in ("verdict", "status", "candidate_status", "decision"))
        if "release_candidate" in status_blob or "controlled_default" in status_blob:
            claims.append("status_release_or_default")
    return sorted(set(claims))


def _safety_violations(dicts: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    for item in dicts:
        for key in SAFETY_FALSE_KEYS:
            if item.get(key) is True:
                violations.append(f"unsafe_{key}")
        for key in COUNT_ZERO_KEYS:
            if item.get(key) not in (None, 0, False):
                violations.append(f"unsafe_{key}")
        for container_key in ("classification", "safety"):
            container = item.get(container_key)
            if not isinstance(container, dict):
                continue
            for key in AUTHORITY_TRUE_KEYS:
                if container.get(key) is True:
                    violations.append(f"unsafe_{key}")
            for key in SAFETY_FALSE_KEYS:
                if container.get(key) is True:
                    violations.append(f"unsafe_{key}")
            for key in COUNT_ZERO_KEYS:
                if container.get(key) not in (None, 0, False):
                    violations.append(f"unsafe_{key}")
    return sorted(set(violations))


def _audit_dir(artifact_dir: Path) -> dict[str, Any]:
    json_paths = sorted(path for path in artifact_dir.glob("*.json") if path.is_file())
    payloads = [payload for path in json_paths if (payload := _read_json(path)) is not None]
    dicts = _dict_values(payloads)
    safety = _safety_violations(dicts)
    release_claims = _release_or_default_claims(dicts)
    has_source_ref_shape = _has_source_ref_shape(dicts)
    has_modern_boundary = _has_modern_candidate_boundary(dicts)

    quality_gaps: list[str] = []
    if not has_modern_boundary:
        quality_gaps.append("missing_modern_candidate_boundary")
    if not has_source_ref_shape:
        quality_gaps.append("missing_field_level_source_ref_or_span_hash")
    if release_claims:
        quality_gaps.append("release_or_default_claim_present")
    quality_gaps.extend(safety)

    return {
        "artifact_dir": str(artifact_dir),
        "json_file_count": len(json_paths),
        "parsed_json_file_count": len(payloads),
        "has_modern_candidate_boundary": has_modern_boundary,
        "has_source_ref_shape": has_source_ref_shape,
        "release_or_default_claims": release_claims,
        "safety_violations": safety,
        "quality_gaps": sorted(set(quality_gaps)),
        "direct_rich_leaf_reuse_allowed": False if quality_gaps else True,
        "reuse_policy": "recompile_or_review_before_rich_leaf_runtime" if quality_gaps else "reviewed_candidate_input_possible",
    }


def run_legacy_compilation_quality_audit(*, artifact_dirs: list[Path]) -> dict[str, Any]:
    findings = [_audit_dir(path) for path in artifact_dirs]
    safety_count = sum(len(finding["safety_violations"]) for finding in findings)
    quality_gap_count = sum(len(finding["quality_gaps"]) for finding in findings)
    direct_reuse_allowed_count = sum(1 for finding in findings if finding["direct_rich_leaf_reuse_allowed"])
    verdict = "PASS"
    if safety_count:
        verdict = "NO_GO_FOR_DIRECT_REUSE"
    elif quality_gap_count:
        verdict = "REVIEW_REQUIRED"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "classification": {
            "review_only": True,
            "legacy_quality_audit": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "artifact_dir_count": len(findings),
            "json_file_count": sum(finding["json_file_count"] for finding in findings),
            "quality_gap_count": quality_gap_count,
            "safety_violation_count": safety_count,
            "direct_reuse_allowed_count": direct_reuse_allowed_count,
            "direct_reuse_blocked_count": len(findings) - direct_reuse_allowed_count,
        },
        "artifact_findings": findings,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
            "learner_memory_write_count": 0,
        },
        "not_exercised": [
            "legacy_artifact_promotion",
            "runtime_default",
            "canonical_truth_write",
            "learner_memory_writeback",
            "remote_db_write",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = run_legacy_compilation_quality_audit(artifact_dirs=args.artifact_dir)
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
