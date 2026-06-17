#!/usr/bin/env python3
"""Stage 1 of the case-rubric source migration: full-bank compile + data-quality quarantine.

Compiles EVERY case_study exercise in the canonical exam bank (FINAL_CLEANED_EXAM_V*.json,
2015-2025) into a `luban_per_question_grading_object.v1`, runs the single-authority validator,
and QUARANTINES the data-quality failure cohort the design flagged (analysis-as-answer, AI
placeholder answers, null/zero score, validator blockers, and post-compile granularity collapse)
so corrupt rubrics never reach the flip set.

Offline / deterministic / REVIEW-ONLY: no LLM, no network, no DB, no production write. Output
goes to a gitignored artifacts dir: the compiled objects, a quarantine ledger (each exclusion
with a reason), a coverage report vs the live 174-qid production bank, and a summary.

This is Stage 1 of docs/plan/鲁班knowql/CASE_RUBRIC_SOURCE_MIGRATION_PLAN.md. It does NOT wire
anything into production — it produces the coverage + quarantine DATA that gates later stages.
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import re
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.per_question_grading_object import (  # noqa: E402
    compile_per_question_grading_object,
    validate_per_question_grading_object,
)

DEFAULT_EXAM_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库")
DEFAULT_BOOK_DIR = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强")
DEFAULT_OUT_DIR = REPO / "artifacts/luban_grading_artifacts/per_question_grading_object_full_compile_20260614"
PROD_BANK = REPO / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json"

# A high-value question collapsed to <=1 scoring point is a granularity-collapse (corrupt slice).
_GRANULARITY_MIN_SCORE = 8.0
# Sub-question / atomic markers the answer's own wording exposes — used to detect collapse.
_SUBQ_MARKERS = re.compile(r"(问题\s*\d|\n\s*\d{1,2}\s*[.．、)）]|不妥之处|【.{0,6}】|①|②|③|（\d+）|\(\d+\))")


def _load_textbook_chunks(book_dir: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    if not book_dir.exists():
        return chunks
    for path in sorted(book_dir.glob("FINAL_CLEANED_BOOK2026-*_fixed.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        blocks = payload.get("content_blocks") if isinstance(payload, dict) else payload
        for block in blocks or []:
            if isinstance(block, dict) and block.get("chunk_id") and block.get("content_markdown"):
                chunks.append(block)
    return chunks


def _enumerate_case_questions(exam_root: Path) -> list[dict[str, Any]]:
    """Every case_study exercise across all FINAL_CLEANED_EXAM_V*.json. qid = chunk_id::E<idx>."""
    out: list[dict[str, Any]] = []
    for f in sorted(glob.glob(str(exam_root / "*" / "FINAL_CLEANED_EXAM_V*.json"))):
        year = re.search(r"V(\d{4})", f).group(1)
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        for chunk in data.get("chunks", []):
            cid = str(chunk.get("chunk_id") or "")
            for idx, ex in enumerate(chunk.get("exercises") or []):
                if str(ex.get("type")) != "case_study":
                    continue
                qd = ex.get("question_data") or {}
                # NOTE: chunk_id repeats ACROSS years (it encodes the taxonomy code, not the
                # year), so {chunk_id}::E{idx} is NOT unique across the 2015-2025 bank — the
                # qid namespace must carry the year (this concretizes Stage 0e). The prod bank
                # qids drop the year, so cross-year collisions are a real namespace hazard.
                out.append({
                    "qid": f"{year}::{cid}::E{idx}", "prod_qid": f"{cid}::E{idx}",
                    "year": year, "chunk_id": cid, "idx": idx,
                    "stem": str(qd.get("stem") or ""),
                    "correct_answer": str(qd.get("correct_answer") or "").strip(),
                    "analysis": str(qd.get("analysis") or "").strip(),
                    "score": qd.get("score"),
                    "source_path": f,
                })
    return out


def _source_quarantine_reason(q: dict[str, Any]) -> str | None:
    """Pre-compile data-quality signals (corrupt source the new compiler must NOT compile)."""
    ca, an = q["correct_answer"], q["analysis"]
    if not ca:
        return "empty_answer"
    if q["score"] in (None, 0, 0.0):
        return "null_or_zero_score"
    if "【选项分析】" in ca or "【AI" in ca or "AI生成" in ca:
        return "ai_placeholder_answer"
    if ca.startswith("【解析") or ca.startswith("解析") or (ca == an and ca):
        return "analysis_as_answer"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-root", type=Path, default=DEFAULT_EXAM_ROOT)
    parser.add_argument("--book-dir", type=Path, default=DEFAULT_BOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    questions = _enumerate_case_questions(args.exam_root)
    textbook_chunks = _load_textbook_chunks(args.book_dir)
    prod_qids: set[str] = set()
    if PROD_BANK.exists():
        prod_qids = {str(r.get("qid")) for r in (json.loads(PROD_BANK.read_text("utf-8")).get("records") or [])}

    out_dir = args.out_dir
    (out_dir / "objects").mkdir(parents=True, exist_ok=True)
    compiled: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []

    for q in questions:
        reason = _source_quarantine_reason(q)
        if reason:
            quarantine.append({"qid": q["qid"], "year": q["year"], "reason": reason, "stage": "source"})
            continue
        try:
            obj = compile_per_question_grading_object(
                question_id=q["qid"], stem=q["stem"], correct_answer=q["correct_answer"],
                official_total_score=float(q["score"]), textbook_chunks=textbook_chunks,
                chunk_id=q["chunk_id"], official_analysis=q["analysis"] or None, source_path=q["source_path"],
            )
        except Exception as exc:  # noqa: BLE001 — compile crash = quarantine, not abort the bank
            quarantine.append({"qid": q["qid"], "year": q["year"], "reason": f"compile_error:{type(exc).__name__}:{str(exc)[:120]}", "stage": "compile"})
            continue
        blockers = validate_per_question_grading_object(obj)
        if blockers:
            quarantine.append({"qid": q["qid"], "year": q["year"], "reason": "validator_failed", "blockers": blockers[:8], "stage": "validate"})
            continue
        # post-compile granularity collapse: a high-value question crushed to <=1 point with a
        # multi-part answer is a corrupt slice (e.g. inline ；N. separator collapse).
        spc = obj.get("scoring_point_count") or 0
        total = float(obj.get("official_total_score") or 0)
        marker_count = len(_SUBQ_MARKERS.findall(q["correct_answer"]))
        if spc <= 1 and total >= _GRANULARITY_MIN_SCORE and marker_count >= 3:
            quarantine.append({"qid": q["qid"], "year": q["year"], "reason": "granularity_collapse",
                               "scoring_point_count": spc, "official_total_score": total, "answer_markers": marker_count, "stage": "post_compile"})
            continue
        obj["compile_excluded"] = False
        obj["prod_qid"] = q["prod_qid"]
        compiled.append(obj)
        (out_dir / "objects" / f"{q['qid'].replace('::', '__')}.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    from collections import Counter
    q_by_reason = Counter(x["reason"].split(":")[0] for x in quarantine)
    # compiled qids are year-unique; match prod (year-less) via the prod_qid carried on each obj.
    compiled_qids = {o["question_id"] for o in compiled}
    compiled_prod_qids = {o.get("prod_qid") for o in compiled if o.get("prod_qid")}
    summary = {
        "schema": "luban_per_question_full_compile.v1",
        "review_only": True,
        "total_case_study": len(questions),
        "compiled_ok": len(compiled),
        "quarantined": len(quarantine),
        "clean_rate": round(len(compiled) / max(len(questions), 1), 4),
        "quarantine_by_reason": dict(q_by_reason),
        "quarantine_by_year": dict(Counter(x["year"] for x in quarantine)),
        "coverage_vs_prod_bank": {
            "prod_bank_qids": len(prod_qids),
            "compiled_objects": len(compiled),
            "compiled_distinct_year_unique_qids": len(compiled_qids),
            "prod_covered_by_new": len(prod_qids & compiled_prod_qids),
            "prod_dropped_by_new": sorted(prod_qids - compiled_prod_qids)[:50],
            "prod_dropped_count": len(prod_qids - compiled_prod_qids),
            "new_not_in_prod_count": len(compiled_prod_qids - prod_qids),
        },
        "point_count_stats": {
            "total_scoring_points": sum(o.get("scoring_point_count") or 0 for o in compiled),
            "mean_points_per_q": round(sum(o.get("scoring_point_count") or 0 for o in compiled) / max(len(compiled), 1), 2),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "quarantine_ledger.json").write_text(json.dumps(quarantine, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "coverage_vs_prod_bank"}, ensure_ascii=False, indent=2))
    print("coverage_vs_prod_bank:", json.dumps({k: v for k, v in summary["coverage_vs_prod_bank"].items() if k != "prod_dropped_by_new"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
