#!/usr/bin/env python3
"""Compile review-only rich field candidates from reviewed RichLeaf source refs.

This is the first rich-field pass. It only derives candidates from reviewed
source spans and keeps every output candidate-only. It does not assemble a
RichLeafArtifact, install runtime supply, or claim release truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_REVIEWED_CANDIDATES = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_reviewed_candidates_20260612/reviewed_rich_leaf_candidates.json"
)
DEFAULT_SEMANTIC_RECORD = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_semantic_evidence_audit_record_20260612/semantic_evidence_audit_record.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_field_candidates_20260612"
SCHEMA = "luban_rich_leaf_field_candidate_batch.v1"

NON_QUESTION_SOURCE_LANES = {"textbook", "standard", "lecture"}
SOURCE_BACKED_KNOWLEDGE_FAMILIES = {
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "teaching_cards",
}
RULE_MARKERS = ("应", "必须", "不得", "不应", "宜", "严禁", "控制", "要求")
PROCEDURE_MARKERS = ("施工", "工艺", "流程", "浇筑", "安装", "拆除", "验收", "处理", "编制")
DEFINITION_MARKERS = ("是", "指", "包括", "可分为", "分为", "属于")
NUMERIC_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:\s*[～~至-]\s*\d+(?:\.\d+)?)?\s*(?:mm|cm|m|%|h|d|天|年|°C|℃)")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normal_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _candidate_id(candidate: dict[str, Any], family: str, suffix: str = "") -> str:
    seed = "|".join(
        [
            str(candidate.get("candidate_id") or ""),
            str(candidate.get("leaf_id") or ""),
            family,
            suffix,
        ]
    )
    return f"rich_leaf_field_candidate_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def _source_ref(candidate: dict[str, Any]) -> dict[str, Any]:
    patch = candidate.get("field_patch") if isinstance(candidate.get("field_patch"), dict) else {}
    source_ref = patch.get("source_ref") if isinstance(patch.get("source_ref"), dict) else {}
    return source_ref


def _source_candidate(record: dict[str, Any]) -> dict[str, Any]:
    source_candidate = record.get("source_candidate")
    return source_candidate if isinstance(source_candidate, dict) else {}


def _source_trace(candidate: dict[str, Any]) -> dict[str, Any]:
    source_ref = _source_ref(candidate)
    return {
        "source_lane": source_ref.get("source_lane"),
        "source_path": source_ref.get("source_path"),
        "record_id": source_ref.get("record_id"),
        "span": source_ref.get("span"),
        "span_hash": source_ref.get("span_hash"),
        "matched_terms": list(source_ref.get("matched_terms") or []),
    }


def _negative_source_trace(record: dict[str, Any]) -> dict[str, Any]:
    source_candidate = _source_candidate(record)
    return {
        "source_lane": source_candidate.get("source_lane"),
        "source_path": source_candidate.get("source_path"),
        "record_id": source_candidate.get("record_id"),
        "span": source_candidate.get("span"),
        "span_hash": source_candidate.get("span_hash"),
        "matched_terms": list(source_candidate.get("matched_terms") or []),
    }


def _base_field(candidate: dict[str, Any], family: str) -> dict[str, Any]:
    return {
        "field_candidate_id": _candidate_id(candidate, family),
        "family": family,
        "leaf_id": candidate.get("leaf_id"),
        "artifact_id": candidate.get("artifact_id"),
        "derived_from_candidate_id": candidate.get("candidate_id"),
        "audit_item_id": candidate.get("audit_item_id"),
        "claim_status": "candidate_only",
        "review_only": True,
        "candidate_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "source_ref_trace": _source_trace(candidate),
    }


def _base_negative_field(record: dict[str, Any], family: str) -> dict[str, Any]:
    seed = "|".join(
        [
            str(record.get("audit_item_id") or ""),
            str(record.get("leaf_id") or ""),
            family,
            str(record.get("decision") or ""),
        ]
    )
    return {
        "field_candidate_id": f"rich_leaf_field_candidate_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}",
        "family": family,
        "leaf_id": record.get("leaf_id"),
        "artifact_id": record.get("artifact_id"),
        "derived_from_candidate_id": record.get("audit_item_id"),
        "audit_item_id": record.get("audit_item_id"),
        "claim_status": "candidate_only",
        "review_only": True,
        "candidate_only": True,
        "runtime_install_allowed": False,
        "release_truth_claimed": False,
        "source_ref_trace": _negative_source_trace(record),
    }


def _first_sentence(span: str) -> str:
    parts = re.split(r"[。；;]", _normal_text(span), maxsplit=1)
    return parts[0].strip(" ：:") if parts else _normal_text(span)


def _numeric_items(span: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in NUMERIC_PATTERN.finditer(span):
        value = _normal_text(match.group(0))
        start = max(0, match.start() - 24)
        end = min(len(span), match.end() + 24)
        items.append({"value": value, "context": _normal_text(span[start:end])})
    return items


def _concept_field(candidate: dict[str, Any]) -> dict[str, Any] | None:
    matched_terms = [
        str(term).strip()
        for term in (_source_ref(candidate).get("matched_terms") or [])
        if str(term).strip()
    ]
    if not matched_terms:
        return None
    field = _base_field(candidate, "concepts")
    field["concept_name"] = matched_terms[0]
    field["aliases"] = matched_terms[1:4]
    field["concept_source"] = "reviewed_source_ref_matched_terms"
    return field


def _learner_memory_event_template(candidate: dict[str, Any]) -> dict[str, Any]:
    field = _base_field(candidate, "learner_memory_event_templates")
    field["event_type"] = "case_grading_completed"
    field["template_status"] = "candidate_only_not_writeable"
    field["canonical_write_allowed"] = False
    field["required_runtime_inputs"] = ["student_id", "question_id", "attempt_id", "scoring_points"]
    field["emits_claim_types"] = ["knowledge_gap_candidate", "mistake_pattern_candidate"]
    field["leaf_id"] = candidate.get("leaf_id")
    return field


def _common_mistake_hypothesis(candidate: dict[str, Any]) -> dict[str, Any]:
    matched_terms = [
        str(term).strip()
        for term in (_source_ref(candidate).get("matched_terms") or [])
        if str(term).strip()
    ]
    field = _base_field(candidate, "common_mistakes")
    field["mistake_group"] = "hypothesized_mistakes"
    field["observed_from"] = "synthetic_candidate"
    field["mistake_type"] = "missing_or_confused_key_term"
    field["learner_evidence_allowed"] = False
    field["canonical_write_allowed"] = False
    field["required_terms"] = matched_terms[:4]
    field["hypothesis_basis"] = "reviewed_source_ref_terms"
    return field


def _non_question_fields(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    span = _normal_text(str(_source_ref(candidate).get("span") or ""))
    if not span:
        return []
    fields: list[dict[str, Any]] = []
    concept = _concept_field(candidate)
    if concept:
        fields.append(concept)
    if any(marker in span for marker in DEFINITION_MARKERS):
        field = _base_field(candidate, "definitions")
        field["text"] = _first_sentence(span)
        fields.append(field)
    if any(marker in span for marker in RULE_MARKERS):
        field = _base_field(candidate, "rules")
        field["rule_text"] = _first_sentence(span)
        field["rule_markers"] = [marker for marker in RULE_MARKERS if marker in span]
        fields.append(field)
    if any(marker in span for marker in PROCEDURE_MARKERS):
        field = _base_field(candidate, "procedures")
        field["procedure_text"] = _first_sentence(span)
        field["procedure_markers"] = [marker for marker in PROCEDURE_MARKERS if marker in span]
        fields.append(field)
    numeric_items = _numeric_items(span)
    if numeric_items:
        field = _base_field(candidate, "numeric_constraints")
        field["items"] = numeric_items
        fields.append(field)
    if span:
        field = _base_field(candidate, "teaching_cards")
        field["card_type"] = "source_backed_explanation_candidate"
        field["prompt"] = "用已审核原文解释该知识点"
        field["source_excerpt"] = _first_sentence(span)
        field["not_for_official_scoring"] = True
        fields.append(field)
    fields.append(_common_mistake_hypothesis(candidate))
    fields.append(_learner_memory_event_template(candidate))
    return fields


def _question_fields(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    span = _normal_text(str(_source_ref(candidate).get("span") or ""))
    field = _base_field(candidate, "exam_patterns")
    field["pattern_type"] = "question_lane_evidence"
    field["question_excerpt"] = _first_sentence(span)
    field["knowledge_source_allowed"] = False
    return [field]


def _is_valid_reviewed_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("candidate_status") != "reviewed_candidate":
        return False
    if candidate.get("candidate_only") is not True or candidate.get("review_only") is not True:
        return False
    if candidate.get("runtime_install_allowed") is not False or candidate.get("release_truth_claimed") is not False:
        return False
    source_ref = _source_ref(candidate)
    return bool(source_ref.get("source_lane") and source_ref.get("span") and source_ref.get("span_hash"))


def _is_negative_evidence_record(record: dict[str, Any]) -> bool:
    if record.get("review_decision_status") != "recorded":
        return False
    if record.get("decision") != "reject_wrong_leaf_source":
        return False
    if record.get("candidate_only") is not True or record.get("review_only") is not True:
        return False
    if record.get("runtime_install_allowed") is not False or record.get("release_truth_claimed") is not False:
        return False
    source_candidate = _source_candidate(record)
    source_lane = str(source_candidate.get("source_lane") or "")
    return (
        source_lane in NON_QUESTION_SOURCE_LANES
        and bool(source_candidate.get("record_id"))
        and bool(source_candidate.get("span"))
        and bool(source_candidate.get("span_hash"))
    )


def _negative_evidence_field(record: dict[str, Any]) -> dict[str, Any]:
    field = _base_negative_field(record, "negative_evidence")
    field["negative_evidence_type"] = "wrong_leaf_source"
    field["rejected_leaf_id"] = record.get("leaf_id")
    field["missing_lane"] = record.get("missing_lane")
    field["review_decision"] = record.get("decision")
    field["reviewer_role"] = record.get("reviewer_role")
    field["rationale"] = record.get("rationale")
    field["positive_context_allowed"] = False
    return field


def compile_field_candidates(
    *,
    reviewed_candidates: dict[str, Any],
    semantic_evidence_audit_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = [
        candidate
        for candidate in reviewed_candidates.get("reviewed_candidates") or []
        if isinstance(candidate, dict) and _is_valid_reviewed_candidate(candidate)
    ]
    field_candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        source_lane = str(_source_ref(candidate).get("source_lane") or "")
        before = len(field_candidates)
        if source_lane == "question":
            field_candidates.extend(_question_fields(candidate))
        elif source_lane in NON_QUESTION_SOURCE_LANES:
            field_candidates.extend(_non_question_fields(candidate))
        else:
            skipped.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "leaf_id": candidate.get("leaf_id"),
                    "reason": f"unsupported_source_lane:{source_lane}",
                }
            )
        if len(field_candidates) == before:
            skipped.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "leaf_id": candidate.get("leaf_id"),
                    "reason": "no_deterministic_field_extracted",
                }
            )
    by_family = Counter(str(field.get("family")) for field in field_candidates)
    semantic_records = (
        semantic_evidence_audit_record.get("semantic_evidence_audit_records")
        if isinstance(semantic_evidence_audit_record, dict)
        else []
    )
    negative_fields = [
        _negative_evidence_field(record)
        for record in semantic_records or []
        if isinstance(record, dict) and _is_negative_evidence_record(record)
    ]
    field_candidates.extend(negative_fields)
    by_family = Counter(str(field.get("family")) for field in field_candidates)
    source_backed_count = sum(
        1
        for field in field_candidates
        if field.get("family") in SOURCE_BACKED_KNOWLEDGE_FAMILIES
        and (field.get("source_ref_trace") or {}).get("source_lane") in NON_QUESTION_SOURCE_LANES
    )
    return {
        "schema": SCHEMA,
        "reviewed_candidate_schema": reviewed_candidates.get("schema"),
        "verdict": "PASS",
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "rich_field_candidate_batch": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "summary": {
            "reviewed_candidate_count": len(candidates),
            "generated_field_candidate_count": len(field_candidates),
            "source_backed_knowledge_candidate_count": source_backed_count,
            "negative_evidence_candidate_count": by_family.get("negative_evidence", 0),
            "question_lane_exam_pattern_count": by_family.get("exam_patterns", 0),
            "skipped_candidate_count": len(skipped),
            "field_family_counts": dict(sorted(by_family.items())),
        },
        "field_candidates": field_candidates,
        "skipped_candidates": skipped,
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
    parser.add_argument("--reviewed-candidates", type=Path, default=DEFAULT_REVIEWED_CANDIDATES)
    parser.add_argument("--semantic-record", type=Path, default=DEFAULT_SEMANTIC_RECORD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = compile_field_candidates(
        reviewed_candidates=_read_json(args.reviewed_candidates),
        semantic_evidence_audit_record=_read_json(args.semantic_record),
    )
    output = args.output_dir / "rich_leaf_field_candidates.json"
    _write_json(output, report)
    print(json.dumps({"out": str(output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
