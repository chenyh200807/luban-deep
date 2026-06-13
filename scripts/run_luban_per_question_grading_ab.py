#!/usr/bin/env python3
"""Per-question grading A/B (review-only): does the compiled atomic contract 摁死 over-credit?

Thin CLI over the fat skills
``deeptutor.services.construction_grading.per_question_grading_object`` (compile +
``build_grading_contract``, where G2 is wired on real data) and
``...per_question_grading_judge`` (over-credit gate).

The thesis (KnowQL Phase B): forcing the judge to adjudicate every atomic OFFICIAL point
separately reduces the measured ~20% over-credit (a high score while an official point is
missed). This harness was redesigned after a Codex adversarial review of the experiment
DESIGN found three fatal confounds; the fixes are baked in here:

* No exact-slice leakage — student answers are HAND-AUTHORED PARAPHRASES (no verbatim
  official slices) with semantic coverage labels (the fixtures file), so an arm cannot win
  by literal substring match.
* Fair arms — THREE arms, not two: ``arm_A0_freestyle`` (holistic), ``arm_A1_self_decompose``
  (same structured rigor: model decomposes the reference itself, per-point verdict + cite +
  coverage score), ``arm_B_atomic_contract`` (the PRE-COMPILED official checklist). The
  thesis is proven only if B beats A1 — not merely A0 — else the win is just "structured
  prompt beats freestyle".
* Honest metrics — PRIMARY over-credit = ``score − true_coverage > margin`` against the
  KNOWN label (not the verdict self-consistency gate, which is ~0 by construction for B);
  plus per-point false-hit rate (arm B), calibration MAE, per-answer-type strata, and a
  margin sensitivity sweep.

``--dry-run`` (default; no LLM key) runs a LABEL ORACLE end-to-end (honest score =
true_coverage) to validate plumbing — it cannot show the thesis (the oracle never
over-credits; an LLM freestyle judge is what does). ``--live`` runs the real LLM judge for
all three arms (needs an LLM key, billable) and reports each arm's over-credit rate.

Nothing here writes canonical truth, official scores, a DB, or a production default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any, Callable
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from run_luban_per_question_grading_object_compile import (  # noqa: E402  (sys.path set above)
    DEFAULT_BOOK_DIR,
    DEFAULT_EXAM_ROOT,
    _load_textbook_chunks,
    compile_selected,
)

from deeptutor.services.construction_grading.per_question_grading_judge import (  # noqa: E402
    CONTRADICTION,
    HIT,
    MISS,
    OVER_CREDIT_GAP_MARGIN,
    PARTIAL,
    detect_over_credit,
)
from deeptutor.services.construction_grading.per_question_grading_object import (  # noqa: E402
    build_grading_contract,
    validate_grading_contract,
)

DEFAULT_FIXTURES = REPO / "deeptutor/services/construction_grading/fixtures/per_question_grading_ab_fixtures.json"
DEFAULT_OUT_DIR = REPO / "artifacts/luban_grading_artifacts/per_question_grading_ab_20260613"
ARM_A0 = "arm_A0_freestyle"
ARM_A1 = "arm_A1_self_decompose"
ARM_B = "arm_B_atomic_contract"
# RAG-grounded arms (the existing production grading lane uses kb_v5 retrieval):
#  * RAG_ONLY — open-world, stem + retrieved KB, NO official answer (question not in bank);
#  * RAG_REF  — production-faithful, official reference + retrieved KB grounding, holistic.
ARM_RAG_ONLY = "arm_RAG_only_openworld"
ARM_RAG_REF = "arm_RAG_plus_reference"
ARMS = (ARM_A0, ARM_A1, ARM_B, ARM_RAG_ONLY, ARM_RAG_REF)
_RAG_ARMS = frozenset({ARM_RAG_ONLY, ARM_RAG_REF})
MARGIN_SWEEP = (0.05, 0.1, 0.15, 0.2)


# ── ground truth from hand-authored labels ───────────────────────────────────


def _true_coverage(answer: dict[str, Any], total: int) -> float:
    """Honest target score: covered points + half credit for partial, over total."""
    if total == 0:
        return 0.0
    covered = len(answer.get("covered_point_ids") or [])
    partial = len(answer.get("partial_point_ids") or [])
    return (covered + 0.5 * partial) / total


def _labeled_verdicts(answer: dict[str, Any]) -> dict[str, str]:
    verdicts: dict[str, str] = {}
    for pid in answer.get("covered_point_ids") or []:
        verdicts[pid] = HIT
    for pid in answer.get("partial_point_ids") or []:
        verdicts[pid] = PARTIAL
    for pid in answer.get("missing_point_ids") or []:
        verdicts[pid] = MISS
    for pid in answer.get("contradiction_point_ids") or []:
        verdicts[pid] = CONTRADICTION
    return verdicts


def _validate_fixture(answer: dict[str, Any], contract: dict[str, Any]) -> None:
    """Fail closed on an authoring error: labels must partition the contract exactly."""
    cpts = {sp["point_id"] for sp in contract["scoring_points"]}
    buckets = [answer.get(k) or [] for k in
               ("covered_point_ids", "missing_point_ids", "partial_point_ids", "contradiction_point_ids")]
    flat = [p for b in buckets for p in b]
    labeled = set(flat)
    if len(flat) != len(labeled):
        raise SystemExit(f"fixture {answer.get('label')}: duplicate point_id across buckets")
    if labeled - cpts:
        raise SystemExit(f"fixture {answer.get('label')}: unknown point_ids {labeled - cpts}")
    if cpts - labeled:
        raise SystemExit(f"fixture {answer.get('label')}: unlabeled point_ids {cpts - labeled}")


# ── judge prompts (the three arms) ────────────────────────────────────────────


def _arm_a0_messages(*, stem: str, official_answer: str, student_answer: str) -> list[dict[str, str]]:
    payload = {
        "task": "你是一级建造师案例题阅卷官。对照官方参考答案给学生作答打分。",
        "stem": stem,
        "official_reference_answer": official_answer,
        "student_answer": student_answer,
        "instruction": "只输出 JSON: {\"score_pct\": 0..1 的小数, \"reason\": \"简短\"}。",
    }
    return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def _arm_a1_messages(*, stem: str, official_answer: str, student_answer: str) -> list[dict[str, str]]:
    """Fair structured baseline: same rigor as B (per-requirement verdict + cite + coverage
    score), but the model decomposes the OFFICIAL REFERENCE ANSWER itself rather than being
    handed the pre-compiled checklist. Isolates 'compiled checklist' from 'be structured'."""
    payload = {
        "task": "你是一级建造师案例题阅卷官。",
        "stem": stem,
        "official_reference_answer": official_answer,
        "student_answer": student_answer,
        "instruction": (
            "请你自己把官方参考答案拆成若干采分要点(requirement);对每个要点判断学生是否答到"
            "verdict∈{hit,partial,miss,contradiction},命中(hit)必须在 evidence_span 引用学生作答里的逐字证据。"
            "教材知识只供你理解题意,不能当判分依据。score_pct = 命中(hit)要点 / 总要点。"
            "只输出 JSON: {\"requirements\":[{\"requirement\":\"..\",\"verdict\":\"..\",\"evidence_span\":\"..\"}],"
            "\"score_pct\":0..1}。"
        ),
    }
    return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def _arm_b_messages(*, contract: dict[str, Any], student_answer: str) -> list[dict[str, str]]:
    checklist = [
        {"point_id": sp["point_id"], "official_slice": sp.get("official_slice"),
         "sub_type": sp.get("sub_type")}
        for sp in contract["scoring_points"]
    ]
    payload = {
        "task": "你是一级建造师案例题阅卷官。下面是该题官方采分点清单(每个都是官方答案逐字原子点)。",
        "stem": contract.get("stem"),
        "scoring_points": checklist,
        "supporting_citations_note": "教材引证仅供理解,不能当官方对错依据(G2: 引证通道,非评分通道)。",
        "student_answer": student_answer,
        "output_contract": contract["output_contract"],
        "instruction": (
            "你必须对每个 point_id 逐一裁决 verdict∈{hit,partial,miss,contradiction};"
            "命中(hit)必须在 evidence_span 引用学生作答里的逐字证据(学生用同义改写也算 hit,但必须真的答到该点语义)。"
            "score_pct = 命中(hit)点数 / 总点数。"
            "只输出 JSON: {\"verdicts\":[{\"point_id\":\"..\",\"verdict\":\"..\",\"evidence_span\":\"..\"}],"
            "\"score_pct\":0..1}。"
        ),
    }
    return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def _rag_chunk_texts(retrieval: dict[str, Any], *, limit: int = 6) -> list[str]:
    out: list[str] = []
    for c in (retrieval.get("chunks") or [])[:limit]:
        if isinstance(c, dict):
            txt = str(c.get("content") or "").strip()
            if txt:
                out.append(txt[:600])
    return out


def _arm_rag_only_messages(*, stem: str, rag_chunks: list[str], student_answer: str) -> list[dict[str, str]]:
    """Open-world RAG grading: no official answer, only stem + kb_v5-retrieved knowledge —
    how the RAG lane grades a question that is NOT in the bank."""
    payload = {
        "task": "你是一级建造师案例题阅卷官。本题没有标准答案,请依据下面检索到的教材/规范知识给学生作答打分。",
        "stem": stem,
        "retrieved_knowledge": rag_chunks,
        "student_answer": student_answer,
        "instruction": "依据检索知识判断学生作答覆盖了多少应得要点,只输出 JSON: {\"score_pct\": 0..1, \"reason\": \"简短\"}。",
    }
    return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def _arm_rag_ref_messages(*, stem: str, official_answer: str, rag_chunks: list[str], student_answer: str) -> list[dict[str, str]]:
    """Production-faithful RAG grading: official reference answer + kb_v5-retrieved grounding,
    holistic score (mirrors _grade_one_case_v1's reference tier + RAG grounding context)."""
    payload = {
        "task": "你是一级建造师案例题阅卷官。对照官方参考答案,并参考检索到的教材/规范知识,给学生作答打分。",
        "stem": stem,
        "official_reference_answer": official_answer,
        "retrieved_knowledge": rag_chunks,
        "student_answer": student_answer,
        "instruction": "只输出 JSON: {\"score_pct\": 0..1 的小数, \"reason\": \"简短\"}。",
    }
    return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def _parse_json_block(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no JSON object in judge output: {text[:160]!r}")
    return json.loads(match.group(0))


# ── judges: label oracle (dry-run) and the real LLM ───────────────────────────


def _official_answer_text(contract: dict[str, Any]) -> str:
    return "\n".join(sp.get("official_slice") or "" for sp in contract["scoring_points"])


def _make_label_oracle(total_by_q: dict[str, int]) -> Callable[..., dict[str, Any]]:
    """Honest oracle for dry-run: score = true_coverage; arm B emits the labeled verdicts.
    Cannot over-credit — proves PLUMBING, not the thesis (an LLM freestyle judge is what
    over-credits)."""
    def judge(*, arm: str, contract: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
        total = len(contract["scoring_points"])
        verdicts = _labeled_verdicts(answer) if arm == ARM_B else {}
        score = _true_coverage(answer, total)
        return {"score_pct": score, "verdicts": verdicts, "oracle": True}
    return judge


def _load_kbv5_retriever(top_k: int = 6):
    """The kb_v5 search_chunks_v2 retriever the production RAG grading lane uses
    (loaded lazily from the case-question eval module, which configures the channel)."""
    import importlib.util

    path = REPO / "scripts" / "run_luban_rich_leaf_case_question_eval.py"
    spec = importlib.util.spec_from_file_location("rl_case_eval_for_ab", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._kbv5_retriever(top_k)


_JUDGE_SYSTEM_PROMPT = "你是严谨的一级建造师案例题阅卷官。只输出题目要求的 JSON,不要多余文字。"


def _stream_chat(*, base_url: str, api_key: str, model: str, messages: list[dict[str, str]],
                 max_tokens: int = 2200, temperature: float = 0.0, timeout_s: float = 120.0) -> dict[str, Any]:
    """One streaming chat call → content + token usage + total latency + TTFT.

    Uses the OpenAI-compatible streaming SSE with ``stream_options.include_usage`` so the
    final chunk carries the token usage. TTFT = time from request to the FIRST content
    token; latency = time to the full completion. (Sequential calls only — no concurrency
    contention — so the latency/TTFT numbers are clean.)"""
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
        # Force strict JSON (the 24-point arm B verdict list must not be decorated/truncated).
        "response_format": {"type": "json_object"},
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    ttft_ms: float | None = None
    parts: list[str] = []
    usage: dict[str, Any] = {}
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(chunk.get("usage"), dict):
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if choices:
                delta = (choices[0].get("delta") or {}).get("content") or ""
                if delta:
                    if ttft_ms is None:
                        ttft_ms = round((time.monotonic() - started) * 1000, 2)
                    parts.append(delta)
    latency_ms = round((time.monotonic() - started) * 1000, 2)
    return {
        "content": "".join(parts),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "latency_ms": latency_ms,
        "ttft_ms": ttft_ms if ttft_ms is not None else latency_ms,
    }


async def _make_llm_judge(model: str | None, *, with_rag: bool):
    from deeptutor.services.llm import get_llm_config  # canonical single-authority LLM config

    cfg = get_llm_config()
    base_url = str(getattr(cfg, "base_url", "") or "")
    api_key = str(getattr(cfg, "api_key", "") or "")
    use_model = model or str(getattr(cfg, "model", "") or "")
    if not (base_url and api_key and use_model):
        raise SystemExit("LLM config incomplete (need base_url/api_key/model) — cannot run --live")

    retriever = _load_kbv5_retriever() if with_rag else None
    rag_cache: dict[str, list[str]] = {}

    def _retrieve(qid: str, stem: str) -> list[str]:
        if retriever is None:
            return []
        if qid not in rag_cache:
            res = retriever(stem[:400])
            rag_cache[qid] = _rag_chunk_texts(res) if res.get("status") == "completed" else []
        return rag_cache[qid]

    async def judge(*, arm: str, contract: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
        official = _official_answer_text(contract)
        stem = str(contract.get("stem") or "")
        student = str(answer.get("student_answer") or "")
        if arm == ARM_A0:
            messages = _arm_a0_messages(stem=stem, official_answer=official, student_answer=student)
        elif arm == ARM_A1:
            messages = _arm_a1_messages(stem=stem, official_answer=official, student_answer=student)
        elif arm == ARM_RAG_ONLY:
            chunks = _retrieve(str(contract.get("question_id")), stem)
            messages = _arm_rag_only_messages(stem=stem, rag_chunks=chunks, student_answer=student)
        elif arm == ARM_RAG_REF:
            chunks = _retrieve(str(contract.get("question_id")), stem)
            messages = _arm_rag_ref_messages(stem=stem, official_answer=official, rag_chunks=chunks, student_answer=student)
        else:
            messages = _arm_b_messages(contract=contract, student_answer=student)
        full_messages = [{"role": "system", "content": _JUDGE_SYSTEM_PROMPT}, *messages]
        # Resilient: neither a malformed JSON response NOR a transient network/stream stall
        # may kill a 300-call run. Retry up to 3×, then record a parse_error row (score 0,
        # no verdicts) so the run completes honestly. A stalled stream is bounded by the
        # short per-call socket timeout, not the 120s default.
        last_call: dict[str, Any] = {}
        data: dict[str, Any] | None = None
        for _attempt in range(3):
            try:
                last_call = await asyncio.to_thread(
                    _stream_chat, base_url=base_url, api_key=api_key, model=use_model,
                    messages=full_messages, timeout_s=60.0,
                )
                data = _parse_json_block(last_call["content"])
                break
            except (TimeoutError, OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
                data = None
        if data is None:
            return {
                "score_pct": 0.0, "verdicts": {}, "oracle": False, "parse_error": True,
                "prompt_tokens": last_call.get("prompt_tokens"),
                "completion_tokens": last_call.get("completion_tokens"),
                "total_tokens": last_call.get("total_tokens"),
                "latency_ms": last_call.get("latency_ms"),
                "ttft_ms": last_call.get("ttft_ms"),
            }
        verdicts = {
            str(v.get("point_id")): str(v.get("verdict"))
            for v in (data.get("verdicts") or [])
            if v.get("point_id")
        }
        return {
            "score_pct": float(data.get("score_pct") or 0.0),
            "verdicts": verdicts,
            "oracle": False,
            "prompt_tokens": last_call["prompt_tokens"],
            "completion_tokens": last_call["completion_tokens"],
            "total_tokens": last_call["total_tokens"],
            "latency_ms": last_call["latency_ms"],
            "ttft_ms": last_call["ttft_ms"],
        }
    return judge


# ── run + metrics ─────────────────────────────────────────────────────────────


def _false_hit_rate(verdicts: dict[str, str], answer: dict[str, Any]) -> float | None:
    """Arm-B diagnostic: fraction of truly missing/contradicted points the arm judged HIT.
    None when the arm reports no per-point verdicts on our point_ids (A0/A1)."""
    if not verdicts:
        return None
    unmet = set(answer.get("missing_point_ids") or []) | set(answer.get("contradiction_point_ids") or [])
    if not unmet:
        return None
    false_hits = sum(1 for pid in unmet if verdicts.get(pid) == HIT)
    return false_hits / len(unmet)


async def _run(objects, fixtures: dict[str, Any], judge, *, gap_margin: float, trials: int,
               concurrency: int = 1) -> dict[str, Any]:
    contracts: dict[str, dict[str, Any]] = {}
    for obj in objects:
        qid = obj["question_id"]
        contract = build_grading_contract(obj)
        blockers = validate_grading_contract(contract)
        if blockers:
            raise SystemExit(f"contract invalid for {qid}: {blockers}")
        contracts[qid] = contract
    work: list[tuple[int, str, dict[str, Any], float, str]] = []
    for trial in range(trials):
        for obj in objects:
            qid = obj["question_id"]
            total = len(contracts[qid]["scoring_points"])
            for answer in fixtures.get(qid) or []:
                _validate_fixture(answer, contracts[qid])
                true_cov = round(_true_coverage(answer, total), 4)
                for arm in ARMS:
                    work.append((trial, qid, answer, true_cov, arm))

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(item: tuple[int, str, dict[str, Any], float, str]) -> dict[str, Any]:
        trial, qid, answer, true_cov, arm = item
        contract = contracts[qid]
        async with sem:
            result = judge(arm=arm, contract=contract, answer=answer)
            if asyncio.iscoroutine(result):
                result = await result
        score = round(float(result["score_pct"]), 4)
        verdicts = result.get("verdicts") or {}
        self_consistency = detect_over_credit(
            score_pct=score, point_verdicts=verdicts, contract=contract, gap_margin=gap_margin,
        )
        return {
            "trial": trial,
            "question_id": qid,
            "answer_label": answer.get("label"),
            "answer_type": answer.get("answer_type"),
            "arm": arm,
            "score_pct": score,
            "true_coverage": true_cov,
            "score_coverage_gap": round(score - true_cov, 4),
            "ground_truth_over_credit": bool(score - true_cov > gap_margin),
            "calibration_abs_error": round(abs(score - true_cov), 4),
            "false_hit_rate": _false_hit_rate(verdicts, answer),
            "verdict_self_inconsistency": self_consistency["over_credit"],
            "oracle": result.get("oracle", False),
            "parse_error": result.get("parse_error", False),
            "prompt_tokens": result.get("prompt_tokens"),
            "completion_tokens": result.get("completion_tokens"),
            "total_tokens": result.get("total_tokens"),
            "latency_ms": result.get("latency_ms"),
            "ttft_ms": result.get("ttft_ms"),
        }

    rows = list(await asyncio.gather(*[_one(w) for w in work]))
    report = _summarize(rows, gap_margin=gap_margin, trials=trials)
    report["concurrency"] = concurrency
    report["latency_ttft_note"] = (
        "latency_ms/ttft_ms measured under concurrency>1 are CONTENDED (upper bound); "
        "run --concurrency 1 for isolated per-call latency"
        if concurrency > 1 else "latency_ms/ttft_ms are isolated per-call (sequential)"
    )
    return report


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [r for r in rows if r.get(key) is not None]
    return round(sum(1 for r in vals if r[key]) / len(vals), 4) if vals else None


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _dist(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    """mean / p50 / p95 / max of a per-call cost metric (None entries skipped)."""
    vals = sorted(float(r[key]) for r in rows if r.get(key) is not None)
    if not vals:
        return None
    def _pct(p: float) -> float:
        idx = min(len(vals) - 1, int(round(p * (len(vals) - 1))))
        return round(vals[idx], 2)
    return {"mean": round(sum(vals) / len(vals), 2), "p50": _pct(0.5), "p95": _pct(0.95),
            "max": round(vals[-1], 2), "n": len(vals)}


def _mean_std(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "std": None}
    return {"mean": round(statistics.fmean(values), 4),
            "std": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0}


def _summarize(rows: list[dict[str, Any]], *, gap_margin: float, trials: int) -> dict[str, Any]:
    by_arm: dict[str, Any] = {}
    answer_types = sorted({r["answer_type"] for r in rows})
    trial_ids = sorted({r["trial"] for r in rows})
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        riskful = [r for r in arm_rows if r["true_coverage"] < 1.0]
        # per-trial metric → mean ± std across trials (the variance the user asked to crush)
        oc_per_trial = [
            _rate([r for r in riskful if r["trial"] == t], "ground_truth_over_credit")
            for t in trial_ids
        ]
        mae_per_trial = [
            _mean([r for r in arm_rows if r["trial"] == t], "calibration_abs_error")
            for t in trial_ids
        ]
        by_arm[arm] = {
            "rows": len(arm_rows),
            "riskful_rows_per_trial": len(riskful) // max(len(trial_ids), 1),
            "over_credit_rate": _mean_std([v for v in oc_per_trial if v is not None]),
            "calibration_mae": _mean_std([v for v in mae_per_trial if v is not None]),
            "false_hit_rate_mean": _mean(arm_rows, "false_hit_rate"),
            "over_credit_rate_by_answer_type": {
                t: _rate([r for r in riskful if r["answer_type"] == t], "ground_truth_over_credit")
                for t in answer_types
            },
            "cost": {
                "total_tokens": _dist(arm_rows, "total_tokens"),
                "prompt_tokens": _dist(arm_rows, "prompt_tokens"),
                "completion_tokens": _dist(arm_rows, "completion_tokens"),
                "latency_ms": _dist(arm_rows, "latency_ms"),
                "ttft_ms": _dist(arm_rows, "ttft_ms"),
            },
        }
    return {
        "schema": "luban_per_question_grading_ab.v3",
        "review_only": True,
        "trials": trials,
        "primary_metric": "calibration_mae (mean±std across trials) — most stable; over_credit_rate noisy at small N",
        "default_margin": gap_margin,
        "thesis": "arm_B_atomic_contract 校准最优 (calibration_mae 最低),over-credit 不高于 baseline",
        "by_arm": by_arm,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-root", type=Path, default=DEFAULT_EXAM_ROOT)
    parser.add_argument("--book-dir", type=Path, default=DEFAULT_BOOK_DIR)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--live", action="store_true", help="use the real LLM judge (needs an LLM key)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--margin", type=float, default=OVER_CREDIT_GAP_MARGIN)
    parser.add_argument("--trials", type=int, default=1,
                        help="repeat the full pass N times → mean±std on the metrics (crush variance)")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="concurrent LLM calls (>1 = throughput; latency/ttft then contended)")
    parser.add_argument("--no-rag", action="store_true",
                        help="skip the kb_v5 RAG-grounded arms (faster; live only)")
    args = parser.parse_args()

    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8")).get("fixtures") or {}
    textbook_chunks = _load_textbook_chunks(args.book_dir)
    objects = compile_selected(exam_root=args.exam_root, textbook_chunks=textbook_chunks)

    if args.live:
        judge = asyncio.run(_make_llm_judge(args.model, with_rag=not args.no_rag))
        mode = "live_llm"
    else:
        judge = _make_label_oracle({o["question_id"]: o["scoring_point_count"] for o in objects})
        mode = "dry_run_label_oracle"

    report = asyncio.run(_run(objects, fixtures, judge, gap_margin=args.margin,
                              trials=args.trials, concurrency=args.concurrency))
    report["mode"] = mode
    report["questions_compiled"] = [o["question_id"] for o in objects]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"per_question_grading_ab_{mode}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"mode": mode, "by_arm": report["by_arm"],
                      "questions": report["questions_compiled"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
