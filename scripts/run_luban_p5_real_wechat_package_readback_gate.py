#!/usr/bin/env python3
"""P5 real WeChat package readback gate for grading-to-brain.

This gate closes the remaining entry-surface gap after P4. It requires the
real WeChat DevTools project root (`yousenwebview`) and the
`packageDeeptutor` report page to be exercised by the existing DevTools page
automation. It consumes the P4 local `/api/v1/ws` readback package as the
backend chain authority and only treats WeChat as the user-facing entry proof.

No production DB, canonical truth, published registry, remote host, or Aliyun
state is written.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_luban_p4_ws_readback_gate import (  # noqa: E402
    DEFAULT_OUTPUT as P4_DEFAULT_OUTPUT,
    build_p4_ws_readback_package,
)
from scripts.run_wechat_devtools_daily_smoke import run as run_wechat_devtools_smoke  # noqa: E402

DEFAULT_OUTPUT = ROOT / "artifacts/luban_grading_artifacts/p5_real_wechat_package_readback_20260612"
P4_PACKAGE_PATH = P4_DEFAULT_OUTPUT / "p4_ws_readback_package.json"


def _artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _default_p4_package() -> dict[str, Any]:
    if P4_PACKAGE_PATH.exists():
        return _read_json(P4_PACKAGE_PATH)
    return build_p4_ws_readback_package(output_dir=P4_DEFAULT_OUTPUT)


def _run_live_wechat_smoke(*, auto_port: int, timeout_seconds: float, page_wait_ms: int) -> dict[str, Any]:
    args = SimpleNamespace(
        project_path=str(ROOT / "yousenwebview"),
        timeout_seconds=float(timeout_seconds),
        auto_port=int(auto_port),
        page_wait_ms=int(page_wait_ms),
        skip_runtime_contract=False,
    )
    return run_wechat_devtools_smoke(args)


def _page_automation(payload: dict[str, Any]) -> dict[str, Any]:
    page = payload.get("page_automation")
    return page if isinstance(page, dict) else {}


def _page_path(payload: dict[str, Any]) -> str:
    raw = str(_page_automation(payload).get("current_page") or "").strip()
    return raw if not raw or raw.startswith("/") else f"/{raw}"


def _auth_state(payload: dict[str, Any]) -> str:
    page_auth = str(_page_automation(payload).get("auth_state") or "").strip()
    return page_auth or str(payload.get("auth_state") or "").strip()


def _auth_mode(payload: dict[str, Any]) -> str:
    page_auth = str(_page_automation(payload).get("auth_mode") or "").strip()
    return page_auth or str(payload.get("auth_mode") or "").strip()


def _grading_to_brain_probe(payload: dict[str, Any]) -> dict[str, Any]:
    probe = _page_automation(payload).get("grading_to_brain_probe")
    return probe if isinstance(probe, dict) else {}


def _p4_readback_ids(p4_package: dict[str, Any]) -> dict[str, Any]:
    return dict((p4_package.get("p4_ws_readback") or {}).get("readback_ids") or {})


def _p4_projection_hashes(p4_package: dict[str, Any]) -> dict[str, str]:
    api = dict(p4_package.get("api_readbacks") or {})
    projection = dict(api.get("learning_brain_projection") or {})
    report = dict(api.get("mobile_learning_report_v2") or {})
    return {
        "learning_brain_projection": str(projection.get("output_projection_hash") or ""),
        "mobile_learning_report_v2": str(report.get("output_projection_hash") or ""),
    }


def build_p5_real_wechat_package_readback_package(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT,
    p4_package: dict[str, Any] | None = None,
    wechat_smoke_payload: dict[str, Any] | None = None,
    auto_port: int = 9420,
    timeout_seconds: float = 45.0,
    page_wait_ms: int = 12000,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    p4 = p4_package if p4_package is not None else _default_p4_package()
    wechat = (
        wechat_smoke_payload
        if wechat_smoke_payload is not None
        else _run_live_wechat_smoke(
            auto_port=auto_port,
            timeout_seconds=timeout_seconds,
            page_wait_ms=page_wait_ms,
        )
    )
    p4_ids = _p4_readback_ids(p4)
    p4_hashes = _p4_projection_hashes(p4)
    p4_strong = (p4.get("p4_ws_readback") or {}).get("verdict") == "STRONG-GO"
    page = _page_automation(wechat)
    probe = _grading_to_brain_probe(wechat)
    target_ok = (
        str(wechat.get("entry_surface") or "") == "real_wechat_package"
        and str(wechat.get("devtools_project_root") or "") == "yousenwebview"
        and str(wechat.get("target_subpackage") or "") == "packageDeeptutor"
        and str(wechat.get("target_page") or "") == "/packageDeeptutor/pages/report/report"
    )
    scenario_passed = (
        bool(wechat.get("ok"))
        and str(wechat.get("scenario_evidence_status") or "") == "passed"
        and str(wechat.get("trace_source") or "") == "devtools_cli_auto_page"
        and bool(page.get("ok"))
        and _page_path(wechat) == "/packageDeeptutor/pages/report/report"
    )
    auth_ok = _auth_state(wechat) in {"qa_token", "logged_in"} and _auth_mode(wechat) in {
        "manual_token",
        "local_dev_wechat",
        "real_wechat",
    }
    page_loop_present = bool(probe.get("has_grading_to_brain_loop")) and (
        bool(str(probe.get("status") or "").strip())
        or int(probe.get("stage_count") or 0) >= 1
        or int(probe.get("evidence_ref_count") or 0) >= 1
        or bool(str(probe.get("current_action_title") or "").strip())
    )
    p4_chain_linked = p4_strong and bool(p4_ids.get("ws_api_surface_pair_id"))

    blockers: list[str] = []
    if not p4_strong:
        blockers.append("p4_ws_readback_not_strong_go")
    if not target_ok:
        blockers.append("real_wechat_project_or_target_boundary_invalid")
    if not scenario_passed:
        blockers.append("devtools_page_scenario_not_passed")
    if not auth_ok:
        blockers.append("real_package_auth_not_established")
    if not page_loop_present:
        blockers.append("grading_to_brain_loop_not_visible_in_real_package")
    if not p4_chain_linked:
        blockers.append("p4_chain_readback_id_missing")

    package = {
        "schema_version": "luban_p5_real_wechat_package_readback_gate.v1",
        "generated_at": "2026-06-12",
        "p5_real_wechat_package_readback": {
            "verdict": "STRONG-GO" if not blockers else "NO-GO",
            "mode": "devtools_real_package_page_readback",
            "real_wechat_package_readback_exercised": scenario_passed,
            "page_grading_to_brain_loop_present": page_loop_present,
            "p4_chain_linked": p4_chain_linked,
            "blockers": blockers,
        },
        "real_wechat_package": {
            "entry_surface": wechat.get("entry_surface"),
            "trace_source": wechat.get("trace_source"),
            "devtools_project_root": wechat.get("devtools_project_root"),
            "project_path": wechat.get("project_path"),
            "target_subpackage": wechat.get("target_subpackage"),
            "target_page": wechat.get("target_page"),
            "entry_flow": wechat.get("entry_flow"),
            "scenario_evidence_status": wechat.get("scenario_evidence_status"),
            "readiness_status": wechat.get("readiness_status"),
            "readiness_blockers": list(wechat.get("readiness_blockers") or []),
            "auth_state": _auth_state(wechat),
            "auth_mode": _auth_mode(wechat),
            "current_page": _page_path(wechat),
            "grading_to_brain_probe": probe,
        },
        "readback_ids": {
            "p4": {
                "turn_id": p4_ids.get("turn_id"),
                "learner_memory_event_id": p4_ids.get("learner_memory_event_id"),
                "ws_api_surface_pair_id": p4_ids.get("ws_api_surface_pair_id"),
            },
            "p4_projection_hashes": p4_hashes,
        },
        "raw_wechat_smoke_artifact": wechat,
        "local_artifacts": {
            "p4_package_source": _artifact_path(P4_PACKAGE_PATH),
        },
        "not_exercised": [
            "production_db_write",
            "canonical_learner_truth_write",
            "published_registry_write",
            "remote_or_aliyun_write",
            "official_score_promotion",
            "real_provider_call",
        ],
        "safety": {
            "production_write_count": 0,
            "db_write_count": 0,
            "remote_write_count": 0,
            "canonical_truth_written": False,
            "published_registry_written": False,
            "official_score_allowed": False,
            "is_release_truth": False,
        },
    }
    (out / "wechat_devtools_smoke.json").write_text(
        json.dumps(wechat, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "p5_real_wechat_package_readback_package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--p4-package-path", default=str(P4_PACKAGE_PATH))
    parser.add_argument("--wechat-smoke-path", default="")
    parser.add_argument("--auto-port", type=int, default=9420)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--page-wait-ms", type=int, default=12000)
    args = parser.parse_args()
    p4_package = _read_json(Path(args.p4_package_path)) if args.p4_package_path else _default_p4_package()
    wechat_payload = _read_json(Path(args.wechat_smoke_path)) if args.wechat_smoke_path else None
    package = build_p5_real_wechat_package_readback_package(
        output_dir=args.output_dir,
        p4_package=p4_package,
        wechat_smoke_payload=wechat_payload,
        auto_port=args.auto_port,
        timeout_seconds=args.timeout_seconds,
        page_wait_ms=args.page_wait_ms,
    )
    print(json.dumps(package, ensure_ascii=False, indent=2))
    return 0 if (package.get("p5_real_wechat_package_readback") or {}).get("verdict") == "STRONG-GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
