"""Daily trend view derived from canonical benchmark artifacts."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from deeptutor.services.benchmark.runner import DEFAULT_OUTPUT_DIR


def _pass_rate(items: list[dict[str, Any]]) -> float | None:
    executed = [item for item in items if item.get("status") != "SKIP"]
    if not executed:
        return None
    passed = len([item for item in executed if item.get("status") == "PASS"])
    return round(passed / len(executed), 4)


def _contract_pass_rate(payload: dict[str, Any], contract_domain: str) -> float | None:
    return _pass_rate(
        [
            item
            for item in payload.get("case_results") or []
            if item.get("contract_domain") == contract_domain
        ]
    )


def _surface_delivery_coverage(payload: dict[str, Any]) -> float | None:
    surface_cases = [
        item
        for item in payload.get("case_results") or []
        if item.get("contract_domain") in {"surface_contract", "production_replay_contract"}
    ]
    if not surface_cases:
        return None
    covered = len([item for item in surface_cases if item.get("status") != "SKIP"])
    return round(covered / len(surface_cases), 4)


def _trend_point(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = payload.get("run_manifest") or {}
    summary = payload.get("summary") or {}
    baseline_diff = payload.get("baseline_diff") or {}
    return {
        "run_id": manifest.get("run_id") or payload.get("run_id"),
        "generated_at": manifest.get("generated_at") or payload.get("generated_at"),
        "release_id": (payload.get("release_spine") or payload.get("release") or {}).get("release_id"),
        "pass_rate": summary.get("pass_rate"),
        "new_regression_count": len(baseline_diff.get("regressions") or [])
        + len(baseline_diff.get("new_failures") or []),
        "blind_spot_count": len(payload.get("blind_spots") or []),
    }


def build_daily_trend(
    *,
    current_payload: dict[str, Any],
    history_payloads: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = current_payload.get("run_manifest") or {}
    release_spine = current_payload.get("release_spine") or {}
    baseline_diff = current_payload.get("baseline_diff") or {}
    failure_taxonomy = current_payload.get("failure_taxonomy") or []
    failure_counter = Counter(
        item.get("failure_type") for item in current_payload.get("case_results") or [] if item.get("failure_type")
    )
    history_points = [_trend_point(payload) for payload in (history_payloads or [])]

    metrics = {
        "pass_rate": (current_payload.get("summary") or {}).get("pass_rate"),
        "new_regression_count": len(baseline_diff.get("regressions") or [])
        + len(baseline_diff.get("new_failures") or []),
        "continuity_floor": _contract_pass_rate(current_payload, "continuity_contract"),
        "groundedness_floor": _contract_pass_rate(current_payload, "grounding_contract"),
        "surface_delivery_coverage": _surface_delivery_coverage(current_payload),
        "blind_spot_count": len(current_payload.get("blind_spots") or []),
    }

    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    source_run_id = str(manifest.get("run_id") or current_payload.get("run_id") or "")
    return {
        "run_manifest": {
            "run_id": f"daily-trend-{int(time.time())}",
            "generated_at": generated_at,
            "source_benchmark_run_id": source_run_id,
            "source_requested_suites": manifest.get("requested_suites") or [],
            "dataset_id": manifest.get("dataset_id"),
            "dataset_version": manifest.get("dataset_version"),
        },
        "release_spine": release_spine,
        "metrics": metrics,
        "failure_taxonomy": failure_taxonomy,
        "failure_bucket_delta": [
            {"failure_type": failure_type, "count": int(count)}
            for failure_type, count in sorted(failure_counter.items(), key=lambda item: item[0])
        ],
        "suite_summaries": current_payload.get("suite_summaries") or [],
        "baseline_diff": current_payload.get("baseline_diff"),
        "blind_spots": current_payload.get("blind_spots") or [],
        "trend_points": [*history_points, _trend_point(current_payload)],
    }


def render_daily_trend_markdown(payload: dict[str, Any]) -> str:
    manifest = payload.get("run_manifest") or {}
    metrics = payload.get("metrics") or {}
    lines = [
        "# Benchmark Daily Trend",
        "",
        f"- run_id: `{manifest.get('run_id')}`",
        f"- source_benchmark_run_id: `{manifest.get('source_benchmark_run_id')}`",
        f"- generated_at: {manifest.get('generated_at')}",
        "",
        "## Metrics",
        "",
    ]
    for key in (
        "pass_rate",
        "new_regression_count",
        "continuity_floor",
        "groundedness_floor",
        "surface_delivery_coverage",
        "blind_spot_count",
    ):
        lines.append(f"- {key}: {metrics.get(key)}")
    lines.extend(["", "## Blind Spots", ""])
    blind_spots = payload.get("blind_spots") or []
    if not blind_spots:
        lines.append("- none")
    else:
        for item in blind_spots:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines)


def write_daily_trend_artifacts(
    payload: dict[str, Any],
    *,
    output_dir: Path | None = None,
) -> dict[str, str]:
    target_dir = (output_dir or (DEFAULT_OUTPUT_DIR / "daily_trend")).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = target_dir / f"benchmark_daily_trend_{stamp}.json"
    md_path = target_dir / f"benchmark_daily_trend_{stamp}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_daily_trend_markdown(payload), encoding="utf-8")
    return {"json_path": str(json_path), "md_path": str(md_path)}
