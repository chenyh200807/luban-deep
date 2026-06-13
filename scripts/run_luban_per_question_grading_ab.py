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
import sys
from typing import Any, Callable

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


async def _make_llm_judge(model: str | None, *, with_rag: bool):
    from deeptutor.services.llm import complete  # canonical single-authority LLM path

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
        # The canonical ``complete`` takes a positional ``prompt``; our single user
        # message's content carries the full JSON payload, so pass it as the prompt.
        prompt_text = messages[0]["content"]
        system_prompt = "你是严谨的一级建造师案例题阅卷官。只输出题目要求的 JSON,不要多余文字。"
        kwargs: dict[str, Any] = {"prompt": prompt_text, "system_prompt": system_prompt}
        if model:
            kwargs["model"] = model
        text = await complete(**kwargs)
        data = _parse_json_block(text if isinstance(text, str) else str(text))
        verdicts = {
            str(v.get("point_id")): str(v.get("verdict"))
            for v in (data.get("verdicts") or [])
            if v.get("point_id")
        }
        return {"score_pct": float(data.get("score_pct") or 0.0), "verdicts": verdicts, "oracle": False}
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


async def _run(objects, fixtures: dict[str, Any], judge, *, gap_margin: float) -> dict[str, Any]:
    total_by_q = {o["question_id"]: o["scoring_point_count"] for o in objects}
    rows: list[dict[str, Any]] = []
    for obj in objects:
        qid = obj["question_id"]
        contract = build_grading_contract(obj)
        blockers = validate_grading_contract(contract)
        if blockers:
            raise SystemExit(f"contract invalid for {qid}: {blockers}")
        total = len(contract["scoring_points"])
        for answer in fixtures.get(qid) or []:
            _validate_fixture(answer, contract)
            true_cov = round(_true_coverage(answer, total), 4)
            for arm in ARMS:
                result = judge(arm=arm, contract=contract, answer=answer)
                if asyncio.iscoroutine(result):
                    result = await result
                score = round(float(result["score_pct"]), 4)
                verdicts = result.get("verdicts") or {}
                self_consistency = detect_over_credit(
                    score_pct=score, point_verdicts=verdicts, contract=contract, gap_margin=gap_margin,
                )
                rows.append({
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
                })
    return _summarize(rows, gap_margin=gap_margin)


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [r for r in rows if r.get(key) is not None]
    return round(sum(1 for r in vals if r[key]) / len(vals), 4) if vals else None


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _summarize(rows: list[dict[str, Any]], *, gap_margin: float) -> dict[str, Any]:
    by_arm: dict[str, Any] = {}
    answer_types = sorted({r["answer_type"] for r in rows})
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        # over-credit only meaningful where the student actually missed something
        riskful = [r for r in arm_rows if r["true_coverage"] < 1.0]
        margin_sweep = {
            f"margin_{m}": _rate(
                [{"oc": (r["score_pct"] - r["true_coverage"] > m)} for r in riskful], "oc"
            )
            for m in MARGIN_SWEEP
        }
        by_arm[arm] = {
            "rows": len(arm_rows),
            "riskful_rows": len(riskful),
            "ground_truth_over_credit_rate": _rate(riskful, "ground_truth_over_credit"),
            "calibration_mae": _mean(arm_rows, "calibration_abs_error"),
            "false_hit_rate_mean": _mean(arm_rows, "false_hit_rate"),
            "over_credit_rate_by_answer_type": {
                t: _rate([r for r in riskful if r["answer_type"] == t], "ground_truth_over_credit")
                for t in answer_types
            },
            "over_credit_margin_sweep": margin_sweep,
        }
    return {
        "schema": "luban_per_question_grading_ab.v2",
        "review_only": True,
        "primary_metric": "ground_truth_over_credit_rate (score - true_coverage > margin)",
        "default_margin": gap_margin,
        "thesis": "arm_B_atomic_contract 的 over-credit 率应 < arm_A1_self_decompose < arm_A0_freestyle",
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

    report = asyncio.run(_run(objects, fixtures, judge, gap_margin=args.margin))
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
