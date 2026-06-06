"""Objective governed release-candidate extractor (M26 Task 4, fat skill).

READ-ONLY extraction of objective answer keys from the GOVERNED ``questions_bank`` source, validated
and signed into a ``release_candidate`` bundle (one governance level above the M25-C
``real_source_candidate`` eval fixture). This is the only path that may mint a governed objective
answer-key release candidate.

Authority rules (hard, §0.26.3):
  * The governed source's ``official_answer`` is the ONLY scoring authority. No LLM, no RAG chunk,
    no model/council vote can change a key (``answer_key_override=0``, ``rag_chunk_as_answer_key=0``).
  * Live extraction connects to ``QUESTIONS_BANK_DB_URL`` in a READ-ONLY transaction. If the URL is
    absent it falls back to a tracked hermetic fixture and records a precise live blocker — it never
    fabricates a live result.
  * Status is ``release_candidate``, namespace ``objective_answer_key_governed`` (separate from the
    case registry and from the candidate namespaces). It is NOT ``published``.
  * Tampered / missing / malformed bundle fails CLOSED.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from deeptutor.services.construction_grading.normalization import normalize_options
from deeptutor.services.construction_grading.objective_answer_key_compiler import (
    _canonical,
    _normalize_answer_key,
    _sha,
)

_REPO = Path(__file__).resolve().parents[3]
_V2_DIR = (
    _REPO / "deeptutor" / "services" / "construction_grading"
    / "runtime_supply" / "v2_objective_release_candidate"
)
FIXTURE = _V2_DIR / "governed_questions_bank_fixture.json"

SCHEMA_VERSION = "luban_objective_answer_key.v2_release_candidate"
NAMESPACE = "objective_answer_key_governed"
STATUS = "release_candidate"
SOURCE_KIND_LIVE = "questions_bank_live_readonly"
SOURCE_KIND_FIXTURE = "questions_bank_hermetic_fixture"


def _option_keys(options: dict[str, str]) -> set[str]:
    return {str(k).strip().upper() for k in options.keys()}


def _validate_rows(questions: list[dict[str, Any]], source_kind: str, provenance: str) -> dict[str, list]:
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    seen_qid_options: dict[str, str] = {}
    seen_stem_key: dict[str, str] = {}

    for q in questions:
        qid = str(q.get("question_id") or q.get("id") or "").strip()
        qtype = str(q.get("question_type") or q.get("type") or "").strip()
        options = normalize_options(q.get("options"))
        raw_key = str(q.get("official_answer") or q.get("answer_key") or "").strip()
        stem = str(q.get("stem") or "").strip()
        origin = str(q.get("governed_origin") or "questions_bank").strip()

        if not qid or not raw_key or not options:
            rejected.append({"question_id": qid, "reason": "missing_id_key_or_options"})
            continue

        answer_key = _normalize_answer_key(qtype, raw_key)
        if not answer_key:
            rejected.append({"question_id": qid, "reason": "unnormalizable_answer_key", "raw_key": raw_key})
            continue
        # choice keys must be valid option letters
        if qtype in {"single_choice", "multiple_choice"}:
            if not set(answer_key).issubset(_option_keys(options)):
                rejected.append({"question_id": qid, "reason": "answer_not_in_options", "raw_key": raw_key})
                continue
            if qtype == "single_choice" and len(answer_key) != 1:
                rejected.append({"question_id": qid, "reason": "single_choice_multi_answer", "raw_key": raw_key})
                continue

        options_hash = _sha(_canonical(options))
        stem_hash = _sha(stem)
        if qid in seen_qid_options and seen_qid_options[qid] != options_hash:
            conflicts.append({"question_id": qid, "reason": "same_id_different_options"})
            continue
        if stem_hash in seen_stem_key and seen_stem_key[stem_hash] != answer_key:
            conflicts.append({"question_id": qid, "reason": "duplicate_stem_different_key"})
            continue
        seen_qid_options[qid] = options_hash
        seen_stem_key[stem_hash] = answer_key

        candidates.append({
            "question_id": qid,
            "question_type": qtype,
            "options": options,
            "option_metadata": options,
            "official_answer": raw_key,
            "answer_key": answer_key,
            "answer_key_hash": _sha(answer_key),
            "options_hash": options_hash,
            "stem_hash": stem_hash,
            "source_refs": [{"kind": "governed_questions_bank", "origin": origin, "source_kind": source_kind}],
            "governed_origin": origin,
            "answer_key_authority": "governed_source_official_answer_only",
            "provenance": provenance,
        })

    return {"candidates": candidates, "rejected": rejected, "conflicts": conflicts}


def _read_fixture() -> tuple[list[dict[str, Any]], str]:
    if not FIXTURE.exists():
        return [], ""
    payload = json.loads(FIXTURE.read_text("utf-8"))
    return list(payload.get("questions") or []), str(payload.get("provenance") or "")


def _read_live(db_url: str, *, querier: Callable[[str], list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    """Read-only governed extraction. ``querier`` is injectable for hermetic tests of the live path."""
    if querier is not None:
        return querier(db_url)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise _GovernedSourceUnavailable(f"psycopg2_unavailable:{exc}") from exc
    import psycopg2

    conn = None
    try:
        conn = psycopg2.connect(db_url, connect_timeout=20)
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        # Governed source projection. Column names are configurable for the live schema; the live
        # blocker (below) records that this exact projection must be confirmed against production.
        cur.execute(
            "select question_id, question_type, stem, options, official_answer "
            "from questions_bank where official_answer is not null"
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        return rows
    finally:
        if conn is not None:
            conn.close()


class _GovernedSourceUnavailable(Exception):
    pass


def governed_source_status(db_url: str | None = None) -> dict[str, Any]:
    """Report whether the live governed source is reachable; never writes, never fabricates."""
    url = db_url if db_url is not None else os.environ.get("QUESTIONS_BANK_DB_URL")
    if not url:
        return {
            "live_available": False,
            "source_kind": SOURCE_KIND_FIXTURE,
            "live_blocker": "QUESTIONS_BANK_DB_URL absent; cannot read governed questions_bank. "
            "Hermetic fixture used. Live blocker: set QUESTIONS_BANK_DB_URL (read-only role) and "
            "confirm the questions_bank column projection (question_id/question_type/stem/options/"
            "official_answer) against production before flipping to release_candidate from live.",
        }
    return {"live_available": True, "source_kind": SOURCE_KIND_LIVE, "live_blocker": ""}


def extract(
    *,
    db_url: str | None = None,
    querier: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Read-only governed extraction. Live when ``db_url``/env present, else hermetic fixture."""
    status = governed_source_status(db_url)
    if status["live_available"]:
        url = db_url if db_url is not None else os.environ["QUESTIONS_BANK_DB_URL"]
        try:
            rows = _read_live(url, querier=querier)
            source_kind = SOURCE_KIND_LIVE
            provenance = "governed_questions_bank_live_readonly"
        except _GovernedSourceUnavailable as exc:
            rows, provenance = _read_fixture()
            source_kind = SOURCE_KIND_FIXTURE
            status = {**status, "live_available": False, "source_kind": SOURCE_KIND_FIXTURE,
                      "live_blocker": f"live_read_failed:{exc}; fell back to hermetic fixture"}
    else:
        rows, provenance = _read_fixture()
        source_kind = SOURCE_KIND_FIXTURE

    validated = _validate_rows(rows, source_kind, provenance)
    return {**validated, "source_status": status, "source_kind": source_kind}


def build_release_candidate_bundle(
    *,
    db_url: str | None = None,
    querier: Callable[[str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build a signed governed ``release_candidate`` bundle. Tamper fails closed via verify_bundle."""
    extracted = extract(db_url=db_url, querier=querier)
    records = sorted(extracted["candidates"], key=lambda r: r["question_id"])
    content_hash = _sha(_canonical(records))
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": NAMESPACE,
        "status": STATUS,  # release_candidate, NOT published
        "release_authority": "governed_questions_bank",
        "published": False,
        "official_answer_role": "governed_source_authority",
        "count": len(records),
        "rejected_count": len(extracted["rejected"]),
        "conflict_count": len(extracted["conflicts"]),
        "content_hash": content_hash,
        "signature": _sha(content_hash + "|" + NAMESPACE + "|" + STATUS),
        "separate_from_case_registry": True,
        "separate_from_candidate_namespace": True,
        "source_kind": extracted["source_kind"],
        "source_status": extracted["source_status"],
        "answer_key_override": 0,
        "rag_chunk_as_answer_key": 0,
        "llm_changed_key": 0,
    }
    return {
        "manifest": manifest,
        "records": records,
        "rejected": extracted["rejected"],
        "conflicts": extracted["conflicts"],
    }


def verify_bundle(bundle: dict[str, Any]) -> bool:
    """Fail-closed: recompute content_hash over records AND signature over (hash|namespace|status)."""
    manifest = bundle.get("manifest") or {}
    records = bundle.get("records") or []
    recomputed = _sha(_canonical(records))
    if recomputed != manifest.get("content_hash"):
        return False
    expected_sig = _sha(recomputed + "|" + NAMESPACE + "|" + str(manifest.get("status")))
    return expected_sig == manifest.get("signature")


__all__ = [
    "extract",
    "build_release_candidate_bundle",
    "verify_bundle",
    "governed_source_status",
    "SCHEMA_VERSION",
    "NAMESPACE",
    "STATUS",
]
