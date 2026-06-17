#!/usr/bin/env python3
"""R4: cached_judge_replay A/B — artifact-first grading vs ai-governed gold.

The R2 gold pack carries, per answer row, the multi-model adjudicated
``gold_point_matches`` (hit/partial/miss per scoring point) and the summed
``gold_score``. R4 re-grades every gold row *artifact-first*: the fixture
scoring points ARE the compiled artifact under test (exam-reference-answer
provenance), graded by ``rubric_grader_v1.grade_with_rubric`` with a single
injected judge (live = ``deepseek-chat`` batch, hermetic = a deterministic
stub). The judge model is the grading runtime's own LLM — NOT a gold panelist
— so this is a true replay of what production grading would award.

The prediction is then scored against gold:

  - point_precision / point_recall over *hit* predictions (the runtime's
    awarded-hit set vs the gold hit set);
  - score_mae = mean |predicted_score - gold_score| across rows.

Gates (plan R4): precision >= 0.90, recall >= 0.90, score_mae <= 1.0, and the
run must beat the historical failure line (0.5267 point-hit agreement /
4.6091 MAE). Live judge outputs are cached to disk (provider/model/cache
provenance recorded) so reruns and CI never re-bill or call providers.

Safety stays all-zero: no DB / remote / RAG / canonical-truth writes,
``official_score_allowed=false``. This runner only reads the gold pack and the
fixture manifest and writes a single report.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.rubric_grader_v1 import (  # noqa: E402
    HIT,
    PARTIAL,
    grade_with_rubric,
)
from scripts.audit_luban_m35_label_authority import audit as audit_label_authority  # noqa: E402

JudgeFn = Callable[[dict[str, Any], str], dict[str, Any]]

SCHEMA_VERSION = "luban_m35_r4_cached_ab.v1"
TIER = "cached_judge_replay"
DEFAULT_GOLD_DIR = REPO / "tests/fixtures/luban_m35_case_scoring_gold_v1"
DEFAULT_FIXTURE_DIR = REPO / "tests/fixtures/luban_m35_fastapi_case_subquestions_20q_100a"

POINT_PRECISION_THRESHOLD = 0.90
POINT_RECALL_THRESHOLD = 0.90
SCORE_MAE_THRESHOLD = 1.0
HISTORICAL_POINT_HIT_AGREEMENT = 0.5267
HISTORICAL_SCORE_MAE = 4.6091

# Mirror the R2 gold scoring: hit -> full, partial -> half, miss -> 0. The
# artifact-first prediction must be scored on the SAME scale as the gold so
# score_mae is comparable.
_PARTIAL_CREDIT_RATIO = 0.5
LIVE_ENV_FLAG = "LUBAN_M35_R4_LIVE"


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _rubric_points(question: dict[str, Any]) -> list[dict[str, Any]]:
    """Project a fixture question's scoring_points into grade_with_rubric points.

    The fixture carries ``criterion`` / ``max_score`` / ``policy_type``; map them
    to the grader's ``text`` / ``score`` / ``policy`` (identity on point_id so
    the prediction aligns to the gold point matches by id).
    """
    points: list[dict[str, Any]] = []
    for raw in question.get("scoring_points") or []:
        if not isinstance(raw, dict):
            continue
        point_id = str(raw.get("point_id") or "").strip()
        text = str(raw.get("criterion") or raw.get("text") or "").strip()
        score = raw.get("max_score")
        if not point_id or not text or score is None:
            continue
        points.append(
            {
                "point_id": point_id,
                "text": text,
                "score": float(score),
                "policy": str(raw.get("policy_type") or "qualitative"),
                "required_terms": list(raw.get("required_terms") or []),
            }
        )
    return points


def _awarded(status: str, max_score: float) -> float:
    if status == HIT:
        return max_score
    if status == PARTIAL:
        return round(max_score * _PARTIAL_CREDIT_RATIO, 4)
    return 0.0


def _cached_judge(
    judge_fn: JudgeFn, cache: dict[str, dict[str, Any]], model: str
) -> JudgeFn:
    """Wrap a judge so identical (point, answer) prompts hit a persisted cache."""

    def judge(point: dict[str, Any], answer: str) -> dict[str, Any]:
        key = hashlib.sha256(
            json.dumps(
                {
                    "model": model,
                    "point_id": str(point.get("point_id") or ""),
                    "text": str(point.get("text") or ""),
                    "policy": str(point.get("policy") or ""),
                    "answer": str(answer or ""),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        if key in cache:
            return cache[key]
        verdict = judge_fn(point, answer) or {}
        cache[key] = verdict
        return verdict

    return judge


def _grade_row(
    row: dict[str, Any],
    question: dict[str, Any],
    judge_fn: JudgeFn,
) -> dict[str, Any]:
    """Grade one gold row artifact-first and compare to its gold matches."""
    points = _rubric_points(question)
    event = grade_with_rubric(
        qid=str(row.get("question_id") or ""),
        student_answer=str(row.get("student_answer") or ""),
        rubric_points=points,
        judge_fn=judge_fn,
        student_id=str(row.get("student_id") or ""),
    )
    predicted_hits = {
        str(p.get("point_id") or "")
        for p in event.get("scoring_points") or []
        if p.get("hit") == HIT
    }
    gold_hits = {
        str(p.get("point_id") or "")
        for p in row.get("gold_point_matches") or []
        if p.get("status") == HIT
    }
    predicted_score = round(float(event.get("awarded_score") or 0.0), 4)
    gold_score = round(float(row.get("gold_score") or 0.0), 4)
    return {
        "answer_id": str(row.get("answer_id") or ""),
        "question_id": str(row.get("question_id") or ""),
        "predicted_hits": predicted_hits,
        "gold_hits": gold_hits,
        "predicted_score": predicted_score,
        "gold_score": gold_score,
        "abs_score_error": round(abs(predicted_score - gold_score), 4),
    }


def _metrics(graded: list[dict[str, Any]]) -> dict[str, Any]:
    true_positive = 0
    predicted_positive = 0
    gold_positive = 0
    abs_errors: list[float] = []
    for item in graded:
        predicted = item["predicted_hits"]
        gold = item["gold_hits"]
        true_positive += len(predicted & gold)
        predicted_positive += len(predicted)
        gold_positive += len(gold)
        abs_errors.append(item["abs_score_error"])
    point_precision = (
        round(true_positive / predicted_positive, 6) if predicted_positive else 0.0
    )
    point_recall = round(true_positive / gold_positive, 6) if gold_positive else 0.0
    score_mae = round(sum(abs_errors) / len(abs_errors), 6) if abs_errors else 0.0
    point_hit_agreement = (
        round(2 * true_positive / (predicted_positive + gold_positive), 6)
        if (predicted_positive + gold_positive)
        else 0.0
    )
    return {
        "point_precision": point_precision,
        "point_recall": point_recall,
        "score_mae": score_mae,
        "point_hit_agreement": point_hit_agreement,
        "true_positive_points": true_positive,
        "predicted_positive_points": predicted_positive,
        "gold_positive_points": gold_positive,
        "graded_row_count": len(graded),
    }


def build_report(
    *,
    answers_path: Path,
    manifest_path: Path,
    judge_fn: JudgeFn,
    judge_model: str,
    cache_path: Path | None = None,
    cache_provenance: str = "hermetic",
) -> dict[str, Any]:
    rows = _read_jsonl(answers_path)
    manifest = _read_json(manifest_path)
    questions_by_id = {
        str(q.get("question_id") or ""): q for q in manifest.get("questions") or []
    }

    cache: dict[str, dict[str, Any]] = {}
    if cache_path is not None and Path(cache_path).is_file():
        cache = _read_json(cache_path)
    cache_size_before = len(cache)
    judge = _cached_judge(judge_fn, cache, judge_model)

    graded: list[dict[str, Any]] = []
    skipped: list[str] = []
    for row in rows:
        question = questions_by_id.get(str(row.get("question_id") or ""))
        if not question or not question.get("scoring_points") or not row.get("gold_point_matches"):
            skipped.append(str(row.get("answer_id") or ""))
            continue
        graded.append(_grade_row(row, question, judge))

    if cache_path is not None:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(
            json.dumps(cache, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    metrics = _metrics(graded)
    precision_pass = metrics["point_precision"] >= POINT_PRECISION_THRESHOLD
    recall_pass = metrics["point_recall"] >= POINT_RECALL_THRESHOLD
    mae_pass = metrics["score_mae"] <= SCORE_MAE_THRESHOLD
    gate_results = {
        "point_precision_pass": precision_pass,
        "point_recall_pass": recall_pass,
        "score_mae_pass": mae_pass,
        "all_thresholds_pass": precision_pass and recall_pass and mae_pass,
        "thresholds": {
            "point_precision": POINT_PRECISION_THRESHOLD,
            "point_recall": POINT_RECALL_THRESHOLD,
            "score_mae": SCORE_MAE_THRESHOLD,
        },
    }
    historical_comparison = {
        "historical_point_hit_agreement": HISTORICAL_POINT_HIT_AGREEMENT,
        "historical_score_mae": HISTORICAL_SCORE_MAE,
        "current_point_hit_agreement": metrics["point_hit_agreement"],
        "current_score_mae": metrics["score_mae"],
        "point_hit_agreement_beats_historical": metrics["point_hit_agreement"]
        > HISTORICAL_POINT_HIT_AGREEMENT,
        "score_mae_beats_historical": metrics["score_mae"] < HISTORICAL_SCORE_MAE,
    }

    label_audit = audit_label_authority(Path(answers_path))

    return {
        "schema_version": SCHEMA_VERSION,
        "tier": TIER,
        "official_score_allowed": False,
        "fixture": {
            "answers_path": str(answers_path),
            "manifest_path": str(manifest_path),
            "row_count": len(rows),
            "graded_row_count": len(graded),
            "skipped_answer_ids": skipped,
        },
        "judge": {
            "model": judge_model,
            "cache_provenance": cache_provenance,
            "cache_path": str(cache_path) if cache_path is not None else None,
            "cache_entries_before": cache_size_before,
            "cache_entries_after": len(cache),
            "cache_new_entries": len(cache) - cache_size_before,
        },
        "metrics": metrics,
        "gate_results": gate_results,
        "historical_comparison": historical_comparison,
        "label_audit": label_audit,
        "safety": {
            "db_write_count": 0,
            "remote_write_count": 0,
            "production_write_count": 0,
            "canonical_truth_written": False,
            "rag_chunk_as_answer_key": 0,
            "provider_call_count": len(cache) - cache_size_before,
        },
        "notes": [
            "artifact-first prediction graded by rubric_grader_v1 with a single judge",
            "judge is the grading runtime LLM, not a gold panelist (true replay)",
            "scores mirror R2 gold scale (hit=full, partial=half, miss=0)",
        ],
    }


def _build_live_judge(model: str) -> tuple[JudgeFn, str]:
    """Build a live deepseek-chat batch judge behind the env opt-in.

    Returns ``(judge_fn, provenance)``. The judge wraps the same DeepSeek
    chat-completions transport the gold pipeline uses (``m35_gold_judges``),
    re-shaped to the ``rubric_grader_v1`` per-point judge contract.
    """
    from scripts.m35_gold_judges import (
        DEEPSEEK_DEFAULT_BASE_URL,
        JudgeStats,
        load_dotenv_file,
        DOTENV_PATH,
        make_deepseek_judge,
    )

    merged: dict[str, str] = {**load_dotenv_file(DOTENV_PATH), **dict(os.environ)}
    api_key = str(merged.get("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("live R4 requires DEEPSEEK_API_KEY")
    stats = JudgeStats()
    base_judge = make_deepseek_judge(
        api_key, stats, base_url=str(merged.get("DEEPSEEK_BASE_URL") or "").strip() or None
    )

    def judge(point: dict[str, Any], answer: str) -> dict[str, Any]:
        # m35 judge contract: (point, answer, anchor) -> {verdict, evidence_span}
        anchor = {"question_id": "", "stem": "", "total_score": point.get("score")}
        gold_point = {
            "criterion": point.get("text"),
            "max_score": point.get("score"),
            "required_terms": point.get("required_terms") or [],
        }
        out = base_judge(gold_point, answer, anchor)
        verdict = str(out.get("verdict") or "")
        if verdict not in (HIT, PARTIAL, "miss"):
            return {"status": "miss", "low_confidence": True}
        return {
            "status": verdict,
            "evidence_span": str(out.get("evidence_span") or ""),
            "partial_ratio": _PARTIAL_CREDIT_RATIO if verdict == PARTIAL else (1.0 if verdict == HIT else 0.0),
        }

    return judge, f"live_deepseek:{DEEPSEEK_DEFAULT_BASE_URL}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", type=Path, default=DEFAULT_GOLD_DIR / "student_answers.jsonl")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_FIXTURE_DIR / "manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--judge-model", default="deepseek-chat")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.live and os.environ.get(LIVE_ENV_FLAG) == "1":
        judge_fn, provenance = _build_live_judge(args.judge_model)
    else:
        raise SystemExit(
            f"R4 grading requires --live and {LIVE_ENV_FLAG}=1 "
            "(or call build_report directly with an injected judge)"
        )

    report = build_report(
        answers_path=args.answers,
        manifest_path=args.manifest,
        judge_fn=judge_fn,
        judge_model=args.judge_model,
        cache_path=args.cache,
        cache_provenance=provenance,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if report["gate_results"]["all_thresholds_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
