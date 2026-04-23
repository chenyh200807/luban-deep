from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHANGE_IMPACT_BASE_REF = "HEAD~1"


_DOMAIN_RULES: tuple[dict[str, Any], ...] = (
    {
        "domain": "turn",
        "risk": "high",
        "prefixes": (
            "contracts/turn.md",
            "deeptutor/api/routers/unified_ws.py",
            "deeptutor/api/routers/mobile.py",
            "deeptutor/services/session/",
            "deeptutor/contracts/unified_turn.py",
            "web/lib/unified-ws.ts",
            "web/context/UnifiedChatContext.tsx",
        ),
        "gates": ("contract_guard", "unified_ws_smoke", "observer_snapshot"),
    },
    {
        "domain": "rag",
        "risk": "high",
        "prefixes": (
            "contracts/rag.md",
            "deeptutor/services/rag/",
            "deeptutor/tools/rag_tool.py",
            "deeptutor/agents/chat/agentic_pipeline.py",
        ),
        "gates": ("contract_guard", "arr_lite", "observer_snapshot"),
    },
    {
        "domain": "capability",
        "risk": "high",
        "prefixes": (
            "contracts/capability.md",
            "deeptutor/runtime/orchestrator.py",
            "deeptutor/runtime/registry/capability_registry.py",
            "deeptutor/capabilities/",
        ),
        "gates": ("contract_guard", "unified_ws_smoke", "arr_lite", "observer_snapshot"),
    },
    {
        "domain": "surface",
        "risk": "medium",
        "prefixes": ("web/", "wx_miniprogram/", "yousenwebview/"),
        "gates": ("surface_smoke", "aae_snapshot", "observer_snapshot"),
    },
    {
        "domain": "bi",
        "risk": "medium",
        "prefixes": (
            "deeptutor/services/bi_service.py",
            "deeptutor/services/bi_metrics.py",
            "deeptutor/services/member_console/",
            "web/lib/bi-api.ts",
            "web/app/(workspace)/bi/",
            "tests/services/test_bi_",
            "tests/services/member_console/",
            "tests/web/test_bi_member_admin_surface.py",
            "docs/zh/bi/",
        ),
        "gates": ("bi_service_tests", "bi_web_tests", "observer_snapshot"),
    },
    {
        "domain": "benchmark",
        "risk": "medium",
        "prefixes": (
            "deeptutor/services/benchmark/",
            "tests/fixtures/benchmark",
            "scripts/run_benchmark.py",
            "scripts/run_daily_benchmark.py",
            "scripts/run_incident_replay.py",
        ),
        "gates": ("arr_lite", "daily_benchmark", "observer_snapshot"),
    },
    {
        "domain": "observability",
        "risk": "medium",
        "prefixes": (
            "deeptutor/services/observability/",
            "scripts/run_om_snapshot.py",
            "scripts/run_arr_lite.py",
            "scripts/run_aae_snapshot.py",
            "scripts/run_observer_snapshot.py",
            "scripts/run_oa.py",
            "scripts/run_release_gate.py",
            "scripts/run_prerelease_observability.py",
            "docs/zh/guide/observability-control-plane.md",
            "docs/zh/guide/benchmark-spine.md",
        ),
        "gates": ("observer_snapshot", "oa", "release_gate"),
    },
    {
        "domain": "learner_state",
        "risk": "medium",
        "prefixes": ("contracts/learner-state.md", "deeptutor/services/memory/", "deeptutor/services/tutor_state/"),
        "gates": ("contract_guard", "unified_ws_smoke", "observer_snapshot"),
    },
    {
        "domain": "config_runtime",
        "risk": "medium",
        "prefixes": ("contracts/config-runtime.md", "deeptutor/services/config/", "deeptutor/services/llm/factory.py"),
        "gates": ("contract_guard", "unified_ws_smoke", "observer_snapshot"),
    },
)

_GATE_COMMANDS: dict[str, str] = {
    "contract_guard": "python3.11 scripts/check_contract_guard.py",
    "unified_ws_smoke": "python3.11 scripts/run_unified_ws_smoke.py --api-base-url http://127.0.0.1:8001 --message '请只回复ok。'",
    "arr_lite": "python3.11 scripts/run_arr_lite.py --mode lite",
    "aae_snapshot": "python3.11 scripts/run_aae_snapshot.py",
    "observer_snapshot": "python3.11 scripts/run_observer_snapshot.py",
    "oa": "python3.11 scripts/run_oa.py --mode pre-release",
    "release_gate": "python3.11 scripts/run_release_gate.py",
    "surface_smoke": "python3.11 scripts/run_prerelease_observability.py --api-base-url http://127.0.0.1:8001 --surface-smoke web",
    "daily_benchmark": "python3.11 scripts/run_daily_benchmark.py",
    "bi_service_tests": "pytest tests/services/test_bi_metrics.py tests/services/test_bi_service_limits.py tests/services/member_console/test_service.py",
    "bi_web_tests": "pytest tests/web/test_bi_member_admin_surface.py",
}


def parse_git_status_changed_files(status_output: str) -> list[str]:
    files: set[str] = set()
    for raw_line in status_output.splitlines():
        if not raw_line:
            continue
        path = raw_line[3:].strip() if len(raw_line) >= 4 else raw_line[2:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            files.add(path)
    return sorted(files)


def collect_git_changed_files(
    *,
    base_ref: str = DEFAULT_CHANGE_IMPACT_BASE_REF,
    include_worktree: bool = True,
) -> list[str]:
    """Collect git changed files; callers can pass explicit files to scope a run."""
    diff = subprocess.run(
        ["git", "diff", "--name-only", base_ref],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    files: set[str] = set()
    if diff.returncode == 0:
        files.update(line.strip() for line in diff.stdout.splitlines() if line.strip())
    if include_worktree:
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if status.returncode == 0:
            files.update(parse_git_status_changed_files(status.stdout))
    return sorted(files)


def _release_from_sources(*sources: dict[str, Any] | None) -> dict[str, Any]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        release = source.get("release")
        if isinstance(release, dict) and release:
            return dict(release)
    return get_release_lineage_snapshot()


def _normalize_changed_files(changed_files: list[str] | tuple[str, ...] | None) -> list[str]:
    files = []
    for item in changed_files or []:
        path = str(item or "").strip().lstrip("./")
        if path:
            files.append(path)
    return sorted(dict.fromkeys(files))


def _domain_matches(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _build_changed_domains(changed_files: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    for path in changed_files:
        matched = False
        for rule in _DOMAIN_RULES:
            if _domain_matches(path, tuple(rule["prefixes"])):
                domain = str(rule["domain"])
                entry = grouped.setdefault(
                    domain,
                    {
                        "domain": domain,
                        "risk": rule["risk"],
                        "files": [],
                        "required_gates": [],
                    },
                )
                entry["files"].append(path)
                entry["required_gates"].extend(rule["gates"])
                matched = True
        if not matched:
            unmatched.append(path)
    if unmatched:
        grouped["other"] = {
            "domain": "other",
            "risk": "low",
            "files": unmatched,
            "required_gates": ("observer_snapshot",),
        }

    domains: list[dict[str, Any]] = []
    for entry in grouped.values():
        gates = sorted(dict.fromkeys(entry["required_gates"]))
        domains.append({**entry, "files": sorted(entry["files"]), "required_gates": gates})
    return sorted(domains, key=lambda item: item["domain"])


def _required_gates(changed_domains: list[dict[str, Any]], *, has_changes: bool) -> list[dict[str, str]]:
    gates: list[str] = []
    for domain in changed_domains:
        gates.extend(domain.get("required_gates") or [])
    gates.extend(["observer_snapshot", "oa", "release_gate"])
    if not has_changes:
        gates = ["observer_snapshot", "oa"]
    return [
        {"gate": gate, "command": _GATE_COMMANDS[gate]}
        for gate in sorted(dict.fromkeys(gates))
        if gate in _GATE_COMMANDS
    ]


def _first_failing_signal(
    *,
    om_payload: dict[str, Any] | None,
    arr_payload: dict[str, Any] | None,
    aae_payload: dict[str, Any] | None,
    observer_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    health = (om_payload or {}).get("health_summary") or {}
    if health.get("ready") is False:
        return {"type": "om_not_ready", "summary": "runtime readiness is false"}

    arr_diff = (arr_payload or {}).get("baseline_diff") or {}
    regressions = arr_diff.get("regressions") or []
    new_failures = arr_diff.get("new_failures") or []
    if regressions or new_failures:
        return {
            "type": "arr_regressions",
            "summary": f"ARR reported {len(regressions)} regressions and {len(new_failures)} new failures",
        }

    turn_events = (observer_payload or {}).get("turn_events") or {}
    error_ratio = turn_events.get("error_ratio")
    if isinstance(error_ratio, (int, float)) and float(error_ratio) >= 0.05:
        return {"type": "turn_error_ratio_high", "summary": f"turn error ratio is {error_ratio}"}

    scorecard = (aae_payload or {}).get("scorecard") or {}
    continuity = (scorecard.get("continuity_score") or {}).get("value")
    if isinstance(continuity, (int, float)) and float(continuity) < 0.8:
        return {"type": "aae_continuity_low", "summary": f"continuity score is {continuity}"}

    blind_spots = (observer_payload or {}).get("blind_spots") or []
    if blind_spots:
        return {"type": "observer_blind_spots", "summary": f"observer has {len(blind_spots)} blind spots"}

    return {"type": "none", "summary": "no failing signal detected"}


def _risk_score_components(
    changed_domains: list[dict[str, Any]],
    first_signal: dict[str, Any],
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    if any(item.get("risk") == "high" for item in changed_domains):
        components.append({"source": "domain", "name": "high_risk_domain", "weight": 0.45})
    elif any(item.get("risk") == "medium" for item in changed_domains):
        components.append({"source": "domain", "name": "medium_risk_domain", "weight": 0.25})
    elif changed_domains:
        components.append({"source": "domain", "name": "low_risk_domain", "weight": 0.1})

    signal_type = first_signal.get("type")
    if signal_type == "om_not_ready":
        components.append({"source": "signal", "name": "om_not_ready", "weight": 0.45})
    elif signal_type == "arr_regressions":
        components.append({"source": "signal", "name": "arr_regressions", "weight": 0.4})
    elif signal_type == "turn_error_ratio_high":
        components.append({"source": "signal", "name": "turn_error_ratio_high", "weight": 0.3})
    elif signal_type == "aae_continuity_low":
        components.append({"source": "signal", "name": "aae_continuity_low", "weight": 0.2})
    elif signal_type == "observer_blind_spots":
        components.append({"source": "signal", "name": "observer_blind_spots", "weight": 0.1})
    return components


def _risk_score(components: list[dict[str, Any]]) -> float:
    score = sum(float(item.get("weight") or 0.0) for item in components)
    return round(min(score, 1.0), 2)


def _risk_level(*, score: float, has_changes: bool) -> str:
    if not has_changes:
        return "unknown"
    if score >= 0.75:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def build_change_impact_run(
    *,
    changed_files: list[str] | tuple[str, ...] | None,
    observer_payload: dict[str, Any] | None = None,
    om_payload: dict[str, Any] | None = None,
    arr_payload: dict[str, Any] | None = None,
    aae_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = _normalize_changed_files(changed_files)
    release = _release_from_sources(observer_payload, arr_payload, om_payload, aae_payload)
    changed_domains = _build_changed_domains(files)
    first_signal = _first_failing_signal(
        om_payload=om_payload,
        arr_payload=arr_payload,
        aae_payload=aae_payload,
        observer_payload=observer_payload,
    )
    score_components = _risk_score_components(changed_domains, first_signal)
    score = _risk_score(score_components)
    level = _risk_level(score=score, has_changes=bool(files))
    required_gates = _required_gates(changed_domains, has_changes=bool(files))
    blind_spots = [
        dict(item)
        for item in (observer_payload or {}).get("blind_spots", [])
        if isinstance(item, dict)
    ]
    if not files:
        blind_spots.append({"type": "missing_changed_files", "severity": "high"})

    recommendation = "canary"
    if level == "high":
        recommendation = "hold"
    elif level == "medium":
        recommendation = "hold_with_conditions"
    elif level == "unknown":
        recommendation = "investigate"

    return {
        "run_id": f"change-impact-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": release,
        "changed_files": files,
        "changed_domains": changed_domains,
        "required_gates": required_gates,
        "risk_score": score,
        "score_components": score_components,
        "risk_level": level,
        "blocking_recommendation": recommendation,
        "first_failing_signal": first_signal,
        "blind_spots": blind_spots,
        "source_runs": {
            "observer_snapshot_run_id": (observer_payload or {}).get("run_id"),
            "om_run_id": (om_payload or {}).get("run_id"),
            "arr_run_id": (arr_payload or {}).get("run_id"),
            "aae_run_id": (aae_payload or {}).get("run_id"),
        },
        "next_commands": [item["command"] for item in required_gates],
    }


def render_change_impact_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Change Impact Run",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- release_id: `{(payload.get('release') or {}).get('release_id', 'unknown')}`",
        f"- risk: `{payload.get('risk_level')}` / `{payload.get('risk_score')}`",
        f"- recommendation: `{payload.get('blocking_recommendation')}`",
        f"- first_failing_signal: `{(payload.get('first_failing_signal') or {}).get('type')}`",
        "",
        "## Changed Domains",
        "",
    ]
    domains = payload.get("changed_domains") or []
    if not domains:
        lines.append("- none")
    else:
        for item in domains:
            lines.append(f"- `{item.get('domain')}` risk=`{item.get('risk')}` files=`{len(item.get('files') or [])}`")
    lines.extend(["", "## Required Gates", ""])
    for item in payload.get("required_gates") or []:
        lines.append(f"- `{item.get('gate')}`: `{item.get('command')}`")
    lines.extend(["", "## Blind Spots", ""])
    blind_spots = payload.get("blind_spots") or []
    if not blind_spots:
        lines.append("- none")
    else:
        for item in blind_spots:
            lines.append(f"- {item}")
    return "\n".join(lines)
