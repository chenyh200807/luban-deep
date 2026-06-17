#!/usr/bin/env python3
"""Scoring-point enrichment compile: v3.1.1 frozen pack -> v3.2 candidate pack.

Upgrades the rich-leaf compile target from "教材要点" to "采分点形态" by attaching a
``compiled_context.scoring_points`` family to each v3.1.1 unit, reconnecting the
M35 scoring-point artifact line:

- m35_artifact lane: gold scoring points (luban_case_grading_golden_v1 + the
  tracked v1_limited_default typed-policy bundle) migrate onto every unit whose
  source chunk_id equals the point's textbook evidence chunk_id. Only points
  carrying real textbook provenance (source_authority=textbook + quote +
  chunk_id) migrate — 无溯源不造点.
- chunk_assessment / knowledge_card lanes: candidates derived from the unit's
  own textbook chunk (assessment.grading_keywords + knowledge_cards). A derived
  required_term survives ONLY if it appears verbatim in the chunk's
  content_markdown; a candidate with zero surviving terms is dropped.

Candidate/review tier only: writes a NEW v3.2 pack artifact (never overwrites
v3.1.1), never installs runtime defaults, never writes canonical truth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SCHEMA = "luban_rich_leaf_scoring_point_compile.v1"
PACK_VERSION = "v3.2_scoring_points_enriched"
DEFAULT_GOLDEN = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
DEFAULT_TYPED_POLICY = (
    REPO / "deeptutor/services/construction_grading/runtime_supply/v1_limited_default/golden_typed_policy.jsonl"
)
DEFAULT_BASE_PACK = (
    REPO
    / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v11_coverage_expansion_20260613"
    / "runtime_token_pack_v311_quarantine_annotated.json"
)
SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_BOOK_FILES = [
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    SOURCE_ROOT / "2026教材/第二次加强/FINAL_CLEANED_BOOK2026-222-382_fixed.json",
]
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_v32_scoring_point_compile_20260613"

MAX_DERIVED_CARDS_PER_UNIT = 4
QUOTE_CONTEXT_BEFORE = 30
QUOTE_CONTEXT_AFTER = 60

CLASSIFICATION = {
    "candidate_only": True,
    "review_only": True,
    "scoring_point_enriched": True,
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _term_quote(text: str, term: str) -> str:
    """Verbatim textbook span around the first occurrence of ``term`` (provenance quote)."""
    idx = text.find(term)
    if idx < 0:
        return ""
    start = max(0, idx - QUOTE_CONTEXT_BEFORE)
    end = min(len(text), idx + len(term) + QUOTE_CONTEXT_AFTER)
    return " ".join(text[start:end].split())


def load_m35_scoring_points(
    golden: dict[str, Any], typed_rows: list[dict[str, Any]]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Project M35 gold scoring points into chunk_id-keyed migration candidates.

    Hard gate: a point migrates ONLY with real textbook provenance
    (evidence_policy.source_authority == "textbook" AND a non-empty quote AND chunk_id).
    Everything else is accounted, never fabricated."""
    typed = {
        (str(r.get("case_id")), str(r.get("point_id"))): r.get("typed_policy") or {}
        for r in typed_rows
        if isinstance(r, dict)
    }
    by_chunk: dict[str, list[dict[str, Any]]] = {}
    total = 0
    migratable = 0
    skipped = 0
    for case in golden.get("cases") or []:
        case_id = str(case.get("case_id") or "")
        for gold_sp in case.get("gold_scoring_points") or []:
            total += 1
            point_id = str(gold_sp.get("point_id") or "")
            policy = typed.get((case_id, point_id)) or {}
            evidence = policy.get("evidence_policy") or {}
            quote = str(evidence.get("textbook_quote") or "").strip()
            chunk_id = str(evidence.get("chunk_id") or "").strip()
            if evidence.get("source_authority") != "textbook" or not quote or not chunk_id:
                skipped += 1
                continue
            migratable += 1
            by_chunk.setdefault(chunk_id, []).append(
                {
                    "point_id": f"m35:{case_id}:{point_id}",
                    "source": "m35_artifact",
                    "statement": str(gold_sp.get("label") or "").strip(),
                    "max_score": gold_sp.get("max_score"),
                    "policy_type": str(policy.get("policy_type") or "semantic_allowed"),
                    "required_terms": [str(t) for t in (policy.get("required_terms") or []) if str(t).strip()],
                    "provenance": {
                        "source_authority": "textbook",
                        "chunk_id": chunk_id,
                        "quote": quote,
                        "case_id": case_id,
                        "gold_point_id": point_id,
                    },
                }
            )
    accounting = {
        "gold_points_total": total,
        "migratable_with_textbook_provenance": migratable,
        "skipped_no_textbook_provenance": skipped,
        "distinct_evidence_chunks": len(by_chunk),
    }
    return by_chunk, accounting


def derive_chunk_scoring_points(chunk: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive scoring-point candidates from a textbook chunk's assessment + knowledge_cards.

    Hard gate (教材原文溯源): a required_term survives only if it appears verbatim in the
    chunk's content_markdown; a candidate with zero surviving terms is dropped entirely."""
    chunk_id = str(chunk.get("chunk_id") or "")
    text = str(chunk.get("content_markdown") or "")
    if not chunk_id or not text:
        return []
    points: list[dict[str, Any]] = []

    assessment = chunk.get("assessment") if isinstance(chunk.get("assessment"), dict) else {}
    statement = str(assessment.get("generated_question") or "").strip()
    terms = [str(k).strip() for k in (assessment.get("grading_keywords") or []) if str(k).strip() in text]
    if statement and terms:
        points.append(
            {
                "point_id": f"ca:{chunk_id}",
                "source": "chunk_assessment",
                "statement": statement,
                "max_score": None,
                "policy_type": "semantic_allowed",
                "required_terms": terms,
                "provenance": {
                    "source_authority": "textbook",
                    "chunk_id": chunk_id,
                    "quote": _term_quote(text, terms[0]),
                    "quote_verified": True,
                },
            }
        )

    cards = [c for c in chunk.get("knowledge_cards") or [] if isinstance(c, dict)]
    kept = 0
    for i, card in enumerate(cards):
        if kept >= MAX_DERIVED_CARDS_PER_UNIT:
            break
        title = str(card.get("card_title") or "").strip()
        raw_terms = [str(k).strip() for k in list(card.get("keywords") or []) + list(card.get("key_numbers") or [])]
        card_terms = [t for t in dict.fromkeys(raw_terms) if t and t in text]
        if not title or not card_terms:
            continue
        content = " ".join(str(card.get("card_content") or "").split())
        statement = f"{title}：{content[:160]}" if content else title
        points.append(
            {
                "point_id": f"kc:{chunk_id}:{i}",
                "source": "knowledge_card",
                "statement": statement,
                "max_score": None,
                "policy_type": "semantic_allowed",
                "required_terms": card_terms,
                "provenance": {
                    "source_authority": "textbook",
                    "chunk_id": chunk_id,
                    "quote": _term_quote(text, card_terms[0]),
                    "quote_verified": True,
                },
            }
        )
        kept += 1
    return points


def attach_scoring_points(
    pack: dict[str, Any],
    *,
    m35_by_chunk: dict[str, list[dict[str, Any]]],
    chunk_lookup: dict[str, dict[str, Any]],
    pack_version: str = PACK_VERSION,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the v3.2 pack: a deep copy of the base pack with ``compiled_context.scoring_points``
    attached per unit (m35 migration first, then chunk-derived candidates). Never mutates the
    base pack; units with nothing traceable get NO scoring_points key (accounted)."""
    new_pack = json.loads(json.dumps(pack))
    new_pack["version"] = pack_version
    points_by_source: dict[str, int] = {}
    units_with_points = 0
    units_without_points = 0
    m35_attachments = 0
    attached_m35_point_ids: set[str] = set()
    for unit in new_pack.get("runtime_token_pack_units") or []:
        chunk_id = str((unit.get("source_ref") or {}).get("chunk_id") or "")
        chunk = chunk_lookup.get(chunk_id)
        text = str((chunk or {}).get("content_markdown") or "")
        scoring_points: list[dict[str, Any]] = []
        for point in m35_by_chunk.get(chunk_id) or []:
            migrated = json.loads(json.dumps(point))
            migrated["provenance"]["quote_verified"] = bool(text) and migrated["provenance"]["quote"] in text
            scoring_points.append(migrated)
            m35_attachments += 1
            attached_m35_point_ids.add(migrated["point_id"])
        if chunk is not None:
            scoring_points.extend(derive_chunk_scoring_points(chunk))
        if scoring_points:
            compiled = unit.get("compiled_context")
            if not isinstance(compiled, dict):
                compiled = {}
                unit["compiled_context"] = compiled
            compiled["scoring_points"] = scoring_points
            units_with_points += 1
            for point in scoring_points:
                points_by_source[point["source"]] = points_by_source.get(point["source"], 0) + 1
        else:
            units_without_points += 1
    stats = {
        "units_total": len(new_pack.get("runtime_token_pack_units") or []),
        "units_with_scoring_points": units_with_points,
        "units_without_scoring_points": units_without_points,
        "points_by_source": points_by_source,
        "points_total": sum(points_by_source.values()),
        "m35_points_attached": len(attached_m35_point_ids),
        "m35_attachments_total": m35_attachments,
    }
    new_pack["status"] = str(pack.get("status") or "candidate_ready_for_shadow_ab_full_accounted")
    new_pack["classification"] = dict(CLASSIFICATION)
    new_pack["safety"] = {**(pack.get("safety") or {}), **SAFETY}
    new_pack["scoring_points_summary"] = stats
    return new_pack, stats


def _chunk_lookup(book_files: list[Path]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for path in book_files:
        payload = _read_json(path)
        for block in payload.get("content_blocks") or []:
            if isinstance(block, dict) and block.get("chunk_id"):
                lookup[str(block["chunk_id"])] = block
    return lookup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-pack", type=Path, default=DEFAULT_BASE_PACK)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--typed-policy", type=Path, default=DEFAULT_TYPED_POLICY)
    parser.add_argument("--book-file", dest="book_files", type=Path, action="append", default=None)
    parser.add_argument("--pack-version", default=PACK_VERSION)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_DIR / "scoring_point_compile_report.json")
    parser.add_argument(
        "--output-pack", type=Path, default=DEFAULT_OUTPUT_DIR / "runtime_token_pack_v32_scoring_points.json"
    )
    args = parser.parse_args(argv)

    golden = _read_json(args.golden)
    typed_rows = [json.loads(line) for line in args.typed_policy.read_text(encoding="utf-8").splitlines() if line.strip()]
    base_pack = _read_json(args.base_pack)
    chunk_lookup = _chunk_lookup(args.book_files or DEFAULT_BOOK_FILES)

    m35_by_chunk, m35_accounting = load_m35_scoring_points(golden, typed_rows)
    unmapped_chunks = sorted(
        chunk_id
        for chunk_id in m35_by_chunk
        if not any(
            str((u.get("source_ref") or {}).get("chunk_id") or "") == chunk_id
            for u in base_pack.get("runtime_token_pack_units") or []
        )
    )
    pack, stats = attach_scoring_points(
        base_pack, m35_by_chunk=m35_by_chunk, chunk_lookup=chunk_lookup, pack_version=args.pack_version
    )

    report = {
        "schema": SCHEMA,
        "verdict": "PASS_SCORING_POINT_COMPILE" if stats["points_total"] else "BLOCKED_NO_POINTS",
        "quality_claim_allowed": False,
        "base_pack": str(args.base_pack),
        "base_pack_version": base_pack.get("version"),
        "pack_version": args.pack_version,
        "m35_accounting": {**m35_accounting, "evidence_chunks_unmapped_to_units": unmapped_chunks},
        "summary": stats,
        "not_exercised": NOT_EXERCISED,
        "classification": dict(CLASSIFICATION),
        "safety": dict(SAFETY),
        "runtime_token_pack_path": str(args.output_pack),
    }
    _write_json(args.output_report, report)
    _write_json(args.output_pack, pack)
    print(
        json.dumps(
            {
                "output_report": str(args.output_report),
                "output_pack": str(args.output_pack),
                "verdict": report["verdict"],
                "m35_accounting": report["m35_accounting"],
                "summary": stats,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["verdict"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
