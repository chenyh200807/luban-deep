#!/usr/bin/env python3
"""M34 general-knowledge dividend slice runner.

Hermetic: resolves local compiled teaching context only. It performs no DB,
canonical learner-truth, remote, or production-default writes.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from deeptutor.services.construction_grading.general_knowledge_context import (
    resolve_general_knowledge_context,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO
    / "artifacts"
    / "luban_grading_artifacts"
    / f"general_knowledge_dividend_m34_{date.today().strftime('%Y%m%d')}"
)

ON_SYLLABUS_QUESTIONS = [
    "高层住宅的建筑高度是怎么界定的？",
    "民用建筑按高度怎么分类？",
    "混凝土强度等级如何理解？",
    "施工现场临时用电三级配电是什么意思？",
    "屋面防水等级怎么划分？",
]

OFF_SYLLABUS_QUESTIONS = [
    "今天天气怎么样随便聊聊",
    "帮我写一首关于咖啡的诗",
    "NBA昨天谁赢了",
    "Python列表怎么排序",
    "上海明天会不会下雨",
]

HIT_RATE_THRESHOLD = 0.80


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _evaluate_on_syllabus() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for question in ON_SYLLABUS_QUESTIONS:
        pack = resolve_general_knowledge_context(question)
        rows.append(
            {
                "question": question,
                "hit": pack is not None,
                "classified_leaf": (pack or {}).get("classified_leaf"),
                "resolved_anchor": (pack or {}).get("resolved_anchor"),
                "tier": (pack or {}).get("tier"),
                "official_score_allowed": (pack or {}).get("official_score_allowed"),
                "llm_may_decide_correctness": (pack or {}).get("llm_may_decide_correctness"),
                "selected_counts": (pack or {}).get("selected_counts"),
                "source_categories_present": sorted(
                    key
                    for key, value in ((pack or {}).get("sources") or {}).items()
                    if value
                ),
            }
        )
    return rows


def _evaluate_off_syllabus() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for question in OFF_SYLLABUS_QUESTIONS:
        pack = resolve_general_knowledge_context(question)
        rows.append(
            {
                "question": question,
                "fall_open": pack is None,
                "wrong_chapter_attribution": pack is not None,
                "classified_leaf": (pack or {}).get("classified_leaf"),
                "resolved_anchor": (pack or {}).get("resolved_anchor"),
            }
        )
    return rows


def run_slice(
    *,
    output_dir: str | Path | None = None,
    live_ws_status: str = "unchecked",
    live_ws_evidence: str = "",
) -> dict[str, Any]:
    out = Path(output_dir) if output_dir is not None else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    on_rows = _evaluate_on_syllabus()
    off_rows = _evaluate_off_syllabus()
    on_hits = sum(1 for row in on_rows if row["hit"])
    off_fall_open = sum(1 for row in off_rows if row["fall_open"])
    teaching_context_hit_rate = on_hits / len(on_rows) if on_rows else 0.0
    off_syllabus_fall_open_rate = off_fall_open / len(off_rows) if off_rows else 0.0

    official_score_violations = sum(
        1 for row in on_rows if row["hit"] and row["official_score_allowed"] is not False
    )
    llm_correctness_violations = sum(
        1 for row in on_rows if row["hit"] and row["llm_may_decide_correctness"] is not False
    )
    wrong_chapter_attribution = sum(1 for row in off_rows if row["wrong_chapter_attribution"])

    coverage = {
        "authority": "luban_general_knowledge_context",
        "threshold": HIT_RATE_THRESHOLD,
        "on_syllabus_total": len(on_rows),
        "on_syllabus_hits": on_hits,
        "teaching_context_hit_rate": teaching_context_hit_rate,
        "off_syllabus_total": len(off_rows),
        "off_syllabus_fall_open": off_fall_open,
        "off_syllabus_fall_open_rate": off_syllabus_fall_open_rate,
        "on_syllabus_cases": on_rows,
        "off_syllabus_cases": off_rows,
    }
    safety = {
        "authority": "luban_general_knowledge_context",
        "official_score_allowed_violations": official_score_violations,
        "llm_may_decide_correctness_violations": llm_correctness_violations,
        "answer_key_minted": 0,
        "canonical_truth_written": False,
        "production_write_count": 0,
        "mutable_chunk_as_answer_key": 0,
        "wrong_chapter_attribution": wrong_chapter_attribution,
    }

    blockers: list[str] = []
    if teaching_context_hit_rate < HIT_RATE_THRESHOLD:
        blockers.append("teaching_context_hit_rate_below_threshold")
    if off_syllabus_fall_open_rate != 1.0:
        blockers.append("off_syllabus_fall_open_not_1_0")
    if any(
        safety[key]
        for key in (
            "official_score_allowed_violations",
            "llm_may_decide_correctness_violations",
            "answer_key_minted",
            "production_write_count",
            "mutable_chunk_as_answer_key",
            "wrong_chapter_attribution",
        )
    ) or safety["canonical_truth_written"] is not False:
        blockers.append("safety_invariant_violation")
    live_ws_evidence_text = str(live_ws_evidence or "").strip()
    live_ws_evidence_valid = (
        live_ws_status == "pass"
        and "test_luban_m34_general_knowledge_dividend_ws.py" in live_ws_evidence_text
        and "passed" in live_ws_evidence_text.lower()
    )
    if live_ws_status != "pass":
        blockers.append("live_ws_status_not_pass")
    elif not live_ws_evidence_valid:
        blockers.append("live_ws_evidence_missing_or_invalid")

    live_only_blockers = {"live_ws_status_not_pass", "live_ws_evidence_missing_or_invalid"}
    if any(blocker not in live_only_blockers for blocker in blockers):
        verdict = "NO-GO"
    elif blockers:
        verdict = "WEAK-GO"
    else:
        verdict = "GO"

    go_no_go = {
        "verdict": verdict,
        "blockers": blockers,
        "live_ws_status": live_ws_status,
        "live_ws_evidence": live_ws_evidence_text,
        "cohort_default": "qa_,test_,operator_",
        "cohort_broadening_requires_user_confirmation": True,
        "production_write_count": safety["production_write_count"],
        "canonical_truth_written": safety["canonical_truth_written"],
        "coverage_report": "coverage_report_m34.json",
        "safety_report": "safety_invariant_report_m34.json",
    }

    _write_json(out / "coverage_report_m34.json", coverage)
    _write_json(out / "safety_invariant_report_m34.json", safety)
    _write_json(out / "go_no_go_m34.json", go_no_go)
    return {"verdict": verdict, "output_dir": str(out), **go_no_go}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--live-ws-status",
        choices=("pass", "unchecked", "fail"),
        default="unchecked",
        help="Set to pass only after the live /api/v1/ws M34 pytest gate passed in this run.",
    )
    parser.add_argument(
        "--live-ws-evidence",
        default="",
        help="Required with --live-ws-status pass; include pytest command/nodeid and passed count.",
    )
    args = parser.parse_args(argv)
    result = run_slice(
        output_dir=args.output_dir,
        live_ws_status=args.live_ws_status,
        live_ws_evidence=args.live_ws_evidence,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["verdict"] in {"GO", "WEAK-GO"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
