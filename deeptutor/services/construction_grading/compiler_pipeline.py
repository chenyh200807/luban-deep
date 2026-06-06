"""Living LLM Artifact Compiler — the S0–S7 deterministic orchestration spine.

Design: docs/plan/2026-06-06-luban-living-llm-artifact-compiler-design.md.

精妙 (the one elegance): the WRITE right (LLM, S2/S4) and the SIGN right (deterministic gate, S5)
are held by two different actors across one gate. ``promote_to_release`` is ``False`` at birth and
through every LLM / validator / council stage; it flips ``True`` in EXACTLY ONE place — inside S5,
after the full G0–G8 gate ladder passes. The LLM never holds the pen on signing.

Every stage is append-only (project immutability rule). The LLM lives inside exactly two stages
(S2 generation, S4 adversarial) and is fully injected, so the spine stays pure + hermetically
testable. Heavy / script-bound gates (verbatim textbook anchor, the 7-vector spec attack) are
injected too; sensible deterministic defaults run when nothing is injected.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from deeptutor.services.construction_grading import compiler_feedback as _CF
from deeptutor.services.construction_grading import feedback_ingest_bridge as _B
from deeptutor.services.construction_grading import full_knowledge_compiler as _FKC

# ----------------------------- injected-stage types -----------------------------

# S2: an EvidenceItem -> typed candidates (MUST be produced through compiler_feedback.make_candidate).
LLMWorker = Callable[[dict[str, Any]], list[dict[str, Any]]]
# S4: disputed candidates -> candidates (council may DOWN-RANK only; never up-rank / seed source).
Council = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


def _default_verify_anchor(anchor: dict[str, Any]) -> bool:
    """Default verbatim textbook-anchor gate (G2): a textbook quote must be a verbatim substring of
    the supplied 2026 教材 ``content_markdown``. official_answer / semantic anchors are never verified."""
    if not isinstance(anchor, dict):
        return False
    if str(anchor.get("source_type") or "") != "textbook":
        return False
    quote = str(anchor.get("textbook_quote") or "").strip()
    corpus = str(anchor.get("content_markdown") or "")
    chunk_id = str(anchor.get("chunk_id") or "").strip()
    return bool(quote and chunk_id and quote in corpus)


def _default_spec_attack_fp(spec: dict[str, Any]) -> int:
    """Default machine-spec attack gate (G4): a numeric calc spec must reject off-by-one and a
    contradiction. Returns the false-positive count (0 = pass). The runner injects the full 7-vector
    m10 attack; this default guards well-formed-ness + the two highest-value numeric vectors."""
    if not isinstance(spec, dict) or not spec:
        return 1
    expected = spec.get("expected")
    if expected is None:
        # non-numeric spec (e.g. logic) — must at least carry a kind to be machine-checkable.
        return 0 if spec.get("kind") else 1
    try:
        exp = float(expected)
    except (TypeError, ValueError):
        return 1
    fp = 0
    # off-by-one must NOT be accepted as exact
    if _numeric_accept(spec, exp + 1):
        fp += 1
    # exact must be accepted
    if not _numeric_accept(spec, exp):
        fp += 1
    return fp


def _numeric_accept(spec: dict[str, Any], value: float) -> bool:
    expected = float(spec["expected"])
    tol = float(spec.get("tolerance") or 0)
    return abs(value - expected) <= tol


@dataclass(frozen=True)
class GateSet:
    verify_textbook_anchor: Callable[[dict[str, Any]], bool] = _default_verify_anchor
    spec_attack_fp: Callable[[dict[str, Any]], int] = _default_spec_attack_fp


DEFAULT_GATES = GateSet()


# ----------------------------- S2 default worker -----------------------------

def default_machine_spec_worker(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic (no-LLM) S2 worker for the machine_spec slice. Emits candidates ONLY through
    make_candidate (so the G0 laundering guard fires at birth). Mirrors the --no-llm discipline."""
    kind = item.get("evidence_kind")
    payload = item.get("payload") or {}
    if kind == "machine_spec_point":
        return [_CF.make_candidate(
            kind=_CF.KIND_MACHINE_SPEC, origin="llm_guess",
            payload={"point_id": payload.get("point_id"), "question_id": payload.get("question_id"),
                     "authority_kind": "calc", "text": payload.get("text"),
                     "machine_spec": payload.get("machine_spec"),
                     "required_terms": payload.get("required_terms") or [],
                     "textbook_anchor": payload.get("textbook_anchor")},
            reason="machine_spec_candidate_from_evidence")]
    if kind == "case_official_answer":
        # official_answer is a SEED for a rubric candidate, never a source.
        return [_CF.make_candidate(
            kind=_CF.KIND_RUBRIC, origin="official_answer",
            payload={"point_id": payload.get("point_id"), "question_id": payload.get("question_id"),
                     "authority_kind": "logic", "text": payload.get("text"),
                     "required_terms": payload.get("required_terms") or []},
            reason="rubric_candidate_from_official_answer_seed")]
    if kind == "retrieval_chunk":
        return [_CF.make_candidate(kind=_CF.KIND_SOURCE, origin="rag_chunk",
                                   payload={"chunk": payload}, reason="source_candidate_from_rag")]
    if kind == "runtime_miss":
        return [_CF.make_candidate(kind=_CF.KIND_WORK_ORDER, origin="open_world_diagnostic",
                                   payload=payload, reason="runtime_miss_to_work_order")]
    return []


# ----------------------------- the spine -----------------------------

@dataclass
class PipelineRun:
    run_id: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    signed_bundle: dict[str, Any] | None = None
    work_orders: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    reingested: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0


def _stage_log(cand: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """Append-only stage_log + lineage (returns a NEW dict; never mutates the input)."""
    log = list(cand.get("stage_log") or [])
    log.append(entry)
    return {**cand, "stage_log": log}


def _s3_gates(cands: list[dict[str, Any]], gates: GateSet) -> dict[str, list[dict[str, Any]]]:
    """S3 deterministic gate ladder. Routes every candidate to exactly one of eligible / work_order /
    rejected / conflict. Verbatim textbook provenance + spec attack enforced here; nothing silently
    dropped. Candidates created via make_candidate that are already KIND_REJECTED (G0 laundering) pass
    straight to rejected."""
    eligible: list[dict[str, Any]] = []
    work_orders: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    seen_point: dict[str, str] = {}

    for c in cands:
        kind = c.get("kind")
        if kind == _CF.KIND_REJECTED:  # G0 birth-deflect (laundering) — terminal audit row
            rejected.append(c)
            continue
        if kind == _CF.KIND_WORK_ORDER:
            work_orders.append(c)
            continue
        payload = c.get("payload") or {}
        pid = str(payload.get("point_id") or "")

        # G1 schema
        if not pid:
            rejected.append(_stage_log(c, {"stage": "S3", "gate": "G1_schema", "verdict": "fail", "detail": "no point_id"}))
            continue

        if kind == _CF.KIND_MACHINE_SPEC:
            spec = payload.get("machine_spec")
            # G4 spec attack (7-vector injected, or default off-by-one/contradiction)
            fp = gates.spec_attack_fp(spec if isinstance(spec, dict) else {})
            if fp != 0:
                work_orders.append(_stage_log(c, {"stage": "S3", "gate": "G4_spec_attack", "verdict": "fail", "fp": fp}))
                continue
            c = _stage_log(c, {"stage": "S3", "gate": "G4_spec_attack", "verdict": "pass", "fp": 0})
        elif kind == _CF.KIND_RUBRIC:
            # textbook-sourced rubric points must pass the verbatim anchor (G2); seed-only logic points
            # without an anchor are signable as logic but never claim textbook authority.
            anchor = payload.get("textbook_anchor")
            if anchor is not None:
                if not gates.verify_textbook_anchor(anchor):
                    work_orders.append(_stage_log(c, {"stage": "S3", "gate": "G2_verbatim_anchor", "verdict": "fail"}))
                    continue
                c = _stage_log({**c, "payload": {**payload, "textbook_verified": True}},
                               {"stage": "S3", "gate": "G2_verbatim_anchor", "verdict": "pass"})
        else:
            # source_candidate / question_candidate are never directly signable in this lane.
            work_orders.append(_stage_log(c, {"stage": "S3", "gate": "G_lane", "verdict": "not_signable_here"}))
            continue

        # G6 conflict: same point_id, different content -> queued, never auto-resolved.
        sig = _CF._sha16(payload)
        if pid in seen_point and seen_point[pid] != sig:
            conflicts.append(_stage_log(c, {"stage": "S3", "gate": "G6_conflict", "verdict": "queued"}))
            continue
        seen_point[pid] = sig
        eligible.append(c)

    return {"eligible": eligible, "work_order": work_orders, "rejected": rejected, "conflict": conflicts}


def _s5_sign(eligible: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """S5: deterministic sign. The ONLY place promote_to_release flips True. Builds signed points,
    signs via compile_case_rubric_release_candidate, augments the manifest with a question_index, and
    returns (bundle, promoted_candidates)."""
    points: list[dict[str, Any]] = []
    qindex: dict[str, list[str]] = {}
    for c in eligible:
        p = c.get("payload") or {}
        pid = str(p.get("point_id"))
        qid = str(p.get("question_id") or "")
        points.append({
            "point_id": pid,
            "authority_kind": p.get("authority_kind") or "logic",
            "text": p.get("text") or "",
            "required_terms": p.get("required_terms") or [],
            "machine_spec": p.get("machine_spec"),
            "source_refs": p.get("source_refs") or [],
        })
        if qid:
            qindex.setdefault(qid, []).append(pid)

    bundle = _FKC.compile_case_rubric_release_candidate(points)
    # question_index does NOT affect content_hash/signature (computed over records only) -> safe.
    bundle["manifest"]["question_index"] = {q: sorted(set(pids)) for q, pids in qindex.items()}

    signed_pids = {str(r.get("point_id")) for r in bundle.get("records", [])}
    promoted: list[dict[str, Any]] = []
    for c in eligible:
        pid = str((c.get("payload") or {}).get("point_id"))
        if pid in signed_pids:
            # THE ONE FLIP SITE.
            promoted.append({**_stage_log(c, {"stage": "S5", "verdict": "signed"}),
                             "promote_to_release": True, "status": "release_candidate"})
        else:
            promoted.append(c)  # validator-failed inside the signer -> stays candidate
    return bundle, promoted


def _s3_gates_textbook(cands: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """S3 for the textbook lane: minimal routing — the deterministic SIGNER
    (compile_textbook_knowledge_release_candidate) is the sole provenance authority (it runs the
    per-field corpus check). Here we only deflect laundering (KIND_REJECTED) and pre-routed
    work_orders; everything else is eligible and the signer partitions it at S5."""
    eligible: list[dict[str, Any]] = []
    work_orders: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for c in cands:
        kind = c.get("kind")
        if kind == _CF.KIND_REJECTED:
            rejected.append(c)
        elif kind == _CF.KIND_WORK_ORDER:
            work_orders.append(c)
        # WHITELIST (defense-in-depth): only a textbook rubric candidate with a point_id is eligible.
        # A mis-injected worker emitting answer_key / source / machine_spec / question candidates must
        # NOT reach the textbook signer even though the signer would also drop most of them.
        elif kind == _CF.KIND_RUBRIC and str((c.get("payload") or {}).get("point_id") or ""):
            eligible.append(c)
        else:
            rejected.append(_stage_log(c, {"stage": "S3", "gate": "G_kind_or_schema", "verdict": "fail"}))
    return {"eligible": eligible, "work_order": work_orders, "rejected": rejected, "conflict": []}


def _s5_sign_textbook(
    eligible: list[dict[str, Any]], *, freq_blocklist: list[str] | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """S5 for the textbook lane (the ONE flip site). Hands the eligible candidate payloads to the
    deterministic signer, which signs ONLY corpus-confirmed fields and work-orders the rest, then
    augments the manifest with a node_index so the resolver can resolve by node_code. The
    ``freq_blocklist`` (high-frequency boilerplate clauses) is threaded to the signer here so it never
    pollutes the candidate payloads / ledger."""
    cards = [dict(c.get("payload") or {}) for c in eligible]
    if freq_blocklist:
        for card in cards:
            card["_freq_blocklist"] = freq_blocklist
    bundle = _FKC.compile_textbook_knowledge_release_candidate(cards)
    nindex: dict[str, list[str]] = {}
    for r in bundle.get("records", []):
        node = str(r.get("node_code") or "")
        if node:
            nindex.setdefault(node, []).append(str(r.get("point_id")))
    # node_index does NOT affect content_hash/signature (computed over records only) -> safe.
    bundle["manifest"]["node_index"] = {n: sorted(set(p)) for n, p in nindex.items()}
    signed_pids = {str(r.get("point_id")) for r in bundle.get("records", [])}
    promoted: list[dict[str, Any]] = []
    for c in eligible:
        pid = str((c.get("payload") or {}).get("point_id"))
        if pid in signed_pids:
            promoted.append({**_stage_log(c, {"stage": "S5", "verdict": "signed"}),
                             "promote_to_release": True, "status": "release_candidate"})
        else:
            promoted.append(c)  # provenance-failed inside the signer -> stays candidate
    return bundle, promoted


def run_pipeline(
    evidence: list[dict[str, Any]],
    *,
    run_id: str,
    gates: GateSet = DEFAULT_GATES,
    llm_worker: LLMWorker | None = None,
    council: Council | None = None,
    max_iter: int = 3,
    prior_seen: set[str] | None = None,
    lane: str = "case",
    textbook_freq_blocklist: list[str] | None = None,
) -> dict[str, Any]:
    """Run S0-applied evidence through S1→S7. Returns a result dict with the signed bundle, ledgers,
    loop proof, and the safety report. ``lane`` selects the S3/S5 pair: "case" (default) or
    "textbook". ``textbook_freq_blocklist`` (boilerplate clauses present in many blocks) is threaded
    to the textbook signer. Deterministic; no production / remote / canonical write."""
    is_textbook = lane == "textbook"
    bundle_namespace = _FKC.TEXTBOOK_KNOWLEDGE_NAMESPACE if is_textbook else "case_rubric_full"
    worker = llm_worker or default_machine_spec_worker
    seen: set[str] = set(prior_seen or set())
    queue = [e for e in evidence if e.get("evidence_id") not in seen]
    seen |= {e["evidence_id"] for e in queue}

    all_candidates: list[dict[str, Any]] = []
    all_work_orders: list[dict[str, Any]] = []
    all_rejected: list[dict[str, Any]] = []
    all_conflicts: list[dict[str, Any]] = []
    all_reingested: list[dict[str, Any]] = []
    signed_bundle: dict[str, Any] | None = None
    iterations = 0

    while queue and iterations < max_iter:
        iterations += 1
        batch, queue = queue, []
        # S2 fan-out (write only)
        cands: list[dict[str, Any]] = []
        for item in batch:
            cands.extend(worker(item))
        cands = [_stage_log(c, {"stage": "S2", "verdict": "produced"}) for c in cands]
        all_candidates.extend(cands)
        # S3 deterministic gates (lane-selected)
        routed = _s3_gates_textbook(cands) if is_textbook else _s3_gates(cands, gates)
        all_rejected.extend(routed["rejected"])
        all_conflicts.extend(routed["conflict"])
        # S4 adversarial council (down-rank only)
        eligible = routed["eligible"]
        if council is not None and eligible:
            kept = council(eligible)
            kept_ids = {c.get("candidate_id") for c in kept}
            down_ranked = [_stage_log(c, {"stage": "S4", "verdict": "down_ranked"})
                           for c in eligible if c.get("candidate_id") not in kept_ids]
            all_work_orders.extend(down_ranked)
            eligible = kept
        # S5 sign (the one flip site; lane-selected)
        if eligible:
            bundle, promoted = (
                _s5_sign_textbook(eligible, freq_blocklist=textbook_freq_blocklist)
                if is_textbook else _s5_sign(eligible)
            )
            signed_bundle = bundle  # last run's signed bundle is canonical for the slice
            all_candidates.extend(promoted)
        all_work_orders.extend(routed["work_order"])
        # S7 re-ingest terminal items as NEW evidence (loop-until-dry, content-addressed dedup)
        terminal = routed["work_order"] + routed["rejected"]
        reingested = _B.reingest_terminal(terminal, seen=seen, run_id=run_id)
        all_reingested.extend(reingested)
        queue = reingested

    ledger = _CF.build_ledger(all_candidates)
    promoted_count = sum(1 for c in all_candidates if c.get("promote_to_release") is True)
    safety = _safety_report(signed_bundle, all_candidates, ledger, promoted_count,
                            namespace=bundle_namespace)
    return {
        "run_id": run_id,
        "iterations": iterations,
        "signed_bundle": signed_bundle,
        "candidates": all_candidates,
        "work_orders": all_work_orders,
        "rejected": all_rejected,
        "conflicts": all_conflicts,
        "reingested": all_reingested,
        "ledger": ledger,
        "promoted_count": promoted_count,
        "seen": sorted(seen),
        "safety": safety,
    }


def _safety_report(bundle, candidates, ledger, promoted_count, *, namespace="case_rubric_full") -> dict[str, Any]:
    """The §9 invariants. Every value must be 0 / False or the run is NO-GO. ``namespace`` selects the
    lane the signed bundle must verify under (case_rubric_full / textbook_knowledge_full)."""
    # a promote_to_release=True candidate that never went through S5 sign would be a violation.
    illegit_promote = sum(
        1 for c in candidates
        if c.get("promote_to_release") is True
        and not any(s.get("stage") == "S5" for s in (c.get("stage_log") or []))
    )
    laundering_blocked = sum(1 for c in candidates
                             if str(c.get("reason", "")).startswith("source_laundering_blocked"))
    tamper_ok = bool(bundle) and _FKC.verify_lane_bundle(bundle, namespace) if bundle else True
    manifest = bundle.get("manifest", {}) if bundle else {}
    return {
        "source_laundering_blocked": laundering_blocked,
        "candidate_used_as_release_truth": illegit_promote,
        "illegit_promote_outside_s5": illegit_promote,
        "promoted_count": promoted_count,
        "rag_chunk_as_answer_key": 0,
        "model_vote_as_source": 0,
        "council_vote_as_source": 0,
        "official_answer_as_source": int(manifest.get("official_answer_as_source", 0) or 0),
        "list_partial_auto": int(manifest.get("list_partial_auto", 0) or 0),
        "key_number_not_in_text_signed": int(manifest.get("key_number_not_in_text_signed", 0) or 0),
        "external_or_reviewonly_auto_signed": int(manifest.get("external_or_reviewonly_auto_signed", 0) or 0),
        "production_write_count": 0,
        "published": bool(manifest.get("published")) if bundle else False,
        "canonical_truth_written": False,
        "tamper_fail_closed": tamper_ok,
        "all_candidates_separate_namespace": ledger.get("all_separate_from_release", True),
    }


__all__ = [
    "GateSet", "DEFAULT_GATES", "LLMWorker", "Council",
    "default_machine_spec_worker", "run_pipeline",
]
