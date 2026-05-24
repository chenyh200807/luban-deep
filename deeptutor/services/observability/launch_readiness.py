from __future__ import annotations

import time
from typing import Any

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore

_PASS = "PASS"
_FAIL = "FAIL"
_WARN = "WARN"
_NOT_RUN = "NOT_RUN"
_SUPPORTED_STATUSES = {_PASS, _FAIL, _WARN, "SKIP", _NOT_RUN}
_RELEASE_SPINE_KEYS = (
    "release_id",
    "git_sha",
    "deployment_environment",
    "prompt_version",
    "ff_snapshot_hash",
    "deploy_manifest_hash",
)

_MANUAL_CHECKS = {
    "contract_guard": {
        "label": "Contract Guard",
        "required": True,
        "missing_summary": "contract guard 还没有进入 readiness evidence",
    },
    "playwright": {
        "label": "Playwright",
        "required": True,
        "missing_summary": "Playwright 回归还没有进入 readiness evidence",
    },
    "wechat_devtools": {
        "label": "微信 DevTools",
        "required": True,
        "missing_summary": "微信开发者工具验收还没有进入 readiness evidence",
    },
}


def build_launch_readiness_run(
    *,
    checks: dict[str, bool],
    release: dict[str, Any],
) -> dict[str, Any]:
    normalized_checks = {
        str(name): bool(value)
        for name, value in sorted((checks or {}).items(), key=lambda item: item[0])
    }
    ready = bool(normalized_checks) and all(normalized_checks.values())
    summary = "startup readiness checks passed" if ready else "startup readiness checks failed"
    evidence = [f"{name}={value}" for name, value in normalized_checks.items()]
    return {
        "run_id": f"launch-readiness-{int(time.time())}",
        "check_id": "launch_readiness",
        "label": "Launch Readiness",
        "status": _PASS if ready else _FAIL,
        "required": True,
        "summary": summary,
        "evidence": evidence,
        "blockers": [] if ready else ["launch_readiness_failed"],
        "release": dict(release or {}),
    }


def _payload(record: dict[str, Any] | None) -> dict[str, Any]:
    payload = (record or {}).get("payload")
    return payload if isinstance(payload, dict) else {}


def _latest_run(store: ObservabilityControlPlaneStore, kind: str) -> dict[str, Any]:
    try:
        return store.latest_run(kind) or {}
    except (FileNotFoundError, TypeError, ValueError):
        return {}


def _normalize_status(value: Any) -> str:
    normalized = str(value or "").strip().upper().replace("-", "_")
    if normalized == "CLEAR":
        return _PASS
    if normalized in {"BLOCKED", "ERROR"}:
        return _FAIL
    return normalized if normalized in _SUPPORTED_STATUSES else _WARN


def _row(
    *,
    check_id: str,
    label: str,
    status: str,
    required: bool,
    summary: str,
    evidence: list[str] | None = None,
    run_id: str | None = None,
    recorded_at: int | None = None,
    source_kind: str | None = None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "label": label,
        "status": _normalize_status(status),
        "required": bool(required),
        "summary": summary,
        "evidence": evidence or [],
        "run_id": run_id or "",
        "recorded_at": recorded_at,
        "source_kind": source_kind or "",
        "blockers": blockers or [],
    }


def _missing_row(check_id: str, label: str, summary: str, *, required: bool = True) -> dict[str, Any]:
    return _row(
        check_id=check_id,
        label=label,
        status=_NOT_RUN,
        required=required,
        summary=summary,
        blockers=[f"{check_id}_missing"] if required else [],
    )


def _gate_by_name(release_gate_payload: dict[str, Any], gate_name: str) -> dict[str, Any]:
    for item in release_gate_payload.get("gate_results") or []:
        if str(item.get("gate") or "") == gate_name:
            return item
    return {}


def _release_from_payloads(*payloads: dict[str, Any]) -> dict[str, Any]:
    for payload in payloads:
        release = payload.get("release") or payload.get("release_spine")
        if isinstance(release, dict) and release:
            return {key: release.get(key) or "" for key in _RELEASE_SPINE_KEYS}
    return {"release_id": "", "git_sha": "", "deployment_environment": ""}


def _release_signature(release: dict[str, Any]) -> tuple[str, str]:
    return (
        str(release.get("git_sha") or "").strip(),
        str(release.get("release_id") or "").strip(),
    )


def _record_release(record: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    release = payload.get("release") or payload.get("release_spine")
    if isinstance(release, dict) and release:
        return release
    if record:
        return {"release_id": str(record.get("release_id") or "").strip()}
    return {}


def _same_release(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    expected_values = {
        key: str(expected.get(key) or "").strip()
        for key in _RELEASE_SPINE_KEYS
        if str(expected.get(key) or "").strip()
    }
    if not expected_values:
        return True
    return all(str(actual.get(key) or "").strip() == value for key, value in expected_values.items())


def _has_release_signature(release: dict[str, Any]) -> bool:
    git_sha, release_id = _release_signature(release)
    return bool(git_sha or release_id)


def _latest_run_for_release(
    store: ObservabilityControlPlaneStore,
    kind: str,
    *,
    release: dict[str, Any],
    limit: int = 100,
) -> dict[str, Any]:
    if not _has_release_signature(release):
        return _latest_run(store, kind)
    try:
        records = store.list_runs(kind, limit=limit)
    except (FileNotFoundError, TypeError, ValueError):
        return {}
    for record in records:
        payload = _payload(record)
        if _same_release(release, _record_release(record, payload)):
            return record
    return records[0] if records else {}


def _release_label(release: dict[str, Any]) -> str:
    git_sha, release_id = _release_signature(release)
    return git_sha or release_id or "unknown"


def _stale_release_row(
    *,
    check_id: str,
    label: str,
    expected_release: dict[str, Any],
    actual_release: dict[str, Any],
    required: bool = True,
    run_id: str | None = None,
    recorded_at: int | None = None,
    source_kind: str | None = None,
) -> dict[str, Any]:
    return _row(
        check_id=check_id,
        label=label,
        status=_FAIL,
        required=required,
        summary="证据不属于当前 release spine",
        evidence=[
            f"expected_release={_release_label(expected_release)}",
            f"actual_release={_release_label(actual_release)}",
        ],
        run_id=run_id,
        recorded_at=recorded_at,
        source_kind=source_kind,
        blockers=[f"{check_id}_stale_release"] if required else [],
    )


def _manual_check_rows(store: ObservabilityControlPlaneStore, *, release: dict[str, Any]) -> list[dict[str, Any]]:
    records = store.list_runs("readiness_checks", limit=100)
    latest_any_by_check: dict[str, dict[str, Any]] = {}
    latest_release_by_check: dict[str, dict[str, Any]] = {}
    for record in records:
        payload = _payload(record)
        check_id = str(payload.get("check_id") or record.get("check_id") or "").strip()
        if not check_id:
            continue
        if check_id not in latest_any_by_check:
            latest_any_by_check[check_id] = record
        if check_id not in latest_release_by_check and _same_release(release, _record_release(record, payload)):
            latest_release_by_check[check_id] = record

    rows: list[dict[str, Any]] = []
    for check_id, config in _MANUAL_CHECKS.items():
        record = latest_release_by_check.get(check_id) or latest_any_by_check.get(check_id)
        payload = _payload(record)
        if not record:
            rows.append(
                _missing_row(
                    check_id,
                    str(config["label"]),
                    str(config["missing_summary"]),
                    required=bool(config["required"]),
                )
            )
            continue
        actual_release = _record_release(record, payload)
        if not _same_release(release, actual_release):
            rows.append(
                _stale_release_row(
                    check_id=check_id,
                    label=str(payload.get("label") or config["label"]),
                    expected_release=release,
                    actual_release=actual_release,
                    required=bool(payload.get("required", config["required"])),
                    run_id=str(record.get("run_id") or payload.get("run_id") or ""),
                    recorded_at=record.get("recorded_at"),
                    source_kind="readiness_checks",
                )
            )
            continue
        rows.append(
            _row(
                check_id=check_id,
                label=str(payload.get("label") or config["label"]),
                status=str(payload.get("status") or _WARN),
                required=bool(payload.get("required", config["required"])),
                summary=str(payload.get("summary") or ""),
                evidence=[str(item) for item in payload.get("evidence") or []],
                run_id=str(record.get("run_id") or payload.get("run_id") or ""),
                recorded_at=record.get("recorded_at"),
                source_kind="readiness_checks",
                blockers=[str(item) for item in payload.get("blockers") or []],
            )
        )
    return rows


def _release_gate_row(release_gate_record: dict[str, Any], release_gate_payload: dict[str, Any]) -> dict[str, Any]:
    if not release_gate_payload:
        return _missing_row("release_gate", "Release Gate", "release gate 尚未生成")
    return _row(
        check_id="release_gate",
        label="Release Gate",
        status=str(release_gate_payload.get("final_status") or _WARN),
        required=True,
        summary=f"recommendation={release_gate_payload.get('recommendation') or 'unknown'}",
        evidence=[
            f"gate_results={len(release_gate_payload.get('gate_results') or [])}",
            f"blockers={len(release_gate_payload.get('blockers') or [])}",
        ],
        run_id=str(release_gate_payload.get("run_id") or release_gate_record.get("run_id") or ""),
        recorded_at=release_gate_record.get("recorded_at"),
        source_kind="release_gate_runs",
        blockers=[str(item) for item in release_gate_payload.get("blockers") or []],
    )


def _benchmark_row(
    *,
    release: dict[str, Any],
    release_gate_record: dict[str, Any],
    release_gate_payload: dict[str, Any],
    arr_record: dict[str, Any],
    arr_payload: dict[str, Any],
    benchmark_record: dict[str, Any],
    benchmark_payload: dict[str, Any],
) -> dict[str, Any]:
    p2 = _gate_by_name(release_gate_payload, "P2 Benchmark Regression")
    if p2:
        return _row(
            check_id="benchmark",
            label="Benchmark / ARR",
            status=str(p2.get("status") or _WARN),
            required=True,
            summary=str(p2.get("summary") or ""),
            evidence=[str(item) for item in p2.get("evidence") or []],
            run_id=str(release_gate_payload.get("run_id") or release_gate_record.get("run_id") or ""),
            recorded_at=release_gate_record.get("recorded_at"),
            source_kind="release_gate_runs",
            blockers=[str(item) for item in p2.get("blockers") or []],
        )

    quality_payload = arr_payload or benchmark_payload
    if not quality_payload:
        return _missing_row("benchmark", "Benchmark / ARR", "benchmark / ARR 还没有进入 control-plane")
    quality_record = arr_record if arr_payload else benchmark_record
    actual_release = _record_release(quality_record, quality_payload)
    if not _same_release(release, actual_release):
        return _stale_release_row(
            check_id="benchmark",
            label="Benchmark / ARR",
            expected_release=release,
            actual_release=actual_release,
            run_id=str(quality_payload.get("run_id") or ""),
            recorded_at=quality_record.get("recorded_at"),
            source_kind="arr_runs" if arr_payload else "benchmark_runs",
        )
    summary = quality_payload.get("summary") or {}
    failed = int(summary.get("failed") or 0)
    status = _FAIL if failed > 0 else _PASS
    return _row(
        check_id="benchmark",
        label="Benchmark / ARR",
        status=status,
        required=True,
        summary="quality run 已记录" if status == _PASS else "quality run 存在失败",
        evidence=[
            f"run_id={quality_payload.get('run_id') or ((quality_payload.get('run_manifest') or {}).get('run_id'))}",
            f"pass_rate={summary.get('pass_rate')}",
            f"failed={failed}",
        ],
        run_id=str(quality_payload.get("run_id") or ""),
        recorded_at=quality_record.get("recorded_at"),
        source_kind="arr_runs" if arr_payload else "benchmark_runs",
        blockers=["benchmark_failure"] if failed > 0 else [],
    )


def _oa_arr_aae_row(
    *,
    release: dict[str, Any],
    release_gate_record: dict[str, Any],
    release_gate_payload: dict[str, Any],
    arr_record: dict[str, Any],
    arr_payload: dict[str, Any],
    aae_record: dict[str, Any],
    aae_payload: dict[str, Any],
    oa_payload: dict[str, Any],
    oa_record: dict[str, Any],
) -> dict[str, Any]:
    gates = [
        _gate_by_name(release_gate_payload, "P2 Benchmark Regression"),
        _gate_by_name(release_gate_payload, "P3 AAE"),
        _gate_by_name(release_gate_payload, "P4 Blind Spot Budget"),
    ]
    present_gates = [item for item in gates if item]
    if present_gates:
        statuses = [_normalize_status(item.get("status")) for item in present_gates]
        status = _FAIL if _FAIL in statuses else _WARN if _WARN in statuses or _NOT_RUN in statuses else _PASS
        return _row(
            check_id="oa_arr_aae",
            label="OA / ARR / AAE",
            status=status,
            required=True,
            summary=" / ".join(str(item.get("summary") or "") for item in present_gates if item.get("summary")),
            evidence=[f"{item.get('gate')}={item.get('status')}" for item in present_gates],
            run_id=str(release_gate_payload.get("run_id") or release_gate_record.get("run_id") or ""),
            recorded_at=release_gate_record.get("recorded_at"),
            source_kind="release_gate_runs",
            blockers=[str(blocker) for item in present_gates for blocker in item.get("blockers") or []],
        )

    missing = [
        name
        for name, payload in (("arr", arr_payload), ("aae", aae_payload), ("oa", oa_payload))
        if not payload
    ]
    if missing:
        return _row(
            check_id="oa_arr_aae",
            label="OA / ARR / AAE",
            status=_NOT_RUN,
            required=True,
            summary=f"缺少 {'/'.join(missing)} control-plane run",
            blockers=[f"{name}_missing" for name in missing],
        )
    stale_sources = [
        name
        for name, record, payload in (
            ("arr", arr_record, arr_payload),
            ("aae", aae_record, aae_payload),
            ("oa", oa_record, oa_payload),
        )
        if not _same_release(release, _record_release(record, payload))
    ]
    if stale_sources:
        return _row(
            check_id="oa_arr_aae",
            label="OA / ARR / AAE",
            status=_FAIL,
            required=True,
            summary=f"{'/'.join(stale_sources)} evidence 不属于当前 release spine",
            evidence=[f"expected_release={_release_label(release)}"],
            blockers=[f"{name}_stale_release" for name in stale_sources],
        )
    return _row(
        check_id="oa_arr_aae",
        label="OA / ARR / AAE",
        status=_PASS,
        required=True,
        summary="OA / ARR / AAE 最新运行均存在",
        evidence=[
            f"arr_run_id={arr_payload.get('run_id')}",
            f"aae_run_id={aae_payload.get('run_id')}",
            f"oa_run_id={oa_payload.get('run_id')}",
        ],
        run_id=str(oa_payload.get("run_id") or ""),
        recorded_at=oa_record.get("recorded_at"),
        source_kind="oa_runs",
    )


def _langfuse_row(
    observer_record: dict[str, Any],
    observer_payload: dict[str, Any],
    *,
    release: dict[str, Any],
) -> dict[str, Any]:
    trace_linkage = observer_payload.get("langfuse_trace_linkage") or {}
    data_sources = observer_payload.get("data_sources") or {}
    source = data_sources.get("langfuse_trace_linkage") or {}
    if not observer_payload:
        return _missing_row("langfuse", "Langfuse Trace Linkage", "observer snapshot 尚未生成，无法判断 Langfuse trace linkage")
    actual_release = _record_release(observer_record, observer_payload)
    if not _same_release(release, actual_release):
        return _stale_release_row(
            check_id="langfuse",
            label="Langfuse Trace Linkage",
            expected_release=release,
            actual_release=actual_release,
            run_id=str(observer_payload.get("run_id") or observer_record.get("run_id") or ""),
            recorded_at=observer_record.get("recorded_at"),
            source_kind="observer_snapshots",
        )
    trace_count = int(trace_linkage.get("trace_id_count") or source.get("sample_count") or 0)
    has_data = bool(source.get("has_data")) or trace_count > 0
    return _row(
        check_id="langfuse",
        label="Langfuse Trace Linkage",
        status=_PASS if has_data else _FAIL,
        required=True,
        summary="Langfuse trace_id linkage 可见" if has_data else "未看到可回链的 Langfuse trace_id",
        evidence=[
            f"trace_id_count={trace_count}",
            f"langfuse_host={trace_linkage.get('langfuse_host') or source.get('source_id') or ''}",
            f"freshness={source.get('freshness') or ''}",
        ],
        run_id=str(observer_payload.get("run_id") or observer_record.get("run_id") or ""),
        recorded_at=observer_record.get("recorded_at"),
        source_kind="observer_snapshots",
        blockers=[] if has_data else ["langfuse_trace_linkage_missing"],
    )


def _final_verdict(rows: list[dict[str, Any]]) -> tuple[str, str, list[str]]:
    required_rows = [row for row in rows if row.get("required")]
    blockers = [blocker for row in required_rows for blocker in row.get("blockers") or []]
    statuses = [_normalize_status(row.get("status")) for row in required_rows]
    if any(status in {_FAIL, _NOT_RUN} for status in statuses):
        return _FAIL, "hold", blockers
    if any(status == _WARN for status in statuses):
        return _WARN, "hold_with_conditions", blockers
    return _PASS, "canary", blockers


def _current_run_id(payload: dict[str, Any], record: dict[str, Any], release: dict[str, Any]) -> str | None:
    if not payload:
        return None
    if _has_release_signature(release) and not _same_release(release, _record_release(record, payload)):
        return None
    return str(payload.get("run_id") or record.get("run_id") or "") or None


def _current_benchmark_run_id(
    payload: dict[str, Any],
    record: dict[str, Any],
    release: dict[str, Any],
) -> str | None:
    run_id = _current_run_id(payload, record, release)
    if run_id:
        return run_id
    if _has_release_signature(release) and not _same_release(release, _record_release(record, payload)):
        return None
    return str((payload.get("run_manifest") or {}).get("run_id") or "") or None


def build_launch_readiness_dashboard(
    *,
    store: ObservabilityControlPlaneStore,
) -> dict[str, Any]:
    release_gate_record = _latest_run(store, "release_gate_runs")
    release_gate_payload = _payload(release_gate_record)
    release = _release_from_payloads(release_gate_payload)
    arr_record = _latest_run_for_release(store, "arr_runs", release=release)
    benchmark_record = _latest_run_for_release(store, "benchmark_runs", release=release)
    aae_record = _latest_run_for_release(store, "aae_composite_runs", release=release)
    oa_record = _latest_run_for_release(store, "oa_runs", release=release)
    observer_record = _latest_run_for_release(store, "observer_snapshots", release=release)
    arr_payload = _payload(arr_record)
    benchmark_payload = _payload(benchmark_record)
    aae_payload = _payload(aae_record)
    oa_payload = _payload(oa_record)
    observer_payload = _payload(observer_record)
    if not _has_release_signature(release):
        release = _release_from_payloads(
            release_gate_payload,
            arr_payload,
            benchmark_payload,
            aae_payload,
            oa_payload,
            observer_payload,
        )

    rows = [
        _release_gate_row(release_gate_record, release_gate_payload),
        *_manual_check_rows(store, release=release),
        _benchmark_row(
            release=release,
            release_gate_record=release_gate_record,
            release_gate_payload=release_gate_payload,
            arr_record=arr_record,
            arr_payload=arr_payload,
            benchmark_record=benchmark_record,
            benchmark_payload=benchmark_payload,
        ),
        _oa_arr_aae_row(
            release=release,
            release_gate_record=release_gate_record,
            release_gate_payload=release_gate_payload,
            arr_record=arr_record,
            arr_payload=arr_payload,
            aae_record=aae_record,
            aae_payload=aae_payload,
            oa_payload=oa_payload,
            oa_record=oa_record,
        ),
        _langfuse_row(observer_record, observer_payload, release=release),
    ]
    final_status, recommendation, blockers = _final_verdict(rows)
    return {
        "run_id": f"launch-readiness-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": release,
        "final_status": final_status,
        "recommendation": recommendation,
        "rows": rows,
        "blockers": blockers,
        "source_runs": {
            "release_gate_run_id": release_gate_payload.get("run_id"),
            "arr_run_id": _current_run_id(arr_payload, arr_record, release),
            "benchmark_run_id": _current_benchmark_run_id(benchmark_payload, benchmark_record, release),
            "aae_run_id": _current_run_id(aae_payload, aae_record, release),
            "oa_run_id": _current_run_id(oa_payload, oa_record, release),
            "observer_snapshot_run_id": _current_run_id(observer_payload, observer_record, release),
        },
    }
