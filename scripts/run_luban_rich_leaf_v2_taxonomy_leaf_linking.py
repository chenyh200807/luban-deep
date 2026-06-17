#!/usr/bin/env python3
"""Link RuntimeTokenPack v2 source-file context units to canonical taxonomy leaves as shadow candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v2_20260612/runtime_token_pack_v2.json"
)
DEFAULT_TAXONOMY_INDEX = (
    REPO / "deeptutor/services/construction_grading/runtime_supply/v_canonical_taxonomy_index/canonical_taxonomy_index.json"
)
DEFAULT_OUTPUT = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v2_taxonomy_leaf_linking_20260612/taxonomy_leaf_linking.json"
)
SCHEMA = "luban_rich_leaf_v2_taxonomy_leaf_linking.v1"
TOKEN_PACK_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2"
TAXONOMY_SCHEMA = "luban_canonical_taxonomy_index.v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _flatten_context(unit: dict[str, Any]) -> list[str]:
    values: list[str] = []
    values.append(str(unit.get("relative_path") or ""))
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    values.append(str(source_ref.get("excerpt") or ""))
    compiled_context = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    for field_values in compiled_context.values():
        if isinstance(field_values, list):
            values.extend(str(value) for value in field_values if value)
        elif field_values:
            values.append(str(field_values))
    return [value.strip() for value in values if value and value.strip()]


def _segments(text: str) -> list[str]:
    parts = re.split(r"[>\s/、，,。；;：:（）()\[\]【】《》\"'“”]+", text)
    return [part.strip() for part in parts if len(part.strip()) >= 2]


def _score_leaf(unit_terms: list[str], haystack: str, leaf: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    name_path = str(leaf.get("name_path") or "")
    leaf_name_segments = _segments(name_path)
    keywords = [str(keyword) for keyword in (leaf.get("keywords") or []) if str(keyword).strip()]

    for keyword in keywords:
        if len(keyword) < 2:
            continue
        if keyword in haystack:
            score += 5
            reasons.append(f"keyword:{keyword}")
        elif any(keyword in term or term in keyword for term in unit_terms if len(term) >= 3):
            score += 2
            reasons.append(f"keyword_partial:{keyword}")

    for segment in leaf_name_segments[-4:]:
        if segment in haystack:
            score += 3
            reasons.append(f"name_path_segment:{segment}")

    code = str(leaf.get("code") or "")
    if code and code[:7] in haystack:
        score += 1
        reasons.append(f"code_prefix:{code[:7]}")

    return score, reasons[:8]


def _dedupe_leaves_by_code(leaves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_code: dict[str, dict[str, Any]] = {}
    for leaf in leaves:
        code = str(leaf.get("code") or "")
        if not code:
            continue
        existing = by_code.setdefault(
            code,
            {
                "code": code,
                "name_path": leaf.get("name_path"),
                "keywords": [],
                "duplicate_row_count": 0,
            },
        )
        existing["duplicate_row_count"] = int(existing.get("duplicate_row_count") or 0) + 1
        if not existing.get("name_path") and leaf.get("name_path"):
            existing["name_path"] = leaf.get("name_path")
        keywords = existing["keywords"] if isinstance(existing.get("keywords"), list) else []
        for keyword in leaf.get("keywords") or []:
            text = str(keyword).strip()
            if text and text not in keywords:
                keywords.append(text)
        existing["keywords"] = keywords
    return list(by_code.values())


def _link_unit(unit: dict[str, Any], leaves: list[dict[str, Any]], *, top_k: int) -> dict[str, Any]:
    unit_terms = _flatten_context(unit)
    haystack = "\n".join(unit_terms)
    scored: list[dict[str, Any]] = []
    for leaf in leaves:
        score, reasons = _score_leaf(unit_terms, haystack, leaf)
        if score <= 0:
            continue
        scored.append(
            {
                "leaf_id": leaf.get("code"),
                "name_path": leaf.get("name_path"),
                "score": score,
                "match_reasons": reasons,
            }
        )
    scored.sort(key=lambda item: (-int(item["score"]), str(item["leaf_id"])))
    top = scored[:top_k]
    top_score = int(top[0]["score"]) if top else 0
    second_score = int(top[1]["score"]) if len(top) > 1 else 0
    if top_score >= 8 and top_score - second_score >= 2:
        status = "linked_shadow_candidate"
    elif top_score >= 4:
        status = "weak_link_candidate"
    else:
        status = "unresolved"
    link_id = hashlib.sha256(f"{unit.get('unit_id')}:{top[0].get('leaf_id') if top else 'unresolved'}".encode()).hexdigest()[:20]
    return {
        "link_id": f"taxonomy_link:{link_id}",
        "unit_id": unit.get("unit_id"),
        "candidate_id": unit.get("candidate_id"),
        "relative_path": unit.get("relative_path"),
        "source_lane": unit.get("source_lane"),
        "status": status,
        "top_score": top_score,
        "score_margin": top_score - second_score,
        "candidate_leaf_links": top,
        "candidate_only": True,
        "review_only": True,
        "runtime_install_allowed": False,
        "production_default": False,
    }


def run_taxonomy_leaf_linking(
    *,
    runtime_token_pack: dict[str, Any],
    taxonomy_index: dict[str, Any],
    top_k: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    if runtime_token_pack.get("schema") != TOKEN_PACK_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    manifest = taxonomy_index.get("manifest") if isinstance(taxonomy_index.get("manifest"), dict) else {}
    if manifest.get("schema_version") != TAXONOMY_SCHEMA:
        blockers.append(f"taxonomy_schema_mismatch:{manifest.get('schema_version')}")
    raw_leaves = [leaf for leaf in (taxonomy_index.get("leaves") or []) if isinstance(leaf, dict) and leaf.get("code")]
    leaves = _dedupe_leaves_by_code(raw_leaves)
    if not leaves:
        blockers.append("taxonomy_leaves_missing")

    units = [
        unit
        for unit in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict) and unit.get("unit_id")
    ]
    links = [] if blockers else [_link_unit(unit, leaves, top_k=top_k) for unit in units]
    status_counts: dict[str, int] = {}
    for link in links:
        status_counts[str(link["status"])] = status_counts.get(str(link["status"]), 0) + 1

    verdict = "PASS_TAXONOMY_LEAF_LINKING_SHADOW_CANDIDATES" if not blockers else "NO_GO_TAXONOMY_LEAF_LINKING_INPUT_INVALID"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "taxonomy_manifest": manifest,
        "summary": {
            "blocker_count": len(blockers),
            "input_unit_count": len(units),
            "taxonomy_leaf_row_count": len(raw_leaves),
            "taxonomy_leaf_count": len(leaves),
            "taxonomy_duplicate_row_count": max(0, len(raw_leaves) - len(leaves)),
            "link_count": len(links),
            "status_counts": status_counts,
            "strong_link_count": status_counts.get("linked_shadow_candidate", 0),
            "weak_link_count": status_counts.get("weak_link_candidate", 0),
            "unresolved_count": status_counts.get("unresolved", 0),
        },
        "taxonomy_leaf_links": links,
        "blockers": blockers,
        "not_exercised": [
            "manual_taxonomy_review",
            "canonical_leaf_pointer_write",
            "runtime_default_install",
            "production_db_write",
            "release_truth_governance",
        ],
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "taxonomy_leaf_linking": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "canonical_pointer_written": False,
            "release_truth_claimed": False,
        },
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
    parser.add_argument("--runtime-token-pack", type=Path, default=DEFAULT_RUNTIME_TOKEN_PACK)
    parser.add_argument("--taxonomy-index", type=Path, default=DEFAULT_TAXONOMY_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)

    report = run_taxonomy_leaf_linking(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        taxonomy_index=_read_json(args.taxonomy_index),
        top_k=max(1, args.top_k),
    )
    _write_json(args.output, report)
    print(json.dumps({"out": str(args.output), "verdict": report["verdict"], "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if report["verdict"] == "PASS_TAXONOMY_LEAF_LINKING_SHADOW_CANDIDATES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
