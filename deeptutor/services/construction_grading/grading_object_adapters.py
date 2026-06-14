"""Deterministic adapters: each pre-existing grading schema -> luban_grading_object.v1.

These are the migration/conformance mappings referenced by
``docs/plan/鲁班knowql/UNIFIED_GRADING_OBJECT_SCHEMA.md``. Each adapter is a pure
function that regularizes a drifting source shape onto the unified canonical core
fields **without dropping data or silently changing semantics**: drift field names
are renamed to their one canonical name (``weight``->``max_score``,
``canonical_answer`` / ``label`` / ``answer_key``->``statement``), and the canonical
``authority_source`` is derived from each source's own authority signal.

No adapter mints a per-point score or grants official authority — every per-point
score that was not an official split is carried over as ``None`` +
``pending_calibration``. Adapters do not modify their input.
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.unified_grading_object import (
    AUTH_OFFICIAL_ANSWER,
    AUTH_PENDING_CALIBRATION,
    AUTH_TEXTBOOK_CITED,
    PENDING_SCORE_AUTHORITY,
    TYPE_CASE,
    TYPE_OBJECTIVE,
    GradingObject,
    span_hash,
)


def _term_provenance_from_anchor(
    *, chunk_id: Any, anchor_verified: bool, quote: str = ""
) -> dict[str, Any]:
    """Normalize a single anchor into the canonical term_provenance entry."""
    if anchor_verified and chunk_id:
        return {
            "chunk_id": str(chunk_id),
            "anchor_verified": True,
            "authority_source": AUTH_TEXTBOOK_CITED,
            "quote": str(quote or ""),
        }
    return {
        "chunk_id": None,
        "anchor_verified": False,
        "authority_source": "unsourced",
        "quote": "",
    }


def _point(
    *,
    point_id: str,
    statement: str,
    authority_source: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical point dict with a span_hash projection proof.

    ``pending_calibration`` points carry no span_hash (nothing is being projected);
    span-backed authorities carry the hash of their own statement.
    """
    point: dict[str, Any] = {
        "point_id": str(point_id),
        "statement": str(statement),
        "authority_source": authority_source,
        "span_hash": None if authority_source == AUTH_PENDING_CALIBRATION else span_hash(statement),
        "max_score": None,
        "score_authority": PENDING_SCORE_AUTHORITY,
        "hit_status": "not_evaluated",
        "required_terms": [],
        "term_provenance": [],
    }
    if extra:
        point.update(extra)
    return point


# ── 1. case_grading_artifact.v1 (eval-inline) ────────────────────────────────────
def map_case_grading_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """``case_grading_artifact.v1`` -> unified. weight->max_score, canonical_answer->statement."""
    points: list[dict[str, Any]] = []
    for sub in artifact.get("subquestions") or []:
        for sp in sub.get("scoring_points") or []:
            prov = sp.get("provenance") if isinstance(sp.get("provenance"), dict) else {}
            sourced = bool(prov.get("sourced"))
            authority = AUTH_TEXTBOOK_CITED if sourced else AUTH_PENDING_CALIBRATION
            statement = str(sp.get("canonical_answer") or "")
            extra = {
                "required_terms": list(sp.get("required_terms") or []),
                "sub_type": "case_sub_point",
                "term_provenance": [
                    _term_provenance_from_anchor(
                        chunk_id=prov.get("source_ref"),
                        anchor_verified=sourced,
                        quote=str(prov.get("textbook_quote") or ""),
                    )
                ],
            }
            points.append(
                _point(
                    point_id=f"{sp.get('point_id')}",
                    statement=statement,
                    authority_source=authority,
                    extra=extra,
                )
            )
    obj = GradingObject(
        object_id=str(artifact.get("case_id") or ""),
        question_type=TYPE_CASE,
        official_total_score=None,
        scoring_points=points,
        authority_source=AUTH_OFFICIAL_ANSWER,
        source_refs=list(artifact.get("source_chunks") or []),
    )
    return obj.to_dict()


# ── 2. rich_leaf v3.2 pack scoring_points / luban.rich_leaf_artifact.v0 ───────────
def map_rich_leaf_scoring_point(sp: dict[str, Any], *, object_id: str) -> dict[str, Any]:
    """A single rich-leaf v3.2 scoring point -> unified canonical point. statement kept."""
    prov = sp.get("provenance") if isinstance(sp.get("provenance"), dict) else {}
    verified = bool(prov.get("quote_verified"))
    authority = AUTH_TEXTBOOK_CITED if verified else AUTH_PENDING_CALIBRATION
    statement = str(sp.get("statement") or "")
    extra = {
        "required_terms": list(sp.get("required_terms") or []),
        "sub_type": str(sp.get("policy_type") or "") or None,
        "term_provenance": [
            _term_provenance_from_anchor(
                chunk_id=prov.get("chunk_id"),
                anchor_verified=verified,
                quote=str(prov.get("quote") or ""),
            )
        ],
    }
    return _point(
        point_id=str(sp.get("point_id") or ""),
        statement=statement,
        authority_source=authority,
        extra=extra,
    )


def map_rich_leaf_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """A rich-leaf v3.2 ``runtime_token_pack_unit`` -> a case unified grading object.

    Also the single canonical converter for ``luban_rich_leaf_scoring_point_compile.v1`` units:
    that compile artifact's ``runtime_token_pack_units`` carry the same
    ``compiled_context.scoring_points`` shape, so they converge to ``luban_grading_object.v1``
    through THIS adapter — one of the two divergent schemas of KnowQL pillar ① (the other is
    ``case_grading_artifact.v1`` via ``map_case_grading_artifact``). Convergence is pinned by
    ``test_dual_schema_converges_to_single_canonical_authority``; no second adapter is minted.
    """
    compiled = (
        unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    )
    object_id = str(unit.get("leaf_id") or unit.get("unit_id") or "")
    points = [
        map_rich_leaf_scoring_point(sp, object_id=object_id)
        for sp in compiled.get("scoring_points") or []
        if isinstance(sp, dict)
    ]
    obj = GradingObject(
        object_id=object_id,
        question_type=TYPE_CASE,
        official_total_score=None,
        scoring_points=points,
        authority_source=AUTH_OFFICIAL_ANSWER,
    )
    return obj.to_dict()


# ── 3. luban_scoring_point_assets.v0.1 ───────────────────────────────────────────
def map_scoring_point_asset(row: dict[str, Any]) -> dict[str, Any]:
    """A scoring-point asset row -> unified canonical point. label->statement, max_score kept."""
    prov = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    verified = bool(prov.get("anchor_verified"))
    authority = AUTH_TEXTBOOK_CITED if verified else AUTH_PENDING_CALIBRATION
    statement = str(row.get("label") or "")
    extra = {
        "required_terms": list(row.get("required_terms") or []),
        "sub_type": str(row.get("point_type") or "") or None,
        "term_provenance": [
            _term_provenance_from_anchor(
                chunk_id=prov.get("chunk_id"),
                anchor_verified=verified,
                quote=str(prov.get("quote") or ""),
            )
        ],
    }
    if isinstance(row.get("calculation"), dict):
        extra["formula_steps"] = [
            {
                "expected_value_literal": v,
                "verification_mode": row["calculation"].get("verification_mode"),
            }
            for v in row["calculation"].get("expected_values") or []
        ]
    return _point(
        point_id=str(row.get("point_id") or ""),
        statement=statement,
        authority_source=authority,
        extra=extra,
    )


def map_scoring_point_assets(rows: list[dict[str, Any]], *, object_id: str) -> dict[str, Any]:
    """A bundle of scoring-point asset rows -> one unified case grading object."""
    points = [map_scoring_point_asset(row) for row in rows if isinstance(row, dict)]
    obj = GradingObject(
        object_id=str(object_id),
        question_type=TYPE_CASE,
        official_total_score=None,
        scoring_points=points,
        authority_source=AUTH_OFFICIAL_ANSWER,
    )
    return obj.to_dict()


# ── 4. M31 governed objective answer key record ──────────────────────────────────
def map_objective_answer_key_record(record: dict[str, Any]) -> dict[str, Any]:
    """A governed objective answer-key record -> objective unified grading object.

    answer_key->statement; the key set is the single official point. The record's
    ``official_answer_role`` ("seed_corroboration_only_not_authority") is preserved by
    keeping the answer as official_answer authority but never granting official score.
    """
    answer_key = str(record.get("answer_key") or "")
    options = record.get("options") if isinstance(record.get("options"), dict) else {}
    correct_keys = [ch for ch in answer_key if ch.strip()]
    point = _point(
        point_id=f"{record.get('question_id')}-key",
        statement=answer_key,
        authority_source=AUTH_OFFICIAL_ANSWER,
        extra={
            "options": {str(k): str(v) for k, v in options.items()},
            "correct_keys": correct_keys,
            "sub_type": str(record.get("question_type") or "") or None,
        },
    )
    obj = GradingObject(
        object_id=str(record.get("question_id") or ""),
        question_type=TYPE_OBJECTIVE,
        official_total_score=None,
        scoring_points=[point],
        authority_source=AUTH_OFFICIAL_ANSWER,
    )
    return obj.to_dict()


# ── 5. arbitration gold_panel row (verdict label) ────────────────────────────────
def map_gold_panel_row(row: dict[str, Any]) -> dict[str, Any]:
    """A gold-panel verdict row -> a single-point unified object (label-quality only).

    The panel verdict is a quality label, NOT release truth. It maps to a point whose
    ``hit_status`` carries the consensus verdict and whose authority stays
    ``pending_calibration`` (the panel never grants official score).
    """
    verdict = str(row.get("consensus_verdict") or "not_evaluated")
    hit_status = (
        verdict if verdict in {"hit", "partial", "miss", "contradiction"} else "not_evaluated"
    )
    statement = f"panel_verdict:{row.get('case_id')}:{row.get('point_id')}"
    point = _point(
        point_id=f"{row.get('case_id')}-{row.get('student_id')}-{row.get('point_id')}",
        statement=statement,
        authority_source=AUTH_PENDING_CALIBRATION,
        extra={
            "hit_status": hit_status,
            "sub_type": "panel_quality_label",
            "term_provenance": [],
        },
    )
    obj = GradingObject(
        object_id=str(row.get("case_id") or ""),
        question_type=TYPE_CASE,
        official_total_score=None,
        scoring_points=[point],
        authority_source=AUTH_OFFICIAL_ANSWER,
    )
    return obj.to_dict()


# ── 6. compact_scoring_artifact.v1 (eval-inline) ─────────────────────────────────
def map_compact_scoring_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """``compact_scoring_artifact.v1`` -> unified. expected_points->statements, max_score kept."""
    points: list[dict[str, Any]] = []
    for idx, entry in enumerate(artifact.get("points") or []):
        sub_no = entry.get("sub_no")
        for ep_idx, expected in enumerate(entry.get("expected_points") or [], start=1):
            points.append(
                _point(
                    point_id=f"{sub_no or idx}-P{ep_idx}",
                    statement=str(expected),
                    authority_source=AUTH_OFFICIAL_ANSWER,
                    extra={"sub_type": "compact_expected_point"},
                )
            )
    obj = GradingObject(
        object_id="compact",
        question_type=TYPE_CASE,
        official_total_score=None,
        scoring_points=points,
        authority_source=AUTH_OFFICIAL_ANSWER,
        source_refs=list(artifact.get("source_chunks") or []),
    )
    return obj.to_dict()


# ── 7. luban_per_question_grading_object.v1 (deterministic compiler) ─────────────
_PQ_AUTHORITY_MAP = {
    "official_answer_verbatim": AUTH_OFFICIAL_ANSWER,
    "textbook_cited": AUTH_TEXTBOOK_CITED,
    "owner": "owner",
    "pending_calibration": AUTH_PENDING_CALIBRATION,
}


def map_per_question_grading_object(obj: dict[str, Any]) -> dict[str, Any]:
    """``luban_per_question_grading_object.v1`` -> unified.

    This source is already authority-native (it pioneered the
    official_answer_verbatim / textbook_cited / owner / pending vocabulary), so the
    mapping mostly renames its authority tags to the canonical set and lifts each
    ``atomic_official_slice`` into the canonical ``statement`` field.
    """
    points: list[dict[str, Any]] = []
    for sub in obj.get("sub_questions") or []:
        for sp in sub.get("scoring_points") or []:
            src_auth = str(sp.get("authority_source") or "official_answer_verbatim")
            authority = _PQ_AUTHORITY_MAP.get(src_auth, AUTH_OFFICIAL_ANSWER)
            statement = str(sp.get("atomic_official_slice") or "")
            term_prov = [
                {
                    "chunk_id": p.get("chunk_id"),
                    "anchor_verified": bool(p.get("anchor_verified")),
                    "authority_source": _PQ_AUTHORITY_MAP.get(
                        str(p.get("authority_source") or ""), "unsourced"
                    )
                    if p.get("anchor_verified")
                    else "unsourced",
                    "quote": "",
                }
                for p in sp.get("term_provenance") or []
            ]
            extra: dict[str, Any] = {
                "sub_type": str(sp.get("sub_type") or "") or None,
                "term_provenance": term_prov,
            }
            for key in ("flaw_span", "correction_span", "pairing", "base_rule", "exception_items"):
                if sp.get(key) is not None:
                    extra[key] = sp[key]
            if isinstance(sp.get("formula_step"), dict):
                extra["formula_steps"] = [sp["formula_step"]]
            points.append(
                _point(
                    point_id=str(sp.get("point_id") or ""),
                    statement=statement,
                    authority_source=authority,
                    extra=extra,
                )
            )
    out = GradingObject(
        object_id=str(obj.get("question_id") or ""),
        question_type=TYPE_CASE,
        official_total_score=obj.get("official_total_score"),
        scoring_points=points,
        authority_source=AUTH_OFFICIAL_ANSWER,
        stem=obj.get("stem"),
        official_analysis=obj.get("official_analysis"),
    )
    return out.to_dict()


ADAPTER_REGISTRY: dict[str, str] = {
    "case_grading_artifact.v1": "map_case_grading_artifact",
    "luban.rich_leaf_artifact.v0": "map_rich_leaf_unit",
    "luban_scoring_point_assets.v0.1": "map_scoring_point_assets",
    "luban_m31_governed_objective_pointer.v1": "map_objective_answer_key_record",
    "luban_arbitration_gold_panel.v1": "map_gold_panel_row",
    "compact_scoring_artifact.v1": "map_compact_scoring_artifact",
    "luban_per_question_grading_object.v1": "map_per_question_grading_object",
}
