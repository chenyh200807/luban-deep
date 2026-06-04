"""AI-Draft shadow grading assembly (test-env / shadow / candidate_only).

This module owns NO grading authority. It is a SHADOW assembler that turns
already-produced DeepSeek-flash per-point predictions into a draft view +
learning_evidence payload preview, applying the validated guards:
  - span guard fail-closed (positive without verbatim student span -> unsupported)
  - exact_required rationale fallback (near/half-term self-admission -> high_risk_review)
  - selective-abstention model-observable proxy (list_rule-partial / weak span / hedge)
  - high_risk_review / unsupported are NEVER auto_certified (route, don't rescore)

It does NOT call any model, does NOT touch CaseGradingSkillKernel, does NOT write
to learner_memory_events, does NOT use RAG. The learning_evidence payload PREVIEW
reuses the EXISTING build_learning_evidence_payload (no new schema/table).
"""
from __future__ import annotations

import re
from typing import Any

from deeptutor.services.construction_grading.learning_evidence import (
    build_learning_evidence_payload,
)
from deeptutor.services.construction_grading.schema import (
    CaseGradingResult,
    CaseRubricItemResult,
)

DRAFT_MARKERS: dict[str, Any] = {
    "authority": "ai_draft_shadow",
    "candidate_only": True,
    "not_production_grade": True,
    "protocol_version": "arm2_semantic_protocol_v0",
    "metric_gate": {
        "legacy_raw_score_delta": "WEAK-GO",
        "metric_v2_qwk": "STRONG-candidate(candidate_only)",
    },
}

# exact_required rationale self-admission signals (mirror of the offline fallback)
_NEAR_SYNONYM = [
    "类似", "相当于", "近义", "部分表达", "泛称", "不完全一致", "不完全相同",
    "只写了一半", "一半", "意思相近", "近似", "约等于", "可视为", "缺少",
    "未写全", "未完全", "不够规范", "大白话", "口语", "非规范",
]
# selective-abstention hedge words
_HEDGE = [
    "不确定", "可能", "近义", "泛称", "大白话", "部分覆盖", "不完全",
    "只写了一半", "一半", "缺少", "存疑",
]


def _as_text(s: Any) -> str:
    if isinstance(s, list):
        return " ".join(_as_text(x) for x in s)
    return s if isinstance(s, str) else ("" if s is None else str(s))


def _norm(s: Any) -> str:
    return re.sub(r"[（）()\s、,.，。/；;:：!！?？]", "", _as_text(s))


def _span_in_answer(span: Any, answer: str) -> bool:
    s = _norm(span)
    return bool(s) and s in _norm(answer)


def _span_has_required_term(span: Any, terms: list[str]) -> bool:
    sc = _norm(span)
    for t in terms or []:
        tc = _norm(t)
        if tc and (tc in sc or (len(tc) >= 4 and tc in sc)):
            return True
    return False


def _exact_required_fallback(pred: dict, policy_type: str | None, required_terms: list[str]) -> bool:
    """exact_required + positive + (near-synonym rationale OR partial w/ span lacking core term)."""
    if policy_type != "exact_required":
        return False
    hit = str(pred.get("hit") or "miss")
    if hit not in ("hit", "partial"):
        return False
    rationale = _as_text(pred.get("rationale"))
    near = any(sig in rationale for sig in _NEAR_SYNONYM)
    span_ok = _span_has_required_term(pred.get("evidence_span"), required_terms)
    if near:
        return True
    if hit == "partial" and not span_ok:
        return True
    return False


def _abstention_risk(pred: dict, policy_type: str | None) -> float:
    """model-observable proxy (NO jury votes at request time)."""
    hit = str(pred.get("hit") or "miss")
    if hit not in ("hit", "partial"):
        return -1.0
    r = 0.0
    if policy_type == "list_rule" and hit == "partial":
        r += 0.6
    if len(_as_text(pred.get("evidence_span")).strip()) < 4:
        r += 0.4
    if any(h in _as_text(pred.get("rationale")) for h in _HEDGE):
        r += 0.3
    return round(r, 3)


def apply_guards(predictions: list[dict], points: list[dict], student_answer: str, *, abstain_tau: float = 0.6) -> list[dict]:
    info = {p.get("point_id"): (p.get("typed_policy") or {}) for p in points}
    out = []
    for pr in predictions:
        p = dict(pr)
        tp = info.get(p.get("point_id")) or {}
        policy_type = tp.get("policy_type")
        required_terms = list(tp.get("required_terms") or (tp.get("list_spec") or {}).get("terms") or [])
        hit = str(p.get("hit") or "miss")
        unsupported = hit in ("hit", "partial") and not _span_in_answer(p.get("evidence_span"), student_answer)
        exact_fb = _exact_required_fallback(p, policy_type, required_terms)
        abstain = _abstention_risk(p, policy_type) >= abstain_tau
        high_risk = bool(exact_fb or abstain or p.get("high_risk") is True)
        p["unsupported"] = bool(unsupported)
        p["high_risk_review"] = high_risk
        if high_risk:
            p.setdefault("review_reason", "exact_required_fallback" if exact_fb else "selective_abstention_proxy")
        p["auto_certified"] = (not unsupported) and (not high_risk)
        out.append(p)
    return out


def _point_max(points: list[dict], point_id: Any) -> float:
    for sp in points:
        if str(sp.get("point_id")) == str(point_id):
            return float(sp.get("max_score") or 0)
    return 0.0


def _point_label(points: list[dict], point_id: Any) -> str:
    for sp in points:
        if str(sp.get("point_id")) == str(point_id):
            return _as_text(sp.get("label"))
    return ""


def _display_status(p: dict) -> str:
    if p.get("unsupported"):
        return "unsupported"
    if p.get("high_risk_review"):
        return "pending_review"
    return "auto_certified"


def _to_case_grading_result(question: dict, points: list[dict], guarded: list[dict]) -> CaseGradingResult:
    items = []
    for p in guarded:
        hit = str(p.get("hit"))
        status = "full" if hit == "hit" else ("partial" if hit == "partial" else "miss")
        items.append(CaseRubricItemResult(
            criterion=str(p.get("point_id")), max_score=_point_max(points, p.get("point_id")),
            awarded_score=0.0 if p.get("unsupported") else float(p.get("score") or 0),
            status=status, keywords=[], evidence_text=_as_text(p.get("evidence_span")),
            source_fields=["ai_draft_shadow"]))
    certified_total = sum(i.awarded_score for i in items if not _is_pending(guarded, i.criterion))
    return CaseGradingResult(
        question_id=str(question.get("case_id") or question.get("id")), grading_mode="curated_rubric",
        score_awarded=round(certified_total, 3),
        max_score=float(question.get("max_score") or sum(i.max_score for i in items)),
        rubric_items=items, next_training_signal={"grading_source": "ai_draft_shadow", "candidate_only": True})


def _is_pending(guarded: list[dict], point_id: Any) -> bool:
    for p in guarded:
        if str(p.get("point_id")) == str(point_id):
            return bool(p.get("high_risk_review")) or bool(p.get("unsupported"))
    return False


def payload_preview(result: CaseGradingResult) -> dict:
    """Reuse the EXISTING learning_evidence builder (no write, no new schema)."""
    return build_learning_evidence_payload(grading_result=result)


def build_ai_draft(question: dict, student_answer: str, predictions: list[dict], *,
                   points: list[dict] | None = None, abstain_tau: float = 0.6,
                   build_preview: bool = True, student_id: str | None = None) -> dict:
    """Assemble the draft view from predictions (NO model call here)."""
    points = points if points is not None else (question.get("scoring_points") or [])
    guarded = apply_guards(predictions, points, student_answer, abstain_tau=abstain_tau)
    expected_n = len(points)
    parse_status = "ok" if len(predictions) == expected_n else ("mismatch" if predictions else "empty")

    def _sc(p):
        return float(p.get("score") or 0)
    model_draft_score = round(sum(_sc(p) for p in guarded), 3)
    auto_certified_score = round(sum(_sc(p) for p in guarded if p.get("auto_certified")), 3)
    pending_review_score = round(sum(_sc(p) for p in guarded if (p.get("high_risk_review") or p.get("unsupported"))), 3)
    bad_certified = sum(1 for p in guarded if (p.get("high_risk_review") or p.get("unsupported")) and p.get("auto_certified"))

    draft = {
        **DRAFT_MARKERS,
        "dry_run": True,
        "question_id": question.get("case_id") or question.get("id"),
        "student_id": student_id,
        "parse_status": parse_status,
        "expected_point_count": expected_n,
        "model_draft_score": model_draft_score,
        "auto_certified_score": auto_certified_score,
        "pending_review_score": pending_review_score,
        "total_score_certified_only": auto_certified_score,
        "bad_certified_count": bad_certified,
        "score_semantics_note": "model_draft_score=模型原始草稿分; auto_certified_score=自动认证分; pending_review_score=待复核分(非0,需人/陪审复核)。展示时 pending 不得当0。",
        "point_count": len(guarded),
        "high_risk_review_count": sum(1 for p in guarded if p.get("high_risk_review")),
        "unsupported_count": sum(1 for p in guarded if p.get("unsupported")),
        "auto_certified_count": sum(1 for p in guarded if p.get("auto_certified")),
        "point_results": [{
            "point_id": p.get("point_id"),
            "policy_type": (info := next((sp.get("typed_policy", {}) for sp in points if str(sp.get("point_id")) == str(p.get("point_id"))), {})).get("policy_type"),
            "expected_point_label": _point_label(points, p.get("point_id")),
            "hit": p.get("hit"), "score": p.get("score"), "max_score": _point_max(points, p.get("point_id")),
            "evidence_span": _as_text(p.get("evidence_span")), "rationale": p.get("rationale"),
            "auto_certified": bool(p.get("auto_certified")), "high_risk_review": bool(p.get("high_risk_review")),
            "unsupported": bool(p.get("unsupported")), "review_reason": p.get("review_reason"),
            "display_status": _display_status(p),
        } for p in guarded],
    }
    if build_preview:
        try:
            draft["learning_evidence_payload_preview"] = payload_preview(_to_case_grading_result(question, points, guarded))
        except Exception as exc:  # noqa: BLE001
            draft["learning_evidence_payload_preview_error"] = str(exc)[:200]
    return draft
