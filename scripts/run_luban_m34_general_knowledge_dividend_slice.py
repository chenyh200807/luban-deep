#!/usr/bin/env python3
"""M34 general-knowledge dividend slice runner.

Hermetic: resolves local compiled teaching context only. It performs no DB,
canonical learner-truth, remote, or production-default writes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from deeptutor.services.compiled_knowledge.general_knowledge import (
    build_general_knowledge_query_plan,
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
    "施工现场临时用电三级配电是什么意思？",
    "混凝土施工缝应该怎么留置？",
    "土方回填压实系数怎么控制？",
    "泥浆护壁灌注桩常见质量问题有哪些？",
    "施工合同索赔成立条件是什么？",
    "脚手架连墙件设置有什么要求？",
    "屋面防水等级怎么区分？",
]

LOW_CONFIDENCE_ON_SYLLABUS_QUESTIONS = [
    "建筑防火分区面积怎么理解？",
    "建筑耐火等级怎么划分？",
    "双代号网络计划总时差怎么算？",
    "砌体结构拉结筋有什么要求？",
    "模板起拱什么时候需要？",
    "临边洞口防护怎么做？",
]

CALIBRATION_CASES = [
    {"question": "高层住宅的建筑高度是怎么界定的？", "expected": "hit", "path_terms": ["高层住宅"]},
    {"question": "施工现场临时用电三级配电是什么意思？", "expected": "hit", "path_terms": ["临时用电"]},
    {"question": "混凝土施工缝应该怎么留置？", "expected": "hit", "path_terms": ["施工缝"]},
    {"question": "土方回填压实系数怎么控制？", "expected": "hit", "path_terms": ["土方回填"]},
    {"question": "泥浆护壁灌注桩常见质量问题有哪些？", "expected": "hit", "path_terms": ["灌注桩"]},
    {"question": "施工合同索赔成立条件是什么？", "expected": "hit", "path_terms": ["索赔"]},
    {"question": "脚手架连墙件设置有什么要求？", "expected": "hit", "path_terms": ["连墙件"]},
    {"question": "屋面防水等级怎么区分？", "expected": "hit", "path_terms": ["屋面", "防水"]},
    {"question": "建筑防火分区面积怎么理解？", "expected": "open"},
    {"question": "建筑耐火等级怎么划分？", "expected": "open"},
    {"question": "双代号网络计划总时差怎么算？", "expected": "open"},
    {"question": "砌体结构拉结筋有什么要求？", "expected": "open"},
    {"question": "模板起拱什么时候需要？", "expected": "open"},
    {"question": "临边洞口防护怎么做？", "expected": "open"},
    {"question": "高强螺栓摩擦面处理要点是什么？", "expected": "open"},
    {"question": "抹灰空鼓开裂怎么预防？", "expected": "open"},
    {"question": "外墙保温施工有哪些质量控制点？", "expected": "open"},
    {"question": "分部工程质量验收谁组织？", "expected": "open"},
    {"question": "今天天气怎么样随便聊聊", "expected": "open"},
    {"question": "帮我写一首关于咖啡的诗", "expected": "open"},
    {"question": "NBA昨天谁赢了", "expected": "open"},
    {"question": "Python列表怎么排序", "expected": "open"},
    {"question": "上海明天会不会下雨", "expected": "open"},
]

OFF_SYLLABUS_QUESTIONS = [
    "今天天气怎么样随便聊聊",
    "帮我写一首关于咖啡的诗",
    "NBA昨天谁赢了",
    "Python列表怎么排序",
    "上海明天会不会下雨",
]

HIT_RATE_THRESHOLD = 0.80
LIVE_WS_GATE_COMMAND_TEXT = (
    "python -m pytest tests/integration/test_luban_m34_general_knowledge_dividend_ws.py -q"
)
LIVE_WS_GATE_COMMAND = (
    sys.executable,
    "-m",
    "pytest",
    "tests/integration/test_luban_m34_general_knowledge_dividend_ws.py",
    "-q",
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _tail(text: str, *, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _run_live_ws_gate() -> dict[str, Any]:
    proc = subprocess.run(
        LIVE_WS_GATE_COMMAND,
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
    return {
        "live_ws_status": "pass" if proc.returncode == 0 else "fail",
        "live_ws_command": LIVE_WS_GATE_COMMAND_TEXT,
        "live_ws_exit_code": proc.returncode,
        "live_ws_evidence": (
            f"{LIVE_WS_GATE_COMMAND_TEXT} => exit_code={proc.returncode}\n{_tail(output)}"
        ).strip(),
    }


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


def _evaluate_low_confidence_on_syllabus() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for question in LOW_CONFIDENCE_ON_SYLLABUS_QUESTIONS:
        pack = resolve_general_knowledge_context(question)
        rows.append(
            {
                "question": question,
                "fall_open": pack is None,
                "wrong_chapter_attribution": pack is not None,
                "classified_leaf": (pack or {}).get("classified_leaf"),
                "resolved_anchor": (pack or {}).get("resolved_anchor"),
                "confidence": (pack or {}).get("confidence"),
            }
        )
    return rows


def _evaluate_calibration_cases() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in CALIBRATION_CASES:
        question = str(case.get("question") or "")
        expected = str(case.get("expected") or "")
        path_terms = [str(term) for term in (case.get("path_terms") or [])]
        pack = resolve_general_knowledge_context(question)
        leaf_name_path = str((pack or {}).get("leaf_name_path") or "")
        hit = pack is not None
        path_ok = all(term in leaf_name_path for term in path_terms)
        passed = (hit and path_ok) if expected == "hit" else not hit
        rows.append(
            {
                "question": question,
                "expected": expected,
                "passed": passed,
                "hit": hit,
                "path_terms": path_terms,
                "leaf_name_path": leaf_name_path,
                "classified_leaf": (pack or {}).get("classified_leaf"),
                "confidence": (pack or {}).get("confidence"),
            }
        )
    return rows


def _build_compiler_source_work_orders() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for case in CALIBRATION_CASES:
        question = str(case.get("question") or "")
        plan = build_general_knowledge_query_plan(question, top_k=12)
        for candidate in plan.get("candidates") or []:
            negative = candidate.get("negative_evidence") or []
            if not any(marker in negative for marker in ("source_path_conflict", "primary_path_mismatch")):
                continue
            source_hits = candidate.get("source_hits") or []
            if not source_hits:
                continue
            key = (question, str(candidate.get("node_code") or ""))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "authority": "luban_general_knowledge_context",
                    "work_order_type": "source_path_conflict",
                    "status": "candidate_only_needs_compiler_review",
                    "question": question,
                    "intent": plan.get("intent"),
                    "query_terms": plan.get("query_terms"),
                    "primary_terms": plan.get("primary_terms"),
                    "critical_path_terms": plan.get("critical_path_terms"),
                    "candidate_node_code": candidate.get("node_code"),
                    "candidate_leaf_name_path": candidate.get("leaf_name_path"),
                    "source_hits": source_hits,
                    "path_hits": candidate.get("path_hits") or [],
                    "negative_evidence": negative,
                    "recommended_action": (
                        "review source chunk canonical attachment; move or split source evidence if "
                        "text proves a different concept than candidate_leaf_name_path"
                    ),
                    "production_write_count": 0,
                    "canonical_truth_written": False,
                }
            )
    rows.sort(key=lambda row: (row["question"], str(row["candidate_node_code"])))
    return rows


def run_slice(
    *,
    output_dir: str | Path | None = None,
    run_live_ws_gate: bool = True,
) -> dict[str, Any]:
    out = Path(output_dir) if output_dir is not None else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    live_ws_gate = (
        _run_live_ws_gate()
        if run_live_ws_gate
        else {
            "live_ws_status": "unchecked",
            "live_ws_command": "",
            "live_ws_exit_code": None,
            "live_ws_evidence": "",
        }
    )

    on_rows = _evaluate_on_syllabus()
    off_rows = _evaluate_off_syllabus()
    low_confidence_rows = _evaluate_low_confidence_on_syllabus()
    calibration_rows = _evaluate_calibration_cases()
    compiler_source_work_orders = _build_compiler_source_work_orders()
    on_hits = sum(1 for row in on_rows if row["hit"])
    off_fall_open = sum(1 for row in off_rows if row["fall_open"])
    low_confidence_fall_open = sum(1 for row in low_confidence_rows if row["fall_open"])
    calibration_passed = sum(1 for row in calibration_rows if row["passed"])
    teaching_context_hit_rate = on_hits / len(on_rows) if on_rows else 0.0
    off_syllabus_fall_open_rate = off_fall_open / len(off_rows) if off_rows else 0.0
    low_confidence_fall_open_rate = (
        low_confidence_fall_open / len(low_confidence_rows) if low_confidence_rows else 0.0
    )
    calibration_pass_rate = calibration_passed / len(calibration_rows) if calibration_rows else 0.0

    official_score_violations = sum(
        1 for row in on_rows if row["hit"] and row["official_score_allowed"] is not False
    )
    llm_correctness_violations = sum(
        1 for row in on_rows if row["hit"] and row["llm_may_decide_correctness"] is not False
    )
    wrong_chapter_attribution = sum(
        1
        for row in [*off_rows, *low_confidence_rows]
        if row["wrong_chapter_attribution"]
    )

    coverage = {
        "authority": "luban_general_knowledge_context",
        "threshold": HIT_RATE_THRESHOLD,
        "on_syllabus_total": len(on_rows),
        "on_syllabus_hits": on_hits,
        "teaching_context_hit_rate": teaching_context_hit_rate,
        "off_syllabus_total": len(off_rows),
        "off_syllabus_fall_open": off_fall_open,
        "off_syllabus_fall_open_rate": off_syllabus_fall_open_rate,
        "low_confidence_on_syllabus_total": len(low_confidence_rows),
        "low_confidence_on_syllabus_fall_open": low_confidence_fall_open,
        "low_confidence_on_syllabus_fall_open_rate": low_confidence_fall_open_rate,
        "calibration_total": len(calibration_rows),
        "calibration_passed": calibration_passed,
        "calibration_pass_rate": calibration_pass_rate,
        "on_syllabus_cases": on_rows,
        "low_confidence_on_syllabus_cases": low_confidence_rows,
        "off_syllabus_cases": off_rows,
        "calibration_cases": calibration_rows,
        "compiler_source_work_order_count": len(compiler_source_work_orders),
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
    if low_confidence_fall_open_rate != 1.0:
        blockers.append("low_confidence_on_syllabus_fall_open_not_1_0")
    if len(calibration_rows) < 20 or calibration_pass_rate < 1.0:
        blockers.append("confidence_calibration_not_passed")
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
    live_ws_status = str(live_ws_gate.get("live_ws_status") or "unchecked")
    live_ws_evidence_text = str(live_ws_gate.get("live_ws_evidence") or "").strip()
    live_ws_command_text = str(live_ws_gate.get("live_ws_command") or "").strip()
    live_ws_exit_code = live_ws_gate.get("live_ws_exit_code")
    live_ws_evidence_valid = (
        live_ws_status == "pass"
        and live_ws_command_text == LIVE_WS_GATE_COMMAND_TEXT
        and live_ws_exit_code == 0
        and "test_luban_m34_general_knowledge_dividend_ws.py" in live_ws_evidence_text
        and "passed" in live_ws_evidence_text.lower()
    )
    if live_ws_command_text != LIVE_WS_GATE_COMMAND_TEXT or live_ws_exit_code is None:
        blockers.append("live_ws_gate_not_executed")
    if live_ws_status != "pass":
        blockers.append("live_ws_status_not_pass")
    elif live_ws_exit_code != 0:
        blockers.append("live_ws_exit_code_not_zero")
    elif not live_ws_evidence_valid:
        blockers.append("live_ws_evidence_missing_or_invalid")

    live_only_blockers = {
        "live_ws_status_not_pass",
        "live_ws_gate_not_executed",
        "live_ws_exit_code_not_zero",
        "live_ws_evidence_missing_or_invalid",
    }
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
        "live_ws_command": live_ws_command_text,
        "live_ws_exit_code": live_ws_exit_code,
        "live_ws_evidence": live_ws_evidence_text,
        "production_default": "disabled_pending_online_shadow_evidence",
        "default_cohort_scope": "shadow_only",
        "system_wide_default_gate": "requires_50_case_online_shadow_compiled_hit_source_validity_and_no_wrong_path_regression",
        "explicit_request_disable": "config.general_knowledge_context=false",
        "kill_switch": "LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED=false",
        "optional_cohort_env": "LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT",
        "production_write_count": safety["production_write_count"],
        "canonical_truth_written": safety["canonical_truth_written"],
        "coverage_report": "coverage_report_m34.json",
        "safety_report": "safety_invariant_report_m34.json",
        "compiler_source_work_orders": "compiler_source_work_orders_m34.jsonl",
    }

    _write_json(out / "coverage_report_m34.json", coverage)
    _write_json(out / "safety_invariant_report_m34.json", safety)
    _write_jsonl(out / "compiler_source_work_orders_m34.jsonl", compiler_source_work_orders)
    _write_json(out / "go_no_go_m34.json", go_no_go)
    return {"verdict": verdict, "output_dir": str(out), **go_no_go}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--skip-live-ws-gate",
        action="store_true",
        help="Do not execute the fixed /api/v1/ws pytest gate; verdict can be at most WEAK-GO.",
    )
    args = parser.parse_args(argv)
    result = run_slice(
        output_dir=args.output_dir,
        run_live_ws_gate=not args.skip_live_ws_gate,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["verdict"] in {"GO", "WEAK-GO"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
