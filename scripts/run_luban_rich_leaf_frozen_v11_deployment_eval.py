#!/usr/bin/env python3
"""Deployment-shape two-arm eval: real kb_v5 RAG + frozen v11 multi-leaf rich context vs RAG-only.

Arm D (deployment): kb_v5 top-3 chunks + multi-leaf rich block rendered through the REAL runtime
seam (``rich_leaf_runtime.get_rich_leaf_contexts`` -> ``format_rich_leaf_pack_grounding_lines``,
supply bundle v3.1.1, 1595 records). Arm E (baseline): the SAME kb_v5 top-3 chunks alone (same
construction as the previous run's real_kbv5_rag arm) — both arms share one retrieval call per
question so the rich block is the only difference.

Candidate/review-only. No runtime install, no canonical truth writes, no DB writes. Question
sampling, leaf resolution (three-tier fallback), judge ordinal discipline and resume are reused
from scripts/run_luban_rich_leaf_real_world_three_arm_eval.py (same 40 questions, seed=20260613).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

SCHEMA = "luban_rich_leaf_frozen_v11_deployment_eval.v1"

ARM_DEPLOY = "kbv5_plus_rich_leaf_deployment"
ARM_BASELINE = "kbv5_only_baseline"
PLANNED_ARMS = [ARM_DEPLOY, ARM_BASELINE]

VALID_CITATION_SOURCES = {"retrieval_chunk", "rich_block", "both", "none"}

DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v11_deployment_eval_20260613"
DEFAULT_PREVIOUS_RESULTS = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_real_world_eval_20260613/real_world_three_arm_eval_results.json"
)
SUPPLY_BUNDLE_PATH = (
    REPO / "deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_context/rich_leaf_context_bundle.json"
)


def _load_base_module() -> Any:
    """Load the previous three-arm runner as a library (question bank / leaf / provider / judge)."""
    path = REPO / "scripts" / "run_luban_rich_leaf_real_world_three_arm_eval.py"
    spec = importlib.util.spec_from_file_location("rich_leaf_real_world_three_arm_eval_base", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("rich_leaf_real_world_three_arm_eval_base", module)
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()
OBJECTIVE_TYPES = BASE.OBJECTIVE_TYPES
VERDICT_SCORE = BASE.VERDICT_SCORE
VALID_VERDICTS = BASE.VALID_VERDICTS


# ---------------------------------------------------------------- rich block (real runtime seam)


def _extract_query_terms(stem: str) -> list[str]:
    """Production query-term extraction (same function general_knowledge feeds the runtime seam)."""
    from deeptutor.services.compiled_knowledge.general_knowledge import _extract_query_terms as extract

    return extract(stem)


def resolve_rich_block(
    question: dict[str, Any],
    units: list[dict[str, Any]],
    *,
    get_contexts: Callable[..., list[dict[str, Any]]] | None = None,
    render: Callable[..., list[str]] | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    """Resolve the multi-leaf rich block exactly the deployment way: three-tier leaf fallback
    (reused from the previous runner) gives the primary leaf, production query terms drive the
    deterministic supplement selection, and rendering goes through the ONE policy seam
    ``format_rich_leaf_pack_grounding_lines`` (1200-char default cap)."""
    if get_contexts is None or render is None:
        from deeptutor.services.construction_grading.rich_leaf_runtime import (
            format_rich_leaf_pack_grounding_lines,
            get_rich_leaf_contexts,
        )

        get_contexts = get_contexts or get_rich_leaf_contexts
        render = render or format_rich_leaf_pack_grounding_lines
    unit, resolution_mode = BASE.resolve_leaf(question, units)
    primary_leaf = str((unit or {}).get("leaf_id") or "")
    query_terms = _extract_query_terms(str(question.get("stem") or ""))
    riches = get_contexts(query_terms, [primary_leaf] if primary_leaf else [], top_k=top_k)
    rendered_lines = render({"rich_leaf_contexts": riches}) if riches else []
    return {
        "primary_leaf": primary_leaf or None,
        "leaf_resolution": resolution_mode,
        "query_terms": query_terms,
        "rich_leaf_ids": [str(r.get("leaf_id") or "") for r in riches],
        "rich_leaf_count": len(riches),
        "rendered_lines": rendered_lines,
        "rendered_chars": sum(len(line) + 1 for line in rendered_lines),
    }


# ---------------------------------------------------------------- arm contexts


def arm_context(arm: str, *, kbv5_chunks: list[dict[str, Any]], rich_block: dict[str, Any]) -> dict[str, Any]:
    retrieved = [
        {
            "chunk_id": chunk.get("chunk_id"),
            "doc_type": chunk.get("doc_type"),
            "score_final": chunk.get("score_final"),
            "content": chunk.get("content"),
        }
        for chunk in kbv5_chunks
    ]
    if arm == ARM_BASELINE:
        return {
            "mode": ARM_BASELINE,
            "retrieval_channel": "kb_v5.search_chunks_v2",
            "retrieved_chunks": retrieved,
        }
    return {
        "mode": ARM_DEPLOY,
        "retrieval_channel": "kb_v5.search_chunks_v2",
        "retrieved_chunks": retrieved,
        "rich_leaf_block": {
            "leaf_ids": rich_block.get("rich_leaf_ids") or [],
            "rendered_text": "\n".join(rich_block.get("rendered_lines") or []),
        },
    }


def answer_messages(question: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    payload = {
        "question_id": question.get("question_id"),
        "question_type": question.get("qtype"),
        "stem": question.get("stem"),
        "options": question.get("options"),
        "context": context,
        "required_json": {
            "answer": "string",
            "explanation": "short Chinese string",
            "citations": "list of chunk_id / rich-leaf leaf_id / source quotes actually used from context",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a Chinese construction-exam (一级建造师建筑实务) solver. "
                "Answer using the provided context plus your own knowledge; prefer cited context evidence. "
                "For single/multiple choice return ONLY the option letter(s) in `answer` (e.g. 'D' or 'ABD'). "
                "For 简答/案例 questions return a concise Chinese answer covering the key points. "
                "`citations` must list only evidence identifiers or quotes that actually appear in the context "
                "(retrieved chunk_id, rich-leaf leaf_id, or a verbatim quote); if you used none, return an "
                "empty list. Return one JSON object only."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


# ---------------------------------------------------------------- judge


def judge_messages(
    question: dict[str, Any],
    arm_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, str]]:
    mapping = {str(index + 1): str(row.get("arm")) for index, row in enumerate(arm_rows)}
    candidates = {
        str(index + 1): {
            "answer": row.get("answer"),
            "explanation": row.get("explanation"),
            "citations": row.get("citations"),
            "evidence_inventory": {
                "retrieval_chunk_ids": row.get("chunk_ids") or [],
                "rich_leaf_ids": row.get("rich_leaf_ids") or [],
            },
            "context_digest": row.get("context_digest"),
        }
        for index, row in enumerate(arm_rows)
    }
    payload = {
        "question_id": question.get("question_id"),
        "question_type": question.get("qtype"),
        "stem": question.get("stem"),
        "gold_answer": question.get("gold_answer"),
        "gold_analysis": question.get("gold_analysis"),
        "candidates": candidates,
        "required_json": {
            key: {
                "verdict": "correct | partial | wrong",
                "explanation_quality": "integer 1-5",
                "citation_grounded": "boolean: citations actually match evidence in that candidate context",
                "citation_source": "retrieval_chunk | rich_block | both | none",
            }
            for key in candidates
        },
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are an independent strict grader. Compare each candidate answer against the gold answer "
                "and gold analysis. verdict: correct = matches gold; partial = covers part of gold key points; "
                "wrong = contradicts or misses gold. explanation_quality 1-5 judges the explanation's correctness "
                "and pedagogy. citation_grounded is true only when the candidate's citations refer to evidence "
                "that really exists in its context_digest / evidence_inventory. citation_source classifies where "
                "the grounded citations land: retrieval_chunk = only retrieved chunk ids/quotes; rich_block = "
                "only rich-leaf leaf ids/quotes (富叶编译上下文); both = at least one of each; none = no grounded "
                "citation. Cover EVERY candidate key. Return one JSON object only, keyed by candidate ordinals."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]
    return messages, mapping


def apply_judge_verdicts(parsed: dict[str, Any], mapping: dict[str, str]) -> dict[str, dict[str, Any]]:
    verdicts: dict[str, dict[str, Any]] = {}
    for ordinal, arm in mapping.items():
        entry = parsed.get(ordinal) if isinstance(parsed.get(ordinal), dict) else {}
        verdict = str(entry.get("verdict") or "").strip().lower()
        if verdict not in VALID_VERDICTS:
            verdicts[arm] = {
                "judge_status": "judge_failed",
                "verdict": None,
                "explanation_quality": None,
                "citation_grounded": None,
                "citation_source": None,
            }
            continue
        try:
            quality = min(5, max(1, int(entry.get("explanation_quality"))))
        except (TypeError, ValueError):
            quality = None
        source = str(entry.get("citation_source") or "").strip().lower()
        verdicts[arm] = {
            "judge_status": "completed",
            "verdict": verdict,
            "explanation_quality": quality,
            "citation_grounded": bool(entry.get("citation_grounded")),
            "citation_source": source if source in VALID_CITATION_SOURCES else None,
        }
    return verdicts


# ---------------------------------------------------------------- scoring


def group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    judged = [row for row in completed if row.get("judge_status") == "completed"]
    qualities = [int(row["explanation_quality"]) for row in judged if row.get("explanation_quality")]
    objective_rows = [row for row in completed if row.get("qtype") in OBJECTIVE_TYPES]
    sources = defaultdict(int)
    for row in judged:
        sources[str(row.get("citation_source") or "unknown")] += 1
    return {
        "sample_count": len(rows),
        "completed_count": len(completed),
        "judged_count": len(judged),
        "fail_rate": round((len(rows) - len(completed)) / len(rows), 4) if rows else 0.0,
        "correct_rate": round(mean([1.0 if row.get("verdict") == "correct" else 0.0 for row in judged]), 4) if judged else 0.0,
        "partial_rate": round(mean([1.0 if row.get("verdict") == "partial" else 0.0 for row in judged]), 4) if judged else 0.0,
        "semantic_score": round(mean([VERDICT_SCORE.get(str(row.get("verdict")), 0.0) for row in judged]), 4) if judged else 0.0,
        "explanation_quality_mean": round(mean(qualities), 2) if qualities else 0.0,
        "citation_grounded_rate": round(mean([1.0 if row.get("citation_grounded") else 0.0 for row in judged]), 4) if judged else 0.0,
        "citation_source_counts": dict(sorted(sources.items())),
        "objective_exact_match_rate": round(mean([1.0 if row.get("exact_match") else 0.0 for row in objective_rows]), 4)
        if objective_rows
        else 0.0,
        "mean_prompt_tokens": round(mean([int(row.get("prompt_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_completion_tokens": round(mean([int(row.get("completion_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_total_tokens": round(mean([int(row.get("total_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_latency_ms": round(mean([float(row.get("latency_ms") or 0.0) for row in completed]), 2) if completed else 0.0,
        "mean_rich_leaf_count": round(mean([int(row.get("rich_leaf_count") or 0) for row in completed]), 2) if completed else 0.0,
        "multi_leaf_rate": round(mean([1.0 if int(row.get("rich_leaf_count") or 0) > 1 else 0.0 for row in completed]), 4)
        if completed
        else 0.0,
    }


def arm_summary(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    objective = [row for row in rows if row.get("qtype") in OBJECTIVE_TYPES]
    subjective = [row for row in rows if row.get("qtype") not in OBJECTIVE_TYPES]
    return {
        "arm": arm,
        **group_summary(rows),
        "by_question_group": {
            "objective": group_summary(objective),
            "subjective_case": group_summary(subjective),
        },
    }


def comparison_block(arms: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm = {str(arm.get("arm")): arm for arm in arms}
    deploy = by_arm.get(ARM_DEPLOY) or {}
    baseline = by_arm.get(ARM_BASELINE) or {}

    def delta(metric: str, scope: Callable[[dict[str, Any]], dict[str, Any]]) -> float | None:
        lhs, rhs = scope(deploy), scope(baseline)
        if not lhs or not rhs:
            return None
        return round(float(lhs.get(metric) or 0.0) - float(rhs.get(metric) or 0.0), 4)

    scopes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
        "overall": lambda arm: arm,
        "objective": lambda arm: (arm.get("by_question_group") or {}).get("objective") or {},
        "subjective_case": lambda arm: (arm.get("by_question_group") or {}).get("subjective_case") or {},
    }
    metrics = ("semantic_score", "correct_rate", "objective_exact_match_rate", "explanation_quality_mean",
               "citation_grounded_rate", "mean_total_tokens", "mean_latency_ms")
    return {
        "deltas_deploy_minus_baseline": {
            scope_name: {metric: delta(metric, scope) for metric in metrics}
            for scope_name, scope in scopes.items()
        },
        "deploy_subjective_multi_leaf": {
            "mean_rich_leaf_count": ((deploy.get("by_question_group") or {}).get("subjective_case") or {}).get("mean_rich_leaf_count"),
            "multi_leaf_rate": ((deploy.get("by_question_group") or {}).get("subjective_case") or {}).get("multi_leaf_rate"),
            "citation_source_counts": ((deploy.get("by_question_group") or {}).get("subjective_case") or {}).get("citation_source_counts"),
        },
    }


def previous_run_reference(previous_path: Path | None, question_ids: list[str]) -> dict[str, Any]:
    """Comparability anchor against the previous run's real_kbv5_rag arm (arm A). The baseline arm
    here is re-run (shared retrieval with arm D), so the previous numbers are reference-only."""
    if previous_path is None or not previous_path.exists():
        return {"available": False, "reason": "previous_results_missing"}
    payload = BASE._read_json(previous_path)
    previous_ids = sorted({str(row.get("question_id")) for row in payload.get("rows") or []})
    same_questions = previous_ids == sorted(question_ids)
    arm_a = next((arm for arm in payload.get("arms") or [] if arm.get("arm") == "real_kbv5_rag"), None)
    return {
        "available": True,
        "reused_from": str(previous_path),
        "seed": payload.get("seed"),
        "question_set_identical": same_questions,
        "previous_question_count": len(previous_ids),
        "previous_real_kbv5_rag_summary": arm_a,
        "note": "reference only — baseline arm E was re-run with retrieval shared per-question with arm D",
    }


# ---------------------------------------------------------------- report


def build_report(
    *,
    questions: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    judge_rows: list[dict[str, Any]],
    model: str,
    seed: int,
    provider_configured: bool,
    kbv5_status: dict[str, Any],
    supply_manifest: dict[str, Any],
    previous_reference: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if not provider_configured:
        blockers.append("provider_call_not_configured")
    if not questions:
        blockers.append("no_questions_sampled")
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm[str(row.get("arm"))].append(row)
    arms = [arm_summary(arm, by_arm.get(arm, [])) for arm in PLANNED_ARMS]
    prompt_tokens = sum(int(row.get("prompt_tokens") or 0) for row in rows + judge_rows)
    completion_tokens = sum(int(row.get("completion_tokens") or 0) for row in rows + judge_rows)
    runtime_exercised = bool(rows) and not blockers
    return {
        "schema": SCHEMA,
        "execution_authority": "authorized_live_deployment_shape_eval" if runtime_exercised else "not_exercised",
        "runtime_exercised": runtime_exercised,
        "seed": seed,
        "models": [model] if runtime_exercised else [],
        "kbv5_retrieval": kbv5_status,
        "rich_leaf_supply": {
            "bundle_schema": supply_manifest.get("schema"),
            "source_pack_version": supply_manifest.get("source_pack_version"),
            "record_count": supply_manifest.get("record_count"),
            "content_hash": supply_manifest.get("content_hash"),
        },
        "question_sample": {
            "total": len(questions),
            "objective": sum(1 for q in questions if q["qtype"] in OBJECTIVE_TYPES),
            "subjective": sum(1 for q in questions if q["qtype"] not in OBJECTIVE_TYPES),
            "years": sorted({q["year"] for q in questions}),
        },
        "provider_usage": {
            "answer_call_count": len(rows),
            "judge_call_count": len(judge_rows),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "arms": arms,
        "comparison": comparison_block(arms),
        "previous_run_reference": previous_reference,
        "rows": rows,
        "judge_rows": judge_rows,
        "blockers": blockers,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "deployment_shape_two_arm_eval": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


# ---------------------------------------------------------------- live loop


def _resume_index(previous: dict[str, Any] | None) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    answer_rows: dict[tuple[str, str], dict[str, Any]] = {}
    judge_rows: dict[str, dict[str, Any]] = {}
    if isinstance(previous, dict) and previous.get("schema") == SCHEMA:
        for row in previous.get("rows") or []:
            if isinstance(row, dict) and row.get("status") == "completed" and row.get("judge_status") == "completed":
                answer_rows[(str(row.get("question_id")), str(row.get("arm")))] = row
        for row in previous.get("judge_rows") or []:
            if isinstance(row, dict) and row.get("status") == "completed":
                judge_rows[str(row.get("question_id"))] = row
    return answer_rows, judge_rows


def run_eval(
    *,
    questions: list[dict[str, Any]],
    units: list[dict[str, Any]],
    provider_call: Callable[..., dict[str, Any]] | None,
    retriever: Callable[[str], dict[str, Any]] | None,
    model: str,
    seed: int,
    token_budget: int,
    supply_manifest: dict[str, Any],
    previous_reference: dict[str, Any],
    resume: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    resumed_answers, resumed_judges = _resume_index(resume)
    rows: list[dict[str, Any]] = []
    judge_rows: list[dict[str, Any]] = []
    kbv5_status: dict[str, Any] = {"channel": "kb_v5.search_chunks_v2", "degraded": False, "unavailable_count": 0}
    spent_tokens = 0

    def _checkpoint() -> dict[str, Any]:
        report = build_report(
            questions=questions,
            rows=rows,
            judge_rows=judge_rows,
            model=model,
            seed=seed,
            provider_configured=provider_call is not None,
            kbv5_status=kbv5_status,
            supply_manifest=supply_manifest,
            previous_reference=previous_reference,
        )
        if output_path is not None:
            BASE._write_json(output_path, report)
        return report

    if provider_call is None:
        return _checkpoint()

    for question in questions:
        question_id = str(question["question_id"])
        resumed = [resumed_answers.get((question_id, arm)) for arm in PLANNED_ARMS]
        if all(resumed) and question_id in resumed_judges:
            rows.extend(resumed)  # type: ignore[arg-type]
            judge_rows.append(resumed_judges[question_id])
            continue
        if spent_tokens > token_budget:
            kbv5_status["budget_exhausted_at"] = question_id
            break

        rich_block = resolve_rich_block(question, units)
        retrieval = retriever(question["stem"]) if retriever else {"status": "skipped", "chunks": [], "latency_ms": 0.0}
        if retrieval["status"] != "completed":
            kbv5_status["unavailable_count"] = int(kbv5_status.get("unavailable_count") or 0) + 1
            kbv5_status["degraded"] = True
        chunk_ids = [str(chunk.get("chunk_id") or "") for chunk in retrieval["chunks"]]

        question_rows: list[dict[str, Any]] = []
        for arm in PLANNED_ARMS:
            context = arm_context(arm, kbv5_chunks=retrieval["chunks"], rich_block=rich_block)
            is_deploy = arm == ARM_DEPLOY
            row: dict[str, Any] = {
                "arm": arm,
                "question_id": question_id,
                "qtype": question["qtype"],
                "year": question["year"],
                "node_code": question["node_code"],
                "leaf_resolution": rich_block["leaf_resolution"],
                "primary_leaf": rich_block["primary_leaf"],
                "rich_leaf_ids": rich_block["rich_leaf_ids"] if is_deploy else [],
                "rich_leaf_count": rich_block["rich_leaf_count"] if is_deploy else 0,
                "rich_rendered_chars": rich_block["rendered_chars"] if is_deploy else 0,
                "chunk_ids": chunk_ids,
                "context_digest": BASE._context_digest(context),
                "retrieval_status": retrieval["status"],
                "retrieval_latency_ms": retrieval["latency_ms"],
            }
            try:
                response = provider_call(answer_messages(question, context), max_tokens=700)
                parsed = BASE._parse_json_object(str(response.get("content") or ""))
                answer = str(parsed.get("answer") or "").strip()
                row.update(
                    {
                        "status": "completed",
                        "answer": answer,
                        "explanation": str(parsed.get("explanation") or "")[:600],
                        "citations": [str(item) for item in parsed.get("citations") or []][:10],
                        "exact_match": BASE.objective_exact_match(answer, question["gold_answer"])
                        if question["qtype"] in OBJECTIVE_TYPES
                        else None,
                        "prompt_tokens": int(response.get("prompt_tokens") or 0),
                        "completion_tokens": int(response.get("completion_tokens") or 0),
                        "total_tokens": int(response.get("prompt_tokens") or 0) + int(response.get("completion_tokens") or 0),
                        "latency_ms": float(response.get("latency_ms") or 0.0),
                    }
                )
            except Exception as exc:  # pragma: no cover - live failure path
                row.update(
                    {
                        "status": "failed",
                        "error": str(exc)[:240],
                        "answer": "",
                        "explanation": "",
                        "citations": [],
                        "exact_match": None,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "latency_ms": 0.0,
                    }
                )
            spent_tokens += int(row.get("total_tokens") or 0)
            question_rows.append(row)

        completed_rows = [row for row in question_rows if row.get("status") == "completed"]
        judge_row: dict[str, Any] = {"question_id": question_id, "status": "skipped"}
        verdicts: dict[str, dict[str, Any]] = {}
        if completed_rows:
            messages, mapping = judge_messages(question, completed_rows)
            try:
                response = provider_call(messages, max_tokens=700)
                verdicts = apply_judge_verdicts(BASE._parse_json_object(str(response.get("content") or "")), mapping)
                judge_row = {
                    "question_id": question_id,
                    "status": "completed",
                    "mapping": mapping,
                    "prompt_tokens": int(response.get("prompt_tokens") or 0),
                    "completion_tokens": int(response.get("completion_tokens") or 0),
                    "latency_ms": float(response.get("latency_ms") or 0.0),
                }
                spent_tokens += int(response.get("prompt_tokens") or 0) + int(response.get("completion_tokens") or 0)
            except Exception as exc:  # pragma: no cover - live failure path
                judge_row = {"question_id": question_id, "status": "failed", "error": str(exc)[:240]}
        for row in question_rows:
            verdict = verdicts.get(str(row["arm"]))
            if verdict is None:
                row.update(
                    {
                        "judge_status": "judge_failed",
                        "verdict": None,
                        "explanation_quality": None,
                        "citation_grounded": None,
                        "citation_source": None,
                    }
                )
            else:
                row.update(verdict)
            row.pop("context_digest", None)
        rows.extend(question_rows)
        judge_rows.append(judge_row)
        _checkpoint()

    return _checkpoint()


# ---------------------------------------------------------------- entrypoint


def load_supply_units(bundle_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bundle = BASE._read_json(bundle_path)
    manifest = bundle.get("manifest") if isinstance(bundle.get("manifest"), dict) else {}
    records = [record for record in bundle.get("records") or [] if isinstance(record, dict)]
    return records, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-dir", type=Path, default=BASE.DEFAULT_EXAM_DIR)
    parser.add_argument("--bundle", type=Path, default=SUPPLY_BUNDLE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "deployment_eval_results.json")
    parser.add_argument("--previous-results", type=Path, default=DEFAULT_PREVIOUS_RESULTS)
    parser.add_argument("--seed", type=int, default=20260613)
    parser.add_argument("--objective-count", type=int, default=32)
    parser.add_argument("--subjective-count", type=int, default=8)
    parser.add_argument("--kbv5-top-k", type=int, default=3)
    parser.add_argument("--token-budget", type=int, default=300_000)
    parser.add_argument("--provider", choices=sorted(BASE.PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--no-provider-call", action="store_true")
    parser.add_argument("--resume-from", type=Path, default=None)
    args = parser.parse_args(argv)

    model = args.model or BASE.PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = (
        None if args.no_provider_call else BASE._openai_compat_provider(provider=args.provider, model=model, timeout_s=args.timeout_s)
    )
    units, supply_manifest = load_supply_units(args.bundle)
    questions = BASE.sample_questions(
        BASE.load_question_bank(args.exam_dir, BASE.DEFAULT_EXAM_YEARS),
        seed=args.seed,
        objective_count=args.objective_count,
        subjective_count=args.subjective_count,
    )
    previous_reference = previous_run_reference(args.previous_results, [str(q["question_id"]) for q in questions])
    resume = BASE._read_json(args.resume_from) if args.resume_from and args.resume_from.exists() else None
    report = run_eval(
        questions=questions,
        units=units,
        provider_call=provider_call,
        retriever=BASE._kbv5_retriever(args.kbv5_top_k) if provider_call is not None else None,
        model=model,
        seed=args.seed,
        token_budget=args.token_budget,
        supply_manifest=supply_manifest,
        previous_reference=previous_reference,
        resume=resume,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "runtime_exercised": report["runtime_exercised"],
                "provider_usage": report["provider_usage"],
                "arms": [
                    {k: arm[k] for k in ("arm", "sample_count", "fail_rate", "semantic_score", "objective_exact_match_rate", "mean_total_tokens")}
                    for arm in report["arms"]
                ],
                "comparison": report["comparison"]["deltas_deploy_minus_baseline"],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
