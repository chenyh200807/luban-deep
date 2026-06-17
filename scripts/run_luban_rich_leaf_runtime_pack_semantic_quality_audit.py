#!/usr/bin/env python3
"""Semantic quality audit for a RichLeaf runtime token pack.

Per-unit checks (read-only, candidate/review tier):

- leaf<->context discriminative keyword overlap against the canonical taxonomy
  (the check whose absence let polluted links reach the v2.3 live A/B);
- provenance completeness of source_ref (record_id/source_path/span_hash/
  file_sha256) and optional on-disk source file existence;
- field-level source_refs coverage of structured context items;
- thin-context detection;
- taxonomy duplicate leaf-code exposure.

This audit never claims release truth and never mutates the pack.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCHEMA = "luban_rich_leaf_runtime_pack_semantic_quality_audit.v1"
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v231_residual_repair_20260612/runtime_token_pack_v231_candidate.json"
)
DEFAULT_TAXONOMY = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
)
DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_OUTPUT = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v231_residual_repair_20260612/runtime_pack_semantic_quality_audit.json"
)

PROVENANCE_FIELDS = ("record_id", "source_path", "span_hash", "file_sha256")
STRUCTURED_FAMILIES = ("rules", "procedures", "exam_patterns", "teaching_cards", "numeric_constraints")
POLLUTION_THRESHOLD = 0.2
SUSPECT_THRESHOLD = 0.5
THIN_CONTEXT_CHARS = 60

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "semantic_quality_audit": True,
    "runtime_install_allowed": False,
    "production_default": False,
    "canonical_pointer_written": False,
    "release_truth_claimed": False,
    "quality_claim_allowed": False,
}
SAFETY = {
    "canonical_truth_written": False,
    "official_score_allowed": False,
    "installed_runtime_supply": False,
    "production_write_count": 0,
    "release_truth_claimed": False,
}
NOT_EXERCISED = [
    "production_rag_runtime",
    "runtime_default_install",
    "canonical_truth_write",
    "official_score",
    "production_db_write",
    "release_truth_claim",
    "llm_semantic_double_check",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _taxonomy_leaves_by_code(taxonomy: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    leaves: dict[str, list[dict[str, Any]]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            code = node.get("code")
            name = node.get("name")
            if code and name:
                entry = {"name": str(name), "keywords": [str(k) for k in node.get("keywords") or []]}
                bucket = leaves.setdefault(str(code), [])
                if not any(e["name"] == entry["name"] for e in bucket):
                    bucket.append(entry)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(taxonomy)
    return leaves


def _context_text(compiled_context: dict[str, Any]) -> str:
    return json.dumps(compiled_context, ensure_ascii=False)


def _field_source_ref_coverage(compiled_context: dict[str, Any]) -> tuple[float, int]:
    items: list[str] = []
    for family in STRUCTURED_FAMILIES:
        items.extend(str(v) for v in compiled_context.get(family) or [])
    if not items:
        return 0.0, 0
    covered = 0
    for item in items:
        try:
            parsed = json.loads(item)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and (parsed.get("source_refs") or parsed.get("source_span")):
            covered += 1
    return covered / len(items), len(items)


def _audit_unit(
    unit: dict[str, Any],
    *,
    leaves_by_code: dict[str, list[dict[str, Any]]],
    source_root: Path,
    check_source_files: bool,
) -> dict[str, Any]:
    leaf_id = str(unit.get("leaf_id") or "")
    leaf_name = str(unit.get("leaf_name_path") or "").split(">")[-1].strip()
    compiled_context = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    context_text = _context_text(compiled_context)

    entries = leaves_by_code.get(leaf_id) or []
    duplicate_code = len(entries) > 1
    entry = next((e for e in entries if e["name"] == leaf_name), entries[0] if entries else None)
    keywords = entry["keywords"] if entry else []
    if keywords:
        hits = [kw for kw in keywords if kw in context_text]
        overlap = len(hits) / len(keywords)
        leaf_name_in_context = bool(leaf_name) and leaf_name in context_text
        if overlap < POLLUTION_THRESHOLD and not leaf_name_in_context:
            tier = "pollution_suspect"
        elif overlap < SUSPECT_THRESHOLD:
            tier = "weak_alignment"
        else:
            tier = "ok"
    else:
        hits = []
        overlap = 0.0
        tier = "low_signal_needs_review"

    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    missing = [f for f in PROVENANCE_FIELDS if not source_ref.get(f)]
    source_file_exists: bool | None = None
    if check_source_files and source_ref.get("source_path"):
        source_file_exists = (source_root / str(source_ref["source_path"])).exists()
        if source_file_exists is False:
            missing.append("source_file_on_disk")

    coverage, structured_count = _field_source_ref_coverage(compiled_context)
    plain_len = sum(len(str(v)) for family in compiled_context.values() if isinstance(family, list) for v in family)

    return {
        "unit_id": unit.get("unit_id"),
        "leaf_id": leaf_id,
        "leaf_name_path": unit.get("leaf_name_path"),
        "semantic_tier": tier,
        "keyword_overlap": round(overlap, 4),
        "keyword_hits": hits,
        "taxonomy_duplicate_code": duplicate_code,
        "leaf_in_canonical_taxonomy": entry is not None,
        "provenance_missing_fields": missing,
        "source_file_exists": source_file_exists,
        "field_source_ref_coverage": round(coverage, 4),
        "structured_item_count": structured_count,
        "thin_context": plain_len < THIN_CONTEXT_CHARS,
        "review_source": unit.get("review_source"),
        "source_lane": unit.get("source_lane"),
    }


def build_runtime_pack_semantic_quality_audit(
    *,
    runtime_token_pack: dict[str, Any],
    taxonomy: dict[str, Any],
    source_root: Path = DEFAULT_SOURCE_ROOT,
    check_source_files: bool = True,
) -> dict[str, Any]:
    leaves_by_code = _taxonomy_leaves_by_code(taxonomy)
    units = [u for u in runtime_token_pack.get("runtime_token_pack_units") or [] if isinstance(u, dict)]
    rows = [
        _audit_unit(
            unit,
            leaves_by_code=leaves_by_code,
            source_root=source_root,
            check_source_files=check_source_files,
        )
        for unit in units
    ]

    def count(predicate) -> int:
        return sum(1 for row in rows if predicate(row))

    pollution = count(lambda r: r["semantic_tier"] == "pollution_suspect")
    weak = count(lambda r: r["semantic_tier"] == "weak_alignment")
    low_signal = count(lambda r: r["semantic_tier"] == "low_signal_needs_review")
    findings = pollution + weak + low_signal
    summary = {
        "pack_version": runtime_token_pack.get("version"),
        "unit_count": len(rows),
        "ok_count": count(lambda r: r["semantic_tier"] == "ok"),
        "pollution_suspect_count": pollution,
        "weak_alignment_count": weak,
        "low_signal_needs_review_count": low_signal,
        "taxonomy_duplicate_code_unit_count": count(lambda r: r["taxonomy_duplicate_code"]),
        "leaf_not_in_taxonomy_count": count(lambda r: not r["leaf_in_canonical_taxonomy"]),
        "provenance_incomplete_count": count(lambda r: bool(r["provenance_missing_fields"])),
        "source_file_missing_count": count(lambda r: r["source_file_exists"] is False),
        "field_source_ref_zero_count": count(lambda r: r["structured_item_count"] > 0 and r["field_source_ref_coverage"] == 0.0),
        "thin_context_count": count(lambda r: r["thin_context"]),
        "production_write_count": 0,
    }
    return {
        "schema": SCHEMA,
        "verdict": "AUDIT_COMPLETED_WITH_FINDINGS" if findings else "AUDIT_COMPLETED_CLEAN",
        "quality_claim_allowed": False,
        "summary": summary,
        "rows": rows,
        "not_exercised": NOT_EXERCISED,
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--no-source-file-check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_runtime_pack_semantic_quality_audit(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        taxonomy=_read_json(args.taxonomy),
        source_root=args.source_root,
        check_source_files=not args.no_source_file_check,
    )
    _write_json(args.output, report)
    print(json.dumps({"output": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
