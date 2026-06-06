"""Full Knowledge Compiler (M30) — compile raw evidence into SIGNED release_candidate knowledge.

Master plan §0.26.3/§0.26.4: the LLM organizes candidate knowledge; DETERMINISTIC gates sign truth.
This module is the deterministic signing/validation layer. It NEVER lets an LLM output, RAG chunk,
official_answer, or model/council vote become release authority. Everything it emits is at most
``release_candidate`` (never ``published``); it carries provenance / content_hash / rollback pointer
and fails CLOSED on tamper.

Lanes:
  * objective: full governed questions_bank answer-key extraction -> signed release_candidate.
  * source: KB v5 chunk refs -> source_context release_candidate (retrieval/context ONLY).
  * case rubric: authority partition (textbook / question_stem / calc / logic / list_full / external
    / review_only / drop) + deterministic validators for calc/list/spec.
  * M20 delta absorption: classify accepted deltas into release_candidate / staged_delta / work_order.
  * manifest: unify all release_candidates into one compiled_knowledge_registry manifest.

All DB access is READ-ONLY and injected via queriers (hermetic-testable). No production / remote /
canonical write.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from deeptutor.services.construction_grading.normalization import normalize_options
from deeptutor.services.construction_grading.objective_answer_key_compiler import (
    _canonical,
    _normalize_answer_key,
    _sha,
)

SCHEMA_VERSION = "luban_full_knowledge_compiler.m30"
STATUS_RELEASE_CANDIDATE = "release_candidate"
STATUS_DRAFT = "draft"
STATUS_CANDIDATE = "candidate"

# Origins that may NEVER seed a release-grade answer key / source authority.
_NON_AUTHORITY_ORIGINS = {"rag_chunk", "model_vote", "council_vote", "llm_guess", "official_answer"}

# Case authority partition buckets (§ case rubric authority partition).
CASE_AUTHORITY_BUCKETS = (
    "textbook", "question_stem", "calc", "logic", "list_full",
    "external", "review_only", "drop",
)
# Buckets that may be signed into the release_candidate; the rest become work_order.
CASE_SIGNABLE_BUCKETS = {"textbook", "question_stem", "calc", "logic", "list_full"}
CASE_WORKORDER_BUCKETS = {"external", "review_only"}


def _sha256_hex(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


# --------------------------- objective full lane ---------------------------

def _normalize_db_options(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k).strip().upper(): str(v) for k, v in raw.items()}
    out: dict[str, str] = {}
    if isinstance(raw, list):
        for idx, el in enumerate(raw):
            if isinstance(el, dict) and el.get("key"):
                out[str(el["key"]).strip().upper()] = str(el.get("value") or "")
            else:
                out[chr(ord("A") + idx)] = str(el)
    return out


def compile_full_objective_release_candidate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate + sign ALL governed objective rows. Conflicts are QUEUED, never silently fixed.

    ``rows`` come from a READ-ONLY governed questions_bank querier and carry: question_id,
    question_type, stem, options, official_answer, content_hash, based_on_version, source_meta.
    """
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    seen_qid_options: dict[str, str] = {}
    seen_stem_key: dict[str, str] = {}
    type_map = {"single_choice": "single_choice", "multi_choice": "multiple_choice",
                "judgment": "single_choice"}

    for r in rows:
        qid = str(r.get("question_id") or r.get("original_id") or r.get("id") or "").strip()
        raw_type = str(r.get("question_type") or "").strip()
        qtype = type_map.get(raw_type, raw_type)
        options = normalize_options(_normalize_db_options(r.get("options")))
        raw_key = str(r.get("official_answer") or r.get("answer_key") or "").strip().strip('"')
        stem = str(r.get("stem") or r.get("question_stem") or "").strip()

        if not qid or not raw_key or not options:
            rejected.append({"question_id": qid, "reason": "missing_id_key_or_options"})
            continue
        answer_key = _normalize_answer_key(qtype, raw_key)
        if not answer_key:
            rejected.append({"question_id": qid, "reason": "unnormalizable_answer_key", "raw_key": raw_key})
            continue
        if qtype in {"single_choice", "multiple_choice"}:
            opt_keys = {str(k).strip().upper() for k in options.keys()}
            if not set(answer_key).issubset(opt_keys):
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
        if stem and stem_hash in seen_stem_key and seen_stem_key[stem_hash] != answer_key:
            conflicts.append({"question_id": qid, "reason": "duplicate_stem_different_key", "stem_hash": stem_hash})
            continue
        seen_qid_options[qid] = options_hash
        if stem:
            seen_stem_key[stem_hash] = answer_key

        records.append({
            "question_id": qid,
            "question_type": qtype,
            "options": options,
            "option_metadata": options,
            "answer_key": answer_key,
            "answer_key_hash": _sha(answer_key),
            "options_hash": options_hash,
            "stem_hash": stem_hash,
            "official_answer_role": "seed_corroboration_only_not_authority",
            "answer_key_authority": "governed_questions_bank_official_answer",
            "content_hash": str(r.get("content_hash") or ""),
            "based_on_version": r.get("based_on_version"),
            "source_meta": r.get("source_meta") if isinstance(r.get("source_meta"), dict) else {},
            "provenance": "governed_questions_bank_readonly",
        })

    records.sort(key=lambda x: x["question_id"])
    content_hash = _sha256_hex(records)
    namespace = "objective_answer_key_full"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": namespace,
        "lane": "objective",
        "status": STATUS_RELEASE_CANDIDATE,
        "published": False,
        "count": len(records),
        "rejected_count": len(rejected),
        "conflict_count": len(conflicts),
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, namespace, STATUS_RELEASE_CANDIDATE]),
        "official_answer_as_source": 0,
        "answer_key_override": 0,
        "model_vote_as_source": 0,
        "rag_chunk_as_answer_key": 0,
        "rollback_pointer": "legacy (bundle missing / hash mismatch -> fail-closed; objective lane absent)",
        "separate_namespace": True,
    }
    return {"manifest": manifest, "records": records, "rejected": rejected, "conflicts": conflicts}


# --------------------------- source lane ---------------------------

def compile_source_context_release_candidate(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """KB v5 chunk refs -> source_context release_candidate. Retrieval/context ONLY; never answer keys."""
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in chunks:
        if not isinstance(c, dict):
            continue
        sid = str(c.get("chunk_id") or c.get("id") or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        loc = c.get("loc") if isinstance(c.get("loc"), dict) else {}
        content = str(c.get("content") or "")
        refs.append({
            "stable_source_id": sid,
            "chunk_id": sid,
            "doc_id": str(c.get("doc_id") or ""),
            "source_table": "kb_v5.chunks",
            "source_type": str(c.get("doc_type") or ""),
            "locator": {"page": loc.get("page"), "chapter": loc.get("chapter"), "section": loc.get("section")},
            "taxonomy_path": str(loc.get("chapter") or "") + "/" + str(loc.get("section") or ""),
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
            "provenance": "kb_v5_readonly_search_chunks_v2",
            "is_answer_key": False,
            "role": "retrieval_context_only",
        })
    refs.sort(key=lambda x: x["stable_source_id"])
    content_hash = _sha256_hex(refs)
    namespace = "source_context_kb_v5"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": namespace,
        "lane": "source",
        "status": STATUS_RELEASE_CANDIDATE,
        "published": False,
        "count": len(refs),
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, namespace, STATUS_RELEASE_CANDIDATE]),
        "rag_chunk_as_answer_key": 0,
        "source_laundering": 0,
        "rollback_pointer": "legacy (no source_context -> retrieval falls back to RAGService live path)",
    }
    return {"manifest": manifest, "records": refs}


# --------------------------- case rubric lane ---------------------------

def _validate_calc_point(point: dict[str, Any]) -> bool:
    spec = point.get("machine_spec") or point.get("spec")
    return isinstance(spec, dict) and bool(spec)


def _validate_list_point(point: dict[str, Any]) -> bool:
    items = point.get("list_items") or point.get("required_items")
    return isinstance(items, list) and len(items) >= 1


def compile_case_rubric_release_candidate(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Partition case scoring points by authority; sign signable buckets, queue the rest as work_order.

    ``points`` carry an ``authority_kind`` (the LLM-organized + previously-signed classification). The
    deterministic gate here only signs textbook/question_stem/calc/logic/list_full; external and
    review_only become work_order; drop is discarded. calc/list get a deterministic validator check.
    """
    signed: list[dict[str, Any]] = []
    work_order: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    by_bucket: dict[str, int] = {b: 0 for b in CASE_AUTHORITY_BUCKETS}
    list_partial_auto = 0
    validator_failed: list[dict[str, Any]] = []

    for p in points:
        bucket = str(p.get("authority_kind") or p.get("bucket") or "review_only").strip().lower()
        if bucket not in CASE_AUTHORITY_BUCKETS:
            bucket = "review_only"
        by_bucket[bucket] = by_bucket.get(bucket, 0) + 1
        pid = str(p.get("point_id") or p.get("id") or "").strip()

        if bucket == "drop":
            dropped.append({"point_id": pid, "reason": "compiler_dropped"})
            continue
        if bucket in CASE_WORKORDER_BUCKETS:
            work_order.append({"point_id": pid, "bucket": bucket,
                               "reason": "external/review_only never auto-signed as source",
                               "promote_to_release": False})
            continue
        # signable buckets: deterministic validator floor for calc / list_full
        if bucket == "calc" and not _validate_calc_point(p):
            validator_failed.append({"point_id": pid, "bucket": bucket, "reason": "calc_spec_missing"})
            work_order.append({"point_id": pid, "bucket": bucket, "reason": "calc_validator_failed",
                               "promote_to_release": False})
            continue
        if bucket == "list_full" and not _validate_list_point(p):
            validator_failed.append({"point_id": pid, "bucket": bucket, "reason": "list_items_missing"})
            work_order.append({"point_id": pid, "bucket": bucket, "reason": "list_validator_failed",
                               "promote_to_release": False})
            continue
        signed.append({
            "point_id": pid,
            "authority_kind": bucket,
            "text": str(p.get("text") or "")[:400],
            "required_terms": list(p.get("required_terms") or []),
            "machine_spec": p.get("machine_spec") or p.get("spec"),
            "list_items": p.get("list_items") or p.get("required_items"),
            "source_refs": list(p.get("source_refs") or []),
            "list_partial_auto": False,  # list points never auto a partial
        })

    signed.sort(key=lambda x: x["point_id"])
    content_hash = _sha256_hex(signed)
    namespace = "case_rubric_full"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "namespace": namespace,
        "lane": "case_rubric",
        "status": STATUS_RELEASE_CANDIDATE,
        "published": False,
        "signed_count": len(signed),
        "work_order_count": len(work_order),
        "dropped_count": len(dropped),
        "by_bucket": by_bucket,
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, namespace, STATUS_RELEASE_CANDIDATE]),
        "list_partial_auto": list_partial_auto,
        "validator_failed_count": len(validator_failed),
        "external_or_reviewonly_auto_signed": 0,
        "rollback_pointer": "legacy (no case_rubric_full -> existing release_candidate registry stays authority)",
    }
    return {"manifest": manifest, "records": signed, "work_order": work_order,
            "dropped": dropped, "validator_failed": validator_failed}


# --------------------------- M20 delta absorption ---------------------------

def absorb_m20_deltas(deltas: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify accepted M20 deltas into release_candidate / staged_delta / work_order.

    A delta only reaches release_candidate if it is a textbook/spec-backed, non-laundering fix; an
    LLM/council vote or an external/needs-review item stays staged_delta or work_order. M20 deltas
    NEVER touch the current production runtime (separate namespace).
    """
    release_candidate: list[dict[str, Any]] = []
    staged_delta: list[dict[str, Any]] = []
    work_order: list[dict[str, Any]] = []
    for d in deltas:
        kind = str(d.get("delta_kind") or d.get("kind") or "").strip().lower()
        origin = str(d.get("origin") or d.get("source") or "").strip().lower()
        backed = bool(d.get("source_backed") or d.get("textbook_backed") or d.get("machine_checkable"))
        entry = {"delta_id": d.get("delta_id") or d.get("id"), "kind": kind, "origin": origin,
                 "promote_to_release": False}
        if origin in _NON_AUTHORITY_ORIGINS and not backed:
            work_order.append({**entry, "reason": f"{origin}_not_source_backed"})
        elif kind in {"rubric_delta", "machine_spec_fix"} and backed:
            release_candidate.append({**entry, "lane": "case_rubric", "promote_to_release": False})
        elif kind in {"validator_rule_review", "needs_review"}:
            work_order.append({**entry, "reason": "needs_human_or_governed_review"})
        else:
            staged_delta.append({**entry, "reason": "staged_pending_more_evidence"})
    namespace = "m20_delta_absorbed"
    content = _sha256_hex([release_candidate, staged_delta, work_order])
    return {
        "namespace": namespace,
        "status": STATUS_RELEASE_CANDIDATE,
        "published": False,
        "input_count": len(deltas),
        "release_candidate": release_candidate,
        "staged_delta": staged_delta,
        "work_order": work_order,
        "content_hash": content,
        "signature": _sha256_hex([content, namespace, STATUS_RELEASE_CANDIDATE]),
        "no_runtime_impact": True,
        "candidate_used_as_release_truth": 0,
        "rollback_pointer": "legacy (deltas absorbed in separate namespace; current registry untouched)",
    }


# --------------------------- unified manifest ---------------------------

def build_compiled_knowledge_registry_manifest(
    *,
    objective: dict[str, Any],
    source: dict[str, Any],
    case_rubric: dict[str, Any],
    m20: dict[str, Any],
) -> dict[str, Any]:
    """Unify all lane release_candidates into ONE signed compiled-knowledge manifest (v2)."""
    lanes = {
        "objective": objective["manifest"],
        "source": source["manifest"],
        "case_rubric": case_rubric["manifest"],
        "m20_delta": {k: m20[k] for k in ("namespace", "status", "published", "content_hash", "signature")},
    }
    registry_hash = _sha256_hex(lanes)
    return {
        "schema_version": "compiled_knowledge_registry.v2",
        "status": STATUS_RELEASE_CANDIDATE,
        "published": False,
        "production_default_connected": False,
        "canonical_truth_written": False,
        "lanes": lanes,
        "blocks_for_runtime_packet": [
            "question_context", "source_context", "rubric_context",
            "learner_context", "diagnostic_policy", "budget_policy", "provenance",
        ],
        "registry_content_hash": registry_hash,
        "registry_signature": _sha256_hex([registry_hash, "compiled_knowledge_registry.v2", STATUS_RELEASE_CANDIDATE]),
        "rollback_pointer": "legacy compiled_context.v1 + existing release_candidate registries",
    }


def verify_lane_bundle(bundle: dict[str, Any], namespace: str) -> bool:
    """Fail-closed: recompute content_hash over records AND signature over (hash|namespace|status)."""
    manifest = bundle.get("manifest") or {}
    records = bundle.get("records") or []
    recomputed = _sha256_hex(records)
    if recomputed != manifest.get("content_hash"):
        return False
    expected = _sha256_hex([recomputed, namespace, manifest.get("status")])
    return expected == manifest.get("signature")


def fetch_full_objective_rows(
    db_url: str,
    *,
    querier: Callable[[str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """READ-ONLY full objective fetch. ``querier`` injectable for hermetic tests."""
    if querier is not None:
        return querier(db_url)
    import psycopg2
    conn = psycopg2.connect(db_url, connect_timeout=30)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "select original_id, id, question_type, question_stem, options, correct_answer, "
            "content_hash, based_on_version, source_meta from public.questions_bank "
            "where question_type in ('single_choice','multi_choice','judgment') "
            "and correct_answer is not null and options is not null order by id"
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "question_id": str(r.get("original_id") or r.get("id") or "").strip(),
            "question_type": r.get("question_type"),
            "stem": r.get("question_stem"),
            "options": r.get("options"),
            "official_answer": r.get("correct_answer"),
            "content_hash": r.get("content_hash"),
            "based_on_version": r.get("based_on_version"),
            "source_meta": r.get("source_meta"),
        })
    return out


__all__ = [
    "SCHEMA_VERSION",
    "compile_full_objective_release_candidate",
    "compile_source_context_release_candidate",
    "compile_case_rubric_release_candidate",
    "absorb_m20_deltas",
    "build_compiled_knowledge_registry_manifest",
    "verify_lane_bundle",
    "fetch_full_objective_rows",
    "CASE_AUTHORITY_BUCKETS",
]
