#!/usr/bin/env python3
"""Recompile runtime unit contexts from their (book-derived) leaf evidence.

After the taxonomy rebuild, every migrated leaf carries source_evidence
pointing at canonical textbook chunks. This recompiles each unit's
compiled_context directly from its own leaf's evidence chunk — compile and
identity become same-sourced, closing the axis mismatch between old compiled
contexts and book-derived leaf naming. Units whose leaf is absent from the
new taxonomy (or has no evidence) are left untouched and reported.

Candidate/review tier only: never installs runtime defaults, never writes
canonical truth or production stores.
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
from scripts.run_luban_rich_leaf_v23_residual_source_repair import _compile_context  # noqa: E402

SCHEMA = "luban_rich_leaf_leaf_evidence_recompile.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
RECOMPILED_VERSION = "v2.5_leaf_evidence_recompiled_candidate_20260612"

DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v24_taxonomy_migrated_20260612/runtime_token_pack_v24_candidate.json"
)
DEFAULT_TAXONOMY = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
)
SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_BOOK_FILES = [
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-222-382_fixed.json",
]
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v25_leaf_evidence_recompile_20260612"

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "leaf_evidence_recompile": True,
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
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _leaves_by_code(taxonomy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    leaves: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any]) -> None:
        code = str(node.get("code") or "")
        if code and node.get("source_evidence"):
            leaves.setdefault(code, node)
        for ch in node.get("children") or []:
            if isinstance(ch, dict):
                walk(ch)

    for root in taxonomy.get("outline_structure") or []:
        if isinstance(root, dict):
            walk(root)
    return leaves


def _chunk_index(book_files: list[Path], source_root: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in book_files:
        payload = _read_json(path)
        file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            relative = str(path.relative_to(source_root))
        except ValueError:
            relative = path.name
        for block in payload.get("content_blocks") or []:
            if isinstance(block, dict) and block.get("chunk_id"):
                index[str(block["chunk_id"])] = {
                    "chunk": block,
                    "file_sha256": file_sha,
                    "relative_path": relative,
                }
    return index


def build_leaf_evidence_recompile(
    *,
    runtime_token_pack: dict[str, Any],
    taxonomy: dict[str, Any],
    book_files: list[Path],
    source_root: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    if runtime_token_pack.get("schema") != RUNTIME_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    leaves = _leaves_by_code(taxonomy)
    chunks = _chunk_index(book_files, source_root)
    if not leaves:
        blockers.append("taxonomy_has_no_evidence_leaves")
    if not chunks:
        blockers.append("no_book_chunks_loaded")

    rows: list[dict[str, Any]] = []
    recompiled_units: list[dict[str, Any]] = []
    recompiled = skipped = 0
    if not blockers:
        for unit in runtime_token_pack.get("runtime_token_pack_units") or []:
            if not isinstance(unit, dict):
                continue
            leaf = leaves.get(str(unit.get("leaf_id") or ""))
            if leaf is None:
                skipped += 1
                rows.append({"unit_id": unit.get("unit_id"), "status": "leaf_not_in_new_taxonomy"})
                recompiled_units.append(unit)
                continue
            evidence = leaf["source_evidence"][0]
            entry = chunks.get(str(evidence.get("chunk_id") or ""))
            if entry is None:
                skipped += 1
                rows.append({"unit_id": unit.get("unit_id"), "status": "evidence_chunk_missing", "chunk_id": evidence.get("chunk_id")})
                recompiled_units.append(unit)
                continue
            chunk = entry["chunk"]
            chunk_id = str(chunk["chunk_id"])
            span_text = str(chunk.get("content_markdown") or "")
            recompiled_units.append(
                {
                    **unit,
                    "compiled_context": _compile_context(span_text, chunk, chunk_id),
                    "source_ref": {
                        "record_id": f"{entry['relative_path']}#chunk:{chunk_id}",
                        "source_path": entry["relative_path"],
                        "source_lane": "textbook",
                        "chunk_id": chunk_id,
                        "page_num": (chunk.get("source_meta") or {}).get("page_num"),
                        "file_sha256": entry["file_sha256"],
                        "span_hash": source_span_hash(span_text),
                    },
                    "relative_path": entry["relative_path"],
                    "source_lane": "source_truth",
                    "review_source": "leaf_evidence_recompile_candidate",
                }
            )
            recompiled += 1
            rows.append({"unit_id": unit.get("unit_id"), "status": "recompiled", "chunk_id": chunk_id, "leaf_id": unit.get("leaf_id")})

    recompiled_pack: dict[str, Any] | None = None
    if not blockers and recompiled:
        recompiled_pack = {
            **runtime_token_pack,
            "version": RECOMPILED_VERSION,
            "runtime_token_pack_units": recompiled_units,
            "classification": {**runtime_token_pack.get("classification", {}), **CLASSIFICATION},
            "safety": {**runtime_token_pack.get("safety", {}), **SAFETY},
            "patch_lineage": {
                "base_version": runtime_token_pack.get("version"),
                "recompiled_unit_count": recompiled,
                "repair_schema": SCHEMA,
            },
        }

    verdict = "PASS_LEAF_EVIDENCE_RECOMPILE" if recompiled_pack is not None else "BLOCKED_LEAF_EVIDENCE_RECOMPILE"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "blockers": blockers,
        "rows": rows,
        "recompiled_runtime_token_pack": recompiled_pack,
        "summary": {
            "unit_count": len(rows),
            "recompiled_unit_count": recompiled,
            "skipped_unit_count": skipped,
            "blocker_count": len(blockers),
            "production_write_count": 0,
        },
        "not_exercised": NOT_EXERCISED,
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--book-file", dest="book_files", type=Path, action="append", default=None)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_DIR / "leaf_evidence_recompile_report.json")
    parser.add_argument("--output-pack", type=Path, default=DEFAULT_OUTPUT_DIR / "runtime_token_pack_v25_candidate.json")
    args = parser.parse_args(argv)

    report = build_leaf_evidence_recompile(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        taxonomy=_read_json(args.taxonomy),
        book_files=args.book_files or DEFAULT_BOOK_FILES,
        source_root=SOURCE_ROOT,
    )
    pack = report.pop("recompiled_runtime_token_pack", None)
    report["recompiled_runtime_token_pack_path"] = str(args.output_pack) if pack else None
    _write_json(args.output_report, report)
    if pack is not None:
        _write_json(args.output_pack, pack)
    print(
        json.dumps(
            {"output_report": str(args.output_report), "output_pack": str(args.output_pack) if pack else None,
             "verdict": report["verdict"], "summary": report["summary"], "blockers": report["blockers"]},
            ensure_ascii=False, sort_keys=True,
        )
    )
    return 0 if report["verdict"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
