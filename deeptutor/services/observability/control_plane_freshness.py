from __future__ import annotations

import time
from typing import Any

from deeptutor.services.observability.runtime_authority import release_identity_matches

FRESHNESS_SECONDS: dict[str, int | None] = {
    "daily_trends": 36 * 60 * 60,
    "oa_runs": 36 * 60 * 60,
    "om_runs": 36 * 60 * 60,
    "arr_runs": 36 * 60 * 60,
    "aae_composite_runs": 36 * 60 * 60,
    "observer_snapshots": 36 * 60 * 60,
    "change_impact_runs": 36 * 60 * 60,
    "plan_completion_audits": 36 * 60 * 60,
    "readiness_checks": 36 * 60 * 60,
    "benchmark_runs": 7 * 24 * 60 * 60,
    "release_gate_runs": 7 * 24 * 60 * 60,
    # Incident ledger is cumulative evidence, not a point-in-time readiness
    # check. It has no expiry, but its wrapper timestamp must still be present
    # and must not be in the future.
    "incident_ledger": None,
}


def payload_release(payload: dict[str, Any] | None) -> dict[str, Any]:
    release = (payload or {}).get("release")
    if isinstance(release, dict) and release:
        return release
    release_spine = (payload or {}).get("release_spine")
    return release_spine if isinstance(release_spine, dict) else {}


def record_is_fresh(
    record: dict[str, Any] | None,
    *,
    kind: str,
    now: float | None = None,
) -> bool:
    recorded_at = (record or {}).get("recorded_at")
    if not isinstance(recorded_at, (int, float)):
        return False
    current = float(time.time() if now is None else now)
    age_seconds = current - float(recorded_at)
    if kind not in FRESHNESS_SECONDS:
        return False
    max_age = FRESHNESS_SECONDS[kind]
    return age_seconds >= 0 and (max_age is None or age_seconds <= max_age)


def select_fresh_payload_for_release(
    *,
    store: Any,
    kind: str,
    release: dict[str, Any],
    limit: int = 100,
    now: float | None = None,
) -> dict[str, Any] | None:
    try:
        records = store.list_runs(kind, limit=limit)
    except (FileNotFoundError, TypeError, ValueError):
        records = []
    try:
        latest = store.latest_run(kind, fallback=False)
    except (FileNotFoundError, TypeError, ValueError):
        latest = None
    if isinstance(latest, dict) and not any(
        (record or {}).get("run_id") == latest.get("run_id") for record in records
    ):
        records = [latest, *records]
    for record in records:
        payload = (record or {}).get("payload")
        if (
            isinstance(payload, dict)
            and record_is_fresh(record, kind=kind, now=now)
            and release_identity_matches(release, payload_release(payload))
        ):
            return payload
    return None
