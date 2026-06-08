"""Runtime LLM Adjudicator (fat skill) — Nexus-style scoped GradingPacket + DeepSeek/Qwen
point-level adjudication, gated by a deterministic validator.

Per §0.12: offline compilation produces a trusted, scoped ``GradingPacket``; every real grading is
adjudicated by a runtime LLM (DeepSeek-V4-flash primary, Qwen3.7 plus fallback). The deterministic
validator is the SAFETY FLOOR — it never lets the LLM upgrade a point the deterministic matcher
rejects, never lets ``evidence_span`` come from outside the student answer, never lets a list_rule
partial auto-certify, and keeps everything append-only / no production write.

The LLM is ADDITIVE: finer dispositions (accept/partial/reject/needs_review), evidence spans and
short reasoning for teacher-review packets. It can DOWNGRADE a deterministic-auto point to
partial/needs_review, but can NEVER UPGRADE a deterministic-reject point to auto.

HARD: official_answer / model vote / AI council are NEVER a source authority; no production default;
no production / canonical learner-truth write; legacy ``construction_grading_result`` untouched.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import re
import threading
import time
from typing import Any, Callable, Optional

from deeptutor.services.construction_grading import beta_shadow_loader as bsl

ADJUDICATOR_SCHEMA = "luban_runtime_grading_packet.v1"
PRIMARY_MODEL = "deepseek_v4_flash"   # routed to deepseek-chat
FALLBACK_MODEL = "qwen3.7_plus"       # routed to qwen-plus (dashscope)
DISPOSITIONS = ("accept", "partial", "reject", "needs_review")
TOKEN_BUDGET = 1200

# --- production runtime hardening config (fat skill; thin wrapper only sets flag/env) ---
DEFAULT_TIMEOUT_S = 30.0          # env LUBAN_V1_ADJUDICATOR_TIMEOUT_S
DEFAULT_MAX_CONCURRENT = 4        # env LUBAN_V1_ADJUDICATOR_MAX_CONCURRENT
# Indicative public-list price estimate (USD / 1M tokens). NOT billing truth — for cost ledger only.
PRICE_USD_PER_M = {
    PRIMARY_MODEL: {"in": 0.27, "out": 1.10},
    FALLBACK_MODEL: {"in": 0.40, "out": 1.20},
}

_SEQ = itertools.count(1)
_CONCURRENCY_SEM: Optional[threading.BoundedSemaphore] = None
_CONCURRENCY_SEM_N: Optional[int] = None


class AdjudicatorUnavailable(Exception):
    """Raised when neither primary nor fallback provider can run -> wrapper fails closed."""


def _norm(s: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’]", "", str(s or ""))


# ----------------------------- GradingPacket builder -----------------------------

def build_grading_packet(question_id: str, student_answer: str, *,
                         supply: bsl.BetaSupply, registry: dict[str, Any],
                         legacy_summary: dict[str, Any] | None = None,
                         personalization_context_pack: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a task-scoped GradingPacket: only this question's counted points + their source/spec/list
    policy slices, the student answer, registry provenance, allowed evidence kinds, and a READ-ONLY
    PersonalizationContextPack block. No answer key is leaked; the packet carries rubric policy only."""
    registry_points = {(p["question_id"], p["point_id"]): p for p in registry.get("points", [])}
    point_slices = []
    for (qid, pid) in sorted(registry_points):
        if qid != question_id:
            continue
        meta = registry_points[(qid, pid)]
        kind = meta["authority_kind"]
        slice_ = {"point_id": pid, "authority_kind": kind, "source_provenance": meta.get("source_provenance")}
        if (qid, pid) in supply.machine_specs:
            spec = supply.machine_specs[(qid, pid)]["spec"]
            slice_["spec_policy"] = {"kind": spec.get("kind"), "expected": spec.get("expected"),
                                     "unit": spec.get("unit"), "judgment": spec.get("judgment"),
                                     "acceptance_range": spec.get("acceptance_range"),
                                     "lo": spec.get("lo"), "hi": spec.get("hi"), "expected_bool": spec.get("expected_bool")}
        elif (qid, pid) in supply.list_specs:
            ls = supply.list_specs[(qid, pid)]["spec"]
            slice_["list_policy"] = {"denominator": ls.get("denominator"),
                                     "item_set": [m_["item"] for m_ in ls.get("item_matchers", [])],
                                     "coverage_required": 1.0}
        elif (qid, pid) in supply.source_terms:
            slice_["textbook_policy"] = {"verified_terms": supply.source_terms[(qid, pid)]}
        point_slices.append(slice_)

    pcp = personalization_context_pack if isinstance(personalization_context_pack, dict) else {}
    feedback_guidance = _feedback_guidance_from_pcp(pcp)
    packet = {
        "schema_version": ADJUDICATOR_SCHEMA,
        "question_id": question_id,
        "point_ids": [s["point_id"] for s in point_slices],
        "student_answer": student_answer,
        "legacy_construction_grading_result_summary": legacy_summary or {"present": False},
        "registry_release_candidate": {"version_id": registry.get("version_id"),
                                       "registry_content_hash": registry.get("registry_content_hash"),
                                       "status": registry.get("status")},
        "source_spec_list_policy_slices": point_slices,
        "allowed_evidence_kinds": ["student_answer_span", "rubric_policy_slice"],
        "blocked_policy": {"official_answer_as_source": False, "model_vote_as_source": False,
                           "list_partial_auto": False, "high_risk_auto": False},
        "personalization_context_pack_readonly": {"read_only": True,
                                                  "source": pcp.get("source") or "PersonalizationContextPack",
                                                  "weakness_hint": feedback_guidance.get("prior_claim_label"),
                                                  "feedback_guidance": feedback_guidance,
                                                  "scoring_authority": "rubric_policy_and_validator_only",
                                                  "is_second_learner_memory": False},
        "token_budget": TOKEN_BUDGET,
        "provenance": {"builder": "runtime_llm_adjudicator", "supply_content_hash": supply.content_hash},
    }
    packet["packet_hash"] = hashlib.sha256(
        json.dumps({k: packet[k] for k in ("question_id", "point_ids", "student_answer",
                                            "registry_release_candidate", "source_spec_list_policy_slices")},
                   ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return packet


# ----------------------------- provider layer (DeepSeek primary, Qwen fallback) -----------------------------

def _adjudication_prompt(packet: dict[str, Any]) -> tuple[str, str]:
    system = ("你是建筑实务案例题的点级判分助手。只依据给定 rubric policy 和学生作答判分。"
              "禁止编造未给出的标准答案；reasoning_summary 必须简短且不得泄露隐藏答案。"
              "personalization_feedback_guidance 只用于讲评语气、错因解释粒度和下一步提示，不得改变采分点命中判断。"
              "只输出 JSON 数组，每个采分点一个对象：{point_id, disposition, evidence_span, confidence, reasoning_summary, blocked_reason}。"
              "disposition ∈ accept|partial|reject|needs_review。evidence_span 必须是学生作答里的原文片段。")
    pcp = packet.get("personalization_context_pack_readonly") if isinstance(
        packet.get("personalization_context_pack_readonly"), dict
    ) else {}
    user = json.dumps({"question_id": packet["question_id"], "student_answer": packet["student_answer"],
                       "points": packet["source_spec_list_policy_slices"],
                       "personalization_feedback_guidance": pcp.get("feedback_guidance") or {}}, ensure_ascii=False)
    return system, user


def _feedback_guidance_from_pcp(pcp: dict[str, Any]) -> dict[str, str]:
    """Derive grading-feedback guidance from the single PersonalizationContextPack.

    This is deliberately a read-only projection: it can change tone and next-action wording,
    but scoring authority stays with rubric policy + validator.
    """
    claims = [claim for claim in list(pcp.get("top_claims") or []) if isinstance(claim, dict)]
    claim = claims[0] if claims else {}
    status = str(claim.get("claim_status") or "").strip()
    label = str(claim.get("label") or claim.get("claim_id") or "").strip()
    actions = [
        action for action in list(pcp.get("next_best_action_candidates") or [])
        if isinstance(action, dict)
    ]
    action = actions[0] if actions else {}
    target = str(action.get("target") or action.get("title") or "").strip()
    if status in {"repeated", "confirmed"}:
        tone = "advanced_repeat_mistake"
        depth = "reference_prior_pattern"
    elif status == "observed":
        tone = "scaffolded_first_observation"
        depth = "concept_and_required_term"
    else:
        tone = "neutral"
        depth = "standard_point_explanation"
    return {
        "grading_tone": tone,
        "explanation_depth": depth,
        "prior_claim_label": label,
        "next_action_hint": target,
    }


def _timeout_s() -> float:
    """Per-call wall-clock timeout (env override). Production runtime hardening (Group C)."""
    try:
        return max(1.0, float(os.environ.get("LUBAN_V1_ADJUDICATOR_TIMEOUT_S", DEFAULT_TIMEOUT_S)))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_S


def _semaphore() -> threading.BoundedSemaphore:
    """Process-wide max-concurrent / rate-limit guard (env override). Rebuilt if the cap changes."""
    global _CONCURRENCY_SEM, _CONCURRENCY_SEM_N
    try:
        n = max(1, int(os.environ.get("LUBAN_V1_ADJUDICATOR_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT)))
    except (TypeError, ValueError):
        n = DEFAULT_MAX_CONCURRENT
    if _CONCURRENCY_SEM is None or _CONCURRENCY_SEM_N != n:
        _CONCURRENCY_SEM = threading.BoundedSemaphore(n)
        _CONCURRENCY_SEM_N = n
    return _CONCURRENCY_SEM


def _is_timeout(exc: BaseException) -> bool:
    import asyncio
    import concurrent.futures
    return isinstance(exc, (asyncio.TimeoutError, concurrent.futures.TimeoutError, TimeoutError)) \
        or "timeout" in str(exc).lower()


def _error_kind(exc: BaseException) -> str:
    if _is_timeout(exc):
        return "timeout"
    msg = str(exc).lower()
    if isinstance(exc, AdjudicatorUnavailable) and "rate_limit" in msg:
        return "rate_limited"
    if "429" in msg or "rate" in msg and "limit" in msg:
        return "rate_limited"
    if "key" in msg and ("absent" in msg or "missing" in msg):
        return "auth_missing"
    if any(t in msg for t in ("connection", "network", "timed out", "resolve", "refused")):
        return "network"
    return "provider_error"


def _est_tokens(text: str) -> int:
    """Rough token estimate (mixed zh/en ~2 chars/token). Labeled indicative, not billing truth."""
    return int(math.ceil(len(text or "") / 2.0))


def _ledger_entry(model: str, role: str, system: str, user: str, raw: str,
                  call_ms: Optional[float], queue_ms: Optional[float], *,
                  ok: bool, error: Optional[str] = None) -> dict[str, Any]:
    in_tok = _est_tokens(system) + _est_tokens(user)
    out_tok = _est_tokens(raw) if ok else 0
    price = PRICE_USD_PER_M.get(model, {"in": 0.0, "out": 0.0})
    est_usd = (in_tok * price["in"] + out_tok * price["out"]) / 1_000_000.0
    return {
        "model": model, "model_role": role, "ok": ok, "error_kind": error,
        "call_latency_ms": round(call_ms, 1) if call_ms is not None else None,
        "queue_wait_ms": round(queue_ms, 1) if queue_ms is not None else None,
        "estimated_prompt_tokens": in_tok, "estimated_output_tokens": out_tok,
        "estimated_cost_usd": round(est_usd, 6),
        "cost_basis": "indicative_public_list_estimate_not_billing_truth",
    }


def _call_provider_timed(prov: Callable[..., str], role: str, system: str, user: str,
                         env: dict[str, str]) -> tuple[str, float, float]:
    """Acquire the concurrency guard, then call the provider and time it. Raises on guard timeout."""
    sem = _semaphore()
    q0 = time.monotonic()
    if not sem.acquire(timeout=_timeout_s() + 5.0):
        raise AdjudicatorUnavailable("rate_limit_acquire_timeout")
    queue_ms = (time.monotonic() - q0) * 1000.0
    try:
        c0 = time.monotonic()
        raw = prov(role, system, user, env)
        return raw, (time.monotonic() - c0) * 1000.0, queue_ms
    finally:
        sem.release()


def _run_coro_blocking(make_coro: Callable[[], Any], *, timeout_s: Optional[float] = None) -> str:
    """Run an async ``complete`` call to completion even when already inside a running event loop
    (the ``/api/v1/ws`` handler runs in one). A fresh thread gets its own loop via ``asyncio.run``.
    A per-call ``timeout_s`` is enforced via ``asyncio.wait_for`` plus a future-level backstop."""
    import asyncio
    import concurrent.futures

    async def _runner():
        if timeout_s:
            return await asyncio.wait_for(make_coro(), timeout=timeout_s)
        return await make_coro()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_runner())  # no loop running -> direct
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lambda: asyncio.run(_runner()))
        return fut.result(timeout=(timeout_s + 5.0) if timeout_s else None)


def _default_provider(model_role: str, system: str, user: str, env: dict[str, str]) -> str:
    """Real provider call. model_role ∈ {primary, fallback}. Returns raw text. Raises on failure.
    Keys come from the passed env dict OR os.environ (so the thin runtime wrapper never loads .env)."""
    from deeptutor.services.llm.factory import complete
    env = env or {}
    timeout_s = _timeout_s()
    if model_role == "primary":
        key = env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise AdjudicatorUnavailable("deepseek key absent")
        return _run_coro_blocking(lambda: complete(prompt=user, system_prompt=system, model="deepseek-chat",
                                                   api_key=key, max_retries=1), timeout_s=timeout_s)
    key = env.get("DASHSCOPE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        raise AdjudicatorUnavailable("dashscope key absent")
    return _run_coro_blocking(lambda: complete(prompt=user, system_prompt=system, model="qwen-plus",
                                              api_key=key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                                              binding="openai_compat", max_retries=1), timeout_s=timeout_s)


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\[.*\]", text or "", re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def adjudicate(packet: dict[str, Any], *, provider: Optional[Callable[..., str]] = None,
               env: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Run the LLM adjudication: DeepSeek primary, Qwen fallback, fail-closed. Hardened with a
    per-call timeout, a max-concurrent guard, a per-call latency/token/cost ledger, and a
    correlation_id (packet_hash + monotonic seq). Returns {model_used, fallback_used, failclosed,
    timed_out, correlation_id, latency_ms, provider_call_ledger, point_outputs:[...]}"""
    system, user = _adjudication_prompt(packet)
    prov = provider or _default_provider
    env = env if env is not None else {}
    correlation_id = f"{str(packet.get('packet_hash') or 'nohash')[:16]}-{next(_SEQ)}"
    model_used, fallback_used, failclosed, raw = None, False, False, ""
    timed_out = False
    ledger: list[dict[str, Any]] = []
    try:
        raw, call_ms, queue_ms = _call_provider_timed(prov, "primary", system, user, env)
        model_used = PRIMARY_MODEL
        ledger.append(_ledger_entry(PRIMARY_MODEL, "primary", system, user, raw, call_ms, queue_ms, ok=True))
    except Exception as e1:  # noqa: BLE001 - fail-closed is intentional
        timed_out = timed_out or _is_timeout(e1)
        ledger.append(_ledger_entry(PRIMARY_MODEL, "primary", system, user, "", None, None,
                                    ok=False, error=_error_kind(e1)))
        try:
            raw, call_ms, queue_ms = _call_provider_timed(prov, "fallback", system, user, env)
            model_used, fallback_used = FALLBACK_MODEL, True
            ledger.append(_ledger_entry(FALLBACK_MODEL, "fallback", system, user, raw, call_ms, queue_ms, ok=True))
        except Exception as e2:  # noqa: BLE001
            failclosed = True
            timed_out = timed_out or _is_timeout(e2)
            ledger.append(_ledger_entry(FALLBACK_MODEL, "fallback", system, user, "", None, None,
                                        ok=False, error=_error_kind(e2)))
    total_latency_ms = round(sum(e["call_latency_ms"] for e in ledger if e.get("call_latency_ms")), 1)
    parsed = _extract_json_array(raw) if not failclosed else []
    by_pid = {str(o.get("point_id")): o for o in parsed if isinstance(o, dict)}
    point_outputs = []
    for pid in packet["point_ids"]:
        o = by_pid.get(pid)
        if o and str(o.get("disposition")) in DISPOSITIONS:
            point_outputs.append({"point_id": pid, "disposition": str(o["disposition"]),
                                  "evidence_span": str(o.get("evidence_span") or "")[:200],
                                  "confidence": o.get("confidence"),
                                  "reasoning_summary": str(o.get("reasoning_summary") or "")[:160],
                                  "blocked_reason": o.get("blocked_reason")})
        else:
            # missing / malformed per-point output -> fail-closed to needs_review (never auto)
            point_outputs.append({"point_id": pid, "disposition": "needs_review", "evidence_span": "",
                                  "confidence": None, "reasoning_summary": "no_parseable_llm_output",
                                  "blocked_reason": "llm_output_missing"})
    return {"model_used": model_used, "fallback_used": fallback_used, "failclosed": failclosed,
            "timed_out": timed_out, "correlation_id": correlation_id,
            "latency_ms": total_latency_ms, "provider_call_ledger": ledger,
            "point_outputs": point_outputs}


# ----------------------------- deterministic validator (safety floor) -----------------------------

def validate(packet: dict[str, Any], adjudication: dict[str, Any], *, supply: bsl.BetaSupply) -> dict[str, Any]:
    """The LLM proposes; the deterministic validator disposes. Auto is allowed ONLY when the LLM
    accepts AND the deterministic matcher also auto-certifies AND the evidence_span is a real student
    answer span AND the point is a counted authority-backed point. Otherwise downgrade to needs_review.
    Guarantees false_positive=0 and source_mismatch=0 regardless of LLM behaviour."""
    qid = packet["question_id"]
    answer = packet["student_answer"]
    answer_norm = _norm(answer)
    counted = {s["point_id"] for s in packet["source_spec_list_policy_slices"]}
    list_pids = {s["point_id"] for s in packet["source_spec_list_policy_slices"] if "list_policy" in s}

    validated, fp_prevented, source_laundering_blocked = [], 0, 0
    false_positive = source_mismatch = 0
    for out in adjudication["point_outputs"]:
        pid = out["point_id"]
        llm_disp = out["disposition"]
        det = bsl.score_point(supply, qid, pid, answer)
        det_auto = bool(det.get("auto_shadow"))
        span = out.get("evidence_span") or ""
        span_in_answer = bool(_norm(span)) and _norm(span) in answer_norm

        final = llm_disp
        reason = None
        auto = False
        if llm_disp == "accept":
            if pid not in counted:
                final, reason = "needs_review", "point_not_in_release_candidate_registry"
            elif not det_auto:
                final, reason = "needs_review", "deterministic_matcher_rejected_llm_accept"
                fp_prevented += 1
            elif not span_in_answer:
                final, reason = "needs_review", "evidence_span_not_in_student_answer"
                source_laundering_blocked += 1
            elif pid in list_pids and det.get("path") == "list_rule_full_coverage_path" and not det_auto:
                final, reason = "needs_review", "list_rule_partial_blocked"
            else:
                final, auto = "accept", True
        # partial / reject / needs_review are taken as-is (never auto, finer than deterministic binary)
        validated.append({"point_id": pid, "llm_disposition": llm_disp, "final_disposition": final,
                          "auto_shadow_safe": auto, "deterministic_auto": det_auto,
                          "evidence_span_valid": span_in_answer, "downgrade_reason": reason,
                          "authority_kind": next((s["authority_kind"] for s in packet["source_spec_list_policy_slices"] if s["point_id"] == pid), None)})
    auto_n = sum(1 for v in validated if v["auto_shadow_safe"])
    review_n = len(validated) - auto_n
    return {"validated_points": validated, "auto_shadow_count": auto_n, "review_required_count": review_n,
            "false_positive": false_positive, "source_mismatch": source_mismatch,
            "false_positive_prevented_by_validator": fp_prevented,
            "source_laundering_blocked": source_laundering_blocked,
            "official_answer_as_source": False, "model_vote_as_source": False}


def build_lb_event_draft(packet: dict[str, Any], validation: dict[str, Any], student_id: str) -> dict[str, Any]:
    """Learning Brain PREVIEW event draft only. Never writes canonical learner truth; shadow/review
    points never raise mastery."""
    auto_pts = [v["point_id"] for v in validation["validated_points"] if v["auto_shadow_safe"]]
    return {"question_id": packet["question_id"], "student_id": student_id,
            "event_kind": "grading_evidence_event_draft", "preview_only": True,
            "auto_points": auto_pts, "review_points": [v["point_id"] for v in validation["validated_points"] if not v["auto_shadow_safe"]],
            "mastery_raised": False, "writeback_performed": False, "production_user_written": False,
            "canonical_truth_written": False, "human_reviewed": False, "qa_simulated": True,
            "personalization_context_pack_is_second_memory": False,
            "claim_authority": "llm_adjudication_validated_preview_not_production_truth"}


# ----------------------------- orchestrator (runtime entry) -----------------------------

def build_llm_adjudication_payload(question_id: str, student_id: str, student_answer: str, *,
                                   provider: Optional[Callable[..., str]] = None,
                                   env: Optional[dict[str, str]] = None,
                                   legacy_summary: dict[str, Any] | None = None,
                                   personalization_context_pack: dict[str, Any] | None = None,
                                   root=None) -> dict[str, Any]:
    """Runtime entry: build packet -> adjudicate (DeepSeek/Qwen) -> validate -> LB draft. Append-only,
    fail-closed (raises to the wrapper if registry unavailable). No production / canonical write."""
    registry = bsl.load_release_candidate_registry(root)  # fail-closed if malformed/missing
    supply = bsl.load_beta_supply(root)
    packet = build_grading_packet(question_id, student_answer, supply=supply, registry=registry,
                                  legacy_summary=legacy_summary,
                                  personalization_context_pack=personalization_context_pack)
    adjudication = adjudicate(packet, provider=provider, env=env)
    validation = validate(packet, adjudication, supply=supply)
    lb_draft = build_lb_event_draft(packet, validation, student_id)
    return {
        "authority": "luban_grading_engine_v1_llm_adjudication",
        "mode": "llm_adjudication_candidate",
        "schema_version": ADJUDICATOR_SCHEMA,
        "packet_hash": packet["packet_hash"],
        "registry_content_hash": registry.get("registry_content_hash"),
        "registry_status": registry.get("status"),
        "model_used": adjudication["model_used"], "fallback_used": adjudication["fallback_used"],
        "adjudicator_failclosed": adjudication["failclosed"],
        "adjudicator_timed_out": adjudication.get("timed_out", False),
        "correlation_id": adjudication.get("correlation_id"),
        "latency_ms": adjudication.get("latency_ms"),
        "provider_call_ledger": adjudication.get("provider_call_ledger", []),
        "hardening": {
            "per_call_timeout_s": _timeout_s(),
            "max_concurrent": _CONCURRENCY_SEM_N if _CONCURRENCY_SEM_N is not None else DEFAULT_MAX_CONCURRENT,
            "fallback_chain": [PRIMARY_MODEL, FALLBACK_MODEL],
            "fail_closed_on_double_failure": True,
            "cost_basis": "indicative_public_list_estimate_not_billing_truth",
            "no_production_write": True, "append_only": True,
        },
        "point_results": validation["validated_points"],
        "auto_shadow_count": validation["auto_shadow_count"],
        "review_required_count": validation["review_required_count"],
        "false_positive": validation["false_positive"], "source_mismatch": validation["source_mismatch"],
        "false_positive_prevented_by_validator": validation["false_positive_prevented_by_validator"],
        "source_laundering_blocked": validation["source_laundering_blocked"],
        "learning_brain_event_draft": lb_draft,
        "official_answer_as_source": False, "model_vote_as_source": False,
        "production_default": "off", "production_runtime_connected": False,
        "writeback_performed": False, "human_reviewed": False, "not_production_grade": True,
        "token_budget": packet["token_budget"],
    }


__all__ = ["AdjudicatorUnavailable", "build_grading_packet", "adjudicate", "validate",
           "build_lb_event_draft", "build_llm_adjudication_payload",
           "PRIMARY_MODEL", "FALLBACK_MODEL", "ADJUDICATOR_SCHEMA", "TOKEN_BUDGET"]
