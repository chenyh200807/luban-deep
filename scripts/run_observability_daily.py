#!/usr/bin/env python3
"""Run the daily observability spine: ObserverSnapshot -> ChangeImpact -> OA -> Gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.benchmark.runner import run_benchmark  # noqa: E402
from deeptutor.services.benchmark.runner import write_benchmark_artifacts  # noqa: E402
from deeptutor.services.observability import get_control_plane_store  # noqa: E402
from deeptutor.services.observability.aae_composite import build_aae_composite_run  # noqa: E402
from deeptutor.services.observability.arr_runner import run_arr  # noqa: E402
from deeptutor.services.observability.arr_runner import write_arr_artifacts  # noqa: E402
from deeptutor.services.observability.change_impact import DEFAULT_CHANGE_IMPACT_BASE_REF  # noqa: E402
from deeptutor.services.observability.change_impact import build_change_impact_run  # noqa: E402
from deeptutor.services.observability.change_impact import collect_git_changed_files  # noqa: E402
from deeptutor.services.observability.change_impact import render_change_impact_markdown  # noqa: E402
from deeptutor.services.observability.control_plane_store import load_payload_json  # noqa: E402
from deeptutor.services.observability.om_snapshot import build_om_run  # noqa: E402
from deeptutor.services.observability.oa_runner import build_oa_run  # noqa: E402
from deeptutor.services.observability.observer_snapshot import build_observer_snapshot  # noqa: E402
from deeptutor.services.observability.observer_snapshot import write_observer_snapshot_artifacts  # noqa: E402
from deeptutor.services.observability.plan_completion import build_plan_completion_audit  # noqa: E402
from deeptutor.services.observability.plan_completion import render_plan_completion_markdown  # noqa: E402
from deeptutor.services.observability.readiness_matrix import build_current_release_readiness_matrix_payload  # noqa: E402
from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot  # noqa: E402
from deeptutor.services.observability.release_gate import build_release_gate_report  # noqa: E402
from deeptutor.services.observability.run_history import build_observability_run_history_from_dir  # noqa: E402
from deeptutor.services.observability.unified_ws_smoke import run_unified_ws_smoke  # noqa: E402

DEFAULT_BASE_REF = DEFAULT_CHANGE_IMPACT_BASE_REF
DEFAULT_API_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_BENCHMARK_SUITES = (
    "pr_gate_core",
    "regression_watch",
    "real_exam_quality_spine",
)
DEFAULT_PLAN_COMPLETION_PLANS = ("docs/plan/INDEX.md",)
SURFACE_READINESS_CHECKS = (
    ("playwright", "Playwright"),
    ("wechat_devtools", "微信 DevTools"),
)
WECHAT_DEVTOOLS_PROJECT_ROOT = "yousenwebview"
WECHAT_DEVTOOLS_TARGET_SUBPACKAGE = "packageDeeptutor"


def _surface_readiness_missing_summary(check_id: str, label: str) -> str:
    if check_id == "wechat_devtools":
        return (
            f"{label} readiness evidence missing for current release: run the daily "
            f"DevTools CLI smoke against {WECHAT_DEVTOOLS_PROJECT_ROOT}"
        )
    return f"{label} readiness evidence missing for current release"


def _surface_readiness_missing_evidence(
    *,
    check_id: str,
    changed_preview: str,
) -> list[str]:
    evidence = [
        "source=daily_observability_fallback",
        "reason=no current-release readiness row existed",
        f"changed_files={changed_preview}",
    ]
    if check_id == "wechat_devtools":
        evidence.extend(
            [
                "expected_task=python scripts/run_readiness_check.py --check-id wechat_devtools --report-only",
                "default_smoke=python scripts/run_wechat_devtools_daily_smoke.py",
                "entry_surface=real_wechat_package",
                f"project_path={WECHAT_DEVTOOLS_PROJECT_ROOT}",
                f"target_subpackage={WECHAT_DEVTOOLS_TARGET_SUBPACKAGE}",
                "auth_state=unknown",
                "auth_mode=none",
                "coverage_targets=container,project_config,page_stack,network_baseURL,WS,cache,login",
                "boundary=islogin/open are preflight until page scenario or automator evidence exists",
            ]
        )
    return evidence


def _load_json(path: str | None, *, expected_kind: str | None = None) -> dict[str, Any] | None:
    return load_payload_json(path, expected_kind=expected_kind)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _payload_release(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    release = payload.get("release")
    if isinstance(release, dict) and release:
        return release
    release_spine = payload.get("release_spine")
    return release_spine if isinstance(release_spine, dict) else {}


def _same_release(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    expected_release_id = str((expected or {}).get("release_id") or "").strip()
    expected_git_sha = str((expected or {}).get("git_sha") or "").strip()
    actual_release_id = str((actual or {}).get("release_id") or "").strip()
    actual_git_sha = str((actual or {}).get("git_sha") or "").strip()
    if expected_git_sha and actual_git_sha:
        return expected_git_sha == actual_git_sha
    if expected_release_id and actual_release_id:
        return expected_release_id == actual_release_id
    return False


def _current_release_payload(store, kind: str, *, release: dict[str, Any]) -> dict[str, Any] | None:
    try:
        records = store.list_runs(kind, limit=100)
    except (FileNotFoundError, TypeError, ValueError):
        records = []
    for record in records:
        payload = (record or {}).get("payload")
        if isinstance(payload, dict) and _same_release(release, _payload_release(payload)):
            return payload
    latest_payload = store.latest_payload(kind, fallback=False)
    if isinstance(latest_payload, dict) and _same_release(release, _payload_release(latest_payload)):
        return latest_payload
    return None


def _load_metrics_snapshot(*, api_base_url: str, metrics_json: str | None) -> dict[str, Any]:
    if metrics_json:
        payload = _load_json(metrics_json)
        if not isinstance(payload, dict):
            raise TypeError("metrics snapshot must be a JSON object")
        return payload

    try:
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            response = client.get(f"{api_base_url.rstrip('/')}/metrics")
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("metrics endpoint must return JSON object")
        return payload
    except Exception:
        from fastapi.testclient import TestClient

        from deeptutor.api.main import app
        from deeptutor.api.main import get_circuit_breaker_snapshot
        from deeptutor.api.main import get_readyz_payload
        from deeptutor.api.main import get_release_lineage_snapshot as get_app_release_snapshot
        from deeptutor.api.main import get_surface_event_store
        from deeptutor.api.main import get_tracker_snapshot
        from deeptutor.api.main import get_turn_runtime_metrics

        with TestClient(app) as client:
            client.get("/healthz").raise_for_status()
            payload = {
                "release": get_app_release_snapshot(),
                "http": app.state.runtime_metrics.snapshot(),
                "turn_runtime": get_turn_runtime_metrics().snapshot(),
                "surface_events": get_surface_event_store().snapshot(),
                "readiness": get_readyz_payload(app)[1],
                "providers": {
                    "error_rates": get_tracker_snapshot(),
                    "circuit_breakers": get_circuit_breaker_snapshot(),
                },
            }
        return payload


def _ensure_om_payload(
    *,
    store,
    release: dict[str, Any],
    metrics_json: str | None,
    api_base_url: str,
    unified_ws_smoke_timeout: float,
) -> dict[str, Any] | None:
    # OM is the runtime evidence row for this daily pass. Rebuild it even when
    # a same-release row exists so /api/v1/ws smoke reflects the current process.
    unified_ws_smoke = _run_unified_ws_smoke_check(
        api_base_url=api_base_url,
        timeout_seconds=unified_ws_smoke_timeout,
    )
    metrics_snapshot = _load_metrics_snapshot(api_base_url=api_base_url, metrics_json=metrics_json)
    payload = build_om_run(
        metrics_snapshot=metrics_snapshot,
        stack_health=[],
        smoke_checks=[unified_ws_smoke],
    )
    store.write_run(
        kind="om_runs",
        run_id=payload["run_id"],
        release_id=str((_payload_release(payload) or {}).get("release_id") or ""),
        payload=payload,
    )
    return payload


def _run_unified_ws_smoke_check(*, api_base_url: str, timeout_seconds: float) -> dict[str, Any]:
    auth_token = _resolve_unified_ws_smoke_token(api_base_url=api_base_url)
    try:
        payload = asyncio.run(
            run_unified_ws_smoke(
                api_base_url=api_base_url,
                message="请只回复 ok。",
                language="zh",
                auth_token=auth_token,
                timeout_seconds=timeout_seconds,
            )
        )
    except Exception as exc:
        return {
            "name": "unified_ws_smoke",
            "ok": False,
            "summary": f"unified /api/v1/ws smoke failed before terminal event: {type(exc).__name__}",
            "evidence": [str(exc)[:500]],
        }

    terminal = payload.get("terminal_event") or {}
    messages = payload.get("messages") or []
    return {
        "name": "unified_ws_smoke",
        "ok": bool(payload.get("passed")),
        "summary": "unified /api/v1/ws reached terminal done"
        if payload.get("passed")
        else f"unified /api/v1/ws terminal={terminal.get('type')}",
        "evidence": [
            f"run_id={payload.get('run_id')}",
            f"api_base_url={payload.get('api_base_url')}",
            f"ws_url={payload.get('ws_url')}",
            f"auth_configured={bool(payload.get('auth_configured'))}",
            f"terminal={terminal.get('type')}",
            f"message_count={len(messages)}",
            f"duration_ms={payload.get('duration_ms')}",
        ],
    }


def _resolve_unified_ws_smoke_token(*, api_base_url: str) -> str:
    explicit = str(
        os.getenv("DEEPTUTOR_UNIFIED_WS_SMOKE_TOKEN")
        or os.getenv("DEEPTUTOR_WS_SMOKE_TOKEN")
        or ""
    ).strip()
    if explicit:
        return explicit

    parsed = urlparse(api_base_url)
    if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        try:
            from deeptutor.services.member_console import get_member_console_service

            issuer = getattr(get_member_console_service(), "_issue_access_token", None)
            if callable(issuer):
                return str(
                    issuer(
                        user_id="student_demo",
                        canonical_uid="student_demo",
                        ttl_seconds=300,
                    )
                )
        except Exception:
            return "demo-token-student_demo"
    return ""


def _ensure_benchmark_payload(
    *,
    store,
    release: dict[str, Any],
    output_dir: Path,
    api_base_url: str,
) -> dict[str, Any] | None:
    existing = _current_release_payload(store, "benchmark_runs", release=release)
    if isinstance(existing, dict) and _benchmark_covers_default_suites(existing):
        return existing

    payload = asyncio.run(
        run_benchmark(
            suite_names=DEFAULT_BENCHMARK_SUITES,
            output_dir=output_dir / "benchmark",
            api_base_url=api_base_url,
        )
    )
    write_benchmark_artifacts(payload, output_dir=output_dir / "benchmark")
    store.write_run(
        kind="benchmark_runs",
        run_id=str((payload.get("run_manifest") or {}).get("run_id") or ""),
        release_id=str((_payload_release(payload) or {}).get("release_id") or ""),
        payload=payload,
    )
    return payload


def _benchmark_covers_default_suites(payload: dict[str, Any]) -> bool:
    requested = {
        str(item)
        for item in ((payload.get("run_manifest") or {}).get("requested_suites") or [])
        if str(item).strip()
    }
    return all(suite in requested for suite in DEFAULT_BENCHMARK_SUITES)


def _quality_api_base_url(api_base_url: str, om_payload: dict[str, Any] | None) -> str:
    health_summary = (om_payload or {}).get("health_summary") or {}
    if health_summary.get("unified_ws_smoke_ok") is False:
        return ""
    return str(api_base_url or "").strip()


def _arr_covers_default_suites(payload: dict[str, Any]) -> bool:
    requested = {
        str(item)
        for item in ((payload.get("benchmark_run_manifest") or {}).get("requested_suites") or [])
        if str(item).strip()
    }
    return all(suite in requested for suite in DEFAULT_BENCHMARK_SUITES)


def _ensure_arr_payload(
    *,
    store,
    release: dict[str, Any],
    output_dir: Path,
    api_base_url: str,
) -> dict[str, Any] | None:
    existing = _current_release_payload(store, "arr_runs", release=release)
    if isinstance(existing, dict) and _arr_covers_default_suites(existing):
        return existing

    payload = asyncio.run(
        run_arr(
            mode="lite",
            output_dir=output_dir / "arr",
            api_base_url=api_base_url,
        )
    )
    write_arr_artifacts(payload, output_dir=output_dir / "arr")
    store.write_run(
        kind="arr_runs",
        run_id=str(payload.get("run_id") or ""),
        release_id=str((_payload_release(payload) or {}).get("release_id") or ""),
        payload=payload,
    )
    canonical_benchmark_payload = payload.get("canonical_benchmark_payload") or {}
    if isinstance(canonical_benchmark_payload, dict) and (canonical_benchmark_payload.get("run_manifest") or {}).get("run_id"):
        store.write_run(
            kind="benchmark_runs",
            run_id=str((canonical_benchmark_payload.get("run_manifest") or {}).get("run_id") or ""),
            release_id=str((canonical_benchmark_payload.get("release_spine") or {}).get("release_id") or ""),
            payload=canonical_benchmark_payload,
        )
    return payload


def _render_aae_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# AAE Snapshot",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- source_arr_run_id: `{payload.get('source_arr_run_id')}`",
        f"- composite: `{json.dumps(payload.get('composite') or {}, ensure_ascii=False)}`",
    ]
    return "\n".join(lines)


def _ensure_aae_payload(
    *,
    store,
    release: dict[str, Any],
    arr_payload: dict[str, Any] | None,
    om_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    existing = _current_release_payload(store, "aae_composite_runs", release=release)
    if isinstance(existing, dict):
        return existing
    if not isinstance(arr_payload, dict):
        return None

    payload = build_aae_composite_run(
        arr_payload=arr_payload,
        om_payload=om_payload,
        feedback_payload=None,
    )
    paths = store.write_run(
        kind="aae_composite_runs",
        run_id=str(payload.get("run_id") or ""),
        release_id=str((_payload_release(payload) or {}).get("release_id") or ""),
        payload=payload,
    )
    Path(paths["json_path"]).with_suffix(".md").write_text(
        _render_aae_markdown(payload),
        encoding="utf-8",
    )
    return payload


def _ensure_surface_readiness_rows(
    *,
    store,
    release: dict[str, Any],
    changed_files: list[str],
) -> None:
    changed_preview = ", ".join(changed_files[:8]) if changed_files else "none"
    for check_id, label in SURFACE_READINESS_CHECKS:
        for record in store.list_runs("readiness_checks", limit=100):
            payload = (record or {}).get("payload")
            if not isinstance(payload, dict):
                continue
            if str(payload.get("check_id") or "").strip() != check_id:
                continue
            if _same_release(release, _payload_release(payload)):
                break
        else:
            payload = {
                "run_id": f"{check_id}-{int(time.time())}",
                "check_id": check_id,
                "label": label,
                "status": "FAIL",
                "required": True,
                "summary": _surface_readiness_missing_summary(check_id, label),
                "evidence": _surface_readiness_missing_evidence(
                    check_id=check_id,
                    changed_preview=changed_preview,
                ),
                "blockers": [f"{check_id}_failed"],
                "release": dict(release or {}),
            }
            store.write_run(
                kind="readiness_checks",
                run_id=payload["run_id"],
                release_id=str((release or {}).get("release_id") or ""),
                payload=payload,
            )


def _ensure_plan_completion_payload(
    *,
    store,
    release: dict[str, Any],
    changed_files: list[str],
    output_dir: Path,
    base_ref: str,
) -> dict[str, Any]:
    existing = _current_release_payload(store, "plan_completion_audits", release=release)
    if isinstance(existing, dict) and str(existing.get("scope_mode") or "") != "report_only":
        return existing

    evidence_files = [
        _as_posix_relative(path)
        for path in (
            output_dir / "observer" / "raw_data_latest.json",
            output_dir / "run_history_latest.json",
        )
        if path.exists()
    ]
    payload = build_plan_completion_audit(
        plan_paths=list(DEFAULT_PLAN_COMPLETION_PLANS),
        changed_files=changed_files,
        evidence_files=evidence_files,
        base_ref=base_ref,
        scope_mode="changed",
        project_root=PROJECT_ROOT,
        release=release,
    )
    store_paths = store.write_run(
        kind="plan_completion_audits",
        run_id=payload["run_id"],
        release_id=str((_payload_release(payload) or {}).get("release_id") or ""),
        payload=payload,
    )
    Path(store_paths["json_path"]).with_suffix(".md").write_text(
        render_plan_completion_markdown(payload),
        encoding="utf-8",
    )
    _write_json(output_dir / "plan_completion" / f"{payload['run_id']}.json", payload)
    return payload


def _as_posix_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _write_contract_guard_readiness(
    *,
    store,
    changed_files: list[str],
    release: dict[str, Any],
) -> None:
    if not changed_files:
        return

    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "check_contract_guard.py"),
        *changed_files,
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = {
        "run_id": f"contract_guard-{int(time.time())}",
        "check_id": "contract_guard",
        "label": "Contract Guard",
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "required": True,
        "summary": "contract guard command passed"
        if result.returncode == 0
        else f"contract guard command failed with exit_code={result.returncode}",
        "evidence": [
            f"command={' '.join(command)}",
            f"exit_code={result.returncode}",
            *(([f"stdout={(result.stdout or '').strip()[:1200]}"]) if (result.stdout or "").strip() else []),
            *(([f"stderr={(result.stderr or '').strip()[:1200]}"]) if (result.stderr or "").strip() else []),
        ],
        "blockers": ["contract_guard_failed"] if result.returncode != 0 else [],
        "release": dict(release or {}),
    }
    store.write_run(
        kind="readiness_checks",
        run_id=payload["run_id"],
        release_id=str((release or {}).get("release_id") or ""),
        payload=payload,
    )


def _render_oa_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# OA Run",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- mode: `{payload.get('mode')}`",
        f"- causal_candidates: `{len(payload.get('causal_candidates') or [])}`",
        f"- root_causes: `{len(payload.get('root_causes') or [])}`",
        f"- blind_spots: `{len(payload.get('blind_spots') or [])}`",
    ]
    return "\n".join(lines)


def _render_gate_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Release Gate",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- final_status: `{payload.get('final_status')}`",
        f"- recommendation: `{payload.get('recommendation')}`",
        "",
        "## Gates",
        "",
    ]
    for item in payload.get("gate_results") or []:
        lines.append(f"- `{item.get('gate')}` => `{item.get('status')}` | {item.get('summary')}")
    return "\n".join(lines)


def build_daily_run_history(*, store_dir: str | Path, limit: int = 20) -> dict[str, Any]:
    return build_observability_run_history_from_dir(store_dir=store_dir, limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeepTutor daily observability control-plane spine")
    parser.add_argument("--base-ref", default=DEFAULT_BASE_REF)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--metrics-json")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--unified-ws-smoke-timeout", type=float, default=20.0)
    parser.add_argument("--event-days", type=int, default=1)
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    store = get_control_plane_store()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else store.base_dir / "_daily"
    output_dir.mkdir(parents=True, exist_ok=True)
    current_release = get_release_lineage_snapshot()
    changed_files = args.changed_file or collect_git_changed_files(base_ref=args.base_ref)

    om_payload = _ensure_om_payload(
        store=store,
        release=current_release,
        metrics_json=args.metrics_json,
        api_base_url=args.api_base_url,
        unified_ws_smoke_timeout=float(getattr(args, "unified_ws_smoke_timeout", 20.0) or 20.0),
    )
    arr_payload = _ensure_arr_payload(
        store=store,
        release=current_release,
        output_dir=output_dir,
        api_base_url=_quality_api_base_url(args.api_base_url, om_payload),
    )
    benchmark_payload = _ensure_benchmark_payload(
        store=store,
        release=current_release,
        output_dir=output_dir,
        api_base_url=_quality_api_base_url(args.api_base_url, om_payload),
    )
    _ensure_surface_readiness_rows(
        store=store,
        release=current_release,
        changed_files=changed_files,
    )
    aae_payload = _ensure_aae_payload(
        store=store,
        release=current_release,
        arr_payload=arr_payload,
        om_payload=om_payload,
    )

    metrics_snapshot = (om_payload or {}).get("metrics_snapshot") or _load_json(args.metrics_json)
    observer_payload = build_observer_snapshot(
        store=store,
        event_days=max(int(args.event_days or 1), 1),
        metrics_snapshot=metrics_snapshot,
        benchmark_payload=benchmark_payload,
        release=current_release,
    )
    observer_artifacts = write_observer_snapshot_artifacts(
        observer_payload,
        output_dir=output_dir / "observer",
    )
    store.write_run(
        kind="observer_snapshots",
        run_id=observer_payload["run_id"],
        release_id=str((observer_payload.get("release") or {}).get("release_id") or ""),
        payload=observer_payload,
    )

    _write_contract_guard_readiness(
        store=store,
        changed_files=changed_files,
        release=current_release,
    )
    change_impact_payload = build_change_impact_run(
        changed_files=changed_files,
        observer_payload=observer_payload,
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
        release=current_release,
    )
    change_paths = store.write_run(
        kind="change_impact_runs",
        run_id=change_impact_payload["run_id"],
        release_id=str((change_impact_payload.get("release") or {}).get("release_id") or ""),
        payload=change_impact_payload,
    )
    Path(change_paths["json_path"]).with_suffix(".md").write_text(
        render_change_impact_markdown(change_impact_payload),
        encoding="utf-8",
    )

    oa_payload = build_oa_run(
        mode="daily",
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
        benchmark_payload=benchmark_payload,
        observer_payload=observer_payload,
        change_impact_payload=change_impact_payload,
        release=current_release,
    )
    oa_paths = store.write_run(
        kind="oa_runs",
        run_id=oa_payload["run_id"],
        release_id=str((oa_payload.get("release") or {}).get("release_id") or ""),
        payload=oa_payload,
    )
    Path(oa_paths["json_path"]).with_suffix(".md").write_text(
        _render_oa_markdown(oa_payload),
        encoding="utf-8",
    )

    plan_completion_payload = _ensure_plan_completion_payload(
        store=store,
        release=current_release,
        changed_files=changed_files,
        output_dir=output_dir,
        base_ref=args.base_ref,
    )
    incident_payload = _current_release_payload(store, "incident_ledger", release=current_release)
    readiness_payload = build_current_release_readiness_matrix_payload(
        store=store,
        release=current_release,
    )
    gate_payload = build_release_gate_report(
        om_payload=om_payload,
        arr_payload=arr_payload,
        benchmark_payload=benchmark_payload,
        incident_payload=incident_payload,
        aae_payload=aae_payload,
        oa_payload=oa_payload,
        change_impact_payload=change_impact_payload,
        plan_completion_payload=plan_completion_payload,
        readiness_payload=readiness_payload,
        release=current_release,
        quality_evidence_required=True,
    )
    gate_paths = store.write_run(
        kind="release_gate_runs",
        run_id=gate_payload["run_id"],
        release_id=str((gate_payload.get("release") or {}).get("release_id") or ""),
        payload=gate_payload,
    )
    Path(gate_paths["json_path"]).with_suffix(".md").write_text(
        _render_gate_markdown(gate_payload),
        encoding="utf-8",
    )

    daily_payload = {
        "run_id": f"observability-daily-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": dict(current_release),
        "verdict": "STALE"
        if gate_payload.get("verdict") == "STALE" or oa_payload.get("verdict") == "STALE"
        else "TRUSTED",
        "source_runs": {
            "observer_snapshot_run_id": observer_payload.get("run_id"),
            "change_impact_run_id": change_impact_payload.get("run_id"),
            "oa_run_id": oa_payload.get("run_id"),
            "release_gate_run_id": gate_payload.get("run_id"),
            "om_run_id": (om_payload or {}).get("run_id"),
            "benchmark_run_id": ((benchmark_payload or {}).get("run_manifest") or {}).get("run_id")
            or (benchmark_payload or {}).get("run_id"),
        },
        "metrics": {
            "change_impact_risk_level": change_impact_payload.get("risk_level"),
            "oa_root_cause_count": len(oa_payload.get("root_causes") or []),
            "oa_causal_candidate_count": len(oa_payload.get("causal_candidates") or []),
            "release_gate_status": gate_payload.get("final_status"),
            "om_ready": ((om_payload or {}).get("health_summary") or {}).get("ready"),
            "benchmark_pass_rate": (benchmark_payload or {}).get("summary", {}).get("pass_rate"),
        },
    }
    daily_paths = store.write_run(
        kind="daily_trends",
        run_id=daily_payload["run_id"],
        release_id=str((daily_payload.get("release") or {}).get("release_id") or ""),
        payload=daily_payload,
    )
    run_history = build_daily_run_history(store_dir=store.base_dir)
    _write_json(output_dir / "run_history_latest.json", run_history)

    print(f"Daily observability completed: {daily_payload['run_id']}")
    print(f"Observer JSON: {observer_artifacts['json_path']}")
    print(f"ChangeImpact JSON: {change_paths['json_path']}")
    print(f"OA JSON: {oa_paths['json_path']}")
    print(f"ReleaseGate JSON: {gate_paths['json_path']}")
    print(f"DailyTrend JSON: {daily_paths['json_path']}")
    print(f"RunHistory JSON: {output_dir / 'run_history_latest.json'}")


if __name__ == "__main__":
    main()
