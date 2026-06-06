#!/usr/bin/env python3
"""Run the WeChat Learning Brain read-model e2e against a local API server."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEVTOOLS_CLI = Path("/Applications/wechatwebdevtools.app/Contents/MacOS/cli")
DEFAULT_DEVTOOLS_PROJECT_PATH = PROJECT_ROOT / "yousenwebview" / "packageDeeptutor"


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


def _levels(payload: dict[str, Any]) -> set[str]:
    weak_points = payload.get("weak_points") if isinstance(payload.get("weak_points"), list) else []
    truth = (payload.get("visible_sections") or {}).get("current_truth") if isinstance(payload.get("visible_sections"), dict) else []
    return {
        str(item.get("evidence_level") or "")
        for item in [*weak_points, *(truth or [])]
        if isinstance(item, dict)
    }


def _open_devtools(project_path: Path) -> dict[str, Any]:
    if not DEVTOOLS_CLI.exists():
        raise RuntimeError(f"WeChat DevTools CLI not found: {DEVTOOLS_CLI}")
    login = subprocess.run(
        [str(DEVTOOLS_CLI), "islogin"],
        check=False,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    opened = subprocess.run(
        [str(DEVTOOLS_CLI), "open", "--project", str(project_path), "--lang", "zh"],
        check=False,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=45,
    )
    if opened.returncode != 0:
        raise RuntimeError(
            "WeChat DevTools project open failed: "
            f"exit_code={opened.returncode} stderr={(opened.stderr or '').strip()[:300]}"
        )
    return {
        "entry_surface": "real_wechat_package",
        "trace_source": "devtools_cli_open",
        "project_path": str(project_path),
        "islogin_returncode": login.returncode,
        "islogin_stdout": (login.stdout or "").strip(),
        "open_returncode": opened.returncode,
        "open_stdout": (opened.stdout or "").strip(),
        "open_stderr": (opened.stderr or "").strip(),
        "evidence_boundary": "project-open preflight; page-level PASS still requires scenario evidence",
    }


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
    env["DEEPTUTOR_MISTAKE_BOOK_ENABLED"] = "1"
    env["DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED"] = "1"
    env["DEEPTUTOR_MISTAKE_BOOK_LOCAL_FALLBACK"] = "1"
    env.setdefault("DEEPTUTOR_USER_DATA_DIR", user_data_dir)
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


def run(args: argparse.Namespace) -> dict[str, Any]:
    code = args.code or f"dev-learning-brain-e2e-{time.time_ns()}-{uuid.uuid4().hex[:8]}"
    login = _request_json(
        method="POST",
        base_url=args.base_url,
        path="/api/v1/wechat/mp/login",
        body={"code": code},
    )
    token = str(login.get("token") or "").strip()
    user_id = str(login.get("user_id") or "").strip()
    _assert(token and user_id, "wechat login did not return token and user_id")

    weak_answer = "案例作答：只写加强现场管理和落实责任，没有写专家论证、专项施工方案审批和验收合格。"
    confirmed_answer = "案例作答：仍然漏写专家论证和专项施工方案审批，只强调现场整改。"
    success_answer = "案例作答：应组织专家论证，编制专项施工方案并按规定审批；按专项施工方案实施，验收合格后方可进入下道工序。"

    first = _request_json(
        method="POST",
        base_url=args.base_url,
        path="/api/v1/learning-brain/harness-case-grading",
        body={"user_id": user_id, "user_answer": weak_answer},
    )
    _assert(first.get("training_uses_question") is True, "first grading did not build training -> question chain")
    _assert(first.get("training_not_improved_error") is True, "first grading did not mark weak point as not improved")
    l1_synthesis = _run_synthesis(
        user_id=user_id,
        event_limit=args.event_limit,
        user_data_dir=args.user_data_dir,
    )
    _assert(l1_synthesis.get("status") == "ok", "first synthesis did not complete")

    l1_projection = _request_json(
        method="GET",
        base_url=args.base_url,
        path=f"/api/v1/learning-brain/projection?event_limit={args.event_limit}",
        token=token,
    )
    visible = l1_projection.get("visible_sections") if isinstance(l1_projection.get("visible_sections"), dict) else {}
    _assert("L1_repeated" in _levels(l1_projection), "authenticated projection did not expose L1_repeated")
    _assert(bool(visible.get("current_truth")), "current_truth section is empty")
    _assert(bool(visible.get("evidence_flow")), "evidence_flow section is empty")
    _assert(bool(visible.get("next_training")), "next_training section is empty")
    _assert(
        (l1_projection.get("graph_chain") or {}).get("has_training_not_improved_error") is True,
        "authenticated projection did not expose training_not_improved_error",
    )

    confirmed = _request_json(
        method="POST",
        base_url=args.base_url,
        path="/api/v1/learning-brain/harness-case-grading",
        body={"user_id": user_id, "user_answer": confirmed_answer, "manual_confirm": True},
    )
    _assert(bool(confirmed.get("manual_confirmation")), "manual confirmation event was not written")
    l2_synthesis = _run_synthesis(
        user_id=user_id,
        event_limit=args.event_limit,
        user_data_dir=args.user_data_dir,
    )
    _assert(l2_synthesis.get("status") == "ok", "manual-confirm synthesis did not complete")
    l2_projection = _request_json(
        method="GET",
        base_url=args.base_url,
        path=f"/api/v1/learning-brain/projection?event_limit={args.event_limit}",
        token=token,
    )
    _assert("L2_confirmed" in _levels(l2_projection), "authenticated projection did not expose L2_confirmed")

    improved = _request_json(
        method="POST",
        base_url=args.base_url,
        path="/api/v1/learning-brain/harness-case-grading",
        body={"user_id": user_id, "user_answer": success_answer},
    )
    _assert(improved.get("training_improved_error") is True, "success grading did not build training_improved_error")
    improved_synthesis = _run_synthesis(
        user_id=user_id,
        event_limit=args.event_limit,
        user_data_dir=args.user_data_dir,
    )
    _assert(improved_synthesis.get("status") == "ok", "improvement synthesis did not complete")
    improved_projection = _request_json(
        method="GET",
        base_url=args.base_url,
        path=f"/api/v1/learning-brain/projection?event_limit={args.event_limit}",
        token=token,
    )
    _assert(
        (improved_projection.get("graph_chain") or {}).get("has_training_improved_error") is True,
        "authenticated projection did not persist improved typed graph chain",
    )
    _assert(bool(improved_projection.get("improvement_signals")), "improvement signal is missing")

    devtools = None
    if args.open_devtools:
        devtools = _open_devtools(Path(args.project_path).resolve())

    return {
        "ok": True,
        "user_id": user_id,
        "devtools": devtools,
        "event_count": improved_projection.get("event_count"),
        "l1_levels": sorted(_levels(l1_projection)),
        "l2_levels": sorted(_levels(l2_projection)),
        "graph_chain": improved_projection.get("graph_chain"),
        "synthesis": {
            "l1_event_count": l1_synthesis.get("event_count"),
            "l2_manual_override_count": l2_synthesis.get("manual_override_count"),
            "improved_decayed_claim_count": improved_synthesis.get("decayed_claim_count"),
        },
        "visible_sections": {
            "current_truth": len((improved_projection.get("visible_sections") or {}).get("current_truth") or []),
            "evidence_flow": len((improved_projection.get("visible_sections") or {}).get("evidence_flow") or []),
            "next_training": len((improved_projection.get("visible_sections") or {}).get("next_training") or []),
        },
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
    parser.add_argument("--project-path", default=str(DEFAULT_DEVTOOLS_PROJECT_PATH))
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
