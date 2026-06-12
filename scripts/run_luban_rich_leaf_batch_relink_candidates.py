#!/usr/bin/env python3
"""Batch re-link pollution-suspect runtime units to canonical textbook chunks.

For every unit the semantic quality audit tiered as pollution_suspect, scan the
canonical 2026 textbook chunk corpus for the chunk whose content matches the
leaf's canonical taxonomy keywords discriminatively. Units with a candidate at
or above the overlap threshold get a quote-grounded recompiled context (same
compile path and gates as the residual source repair); the rest become typed
unresolved work orders. Candidate/review tier only — never installs runtime
defaults, never writes canonical truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash  # noqa: E402
from scripts.run_luban_rich_leaf_v23_residual_source_repair import (  # noqa: E402
    _compile_context,
    _keyword_overlap,
    _taxonomy_leaves_by_code,
)

SCHEMA = "luban_rich_leaf_batch_relink_candidates.v1"
AUDIT_SCHEMA = "luban_rich_leaf_runtime_pack_semantic_quality_audit.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
PATCHED_VERSION = "v2.3.2_batch_relink_candidate_20260612"
AMBIGUITY_MARGIN = 0.1

DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v231_residual_repair_20260612/runtime_token_pack_v231_candidate.json"
)
DEFAULT_AUDIT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v231_residual_repair_20260612/runtime_pack_semantic_quality_audit.json"
)
DEFAULT_TAXONOMY = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
)
DEFAULT_SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_BOOK_FILES = [
    DEFAULT_SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    DEFAULT_SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    DEFAULT_SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-222-382_fixed.json",
]
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v232_batch_relink_20260612"

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "batch_relink_patch": True,
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
    "live_provider_revalidation",
    "human_or_council_review_of_relink_candidates",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_chunks(book_files: list[Path], source_root: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for path in book_files:
        payload = _read_json(path)
        file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            relative = str(path.relative_to(source_root))
        except ValueError:
            relative = path.name
        for block in payload.get("content_blocks") or []:
            if not isinstance(block, dict) or not block.get("chunk_id"):
                continue
            content = str(block.get("content_markdown") or "")
            cards_text = json.dumps(block.get("knowledge_cards") or [], ensure_ascii=False)
            chunks.append(
                {
                    "chunk": block,
                    "chunk_id": str(block["chunk_id"]),
                    "search_text": content + cards_text,
                    "content_markdown": content,
                    "file_path": path,
                    "file_sha256": file_sha,
                    "relative_path": relative,
                }
            )
    return chunks


def _best_chunks(keywords: list[str], chunks: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float, float]:
    best: dict[str, Any] | None = None
    best_score = 0.0
    runner_up = 0.0
    for entry in chunks:
        score, _ = _keyword_overlap(keywords, entry["search_text"])
        if score > best_score:
            runner_up = best_score
            best, best_score = entry, score
        elif score > runner_up:
            runner_up = score
    return best, best_score, runner_up


def build_batch_relink_candidates(
    *,
    runtime_token_pack: dict[str, Any],
    audit: dict[str, Any],
    taxonomy: dict[str, Any],
    book_files: list[Path],
    source_root: Path,
    min_keyword_overlap: float = 0.6,
    tiers: tuple[str, ...] = ("pollution_suspect",),
) -> dict[str, Any]:
    blockers: list[str] = []
    if runtime_token_pack.get("schema") != RUNTIME_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if audit.get("schema") != AUDIT_SCHEMA:
        blockers.append(f"audit_schema_mismatch:{audit.get('schema')}")

    units_by_id = {
        str(u.get("unit_id")): u
        for u in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(u, dict) and u.get("unit_id")
    }
    leaves_by_code = _taxonomy_leaves_by_code(taxonomy)
    chunks = _load_chunks(book_files, source_root)
    if not chunks:
        blockers.append("no_canonical_book_chunks_loaded")

    target_rows = [
        row
        for row in audit.get("rows") or []
        if isinstance(row, dict) and row.get("semantic_tier") in tiers and str(row.get("unit_id")) in units_by_id
    ]

    relinked: list[dict[str, Any]] = []
    repaired_units: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    if not blockers:
        for row in target_rows:
            unit_id = str(row["unit_id"])
            unit = units_by_id[unit_id]
            leaf_id = str(unit.get("leaf_id") or "")
            leaf_name = str(unit.get("leaf_name_path") or "").split(">")[-1].strip()
            entries = leaves_by_code.get(leaf_id) or []
            leaf_entry = next((e for e in entries if e["name"] == leaf_name), None)
            if leaf_entry is None or not leaf_entry["keywords"]:
                unresolved.append(
                    {
                        "work_order_type": "batch_relink_unresolved_source_gap",
                        "unit_id": unit_id,
                        "leaf_id": leaf_id,
                        "leaf_name_path": unit.get("leaf_name_path"),
                        "reason": "leaf_keywords_missing_in_canonical_taxonomy",
                        "recommended_action": "taxonomy owner must supply discriminative keywords or review leaf placement",
                        "candidate_only": True,
                        "review_only": True,
                    }
                )
                continue

            best, best_score, runner_up = _best_chunks(leaf_entry["keywords"], chunks)
            min_hits = min(2, len(leaf_entry["keywords"]))
            hits = [kw for kw in leaf_entry["keywords"] if best is not None and kw in best["search_text"]]
            if best is None or best_score < min_keyword_overlap or len(hits) < min_hits:
                unresolved.append(
                    {
                        "work_order_type": "batch_relink_unresolved_source_gap",
                        "unit_id": unit_id,
                        "leaf_id": leaf_id,
                        "leaf_name_path": unit.get("leaf_name_path"),
                        "reason": "no_candidate_chunk_above_threshold",
                        "best_score": round(best_score, 4),
                        "best_chunk_id": best["chunk_id"] if best else None,
                        "recommended_action": "needs new source acquisition or taxonomy review; do not promote this unit",
                        "candidate_only": True,
                        "review_only": True,
                    }
                )
                continue

            span_text = best["content_markdown"]
            old_overlap, _ = _keyword_overlap(
                leaf_entry["keywords"], json.dumps(unit.get("compiled_context") or {}, ensure_ascii=False)
            )
            repaired_units[unit_id] = {
                **unit,
                "compiled_context": _compile_context(span_text, best["chunk"], best["chunk_id"]),
                "source_ref": {
                    "record_id": f"{best['relative_path']}#chunk:{best['chunk_id']}",
                    "source_path": best["relative_path"],
                    "source_lane": "textbook",
                    "chunk_id": best["chunk_id"],
                    "page_num": (best["chunk"].get("source_meta") or {}).get("page_num"),
                    "file_sha256": best["file_sha256"],
                    "span_hash": source_span_hash(span_text),
                },
                "relative_path": best["relative_path"],
                "source_lane": "source_truth",
                "review_source": "batch_relink_candidate",
                "repair": {
                    "relink_origin": "semantic_quality_audit",
                    "replaced_source_path": (unit.get("source_ref") or {}).get("source_path"),
                    "keyword_overlap_old": round(old_overlap, 4),
                    "keyword_overlap_new": round(best_score, 4),
                    "keyword_hits": hits,
                    "runner_up_score": round(runner_up, 4),
                },
            }
            relinked.append(
                {
                    "unit_id": unit_id,
                    "leaf_id": leaf_id,
                    "leaf_name_path": unit.get("leaf_name_path"),
                    "chunk_id": best["chunk_id"],
                    "source_path": best["relative_path"],
                    "keyword_overlap_old": round(old_overlap, 4),
                    "keyword_overlap_new": round(best_score, 4),
                    "ambiguous_runner_up": (best_score - runner_up) < AMBIGUITY_MARGIN,
                }
            )

    patched_pack: dict[str, Any] | None = None
    if not blockers and repaired_units:
        patched_pack = {
            **runtime_token_pack,
            "version": PATCHED_VERSION,
            "runtime_token_pack_units": [
                repaired_units.get(str(u.get("unit_id")), u)
                for u in runtime_token_pack.get("runtime_token_pack_units") or []
            ],
            "classification": {**runtime_token_pack.get("classification", {}), **CLASSIFICATION},
            "safety": {**runtime_token_pack.get("safety", {}), **SAFETY},
            "patch_lineage": {
                "base_version": runtime_token_pack.get("version"),
                "patched_unit_ids": sorted(repaired_units),
                "repair_schema": SCHEMA,
            },
        }

    if blockers:
        verdict = "BLOCKED_BATCH_RELINK"
    elif unresolved:
        verdict = "PASS_BATCH_RELINK_CANDIDATES_WITH_UNRESOLVED"
    else:
        verdict = "PASS_BATCH_RELINK_CANDIDATES"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "blockers": blockers,
        "relinked": relinked,
        "unresolved_work_orders": unresolved,
        "patched_runtime_token_pack": patched_pack,
        "summary": {
            "target_unit_count": len(target_rows),
            "relinked_unit_count": len(relinked),
            "unresolved_unit_count": len(unresolved),
            "ambiguous_relink_count": sum(1 for r in relinked if r["ambiguous_runner_up"]),
            "blocker_count": len(blockers),
            "canonical_chunk_count": len(chunks),
            "production_write_count": 0,
        },
        "not_exercised": NOT_EXERCISED,
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--book-file", dest="book_files", type=Path, action="append", default=None)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--min-keyword-overlap", type=float, default=0.6)
    parser.add_argument("--include-weak-alignment", action="store_true")
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_DIR / "batch_relink_report.json")
    parser.add_argument("--output-pack", type=Path, default=DEFAULT_OUTPUT_DIR / "runtime_token_pack_v232_candidate.json")
    args = parser.parse_args(argv)

    tiers: tuple[str, ...] = ("pollution_suspect",)
    if args.include_weak_alignment:
        tiers = ("pollution_suspect", "weak_alignment")
    report = build_batch_relink_candidates(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        audit=_read_json(args.audit),
        taxonomy=_read_json(args.taxonomy),
        book_files=args.book_files or DEFAULT_BOOK_FILES,
        source_root=args.source_root,
        min_keyword_overlap=args.min_keyword_overlap,
        tiers=tiers,
    )
    patched_pack = report.pop("patched_runtime_token_pack", None)
    report["patched_runtime_token_pack_path"] = str(args.output_pack) if patched_pack else None
    _write_json(args.output_report, report)
    if patched_pack is not None:
        _write_json(args.output_pack, patched_pack)
    print(
        json.dumps(
            {
                "output_report": str(args.output_report),
                "output_pack": str(args.output_pack) if patched_pack else None,
                "verdict": report["verdict"],
                "summary": report["summary"],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["verdict"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
