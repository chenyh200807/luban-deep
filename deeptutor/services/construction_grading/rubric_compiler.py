"""Rubric compiler — turn case-question reference answers into scored scoring-point rubrics.

The grading ground truth is the EXAM REFERENCE ANSWER, not the textbook. Each independent information
point in the reference answer is one scoring point; its score is that point's weight in the total; a
student gets a point's score when their answer hits it (semantic match — near-synonyms accepted except
exact_required term points). This is the Nexus-like design: the rubric is evidence/structure for runtime
LLM adjudication, NOT a verbatim hard gate. Open-world questions (not in bank) get a rubric extracted on
the fly the same way.

This module is the DETERMINISTIC spine: it validates + normalizes the (LLM-extracted) rubric — the score
split must sum to the total (a hard gate that catches extraction errors), policy must be known, points
must be non-empty. The LLM extraction (reading reference answers) happens in the runner / online grader;
the signer (``compile_case_rubric_release_candidate``) is the sole authority that emits the release.
"""
from __future__ import annotations

from typing import Any

POLICIES = {"exact_required", "list", "calc", "qualitative", "boolean_judgment"}
_SCORE_EPS = 0.01


def validate_rubric(rubric: dict[str, Any]) -> dict[str, Any]:
    """Validate one extracted rubric. Returns {ok, reason, normalized} — the deterministic gate that
    makes 'how many points / what score' trustworthy (LLM proposes, this checks)."""
    qid = str(rubric.get("qid") or "").strip()
    total = rubric.get("total_score")
    points = rubric.get("scoring_points") or []
    if not qid:
        return {"ok": False, "reason": "missing_qid", "normalized": None}
    if not isinstance(points, list) or not points:
        return {"ok": False, "reason": "no_scoring_points", "normalized": None}
    norm_points: list[dict[str, Any]] = []
    ssum = 0.0
    for i, p in enumerate(points):
        text = str(p.get("text") or "").strip()
        policy = str(p.get("policy") or "").strip()
        try:
            score = float(p.get("score"))
        except (TypeError, ValueError):
            return {"ok": False, "reason": f"bad_score_at_{i}", "normalized": None}
        if not text:
            return {"ok": False, "reason": f"empty_point_text_at_{i}", "normalized": None}
        if policy not in POLICIES:
            return {"ok": False, "reason": f"unknown_policy:{policy}", "normalized": None}
        if score <= 0:
            return {"ok": False, "reason": f"nonpositive_score_at_{i}", "normalized": None}
        ssum += score
        norm_points.append({
            "point_id": str(p.get("point_id") or f"SP{i}"),
            "text": text, "score": score, "policy": policy,
            "required_terms": [str(t) for t in (p.get("required_terms") or []) if str(t).strip()],
        })
    # HARD GATE: the score split must reconstruct the official total — this is what makes "2 or 3 points"
    # a deterministic sum, not an LLM guess.
    try:
        total_f = float(total)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "bad_total_score", "normalized": None}
    if abs(ssum - total_f) > _SCORE_EPS:
        return {"ok": False, "reason": f"score_sum_mismatch:{ssum}!={total_f}", "normalized": None}
    return {"ok": True, "reason": "ok",
            "normalized": {"qid": qid, "total_score": total_f, "scoring_points": norm_points}}


def to_signable_points(rubric: dict[str, Any], *, source_meta: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Shape a validated rubric into per-point records for ``compile_case_rubric_release_candidate``.
    provenance = exam reference answer (NOT textbook verbatim — that was the old over-constraint)."""
    qid = rubric["qid"]
    out: list[dict[str, Any]] = []
    for p in rubric["scoring_points"]:
        out.append({
            "point_id": f"{qid}::{p['point_id']}",
            "text": p["text"],
            "authority_kind": p["policy"],
            "required_terms": p["required_terms"],
            "max_score": p["score"],
            "source_refs": [{"kind": "exam_reference_answer", "qid": qid, **(source_meta or {})}],
        })
    return out


def reconcile_dual_model(opus: dict[str, Any], codex: dict[str, Any]) -> dict[str, Any]:
    """Reconcile two models' rubrics for the same question. Prefer the FINER-grained valid extraction
    (real exam grading is per-item; the finer split gives sharper hit diagnosis), provided it passes the
    score-sum gate. Returns {chosen, basis, agree_total}."""
    vo, vc = validate_rubric(opus), validate_rubric(codex)
    agree_total = (vo["ok"] and vc["ok"]
                   and abs(vo["normalized"]["total_score"] - vc["normalized"]["total_score"]) <= _SCORE_EPS)
    if vo["ok"] and vc["ok"]:
        no, nc = len(vo["normalized"]["scoring_points"]), len(vc["normalized"]["scoring_points"])
        chosen = vc["normalized"] if nc >= no else vo["normalized"]
        basis = "finer_grained" if nc != no else "equal_pick_codex" if nc == no else "tie"
        return {"chosen": chosen, "basis": basis, "agree_total": agree_total,
                "opus_points": no, "codex_points": nc}
    if vo["ok"]:
        return {"chosen": vo["normalized"], "basis": "only_opus_valid", "agree_total": False}
    if vc["ok"]:
        return {"chosen": vc["normalized"], "basis": "only_codex_valid", "agree_total": False}
    return {"chosen": None, "basis": "both_invalid", "agree_total": False,
            "opus_reason": vo["reason"], "codex_reason": vc["reason"]}


def sign_rubric_release_candidate(rubrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Sign validated rubrics into a release_candidate bundle (Nexus-like model: rubric = scored
    scoring-point structure for runtime LLM adjudication, sourced from exam reference answers).

    Unlike the legacy case_rubric signer (which demanded machine_spec / list_items verbatim specs),
    this signs the lightweight rubric: point text + score + policy + required_terms + reference-answer
    provenance. The score-sum gate is the determinism guarantee. Per-record + bundle hash/signature."""
    from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex
    signed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    by_policy: dict[str, int] = {}
    for r in rubrics:
        v = validate_rubric(r)
        if not v["ok"]:
            rejected.append({"qid": r.get("qid"), "reason": v["reason"]})
            continue
        nr = v["normalized"]
        for p in nr["scoring_points"]:
            by_policy[p["policy"]] = by_policy.get(p["policy"], 0) + 1
            signed.append({
                "point_id": f"{nr['qid']}::{p['point_id']}",
                "qid": nr["qid"],
                "text": p["text"][:400],
                "score": p["score"],
                "policy": p["policy"],
                "required_terms": p["required_terms"],
                "total_score": nr["total_score"],
                "answer_key_authority": "exam_reference_answer",
            })
    signed.sort(key=lambda x: x["point_id"])
    content_hash = _sha256_hex(signed)
    namespace = "case_rubric_scored"
    status = "release_candidate"
    manifest = {
        "schema_version": "luban_rubric_compiler.v1",
        "namespace": namespace, "lane": "case_rubric_scored", "status": status, "published": False,
        "question_count": len({s["qid"] for s in signed}),
        "scoring_point_count": len(signed),
        "by_policy": by_policy,
        "rejected_count": len(rejected),
        "answer_key_authority": "exam_reference_answer",  # NOT textbook verbatim (Nexus-like)
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, namespace, status]),
        "rollback_pointer": "legacy (no case_rubric_scored -> existing case_rubric_full stays)",
    }
    return {"manifest": manifest, "records": signed, "rejected": rejected}


__all__ = ["POLICIES", "validate_rubric", "to_signable_points", "reconcile_dual_model",
           "sign_rubric_release_candidate"]
