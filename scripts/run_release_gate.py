#!/usr/bin/env python3
"""Build a release gate report from OM/ARR/AAE/OA runs."""

from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability import get_release_lineage_snapshot  # noqa: E402
from deeptutor.services.observability.control_plane_store import load_payload_json  # noqa: E402
from deeptutor.services.observability.release_gate import build_release_gate_report  # noqa: E402

_RELEASE_SPINE_KEYS = (
    "release_id",
    "git_sha",
    "deployment_environment",
    "prompt_version",
    "ff_snapshot_hash",
    "deploy_manifest_hash",
)


def _load_json(path: str | None, *, expected_kind: str | None = None) -> dict | None:
    return load_payload_json(path, expected_kind=expected_kind)


def _load_store_payload(kind: str, *, fallback: bool = True) -> dict | None:
    return get_control_plane_store().latest_payload(kind, fallback=fallback)


def _payload_release(payload: dict | None) -> dict:
    release = (payload or {}).get("release")
    return release if isinstance(release, dict) else {}


def _same_release_spine(expected: dict, actual: dict) -> bool:
    expected_values = {
        key: str((expected or {}).get(key) or "").strip()
        for key in _RELEASE_SPINE_KEYS
        if str((expected or {}).get(key) or "").strip()
    }
    if not expected_values:
        return True
    return all(str((actual or {}).get(key) or "").strip() == value for key, value in expected_values.items())


def _build_report_only_plan_completion_payload(*, release: dict) -> dict:
    return {
        "run_id": f"plan-completion-report-only-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": dict(release or {}),
        "scope_mode": "report_only",
        "status": "WARN",
        "summary": {
            "total": 0,
            "scoped": 0,
            "done": 0,
            "partial": 0,
            "not_done": 0,
            "unverifiable": 0,
            "out_of_scope": 0,
            "plan_count": 0,
            "changed_file_count": 0,
            "evidence_file_count": 0,
        },
        "plan_files": [],
        "changed_files": [],
        "evidence_files": [],
        "items": [],
        "blockers": [],
        "warnings": ["plan_completion_report_only_placeholder"],
    }


def _ensure_report_only_plan_completion_payload(
    *,
    existing_payload: dict | None,
    release: dict,
) -> dict | None:
    if existing_payload is not None and _same_release_spine(release, _payload_release(existing_payload)):
        return existing_payload
    payload = _build_report_only_plan_completion_payload(release=release)
    get_control_plane_store().write_run(
        kind="plan_completion_audits",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    return payload


def _render_markdown(payload: dict) -> str:
    lines = [
        "# Release Gate",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- release_id: `{(payload.get('release') or {}).get('release_id', 'unknown')}`",
        f"- final_status: `{payload.get('final_status')}`",
        f"- recommendation: `{payload.get('recommendation')}`",
        "",
        "## Gates",
        "",
    ]
    for item in payload.get("gate_results") or []:
        lines.append(f"- `{item['gate']}` => `{item['status']}` | {item['summary']}")
    lines.extend(["", "## Blockers", ""])
    blockers = payload.get("blockers") or []
    if not blockers:
        lines.append("- 无")
    else:
        for blocker in blockers:
            lines.append(f"- `{blocker}`")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor release gate")
    parser.add_argument("--om-json")
    parser.add_argument("--arr-json")
    parser.add_argument("--aae-json")
    parser.add_argument("--oa-json")
    parser.add_argument("--change-impact-json")
    parser.add_argument("--plan-completion-json")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="只生成报告，不用退出码作为上线 gate；默认 recommendation 非 canary 时非 0 退出",
    )
    args = parser.parse_args()

    om_payload = _load_json(args.om_json, expected_kind="om_runs") or _load_store_payload("om_runs")
    arr_payload = _load_json(args.arr_json, expected_kind="arr_runs") or _load_store_payload("arr_runs")
    benchmark_payload = _load_store_payload("benchmark_runs", fallback=False)
    aae_payload = _load_json(args.aae_json, expected_kind="aae_composite_runs") or _load_store_payload("aae_composite_runs")
    oa_payload = _load_json(args.oa_json, expected_kind="oa_runs") or _load_store_payload("oa_runs")
    change_impact_payload = _load_json(args.change_impact_json, expected_kind="change_impact_runs") or _load_store_payload("change_impact_runs")
    current_release = get_release_lineage_snapshot()
    explicit_plan_completion_payload = _load_json(args.plan_completion_json, expected_kind="plan_completion_audits")
    plan_completion_payload = explicit_plan_completion_payload or _load_store_payload("plan_completion_audits")
    if args.report_only and explicit_plan_completion_payload is None:
        plan_completion_payload = _ensure_report_only_plan_completion_payload(
            existing_payload=plan_completion_payload,
            release=current_release,
        )
    payload = build_release_gate_report(
        om_payload=om_payload,
        arr_payload=arr_payload,
        benchmark_payload=benchmark_payload,
        aae_payload=aae_payload,
        oa_payload=oa_payload,
        change_impact_payload=change_impact_payload,
        plan_completion_payload=plan_completion_payload,
        release=current_release,
    )
    store_paths = get_control_plane_store().write_run(
        kind="release_gate_runs",
        run_id=payload["run_id"],
        release_id=str((payload.get("release") or {}).get("release_id") or ""),
        payload=payload,
    )
    md_path = Path(store_paths["json_path"]).with_suffix(".md")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(f"Release gate completed: {payload['run_id']}")
    print(f"Final status: {payload['final_status']}")
    print(f"Recommendation: {payload['recommendation']}")
    print(f"JSON: {store_paths['json_path']}")
    print(f"MD:   {md_path}")
    if not args.report_only and payload.get("recommendation") != "canary":
        raise SystemExit(f"release_gate_failed: recommendation={payload.get('recommendation')}")


if __name__ == "__main__":
    main()
