#!/usr/bin/env python3
"""Per-question grading A/B (review-only): does the compiled atomic contract 摁死 over-credit?

Thin CLI over the fat skills
``deeptutor.services.construction_grading.per_question_grading_object`` (compile +
``build_grading_contract``, where G2 is wired on real data) and
``...per_question_grading_judge`` (controlled answers + over-credit gate).

The thesis (KnowQL Phase B): forcing the judge to adjudicate every atomic OFFICIAL point
separately reduces the measured ~20% over-credit (a high score while an official point is
missed), vs a freestyle judge that scores holistically.

Two arms, same student answer:
  * arm_A_freestyle      — judge sees the official reference answer, returns a 0-1 score.
  * arm_B_atomic_contract — judge sees the atomic official checklist, MUST return one
    verdict per point_id (+ evidence cite) and score = fraction hit.

Measurement uses CONTROLLED student answers with EXACT ground truth (atomic slices kept or
dropped), so over-credit = (score ≥ 0.95 AND the student actually omitted an official
point) needs no human labelling.

``--dry-run`` (default when no LLM key) runs a perfect-judge ORACLE end-to-end: it proves
the plumbing and that arm B is over-credit-safe BY CONSTRUCTION. ``--live`` runs the real
LLM judge for both arms (needs an LLM key) and reports each arm's over-credit rate.

Nothing here writes canonical truth, official scores, a DB, or a production default.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from run_luban_per_question_grading_object_compile import (  # noqa: E402  (sys.path set above)
    DEFAULT_BOOK_DIR,
    DEFAULT_EXAM_ROOT,
    _load_textbook_chunks,
    compile_selected,
)

from deeptutor.services.construction_grading.per_question_grading_judge import (
    OVER_CREDIT_GAP_MARGIN,
    OVER_CREDIT_HIGH_THRESHOLD,
    ControlledAnswer,
    candidate_coverage_score,
    detect_over_credit,
    make_controlled_student_answers,
    oracle_verdicts,
)
from deeptutor.services.construction_grading.per_question_grading_object import (
    build_grading_contract,
    validate_grading_contract,
)

DEFAULT_OUT_DIR = REPO / "artifacts/luban_grading_artifacts/per_question_grading_ab_20260613"
ARM_A = "arm_A_freestyle"
ARM_B = "arm_B_atomic_contract"


def _arm_a_messages(*, stem: str, official_answer: str, student_answer: str) -> list[dict[str, str]]:
    payload = {
        "task": "你是一级建造师案例题阅卷官。对照官方参考答案给学生作答打分。",
        "stem": stem,
        "official_reference_answer": official_answer,
        "student_answer": student_answer,
        "instruction": "只输出 JSON: {\"score_pct\": 0..1 的小数, \"reason\": \"简短\"}。",
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
            "命中(hit)必须在 evidence_span 引用学生作答里的逐字证据。"
            "score_pct = 命中(hit)点数 / 总点数。"
            "只输出 JSON: {\"verdicts\":[{\"point_id\":\"..\",\"verdict\":\"..\",\"evidence_span\":\"..\"}],"
            "\"score_pct\":0..1}。"
        ),
    }
    return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


def _parse_json_block(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"no JSON object in judge output: {text[:160]!r}")
    return json.loads(match.group(0))


def _ground_truth_over_credit(
    score_pct: float, answer: ControlledAnswer, *, gap_margin: float
) -> bool:
    """The honest over-credit measure: the score MATERIALLY exceeds the student's true
    coverage (covered / total atomic official points), known by construction. A score
    that tracks coverage — even a high one for 23/24 — is honest, not over-credit."""
    total = len(answer.covered_point_ids) + len(answer.missing_point_ids)
    if total == 0:
        return False
    coverage = len(answer.covered_point_ids) / total
    return bool(score_pct - coverage > gap_margin)


def _make_oracle_judge() -> Callable[..., dict[str, Any]]:
    """Perfect-judge oracle for dry-run: arm B HITs covered points (so its score honestly
    equals coverage). Arm A is given the same coverage-honest score — the oracle cannot
    over-credit, which is exactly why dry-run proves PLUMBING, not the thesis (an LLM
    freestyle judge is what over-credits)."""
    def judge(*, arm: str, contract: dict[str, Any], answer: ControlledAnswer) -> dict[str, Any]:
        verdicts = oracle_verdicts(contract, answer)
        score = candidate_coverage_score(verdicts, contract)
        return {"score_pct": score, "verdicts": verdicts, "oracle": True}
    return judge


async def _make_llm_judge(model: str | None):
    from deeptutor.services.llm import complete  # canonical single-authority LLM path

    async def judge(*, arm: str, contract: dict[str, Any], answer: ControlledAnswer) -> dict[str, Any]:
        if arm == ARM_A:
            messages = _arm_a_messages(
                stem=str(contract.get("stem") or ""),
                official_answer="\n".join(sp.get("official_slice") or "" for sp in contract["scoring_points"]),
                student_answer=answer.student_answer,
            )
        else:
            messages = _arm_b_messages(contract=contract, student_answer=answer.student_answer)
        text = await complete(messages=messages, model=model) if model else await complete(messages=messages)
        data = _parse_json_block(text if isinstance(text, str) else str(text))
        verdicts = {
            str(v.get("point_id")): str(v.get("verdict"))
            for v in (data.get("verdicts") or [])
        }
        return {"score_pct": float(data.get("score_pct") or 0.0), "verdicts": verdicts, "oracle": False}
    return judge


async def _run(
    objects: list[dict[str, Any]], judge, *, threshold: float, gap_margin: float
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for obj in objects:
        contract = build_grading_contract(obj)
        blockers = validate_grading_contract(contract)
        if blockers:
            raise SystemExit(f"contract invalid for {obj['question_id']}: {blockers}")
        for answer in make_controlled_student_answers(obj):
            for arm in (ARM_A, ARM_B):
                result = judge(arm=arm, contract=contract, answer=answer)
                if asyncio.iscoroutine(result):
                    result = await result
                score = float(result["score_pct"])
                gate = detect_over_credit(
                    score_pct=score, point_verdicts=result.get("verdicts") or {},
                    contract=contract, high_threshold=threshold, gap_margin=gap_margin,
                )
                rows.append({
                    "question_id": obj["question_id"],
                    "answer_label": answer.label,
                    "arm": arm,
                    "score_pct": round(score, 4),
                    "ground_truth_missing": list(answer.missing_point_ids),
                    "ground_truth_over_credit": _ground_truth_over_credit(
                        score, answer, gap_margin=gap_margin
                    ),
                    "verdict_based_over_credit": gate["over_credit"],
                    "score_coverage_gap": gate["score_coverage_gap"],
                    "oracle": result.get("oracle", False),
                })
    return _summarize(rows, threshold=threshold)


def _summarize(rows: list[dict[str, Any]], *, threshold: float) -> dict[str, Any]:
    by_arm: dict[str, dict[str, Any]] = {}
    for arm in (ARM_A, ARM_B):
        arm_rows = [r for r in rows if r["arm"] == arm]
        partial = [r for r in arm_rows if r["ground_truth_missing"]]
        gt_over = [r for r in partial if r["ground_truth_over_credit"]]
        by_arm[arm] = {
            "rows": len(arm_rows),
            "partial_answer_rows": len(partial),
            "ground_truth_over_credit_count": len(gt_over),
            "ground_truth_over_credit_rate": (len(gt_over) / len(partial)) if partial else None,
            "mean_score_pct": round(sum(r["score_pct"] for r in arm_rows) / len(arm_rows), 4) if arm_rows else None,
        }
    return {
        "schema": "luban_per_question_grading_ab.v1",
        "review_only": True,
        "over_credit_high_threshold": threshold,
        "thesis": "arm_B_atomic_contract 的 over-credit 率应 ≤ arm_A_freestyle",
        "by_arm": by_arm,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-root", type=Path, default=DEFAULT_EXAM_ROOT)
    parser.add_argument("--book-dir", type=Path, default=DEFAULT_BOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--live", action="store_true", help="use the real LLM judge (needs an LLM key)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--threshold", type=float, default=OVER_CREDIT_HIGH_THRESHOLD)
    args = parser.parse_args()

    textbook_chunks = _load_textbook_chunks(args.book_dir)
    objects = compile_selected(exam_root=args.exam_root, textbook_chunks=textbook_chunks)

    if args.live:
        judge = asyncio.run(_make_llm_judge(args.model))
        mode = "live_llm"
    else:
        judge = _make_oracle_judge()
        mode = "dry_run_oracle"

    report = asyncio.run(
        _run(objects, judge, threshold=args.threshold, gap_margin=OVER_CREDIT_GAP_MARGIN)
    )
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
