#!/usr/bin/env python3
"""Run the local Learning Report world-class gate.

This is the local, deterministic gate for the 2026-05-21 plan. Production-only
proofs such as 14-day metrics, Langfuse sampling, and WeChat device screenshots
must be attached separately; this script records them as pending instead of
pretending local automation can prove them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = PROJECT_ROOT / ".gstack" / "qa-reports" / "learning-report-world-class-gate.json"


COMMANDS: list[list[str]] = [
    [
        sys.executable,
        "-m",
        "pytest",
        "tests/api/test_mobile_router.py",
        "tests/services/learner_state/test_learning_report_read_model.py",
        "tests/capabilities/test_next_training_signal_consumption.py",
        "tests/services/member_console/test_home_dashboard_learning_projection.py",
        "-q",
    ],
    [
        sys.executable,
        "scripts/check_contract_guard.py",
    ],
    [
        sys.executable,
        "-m",
        "pytest",
        "tests/contracts/test_index_consistency.py",
        "tests/supabase/test_learner_state_rls_migration.py",
        "tests/services/test_app_facade.py::test_packaged_contract_index_matches_repo_contract_index",
        "-q",
    ],
    ["node", "wx_miniprogram/tests/test_report_view_model.js"],
    ["node", "yousenwebview/tests/test_report_view_model.js"],
    ["node", "wx_miniprogram/tests/test_home_dashboard_learning_prompts.js"],
    ["node", "yousenwebview/tests/test_home_dashboard_learning_prompts.js"],
    ["node", "wx_miniprogram/tests/test_report_learning_brain.js"],
    ["node", "wx_miniprogram/tests/test_report_layout.js"],
    ["node", "wx_miniprogram/tests/test_chat_layout.js"],
    ["node", "yousenwebview/tests/test_report_snapshot_dedupe.js"],
    ["node", "yousenwebview/tests/test_report_layout.js"],
    ["node", "yousenwebview/tests/test_package_chat_home_actions.js"],
]


def _run(command: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _file_text(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _static_assertions() -> list[dict[str, Any]]:
    wx_report_vm = _file_text("wx_miniprogram/utils/learning-report-view-model.js")
    yousen_report_vm = _file_text("yousenwebview/packageDeeptutor/utils/learning-report-view-model.js")
    wx_home_vm = _file_text("wx_miniprogram/utils/learning-home-view-model.js")
    yousen_home_vm = _file_text("yousenwebview/packageDeeptutor/utils/learning-home-view-model.js")
    wx_ws = _file_text("wx_miniprogram/utils/ws-stream.js")
    yousen_ws = _file_text("yousenwebview/packageDeeptutor/utils/ws-stream.js")
    wx_chat = _file_text("wx_miniprogram/pages/chat/chat.js")
    yousen_chat = _file_text("yousenwebview/packageDeeptutor/pages/chat/chat.js")
    wx_report = _file_text("wx_miniprogram/pages/report/report.js")
    yousen_report = _file_text("yousenwebview/packageDeeptutor/pages/report/report.js")
    wx_report_load = wx_report.split("async _loadLearningReport()", 1)[1].split("toggleMastery()", 1)[0]
    yousen_report_hydrate = yousen_report.split("_hydrateFromUnifiedReport(snapshot)", 1)[1].split("onReady()", 1)[0]
    return [
        {
            "name": "report_view_model_byte_identical",
            "ok": wx_report_vm == yousen_report_vm,
        },
        {
            "name": "home_view_model_byte_identical",
            "ok": wx_home_vm == yousen_home_vm,
        },
        {
            "name": "prompt_intent_round_trip_surface",
            "ok": "prompt_intent" in wx_ws
            and "prompt_intent" in yousen_ws
            and "promptIntent: prompt.promptIntent" in wx_chat
            and "promptIntent: prompt.promptIntent" in yousen_chat,
        },
        {
            "name": "frontend_no_static_practice_prompt_authority",
            "ok": "请给我来5道高价值选择题" not in wx_chat
            and "请给我来5道高价值选择题" not in yousen_chat
            and "只输出题目和选项" not in wx_chat
            and "只输出题目和选项" not in yousen_chat
            and "buildFocusQuery" not in wx_chat
            and "buildFocusQuery" not in yousen_chat
            and "请根据我的学习记录和最近进度" not in wx_chat
            and "请根据我的学习记录和最近进度" not in yousen_chat,
        },
        {
            "name": "home_view_model_does_not_build_prompt_fallback",
            "ok": "buildFallbackFocusQuery" not in wx_home_vm
            and "buildFallbackFocusQuery" not in yousen_home_vm,
        },
        {
            "name": "report_pages_bind_shared_view_model_without_local_recompute",
            "ok": "normalizeMasteryGroups(" not in wx_report_load
            and "normalizeRadarState(" not in wx_report_load
            and "normalizeLearningBrainPayload(" not in wx_report_load
            and "_normalizeRadarDimensions(" not in yousen_report_hydrate
            and "_buildRadarViewModel(" not in yousen_report_hydrate
            and "_normalizeLearningBrainPayload(" not in yousen_report_hydrate,
        },
        {
            "name": "yousen_report_unified_failure_does_not_call_legacy_readers",
            "ok": "_loadOverview(null)" not in yousen_report
            and "_loadLearningBrain(null)" not in yousen_report
            and "_loadRadar(null)" not in yousen_report
            and "_loadMastery(null)" not in yousen_report,
        },
    ]


def run(output: Path) -> dict[str, Any]:
    command_results = [_run(command) for command in COMMANDS]
    static_results = _static_assertions()
    ok = all(item["returncode"] == 0 for item in command_results) and all(
        item["ok"] for item in static_results
    )
    report = {
        "ok": ok,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scope": "local_deterministic_gate",
        "commands": command_results,
        "static_assertions": static_results,
        "production_required_but_not_proven_locally": [
            "14 days stable metrics",
            "deprecated page source RPS = 0 for 7 days",
            "mistake book write success >= 99.5%",
            "next-training click -> practice start conversion tracked",
            "homepage focus click -> useful answer / training conversion tracked",
            "conversation evidence extraction success >= 90%",
            "iOS / Android / PC WeChat device screenshots",
            "Langfuse or backend log trace bundle for grading/evidence/report/detail/training/home prompt chain",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    args = parser.parse_args()
    report = run(Path(args.output))
    print(json.dumps({"ok": report["ok"], "output": args.output}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
