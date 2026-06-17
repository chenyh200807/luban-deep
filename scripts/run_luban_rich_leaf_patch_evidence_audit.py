#!/usr/bin/env python3
"""Review-only machine precheck for RichLeaf candidate patch evidence."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash  # noqa: E402


DEFAULT_PATCHES = REPO / "artifacts/luban_grading_artifacts/rich_leaf_candidate_patches_20260611/candidate_patches.json"
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_patch_evidence_audit_20260611/patch_evidence_audit.json"
)
SCHEMA = "luban_rich_leaf_patch_evidence_audit.v1"
OPTION_MARKERS = {"a", "b", "c", "d", "a.", "b.", "c.", "d.", "A.", "B.", "C.", "D."}
STOP_TERMS = {
    "建筑工程技术",
    "建筑工程",
    "建筑",
    "工程",
    "技术",
    "施工",
    "要求",
    "管理",
    "应用",
    "分类",
    "内容",
    "与",
}
POLLUTION_MARKERS = (
    "真题",
    "答案解析",
    "学生答卷",
    "按学生答卷",
    "必刷",
    "千题",
    "题斩",
    "考证宝典",
    "mcq",
    "practice",
    "exercise",
    "question_data",
    "correct_answer",
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _split_terms(text: str) -> list[str]:
    raw_terms = [part.strip() for part in re.split(r"[>\s/、，,（）()：:；;|]+", str(text or "")) if part.strip()]
    terms: list[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        normalized = term.strip()
        if len(normalized) < 2 or normalized in STOP_TERMS or normalized in OPTION_MARKERS:
            continue
        if normalized not in seen:
            seen.add(normalized)
            terms.append(normalized)
    return terms


def _matched_terms(source_ref: dict[str, Any]) -> list[str]:
    return [str(term) for term in source_ref.get("matched_terms") or [] if str(term).strip()]


def _has_pollution_marker(source_ref: dict[str, Any], review_packet: dict[str, Any]) -> bool:
    text = json.dumps(
        {
            "path": source_ref.get("path"),
            "record_id": source_ref.get("record_id"),
            "provenance": source_ref.get("provenance"),
            "snippet": review_packet.get("snippet"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).lower()
    return any(marker in text for marker in POLLUTION_MARKERS)


def _audit_patch(patch: dict[str, Any]) -> dict[str, Any]:
    source_ref = patch.get("source_ref_candidate") if isinstance(patch.get("source_ref_candidate"), dict) else {}
    review_packet = patch.get("review_packet") if isinstance(patch.get("review_packet"), dict) else {}
    span = str(source_ref.get("span") or "")
    matched_terms = _matched_terms(source_ref)
    specific_matched_terms = [
        term for term in matched_terms if term not in OPTION_MARKERS and len(term.strip()) >= 2
    ]
    specific_name_terms = _split_terms(str(patch.get("name_path") or ""))
    name_terms_in_span = [term for term in specific_name_terms if term in span]
    reason_codes: list[str] = []
    warnings: list[str] = []

    if patch.get("candidate_only") is not True or patch.get("apply_allowed") is not False:
        reason_codes.append("patch_flags_invalid")
    if patch.get("runtime_install_allowed") is not False:
        reason_codes.append("runtime_install_allowed")
    if patch.get("review_status") != "pending_review":
        reason_codes.append("patch_not_pending_review")
    if source_ref.get("source_lane") != patch.get("missing_lane"):
        reason_codes.append("source_lane_missing_lane_mismatch")
    if not source_ref.get("path") or not source_ref.get("record_id") or not span:
        reason_codes.append("missing_traceable_source_ref")
    if source_ref.get("span_hash") != source_span_hash(span):
        reason_codes.append("span_hash_mismatch")
    if source_ref.get("source_lane") != "question" and _has_pollution_marker(source_ref, review_packet):
        reason_codes.append("practice_or_question_source_pollution")
    if matched_terms and all(term in OPTION_MARKERS for term in matched_terms):
        reason_codes.append("option_marker_only_match")
    if specific_name_terms and not name_terms_in_span and not specific_matched_terms:
        reason_codes.append("no_name_path_specific_term_in_span")
    elif specific_name_terms and len(name_terms_in_span) < min(2, len(specific_name_terms)) and len(specific_matched_terms) < 2:
        warnings.append("low_name_path_term_overlap")
    if len(specific_matched_terms) <= 1:
        warnings.append("low_matched_term_specificity")

    reject_reasons = {
        "patch_flags_invalid",
        "runtime_install_allowed",
        "patch_not_pending_review",
        "source_lane_missing_lane_mismatch",
        "missing_traceable_source_ref",
        "span_hash_mismatch",
        "practice_or_question_source_pollution",
        "option_marker_only_match",
        "no_name_path_specific_term_in_span",
    }
    if reject_reasons & set(reason_codes):
        decision = "machine_reject"
    elif warnings:
        decision = "needs_semantic_review"
        reason_codes.extend(warnings)
    else:
        decision = "machine_precheck_pass"

    return {
        "patch_id": patch.get("patch_id"),
        "artifact_id": patch.get("artifact_id"),
        "leaf_id": patch.get("leaf_id"),
        "name_path": patch.get("name_path"),
        "missing_lane": patch.get("missing_lane"),
        "source_lane": source_ref.get("source_lane"),
        "source_ref_id": source_ref.get("source_ref_id"),
        "record_id": source_ref.get("record_id"),
        "path": source_ref.get("path"),
        "audit_decision": decision,
        "review_status": "machine_precheck_only",
        "reason_codes": reason_codes,
        "matched_terms": matched_terms,
        "name_path_terms_in_span": name_terms_in_span,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "candidate_only": True,
    }


def build_patch_evidence_audit(*, patch_batch: dict[str, Any]) -> dict[str, Any]:
    audits = [_audit_patch(patch) for patch in patch_batch.get("candidate_patches") or [] if isinstance(patch, dict)]
    return {
        "schema": SCHEMA,
        "source_patch_schema": patch_batch.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "audit_apply_allowed": False,
            "runtime_install_allowed": False,
        },
        "summary": {
            "audited_patch_count": len(audits),
            "machine_precheck_pass_count": sum(1 for audit in audits if audit["audit_decision"] == "machine_precheck_pass"),
            "machine_reject_count": sum(1 for audit in audits if audit["audit_decision"] == "machine_reject"),
            "needs_semantic_review_count": sum(
                1 for audit in audits if audit["audit_decision"] == "needs_semantic_review"
            ),
        },
        "patch_audits": audits,
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
    parser.add_argument("--patches", type=Path, default=DEFAULT_PATCHES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    patch_batch = _read_json(args.patches)
    report = build_patch_evidence_audit(patch_batch=patch_batch)
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
