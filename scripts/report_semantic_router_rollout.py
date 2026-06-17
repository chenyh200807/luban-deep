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


def _selected_chat_like_capability(value: Any) -> bool:
    selected = str(value or "").strip()
    return selected in {"chat", "tutorbot"}


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
        if _selected_chat_like_capability(selected) and shadow_route == "deep_question":
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


def _telemetry_of(record: dict[str, Any]) -> dict[str, Any] | None:
    tele = record.get("semantic_router_telemetry")
    if isinstance(tele, dict):
        return tele
    # Allow the tuple at top level too (flat export).
    if "drove_route" in record and "is_default_template" in record:
        return record
    return None


def build_telemetry_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Credible mis-route-rate dataset from the additive decision telemetry tuple.

    Closes the 3 baseline breakpoints: in-place ``captured_raw_input`` (no join),
    ``drove_route`` (decision actually drove the route), and ``is_default_template``
    (non-discriminative default/fallback/hold excluded). The *judgeable* set is the
    subset where ``drove_route`` is true AND it is not a default template — only
    that subset supports a credible absolute mis-route rate.
    """
    teles = [t for t in (_telemetry_of(r) for r in records) if t is not None]
    drove = [t for t in teles if bool(t.get("drove_route"))]
    default_template = [t for t in teles if bool(t.get("is_default_template"))]
    judgeable = [t for t in drove if not bool(t.get("is_default_template"))]

    by_na: Counter = Counter()
    for t in judgeable:
        decision = t.get("semantic_decision") if isinstance(t.get("semantic_decision"), dict) else {}
        by_na[str(decision.get("next_action") or "")] += 1

    return {
        "total": len(teles),
        "drove_route_count": len(drove),
        "default_template_count": len(default_template),
        "judgeable_count": len(judgeable),
        "non_discriminative_excluded": len(teles) - len(judgeable),
        "judgeable_by_next_action": dict(sorted(by_na.items())),
        "mode_distribution": dict(
            sorted(Counter(str(t.get("mode") or "") for t in teles).items())
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a semantic-router rollout report from JSONL trace metadata."
    )
    parser.add_argument("input", help="Path to JSONL trace export.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    parser.add_argument(
        "--telemetry",
        action="store_true",
        help="Use the additive decision-telemetry tuple report (credible mis-route dataset).",
    )
    args = parser.parse_args()

    records = _load_records(Path(args.input).resolve())
    report = build_telemetry_report(records) if args.telemetry else build_report(records)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
