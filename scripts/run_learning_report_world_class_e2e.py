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
import re
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = PROJECT_ROOT / ".gstack" / "qa-reports" / "learning-report-world-class-gate.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


LOCAL_COMMAND_GATES: list[dict[str, Any]] = [
    {
        "name": "service_api_pytest",
        "description": "P0 service/API pytest for mobile report, read model, training intent, and home projection.",
        "commands": [
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/api/test_mobile_router.py",
                "tests/services/learner_state/test_learning_report_read_model.py",
                "tests/capabilities/test_next_training_signal_consumption.py",
                "tests/services/member_console/test_home_dashboard_learning_projection.py",
                "-q",
            ]
        ],
    },
    {
        "name": "contract_guard",
        "description": "Contract guard plus contract index / RLS / packaged contract consistency checks.",
        "commands": [
            [sys.executable, "scripts/check_contract_guard.py"],
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/contracts/test_index_consistency.py",
                "tests/supabase/test_learner_state_rls_migration.py",
                "tests/services/test_app_facade.py::test_packaged_contract_index_matches_repo_contract_index",
                "-q",
            ],
        ],
    },
    {
        "name": "node_view_model_layout",
        "description": "Node view-model, layout, chat, and package parity checks for wx/yousen surfaces.",
        "commands": [
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
        ],
    },
    {
        "name": "b5_prod_secret_fail_closed_ci_simulation",
        "description": "Round 2 B5 local CI simulation: prod secret validation, fail-closed import path, and forged ref rejection.",
        "commands": [
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/scripts/test_check_secret_envs.py",
                "tests/services/learner_state/test_attempt_refs.py",
                "-q",
            ]
        ],
    },
]

PAYLOAD_SIZE_LIMIT_BYTES = 80 * 1024
B7_WARM_P95_LIMIT_MS = 100.0
B7_FIXTURE_EVENTS = 5000


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


def _result(
    *,
    name: str,
    ok: bool,
    description: str,
    evidence: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "status": status or ("passed" if ok else "failed"),
        "description": description,
        "evidence": evidence or {},
    }


def _run_command_gate(gate: dict[str, Any]) -> dict[str, Any]:
    command_results = [_run(command) for command in gate["commands"]]
    ok = all(item.get("returncode") == 0 for item in command_results)
    return _result(
        name=str(gate["name"]),
        ok=ok,
        description=str(gate["description"]),
        evidence={"commands": command_results},
    )


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


def _b1_forbidden_positive_usage_scan() -> dict[str, Any]:
    scanned_roots = ["deeptutor", "tests", "supabase", "contracts"]
    positive_patterns = [
        re.compile(r"event_type\s*[=:]\s*[\"']conversation_learning_evidence[\"']"),
        re.compile(r"[\"']event_type[\"']\s*:\s*[\"']conversation_learning_evidence[\"']"),
        re.compile(r"_supports_event_type\([\"']conversation_learning_evidence[\"']\)"),
    ]
    allowed_negative_markers = (
        "assert not ",
        "不得新增",
        "forbidden",
        "anti-pattern",
        "negative assertion",
    )
    hits: list[dict[str, Any]] = []
    for root in scanned_roots:
        for path in (PROJECT_ROOT / root).rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".sql", ".md"}:
                continue
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            if "__pycache__" in rel:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(lines, start=1):
                if not any(pattern.search(line) for pattern in positive_patterns):
                    continue
                if any(marker in line for marker in allowed_negative_markers):
                    continue
                hits.append({"path": rel, "line": lineno, "text": line.strip()[:240]})
    return _result(
        name="b1_forbidden_positive_usage_scan",
        ok=not hits,
        description=(
            "Round 2 B1 scan: no positive writer/reader path may use "
            "event_type=conversation_learning_evidence; docs may keep it only as an anti-pattern."
        ),
        evidence={"scanned_roots": scanned_roots, "hits": hits},
    )


def _v1_v2_dual_emit_gate() -> dict[str, Any]:
    mobile_tests = _file_text("tests/api/test_mobile_router.py")
    read_model_tests = _file_text("tests/services/learner_state/test_learning_report_read_model.py")
    contract = _file_text("contracts/learning-report.md")
    api = _file_text("deeptutor/api/routers/mobile.py")
    checks = {
        "api_accepts_schema_version_2": "schema_version: int = Query(default=1, ge=1, le=2)" in api,
        "api_tests_request_schema_version_2": "schema_version=2" in mobile_tests,
        "read_model_tests_assert_schema_version_2": 'model["schema_version"] == 2' in read_model_tests,
        "contract_declares_v1_v2_dual_emit": "v1 与 v2 dual-emit" in contract,
    }
    return _result(
        name="v1_v2_dual_emit",
        ok=all(checks.values()),
        description="Local proof that v1/v2 dual emit is covered by API, tests, and contract.",
        evidence={"checks": checks},
    )


def _g12_i18n_keys_gate() -> dict[str, Any]:
    read_model = _file_text("deeptutor/services/learner_state/learning_report_read_model.py")
    read_model_tests = _file_text("tests/services/learner_state/test_learning_report_read_model.py")
    contract = _file_text("contracts/learning-report.md")
    checks = {
        "read_model_emits_i18n_keys": '"i18n_keys"' in read_model and '"locale": "zh-CN"' in read_model,
        "tests_assert_i18n_keys": 'model["i18n_keys"]["locale"] == "zh-CN"' in read_model_tests,
        "contract_declares_i18n_keys": "`i18n_keys`" in contract,
    }
    return _result(
        name="g12_i18n_keys_presence",
        ok=all(checks.values()),
        description="Round 2 G12 local proof: read model carries i18n_keys for future locale evolution.",
        evidence={"checks": checks},
    )


class _GatePathService:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def project_root(self) -> Path:
        return self._root

    def get_user_root(self) -> Path:
        return self._root

    def get_tutor_state_root(self) -> Path:
        return self._root / "tutor_state"

    def get_learner_state_root(self) -> Path:
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self) -> Path:
        return self._root / "runtime" / "outbox.db"

    def get_guide_dir(self) -> Path:
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _NoopOutbox:
    def enqueue(self, **_kwargs: Any) -> None:
        return None


class _UnconfiguredCoreStore:
    is_configured = False


class _GateMemberService:
    def get_today_progress(self, _user_id: str) -> dict[str, Any]:
        return {"today_done": 2, "daily_target": 5, "streak_days": 1}

    def get_home_dashboard(self, _user_id: str) -> dict[str, Any]:
        return {
            "today_focus": {"concept": "专家论证程序", "error": "漏写专项方案审批"},
            "recommended_prompts": [
                {
                    "text": "专家论证程序怎么写才不漏分？",
                    "prompt_intent": {
                        "source": "home_dashboard",
                        "learning_signal_type": "concept_explain",
                    },
                }
            ],
            "source_status": {"ok": True},
        }

    def get_assessment_profile(self, _user_id: str) -> dict[str, Any]:
        return {}

    def get_mastery_dashboard(self, _user_id: str) -> dict[str, Any]:
        return {}


def _make_learning_evidence_payload(index: int) -> dict[str, Any]:
    return {
        "event_type": "learning_evidence",
        "question_id": f"q-{index}",
        "question_type": "case_study",
        "question_text": "某超过一定规模的危险性较大工程施工前，应履行哪些专家论证程序？",
        "user_answer": "只写了加强现场管理，漏写专家论证和专项施工方案审批。",
        "correct_answer": "应编制专项施工方案，按规定审批后组织专家论证，并按论证意见修改实施。",
        "score_awarded": 0 if index % 2 else 1,
        "max_score": 1,
        "error_events": [
            {
                "error_code": "E02",
                "concept_tag": "1A432000",
                "diagnosis": "漏写专家论证和专项施工方案审批。",
            }
        ],
        "explanation": {
            "summary": "本题核心是先专项方案审批，再组织专家论证。",
            "why_user_wrong": "答案只写现场整改，没有覆盖程序性采分点。",
        },
        "next_training_signal": {
            "concept": "专家论证程序",
            "error": "漏写专项方案审批",
            "mode": "case_repair",
        },
        "quality": {"evidence_level": "L1_repeated", "writeback_eligible": True},
    }


def _new_gate_service(root: Path) -> Any:
    from deeptutor.services.learner_state.service import LearnerStateService

    return LearnerStateService(
        path_service=_GatePathService(root),
        outbox_service=_NoopOutbox(),
        core_store=_UnconfiguredCoreStore(),
    )


def _write_fixture_events(root: Path, *, user_id: str, count: int) -> str:
    events_path = root / "learner_state" / user_id / "MEMORY_EVENTS.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    target_event_id = ""
    with events_path.open("w", encoding="utf-8") as handle:
        for index in range(count):
            event_id = f"{index + 1:032x}"
            target_event_id = event_id
            record = {
                "event_id": event_id,
                "user_id": user_id,
                "source_feature": "construction_grading",
                "source_id": f"gate-5k:{index}",
                "source_bot_id": "construction-exam",
                "memory_kind": "learning_evidence",
                "payload_json": _make_learning_evidence_payload(index),
                "dedupe_key": f"gate-5k:{index}",
                "created_at": "2026-05-21T00:00:00+08:00",
            }
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return target_event_id


def _b7_5k_attempt_detail_warm_p95_gate() -> dict[str, Any]:
    from deeptutor.services.learner_state.attempt_detail_read_model import build_attempt_detail_read_model
    from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref

    with tempfile.TemporaryDirectory(prefix="learning-report-b7-") as temp_dir:
        root = Path(temp_dir)
        service = _new_gate_service(root)
        user_id = "gate_5k_user"
        target_event_id = _write_fixture_events(root, user_id=user_id, count=B7_FIXTURE_EVENTS)
        attempt_ref = sign_attempt_ref(user_id=user_id, event_id=target_event_id, question_id="q-4999")
        warm = build_attempt_detail_read_model(
            user_id=user_id,
            learner_state_service=service,
            attempt_ref=attempt_ref,
        )
        durations: list[float] = []
        for _ in range(50):
            started = time.perf_counter()
            detail = build_attempt_detail_read_model(
                user_id=user_id,
                learner_state_service=service,
                attempt_ref=attempt_ref,
            )
            durations.append((time.perf_counter() - started) * 1000)
            if detail.get("ok") is not True:
                warm = detail
                break
        ordered = sorted(durations)
        p95_ms = ordered[max(0, int(len(ordered) * 0.95) - 1)] if ordered else float("inf")
    return _result(
        name="b7_5k_attempt_detail_warm_p95",
        ok=warm.get("ok") is True and p95_ms < B7_WARM_P95_LIMIT_MS,
        description="Round 2 B7 local fixture: 5k learning_evidence events, attempt-detail warm p95 below local threshold.",
        evidence={
            "fixture_events": B7_FIXTURE_EVENTS,
            "warm_ok": warm.get("ok") is True,
            "p95_ms": round(p95_ms, 3),
            "threshold_ms": B7_WARM_P95_LIMIT_MS,
        },
    )


def _payload_size_under_80kb_fixture_gate() -> dict[str, Any]:
    from deeptutor.services.learner_state.learning_report_read_model import build_learning_report_read_model

    with tempfile.TemporaryDirectory(prefix="learning-report-payload-") as temp_dir:
        service = _new_gate_service(Path(temp_dir))
        user_id = "gate_payload_user"
        for index in range(30):
            service.append_memory_event(
                user_id,
                source_feature="construction_grading",
                source_id=f"payload:{index}",
                source_bot_id="construction-exam",
                memory_kind="learning_evidence",
                payload_json=_make_learning_evidence_payload(index),
                dedupe_key=f"payload:{index}",
            )
        payload = build_learning_report_read_model(
            user_id=user_id,
            member_service=_GateMemberService(),
            learner_state_service=service,
            event_limit=100,
            schema_version=2,
        )
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    learner_facing = json.dumps(payload.get("learner_facing", {}), ensure_ascii=False)
    forbidden_tokens = ["M06", "question_tests_concept"]
    forbidden_hits = [token for token in forbidden_tokens if token in learner_facing]
    event_hash_leak = bool(re.search(r"\b[0-9a-f]{32}\b", learner_facing))
    return _result(
        name="payload_size_under_80kb_fixture",
        ok=len(encoded) < PAYLOAD_SIZE_LIMIT_BYTES and not forbidden_hits and not event_hash_leak,
        description="Local fixture payload size stays below 80KB and learner-facing payload does not expose raw internal tokens.",
        evidence={
            "payload_size_bytes": len(encoded),
            "threshold_bytes": PAYLOAD_SIZE_LIMIT_BYTES,
            "forbidden_hits": forbidden_hits,
            "event_hash_leak": event_hash_leak,
            "schema_version": payload.get("schema_version"),
        },
    )


def _static_local_gates() -> list[dict[str, Any]]:
    static_results = _static_assertions()
    return [
        _result(
            name="frontend_static_authority_assertions",
            ok=all(item.get("ok") for item in static_results),
            description="Existing static assertions for shared view models, no local recompute, and prompt authority.",
            evidence={"assertions": static_results},
        ),
        _v1_v2_dual_emit_gate(),
        _b1_forbidden_positive_usage_scan(),
        _b7_5k_attempt_detail_warm_p95_gate(),
        _payload_size_under_80kb_fixture_gate(),
        _g12_i18n_keys_gate(),
    ]


def _external_blockers() -> list[dict[str, Any]]:
    return [
        {
            "name": "production_14_day_observation",
            "status": "blocking",
            "description": "14 days stable production metrics: 5xx < 0.1%, p95 within target, degraded < 1%.",
        },
        {
            "name": "deprecated_source_rps_zero_7d",
            "status": "blocking",
            "description": "Deprecated page source RPS must remain 0 for 7 days before old readers are declared removable.",
        },
        {
            "name": "staging_v1_v2_dual_emit",
            "status": "blocking",
            "description": "Staging must prove /learning-report schema_version=1 and 2 both return correct fields and generate v1-vs-v2 evidence JSON.",
        },
        {
            "name": "langfuse_trace_bundle",
            "status": "blocking",
            "description": "Langfuse or backend logs must prove grading/evidence/report/detail/training/home-prompt chain including G8 trace keys.",
        },
        {
            "name": "production_secret_manager_fingerprint",
            "status": "blocking",
            "description": "Prod DEEPTUTOR_ATTEMPT_REF_SECRET must be set in secret manager and startup fingerprint reconciled with ops record.",
        },
        {
            "name": "production_supabase_rls",
            "status": "blocking",
            "description": "Prod/staging Supabase RLS checks for mistake book and cross-user access must be attached.",
        },
    ]


def _manual_required() -> list[dict[str, Any]]:
    return [
        {
            "name": "wechat_ios_android_pc_screenshots",
            "status": "pending",
            "description": "G11 requires iOS WeChat, Android WeChat, and PC WeChat P0 screenshots; local automation cannot mark this ok.",
        },
        {
            "name": "production_conversion_sampling",
            "status": "pending",
            "description": "Manual/product review required for useful-answer, practice-start, and conversation evidence extraction sampling.",
        },
    ]


def run(output: Path) -> dict[str, Any]:
    local_gates = [_run_command_gate(gate) for gate in LOCAL_COMMAND_GATES]
    local_gates.extend(_static_local_gates())
    passed_local_gates = [gate for gate in local_gates if gate["ok"]]
    failed_local_gates = [gate for gate in local_gates if not gate["ok"]]
    ok = not failed_local_gates
    report = {
        "ok": ok,
        "local_deterministic_ok": ok,
        "rollout_ready": False,
        "external_proof_required": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scope": "local_deterministic_gate",
        "passed_local_gates": passed_local_gates,
        "failed_local_gates": failed_local_gates,
        "blocked_external_gates": _external_blockers(),
        "manual_required": _manual_required(),
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
