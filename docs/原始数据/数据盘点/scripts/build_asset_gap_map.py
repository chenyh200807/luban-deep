#!/usr/bin/env python3
"""Build an AI-readable gap map from source ledgers and authority maps."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS_ROOT = INVENTORY_ROOT / "extractions"
DEFAULT_DATA_ASSET_BRIEF = EXTRACTIONS_ROOT / "data_asset_brief_v1" / "manifest.json"
DEFAULT_ASSET_BUCKETS = EXTRACTIONS_ROOT / "data_asset_brief_v1" / "asset_buckets.json"
DEFAULT_JSON_LEDGER = EXTRACTIONS_ROOT / "json_source_ledger_v0" / "manifest.json"
DEFAULT_JSON_SOURCES = EXTRACTIONS_ROOT / "json_source_ledger_v0" / "sources.jsonl"
DEFAULT_PDF_LEDGER = EXTRACTIONS_ROOT / "pdf_source_ledger_v1" / "manifest.json"
DEFAULT_PDF_SOURCES = EXTRACTIONS_ROOT / "pdf_source_ledger_v1" / "pdf_sources.jsonl"
DEFAULT_OKF_SCOPE = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "manifest.json"
DEFAULT_OKF_ALIGNMENT = EXTRACTIONS_ROOT / "okf_source_alignment_v0" / "report.json"
DEFAULT_OKF_CASE_ALIGNMENT = EXTRACTIONS_ROOT / "okf_source_alignment_v0" / "case_alignment.jsonl"
DEFAULT_COMPILED_AUTHORITY = EXTRACTIONS_ROOT / "compiled_asset_authority_map_v1" / "manifest.json"
DEFAULT_RUNTIME_POINTERS = EXTRACTIONS_ROOT / "compiled_asset_authority_map_v1" / "runtime_pointers.jsonl"
DEFAULT_OUTPUT_ROOT = EXTRACTIONS_ROOT / "asset_gap_map_v1"
OUTPUT_ROOT_SUFFIX = ("extractions", "asset_gap_map_v1")
SENTINEL_NAME = ".asset_gap_map_generated.json"

RUNTIME_GUARD = {
    "release_stage": "asset_gap_map_only",
    "runtime_consumable": False,
    "installed_runtime_supply": False,
    "canonical_write_allowed": False,
    "learner_truth_write_allowed": False,
    "gbrain_write_allowed": False,
    "production_registry_write_allowed": False,
    "official_score_allowed": False,
}

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
MAX_PAYLOAD_METADATA_BYTES = 10 * 1024 * 1024


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def display_path(path: Path) -> str:
    try:
        return rel(path)
    except ValueError:
        return str(path)


def resolve_soft(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def has_suffix(path: Path, suffix: tuple[str, ...]) -> bool:
    return tuple(path.parts[-len(suffix) :]) == suffix


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"required input not found: {display_path(path)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON input: {display_path(path)}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid JSON object input: {display_path(path)}")
    return data


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"required input not found: {display_path(path)}")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL input at {display_path(path)}:{line_no}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"invalid JSONL object at {display_path(path)}:{line_no}")
        rows.append(data)
    return rows


def guard_is_closed(data: dict[str, Any], path: Path) -> None:
    guard = data.get("runtime_guard") or {}
    required_false = [
        "runtime_consumable",
        "canonical_write_allowed",
        "learner_truth_write_allowed",
        "gbrain_write_allowed",
        "production_registry_write_allowed",
        "official_score_allowed",
    ]
    for key in required_false:
        if guard.get(key) is not False:
            raise ValueError(f"invalid runtime guard {key}: {display_path(path)}")


def validate_manifest(data: dict[str, Any], path: Path, schema: str, authority_status: str | None = None) -> None:
    if data.get("schema") != schema:
        raise ValueError(f"invalid schema for {display_path(path)}")
    if authority_status is not None and data.get("authority_status") != authority_status:
        raise ValueError(f"invalid authority for {display_path(path)}")
    guard_is_closed(data, path)


def validate_output_root(path: Path) -> None:
    resolved = resolve_soft(path)
    controlled_roots = {
        EXTRACTIONS_ROOT.resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        EXTRACTIONS_ROOT.resolve(),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if not any(is_relative_to(resolved, root) for root in controlled_roots):
        raise ValueError(f"unsafe output root outside controlled roots: {display_path(path)}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def load_sentinel(path: Path) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}") from exc
    if (
        sentinel.get("generated_by") != "build_asset_gap_map.py"
        or sentinel.get("kind") != "asset_gap_map"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {
        "manifest.json",
        "gap_summary.json",
        "gap_items.jsonl",
        "action_queues.json",
        "next_actions.json",
        "summary.md",
        SENTINEL_NAME,
    }
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "asset_gap_map",
        "generated_by": "build_asset_gap_map.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def compact_pdf_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pdf_id": row["pdf_id"],
        "source_path": row["source_path"],
        "category": row["category"],
        "compilation_status": row["compilation_status"],
        "priority": row["priority"],
        "recommended_next_action": row["recommended_next_action"],
        "candidate_structured_derivative_refs": row.get("candidate_structured_derivative_refs") or [],
        "sha256": (row.get("file") or {}).get("sha256"),
    }


def compact_json_source_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": row["source_id"],
        "source_path": row["source_path"],
        "bucket": row["bucket"],
        "source_claim_reviewed": row.get("source_claim_reviewed"),
        "authority_status": row.get("authority_status"),
        "json_shape": row.get("json_shape"),
        "sha256": (row.get("file") or {}).get("sha256"),
    }


def compact_case_alignment(row: dict[str, Any]) -> dict[str, Any]:
    sub = row.get("subquestion_alignment") or {}
    return {
        "case_id": row["case_id"],
        "year": row["year"],
        "case_no": row["case_no"],
        "alignment_status": row["alignment_status"],
        "subquestion_alignment_status": sub.get("status"),
        "target_sub_questions": sub.get("target_sub_questions") or row.get("target", {}).get("sub_questions"),
        "target": row.get("target"),
        "question_chunk": row.get("question_chunk"),
        "exam_source": row.get("exam_source"),
    }


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(Counter(str(row.get(key)) for row in rows).most_common())


def source_path_to_path(source_path: str | None) -> Path | None:
    if not source_path:
        return None
    path = Path(source_path)
    return path if path.is_absolute() else REPO_ROOT / path


def payload_metadata(row: dict[str, Any]) -> dict[str, Any]:
    pointer_path = source_path_to_path(row.get("source_path"))
    if pointer_path is None:
        return {"payload_manifest_status": "missing_pointer_path"}
    candidates: list[Path] = []
    bundle_path = row.get("bundle_path")
    if isinstance(bundle_path, str) and bundle_path:
        candidates.append(pointer_path.parent / bundle_path)
    namespace = row.get("namespace")
    if isinstance(namespace, str) and namespace:
        candidates.append(pointer_path.parent / f"{namespace}.json")
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        if candidate.stat().st_size > MAX_PAYLOAD_METADATA_BYTES:
            return {
                "payload_path": display_path(candidate),
                "payload_manifest_status": "payload_too_large_for_gap_map_metadata",
                "payload_manifest_published": None,
                "payload_manifest_content_hash": None,
            }
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {
                "payload_path": display_path(candidate),
                "payload_manifest_status": "payload_json_parse_error",
                "payload_manifest_published": None,
                "payload_manifest_content_hash": None,
            }
        if not isinstance(payload, dict):
            return {
                "payload_path": display_path(candidate),
                "payload_manifest_status": "payload_not_object",
                "payload_manifest_published": None,
                "payload_manifest_content_hash": None,
            }
        manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else payload
        return {
            "payload_path": display_path(candidate),
            "payload_manifest_status": str(manifest.get("status") or "unknown"),
            "payload_manifest_published": manifest.get("published"),
            "payload_manifest_content_hash": manifest.get("content_hash") or manifest.get("expected_content_hash"),
        }
    return {
        "payload_manifest_status": "not_found_by_gap_map",
        "payload_manifest_published": None,
        "payload_manifest_content_hash": None,
    }


def hash_gate_status(row: dict[str, Any], metadata: dict[str, Any]) -> str:
    pointer_hash = row.get("content_hash")
    payload_hash = metadata.get("payload_manifest_content_hash")
    if isinstance(pointer_hash, str) and pointer_hash and isinstance(payload_hash, str) and payload_hash:
        return "matches" if pointer_hash == payload_hash else "mismatch"
    if row.get("requires_hash_gate") is True:
        return "unverified"
    return "not_required"


def runtime_gap_kind(row: dict[str, Any], metadata: dict[str, Any]) -> str:
    if row.get("runtime_bundle") == "v_case_rubric_scored":
        return "policy_conflict_live_reader"
    if row.get("runtime_read_allowed") is True:
        if metadata.get("payload_manifest_published") is False:
            return "published_pointer_payload_manifest_conflict"
        return "published_pointer_no_consumer_evidence"
    return "candidate_not_runtime_default"


def compact_runtime_pointer(row: dict[str, Any]) -> dict[str, Any]:
    metadata = payload_metadata(row)
    gap_kind = runtime_gap_kind(row, metadata)
    consumer_evidence_status = "policy_conflict_live_reader" if gap_kind == "policy_conflict_live_reader" else "none"
    return {
        "namespace": row.get("namespace"),
        "runtime_bundle": row.get("runtime_bundle"),
        "source_path": row.get("source_path"),
        "gap_kind": gap_kind,
        "consumer_status": row.get("consumer_status"),
        "consumer_evidence_status": consumer_evidence_status,
        "hash_gate_status": hash_gate_status(row, metadata),
        "runtime_read_allowed": row.get("runtime_read_allowed"),
        "pointer_published": row.get("published"),
        "payload_manifest_published": metadata.get("payload_manifest_published"),
        "payload_manifest_status": metadata.get("payload_manifest_status"),
        "payload_manifest_content_hash": metadata.get("payload_manifest_content_hash"),
        "payload_path": metadata.get("payload_path"),
        "status": row.get("status"),
        "requires_hash_gate": row.get("requires_hash_gate"),
        "content_hash": row.get("content_hash"),
        "schema_version": row.get("schema_version"),
        "signature_present": row.get("signature_present"),
        "rollback_pointer": row.get("rollback_pointer"),
        "policy_conflict_live_reader": gap_kind == "policy_conflict_live_reader",
        "live_reader_evidence": (
            {
                "source_path": "deeptutor/services/construction_grading/rubric_grader_v1.py",
                "slot": "legacy",
                "runtime_bundle": "v_case_rubric_scored",
                "env_var": "LUBAN_CASE_RUBRIC_BANK_SLOT",
                "default_slot": "legacy",
            }
            if gap_kind == "policy_conflict_live_reader"
            else None
        ),
    }


def find_asset_bucket(asset_buckets: dict[str, Any], bucket_id: str) -> dict[str, Any]:
    if asset_buckets.get("schema") != "luban_data_asset_buckets.v1":
        raise ValueError("invalid schema for asset_buckets.json")
    for row in asset_buckets.get("asset_buckets") or []:
        if row.get("id") == bucket_id:
            return row
    raise ValueError(f"asset bucket not found: {bucket_id}")


def build_exam_content_gaps(asset_buckets: dict[str, Any]) -> list[dict[str, Any]]:
    exam = find_asset_bucket(asset_buckets, "exam_cleaned_json")
    metrics = exam.get("metrics") or {}
    case_questions = int(metrics.get("case_questions") or 0)
    analysis_nonempty = int(metrics.get("case_analysis_nonempty") or 0)
    score_nonnull = int(metrics.get("case_score_nonnull") or 0)
    return [
        {
            "field": "taxonomy_missing_chunks",
            "missing_count": int(metrics.get("taxonomy_missing_chunks") or 0),
            "unit": "chunk",
            "recommended_next_action": "map remaining exam chunks to taxonomy nodes or mark out-of-scope with evidence",
        },
        {
            "field": "case_analysis_missing",
            "missing_count": max(case_questions - analysis_nonempty, 0),
            "unit": "case_question",
            "recommended_next_action": "backfill or verify case analysis from source evidence before teaching/rubric use",
        },
        {
            "field": "case_score_missing",
            "missing_count": max(case_questions - score_nonnull, 0),
            "unit": "case_question",
            "recommended_next_action": "backfill case score candidates from rubric/source evidence; keep official_score_allowed=false",
        },
    ]


def make_gap_item(
    gap_id: str,
    area: str,
    priority: str,
    title: str,
    affected_count: int,
    source_paths: list[str],
    evidence: dict[str, Any],
    llm_role: str,
    deterministic_gate: str,
    recommended_next_action: str,
    blocks: list[str],
) -> dict[str, Any]:
    return {
        "schema": "luban_asset_gap_item.v1",
        "gap_id": gap_id,
        "area": area,
        "priority": priority,
        "status": "open" if affected_count else "closed",
        "title": title,
        "affected_count": affected_count,
        "source_paths": source_paths,
        "evidence": evidence,
        "llm_role": llm_role,
        "deterministic_gate": deterministic_gate,
        "recommended_next_action": recommended_next_action,
        "blocks": blocks,
        "runtime_guard": RUNTIME_GUARD,
    }


def build_action_queues(
    asset_buckets: dict[str, Any],
    json_rows: list[dict[str, Any]],
    pdf_rows: list[dict[str, Any]],
    case_rows: list[dict[str, Any]],
    runtime_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    json_unreviewed = [
        compact_json_source_record(row)
        for row in json_rows
        if row.get("source_claim_reviewed") is not True
    ]
    pdf_p1 = [compact_pdf_record(row) for row in pdf_rows if row.get("priority") == "P1_compile_or_map"]
    pdf_p2_verify = [compact_pdf_record(row) for row in pdf_rows if row.get("priority") == "P2_verify_provenance"]
    pdf_p2_compile = [compact_pdf_record(row) for row in pdf_rows if row.get("priority") == "P2_compile_if_needed"]
    case_level = [
        compact_case_alignment(row)
        for row in case_rows
        if (row.get("subquestion_alignment") or {}).get("status") == "case_level_only"
    ]
    published_runtime = [
        compact_runtime_pointer(row)
        for row in runtime_rows
        if row.get("consumer_status") == "published_runtime_supply_hash_gated"
    ]
    blocked_runtime = [
        compact_runtime_pointer(row)
        for row in runtime_rows
        if row.get("runtime_read_allowed") is not True
    ]
    policy_conflict_runtime = [
        row for row in blocked_runtime if row.get("gap_kind") == "policy_conflict_live_reader"
    ]
    return {
        "schema": "luban_asset_gap_action_queues.v1",
        "queues": {
            "exam_content_gap": build_exam_content_gaps(asset_buckets),
            "json_source_claim_review_backlog": json_unreviewed,
            "pdf_p1_compile_or_map": pdf_p1,
            "pdf_p2_verify_provenance": pdf_p2_verify,
            "pdf_p2_compile_if_needed": pdf_p2_compile,
            "okf_case_level_alignment_backfill": case_level,
            "runtime_published_pointer_consumer_evidence": published_runtime,
            "runtime_policy_conflict_live_reader": policy_conflict_runtime,
            "runtime_blocked_or_candidate_pointer_review": blocked_runtime,
        },
        "runtime_guard": RUNTIME_GUARD,
    }


def build_gap_items(
    asset_buckets: dict[str, Any],
    json_ledger: dict[str, Any],
    pdf_manifest: dict[str, Any],
    okf_scope: dict[str, Any],
    okf_alignment: dict[str, Any],
    compiled_authority: dict[str, Any],
    action_queues: dict[str, Any],
) -> list[dict[str, Any]]:
    queues = action_queues["queues"]
    json_counts = json_ledger.get("counts") or {}
    pdf_counts = pdf_manifest.get("counts") or {}
    okf_counts = okf_scope.get("counts") or {}
    alignment_counts = okf_alignment.get("counts") or {}
    runtime_counts = compiled_authority.get("counts") or {}
    exam_gap_units = sum(row["missing_count"] for row in queues["exam_content_gap"])
    items = [
        make_gap_item(
            gap_id="exam_content_gap",
            area="exam_source",
            priority="P1",
            title="Structured exam JSON still has taxonomy, analysis, and score content gaps",
            affected_count=exam_gap_units,
            source_paths=["data_asset_brief_v1/asset_buckets.json"],
            evidence={
                "gap_units": queues["exam_content_gap"],
                "exam_bucket": find_asset_bucket(asset_buckets, "exam_cleaned_json"),
            },
            llm_role="propose candidate taxonomy links, analysis backfill, and score backfill from source evidence",
            deterministic_gate="source chunk evidence, rubric refs, score cap validation, official_score_allowed remains false",
            recommended_next_action="Backfill exam taxonomy/analysis/score candidate gaps before signed grading release.",
            blocks=["signed_case_rubric_release", "deep_exam_context_quality"],
        ),
        make_gap_item(
            gap_id="json_source_claim_review_gap",
            area="json_source",
            priority="P2",
            title="Cleaned JSON sources are indexed but source claims are not reviewed",
            affected_count=len(queues["json_source_claim_review_backlog"]),
            source_paths=["json_source_ledger_v0/manifest.json", "json_source_ledger_v0/sources.jsonl"],
            evidence={
                "json_sources": json_counts.get("json_sources"),
                "by_bucket": count_by(queues["json_source_claim_review_backlog"], "bucket"),
                "source_claim_reviewed_false": len(queues["json_source_claim_review_backlog"]),
            },
            llm_role="summarize source claims and flag likely source/type mismatches",
            deterministic_gate="file hash, source path, bucket policy, schema shape, human or scripted claim review",
            recommended_next_action="Review source claims by bucket, prioritizing exam, standard, textbook, and taxonomy before lectures.",
            blocks=["signed_source_lineage", "source_laundering_prevention"],
        ),
        make_gap_item(
            gap_id="pdf_p1_compile_or_map",
            area="pdf_source",
            priority="P1",
            title="P1 PDFs still need compile or PDF->JSON mapping",
            affected_count=len(queues["pdf_p1_compile_or_map"]),
            source_paths=["pdf_source_ledger_v1/manifest.json", "pdf_source_ledger_v1/pdf_sources.jsonl"],
            evidence={
                "by_category": count_by(queues["pdf_p1_compile_or_map"], "category"),
                "by_compilation_status": count_by(queues["pdf_p1_compile_or_map"], "compilation_status"),
                "ledger_counts": {
                    "pdf_sources": pdf_counts.get("pdf_sources"),
                    "needs_compilation_or_mapping": pdf_counts.get("needs_compilation_or_mapping"),
                },
            },
            llm_role="extract or propose candidate full_text/chunks/mappings for compiler review",
            deterministic_gate="source hash, page/chunk provenance, schema validation, OCR quality or mapping proof",
            recommended_next_action="Run PDF compiler or mapping workflow for the P1 queue before any release signing.",
            blocks=["full_okf_runtime_release", "complete_pdf_context_recall"],
        ),
        make_gap_item(
            gap_id="pdf_p2_verify_provenance",
            area="pdf_source",
            priority="P2",
            title="Candidate PDF derivatives need one-to-one provenance verification",
            affected_count=len(queues["pdf_p2_verify_provenance"]),
            source_paths=["pdf_source_ledger_v1/pdf_sources.jsonl"],
            evidence={
                "candidate_structured_derivative_refs_available": pdf_counts.get(
                    "candidate_structured_derivative_refs_available"
                ),
                "by_category": count_by(queues["pdf_p2_verify_provenance"], "category"),
            },
            llm_role="summarize likely derivative links and flag suspicious source mismatches",
            deterministic_gate="PDF hash, derivative JSON hash, page/chunk anchors, manual or scripted provenance proof",
            recommended_next_action="Backfill PDF->JSON provenance map for candidate derivatives.",
            blocks=["signed_source_lineage", "source_laundering_prevention"],
        ),
        make_gap_item(
            gap_id="okf_case_level_alignment_backfill",
            area="okf_source_alignment",
            priority="P1",
            title="OKF cases with case-level-only alignment need sub-question evidence",
            affected_count=len(queues["okf_case_level_alignment_backfill"]),
            source_paths=["okf_source_alignment_v0/report.json", "okf_source_alignment_v0/case_alignment.jsonl"],
            evidence={
                "target_cases": alignment_counts.get("target_cases"),
                "aligned_cases": alignment_counts.get("aligned_cases"),
                "ordinal_subquestion_matches": alignment_counts.get("ordinal_subquestion_matches"),
                "case_level_only": alignment_counts.get("case_level_only"),
            },
            llm_role="propose sub-question splits and candidate source anchors",
            deterministic_gate="case/sub-question count, source chunk anchors, rubric refs, score cap validation",
            recommended_next_action="Backfill sub-question-level source alignment for the 16 case-level-only cases.",
            blocks=["signed_case_rubric_release", "official_score_candidate_gate"],
        ),
        make_gap_item(
            gap_id="okf_candidate_not_signed_release",
            area="okf_release",
            priority="P1",
            title="OKF source-layer candidate is complete but not signed release",
            affected_count=int(okf_counts.get("cases") or 0),
            source_paths=["okf_candidate_scope_v0/manifest.json", "okf_candidate_scope_v0/scoring_points.jsonl"],
            evidence={
                "candidate_cases": okf_counts.get("cases"),
                "candidate_rubrics": okf_counts.get("rubrics"),
                "candidate_scoring_points": okf_counts.get("scoring_points"),
                "status": okf_scope.get("status"),
                "authority_status": okf_scope.get("authority_status"),
            },
            llm_role="critique and improve candidate rubric/scoring-point organization",
            deterministic_gate="schema validation, source verification, adversarial scoring guard, signed release pointer",
            recommended_next_action="Create signed release-candidate review pack; do not promote candidate scope directly.",
            blocks=["official_score_authority", "runtime_default_case_grading"],
        ),
        make_gap_item(
            gap_id="runtime_policy_conflict_live_reader",
            area="runtime_supply",
            priority="P1",
            title="Runtime reader can load a pointer that authority map marks non-readable",
            affected_count=len(queues["runtime_policy_conflict_live_reader"]),
            source_paths=[
                "compiled_asset_authority_map_v1/runtime_pointers.jsonl",
                "deeptutor/services/construction_grading/rubric_grader_v1.py",
            ],
            evidence={
                "policy_conflict_rows": queues["runtime_policy_conflict_live_reader"],
                "why": "v_case_rubric_scored is runtime_read_allowed=false, but rubric_grader_v1 default slot is legacy.",
            },
            llm_role="explain the authority conflict and propose a migration or fail-closed plan",
            deterministic_gate="reader default, pointer policy, hash/schema gate, rollback behavior, and test evidence agree",
            recommended_next_action="Decide whether to publish/sign the bank or change the reader default to a published pointer path.",
            blocks=["single_runtime_authority", "official_score_readiness_claim"],
        ),
        make_gap_item(
            gap_id="runtime_published_pointer_consumer_evidence",
            area="runtime_supply",
            priority="P2",
            title="Published runtime pointers still need consumer-level evidence",
            affected_count=len(queues["runtime_published_pointer_consumer_evidence"]),
            source_paths=["compiled_asset_authority_map_v1/runtime_pointers.jsonl"],
            evidence={
                "published_runtime_pointers": runtime_counts.get("published_runtime_pointers"),
                "namespaces": [
                    row.get("namespace") for row in queues["runtime_published_pointer_consumer_evidence"]
                ],
                "by_gap_kind": count_by(queues["runtime_published_pointer_consumer_evidence"], "gap_kind"),
                "by_hash_gate_status": count_by(queues["runtime_published_pointer_consumer_evidence"], "hash_gate_status"),
                "evidence_gap": "pointer is hash-gated, but this map has no true consumer trace evidence",
            },
            llm_role="summarize runtime packet intent and review consumer evidence",
            deterministic_gate="consumer smoke/trace, hash match, schema gate, rollback verification",
            recommended_next_action="For each published pointer, run or record a true consumer read proof before calling it runtime-ready.",
            blocks=["runtime_readiness_claim", "production_consumer_claim"],
        ),
        make_gap_item(
            gap_id="runtime_candidate_or_blocked_pointers",
            area="runtime_supply",
            priority="P2",
            title="Runtime supply has candidate or blocked pointers not allowed as defaults",
            affected_count=len(queues["runtime_blocked_or_candidate_pointer_review"]),
            source_paths=["compiled_asset_authority_map_v1/runtime_pointers.jsonl"],
            evidence={
                "blocked_or_candidate_runtime_pointers": runtime_counts.get("blocked_or_candidate_runtime_pointers"),
                "by_consumer_status": count_by(queues["runtime_blocked_or_candidate_pointer_review"], "consumer_status"),
                "by_gap_kind": count_by(queues["runtime_blocked_or_candidate_pointer_review"], "gap_kind"),
            },
            llm_role="review candidate bundle purpose and decide whether it deserves promotion or archival",
            deterministic_gate="published flag, content hash, schema, signed owner decision, rollback pointer",
            recommended_next_action="Review candidate/blocked pointers one by one; publish only via signed gate.",
            blocks=["runtime_default_claim", "single_authority_runtime_supply"],
        ),
    ]
    return sorted(items, key=lambda row: (PRIORITY_ORDER[row["priority"]], row["gap_id"]))


def build_next_actions(gap_items: list[dict[str, Any]]) -> dict[str, Any]:
    action_ids = [
        "exam_content_gap",
        "pdf_p1_compile_or_map",
        "okf_case_level_alignment_backfill",
        "okf_candidate_not_signed_release",
        "runtime_policy_conflict_live_reader",
        "runtime_published_pointer_consumer_evidence",
        "pdf_p2_verify_provenance",
        "json_source_claim_review_gap",
        "runtime_candidate_or_blocked_pointers",
    ]
    by_id = {item["gap_id"]: item for item in gap_items}
    actions = []
    for order, action_id in enumerate(action_ids, start=1):
        item = by_id[action_id]
        actions.append(
            {
                "order": order,
                "gap_id": action_id,
                "priority": item["priority"],
                "affected_count": item["affected_count"],
                "action": item["recommended_next_action"],
                "pass_criteria": item["deterministic_gate"],
                "must_not_do": [
                    "do not write runtime_supply",
                    "do not claim official score",
                    "do not write LearnerState/GBrain/production registry",
                ],
            }
        )
    return {
        "schema": "luban_asset_gap_next_actions.v1",
        "principle": "LLMs maintain candidate knowledge organization; deterministic gates sign releases and protect authority.",
        "actions": actions,
        "runtime_guard": RUNTIME_GUARD,
    }


def render_summary(manifest: dict[str, Any], gap_items: list[dict[str, Any]], action_queues: dict[str, Any]) -> str:
    counts = manifest["counts"]
    queues = action_queues["queues"]
    lines = [
        "# Asset Gap Map v1",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Authority: gap map only; not runtime supply, not official score authority.",
        f"- Open gap items: **{counts['open_gap_items']:,}**",
        f"- P1 gap items: **{counts['by_priority'].get('P1', 0):,}**",
        "",
        "## Action Queues",
        "",
        "| Queue | Count | Why it matters |",
        "|---|---:|---|",
        f"| `pdf_p1_compile_or_map` | {len(queues['pdf_p1_compile_or_map']):,} | PDF full text/chunk or PDF->JSON map is still missing. |",
        f"| `json_source_claim_review_backlog` | {len(queues['json_source_claim_review_backlog']):,} | JSON source claims are indexed but not reviewed. |",
        f"| `exam_content_gap` | {sum(row['missing_count'] for row in queues['exam_content_gap']):,} | Exam JSON still has taxonomy, analysis, and score gaps. |",
        f"| `pdf_p2_verify_provenance` | {len(queues['pdf_p2_verify_provenance']):,} | Candidate derivatives exist but need one-to-one source proof. |",
        f"| `okf_case_level_alignment_backfill` | {len(queues['okf_case_level_alignment_backfill']):,} | OKF cases are source-aligned only at case level, not sub-question level. |",
        f"| `runtime_published_pointer_consumer_evidence` | {len(queues['runtime_published_pointer_consumer_evidence']):,} | Published pointers need true consumer read evidence. |",
        f"| `runtime_policy_conflict_live_reader` | {len(queues['runtime_policy_conflict_live_reader']):,} | Runtime reader and pointer policy disagree. |",
        f"| `runtime_blocked_or_candidate_pointer_review` | {len(queues['runtime_blocked_or_candidate_pointer_review']):,} | Candidate/blocked runtime pointers cannot become defaults without signing. |",
        "",
        "## Gap Items",
        "",
        "| Gap | Priority | Area | Count | Blocks |",
        "|---|---|---|---:|---|",
    ]
    for item in gap_items:
        lines.append(
            f"| `{item['gap_id']}` | {item['priority']} | {item['area']} | {item['affected_count']:,} | {', '.join(item['blocks'])} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- This map may route work to compiler/review skills, but it cannot sign release artifacts.",
            "- Candidate OKF scope remains candidate-only until deterministic validators and owner signing pass.",
            "- Published runtime pointers still require consumer-level evidence before production readiness claims.",
            "- PDF derivative links remain candidate evidence until provenance is verified.",
            "",
        ]
    )
    return "\n".join(lines)


def build_asset_gap_map(
    data_asset_brief_path: Path = DEFAULT_DATA_ASSET_BRIEF,
    asset_buckets_path: Path = DEFAULT_ASSET_BUCKETS,
    json_ledger_path: Path = DEFAULT_JSON_LEDGER,
    json_sources_path: Path = DEFAULT_JSON_SOURCES,
    pdf_ledger_path: Path = DEFAULT_PDF_LEDGER,
    pdf_sources_path: Path = DEFAULT_PDF_SOURCES,
    okf_scope_path: Path = DEFAULT_OKF_SCOPE,
    okf_alignment_path: Path = DEFAULT_OKF_ALIGNMENT,
    okf_case_alignment_path: Path = DEFAULT_OKF_CASE_ALIGNMENT,
    compiled_authority_path: Path = DEFAULT_COMPILED_AUTHORITY,
    runtime_pointers_path: Path = DEFAULT_RUNTIME_POINTERS,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_output_root(output_root)
    assert_generated_tree(output_root)

    data_asset_brief = load_json(data_asset_brief_path)
    asset_buckets = load_json(asset_buckets_path)
    json_ledger = load_json(json_ledger_path)
    json_rows = load_jsonl(json_sources_path)
    pdf_manifest = load_json(pdf_ledger_path)
    pdf_rows = load_jsonl(pdf_sources_path)
    okf_scope = load_json(okf_scope_path)
    okf_alignment = load_json(okf_alignment_path)
    okf_case_rows = load_jsonl(okf_case_alignment_path)
    compiled_authority = load_json(compiled_authority_path)
    runtime_rows = load_jsonl(runtime_pointers_path)

    validate_manifest(data_asset_brief, data_asset_brief_path, "luban_data_asset_brief_manifest.v1", "asset_inventory_only")
    if asset_buckets.get("schema") != "luban_data_asset_buckets.v1":
        raise ValueError(f"invalid schema for {display_path(asset_buckets_path)}")
    validate_manifest(json_ledger, json_ledger_path, "luban_json_source_ledger_manifest.v0", "raw_evidence_ledger")
    validate_manifest(pdf_manifest, pdf_ledger_path, "luban_pdf_source_ledger_manifest.v1", "raw_pdf_evidence_ledger")
    validate_manifest(okf_scope, okf_scope_path, "luban_okf_candidate_scope_manifest.v0", "candidate_review")
    if okf_alignment.get("schema") != "luban_okf_source_alignment_report.v0":
        raise ValueError(f"invalid schema for {display_path(okf_alignment_path)}")
    guard_is_closed(okf_alignment, okf_alignment_path)
    validate_manifest(
        compiled_authority,
        compiled_authority_path,
        "luban_compiled_asset_authority_map_manifest.v1",
        "compiled_asset_authority_map_only",
    )
    if len(json_rows) != int((json_ledger.get("counts") or {}).get("json_sources") or -1):
        raise ValueError(f"JSON source row count does not match manifest: {display_path(json_sources_path)}")
    if len(pdf_rows) != int((pdf_manifest.get("counts") or {}).get("pdf_sources") or -1):
        raise ValueError(f"PDF source row count does not match manifest: {display_path(pdf_sources_path)}")
    if len(okf_case_rows) != int((okf_alignment.get("counts") or {}).get("target_cases") or -1):
        raise ValueError(f"OKF case alignment row count does not match report: {display_path(okf_case_alignment_path)}")
    if len(runtime_rows) != int((compiled_authority.get("counts") or {}).get("runtime_pointer_records") or -1):
        raise ValueError(f"runtime pointer row count does not match manifest: {display_path(runtime_pointers_path)}")

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    action_queues = build_action_queues(asset_buckets, json_rows, pdf_rows, okf_case_rows, runtime_rows)
    gap_items = build_gap_items(
        asset_buckets,
        json_ledger,
        pdf_manifest,
        okf_scope,
        okf_alignment,
        compiled_authority,
        action_queues,
    )
    next_actions = build_next_actions(gap_items)
    open_items = [item for item in gap_items if item["status"] == "open"]
    priority_counts = Counter(item["priority"] for item in open_items)
    area_counts = Counter(item["area"] for item in open_items)
    queue_counts = {key: len(value) for key, value in action_queues["queues"].items()}

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    manifest = {
        "schema": "luban_asset_gap_map_manifest.v1",
        "generated_at": generated_at,
        "authority_status": "asset_gap_map_only",
        "runtime_guard": RUNTIME_GUARD,
        "source_paths": {
            "data_asset_brief": display_path(data_asset_brief_path),
            "asset_buckets": display_path(asset_buckets_path),
            "json_source_ledger": display_path(json_ledger_path),
            "json_sources": display_path(json_sources_path),
            "pdf_source_ledger": display_path(pdf_ledger_path),
            "pdf_sources": display_path(pdf_sources_path),
            "okf_candidate_scope": display_path(okf_scope_path),
            "okf_source_alignment": display_path(okf_alignment_path),
            "okf_case_alignment": display_path(okf_case_alignment_path),
            "compiled_asset_authority_map": display_path(compiled_authority_path),
            "runtime_pointers": display_path(runtime_pointers_path),
        },
        "outputs": {
            "gap_summary": "gap_summary.json",
            "gap_items": "gap_items.jsonl",
            "action_queues": "action_queues.json",
            "next_actions": "next_actions.json",
            "summary": "summary.md",
        },
        "counts": {
            "gap_items": len(gap_items),
            "open_gap_items": len(open_items),
            "by_priority": dict(priority_counts.most_common()),
            "by_area": dict(area_counts.most_common()),
            "action_queue_counts": queue_counts,
        },
        "guardrails": [
            "gap map only; not runtime install",
            "LLM outputs are candidate organization work only",
            "deterministic gates sign releases and protect authority",
            "official score and learner truth remain false",
        ],
    }
    gap_summary = {
        "schema": "luban_asset_gap_summary.v1",
        "generated_at": generated_at,
        "source_status": {
            "asset_inventory_status": data_asset_brief.get("authority_status"),
            "json_sources": (json_ledger.get("counts") or {}).get("json_sources"),
            "pdf_sources": (pdf_manifest.get("counts") or {}).get("pdf_sources"),
            "okf_candidate_status": okf_scope.get("status"),
            "okf_alignment_status": okf_alignment.get("status"),
            "compiled_authority_status": compiled_authority.get("authority_status"),
        },
        "counts": manifest["counts"],
        "runtime_guard": RUNTIME_GUARD,
    }

    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "gap_summary.json").write_text(
        json.dumps(gap_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_root / "gap_items.jsonl").open("w", encoding="utf-8") as f:
        for item in gap_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    (output_root / "action_queues.json").write_text(
        json.dumps(action_queues, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "next_actions.json").write_text(
        json.dumps(next_actions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "summary.md").write_text(render_summary(manifest, gap_items, action_queues), encoding="utf-8")
    return {
        "manifest": manifest,
        "gap_summary": gap_summary,
        "gap_items": gap_items,
        "action_queues": action_queues,
        "next_actions": next_actions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-asset-brief", type=Path, default=DEFAULT_DATA_ASSET_BRIEF)
    parser.add_argument("--asset-buckets", type=Path, default=DEFAULT_ASSET_BUCKETS)
    parser.add_argument("--json-ledger", type=Path, default=DEFAULT_JSON_LEDGER)
    parser.add_argument("--json-sources", type=Path, default=DEFAULT_JSON_SOURCES)
    parser.add_argument("--pdf-ledger", type=Path, default=DEFAULT_PDF_LEDGER)
    parser.add_argument("--pdf-sources", type=Path, default=DEFAULT_PDF_SOURCES)
    parser.add_argument("--okf-scope", type=Path, default=DEFAULT_OKF_SCOPE)
    parser.add_argument("--okf-alignment", type=Path, default=DEFAULT_OKF_ALIGNMENT)
    parser.add_argument("--okf-case-alignment", type=Path, default=DEFAULT_OKF_CASE_ALIGNMENT)
    parser.add_argument("--compiled-authority", type=Path, default=DEFAULT_COMPILED_AUTHORITY)
    parser.add_argument("--runtime-pointers", type=Path, default=DEFAULT_RUNTIME_POINTERS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    result = build_asset_gap_map(
        data_asset_brief_path=args.data_asset_brief,
        asset_buckets_path=args.asset_buckets,
        json_ledger_path=args.json_ledger,
        json_sources_path=args.json_sources,
        pdf_ledger_path=args.pdf_ledger,
        pdf_sources_path=args.pdf_sources,
        okf_scope_path=args.okf_scope,
        okf_alignment_path=args.okf_alignment,
        okf_case_alignment_path=args.okf_case_alignment,
        compiled_authority_path=args.compiled_authority,
        runtime_pointers_path=args.runtime_pointers,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(
        json.dumps(
            {
                "manifest": display_path(args.output_root / "manifest.json"),
                "gap_summary": display_path(args.output_root / "gap_summary.json"),
                "gap_items": display_path(args.output_root / "gap_items.jsonl"),
                "action_queues": display_path(args.output_root / "action_queues.json"),
                "next_actions": display_path(args.output_root / "next_actions.json"),
                "summary": display_path(args.output_root / "summary.md"),
                "counts": result["manifest"]["counts"],
                "runtime_consumable": result["manifest"]["runtime_guard"]["runtime_consumable"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
