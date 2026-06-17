#!/usr/bin/env python3
"""Build Phase 1a RichLeafArtifact skeleton candidates.

This compiler is intentionally candidate-only. It reads the Phase 1 sample
manifest and canonical unified knowledge bundle, emits review skeletons, and
does not install runtime supply, write canonical truth, or grant score policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rich_leaf_artifacts import (  # noqa: E402
    normalize_source_span,
    source_span_hash,
    validate_rich_leaf_artifact,
)


SOURCE_LANES = ("textbook", "standard", "lecture", "question")
SCHEMA = "luban_rich_leaf_skeleton_batch.v1"
SOURCE_REGISTRY_ID = "canonical_unified_knowledge"
DEFAULT_BUNDLE_VERSION = "v_rich_leaf_skeleton_candidate"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _bundle_source_version(unified_bundle: dict[str, Any]) -> str:
    manifest = unified_bundle.get("manifest")
    if isinstance(manifest, dict):
        for key in ("content_hash", "hash", "bundle_content_hash", "version"):
            if manifest.get(key):
                return str(manifest[key])
    return _content_hash(unified_bundle)


def _artifact_id(bundle_version: str, leaf_id: str) -> str:
    digest = hashlib.sha256(f"{bundle_version}:{leaf_id}".encode("utf-8")).hexdigest()[:12]
    return f"rich_leaf_skeleton_{leaf_id}_{digest}"


def _source_text(source: dict[str, Any]) -> str:
    for key in ("text_preview", "text", "content", "quote", "span"):
        value = source.get(key)
        if value:
            return str(value)
    return ""


def _source_record_id(source: dict[str, Any], lane: str, idx: int) -> str:
    provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
    for value in (
        source.get("unit_id"),
        source.get("record_id"),
        source.get("chunk_id"),
        provenance.get("chunk_id"),
        provenance.get("record_id"),
        provenance.get("content_hash"),
    ):
        if value:
            return str(value)
    return f"{lane}_{idx}"


def _usable_lane_sources(node: dict[str, Any], lane: str) -> list[dict[str, Any]]:
    sources = node.get("sources") if isinstance(node.get("sources"), dict) else {}
    lane_sources = sources.get(lane) if isinstance(sources, dict) else None
    if not isinstance(lane_sources, list):
        return []
    return [
        source
        for source in lane_sources
        if isinstance(source, dict) and normalize_source_span(_source_text(source))
    ]


def _source_ref(
    *,
    leaf_id: str,
    lane: str,
    idx: int,
    source: dict[str, Any],
    source_version: str,
) -> dict[str, Any]:
    span = _source_text(source)
    record_id = _source_record_id(source, lane, idx)
    ref_digest = hashlib.sha256(f"{leaf_id}:{lane}:{idx}:{record_id}:{span}".encode("utf-8")).hexdigest()[:16]
    ref = {
        "source_ref_id": f"src_{ref_digest}",
        "source_registry_id": SOURCE_REGISTRY_ID,
        "source_dataset_id": str(source.get("authority_tier") or source.get("dataset_id") or lane),
        "source_version": source_version,
        "extractor_version": str(source.get("method") or source.get("extractor_version") or "unified_bundle"),
        "source_lane": lane,
        "path": f"nodes.{leaf_id}.sources.{lane}[{idx}]",
        "record_id": record_id,
        "span": span,
        "span_hash": source_span_hash(span),
    }
    provenance = source.get("provenance")
    if isinstance(provenance, dict):
        ref["provenance"] = dict(provenance)
    return ref


def _source_refs_for_leaf(
    *,
    leaf_id: str,
    node: dict[str, Any],
    source_version: str,
    max_sources_per_lane: int,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for lane in SOURCE_LANES:
        for idx, source in enumerate(_usable_lane_sources(node, lane)[:max_sources_per_lane]):
            refs.append(
                _source_ref(
                    leaf_id=leaf_id,
                    lane=lane,
                    idx=idx,
                    source=source,
                    source_version=source_version,
                )
            )
    return refs


def _missing_source_lanes(node: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for lane in SOURCE_LANES:
        if not _usable_lane_sources(node, lane):
            missing.append(lane)
    return missing


def _teaching_card(leaf: dict[str, Any], source_refs: list[dict[str, Any]]) -> dict[str, Any]:
    leaf_id = str(leaf.get("leaf_id") or "")
    keywords = [str(k) for k in (leaf.get("keywords") or []) if k]
    prompt = str(leaf.get("name_path") or leaf_id)
    if keywords:
        prompt = f"{prompt} | keywords: {', '.join(keywords[:6])}"
    return {
        "field_id": f"teaching_card_{hashlib.sha256(leaf_id.encode('utf-8')).hexdigest()[:12]}",
        "claim_status": "candidate_only",
        "source_ref_ids": [str(ref["source_ref_id"]) for ref in source_refs],
        "card": prompt,
        "skeleton_note": "candidate skeleton only; requires human/compiler review before release use",
    }


def _build_artifact(
    *,
    leaf: dict[str, Any],
    node: dict[str, Any],
    bundle_version: str,
    source_version: str,
    max_sources_per_lane: int,
) -> dict[str, Any]:
    leaf_id = str(leaf.get("leaf_id") or "")
    source_refs = _source_refs_for_leaf(
        leaf_id=leaf_id,
        node=node,
        source_version=source_version,
        max_sources_per_lane=max_sources_per_lane,
    )
    return {
        "artifact_id": _artifact_id(bundle_version, leaf_id),
        "leaf_id": leaf_id,
        "bundle_version": bundle_version,
        "candidate_status": "candidate",
        "source_refs": source_refs,
        "missing_source_lanes": _missing_source_lanes(node),
        "name_path": str(leaf.get("name_path") or node.get("name_path") or leaf_id),
        "bucket": str(leaf.get("bucket") or ""),
        "definitions": [],
        "rules": [],
        "procedures": [],
        "numeric_constraints": [],
        "negative_evidence": [],
        "teaching_cards": [_teaching_card(leaf, source_refs)],
        "rubric_link_index": [],
        "common_mistakes": {"observed_mistakes": [], "hypothesized_mistakes": []},
        "learner_memory_event_templates": [],
    }


def build_rich_leaf_skeleton_batch(
    *,
    sample_manifest: dict[str, Any],
    unified_bundle: dict[str, Any],
    bundle_version: str,
    max_sources_per_lane: int = 3,
) -> dict[str, Any]:
    nodes = unified_bundle.get("nodes") if isinstance(unified_bundle.get("nodes"), dict) else {}
    source_version = _bundle_source_version(unified_bundle)
    artifacts: list[dict[str, Any]] = []
    validation_reports: list[dict[str, Any]] = []

    for leaf in sample_manifest.get("selected_leaves") or []:
        if not isinstance(leaf, dict):
            continue
        leaf_id = str(leaf.get("leaf_id") or "")
        node = nodes.get(leaf_id) if isinstance(nodes.get(leaf_id), dict) else {}
        artifact = _build_artifact(
            leaf=leaf,
            node=node,
            bundle_version=bundle_version,
            source_version=source_version,
            max_sources_per_lane=max_sources_per_lane,
        )
        report = validate_rich_leaf_artifact(artifact)
        artifacts.append(artifact)
        validation_reports.append(
            {
                "artifact_id": artifact["artifact_id"],
                "leaf_id": artifact["leaf_id"],
                "ok": report.ok,
                "blockers": list(report.blockers),
                "warnings": list(report.warnings),
                "candidate_only_field_ids": list(report.candidate_only_field_ids),
                "canonical_truth_written": report.canonical_truth_written,
                "official_score_allowed": report.official_score_allowed,
                "production_write_count": report.production_write_count,
            }
        )

    with_source_refs = sum(1 for artifact in artifacts if artifact.get("source_refs"))
    summary = {
        "artifact_count": len(artifacts),
        "with_source_refs_count": with_source_refs,
        "missing_source_refs_count": len(artifacts) - with_source_refs,
        "valid_artifact_count": sum(1 for report in validation_reports if report["ok"]),
        "invalid_artifact_count": sum(1 for report in validation_reports if not report["ok"]),
    }
    classification = {
        "candidate_only": True,
        "review_required": True,
    }
    safety = {
        "installed_runtime_supply": False,
        "canonical_truth_written": False,
        "official_score_allowed": False,
        "production_write_count": 0,
        "release_truth_claimed": False,
    }
    return {
        "schema": SCHEMA,
        "bundle_version": bundle_version,
        "source_registry_id": SOURCE_REGISTRY_ID,
        "input_hashes": {
            "sample_manifest": _content_hash(sample_manifest),
            "unified_bundle": _content_hash(unified_bundle),
            "canonical_unified_knowledge": source_version,
        },
        "summary": summary,
        "classification": classification,
        "safety": safety,
        "rich_leaf_artifacts": artifacts,
        "validation_reports": validation_reports,
    }


def _report_from_batch(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "luban_rich_leaf_skeleton_report.v1",
        "bundle_version": batch["bundle_version"],
        "source_registry_id": batch["source_registry_id"],
        "summary": batch["summary"],
        "safety": batch["safety"],
        "validation_reports": batch["validation_reports"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--unified-bundle", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bundle-version", default=DEFAULT_BUNDLE_VERSION)
    parser.add_argument("--max-sources-per-lane", type=int, default=3)
    args = parser.parse_args(argv)

    batch = build_rich_leaf_skeleton_batch(
        sample_manifest=_read_json(args.sample_manifest),
        unified_bundle=_read_json(args.unified_bundle),
        bundle_version=args.bundle_version,
        max_sources_per_lane=args.max_sources_per_lane,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "rich_leaf_skeleton_candidates.json", batch)
    _write_json(args.output_dir / "skeleton_report.json", _report_from_batch(batch))
    print(json.dumps({"out": str(args.output_dir), "summary": batch["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
