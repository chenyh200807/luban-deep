from __future__ import annotations

import time
from typing import Any

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


def _payload(record: dict[str, Any] | None) -> dict[str, Any]:
    payload = (record or {}).get("payload")
    return payload if isinstance(payload, dict) else {}


def _normalize_status(value: Any) -> str:
    normalized = str(value or "").strip().upper().replace("-", "_")
    if normalized == "CLEAR":
        return _PASS
    if normalized in {"BLOCKED", "ERROR"}:
        return _FAIL
    return normalized if normalized in _SUPPORTED_STATUSES else _WARN


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


def _release_has_signature(release: dict[str, Any]) -> bool:
    return any(str(release.get(key) or "").strip() for key in ("git_sha", "release_id"))


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def build_current_release_readiness_matrix_payload(
    *,
    store,
    release: dict[str, Any] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        records = store.list_runs("readiness_checks", limit=limit)
    except (FileNotFoundError, TypeError, ValueError):
        records = []

    anchor_release = dict(release or {})
    if not _release_has_signature(anchor_release):
        for record in records:
            candidate_release = _record_release(record, _payload(record))
            if _release_has_signature(candidate_release):
                anchor_release = candidate_release
                break

    latest_by_check: dict[str, dict[str, Any]] = {}
    for record in records:
        payload = _payload(record)
        check_id = str(payload.get("check_id") or record.get("check_id") or "").strip()
        if not check_id:
            continue
        actual_release = _record_release(record, payload)
        if _release_has_signature(anchor_release) and not _same_release(anchor_release, actual_release):
            continue
        if check_id not in latest_by_check:
            latest_by_check[check_id] = record

    rows: list[dict[str, Any]] = []
    for check_id in sorted(latest_by_check):
        record = latest_by_check[check_id]
        payload = _payload(record)
        blockers = payload.get("blockers") or []
        if not isinstance(blockers, list):
            blockers = [blockers]
        rows.append(
            {
                "check_id": check_id,
                "label": str(payload.get("label") or check_id),
                "status": _normalize_status(payload.get("status")),
                "required": bool(payload.get("required", True)),
                "summary": str(payload.get("summary") or ""),
                "evidence": [str(item) for item in payload.get("evidence") or []],
                "blockers": [str(item) for item in blockers if str(item).strip()],
                "run_id": str(payload.get("run_id") or record.get("run_id") or ""),
                "recorded_at": record.get("recorded_at"),
                "release": _record_release(record, payload),
                "source_kind": "readiness_checks",
            }
        )

    required_rows = [row for row in rows if row.get("required")]
    required_non_pass = [row for row in required_rows if row.get("status") != _PASS]
    any_fail = any(row.get("status") == _FAIL for row in rows)
    any_non_pass = any(row.get("status") != _PASS for row in rows)
    if required_non_pass or any_fail:
        final_status = _FAIL
    elif any_non_pass:
        final_status = _WARN
    elif rows:
        final_status = _PASS
    else:
        final_status = _WARN

    blockers = _unique_strings(
        [
            blocker
            for row in required_non_pass
            for blocker in row.get("blockers") or []
        ]
    )
    return {
        "run_id": f"readiness-matrix-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "view": "current_release_latest_matrix",
        "release": anchor_release,
        "final_status": final_status,
        "summary": {
            "check_count": len(rows),
            "required_count": len(required_rows),
            "required_non_pass_count": len(required_non_pass),
        },
        "rows": rows,
        "checks": {row["check_id"]: row for row in rows},
        "blockers": blockers,
    }
