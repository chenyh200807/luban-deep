#!/usr/bin/env python3
"""Build quote-grounded repair candidates for v2.3 live-residual runtime units.

Each repair replaces a polluted unit's compiled_context with content compiled
deterministically from a canonical textbook chunk named by a repair manifest.
Fail-closed gates:

- only units named by the live residual work orders may be repaired;
- the manifest span_text must literally appear in the named chunk;
- the leaf's canonical taxonomy keywords must overlap the repaired evidence
  above a threshold (the discriminative check the original linker lacked).

This produces candidate/review artifacts only. It never installs runtime
defaults, never writes canonical truth, and never writes production stores.
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

SCHEMA = "luban_rich_leaf_v23_residual_source_repair.v1"
MANIFEST_SCHEMA = "luban_rich_leaf_v23_residual_repair_manifest.v1"
RUNTIME_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
WORK_ORDERS_SCHEMA = "luban_rich_leaf_v23_live_residual_work_orders.v1"
PATCHED_VERSION = "v2.3.1_residual_repair_candidate_20260612"

DEFAULT_RUNTIME_TOKEN_PACK = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_runtime_token_pack_v23_20260612/runtime_token_pack_v23.json"
)
DEFAULT_WORK_ORDERS = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v23_live_residual_work_orders_20260612/live_residual_work_orders_sample8_promptfix.json"
)
DEFAULT_TAXONOMY = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json"
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_full2026_v231_residual_repair_20260612"

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "residual_repair_patch": True,
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


def _safety_blockers(name: str, payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    if classification.get("candidate_only") is not True:
        blockers.append(f"{name}:candidate_only_not_true")
    if classification.get("review_only") is not True:
        blockers.append(f"{name}:review_only_not_true")
    for key in ("runtime_install_allowed", "production_default", "release_truth_claimed"):
        if classification.get(key) is not False:
            blockers.append(f"{name}:{key}_not_false")
    if safety and int(safety.get("production_write_count") or 0) != 0:
        blockers.append(f"{name}:production_write_count_nonzero")
    return blockers


def _taxonomy_leaves_by_code(taxonomy: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    leaves: dict[str, list[dict[str, Any]]] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            code = node.get("code")
            name = node.get("name")
            if code and name:
                entry = {"code": str(code), "name": str(name), "keywords": [str(k) for k in node.get("keywords") or []]}
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


def _find_chunk(chunk_file: Path, chunk_id: str) -> dict[str, Any] | None:
    try:
        book = _read_json(chunk_file)
    except (OSError, ValueError):
        return None
    for block in book.get("content_blocks") or []:
        if isinstance(block, dict) and block.get("chunk_id") == chunk_id:
            return block
    return None


def _keyword_overlap(keywords: list[str], evidence_text: str) -> tuple[float, list[str]]:
    if not keywords:
        return 0.0, []
    hit = [kw for kw in keywords if kw in evidence_text]
    return len(hit) / len(keywords), hit


def _text_overlaps_span(text: str, span_text: str) -> bool:
    """Character-bigram overlap of ``text`` against ``span_text`` (>= 0.6). The
    primitive both card and exam-pattern attribution share."""
    content = str(text or "")
    if len(content) < 4 or not span_text:
        return False
    grams = {content[i : i + 2] for i in range(len(content) - 1)}
    if not grams:
        return False
    span_grams = {span_text[i : i + 2] for i in range(len(span_text) - 1)}
    overlap = len(grams & span_grams) / len(grams)
    return overlap >= 0.6


def _card_overlaps_span(card: dict[str, Any], span_text: str) -> bool:
    """Deterministic per-leaf attribution: does a knowledge card belong to THIS
    leaf's span? Cards are condensed paraphrases, so we test character-bigram
    overlap (robust to light rewording) against a conservative threshold. A card
    that does not clearly overlap the span is DROPPED — carrying the whole chunk's
    cards to every co-located leaf is a silent pollution channel (a 天窗 leaf must
    not inherit the 门 leaf's teaching cards). When in doubt, drop (abstain).

    Attribution considers BOTH ``card_title`` and ``card_content``: a card belongs
    to the span if EITHER overlaps it. A heavily-reworded card whose CONTENT drifts
    from the source prose can still be correctly attributed by its title (which is
    typically the verbatim subsection topic), reducing over-dropping of legitimate
    paraphrase cards. A foreign card's title will not match this leaf's span, so the
    fail-closed direction (reject the 门 card from a 天窗 leaf) is preserved."""
    title = str(card.get("card_title") or "")
    content = str(card.get("card_content") or "")
    return _text_overlaps_span(title, span_text) or _text_overlaps_span(content, span_text)


def _compile_context(
    span_text: str, chunk: dict[str, Any], chunk_id: str, *, span_scoped: bool = False
) -> dict[str, list[str]]:
    sentences = [s.strip() + "。" for s in span_text.split("。") if s.strip()]
    cards = [c for c in chunk.get("knowledge_cards") or [] if isinstance(c, dict)]
    assessment = chunk.get("assessment") if isinstance(chunk.get("assessment"), dict) else {}

    # When the leaf is a true sub-section of a larger chunk, chunk-level cards /
    # assessment are restricted to those whose content overlaps THIS leaf's span,
    # so co-located leaves carry distinct annotations (not the whole chunk's).
    if span_scoped:
        cards = [c for c in cards if _card_overlaps_span(c, span_text)]
        # Attribute the exam pattern by its question OR its grading_keywords: a
        # question reworded away from the span prose can still be anchored by its
        # keywords (often the verbatim采分点 terms), reducing over-dropping.
        q_text = str(assessment.get("generated_question") or "")
        kw_text = " ".join(str(k) for k in (assessment.get("grading_keywords") or []))
        if not (_text_overlaps_span(q_text, span_text) or _text_overlaps_span(kw_text, span_text)):
            assessment = {}

    rules = [
        json.dumps(
            {
                "id": f"R{i + 1}",
                "description": str(card.get("card_content") or ""),
                "severity": "informative",
                "source_refs": [chunk_id],
            },
            ensure_ascii=False,
        )
        for i, card in enumerate(cards)
        if card.get("card_content")
    ]
    teaching_cards = [
        json.dumps(
            {
                "id": f"TC{i + 1}",
                "title": str(card.get("card_title") or ""),
                "content": str(card.get("card_content") or ""),
                "source_refs": [chunk_id],
            },
            ensure_ascii=False,
        )
        for i, card in enumerate(cards)
        if card.get("card_content")
    ]
    exam_patterns = []
    if assessment.get("generated_question"):
        exam_patterns.append(
            json.dumps(
                {
                    "id": "EP1",
                    "description": str(assessment["generated_question"]),
                    "grading_keywords": [str(k) for k in assessment.get("grading_keywords") or []],
                    "source_refs": [chunk_id],
                },
                ensure_ascii=False,
            )
        )
    context: dict[str, list[str]] = {"concepts": sentences[:4]}
    if rules:
        context["rules"] = rules
    if teaching_cards:
        context["teaching_cards"] = teaching_cards
    if exam_patterns:
        context["exam_patterns"] = exam_patterns
    return context


def compile_context_for_leaf(
    *,
    chunk: dict[str, Any],
    chunk_id: str,
    leaf_name: str,
    chunk_hosts_multiple_leaves: bool,
    sibling_cores: tuple[str, ...] = (),
) -> dict[str, list[str]] | None:
    """Per-leaf compile entry: 编译单位 = 召回单位 = leaf.

    Slices the leaf's OWN subsection out of the chunk markdown (heading match on
    the leaf name, guarded by a positive+negative check against ``sibling_cores``)
    and compiles compiled_context from that span only — so two leaves under one
    chunk get distinct content. Returns ``None`` when no distinct subsection can be
    deterministically located; the caller MUST quarantine (never fall back to the
    whole chunk, which is the original pollution).

    This is the single fix for the root cause that ``_compile_context`` ignored
    ``leaf_name`` and handed the whole chunk to every co-located leaf.
    """
    from scripts.luban_rich_leaf_subsection import slice_leaf_subsection

    markdown = str(chunk.get("content_markdown") or "")
    sub = slice_leaf_subsection(
        markdown,
        leaf_name,
        chunk_hosts_multiple_leaves=chunk_hosts_multiple_leaves,
        sibling_cores=sibling_cores,
    )
    if sub is None:
        return None
    # When the leaf is a true sub-section of a larger chunk, only the prose
    # (``concepts``) is sliced per-leaf; ``rules``/``teaching_cards``/
    # ``exam_patterns`` are chunk-level annotations. Restrict those to the ones
    # whose content actually overlaps THIS leaf's span, so co-located leaves do
    # not all carry the whole chunk's cards (a second, silent pollution channel).
    span_scoped = sub.text.strip() != markdown.strip()
    return _compile_context(sub.text, chunk, chunk_id, span_scoped=span_scoped)


def build_v23_residual_source_repair(
    *,
    runtime_token_pack: dict[str, Any],
    work_orders: dict[str, Any],
    manifest: dict[str, Any],
    taxonomy: dict[str, Any],
    min_keyword_overlap: float = 0.6,
) -> dict[str, Any]:
    blockers: list[str] = []
    if runtime_token_pack.get("schema") != RUNTIME_SCHEMA:
        blockers.append(f"runtime_token_pack_schema_mismatch:{runtime_token_pack.get('schema')}")
    if work_orders.get("schema") != WORK_ORDERS_SCHEMA:
        blockers.append(f"work_orders_schema_mismatch:{work_orders.get('schema')}")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        blockers.append(f"manifest_schema_mismatch:{manifest.get('schema')}")
    blockers.extend(_safety_blockers("runtime_token_pack", runtime_token_pack))
    blockers.extend(_safety_blockers("work_orders", work_orders))

    work_order_units = {
        str(order.get("unit_id")): order
        for order in work_orders.get("work_orders") or []
        if isinstance(order, dict) and order.get("unit_id")
    }
    units_by_id = {
        str(unit.get("unit_id")): unit
        for unit in runtime_token_pack.get("runtime_token_pack_units") or []
        if isinstance(unit, dict) and unit.get("unit_id")
    }
    leaves_by_code = _taxonomy_leaves_by_code(taxonomy)

    repairs: list[dict[str, Any]] = []
    follow_up_work_orders: list[dict[str, Any]] = []
    seen_duplicate_codes: set[str] = set()
    candidates = [c for c in manifest.get("repair_candidates") or [] if isinstance(c, dict)]
    if not candidates:
        blockers.append("manifest_has_no_repair_candidates")

    for candidate in candidates:
        unit_id = str(candidate.get("unit_id") or "")
        leaf_id = str(candidate.get("leaf_id") or "")
        leaf_name = str(candidate.get("leaf_name") or "")
        chunk_id = str(candidate.get("chunk_id") or "")
        span_text = str(candidate.get("span_text") or "")
        chunk_file = Path(str(candidate.get("chunk_file") or ""))

        if unit_id not in work_order_units:
            blockers.append(f"{unit_id}:unit_not_named_by_residual_work_orders")
            continue
        unit = units_by_id.get(unit_id)
        if unit is None:
            blockers.append(f"{unit_id}:unit_not_in_runtime_token_pack")
            continue
        if str(unit.get("leaf_id")) != leaf_id:
            blockers.append(f"{unit_id}:manifest_leaf_id_mismatch")
            continue

        chunk = _find_chunk(chunk_file, chunk_id)
        if chunk is None:
            blockers.append(f"{unit_id}:chunk_not_found:{chunk_id}")
            continue
        content_markdown = str(chunk.get("content_markdown") or "")
        if span_text not in content_markdown:
            blockers.append(f"{unit_id}:span_text_not_found_in_chunk:{chunk_id}")
            continue

        taxonomy_entries = leaves_by_code.get(leaf_id) or []
        if len(taxonomy_entries) > 1 and leaf_id not in seen_duplicate_codes:
            seen_duplicate_codes.add(leaf_id)
            follow_up_work_orders.append(
                {
                    "work_order_type": "taxonomy_duplicate_code",
                    "leaf_id": leaf_id,
                    "conflicting_leaf_names": [entry["name"] for entry in taxonomy_entries],
                    "recommended_action": "canonical taxonomy owner must assign unique codes before this leaf can carry canonical truth",
                    "candidate_only": True,
                    "review_only": True,
                }
            )
        leaf_entry = next((entry for entry in taxonomy_entries if entry["name"] == leaf_name), None)
        if leaf_entry is None:
            blockers.append(f"{unit_id}:leaf_name_not_in_canonical_taxonomy:{leaf_name}")
            continue

        cards_text = json.dumps(chunk.get("knowledge_cards") or [], ensure_ascii=False)
        overlap, hit_keywords = _keyword_overlap(leaf_entry["keywords"], span_text + cards_text)
        old_overlap, _ = _keyword_overlap(
            leaf_entry["keywords"], json.dumps(unit.get("compiled_context") or {}, ensure_ascii=False)
        )
        if overlap < min_keyword_overlap:
            blockers.append(
                f"{unit_id}:keyword_overlap_below_threshold:{overlap:.2f}<{min_keyword_overlap:.2f}"
            )
            continue

        source_meta = chunk.get("source_meta") if isinstance(chunk.get("source_meta"), dict) else {}
        relative_path = str(candidate.get("source_relative_path") or chunk_file.name)
        new_source_ref = {
            "record_id": f"{relative_path}#chunk:{chunk_id}",
            "source_path": relative_path,
            "source_lane": "textbook",
            "chunk_id": chunk_id,
            "page_num": source_meta.get("page_num"),
            "file_sha256": hashlib.sha256(chunk_file.read_bytes()).hexdigest(),
            "span_hash": source_span_hash(span_text),
        }
        repaired_unit = {
            **unit,
            "compiled_context": _compile_context(span_text, chunk, chunk_id),
            "source_ref": new_source_ref,
            "relative_path": relative_path,
            "source_lane": "source_truth",
            "review_source": "residual_source_repair_candidate",
            "repair": {
                "base_work_order_id": work_order_units[unit_id].get("work_order_id"),
                "investigation_note": str(candidate.get("investigation_note") or ""),
                "replaced_source_path": (unit.get("source_ref") or {}).get("source_path"),
                "keyword_overlap_old": round(old_overlap, 4),
                "keyword_overlap_new": round(overlap, 4),
                "keyword_hits": hit_keywords,
            },
        }
        repairs.append(repaired_unit)

    patched_pack: dict[str, Any] | None = None
    if not blockers and repairs:
        repaired_by_id = {str(u["unit_id"]): u for u in repairs}
        patched_units = [
            repaired_by_id.get(str(unit.get("unit_id")), unit)
            for unit in runtime_token_pack.get("runtime_token_pack_units") or []
        ]
        patched_pack = {
            **runtime_token_pack,
            "version": PATCHED_VERSION,
            "runtime_token_pack_units": patched_units,
            "classification": {**runtime_token_pack.get("classification", {}), **CLASSIFICATION},
            "safety": {**runtime_token_pack.get("safety", {}), **SAFETY},
            "patch_lineage": {
                "base_version": runtime_token_pack.get("version"),
                "patched_unit_ids": sorted(repaired_by_id),
                "repair_schema": SCHEMA,
            },
        }

    verdict = (
        "PASS_V23_RESIDUAL_SOURCE_REPAIR_CANDIDATES"
        if patched_pack is not None
        else "BLOCKED_V23_RESIDUAL_SOURCE_REPAIR"
    )
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "quality_claim_allowed": False,
        "blockers": blockers,
        "repaired_unit_count": len(repairs),
        "repairs": [
            {
                "unit_id": u["unit_id"],
                "leaf_id": u["leaf_id"],
                "leaf_name_path": u.get("leaf_name_path"),
                "source_ref": u["source_ref"],
                "repair": u["repair"],
            }
            for u in repairs
        ],
        "follow_up_work_orders": follow_up_work_orders,
        "patched_runtime_token_pack": patched_pack,
        "summary": {
            "repair_candidate_count": len(candidates),
            "repaired_unit_count": len(repairs),
            "follow_up_work_order_count": len(follow_up_work_orders),
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
    parser.add_argument("--work-orders", type=Path, default=DEFAULT_WORK_ORDERS)
    parser.add_argument("--repair-manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument("--min-keyword-overlap", type=float, default=0.6)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_DIR / "residual_source_repair_report.json")
    parser.add_argument("--output-pack", type=Path, default=DEFAULT_OUTPUT_DIR / "runtime_token_pack_v231_candidate.json")
    args = parser.parse_args(argv)

    report = build_v23_residual_source_repair(
        runtime_token_pack=_read_json(args.runtime_token_pack),
        work_orders=_read_json(args.work_orders),
        manifest=_read_json(args.repair_manifest),
        taxonomy=_read_json(args.taxonomy),
        min_keyword_overlap=args.min_keyword_overlap,
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
    return 0 if report["verdict"] == "PASS_V23_RESIDUAL_SOURCE_REPAIR_CANDIDATES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
