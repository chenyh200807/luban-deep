#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def _load_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload.get("metadata"), dict):
            payload = payload["metadata"]
        records.append(payload)
    return records


def _decision_confidence(record: dict[str, Any]) -> float | None:
    decision = record.get("turn_semantic_decision")
    if isinstance(decision, dict):
        try:
            return float(decision.get("confidence"))
        except (TypeError, ValueError):
            pass
    try:
        return float(record.get("route_confidence"))
    except (TypeError, ValueError):
        return None


def _latency_ms(record: dict[str, Any]) -> float | None:
    for key in ("latency_ms", "duration_ms"):
        try:
            value = float(record.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((q / 100.0) * len(ordered)) - 1))
    return ordered[index]


def _confidence_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 0.4:
        return "<0.4"
    if value < 0.7:
        return "0.4-0.7"
    return ">=0.7"


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    shadow_records = [record for record in records if str(record.get("semantic_router_mode") or "") == "shadow"]
    disagreement_count = 0
    downgraded_to_chat = 0
    confidence_buckets = Counter()
    latencies: list[float] = []

    for record in shadow_records:
        selected = str(record.get("semantic_router_selected_capability") or "")
        shadow_route = str(record.get("semantic_router_shadow_route") or "")
        if selected and shadow_route and selected != shadow_route:
            disagreement_count += 1
        if selected == "chat" and shadow_route == "deep_question":
            downgraded_to_chat += 1
        confidence_buckets[_confidence_bucket(_decision_confidence(record))] += 1
        latency = _latency_ms(record)
        if latency is not None:
            latencies.append(latency)

    mode_counter = Counter(str(record.get("semantic_router_mode") or "unknown") for record in records)
    scope_counter = Counter(str(record.get("semantic_router_scope") or "unspecified") for record in records)
    return {
        "total_records": len(records),
        "by_mode": dict(sorted(mode_counter.items())),
        "by_scope": dict(sorted(scope_counter.items())),
        "shadow_total": len(shadow_records),
        "shadow_disagreement_count": disagreement_count,
        "shadow_disagreement_rate": (
            round(disagreement_count / len(shadow_records), 4) if shadow_records else 0.0
        ),
        "deep_question_to_chat_disagreements": downgraded_to_chat,
        "confidence_buckets": dict(sorted(confidence_buckets.items())),
        "p95_latency_ms": _percentile(latencies, 95),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a semantic-router rollout report from JSONL trace metadata."
    )
    parser.add_argument("input", help="Path to JSONL trace export.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    report = build_report(_load_records(Path(args.input).resolve()))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
