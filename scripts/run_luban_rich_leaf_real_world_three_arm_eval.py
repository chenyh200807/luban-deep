#!/usr/bin/env python3
"""Real-world three-arm eval: real kb_v5 RAG vs rich_leaf full vs rich_leaf guard.

Candidate/review-only. No runtime install, no canonical truth writes, no DB writes.
Questions come from real 2021-2025 exam papers with gold answers; answers and an
independent semantic judge run on the same live provider (deepseek by default).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
SCHEMA = "luban_rich_leaf_real_world_three_arm_eval.v1"

ARM_KBV5 = "real_kbv5_rag"
ARM_RICH_FULL = "rich_leaf_full"
ARM_RICH_GUARD = "rich_leaf_guard"
PLANNED_ARMS = [ARM_KBV5, ARM_RICH_FULL, ARM_RICH_GUARD]

OBJECTIVE_TYPES = {"single_choice", "multiple_choice"}
CONTEXT_FAMILIES = (
    "concepts",
    "definitions",
    "rules",
    "procedures",
    "numeric_constraints",
    "exam_patterns",
    "teaching_cards",
)
VALID_VERDICTS = {"correct", "partial", "wrong"}
VERDICT_SCORE = {"correct": 1.0, "partial": 0.5, "wrong": 0.0}

DEFAULT_EXAM_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库")
DEFAULT_EXAM_YEARS = (2021, 2022, 2023, 2024, 2025)
DEFAULT_PACK = REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_full_compile_20260613/runtime_token_pack_v301_quarantine_annotated.json"
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_frozen_v1_real_world_eval_20260613"

PROVIDER_DEFAULTS = {
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "dashscope": {
        "env_key": "DASHSCOPE_API_KEY",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
}

ProviderCall = Callable[..., dict[str, Any]]


# ---------------------------------------------------------------- io helpers


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_dotenv() -> None:
    for path in (REPO / ".env", Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env")):
        if not path.exists():
            continue
        for line in path.read_text("utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


def _openai_compat_provider(*, provider: str, model: str | None, timeout_s: float) -> ProviderCall | None:
    _load_dotenv()
    spec = PROVIDER_DEFAULTS[provider]
    api_key = os.environ.get(spec["env_key"])
    if not api_key:
        return None
    base_url = (os.environ.get(spec["base_url_env"]) or spec["base_url"]).rstrip("/")
    selected_model = model or spec["model"]

    def call(messages: list[dict[str, str]], *, max_tokens: int = 700, timeout_s: float = timeout_s) -> dict[str, Any]:
        started = time.monotonic()
        body = json.dumps(
            {
                "model": selected_model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{provider}_http_error:{exc.code}:{text[:200]}") from exc
        content = str(payload["choices"][0]["message"].get("content") or "")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return {
            "model": selected_model,
            "content": content,
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
        }

    return call


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(text[start : end + 1])
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


# ---------------------------------------------------------------- question bank


def extract_questions(exam_payload: dict[str, Any], *, year: int) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for chunk in exam_payload.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("chunk_id") or "")
        node_code = str((chunk.get("taxonomy") or {}).get("node_code") or "")
        for index, exercise in enumerate(chunk.get("exercises") or []):
            if not isinstance(exercise, dict):
                continue
            data = exercise.get("question_data") if isinstance(exercise.get("question_data"), dict) else {}
            stem = str(data.get("stem") or "").strip()
            gold = str(data.get("correct_answer") or "").strip()
            if not stem or not gold:
                continue
            questions.append(
                {
                    "question_id": f"{year}:{chunk_id}:{index}",
                    "year": year,
                    "node_code": node_code,
                    "qtype": str(exercise.get("type") or "unknown"),
                    "stem": stem,
                    "options": [opt for opt in data.get("options") or [] if isinstance(opt, dict)],
                    "gold_answer": gold,
                    "gold_analysis": str(data.get("analysis") or ""),
                    "score": float(data.get("score") or 0.0),
                }
            )
    return questions


def load_question_bank(exam_dir: Path, years: tuple[int, ...]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for year in years:
        path = exam_dir / f"{year}年一级建造师《建筑实务》考试真题及答案解析" / f"FINAL_CLEANED_EXAM_V{year}.json"
        if not path.exists():
            continue
        questions.extend(extract_questions(_read_json(path), year=year))
    return questions


def sample_questions(
    questions: list[dict[str, Any]],
    *,
    seed: int,
    objective_count: int,
    subjective_count: int,
) -> list[dict[str, Any]]:
    objective = sorted((q for q in questions if q["qtype"] in OBJECTIVE_TYPES), key=lambda q: q["question_id"])
    subjective = sorted((q for q in questions if q["qtype"] not in OBJECTIVE_TYPES), key=lambda q: q["question_id"])
    rng = random.Random(seed)
    picked = rng.sample(objective, min(objective_count, len(objective)))
    picked += rng.sample(subjective, min(subjective_count, len(subjective)))
    return sorted(picked, key=lambda q: q["question_id"])


# ---------------------------------------------------------------- leaf resolution


_CJK = re.compile(r"[一-鿿]")


def _bigrams(text: str) -> set[str]:
    chars = [ch for ch in text if _CJK.match(ch)]
    return {a + b for a, b in zip(chars, chars[1:])}


def _unit_text(unit: dict[str, Any]) -> str:
    compiled = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
    parts = [str(unit.get("leaf_name_path") or "")]
    for family in CONTEXT_FAMILIES:
        parts.extend(str(item) for item in compiled.get(family) or [])
    return "\n".join(parts)


def resolve_leaf(question: dict[str, Any], units: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    if not units:
        return None, "no_units"
    node_code = str(question.get("node_code") or "")
    exact = [u for u in units if str(u.get("leaf_id") or "").split("-")[0] == node_code]
    if exact:
        candidates, mode = exact, "node_code_exact"
    else:
        family = [u for u in units if node_code[:6] and str(u.get("leaf_id") or "").startswith(node_code[:6])]
        if family:
            candidates, mode = family, "node_code_family"
        else:
            candidates, mode = units, "keyword_fallback"
    stem_grams = _bigrams(str(question.get("stem") or ""))
    best = max(
        candidates,
        key=lambda u: (len(stem_grams & _bigrams(_unit_text(u))), str(u.get("leaf_id") or "")),
    )
    return best, mode


# ---------------------------------------------------------------- arm contexts


def _compact_context(compiled_context: dict[str, Any], *, max_items_per_family: int) -> dict[str, list[str]]:
    compact: dict[str, list[str]] = {}
    for family in CONTEXT_FAMILIES:
        values = [str(item) for item in compiled_context.get(family) or [] if str(item).strip()]
        if values:
            compact[family] = values[:max_items_per_family]
    return compact


def _source_pointer(unit: dict[str, Any]) -> dict[str, Any]:
    source_ref = unit.get("source_ref") if isinstance(unit.get("source_ref"), dict) else {}
    return {
        "chunk_id": source_ref.get("chunk_id"),
        "source_lane": source_ref.get("source_lane"),
        "source_path": source_ref.get("source_path"),
        "record_id": source_ref.get("record_id"),
        "span_hash": source_ref.get("span_hash"),
    }


def arm_context(
    arm: str,
    *,
    question: dict[str, Any],
    kbv5_chunks: list[dict[str, Any]],
    unit: dict[str, Any] | None,
) -> dict[str, Any]:
    if arm == ARM_KBV5:
        return {
            "mode": ARM_KBV5,
            "retrieval_channel": "kb_v5.search_chunks_v2",
            "retrieved_chunks": [
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "doc_type": chunk.get("doc_type"),
                    "score_final": chunk.get("score_final"),
                    "content": chunk.get("content"),
                }
                for chunk in kbv5_chunks
            ],
        }
    compiled = (unit or {}).get("compiled_context") if isinstance((unit or {}).get("compiled_context"), dict) else {}
    if arm == ARM_RICH_GUARD:
        return {
            "mode": ARM_RICH_GUARD,
            "leaf_id": (unit or {}).get("leaf_id"),
            "source_ref": _source_pointer(unit or {}),
            "guardrails": [
                "only_answer_if_source_evidence_present",
                "do_not_invent_evidence",
                "fail_closed_if_context_insufficient",
            ],
            "compiled_context": _compact_context(compiled, max_items_per_family=1),
        }
    return {
        "mode": ARM_RICH_FULL,
        "leaf_id": (unit or {}).get("leaf_id"),
        "leaf_name_path": (unit or {}).get("leaf_name_path"),
        "source_ref": _source_pointer(unit or {}),
        "compiled_context": _compact_context(compiled, max_items_per_family=2),
    }


# ---------------------------------------------------------------- prompts


def answer_messages(arm: str, *, question: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    payload = {
        "question_id": question.get("question_id"),
        "question_type": question.get("qtype"),
        "stem": question.get("stem"),
        "options": question.get("options"),
        "context": context,
        "required_json": {
            "answer": "string",
            "explanation": "short Chinese string",
            "citations": "list of chunk_id / source quotes actually used from context",
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
                "`citations` must list only evidence identifiers or quotes that actually appear in the context; "
                "if you used none, return an empty list. Return one JSON object only."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


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
                "citation_grounded": "boolean: citations actually match evidence in that candidate context digest",
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
                "that really exists in its context_digest. Cover EVERY candidate key. Return one JSON object only, "
                "keyed by the candidate ordinals."
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
            }
            continue
        quality_raw = entry.get("explanation_quality")
        try:
            quality = min(5, max(1, int(quality_raw)))
        except (TypeError, ValueError):
            quality = None
        verdicts[arm] = {
            "judge_status": "completed",
            "verdict": verdict,
            "explanation_quality": quality,
            "citation_grounded": bool(entry.get("citation_grounded")),
        }
    return verdicts


# ---------------------------------------------------------------- scoring


def objective_exact_match(answer: str, gold: str) -> bool:
    norm_answer = "".join(sorted(ch for ch in str(answer).upper() if ch.isalpha()))
    norm_gold = "".join(sorted(ch for ch in str(gold).upper() if ch.isalpha()))
    return bool(norm_answer) and norm_answer == norm_gold


def arm_summary(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    judged = [row for row in completed if row.get("judge_status") == "completed"]
    qualities = [int(row["explanation_quality"]) for row in judged if row.get("explanation_quality")]
    objective_rows = [row for row in completed if row.get("qtype") in OBJECTIVE_TYPES]
    return {
        "arm": arm,
        "sample_count": len(rows),
        "completed_count": len(completed),
        "judged_count": len(judged),
        "fail_rate": round((len(rows) - len(completed)) / len(rows), 4) if rows else 0.0,
        "correct_rate": round(mean([1.0 if row.get("verdict") == "correct" else 0.0 for row in judged]), 4) if judged else 0.0,
        "partial_rate": round(mean([1.0 if row.get("verdict") == "partial" else 0.0 for row in judged]), 4) if judged else 0.0,
        "semantic_score": round(mean([VERDICT_SCORE.get(str(row.get("verdict")), 0.0) for row in judged]), 4) if judged else 0.0,
        "explanation_quality_mean": round(mean(qualities), 2) if qualities else 0.0,
        "citation_grounded_rate": round(mean([1.0 if row.get("citation_grounded") else 0.0 for row in judged]), 4) if judged else 0.0,
        "objective_exact_match_rate": round(mean([1.0 if row.get("exact_match") else 0.0 for row in objective_rows]), 4)
        if objective_rows
        else 0.0,
        "mean_prompt_tokens": round(mean([int(row.get("prompt_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_completion_tokens": round(mean([int(row.get("completion_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_total_tokens": round(mean([int(row.get("total_tokens") or 0) for row in completed]), 2) if completed else 0.0,
        "mean_latency_ms": round(mean([float(row.get("latency_ms") or 0.0) for row in completed]), 2) if completed else 0.0,
    }


def build_report(
    *,
    questions: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    judge_rows: list[dict[str, Any]],
    model: str,
    seed: int,
    provider_configured: bool,
    kbv5_status: dict[str, Any],
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
        "execution_authority": "authorized_live_real_world_eval" if runtime_exercised else "not_exercised",
        "runtime_exercised": runtime_exercised,
        "seed": seed,
        "models": [model] if runtime_exercised else [],
        "kbv5_retrieval": kbv5_status,
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
        "rows": rows,
        "judge_rows": judge_rows,
        "blockers": blockers,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "real_world_three_arm_eval": True,
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


def _kbv5_retriever(top_k: int) -> Callable[[str], dict[str, Any]]:
    import sys

    sys.path.insert(0, str(REPO))
    _load_dotenv()
    from deeptutor.services.rag.pipelines.kbv5 import _KbV5Unavailable, _retrieve_chunks

    def retrieve(query: str) -> dict[str, Any]:
        try:
            result = _retrieve_chunks(
                query,
                top_k=top_k,
                doc_types=("standard", "textbook", "exam"),
                data_version=int(os.getenv("KBV5_RAG_DATA_VERSION", "2026")),
            )
        except _KbV5Unavailable as exc:
            return {"status": "unavailable", "error": str(exc)[:200], "chunks": [], "latency_ms": 0.0}
        return {
            "status": "completed",
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_type": chunk.doc_type,
                    "score_final": chunk.score_final,
                    "content": chunk.content,
                }
                for chunk in result.chunks
            ],
            "latency_ms": result.latency_ms,
        }

    return retrieve


def _context_digest(context: dict[str, Any]) -> str:
    return json.dumps(context, ensure_ascii=False, sort_keys=True)[:2000]


def _resume_index(previous: dict[str, Any] | None) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    answer_rows: dict[tuple[str, str], dict[str, Any]] = {}
    judge_rows: dict[str, dict[str, Any]] = {}
    if isinstance(previous, dict):
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
    provider_call: ProviderCall | None,
    retriever: Callable[[str], dict[str, Any]] | None,
    model: str,
    seed: int,
    token_budget: int,
    previous: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    resumed_answers, resumed_judges = _resume_index(previous)
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
        )
        if output_path is not None:
            _write_json(output_path, report)
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

        unit, resolution_mode = resolve_leaf(question, units)
        retrieval = retriever(question["stem"]) if retriever else {"status": "skipped", "chunks": [], "latency_ms": 0.0}
        if retrieval["status"] != "completed":
            kbv5_status["unavailable_count"] = int(kbv5_status.get("unavailable_count") or 0) + 1
            kbv5_status["degraded"] = True

        question_rows: list[dict[str, Any]] = []
        for arm in PLANNED_ARMS:
            context = arm_context(arm, question=question, kbv5_chunks=retrieval["chunks"], unit=unit)
            row: dict[str, Any] = {
                "arm": arm,
                "question_id": question_id,
                "qtype": question["qtype"],
                "year": question["year"],
                "node_code": question["node_code"],
                "leaf_id": (unit or {}).get("leaf_id"),
                "leaf_resolution": resolution_mode,
                "context_digest": _context_digest(context),
                "retrieval_status": retrieval["status"] if arm == ARM_KBV5 else None,
                "retrieval_latency_ms": retrieval["latency_ms"] if arm == ARM_KBV5 else None,
            }
            try:
                response = provider_call(answer_messages(arm, question=question, context=context), max_tokens=700)
                parsed = _parse_json_object(str(response.get("content") or ""))
                answer = str(parsed.get("answer") or "").strip()
                row.update(
                    {
                        "status": "completed",
                        "answer": answer,
                        "explanation": str(parsed.get("explanation") or "")[:600],
                        "citations": [str(item) for item in parsed.get("citations") or []][:10],
                        "exact_match": objective_exact_match(answer, question["gold_answer"])
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
        if completed_rows:
            messages, mapping = judge_messages(question, completed_rows)
            try:
                response = provider_call(messages, max_tokens=700)
                verdicts = apply_judge_verdicts(_parse_json_object(str(response.get("content") or "")), mapping)
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
                verdicts = {}
                judge_row = {"question_id": question_id, "status": "failed", "error": str(exc)[:240]}
        else:
            verdicts = {}
        for row in question_rows:
            verdict = verdicts.get(str(row["arm"]))
            if verdict is None:
                row.update({"judge_status": "judge_failed", "verdict": None, "explanation_quality": None, "citation_grounded": None})
            else:
                row.update(verdict)
            row.pop("context_digest", None)
        rows.extend(question_rows)
        judge_rows.append(judge_row)
        _checkpoint()

    return _checkpoint()


# ---------------------------------------------------------------- entrypoint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-dir", type=Path, default=DEFAULT_EXAM_DIR)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "real_world_three_arm_eval_results.json")
    parser.add_argument("--seed", type=int, default=20260613)
    parser.add_argument("--objective-count", type=int, default=32)
    parser.add_argument("--subjective-count", type=int, default=8)
    parser.add_argument("--kbv5-top-k", type=int, default=3)
    parser.add_argument("--token-budget", type=int, default=400_000)
    parser.add_argument("--provider", choices=sorted(PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--no-provider-call", action="store_true")
    parser.add_argument("--resume-from", type=Path, default=None)
    args = parser.parse_args(argv)

    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    provider_call = None if args.no_provider_call else _openai_compat_provider(provider=args.provider, model=model, timeout_s=args.timeout_s)
    pack = _read_json(args.pack)
    units = [unit for unit in pack.get("runtime_token_pack_units") or [] if isinstance(unit, dict)]
    questions = sample_questions(
        load_question_bank(args.exam_dir, DEFAULT_EXAM_YEARS),
        seed=args.seed,
        objective_count=args.objective_count,
        subjective_count=args.subjective_count,
    )
    previous = _read_json(args.resume_from) if args.resume_from and args.resume_from.exists() else None
    report = run_eval(
        questions=questions,
        units=units,
        provider_call=provider_call,
        retriever=_kbv5_retriever(args.kbv5_top_k) if provider_call is not None else None,
        model=model,
        seed=args.seed,
        token_budget=args.token_budget,
        previous=previous,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "runtime_exercised": report["runtime_exercised"],
                "provider_usage": report["provider_usage"],
                "arms": [
                    {k: arm[k] for k in ("arm", "sample_count", "fail_rate", "correct_rate", "semantic_score", "mean_total_tokens")}
                    for arm in report["arms"]
                ],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
