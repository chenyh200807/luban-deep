#!/usr/bin/env python3
"""Run the mobile learning-report read-model e2e against a local API server."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEVTOOLS_CLI = Path("/Applications/wechatwebdevtools.app/Contents/MacOS/cli")


def _request_json(
    *,
    method: str,
    base_url: str,
    path: str,
    token: str = "",
    body: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _write_grading_attempt(
    *,
    user_id: str,
    run_id: str,
    attempt_index: int,
    user_answer: str,
    score_awarded: int,
) -> int:
    from deeptutor.services.construction_grading.writeback import write_grading_error_events
    from deeptutor.services.learner_state import get_learner_state_service

    is_success = score_awarded > 0
    grading_result = {
        "question_id": "learning-report-e2e-case-001",
        "question_type": "case_study",
        "user_answer": user_answer,
        "score_awarded": score_awarded,
        "max_score": 1,
        "grading_mode": "projected_rubric",
        "rubric_items": [
            {
                "rubric_item_id": "r1",
                "criterion": "识别专家论证程序",
                "status": "hit" if is_success else "miss",
                "evidence_text": "超过一定规模的危险性较大工程应组织专家论证。",
            }
        ],
        "error_events": []
        if is_success
        else [
            {
                "error_code": "E02",
                "concept_tag": "1A432000",
                "rubric_item_id": "r1",
                "diagnosis": "中文案例作答后，漏掉专家论证和专项施工方案审批这一采分点。",
            }
        ],
        "next_training_signal": {
            "concept": "1A432000",
            "focus": "专家论证程序",
            "mode": "case_repair",
        },
        "evidence_refs": [
            {
                "source": "rag",
                "source_id": "kb:construction:expert-review",
                "snippet": "超过一定规模的危险性较大的分部分项工程，应组织专家论证并按专项施工方案实施。",
            }
        ],
    }
    return write_grading_error_events(
        learner_state_service=get_learner_state_service(),
        user_id=user_id,
        grading_result=grading_result,
        source_id=f"learning-report-e2e-{run_id}:attempt-{attempt_index}",
        source_bot_id="construction-exam",
        include_success_events=True,
    )


def _run_synthesis(*, user_id: str, event_limit: int, user_data_dir: str) -> dict[str, Any]:
    env = dict(os.environ)
    for key in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_KEY",
        "SUPABASE_DB_URL",
        "SUPABASE_URL_V5",
        "SUPABASE_SERVICE_ROLE_KEY_V5",
        "SUPABASE_ANON_KEY",
        "SUPABASE_ANON_KEY_V5",
        "NEXT_PUBLIC_SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ):
        env.pop(key, None)
    env.setdefault("DEEPTUTOR_ENV", "local")
    env.setdefault("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    env["DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK"] = "1"
    env.setdefault("DEEPTUTOR_ALLOW_LOCAL_WALLET_FALLBACK", "1")
    env["DEEPTUTOR_USER_DATA_DIR"] = user_data_dir
    env["FF_AUTH_SUPABASE_BACKEND"] = "false"
    env["SUPABASE_RAG_ENABLED"] = "false"
    completed = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "run_learning_synthesis.py"),
            "--user-id",
            user_id,
            "--dry-run",
            "--event-limit",
            str(event_limit),
        ],
        check=True,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _open_devtools(project_path: Path) -> dict[str, Any]:
    if not DEVTOOLS_CLI.exists():
        return {"ok": False, "error": f"WeChat DevTools CLI not found: {DEVTOOLS_CLI}"}
    try:
        login = subprocess.run(
            [str(DEVTOOLS_CLI), "islogin"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        opened = subprocess.run(
            [str(DEVTOOLS_CLI), "open", "--project", str(project_path), "--lang", "zh"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=45,
        )
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": f"WeChat DevTools CLI timed out: {exc.cmd}"}
    return {
        "ok": opened.returncode == 0,
        "islogin_returncode": login.returncode,
        "islogin_stdout": login.stdout.strip(),
        "open_returncode": opened.returncode,
        "open_stdout": opened.stdout.strip(),
        "open_stderr": opened.stderr.strip(),
    }


def _core_source_status_ok(report: dict[str, Any]) -> bool:
    core_sources = {"learner_events", "compiled_truth", "dry_run_synthesis"}
    for name, status in dict(report.get("source_status") or {}).items():
        if name not in core_sources:
            continue
        if name == "dry_run_synthesis" and status.get("ok") is None:
            continue
        if status.get("ok") is not True:
            return False
    return True


def _visible_sections(report: dict[str, Any]) -> dict[str, Any]:
    learning_brain = report.get("learning_brain") if isinstance(report.get("learning_brain"), dict) else {}
    return learning_brain.get("visible_sections") if isinstance(learning_brain.get("visible_sections"), dict) else {}


def run(args: argparse.Namespace) -> dict[str, Any]:
    os.environ.setdefault("DEEPTUTOR_ENV", "local")
    os.environ.setdefault("DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA", "1")
    os.environ.setdefault("DEEPTUTOR_ALLOW_LOCAL_WALLET_FALLBACK", "1")
    os.environ["DEEPTUTOR_USER_DATA_DIR"] = args.user_data_dir

    run_id = str(args.code or f"dev-learning-report-e2e-{int(time.time())}").strip()
    login = _request_json(
        method="POST",
        base_url=args.base_url,
        path="/api/v1/wechat/mp/login",
        body={"code": run_id},
    )
    token = str(login.get("token") or "").strip()
    user_id = str(login.get("user_id") or "").strip()
    _assert(token and user_id, "wechat login did not return token and user_id")

    before = _request_json(
        method="GET",
        base_url=args.base_url,
        path=f"/api/v1/mobile/learning-report?event_limit={args.event_limit}",
        token=token,
    )
    _assert(before["authority"]["read_model"] == "learning-report-read-model", "read model authority mismatch")
    _assert(before["overview"]["recent_three_done"] == 0, "fresh e2e user should start at 0 recent attempts")

    first_written = _write_grading_attempt(
        user_id=user_id,
        run_id=run_id,
        attempt_index=1,
        user_answer="我只写了加强现场管理，没有写专家论证和专项施工方案审批。",
        score_awarded=0,
    )
    second_written = _write_grading_attempt(
        user_id=user_id,
        run_id=run_id,
        attempt_index=2,
        user_answer="我仍然只写现场整改，漏掉专家论证程序。",
        score_awarded=0,
    )
    _assert(first_written == 1 and second_written == 1, "two grading evidence events were not written")
    after_two_synthesis = _run_synthesis(
        user_id=user_id,
        event_limit=args.event_limit,
        user_data_dir=args.user_data_dir,
    )
    _assert(after_two_synthesis.get("status") == "ok", "synthesis after two attempts failed")

    after_two = _request_json(
        method="GET",
        base_url=args.base_url,
        path=f"/api/v1/mobile/learning-report?event_limit={args.event_limit}",
        token=token,
    )
    overview = dict(after_two.get("overview") or {})
    _assert(overview.get("recent_three_done") == 2, "recent_three_done should use attempt count after replay")
    _assert(overview.get("today_done") >= 2, "today_done should reflect the two grading attempts")
    _assert(overview.get("attempt_count") == 2, "attempt_count should equal two events")
    _assert(overview.get("unique_question_count") == 1, "same question replay should keep unique_question_count=1")
    _assert(
        overview.get("recent_three_unique_questions") == 1,
        "same question replay should keep recent_three_unique_questions=1",
    )
    sections = _visible_sections(after_two)
    _assert(bool(sections.get("current_truth")), "current_truth should be visible after grading evidence")
    _assert(bool(sections.get("evidence_flow")), "evidence_flow should be visible after grading evidence")
    _assert(bool(sections.get("next_training")), "next_training should be visible after grading evidence")
    _assert(_core_source_status_ok(after_two), "core source_status should be ok after local e2e")
    graph_chain = dict(dict(after_two.get("learning_brain") or {}).get("graph_chain") or {})
    _assert(graph_chain.get("has_training_uses_question") is True, "typed graph should include training -> question")

    improvement_written = _write_grading_attempt(
        user_id=user_id,
        run_id=run_id,
        attempt_index=3,
        user_answer="应组织专家论证，编制专项施工方案并按规定审批；按专项施工方案实施，验收合格后进入下道工序。",
        score_awarded=1,
    )
    _assert(improvement_written == 1, "success improvement evidence was not written")
    after_improve_synthesis = _run_synthesis(
        user_id=user_id,
        event_limit=args.event_limit,
        user_data_dir=args.user_data_dir,
    )
    _assert(after_improve_synthesis.get("status") == "ok", "synthesis after improvement failed")
    after_improve = _request_json(
        method="GET",
        base_url=args.base_url,
        path=f"/api/v1/mobile/learning-report?event_limit={args.event_limit}",
        token=token,
    )
    improved_chain = dict(dict(after_improve.get("learning_brain") or {}).get("graph_chain") or {})
    _assert(
        improved_chain.get("has_training_improved_error") is True
        or improved_chain.get("has_training_not_improved_error") is True,
        "typed graph should expose improved or not-improved training outcome",
    )

    devtools = _open_devtools(Path(args.project_path).resolve()) if args.open_devtools else {"ok": None}
    return {
        "ok": True,
        "user_id": user_id,
        "run_id": run_id,
        "before": {
            "recent_three_done": before["overview"]["recent_three_done"],
            "attempt_count": before["overview"]["attempt_count"],
        },
        "after_two_attempts": {
            "recent_three_done": after_two["overview"]["recent_three_done"],
            "today_done": after_two["overview"]["today_done"],
            "attempt_count": after_two["overview"]["attempt_count"],
            "unique_question_count": after_two["overview"]["unique_question_count"],
            "recent_three_unique_questions": after_two["overview"]["recent_three_unique_questions"],
            "degraded": after_two["degraded"],
            "learning_brain_source": after_two["authority"]["learning_brain_source"],
            "visible_sections": {
                "current_truth": len(sections.get("current_truth") or []),
                "evidence_flow": len(sections.get("evidence_flow") or []),
                "next_training": len(sections.get("next_training") or []),
            },
            "graph_chain": graph_chain,
        },
        "after_improvement": {
            "attempt_count": after_improve["overview"]["attempt_count"],
            "unique_question_count": after_improve["overview"]["unique_question_count"],
            "graph_chain": improved_chain,
        },
        "source_status": after_two.get("source_status"),
        "synthesis": {
            "after_two_event_count": after_two_synthesis.get("event_count"),
            "after_improve_event_count": after_improve_synthesis.get("event_count"),
        },
        "devtools": devtools,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--code", default="")
    parser.add_argument("--event-limit", type=int, default=100)
    parser.add_argument(
        "--user-data-dir",
        default=str(PROJECT_ROOT / ".local-runs" / "learning-brain" / "user-data"),
    )
    parser.add_argument("--open-devtools", action="store_true")
    parser.add_argument("--project-path", default=str(PROJECT_ROOT / "wx_miniprogram"))
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
