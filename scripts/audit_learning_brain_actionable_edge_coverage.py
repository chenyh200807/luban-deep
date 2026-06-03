from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ACTIONABLE_EDGE_TYPES = frozenset({
    "error_points_to_training",
    "training_uses_question",
    "training_improved_error",
})


def collect_actionable_edge_coverage(root: Path) -> dict[str, Any]:
    user_files = sorted(Path(root).glob("*/MEMORY_EVENTS.jsonl"))
    total = Counter()
    edge_counts: Counter[str] = Counter()
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    by_user: dict[str, Counter[str]] = {}

    for path in user_files:
        user_id = path.parent.name
        user_stats: Counter[str] = Counter()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                user_stats["invalid_json_lines"] += 1
                continue
            if row.get("memory_kind") != "learning_evidence":
                continue
            payload = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
            edges = list(payload.get("typed_edges") or [])
            source = str(row.get("source_feature") or payload.get("source_feature") or "unknown").strip() or "unknown"
            user_stats["learning_evidence_events"] += 1
            by_source[source]["learning_evidence_events"] += 1
            if edges:
                user_stats["events_with_typed_edges"] += 1
                by_source[source]["events_with_typed_edges"] += 1
            has_actionable = False
            for edge in edges:
                edge_type = str((edge or {}).get("edge_type") or "").strip()
                if not edge_type:
                    continue
                edge_counts[edge_type] += 1
                if edge_type in ACTIONABLE_EDGE_TYPES:
                    has_actionable = True
            if has_actionable:
                user_stats["events_with_actionable_edges"] += 1
                by_source[source]["events_with_actionable_edges"] += 1
        if user_stats:
            by_user[user_id] = user_stats
            total.update(user_stats)

    total_report = _with_ratio(total)
    return {
        "actionable_edge_types": sorted(ACTIONABLE_EDGE_TYPES),
        "files": len(user_files),
        "users_with_learning_evidence": len(by_user),
        "total": total_report,
        "edge_counts": dict(sorted(edge_counts.items())),
        "by_source": {key: _with_ratio(value) for key, value in sorted(by_source.items())},
        "by_user": {key: _with_ratio(value) for key, value in sorted(by_user.items())},
    }


def _with_ratio(stats: Counter[str]) -> dict[str, Any]:
    events = int(stats.get("learning_evidence_events") or 0)
    actionable = int(stats.get("events_with_actionable_edges") or 0)
    return {
        **dict(stats),
        "actionable_edge_coverage": round(actionable / events, 4) if events else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Learning Brain actionable typed-edge coverage.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data/user/learner_state"),
        help="Directory containing per-user MEMORY_EVENTS.jsonl files.",
    )
    parser.add_argument(
        "--min-actionable-coverage",
        type=float,
        default=None,
        help="Fail when total actionable edge coverage is below this ratio.",
    )
    args = parser.parse_args()

    report = collect_actionable_edge_coverage(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.min_actionable_coverage is not None:
        coverage = float(report["total"]["actionable_edge_coverage"])
        if coverage < args.min_actionable_coverage:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
