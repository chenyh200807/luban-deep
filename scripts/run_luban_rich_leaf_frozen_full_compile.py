#!/usr/bin/env python3
"""Full-compile RichLeafArtifact units from the frozen canonical taxonomy.

Walks every evidence-bearing leaf of the frozen axis (taxonomy-frozen-v1)
and compiles one runtime unit per leaf directly from the leaf's own
source_evidence chunk:

- textbook lane: chunk located by chunk_id in the three FINAL_CLEANED_BOOK2026
  volumes named by source_evidence.source_file;
- lecture lane: chunk located in 讲义 page files named by
  source_evidence.source_file (fuzzy directory resolution), best chunk chosen
  by leaf-name/keyword overlap;
- lecture unit-reference lane: leaves whose evidence names existing rtp22_*
  pack units are carried over from a base candidate pack.

Candidate/review tier only: never installs runtime defaults, never writes
canonical truth or production stores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rich_leaf_artifacts import source_span_hash  # noqa: E402
from scripts.luban_rich_leaf_subsection import leaf_name_core  # noqa: E402
from scripts.run_luban_rich_leaf_v23_residual_source_repair import (  # noqa: E402
    _compile_context,
    compile_context_for_leaf,
)

SCHEMA = "luban_rich_leaf_frozen_full_compile.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
PACK_VERSION = "v3.0_frozen_v1_full_compile"
PACK_STATUS = "candidate_ready_for_shadow_ab_full_accounted"
EXPECTED_FROZEN_PREFIX = "taxonomy-frozen-v1"
UNIT_ID_PREFIX = "rtpf1"

DEFAULT_TAXONOMY = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
)
SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_BOOK_FILES = [
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-222-382_fixed.json",
]
DEFAULT_BASE_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v26_council_sourced_20260612/runtime_token_pack_v262_candidate.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613"

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "frozen_full_compile": True,
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


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _unit_id(leaf_code: str) -> str:
    return f"{UNIT_ID_PREFIX}_{hashlib.sha256(leaf_code.encode('utf-8')).hexdigest()[:16]}"


def _evidence_leaves(taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect terminal leaves carrying source_evidence, with full name paths."""
    leaves: list[dict[str, Any]] = []
    seen_codes: set[str] = set()

    def walk(node: dict[str, Any], names: list[str]) -> None:
        name = str(node.get("name") or "")
        path = names + ([name] if name else [])
        children = [c for c in node.get("children") or [] if isinstance(c, dict)]
        if children:
            for child in children:
                walk(child, path)
            return
        code = str(node.get("code") or "")
        evidence = node.get("source_evidence")
        if not code or not evidence or code in seen_codes:
            return
        seen_codes.add(code)
        leaves.append(
            {
                "code": code,
                "name": name,
                "name_path": " > ".join(path),
                "keywords": [str(k) for k in node.get("keywords") or []],
                "evidence": evidence[0] if isinstance(evidence, list) else evidence,
            }
        )

    for root in taxonomy.get("outline_structure") or []:
        if isinstance(root, dict):
            walk(root, [])
    return leaves


def _chunk_index(book_files: list[Path], source_root: Path) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in book_files:
        payload = _read_json_object(path)
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


def _resolve_lecture_page_files(source_file: str, source_root: Path) -> list[Path]:
    """Resolve '讲义/<dir>/page_a.json[,page_b.json]' against possibly abbreviated dir names."""
    parts = source_file.split("/")
    if len(parts) < 3:
        return []
    evidence_dir = parts[1]
    page_names = [p.strip() for p in parts[2].split(",") if p.strip()]
    lecture_root = source_root / parts[0]
    if not lecture_root.is_dir():
        return []
    resolved_dir: Path | None = None
    if (lecture_root / evidence_dir).is_dir():
        resolved_dir = lecture_root / evidence_dir
    else:
        normalized = re.sub(r"[，,].*?(_v\d+)$", r"\1", evidence_dir)
        for candidate in lecture_root.iterdir():
            if not candidate.is_dir():
                continue
            if re.sub(r"[，,].*?(_v\d+)$", r"\1", candidate.name) == normalized:
                resolved_dir = candidate
                break
    if resolved_dir is None:
        return []
    return [resolved_dir / name for name in page_names if (resolved_dir / name).exists()]


def _best_lecture_chunk(
    page_files: list[Path], *, leaf_name: str, keywords: list[str], source_root: Path
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1.0
    for path in page_files:
        try:
            payload = _read_json(path)
        except (OSError, ValueError):
            continue
        blocks = payload if isinstance(payload, list) else payload.get("content_blocks") or []
        file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            relative = str(path.relative_to(source_root))
        except ValueError:
            relative = path.name
        for block in blocks:
            if not isinstance(block, dict) or not block.get("chunk_id"):
                continue
            text = str(block.get("content_markdown") or "")
            score = sum(1.0 for kw in keywords if kw in text)
            if leaf_name and leaf_name in text:
                score += 2.0
            if score > best_score:
                best_score = score
                best = {"chunk": block, "file_sha256": file_sha, "relative_path": relative}
    return best


def _base_pack_units_by_id(base_pack: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not base_pack:
        return {}
    return {
        str(unit.get("unit_id")): unit
        for unit in base_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict) and unit.get("unit_id")
    }


def _compiled_unit_common(leaf: dict[str, Any]) -> dict[str, Any]:
    return {
        "unit_id": _unit_id(leaf["code"]),
        "leaf_id": leaf["code"],
        "leaf_name_path": leaf["name_path"],
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
        "confidence": "high",
    }


# Suffixes the frozen taxonomy uses for over-subdivided abstract nodes (E rules,
# G groupings, R derived requirements) that have no atomic textbook source span.
_ABSTRACT_CODE_RE = re.compile(r"-(?:E\d+|G\d+|R\d+)$")


def _quarantine_bucket(leaf_code: str, leaf_name: str, chunk_markdown: str) -> str:
    """Classify a leaf that could NOT be sliced into a deterministic subsection.

    - ``over_subdivided`` (C): the leaf code is an abstract -Exx/-Gxx/-Rxx node
      that has no atomic source span (taxonomy over-subdivision, not a compile bug).
    - ``mislink`` (A): the leaf name's discriminative core does not appear in the
      chunk markdown at all — the chunk_id points at the wrong content.
    - ``unsliceable`` (B-residual): the core IS in the chunk but no distinct
      subsection boundary could be drawn deterministically (ambiguous / no heading).
    All three quarantine -> ``needs_source`` work order; NONE are auto-relinked
    (a wrong relink is a new pollution — the expert-1 red line)."""
    core = leaf_name_core(leaf_name)
    if _ABSTRACT_CODE_RE.search(leaf_code):
        return "over_subdivided"
    if core and core not in str(chunk_markdown or ""):
        return "mislink"
    return "unsliceable"


def _context_fingerprint(compiled_context: dict[str, Any]) -> str:
    """Deterministic fingerprint over the COMPLETE compiled_context payload.

    v1 fingerprinted only the first 600 chars, so two leaves whose payloads shared
    a 600-char prefix (e.g. identical ``concepts`` head but different trailing
    ``rules``/``teaching_cards``) collided spuriously, while two leaves that
    differed only AFTER char 600 (different concepts but identical shared cards)
    escaped detection. Hashing the whole payload closes both holes: the gate now
    blocks exactly the leaves whose ENTIRE compiled content is byte-identical."""
    text = json.dumps(compiled_context, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]  # noqa: S324 — non-crypto fingerprint


def enforce_no_intra_chunk_pollution(units: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fail-closed structural gate (单一汇点, replaces blocklist patching).

    Invariant: under one ``source_ref.chunk_id``, no two leaves may carry the
    SAME complete compiled_context payload. A collision means leaves were handed
    content that does not distinguish them — the exact pollution shape. Because the
    slicer already guarantees each leaf its OWN span, a surviving full-payload
    collision means the seam genuinely could not tell the leaves apart; there is no
    trustworthy owner. So ALL units in a colliding group are BLOCKED (no
    presumptive owner kept) and returned as quarantine rows, so re-pollution can
    never enter the clean bundle. Returns ``(clean_units, blocked)``.

    A kept owner would require positive ownership proof; lacking that, blocking the
    whole group is the only fail-closed choice. The gate is idempotent and
    order-stable (leaf_id-sorted block rows)."""
    by_chunk: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        cid = str((unit.get("source_ref") or {}).get("chunk_id") or "")
        by_chunk.setdefault(cid, []).append(unit)
    clean: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for cid, group in by_chunk.items():
        if not cid or len(group) < 2:
            clean.extend(group)
            continue
        by_fp: dict[str, list[dict[str, Any]]] = {}
        for unit in group:
            fp = _context_fingerprint(unit.get("compiled_context") or {})
            by_fp.setdefault(fp, []).append(unit)
        for fp, shared in by_fp.items():
            ordered = sorted(shared, key=lambda u: str(u.get("leaf_id") or ""))
            if len(ordered) < 2:
                clean.extend(ordered)
                continue
            # collision with no trustworthy owner: block the WHOLE group.
            colliding_ids = [u.get("leaf_id") for u in ordered]
            for unit in ordered:
                blocked.append(
                    {
                        "leaf_id": unit.get("leaf_id"),
                        "unit_id": unit.get("unit_id"),
                        "chunk_id": cid,
                        "fingerprint": fp,
                        "status": "blocked_intra_chunk_pollution",
                        "quarantine_bucket": "fail_closed_collision",
                        "colliding_leaf_ids": colliding_ids,
                    }
                )
    return clean, blocked


def build_frozen_full_compile(
    *,
    taxonomy: dict[str, Any],
    book_files: list[Path],
    source_root: Path,
    base_pack: dict[str, Any] | None = None,
    pack_version: str = PACK_VERSION,
) -> dict[str, Any]:
    blockers: list[str] = []
    meta = taxonomy.get("meta") if isinstance(taxonomy.get("meta"), dict) else {}
    frozen_tag = str(meta.get("frozen") or "")
    if not frozen_tag.startswith(EXPECTED_FROZEN_PREFIX):
        blockers.append(f"taxonomy_not_frozen_v1:{frozen_tag or 'missing'}")

    leaves = _evidence_leaves(taxonomy)
    if not leaves:
        blockers.append("taxonomy_has_no_evidence_leaves")
    chunks = _chunk_index(book_files, source_root) if not blockers else {}
    if not blockers and not chunks:
        blockers.append("no_book_chunks_loaded")
    base_units = _base_pack_units_by_id(base_pack)

    rows: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    lane_counts: dict[str, int] = {"textbook": 0, "lecture_page": 0, "lecture_unit_carryover": 0}
    unresolved: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []

    # How many evidence leaves point at each textbook chunk_id, and their names.
    # A chunk hosting >1 leaf is where pollution lives: every co-located leaf must
    # get its OWN subsection (positive+negative-checked against the other leaves'
    # cores) or be quarantined — never the whole shared chunk.
    chunk_leaf_count: dict[str, int] = {}
    chunk_leaf_names: dict[str, list[str]] = {}
    for leaf in leaves:
        ev = leaf["evidence"] if isinstance(leaf["evidence"], dict) else {}
        if str(ev.get("source_lane") or "") != "lecture":
            cid = str(ev.get("chunk_id") or "")
            if cid:
                chunk_leaf_count[cid] = chunk_leaf_count.get(cid, 0) + 1
                chunk_leaf_names.setdefault(cid, []).append(leaf["name"])

    def _sibling_cores(chunk_id: str, leaf_name: str) -> tuple[str, ...]:
        """Discriminative cores of the OTHER leaves co-located under ``chunk_id``."""
        own = leaf_name_core(leaf_name)
        cores: list[str] = []
        for other in chunk_leaf_names.get(chunk_id, ()):  # pragma: no branch
            if other == leaf_name:
                continue
            oc = leaf_name_core(other)
            if oc and oc != own and oc not in cores:
                cores.append(oc)
        return tuple(cores)

    if not blockers:
        for leaf in leaves:
            evidence = leaf["evidence"] if isinstance(leaf["evidence"], dict) else {}
            source_file = str(evidence.get("source_file") or "")
            lane = str(evidence.get("source_lane") or "")
            row_base = {"leaf_id": leaf["code"], "unit_id": _unit_id(leaf["code"]), "source_lane": lane}

            if lane != "lecture":
                chunk_id = str(evidence.get("chunk_id") or "")
                entry = chunks.get(chunk_id)
                if entry is None:
                    unresolved.append({**row_base, "status": "evidence_chunk_missing", "chunk_id": chunk_id})
                    rows.append({**row_base, "status": "evidence_chunk_missing", "chunk_id": chunk_id})
                    continue
                chunk = entry["chunk"]
                markdown = str(chunk.get("content_markdown") or "")
                hosts_multiple = chunk_leaf_count.get(chunk_id, 0) > 1
                compiled = compile_context_for_leaf(
                    chunk=chunk,
                    chunk_id=chunk_id,
                    leaf_name=leaf["name"],
                    chunk_hosts_multiple_leaves=hosts_multiple,
                    sibling_cores=_sibling_cores(chunk_id, leaf["name"]),
                )
                if compiled is None:
                    bucket = _quarantine_bucket(leaf["code"], leaf["name"], markdown)
                    q = {
                        **row_base,
                        "status": "needs_source",
                        "chunk_id": chunk_id,
                        "quarantine_bucket": bucket,
                        "leaf_name": leaf["name"],
                    }
                    quarantine.append(q)
                    rows.append({**row_base, "status": "quarantined", "chunk_id": chunk_id, "quarantine_bucket": bucket})
                    continue
                # Per-leaf span hash so two co-located leaves carry distinct provenance:
                # derive the hash from THIS leaf's sliced concepts, not the whole chunk.
                span_text = "\n".join(compiled.get("concepts") or []) or markdown
                units.append(
                    {
                        **_compiled_unit_common(leaf),
                        "compiled_context": compiled,
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
                        "review_source": "frozen_v1_full_compile_per_leaf",
                    }
                )
                lane_counts["textbook"] += 1
                rows.append({**row_base, "status": "compiled_textbook", "chunk_id": chunk_id})
                continue

            referenced_unit_ids = re.findall(r"rtp\w*_[0-9a-f]{8,}", source_file)
            if referenced_unit_ids:
                carried = next((base_units[uid] for uid in referenced_unit_ids if uid in base_units), None)
                if carried is None:
                    unresolved.append({**row_base, "status": "lecture_unit_reference_unresolved", "source_file": source_file})
                    rows.append({**row_base, "status": "lecture_unit_reference_unresolved", "source_file": source_file})
                    continue
                units.append(
                    {
                        **_compiled_unit_common(leaf),
                        "compiled_context": carried.get("compiled_context") or {},
                        "source_ref": carried.get("source_ref") or {},
                        "relative_path": carried.get("relative_path"),
                        "source_lane": "lecture",
                        "review_source": "frozen_v1_base_pack_carryover",
                        "carryover_base_unit_id": carried.get("unit_id"),
                    }
                )
                lane_counts["lecture_unit_carryover"] += 1
                rows.append({**row_base, "status": "compiled_lecture_carryover", "base_unit_id": carried.get("unit_id")})
                continue

            page_files = _resolve_lecture_page_files(source_file, source_root)
            entry = (
                _best_lecture_chunk(page_files, leaf_name=leaf["name"], keywords=leaf["keywords"], source_root=source_root)
                if page_files
                else None
            )
            if entry is None:
                unresolved.append({**row_base, "status": "lecture_page_unresolved", "source_file": source_file})
                rows.append({**row_base, "status": "lecture_page_unresolved", "source_file": source_file})
                continue
            chunk = entry["chunk"]
            chunk_id = str(chunk["chunk_id"])
            markdown = str(chunk.get("content_markdown") or "")
            # Single rule for every lane: slice the leaf's OWN subsection or
            # quarantine. NO whole-chunk fallback (that was the second, looser
            # rule — handing a lecture leaf the whole best-match chunk is the same
            # pollution shape the textbook lane forbids). A lecture chunk is chosen
            # 1:1 per leaf, so it carries no co-located siblings.
            compiled = compile_context_for_leaf(
                chunk=chunk,
                chunk_id=chunk_id,
                leaf_name=leaf["name"],
                chunk_hosts_multiple_leaves=False,
            )
            if compiled is None:
                bucket = _quarantine_bucket(leaf["code"], leaf["name"], markdown)
                quarantine.append(
                    {
                        **row_base,
                        "status": "needs_source",
                        "chunk_id": chunk_id,
                        "quarantine_bucket": bucket,
                        "leaf_name": leaf["name"],
                    }
                )
                rows.append({**row_base, "status": "quarantined", "chunk_id": chunk_id, "quarantine_bucket": bucket})
                continue
            span_text = "\n".join(compiled.get("concepts") or []) or markdown
            units.append(
                {
                    **_compiled_unit_common(leaf),
                    "compiled_context": compiled,
                    "source_ref": {
                        "record_id": f"{entry['relative_path']}#chunk:{chunk_id}",
                        "source_path": entry["relative_path"],
                        "source_lane": "lecture",
                        "chunk_id": chunk_id,
                        "page_num": (chunk.get("source_meta") or {}).get("page_num"),
                        "file_sha256": entry["file_sha256"],
                        "span_hash": source_span_hash(span_text),
                    },
                    "relative_path": entry["relative_path"],
                    "source_lane": "lecture",
                    "review_source": "frozen_v1_full_compile",
                }
            )
            lane_counts["lecture_page"] += 1
            rows.append({**row_base, "status": "compiled_lecture_page", "chunk_id": chunk_id})

    # Fail-closed structural gate (单一汇点): any leaf that still collides with a
    # co-located leaf's compiled_context is BLOCKED out of the clean unit set and
    # routed to quarantine. This makes re-pollution structurally impossible in the
    # clean bundle, replacing the per-leaf blocklist patch.
    gate_blocked: list[dict[str, Any]] = []
    if not blockers and units:
        units, gate_blocked = enforce_no_intra_chunk_pollution(units)
        quarantine.extend(gate_blocked)

    quarantine_buckets: dict[str, int] = {}
    for q in quarantine:
        b = str(q.get("quarantine_bucket") or "unspecified")
        quarantine_buckets[b] = quarantine_buckets.get(b, 0) + 1

    pack: dict[str, Any] | None = None
    if not blockers and units:
        pack = {
            "schema": RUNTIME_SCHEMA,
            "version": pack_version,
            "status": PACK_STATUS,
            "frozen_axis": {
                "frozen": frozen_tag,
                "node_count": (taxonomy.get("stats") or {}).get("total_nodes"),
                "evidence_leaf_count": len(leaves),
            },
            "runtime_token_pack_units": units,
            "non_runtime_accounted_items": unresolved,
            "quarantine": {
                "quarantine_candidate_unit_ids": sorted(
                    {str(q.get("unit_id")) for q in quarantine if q.get("unit_id")}
                ),
                "quarantine_rows": quarantine,
                "quarantine_buckets": dict(quarantine_buckets),
                "fail_closed_gate": "enforce_no_intra_chunk_pollution",
            },
            "classification": dict(CLASSIFICATION),
            "safety": dict(SAFETY),
            "summary": {
                "unit_count": len(units),
                "evidence_leaf_count": len(leaves),
                "unresolved_count": len(unresolved),
                "quarantine_count": len(quarantine),
                "quarantine_buckets": dict(quarantine_buckets),
                "gate_blocked_count": len(gate_blocked),
                "lane_counts": dict(lane_counts),
                "production_write_count": 0,
            },
        }

    verdict = "PASS_FROZEN_FULL_COMPILE" if pack is not None else "BLOCKED_FROZEN_FULL_COMPILE"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "frozen_tag": frozen_tag,
        "blockers": blockers,
        "rows": rows,
        "unresolved": unresolved,
        "quarantine": quarantine,
        "runtime_token_pack": pack,
        "summary": {
            "evidence_leaf_count": len(leaves),
            "compiled_unit_count": len(units),
            "unresolved_count": len(unresolved),
            "quarantine_count": len(quarantine),
            "quarantine_buckets": dict(quarantine_buckets),
            "gate_blocked_count": len(gate_blocked),
            "lane_counts": dict(lane_counts),
            "blocker_count": len(blockers),
            "production_write_count": 0,
        },
        "not_exercised": NOT_EXERCISED,
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--book-file", dest="book_files", type=Path, action="append", default=None)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--base-pack", type=Path, default=DEFAULT_BASE_PACK)
    parser.add_argument("--no-base-pack", action="store_true")
    parser.add_argument("--pack-version", default=PACK_VERSION)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_DIR / "frozen_full_compile_report.json")
    parser.add_argument("--output-pack", type=Path, default=DEFAULT_OUTPUT_DIR / "runtime_token_pack_v30_frozen_full.json")
    args = parser.parse_args(argv)

    base_pack = None
    if not args.no_base_pack and args.base_pack.exists():
        base_pack = _read_json_object(args.base_pack)
    report = build_frozen_full_compile(
        taxonomy=_read_json_object(args.taxonomy),
        book_files=args.book_files or DEFAULT_BOOK_FILES,
        source_root=args.source_root,
        base_pack=base_pack,
        pack_version=args.pack_version,
    )
    pack = report.pop("runtime_token_pack", None)
    report["runtime_token_pack_path"] = str(args.output_pack) if pack else None
    _write_json(args.output_report, report)
    if pack is not None:
        _write_json(args.output_pack, pack)
    print(
        json.dumps(
            {
                "output_report": str(args.output_report),
                "output_pack": str(args.output_pack) if pack else None,
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
