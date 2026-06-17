#!/usr/bin/env python3
"""Run the requested three-arm case-grading comparison.

Arms:
  1. original RAG/ref         -> legacy CaseGradingSkillKernel with reference evidence rows
  2. Nexus V1, no KnowQL      -> rubric_grader_v1, rubric extracted from reference answer
  3. Nexus V1 + KnowQL        -> rubric_grader_v1, compiled rubric + LubanContextPack + learner evidence

This is a benchmark harness only. It does not flip production defaults, write DB,
write canonical learner truth, or make RAG/learner evidence a scoring authority.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.construction_grading.compiled_context import build_luban_context_pack
from deeptutor.services.construction_grading.rubric_grader_v1 import (
    HIT,
    PARTIAL,
    extract_rubric_from_reference_async,
    grade_with_batch_judge_async,
    render_case_rubric_feedback,
)

from scripts.poc_luban_case_grading_three_arms import (
    DEFAULT_FIXTURE,
    _case_group_tags,
    _compact,
    _precision_recall,
    _question_row,
    _rag_evidence_rows,
    _result_terms,
    _score_arm,
    _token_proxy,
    compile_kernel_scoring_points,
    extract_required_terms,
    gold_from_ledger,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "luban_knowql_nexus_three_arm_ab"

ARM_RAG_REF = "rag_ref"
ARM_NEXUS_V1_NO_KNOWQL = "nexus_v1_no_knowql"
ARM_NEXUS_V1_KNOWQL = "nexus_v1_knowql"
REQUESTED_ARMS = (ARM_RAG_REF, ARM_NEXUS_V1_NO_KNOWQL, ARM_NEXUS_V1_KNOWQL)

CompleteFn = Callable[..., Awaitable[str]]


def _avg(values: list[float]) -> float | None:
    return round(float(mean(values)), 4) if values else None


def _f1(precision: float, recall: float) -> float:
    return round((2 * precision * recall) / (precision + recall), 4) if precision + recall else 0.0


def semantic_understanding_score(
    *,
    pred_score: float,
    gold_score: float,
    max_score: float,
    point_precision: float,
    point_recall: float,
    hallucination: bool,
) -> float:
    """Single semantic-quality scalar for comparison.

    It combines score alignment with point-level discrimination. Over-credit hurts precision,
    missed points hurt recall, and unsupported terms get a small hallucination penalty.
    """
    denominator = max(float(max_score or 0), 1.0)
    score_alignment = max(0.0, 1.0 - abs(float(pred_score) - float(gold_score)) / denominator)
    point_alignment = _f1(float(point_precision), float(point_recall))
    penalty = 0.15 if hallucination else 0.0
    return round(max(0.0, min(1.0, 0.5 * score_alignment + 0.5 * point_alignment - penalty)), 4)


def _load_env() -> None:
    for env_path in (PROJECT_ROOT / ".env",):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_fixture(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("suite") != "luban_case_grading_golden_v1":
        raise ValueError("unexpected fixture suite")
    return [case for case in list(payload.get("cases") or []) if isinstance(case, dict)]


def _case_reference_answer(case: dict[str, Any]) -> str:
    parts = [
        str(case.get("official_answer") or "").strip(),
        str(case.get("official_analysis") or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def _compiled_point_policy(case: dict[str, Any], source_point_id: str) -> str:
    point = next(
        (
            p for p in list(case.get("gold_scoring_points") or [])
            if str(p.get("point_id") or "") == source_point_id
        ),
        {},
    )
    text = " ".join(
        str(point.get(key) or "")
        for key in ("label", "official_basis", "list_rule")
    )
    if "近义不算" in text or "规范术语原文" in text or "必须写出" in text:
        return "exact_required"
    if "列举" in text or "应得分项" in text:
        return "list"
    if re.search(r"计算|价款|工期|费用|kg|万元|天|=", text, flags=re.I):
        return "calc"
    return "qualitative"


def _compiled_points_for_v1(case: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for item in compile_kernel_scoring_points(case):
        criterion = str(item.get("criterion") or "")
        source_point_id, _, tail = criterion.partition("::")
        text = tail or criterion
        if not text:
            continue
        score = float(item.get("score") or 0)
        points.append(
            {
                "point_id": criterion,
                "text": text,
                "score": score,
                "policy": _compiled_point_policy(case, source_point_id),
                "required_terms": list(item.get("keywords") or []),
                "source_qid": str(case.get("case_id") or ""),
                "rubric_provenance": "compiled_rubric",
                "authority_source": "official_answer",
            }
        )
    return points


def _normalize_extracted_points(points: list[dict[str, Any]], *, case_id: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, point in enumerate(points, start=1):
        if not isinstance(point, dict):
            continue
        text = str(point.get("text") or point.get("knowledge_point") or "").strip()
        if not text:
            continue
        normalized.append(
            {
                "point_id": str(point.get("point_id") or f"ref::{case_id}::{index}"),
                "text": text,
                "score": float(point.get("score") or 1.0),
                "policy": str(point.get("policy") or "qualitative"),
                "required_terms": list(point.get("required_terms") or []),
                "source_qid": case_id,
                "rubric_provenance": "on_the_fly_reference",
                "authority_source": "official_answer",
            }
        )
    return normalized


def _gold_known_terms(case: dict[str, Any]) -> set[str]:
    return {
        term
        for point in list(case.get("gold_scoring_points") or [])
        for term in extract_required_terms(point)
    }


def _term_overlaps(candidate: Any, gold_term: Any) -> bool:
    cand = _compact(candidate)
    gold = _compact(gold_term)
    if not cand or not gold:
        return False
    if cand == gold:
        return True
    if len(cand) >= 2 and cand in gold:
        return True
    return len(gold) >= 2 and gold in cand


def _matched_gold_terms(candidate_terms: set[str], gold_terms: set[str]) -> set[str]:
    return {
        gold_term
        for gold_term in gold_terms
        if any(_term_overlaps(candidate, gold_term) for candidate in candidate_terms)
    }


def _unmatched_meaningful_terms(candidate_terms: set[str], known_terms: set[str]) -> list[str]:
    unmatched: list[str] = []
    for candidate in sorted(candidate_terms):
        compact = _compact(candidate)
        if len(compact) < 2:
            continue
        if not any(_term_overlaps(candidate, known) for known in known_terms):
            unmatched.append(candidate)
    return unmatched


def _gold_point_by_term(case: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for point in list(case.get("gold_scoring_points") or []):
        point_id = str(point.get("point_id") or "")
        for term in extract_required_terms(point):
            compact = _compact(term)
            if compact and point_id:
                mapping[compact] = point_id
    return mapping


def _event_hit_terms(event: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    for point in list(event.get("scoring_points") or []):
        if not isinstance(point, dict) or point.get("hit") not in {HIT, PARTIAL}:
            continue
        values = [str(term) for term in list(point.get("required_terms") or []) if str(term).strip()]
        if not values and str(point.get("knowledge_point") or "").strip():
            values = [str(point.get("knowledge_point"))]
        terms.update(values)
    return terms


def _event_predicted_points(event: dict[str, Any], case: dict[str, Any]) -> set[str]:
    term_to_point = _gold_point_by_term(case)
    gold_point_ids = {
        str(point.get("point_id") or "")
        for point in list(case.get("gold_scoring_points") or [])
        if str(point.get("point_id") or "")
    }
    predicted: set[str] = set()
    for point in list(event.get("scoring_points") or []):
        if not isinstance(point, dict) or point.get("hit") not in {HIT, PARTIAL}:
            continue
        point_id = str(point.get("point_id") or "")
        if "::" in point_id:
            source_id = point_id.split("::", 1)[0]
            if source_id in gold_point_ids:
                predicted.add(source_id)
                continue
        for term in list(point.get("required_terms") or []) or [point.get("knowledge_point")]:
            for compact_gold, mapped in term_to_point.items():
                if _term_overlaps(term, compact_gold):
                    predicted.add(mapped)
    return predicted


def _legacy_predicted_points(result: Any, case: dict[str, Any]) -> set[str]:
    result_terms = _result_terms(result)
    predicted: set[str] = set()
    for point in list(case.get("gold_scoring_points") or []):
        point_id = str(point.get("point_id") or "")
        terms = set(extract_required_terms(point))
        if point_id and terms and _matched_gold_terms(result_terms, terms):
            predicted.add(point_id)
    return predicted


def _learner_context(case: dict[str, Any], sample: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    weak_rows = [
        row for row in list(gold.get("point_rows") or [])
        if float(row.get("gold_score") or 0) < float(row.get("max_score") or 0)
    ]
    recent_evidence = [
        {
            "question_id": case.get("case_id"),
            "point_id": row.get("point_id"),
            "miss_reasons": row.get("injected_error_codes") or [row.get("ledger_hit")],
        }
        for row in weak_rows[:5]
    ]
    return {
        "personalization_context_pack": {
            "schema_version": "benchmark_personalization_context_pack.v1",
            "learner_id": str(sample.get("student_id") or ""),
            "weak_point_count": len(weak_rows),
            "weak_points": [row.get("point_id") for row in weak_rows[:5]],
        },
        "recent_evidence": recent_evidence,
        "active_training_intent": "case_point_repair" if weak_rows else "maintain_case_precision",
    }


def _knowql_context_pack(case: dict[str, Any], compiled_points: list[dict[str, Any]], learner_context: dict[str, Any]) -> dict[str, Any]:
    pack = build_luban_context_pack(
        resolution={
            "status": "candidate",
            "question_id": case.get("case_id"),
            "question_type": "case",
            "stem": case.get("stem"),
            "answer_key": case.get("official_answer"),
            "registry_status": "candidate",
            "rubric": {"scoring_points": compiled_points},
            "source_refs": [{"kind": "golden_fixture", "case_id": case.get("case_id")}],
            "is_historical_exam": True,
        },
        retrieval_sources=_rag_evidence_rows(case),
        learner_context=learner_context,
        supply_bundle_hash="benchmark_local_fixture",
    )
    return pack.to_dict()


def _row_common(
    *,
    case: dict[str, Any],
    sample: dict[str, Any],
    gold: dict[str, Any],
    arm: str,
    pred_score: float,
    max_score: float,
    predicted_points: set[str],
    predicted_terms: set[str],
    hallucinated_terms: list[str],
    latency_ms: float,
    token_proxy: int,
    extra: dict[str, Any],
) -> dict[str, Any]:
    point_precision, point_recall = _precision_recall(predicted_points, set(gold["positive_points"]))
    term_precision, term_recall = _precision_recall(predicted_terms, set(gold["positive_terms"]))
    score = semantic_understanding_score(
        pred_score=pred_score,
        gold_score=float(gold["score"]),
        max_score=max_score,
        point_precision=point_precision,
        point_recall=point_recall,
        hallucination=bool(hallucinated_terms),
    )
    return {
        "case_id": case.get("case_id"),
        "sample_id": sample.get("student_id"),
        "archetype": sample.get("archetype"),
        "arm": arm,
        "gold_score": gold["score"],
        "pred_score": round(float(pred_score), 4),
        "max_score": round(float(max_score or case.get("max_score") or 0), 4),
        "score_delta": round(float(pred_score) - float(gold["score"]), 4),
        "point_precision": round(point_precision, 4),
        "point_recall": round(point_recall, 4),
        "point_f1": _f1(point_precision, point_recall),
        "term_precision": round(term_precision, 4),
        "term_recall": round(term_recall, 4),
        "semantic_understanding_score": score,
        "hallucination": bool(hallucinated_terms),
        "hallucinated_terms": hallucinated_terms,
        "token_proxy": int(token_proxy),
        "latency_ms": round(float(latency_ms), 4),
        "case_group_tags": _case_group_tags(case),
        "predicted_points": sorted(predicted_points),
        "gold_positive_points": sorted(gold["positive_points"]),
        "predicted_terms": sorted(predicted_terms),
        "gold_positive_terms": sorted(gold["positive_terms"]),
        **extra,
    }


def _score_rag_ref(case: dict[str, Any], sample: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    evidence_rows = _rag_evidence_rows(case)
    result, latency_ms = _score_arm(
        arm=ARM_RAG_REF,
        case=case,
        sample=sample,
        grading_key=None,
        evidence_rows=evidence_rows,
    )
    predicted_points = _legacy_predicted_points(result, case)
    result_terms = _result_terms(result)
    predicted_terms = _matched_gold_terms(result_terms, set(gold["positive_terms"]))
    known_terms = _gold_known_terms(case)
    hallucinated = _unmatched_meaningful_terms(result_terms, known_terms)
    return _row_common(
        case=case,
        sample=sample,
        gold=gold,
        arm=ARM_RAG_REF,
        pred_score=float(result.score_awarded),
        max_score=float(result.max_score or case.get("max_score") or 0),
        predicted_points=predicted_points,
        predicted_terms=predicted_terms,
        hallucinated_terms=hallucinated,
        latency_ms=latency_ms,
        token_proxy=_token_proxy(_question_row(case)) + _token_proxy(evidence_rows),
        extra={
            "score_authority": "legacy_rag_ref_kernel",
            "rag_ref_context_used": bool(evidence_rows),
            "compiled_rubric_used": False,
            "knowql_context_pack_attached": False,
            "learner_evidence_attached": False,
            "evidence_ref_count": len(getattr(result, "evidence_refs", []) or []),
            "ttft_status": "not_exercised_non_streaming_core",
        },
    )


async def _score_v1(
    *,
    arm: str,
    case: dict[str, Any],
    sample: dict[str, Any],
    gold: dict[str, Any],
    rubric_points: list[dict[str, Any]],
    complete_fn: CompleteFn,
    api_key: str,
    model: str,
    compiled_rubric_used: bool,
    learner_context: dict[str, Any] | None = None,
    context_pack: dict[str, Any] | None = None,
    rubric_build_latency_ms: float = 0.0,
    rubric_build_token_proxy: int = 0,
) -> dict[str, Any]:
    started = time.perf_counter()
    event = await grade_with_batch_judge_async(
        qid=str(case.get("case_id") or ""),
        student_answer=str(sample.get("answer_text") or ""),
        rubric_points=rubric_points,
        complete_fn=complete_fn,
        api_key=api_key,
        model=model,
        student_id=str(sample.get("student_id") or ""),
    )
    latency_ms = (time.perf_counter() - started) * 1000
    pcp = (learner_context or {}).get("personalization_context_pack") if learner_context else None
    rendered = render_case_rubric_feedback(
        event,
        question_stem=str(case.get("stem") or ""),
        personalization_context_pack=pcp,
    )
    all_hit_terms = _event_hit_terms(event)
    predicted_terms = _matched_gold_terms(all_hit_terms, set(gold["positive_terms"]))
    known_terms = _gold_known_terms(case)
    hallucinated = _unmatched_meaningful_terms(all_hit_terms, known_terms)
    llm_token_proxy = _token_proxy(str(sample.get("answer_text") or "")) + _token_proxy(rubric_points)
    context_token_proxy = _token_proxy(context_pack or {}) if context_pack else 0
    return _row_common(
        case=case,
        sample=sample,
        gold=gold,
        arm=arm,
        pred_score=float(event.get("awarded_score") or 0),
        max_score=float(event.get("max_score") or case.get("max_score") or 0),
        predicted_points=_event_predicted_points(event, case),
        predicted_terms=predicted_terms,
        hallucinated_terms=hallucinated,
        latency_ms=latency_ms,
        token_proxy=llm_token_proxy,
        extra={
            "score_authority": "rubric_grader_v1",
            "rag_ref_context_used": False,
            "compiled_rubric_used": compiled_rubric_used,
            "knowql_context_pack_attached": bool(context_pack),
            "learner_evidence_attached": bool(learner_context and learner_context.get("recent_evidence") is not None),
            "context_pack_status": (context_pack or {}).get("question_context", {}).get("status"),
            "context_pack_official_score_allowed": bool((context_pack or {}).get("diagnostic_policy", {}).get("official_score_allowed")),
            "rubric_build_latency_ms": round(float(rubric_build_latency_ms), 4),
            "cold_latency_ms": round(float(latency_ms + rubric_build_latency_ms), 4),
            "llm_token_proxy": llm_token_proxy,
            "context_token_proxy": context_token_proxy,
            "rubric_build_token_proxy": int(rubric_build_token_proxy),
            "cold_token_proxy": int(llm_token_proxy + rubric_build_token_proxy),
            "adjudication_strategy": event.get("adjudication_strategy"),
            "adjudication_group_count": event.get("adjudication_group_count"),
            "adjudication_point_count": event.get("adjudication_point_count"),
            "degraded": bool(event.get("degraded")),
            "feedback_preview_chars": len(rendered),
            "ttft_status": "not_exercised_non_streaming_core",
            "result_event": event,
        },
    )


async def _extract_reference_rubrics(
    *,
    cases: list[dict[str, Any]],
    complete_fn: CompleteFn,
    api_key: str,
    model: str,
) -> dict[str, tuple[list[dict[str, Any]], float, int]]:
    extracted: dict[str, tuple[list[dict[str, Any]], float, int]] = {}
    for case in cases:
        case_id = str(case.get("case_id") or "")
        reference_answer = _case_reference_answer(case)
        started = time.perf_counter()
        points = await extract_rubric_from_reference_async(
            reference_answer,
            str(case.get("stem") or ""),
            complete_fn,
            api_key,
            model=model,
            provider_authority="benchmark:no_knowql",
        )
        latency_ms = (time.perf_counter() - started) * 1000
        extracted[case_id] = (
            _normalize_extracted_points(points, case_id=case_id),
            latency_ms,
            _token_proxy(reference_answer) + _token_proxy(case.get("stem") or ""),
        )
    return extracted


async def _run_three_arm_eval_for_cases_async(
    *,
    cases: list[dict[str, Any]],
    complete_fn: CompleteFn,
    api_key: str,
    model: str,
    concurrency: int,
    sample_cap: int | None = None,
) -> dict[str, Any]:
    selected_cases = list(cases)
    reference_rubrics = await _extract_reference_rubrics(
        cases=selected_cases,
        complete_fn=complete_fn,
        api_key=api_key,
        model=model,
    )
    semaphore = asyncio.Semaphore(max(1, int(concurrency or 1)))
    rows: list[dict[str, Any]] = []
    tasks: list[asyncio.Task[list[dict[str, Any]]]] = []
    sample_count = 0

    async def _score_sample(case: dict[str, Any], sample: dict[str, Any]) -> list[dict[str, Any]]:
        async with semaphore:
            gold = gold_from_ledger(case, sample)
            rag_row = _score_rag_ref(case, sample, gold)
            case_id = str(case.get("case_id") or "")
            no_knowql_points, build_latency, build_token_proxy = reference_rubrics.get(case_id, ([], 0.0, 0))
            no_knowql = await _score_v1(
                arm=ARM_NEXUS_V1_NO_KNOWQL,
                case=case,
                sample=sample,
                gold=gold,
                rubric_points=no_knowql_points,
                complete_fn=complete_fn,
                api_key=api_key,
                model=model,
                compiled_rubric_used=False,
                rubric_build_latency_ms=build_latency,
                rubric_build_token_proxy=build_token_proxy,
            )
            compiled_points = _compiled_points_for_v1(case)
            learner_context = _learner_context(case, sample, gold)
            context_pack = _knowql_context_pack(case, compiled_points, learner_context)
            knowql = await _score_v1(
                arm=ARM_NEXUS_V1_KNOWQL,
                case=case,
                sample=sample,
                gold=gold,
                rubric_points=compiled_points,
                complete_fn=complete_fn,
                api_key=api_key,
                model=model,
                compiled_rubric_used=True,
                learner_context=learner_context,
                context_pack=context_pack,
            )
            return [rag_row, no_knowql, knowql]

    for case in selected_cases:
        for sample in list(case.get("eval_samples") or []):
            if sample_cap is not None and sample_count >= sample_cap:
                break
            tasks.append(asyncio.create_task(_score_sample(case, sample)))
            sample_count += 1
        if sample_cap is not None and sample_count >= sample_cap:
            break

    for chunk in await asyncio.gather(*tasks):
        rows.extend(chunk)

    return _build_report(rows=rows, cases=selected_cases, model=model)


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("arm") or "")].append(row)
    summary: dict[str, dict[str, Any]] = {}
    for arm in REQUESTED_ARMS:
        arm_rows = grouped.get(arm, [])
        summary[arm] = {
            "case_count": len({str(row.get("case_id")) for row in arm_rows}),
            "sample_count": len(arm_rows),
            "mean_abs_score_delta": _avg([abs(float(row["score_delta"])) for row in arm_rows]),
            "mean_point_recall": _avg([float(row["point_recall"]) for row in arm_rows]),
            "mean_point_precision": _avg([float(row["point_precision"]) for row in arm_rows]),
            "mean_term_recall": _avg([float(row["term_recall"]) for row in arm_rows]),
            "mean_term_precision": _avg([float(row["term_precision"]) for row in arm_rows]),
            "mean_semantic_understanding_score": _avg([float(row["semantic_understanding_score"]) for row in arm_rows]),
            "hallucination_rate": _avg([1.0 if row.get("hallucination") else 0.0 for row in arm_rows]),
            "mean_token_proxy": _avg([float(row["token_proxy"]) for row in arm_rows]),
            "mean_cold_token_proxy": _avg([float(row.get("cold_token_proxy") or row["token_proxy"]) for row in arm_rows]),
            "mean_context_token_proxy": _avg([float(row.get("context_token_proxy") or 0) for row in arm_rows]),
            "mean_latency_ms": _avg([float(row["latency_ms"]) for row in arm_rows]),
            "mean_cold_latency_ms": _avg([float(row.get("cold_latency_ms") or row["latency_ms"]) for row in arm_rows]),
            "degraded_rate": _avg([1.0 if row.get("degraded") else 0.0 for row in arm_rows]),
        }
    return summary


def _build_report(*, rows: list[dict[str, Any]], cases: list[dict[str, Any]], model: str) -> dict[str, Any]:
    return {
        "schema": "luban_knowql_nexus_three_arm_ab.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": model,
        "arms": list(REQUESTED_ARMS),
        "evaluation_criteria": [
            "score_alignment",
            "point_precision",
            "point_recall",
            "term_precision",
            "term_recall",
            "semantic_understanding",
            "hallucination_rate",
            "latency_ms",
            "cold_latency_ms",
            "token_proxy",
            "cold_token_proxy",
            "context_token_proxy",
            "degraded_rate",
        ],
        "case_ids": [str(case.get("case_id") or "") for case in cases],
        "summary": summarize_rows(rows),
        "rows": rows,
        "safety": {
            "production_default_flip": False,
            "remote_write": False,
            "db_write": False,
            "canonical_learner_truth_written": False,
            "rag_is_scoring_authority": False,
            "learner_evidence_is_scoring_authority": False,
        },
        "interpretation_guardrails": {
            "ttft": "not_exercised_non_streaming_core; run /api/v1/ws streaming probe for client TTFT",
            "tokens": "token_proxy estimates V1 adjudication prompt size; cold_token_proxy adds rubric extraction; context_token_proxy is attached context not necessarily sent to LLM",
            "release_truth": "benchmark/shadow evidence only; no production flip by this script",
        },
    }


def run_three_arm_eval_for_cases(
    *,
    cases: list[dict[str, Any]],
    complete_fn: CompleteFn,
    api_key: str,
    model: str,
    concurrency: int = 4,
    sample_cap: int | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        _run_three_arm_eval_for_cases_async(
            cases=cases,
            complete_fn=complete_fn,
            api_key=api_key,
            model=model,
            concurrency=concurrency,
            sample_cap=sample_cap,
        )
    )


def _select_cases(cases: list[dict[str, Any]], case_ids: list[str], *, all_cases: bool) -> list[dict[str, Any]]:
    if all_cases:
        return cases
    selected_ids = case_ids or [str(cases[0].get("case_id") or "")] if cases else []
    by_id = {str(case.get("case_id") or ""): case for case in cases}
    missing = sorted(set(selected_ids) - set(by_id))
    if missing:
        raise ValueError(f"missing eval cases: {missing}")
    return [by_id[case_id] for case_id in selected_ids]


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Luban KnowQL / Nexus Three-Arm AB",
        "",
        f"- schema: `{report['schema']}`",
        f"- model: `{report['model']}`",
        f"- arms: `{', '.join(report['arms'])}`",
        f"- cases: `{', '.join(report['case_ids'])}`",
        "- status: `benchmark_shadow_only`",
        "",
        "## Summary",
        "",
        "| arm | samples | score MAE | point recall | point precision | semantic | hallucination | llm token proxy | cold token proxy | context token proxy | latency ms | cold latency ms | degraded |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in REQUESTED_ARMS:
        data = report["summary"].get(arm) or {}
        lines.append(
            "| {arm} | {sample_count} | {mean_abs_score_delta} | {mean_point_recall} | {mean_point_precision} | {mean_semantic_understanding_score} | {hallucination_rate} | {mean_token_proxy} | {mean_cold_token_proxy} | {mean_context_token_proxy} | {mean_latency_ms} | {mean_cold_latency_ms} | {degraded_rate} |".format(
                arm=arm,
                **data,
            )
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            f"- ttft: {report['interpretation_guardrails']['ttft']}",
            f"- tokens: {report['interpretation_guardrails']['tokens']}",
            f"- release_truth: {report['interpretation_guardrails']['release_truth']}",
            "",
            "## Per Sample",
            "",
            "| case | sample | arm | pred | gold | delta | semantic | p_recall | p_precision | latency | token |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| {case_id} | {sample_id} | {arm} | {pred_score} | {gold_score} | {score_delta} | {semantic_understanding_score} | {point_recall} | {point_precision} | {latency_ms} | {token_proxy} |".format(
                **row
            )
        )
    lines.append("")
    return "\n".join(lines)


def _default_complete_fn(*, binding: str, base_url: str | None) -> CompleteFn:
    from deeptutor.services.llm import factory as llm_factory

    async def _complete(**kwargs: Any) -> str:
        return await llm_factory.complete(
            prompt=str(kwargs.get("prompt") or ""),
            system_prompt=str(kwargs.get("system_prompt") or "You are a helpful assistant."),
            model=str(kwargs.get("model") or ""),
            api_key=kwargs.get("api_key"),
            base_url=base_url,
            binding=binding,
            max_retries=int(kwargs.get("max_retries") or 1),
            temperature=0,
        )

    return _complete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--sample-cap", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--model", default="")
    parser.add_argument("--binding", default="deepseek")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    _load_env()
    model = args.model or os.environ.get("LLM_MODEL") or "deepseek-v4-flash"
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY") or ""
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY or LLM_API_KEY is required for live benchmark")
    base_url = args.base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
    cases = _select_cases(_load_fixture(Path(args.fixture)), args.case_id, all_cases=args.all)
    report = run_three_arm_eval_for_cases(
        cases=cases,
        complete_fn=_default_complete_fn(binding=args.binding, base_url=base_url),
        api_key=api_key,
        model=model,
        concurrency=args.concurrency,
        sample_cap=args.sample_cap,
    )

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    prefix = "full" if args.all else "pilot"
    json_path = output_dir / f"{prefix}_three_arm_ab_{stamp}.json"
    md_path = output_dir / f"{prefix}_three_arm_ab_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"json_path": str(json_path), "md_path": str(md_path), "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
