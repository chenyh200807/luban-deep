"""Incident replay view derived from canonical benchmark artifacts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from deeptutor.services.benchmark.runner import DEFAULT_OUTPUT_DIR


def build_incident_replay_report(
    *,
    benchmark_payload: dict[str, Any],
    incident_id: str,
) -> dict[str, Any]:
    manifest = benchmark_payload.get("run_manifest") or {}
    baseline_diff = benchmark_payload.get("baseline_diff") or {}
    blind_spots = benchmark_payload.get("blind_spots") or []
    failures = [
        item
        for item in benchmark_payload.get("case_results") or []
        if item.get("status") == "FAIL"
    ]
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    normalized_incident_id = str(incident_id or "").strip() or f"incident-{int(time.time())}"
    return {
        "run_manifest": {
            "run_id": f"incident-replay-{int(time.time())}",
            "generated_at": generated_at,
            "incident_id": normalized_incident_id,
            "source_benchmark_run_id": manifest.get("run_id"),
            "source_requested_suites": manifest.get("requested_suites") or [],
            "dataset_id": manifest.get("dataset_id"),
            "dataset_version": manifest.get("dataset_version"),
        },
        "release_spine": benchmark_payload.get("release_spine") or {},
        "classification": {
            "known_regression_count": len(baseline_diff.get("regressions") or []),
            "new_failure_count": len(baseline_diff.get("new_failures") or []),
            "current_failure_count": len(failures),
            "blind_spot_count": len(blind_spots),
        },
        "failure_taxonomy": benchmark_payload.get("failure_taxonomy") or [],
        "failures": failures,
        "baseline_diff": benchmark_payload.get("baseline_diff"),
        "blind_spots": blind_spots,
        "replay_candidates": [
            {
                "incident_id": normalized_incident_id,
                "case_id": item.get("case_id"),
                "suite": item.get("suite"),
                "reason": item.get("reason"),
                "recommended_tier": "incident_replay",
            }
            for item in blind_spots
        ],
    }


def render_incident_replay_markdown(payload: dict[str, Any]) -> str:
    manifest = payload.get("run_manifest") or {}
    classification = payload.get("classification") or {}
    lines = [
        "# Benchmark Incident Replay",
        "",
        f"- run_id: `{manifest.get('run_id')}`",
        f"- incident_id: `{manifest.get('incident_id')}`",
        f"- source_benchmark_run_id: `{manifest.get('source_benchmark_run_id')}`",
        "",
        "## Classification",
        "",
    ]
    for key in (
        "known_regression_count",
        "new_failure_count",
        "current_failure_count",
        "blind_spot_count",
    ):
        lines.append(f"- {key}: {classification.get(key)}")
    lines.extend(["", "## Replay Candidates", ""])
    candidates = payload.get("replay_candidates") or []
    if not candidates:
        lines.append("- none")
    else:
        for item in candidates:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)


def write_incident_replay_artifacts(
    payload: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> dict[str, str]:
    target_dir = (output_dir or (DEFAULT_OUTPUT_DIR / "incident")).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = target_dir / f"benchmark_incident_replay_{stamp}.json"
    md_path = target_dir / f"benchmark_incident_replay_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_incident_replay_markdown(payload), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}
