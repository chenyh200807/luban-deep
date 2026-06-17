#!/usr/bin/env python3
"""R6 remote/prod-like /api/v1/ws readback gate.

This wrapper keeps the remote evidence boundary explicit. Without QA auth
material it writes a local blocker artifact and performs no network action.
With QA auth material it delegates to the existing remote Test2 WS soak, while
forcing remote SSH synthesis off.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.run_learner_memory_lifecycle_test2_cohort_soak as soak  # noqa: E402

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/r6_remote_or_production_ws_turn_20260612"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _has_auth_material(
    *,
    auth_token: str,
    username: str,
    password: str,
    phone: str,
    register: bool,
) -> bool:
    if str(auth_token or "").strip():
        return True
    if register:
        return True
    return bool(str(username or "").strip() and str(password or "").strip())


def _auth_missing_result(*, out_dir: Path, api_base_url: str, scenario_id: str) -> dict[str, Any]:
    run_id = f"r6_remote_ws_auth_missing_{int(time.time())}"
    manifest = {
        "run_id": run_id,
        "mode": "r6-remote-or-production-ws-turn",
        "entry": "remote/prod-like /api/v1/ws QA-scoped turn",
        "api_base_url": str(api_base_url or "").rstrip("/"),
        "evidence_scope": "remote_or_production_ws_turn_preflight",
        "remote_or_production_ws_turn_exercised": False,
        "scenario_id": scenario_id,
        "auth_state": "missing",
        "auth_mode": "none",
        "remote_write_performed": False,
        "canonical_truth_written": False,
        "published_registry_written": False,
        "production_db_write_performed": False,
        "stage_chain": [],
    }
    go_no_go = {
        "status": "REMOTE_WS_AUTH_MATERIAL_MISSING",
        "reason": "DEEPTUTOR_TEST2_COHORT_AUTH_TOKEN or QA username/password is required",
        "remote_or_production_ws_turn_exercised": False,
        "remote_write_performed": False,
        "canonical_truth_written": False,
        "published_registry_written": False,
        "production_db_write_performed": False,
        "next_step": (
            "Provide a QA cohort token via DEEPTUTOR_TEST2_COHORT_AUTH_TOKEN, or QA username/password, "
            "then rerun this gate."
        ),
    }
    _write_json(out_dir / "manifest.json", manifest)
    _write_json(out_dir / "go_no_go.json", go_no_go)
    return {"out_dir": str(out_dir), "manifest": manifest, "go_no_go": go_no_go}


async def run_r6_remote_ws_readback_gate(
    *,
    out_dir: Path | None = None,
    api_base_url: str = "https://test2.yousenjiaoyu.com",
    auth_token: str = "",
    username: str = "",
    password: str = "",
    phone: str = "",
    register: bool = False,
    scenario_id: str = "temporary-electricity-smoke",
    answer_file: Path | None = None,
    sample_id: str = "",
    timeout_seconds: float = 90.0,
    poll_attempts: int = 12,
    poll_interval_seconds: float = 5.0,
) -> dict[str, Any]:
    out = out_dir or DEFAULT_OUTPUT
    out.mkdir(parents=True, exist_ok=True)
    if not _has_auth_material(
        auth_token=auth_token,
        username=username,
        password=password,
        phone=phone,
        register=register,
    ):
        return _auth_missing_result(out_dir=out, api_base_url=api_base_url, scenario_id=scenario_id)
    return await soak.run_remote_test2_ws_soak(
        api_base_url=api_base_url,
        auth_token=auth_token,
        username=username,
        password=password,
        phone=phone,
        register=register,
        out_dir=out,
        timeout_seconds=timeout_seconds,
        poll_attempts=poll_attempts,
        poll_interval_seconds=poll_interval_seconds,
        remote_synthesis_ssh_host="",
        scenario_id=scenario_id,
        answer_file=answer_file,
        sample_id=sample_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--api-base-url", default=os.getenv("TEST2_BASE_URL") or "https://test2.yousenjiaoyu.com")
    parser.add_argument("--auth-token", default=os.getenv("DEEPTUTOR_TEST2_COHORT_AUTH_TOKEN") or "")
    parser.add_argument("--username", default=os.getenv("DEEPTUTOR_TEST2_COHORT_USERNAME") or "")
    parser.add_argument("--password", default=os.getenv("DEEPTUTOR_TEST2_COHORT_PASSWORD") or "")
    parser.add_argument("--phone", default=os.getenv("DEEPTUTOR_TEST2_COHORT_PHONE") or "")
    parser.add_argument("--register", action="store_true")
    parser.add_argument(
        "--scenario",
        default=os.getenv("DEEPTUTOR_TEST2_SOAK_SCENARIO") or "temporary-electricity-smoke",
        choices=["temporary-electricity-smoke", "construction-long-case"],
    )
    parser.add_argument("--answer-file", type=Path, default=None)
    parser.add_argument("--sample-id", default=os.getenv("DEEPTUTOR_TEST2_SOAK_SAMPLE_ID") or "")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--poll-attempts", type=int, default=12)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    args = parser.parse_args()
    result = asyncio.run(
        run_r6_remote_ws_readback_gate(
            out_dir=args.out_dir,
            api_base_url=args.api_base_url,
            auth_token=args.auth_token,
            username=args.username,
            password=args.password,
            phone=args.phone,
            register=args.register,
            scenario_id=args.scenario,
            answer_file=args.answer_file,
            sample_id=args.sample_id,
            timeout_seconds=args.timeout_seconds,
            poll_attempts=args.poll_attempts,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["go_no_go"]["status"] == "REMOTE_TEST2_WS_GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
