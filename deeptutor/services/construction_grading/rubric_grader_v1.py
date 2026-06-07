"""Rubric grader v1 — LLM-adjudicated, scoring-point grading that produces learning-evidence events.

The Nexus-like grading engine v1: load the compiled scored rubric (``v_case_rubric_scored``, sourced
from exam reference answers), have an LLM adjudicate EACH scoring point (hit / partial / miss — semantic
match, near-synonyms accepted except exact_required term points), then DETERMINISTICALLY sum awarded
scores. "2 or 3 points" is a sum of per-point judgments, never an LLM guess of a whole-question score.

Open-world: a question not in the rubric bank is graded with an on-the-fly rubric extracted the same way
(the caller passes ``rubric`` directly). The grader never refuses for "not in bank".

Output is a GradingEvent that maps onto the learner_state learning_evidence schema (concept-level
scoring points + mistake types + evidence span + high-risk flag) -> feeds learner_memory_events -> PCP
-> next_best_action.

This module is the DETERMINISTIC spine + event shaping; the per-point hit judgment is injected as
``judge_fn`` (an LLM in production, a deterministic stub in tests), so it is hermetic and testable.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

# a judge returns one of these per scoring point
HIT = "hit"
PARTIAL = "partial"
MISS = "miss"

# mistake taxonomy carried into learner evidence (why the point was lost)
MISTAKE_MISS = "omitted"
MISTAKE_NEAR_SYNONYM = "near_synonym_not_exact"   # exact_required term not precisely hit
MISTAKE_PARTIAL_LIST = "list_incomplete"
MISTAKE_WRONG = "wrong_content"

JudgeFn = Callable[[dict[str, Any], str], dict[str, Any]]
# judge_fn(scoring_point, student_answer) -> {"status": hit|partial|miss, "evidence_span": str,
#                                             "mistake_type": str, "partial_ratio": float}


def grade_with_rubric(
    *,
    qid: str,
    student_answer: str,
    rubric_points: list[dict[str, Any]],
    judge_fn: JudgeFn,
    student_id: str = "",
    high_risk_margin: float = 0.15,
) -> dict[str, Any]:
    """Grade one case answer against its scored rubric. Returns a GradingEvent.

    Each point: {point_id, text, score, policy, required_terms}. judge_fn adjudicates hit/partial/miss
    per point; partial awards score*partial_ratio (for list/qualitative); exact_required awards full or
    zero (a term is right or wrong). Sum is deterministic. high_risk flags low-confidence/near-miss
    grading for human review (the high-risk fallback)."""
    answer = str(student_answer or "")
    points_out: list[dict[str, Any]] = []
    awarded_total = 0.0
    max_total = 0.0
    low_conf = 0
    for p in rubric_points:
        max_score = float(p.get("score") or 0)
        max_total += max_score
        policy = str(p.get("policy") or "qualitative")
        verdict = judge_fn(p, answer) or {}
        status = str(verdict.get("status") or MISS)
        ratio = float(verdict.get("partial_ratio") or (1.0 if status == HIT else 0.0))
        # exact_required is binary: a规范术语 is right or wrong, no partial credit
        if policy == "exact_required":
            awarded = max_score if status == HIT else 0.0
            status = HIT if status == HIT else MISS
        elif status == HIT:
            awarded = max_score
        elif status == PARTIAL:
            awarded = round(max_score * max(0.0, min(1.0, ratio)), 2)
        else:
            awarded = 0.0
        awarded_total += awarded
        mistake = None
        if status != HIT:
            mistake = (MISTAKE_NEAR_SYNONYM if policy == "exact_required"
                       else MISTAKE_PARTIAL_LIST if status == PARTIAL
                       else str(verdict.get("mistake_type") or MISTAKE_MISS))
        if verdict.get("low_confidence"):
            low_conf += 1
        points_out.append({
            "point_id": p.get("point_id"),
            "knowledge_point": p.get("text"),
            "policy_type": policy,
            "hit": status,
            "score": awarded,
            "max_score": max_score,
            "mistake_type": mistake,
            "evidence_span": str(verdict.get("evidence_span") or ""),
            "required_terms": list(p.get("required_terms") or []),
        })
    awarded_total = round(awarded_total, 2)
    # high-risk: any low-confidence judgment, or near a scoring boundary -> route to human review
    near_boundary = bool(max_total) and (0 < abs(awarded_total - round(awarded_total)) < high_risk_margin)
    high_risk = low_conf > 0 or near_boundary
    return {
        "event_type": "case_grading_completed",
        "student_id": student_id,
        "question_id": qid,
        "scoring_points": points_out,
        "awarded_score": awarded_total,
        "max_score": round(max_total, 2),
        "high_risk_review": high_risk,
        "grading_source": "rubric_scored_v1",
        "answer_key_authority": "exam_reference_answer",
        "llm_adjudicated": True,
        "official_score_allowed": False,   # v1 is candidate evidence; teacher/governed gate promotes
    }


def to_learning_evidence(event: dict[str, Any], *, node_code: str = "") -> dict[str, Any]:
    """Project a GradingEvent into a learner_state learning_evidence payload (weak points = missed
    scoring points). Append-only producer; never writes learner truth itself."""
    weak_points = []
    for sp in event.get("scoring_points") or []:
        if sp.get("hit") != HIT:
            weak_points.append({
                "concept_id": node_code or sp.get("point_id"),
                "concept_label": sp.get("knowledge_point"),
                "error_code": sp.get("mistake_type") or MISTAKE_MISS,
                "evidence_span": sp.get("evidence_span"),
                "policy_type": sp.get("policy_type"),
                "lost_score": round(sp.get("max_score", 0) - sp.get("score", 0), 2),
            })
    return {
        "event_type": "learning_evidence",
        "learning_signal_type": "case_grading",
        "student_id": event.get("student_id"),
        "question_id": event.get("question_id"),
        "awarded_score": event.get("awarded_score"),
        "max_score": event.get("max_score"),
        "weak_points": weak_points,
        "high_risk_review": event.get("high_risk_review"),
        "source_refs": [{"kind": "exam_reference_answer", "qid": event.get("question_id")}],
        "writeback_performed": False,
    }


def load_rubric(qid: str) -> list[dict[str, Any]]:
    """Load a question's compiled scoring-point rubric from the tracked supply (empty if not in bank ->
    caller does open-world on-the-fly extraction). Verify-gated."""
    from functools import lru_cache
    import json
    from pathlib import Path

    @lru_cache(maxsize=1)
    def _bank() -> dict[str, list[dict[str, Any]]]:
        p = Path(__file__).parent / "runtime_supply" / "v_case_rubric_scored" / "case_rubric_scored.json"
        if not p.exists():
            return {}
        try:
            b = json.loads(p.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex
        m = b.get("manifest") or {}
        if _sha256_hex(b.get("records") or []) != m.get("content_hash"):
            return {}
        by_q: dict[str, list[dict[str, Any]]] = {}
        for r in b.get("records") or []:
            by_q.setdefault(str(r.get("qid")), []).append({
                "point_id": r.get("point_id"), "text": r.get("text"), "score": r.get("score"),
                "policy": r.get("policy"), "required_terms": r.get("required_terms") or []})
        return by_q

    return _bank().get(str(qid), [])


_BATCH_SYSTEM_PROMPT = "你只判采分点命中,输出JSON数组。"


def _batch_prompt(rubric_points: list[dict[str, Any]], student_answer: str) -> str:
    """Pure prompt builder for the one-shot batch adjudication (shared by sync + async paths)."""
    import json as _json

    lines = []
    for p in rubric_points:
        strict = "(术语必须精确,近义不算)" if p.get("policy") == "exact_required" else "(意思对即可,允许近义)"
        lines.append(f'  {{"point_id":"{p.get("point_id")}","采分点":"{p.get("text")}",'
                     f'"关键词":{_json.dumps(p.get("required_terms") or [], ensure_ascii=False)},"判定标准":"{strict}"}}')
    return (
        "你是一建案例题阅卷员。逐个判断学生作答是否命中每个采分点,只判命中不改分值。\n"
        "采分点列表:\n[" + ",\n".join(lines) + "]\n\n"
        f"学生作答:\n{str(student_answer)[:1500]}\n\n"
        '只输出JSON数组,每个采分点一项: '
        '[{"point_id":..,"status":"hit|partial|miss","partial_ratio":0-1,'
        '"evidence_span":"命中的原句片段","mistake_type":"omitted|wrong_content"}]'
    )


def _parse_batch_verdicts(raw: Any) -> dict[str, dict[str, Any]]:
    """Pure parser: LLM JSON-array text -> {point_id: verdict}. Malformed -> {} (caller fails closed)."""
    import json as _json

    out: dict[str, dict[str, Any]] = {}
    try:
        s = str(raw)
        arr = _json.loads(s[s.find("["):s.rfind("]") + 1])
        for v in arr:
            if isinstance(v, dict) and v.get("point_id"):
                out[str(v["point_id"])] = v
    except Exception:  # noqa: BLE001 — malformed -> empty -> all miss+low_conf (high-risk fallback)
        pass
    return out


def batch_judge(
    rubric_points: list[dict[str, Any]], student_answer: str,
    complete_fn: Callable[..., Any], api_key: str, *, model: str = "deepseek-chat",
) -> dict[str, dict[str, Any]]:
    """Adjudicate ALL scoring points in ONE LLM call (O(1) cost vs O(n) per-point). Returns
    {point_id: verdict}. A point missing from the LLM response -> miss+low_confidence (never silent
    credit). The deterministic sum in grade_with_rubric is unchanged; only the verdict source batches.

    Sync entrypoint — uses ``asyncio.run``; do NOT call from a running event loop (use
    ``batch_judge_async`` there)."""
    import asyncio

    prompt = _batch_prompt(rubric_points, student_answer)
    try:
        raw = asyncio.run(complete_fn(prompt=prompt, system_prompt=_BATCH_SYSTEM_PROMPT,
                                      model=model, api_key=api_key, max_retries=1))
    except Exception:  # noqa: BLE001 — batch failure -> all miss+low_conf (high-risk fallback)
        return {}
    return _parse_batch_verdicts(raw)


async def batch_judge_async(
    rubric_points: list[dict[str, Any]], student_answer: str,
    complete_fn: Callable[..., Any], api_key: str, *, model: str = "deepseek-chat",
) -> dict[str, dict[str, Any]]:
    """Async twin of ``batch_judge`` — awaits ``complete_fn`` directly so it is safe to call from inside
    a running event loop (e.g. the deep_question runtime). Same fail-closed contract."""
    prompt = _batch_prompt(rubric_points, student_answer)
    try:
        raw = await complete_fn(prompt=prompt, system_prompt=_BATCH_SYSTEM_PROMPT,
                                model=model, api_key=api_key, max_retries=1)
    except Exception:  # noqa: BLE001 — batch failure -> all miss+low_conf (high-risk fallback)
        return {}
    return _parse_batch_verdicts(raw)


def make_batch_judge(complete_fn: Callable[..., Any], api_key: str, *, model: str = "deepseek-chat") -> JudgeFn:
    """A JudgeFn backed by a single batched LLM call (cached per answer). Drop-in for grade_with_rubric."""
    cache: dict[str, dict[str, dict[str, Any]]] = {}

    def judge(point: dict[str, Any], answer: str, *, _all: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        # cache keyed by answer; first call populates all verdicts via one batch call
        if answer not in cache:
            cache[answer] = batch_judge(_all or [point], answer, complete_fn, api_key, model=model)
        return cache[answer].get(str(point.get("point_id")), {"status": MISS, "low_confidence": True})

    return judge


def grade_with_batch_judge(
    *, qid: str, student_answer: str, rubric_points: list[dict[str, Any]],
    complete_fn: Callable[..., Any], api_key: str, student_id: str = "", model: str = "deepseek-chat",
) -> dict[str, Any]:
    """grade_with_rubric using a SINGLE batched LLM call for all points (production case path)."""
    verdicts = batch_judge(rubric_points, student_answer, complete_fn, api_key, model=model)

    def judge(point: dict[str, Any], _answer: str) -> dict[str, Any]:
        return verdicts.get(str(point.get("point_id")), {"status": MISS, "low_confidence": True})

    return grade_with_rubric(qid=qid, student_answer=student_answer, rubric_points=rubric_points,
                             judge_fn=judge, student_id=student_id)


async def grade_with_batch_judge_async(
    *, qid: str, student_answer: str, rubric_points: list[dict[str, Any]],
    complete_fn: Callable[..., Any], api_key: str, student_id: str = "", model: str = "deepseek-chat",
) -> dict[str, Any]:
    """Async twin of ``grade_with_batch_judge`` — safe to call from a running event loop. ONE awaited
    LLM call for all points; the deterministic sum (``grade_with_rubric``) stays unchanged."""
    verdicts = await batch_judge_async(rubric_points, student_answer, complete_fn, api_key, model=model)

    def judge(point: dict[str, Any], _answer: str) -> dict[str, Any]:
        return verdicts.get(str(point.get("point_id")), {"status": MISS, "low_confidence": True})

    return grade_with_rubric(qid=qid, student_answer=student_answer, rubric_points=rubric_points,
                             judge_fn=judge, student_id=student_id)


def make_llm_judge(complete_fn: Callable[..., Any], api_key: str, *, model: str = "deepseek-chat") -> JudgeFn:
    """Production judge: an LLM decides hit/partial/miss per scoring point (semantic, near-synonym aware).
    DeepSeek for cost; high-risk results route to a stronger model / human (handled by the caller)."""
    import asyncio
    import json as _json

    def judge(point: dict[str, Any], answer: str) -> dict[str, Any]:
        policy = str(point.get("policy") or "")
        strict = "术语必须精确命中(近义不算)" if policy == "exact_required" else "意思对即可(允许近义/换种说法)"
        prompt = (
            f"判断学生作答是否命中该采分点。{strict}。\n"
            f"采分点: {point.get('text')}\n关键词: {point.get('required_terms')}\n"
            f"学生作答: {str(answer)[:1200]}\n"
            f'只输出JSON: {{"status":"hit|partial|miss","partial_ratio":0-1,'
            f'"evidence_span":"命中的原句片段","mistake_type":"omitted|wrong_content","low_confidence":bool}}'
        )
        try:
            raw = asyncio.run(complete_fn(prompt=prompt, system_prompt="你是一建案例题阅卷员,只判命中不改分值。",
                                          model=model, api_key=api_key, max_retries=1))
            v = _json.loads(str(raw)[str(raw).find("{"):str(raw).rfind("}") + 1])
            return v if isinstance(v, dict) else {"status": MISS, "low_confidence": True}
        except Exception:  # noqa: BLE001 — judge failure -> miss + low_confidence (high-risk fallback)
            return {"status": MISS, "low_confidence": True}

    return judge


__all__ = ["grade_with_rubric", "grade_with_batch_judge", "grade_with_batch_judge_async",
           "batch_judge", "batch_judge_async", "make_batch_judge",
           "to_learning_evidence", "load_rubric", "make_llm_judge",
           "HIT", "PARTIAL", "MISS", "MISTAKE_MISS", "MISTAKE_NEAR_SYNONYM", "MISTAKE_PARTIAL_LIST"]
