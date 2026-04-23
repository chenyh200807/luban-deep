from __future__ import annotations

from typing import Any

_CONFIRMED_SIGNALS = {"om_not_ready", "arr_regressions", "turn_error_ratio_high"}
_REGRESSION_SIGNALS = {"om_not_ready", "arr_regressions", "turn_error_ratio_high", "aae_continuity_low"}


def _source_run_ids(
    *,
    observer_payload: dict[str, Any] | None,
    change_impact_payload: dict[str, Any] | None,
    om_payload: dict[str, Any] | None,
    arr_payload: dict[str, Any] | None,
    aae_payload: dict[str, Any] | None,
) -> dict[str, str | None]:
    return {
        "observer_snapshot": (observer_payload or {}).get("run_id"),
        "change_impact": (change_impact_payload or {}).get("run_id"),
        "om": (om_payload or {}).get("run_id"),
        "arr": (arr_payload or {}).get("run_id"),
        "aae": (aae_payload or {}).get("run_id"),
    }


def _changed_domain_names(change_impact_payload: dict[str, Any] | None) -> list[str]:
    domains: list[str] = []
    for item in (change_impact_payload or {}).get("changed_domains") or []:
        if isinstance(item, dict):
            domain = str(item.get("domain") or "").strip()
            if domain:
                domains.append(domain)
    return domains


def _confidence_tier(*, signal_type: str, risk_level: str, risk_score: float) -> str:
    if signal_type in _CONFIRMED_SIGNALS and (risk_level == "high" or risk_score >= 0.75):
        return "confirmed"
    if signal_type in _REGRESSION_SIGNALS and (risk_level in {"high", "medium"} or risk_score >= 0.35):
        return "likely"
    if signal_type in {"observer_blind_spots", "none", ""}:
        return "pending"
    return "possible"


def _verdict(signal_type: str) -> str:
    if signal_type in _REGRESSION_SIGNALS:
        return "regression"
    if signal_type == "observer_blind_spots":
        return "blind_spot"
    return "pending"


def _repair_playbook(change_impact_payload: dict[str, Any] | None, signal_type: str) -> dict[str, Any]:
    commands = [
        str(item).strip()
        for item in (change_impact_payload or {}).get("next_commands") or []
        if str(item).strip()
    ]
    if not commands:
        commands = [
            "python3.11 scripts/run_observer_snapshot.py",
            "python3.11 scripts/run_oa.py --mode pre-release",
        ]
    return {
        "type": "first_failing_signal_replay",
        "steps": [
            "先固定 ChangeImpactRun 的 changed_domains，不扩大调查面。",
            f"按 first_failing_signal={signal_type or 'unknown'} 回放对应 gate。",
            "若回放不能复现，再升级为观测盲区而不是直接补业务逻辑。",
        ],
        "validation_cmds": commands,
    }


def build_causal_candidates(
    *,
    observer_payload: dict[str, Any] | None = None,
    change_impact_payload: dict[str, Any] | None = None,
    om_payload: dict[str, Any] | None = None,
    arr_payload: dict[str, Any] | None = None,
    aae_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic causal candidates from canonical observability runs.

    This is intentionally not an LLM judge and not a second change-impact model.
    It only ranks the already canonical first failing signal against source run ids.
    """

    if not change_impact_payload:
        return []

    first_signal = (change_impact_payload or {}).get("first_failing_signal") or {}
    signal_type = str(first_signal.get("type") or "").strip() or "none"
    risk_level = str(change_impact_payload.get("risk_level") or "unknown").strip()
    risk_score = float(change_impact_payload.get("risk_score") or 0.0)
    changed_domains = _changed_domain_names(change_impact_payload)
    source_run_ids = _source_run_ids(
        observer_payload=observer_payload,
        change_impact_payload=change_impact_payload,
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
    )
    data_sources = (observer_payload or {}).get("data_sources") or {}

    candidate = {
        "schema_version": "causal_oa_v1",
        "id": f"causal-{signal_type}-{(change_impact_payload or {}).get('run_id') or 'unknown'}",
        "verdict": _verdict(signal_type),
        "confidence_tier": _confidence_tier(
            signal_type=signal_type,
            risk_level=risk_level,
            risk_score=risk_score,
        ),
        "score": round(risk_score, 2),
        "changed_domains": changed_domains,
        "first_failing_signal": first_signal,
        "evidence_chain": {
            "change_impact_run_id": (change_impact_payload or {}).get("run_id"),
            "source_run_ids": source_run_ids,
            "score_components": (change_impact_payload or {}).get("score_components") or [],
            "observer_data_sources": {
                key: {
                    "freshness": value.get("freshness"),
                    "sample_count": value.get("sample_count"),
                    "has_data": value.get("has_data"),
                }
                for key, value in data_sources.items()
                if isinstance(value, dict)
            },
        },
        "repair_playbook": _repair_playbook(change_impact_payload, signal_type),
        "counterfactual": (
            "若相同 changed_domains 下 first_failing_signal 消失且 required_gates 通过，"
            "则该候选应降级为非因果或观测噪声。"
        ),
    }
    return [candidate]
