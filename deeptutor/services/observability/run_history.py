from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore

RUN_HISTORY_KINDS: tuple[str, ...] = (
    "change_impact_runs",
    "oa_runs",
    "release_gate_runs",
    "observer_snapshots",
    "om_runs",
    "arr_runs",
    "aae_composite_runs",
    "daily_trends",
    "incident_ledger",
)


def _release(payload: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    release = payload.get("release") or payload.get("release_spine") or {}
    if not isinstance(release, dict):
        release = {}
    return {
        "release_id": release.get("release_id") or record.get("release_id") or "",
        "git_sha": release.get("git_sha") or "",
        "deployment_environment": release.get("deployment_environment") or "",
    }


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def _matches_commit(record: dict[str, Any], commit_sha: str | None) -> bool:
    normalized = str(commit_sha or "").strip()
    if not normalized:
        return True
    payload = _payload(record)
    git_sha = str(_release(payload, record).get("git_sha") or "").strip()
    return bool(git_sha and git_sha.startswith(normalized))


def _record_summary(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind == "change_impact_runs":
        return {
            "risk_level": payload.get("risk_level"),
            "risk_score": payload.get("risk_score"),
            "changed_domains": [
                item.get("domain")
                for item in payload.get("changed_domains") or []
                if isinstance(item, dict)
            ],
        }
    if kind == "oa_runs":
        return {
            "root_cause_count": len(payload.get("root_causes") or []),
            "blind_spot_count": len(payload.get("blind_spots") or []),
            "causal_candidate_count": len(payload.get("causal_candidates") or []),
        }
    if kind == "release_gate_runs":
        return {
            "final_status": payload.get("final_status"),
            "recommendation": payload.get("recommendation"),
        }
    if kind == "observer_snapshots":
        return {
            "coverage_ratio": (payload.get("data_coverage") or {}).get("coverage_ratio"),
            "blind_spot_count": len(payload.get("blind_spots") or []),
        }
    return {"run_id": payload.get("run_id")}


def _normalize_record(kind: str, record: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(record)
    release = _release(payload, record)
    return {
        "kind": kind,
        "run_id": record.get("run_id") or payload.get("run_id") or "",
        "release_id": release.get("release_id") or "",
        "git_sha": release.get("git_sha") or "",
        "recorded_at": record.get("recorded_at"),
        "summary": _record_summary(kind, payload),
    }


def _latest_by_kind(records: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for record in records:
        if record.get("kind") == kind:
            return record
    return None


def build_observability_run_history(
    *,
    store: ObservabilityControlPlaneStore,
    limit: int = 20,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit or 20), 100))
    records: list[dict[str, Any]] = []
    for kind in RUN_HISTORY_KINDS:
        for record in store.list_runs(kind, limit=bounded_limit):
            if _matches_commit(record, commit_sha):
                records.append(_normalize_record(kind, record))

    records.sort(
        key=lambda item: (
            int(item.get("recorded_at") or 0),
            str(item.get("kind") or ""),
            str(item.get("run_id") or ""),
        ),
        reverse=True,
    )
    records = records[:bounded_limit]

    by_kind = Counter(str(item.get("kind") or "") for item in records)
    latest_change_impact = _latest_by_kind(records, "change_impact_runs") or {}
    latest_oa = _latest_by_kind(records, "oa_runs") or {}
    latest_release_gate = _latest_by_kind(records, "release_gate_runs") or {}
    latest_oa_summary = latest_oa.get("summary") or {}

    return {
        "summary": {
            "total": len(records),
            "by_kind": dict(sorted(by_kind.items(), key=lambda item: item[0])),
            "latest_risk_level": (latest_change_impact.get("summary") or {}).get("risk_level"),
            "latest_release_gate_status": (latest_release_gate.get("summary") or {}).get("final_status"),
            "latest_root_cause_count": latest_oa_summary.get("root_cause_count"),
            "blind_spot_count": latest_oa_summary.get("blind_spot_count"),
        },
        "records": records,
    }


def build_observability_run_history_from_dir(
    *,
    store_dir: str | Path,
    limit: int = 20,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    store = ObservabilityControlPlaneStore(base_dir=Path(store_dir).expanduser().resolve())
    return build_observability_run_history(store=store, limit=limit, commit_sha=commit_sha)
