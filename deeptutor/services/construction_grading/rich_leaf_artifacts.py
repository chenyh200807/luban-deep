"""Phase 0 RichLeafArtifact schema, validator, and pack contract.

This module is intentionally not wired into production runtime. It is the fat
kernel for the Nexus-like rich leaf compiler: validate field authority, strip
candidate-only material, and build task-specific context packs. It does not
call LLMs, read/write DBs, promote release truth, or grant official score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
import unicodedata
from typing import Any


ALLOWED_CANDIDATE_STATUSES = {"candidate", "reviewed_candidate", "release_candidate", "superseded"}
CONTROLLED_DEFAULT = "controlled_default"

SOURCE_REF_REQUIRED_KEYS = {
    "source_ref_id",
    "source_registry_id",
    "source_dataset_id",
    "source_version",
    "extractor_version",
    "source_lane",
    "path",
    "record_id",
    "span",
    "span_hash",
}

SOURCE_BACKED_STATUSES = {"source_backed", "learner_evidence", "assessment_evidence"}
CANDIDATE_ONLY_STATUSES = {"candidate_only", "needs_review", "hypothesis"}

CORE_FIELD_FAMILIES = {
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "negative_evidence",
    "teaching_cards",
    "rubric_link_index",
}

TASK_FIELD_FAMILIES = {
    "grading": ("rubric_link_index", "rules", "numeric_constraints", "negative_evidence", "source_refs"),
    "tutoring": ("concepts", "definitions", "procedures", "teaching_cards", "rules", "source_refs", "common_mistakes"),
    "rag_answer": ("definitions", "rules", "procedures", "source_refs"),
    "next_action": ("teaching_cards", "exam_patterns", "common_mistakes", "learner_memory_event_templates", "source_refs"),
    "review": (
        "concepts",
        "definitions",
        "rules",
        "procedures",
        "numeric_constraints",
        "negative_evidence",
        "teaching_cards",
        "rubric_link_index",
        "common_mistakes",
        "source_refs",
    ),
}

RUBRIC_POLICY_KEYS = {
    "policy_type",
    "required_terms",
    "partial_credit_policy",
    "high_risk_flags",
    "score",
    "max_score",
}

OBSERVED_MISTAKE_AUTHORITIES = {"student_answer", "residual", "teacher_review", "teacher_final"}
HYPOTHESIZED_MISTAKE_SOURCES = {"synthetic_candidate", "council_shadow", "ai_review_suggestion"}

RICH_LEAF_ARTIFACT_V0_SCHEMA: dict[str, Any] = {
    "schema_id": "luban.rich_leaf_artifact.v0",
    "type": "object",
    "required": ["artifact_id", "leaf_id", "bundle_version", "candidate_status", "source_refs"],
    "properties": {
        "artifact_id": {"type": "string"},
        "leaf_id": {"type": "string"},
        "bundle_version": {"type": "string"},
        "candidate_status": {"type": "string", "enum": sorted(ALLOWED_CANDIDATE_STATUSES)},
        "source_refs": {"type": "array"},
        "concepts": {"type": "array"},
        "definitions": {"type": "array"},
        "rules": {"type": "array"},
        "procedures": {"type": "array"},
        "numeric_constraints": {"type": "array"},
        "negative_evidence": {"type": "array"},
        "teaching_cards": {"type": "array"},
        "rubric_link_index": {"type": "array"},
        "common_mistakes": {"type": "object"},
        "exam_patterns": {"type": "array"},
        "learner_memory_event_templates": {"type": "array"},
    },
    "forbidden_properties": ["controlled_default", "official_score_allowed", "canonical_truth_written"],
}

COMPILED_CONTEXT_PACK_V0_SCHEMA: dict[str, Any] = {
    "schema_id": "luban.compiled_context_pack.rich_leaf.v0",
    "type": "object",
    "required": ["task", "fields", "source_refs", "consumption_trace"],
    "properties": {
        "task": {"type": "string", "enum": sorted(TASK_FIELD_FAMILIES)},
        "fields": {"type": "array"},
        "source_refs": {"type": "array"},
        "consumption_trace": {"type": "object"},
        "personalization_level": {
            "type": "string",
            "enum": ["none", "generic", "evidence_backed", "teacher_final_backed"],
        },
        "canonical_write_allowed": {"const": False},
        "production_write_count": {"const": 0},
        "official_score_allowed": {"const": False},
    },
}


def normalize_source_span(raw_span: str) -> str:
    """Normalize source spans for stable hashing without deleting Chinese punctuation."""
    normalized = unicodedata.normalize("NFKC", str(raw_span or ""))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    # Keep table cell text but remove Markdown alignment marker noise.
    normalized = re.sub(r"\|?\s*:?-{3,}:?\s*(?=\||$)", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def source_span_hash(raw_span: str) -> str:
    return hashlib.sha256(normalize_source_span(raw_span).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RichLeafValidationReport:
    ok: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    accepted_field_ids: list[str] = field(default_factory=list)
    candidate_only_field_ids: list[str] = field(default_factory=list)
    rejected_field_ids: list[str] = field(default_factory=list)
    canonical_truth_written: bool = False
    official_score_allowed: bool = False
    production_write_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "accepted_field_ids": list(self.accepted_field_ids),
            "candidate_only_field_ids": list(self.candidate_only_field_ids),
            "rejected_field_ids": list(self.rejected_field_ids),
            "canonical_truth_written": self.canonical_truth_written,
            "official_score_allowed": self.official_score_allowed,
            "production_write_count": self.production_write_count,
        }


@dataclass(frozen=True)
class CompiledContextPack:
    task: str
    fields: list[dict[str, Any]]
    source_refs: list[dict[str, Any]]
    consumption_trace: dict[str, Any]
    personalization_level: str = "none"
    canonical_write_allowed: bool = False
    production_write_count: int = 0
    official_score_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "fields": list(self.fields),
            "source_refs": list(self.source_refs),
            "consumption_trace": dict(self.consumption_trace),
            "personalization_level": self.personalization_level,
            "canonical_write_allowed": self.canonical_write_allowed,
            "production_write_count": self.production_write_count,
            "official_score_allowed": self.official_score_allowed,
        }


def _field_id(field: dict[str, Any], fallback: str) -> str:
    return str(field.get("field_id") or field.get("id") or fallback)


def _claim_status(field: dict[str, Any]) -> str:
    return str(field.get("claim_status") or field.get("authority_level") or "candidate_only")


def _iter_family_fields(artifact: dict[str, Any], family: str) -> list[dict[str, Any]]:
    value = artifact.get(family)
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if family == "common_mistakes" and isinstance(value, dict):
        fields: list[dict[str, Any]] = []
        for key in ("observed_mistakes", "hypothesized_mistakes"):
            items = value.get(key) or []
            for item in items:
                if isinstance(item, dict):
                    fields.append({**item, "_mistake_group": key})
        return fields
    return []


def _source_ref_index(artifact: dict[str, Any], blockers: list[str]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for raw_ref in artifact.get("source_refs") or []:
        if not isinstance(raw_ref, dict):
            blockers.append("source_ref_malformed")
            continue
        ref_id = str(raw_ref.get("source_ref_id") or "")
        if not ref_id:
            blockers.append("source_ref_missing_id")
            continue
        missing = SOURCE_REF_REQUIRED_KEYS - set(raw_ref)
        if "source_registry_id" in missing:
            blockers.append(f"source_ref_missing_registry:{ref_id}")
        elif missing:
            blockers.append(f"source_ref_missing_required_keys:{ref_id}:{','.join(sorted(missing))}")
        if not normalize_source_span(str(raw_ref.get("span") or "")):
            blockers.append(f"source_ref_empty_span:{ref_id}")
            continue
        expected_hash = source_span_hash(str(raw_ref.get("span") or ""))
        if raw_ref.get("span_hash") and raw_ref.get("span_hash") != expected_hash:
            blockers.append(f"source_ref_span_hash_mismatch:{ref_id}")
        if not missing:
            index[ref_id] = raw_ref
    return index


def _validate_field_sources(
    *,
    family: str,
    field_obj: dict[str, Any],
    fid: str,
    source_refs: dict[str, dict[str, Any]],
    blockers: list[str],
) -> None:
    status = _claim_status(field_obj)
    if status not in SOURCE_BACKED_STATUSES:
        return
    ref_ids = [str(r) for r in field_obj.get("source_ref_ids") or []]
    if not ref_ids or any(ref_id not in source_refs for ref_id in ref_ids):
        blockers.append(f"source_backed_field_without_valid_source:{family}:{fid}")


def _validate_rubric_link(field_obj: dict[str, Any], fid: str, blockers: list[str]) -> None:
    if RUBRIC_POLICY_KEYS & set(field_obj):
        blockers.append(f"rubric_link_copies_scoring_policy:{fid}")
    required = {"scoring_artifact_id", "rubric_version", "scoring_point_ids", "link_status"}
    missing = required - set(field_obj)
    if missing:
        blockers.append(f"rubric_link_missing_required_keys:{fid}:{','.join(sorted(missing))}")


def _validate_mistake(field_obj: dict[str, Any], fid: str, blockers: list[str]) -> None:
    group = str(field_obj.get("_mistake_group") or "")
    observed_from = str(field_obj.get("observed_from") or "")
    status = _claim_status(field_obj)
    if group == "observed_mistakes" and observed_from not in OBSERVED_MISTAKE_AUTHORITIES:
        blockers.append(f"observed_mistake_from_non_authority:{observed_from}:{fid}")
    if group == "observed_mistakes" and status == "learner_evidence" and not field_obj.get("evidence_refs"):
        blockers.append(f"observed_mistake_without_learning_evidence:{fid}")
    if group == "hypothesized_mistakes":
        if observed_from not in HYPOTHESIZED_MISTAKE_SOURCES:
            blockers.append(f"hypothesized_mistake_unknown_source:{observed_from}:{fid}")
        if status != "candidate_only":
            blockers.append(f"hypothesized_mistake_not_candidate_only:{fid}")


def validate_rich_leaf_artifact(artifact: dict[str, Any]) -> RichLeafValidationReport:
    """Validate a RichLeafArtifact candidate without granting release/score authority."""
    blockers: list[str] = []
    warnings: list[str] = []
    accepted: list[str] = []
    candidate_only: list[str] = []
    rejected: list[str] = []

    if not isinstance(artifact, dict):
        return RichLeafValidationReport(ok=False, blockers=["artifact_not_dict"])

    for key in RICH_LEAF_ARTIFACT_V0_SCHEMA["required"]:
        if key not in artifact:
            blockers.append(f"artifact_missing_required:{key}")
    for key in RICH_LEAF_ARTIFACT_V0_SCHEMA["forbidden_properties"]:
        if key in artifact:
            blockers.append(f"artifact_forbidden_property:{key}")

    candidate_status = str(artifact.get("candidate_status") or artifact.get("lifecycle_status") or "")
    if candidate_status == CONTROLLED_DEFAULT or artifact.get(CONTROLLED_DEFAULT) is True:
        blockers.append("artifact_self_declared_controlled_default")
    if candidate_status and candidate_status not in ALLOWED_CANDIDATE_STATUSES:
        blockers.append(f"candidate_status_unknown:{candidate_status}")
    if "lifecycle_status" in artifact:
        warnings.append("legacy_lifecycle_status_seen_use_candidate_status")

    source_refs = _source_ref_index(artifact, blockers)

    for family in sorted(CORE_FIELD_FAMILIES | {"common_mistakes", "exam_patterns", "learner_memory_event_templates"}):
        for idx, field_obj in enumerate(_iter_family_fields(artifact, family)):
            fid = _field_id(field_obj, f"{family}_{idx}")
            status = _claim_status(field_obj)
            if family == "rubric_link_index":
                _validate_rubric_link(field_obj, fid, blockers)
            if family == "common_mistakes":
                _validate_mistake(field_obj, fid, blockers)
            if not (family == "common_mistakes" and _claim_status(field_obj) == "learner_evidence"):
                _validate_field_sources(
                    family=family,
                    field_obj=field_obj,
                    fid=fid,
                    source_refs=source_refs,
                    blockers=blockers,
                )
            if status in CANDIDATE_ONLY_STATUSES:
                candidate_only.append(fid)
            elif status in SOURCE_BACKED_STATUSES:
                accepted.append(fid)
            else:
                rejected.append(fid)
                blockers.append(f"field_unknown_claim_status:{family}:{fid}:{status}")

    return RichLeafValidationReport(
        ok=not blockers,
        blockers=blockers,
        warnings=warnings,
        accepted_field_ids=accepted,
        candidate_only_field_ids=candidate_only,
        rejected_field_ids=rejected,
        canonical_truth_written=False,
        official_score_allowed=False,
        production_write_count=0,
    )


def _pack_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_compiled_context_pack(
    *,
    task: str,
    artifacts: list[dict[str, Any]],
    bundle_version: str,
    manifest_hash: str,
    personalization_level: str = "none",
) -> CompiledContextPack:
    """Build a task-specific context pack from validated rich leaf candidates.

    Candidate-only fields are stripped from positive context. Invalid artifacts
    fail closed by contributing rejected ids and reasons, not positive fields.
    """
    if task not in TASK_FIELD_FAMILIES:
        raise ValueError(f"unknown rich leaf context task: {task}")

    allowed_families = set(TASK_FIELD_FAMILIES[task])
    fields: list[dict[str, Any]] = []
    source_refs: list[dict[str, Any]] = []
    consumed: list[str] = []
    review_candidates: list[str] = []
    stripped: list[str] = []
    rejected: list[str] = []
    fail_closed_reasons: list[str] = []
    seen_sources: set[str] = set()

    for artifact in artifacts:
        report = validate_rich_leaf_artifact(artifact)
        if not report.ok:
            rejected.extend(report.rejected_field_ids)
            fail_closed_reasons.extend(report.blockers)
            continue

        source_refs_by_id = {
            str(src.get("source_ref_id")): src
            for src in artifact.get("source_refs") or []
            if isinstance(src, dict) and src.get("source_ref_id")
        }

        for family in allowed_families - {"source_refs"}:
            for field_obj in _iter_family_fields(artifact, family):
                fid = _field_id(field_obj, family)
                status = _claim_status(field_obj)
                if status in CANDIDATE_ONLY_STATUSES:
                    if task == "review":
                        fields.append({k: v for k, v in field_obj.items() if not k.startswith("_")})
                        review_candidates.append(fid)
                        if "source_refs" in allowed_families:
                            for ref_id in field_obj.get("source_ref_ids") or []:
                                ref = source_refs_by_id.get(str(ref_id))
                                if ref and str(ref_id) not in seen_sources:
                                    seen_sources.add(str(ref_id))
                                    source_refs.append(ref)
                        continue
                    stripped.append(fid)
                    continue
                if status not in SOURCE_BACKED_STATUSES:
                    rejected.append(fid)
                    continue
                fields.append({k: v for k, v in field_obj.items() if not k.startswith("_")})
                consumed.append(fid)
                if "source_refs" in allowed_families:
                    for ref_id in field_obj.get("source_ref_ids") or []:
                        ref = source_refs_by_id.get(str(ref_id))
                        if ref and str(ref_id) not in seen_sources:
                            seen_sources.add(str(ref_id))
                            source_refs.append(ref)

        # Candidate-only fields outside the selected task still need traceability when present.
        for family in set(TASK_FIELD_FAMILIES["next_action"]) | {"common_mistakes", "teaching_cards"}:
            if family in allowed_families:
                continue
            for field_obj in _iter_family_fields(artifact, family):
                fid = _field_id(field_obj, family)
                if _claim_status(field_obj) in CANDIDATE_ONLY_STATUSES and fid not in stripped:
                    stripped.append(fid)

    trace_payload = {
        "bundle_version": bundle_version,
        "manifest_hash": manifest_hash,
        "consumed_field_ids": sorted(set(consumed)),
        "review_candidate_field_ids": sorted(set(review_candidates)),
        "stripped_candidate_field_ids": sorted(set(stripped)),
        "rejected_field_ids": sorted(set(rejected)),
        "fail_closed_reasons": sorted(set(fail_closed_reasons)),
        "canonical_write_allowed": False,
        "production_write_count": 0,
    }
    trace_payload["pack_hash"] = _pack_hash({"task": task, "fields": fields, "trace": trace_payload})

    return CompiledContextPack(
        task=task,
        fields=fields,
        source_refs=source_refs,
        consumption_trace=trace_payload,
        personalization_level=personalization_level,
        canonical_write_allowed=False,
        production_write_count=0,
        official_score_allowed=False,
    )
