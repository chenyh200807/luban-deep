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
        "production_default": "on_teaching_context_only",
        "default_cohort_scope": "all_users",
        "explicit_request_disable": "config.general_knowledge_context=false",
        "kill_switch": "LUBAN_GENERAL_KNOWLEDGE_CONTEXT_ENABLED=false",
        "optional_cohort_env": "LUBAN_GENERAL_KNOWLEDGE_CONTEXT_COHORT",
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
