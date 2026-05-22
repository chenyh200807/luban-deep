#!/usr/bin/env python
"""Phase -1.D: synthesize_learning_truth performance baseline.

Generates synthetic LearnerStateEvent payloads, runs synthesis under several
window sizes, and writes a markdown report with p50 / p95 / p99 wall-clock
timings. Read-only — no Supabase writes, no network.

Budget (from the transformation plan):
- synthesize_learning_truth p95 ≤ 200ms on 2000 events.

Usage:
    python scripts/bench_learning_synthesis.py --events 2000 \\
        --out docs/qa/2026-05-22-learning-state-performance-baseline.md
"""
from __future__ import annotations

import argparse
import datetime as _dt
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.service import LearnerStateEvent


_TZ = _dt.timezone(_dt.timedelta(hours=8))

# Spread synthetic events across a few concepts and error codes so the
# clustering / weak-point logic exercises realistic branches.
_CONCEPTS = (
    "1A412010",
    "1A412020",
    "1A413030",
    "1A422000",
    "1A432000",
    "1A436000",
)
_ERROR_CODES = ("M01", "M06", "M07", "E02", "E04", "E09")


def _make_event(index: int, total: int) -> LearnerStateEvent:
    concept = _CONCEPTS[index % len(_CONCEPTS)]
    code = _ERROR_CODES[index % len(_ERROR_CODES)]
    # days_ago decreases as index increases so larger index = more recent.
    days_ago = total - index
    created_at = (_dt.datetime.now(_TZ) - _dt.timedelta(days=days_ago, seconds=index)).isoformat()
    return LearnerStateEvent(
        event_id=f"bench_evt_{index:06d}",
        user_id="bench_student",
        source_feature="construction_grading",
        source_id=f"turn:bench_{index}",
        source_bot_id="construction-exam",
        memory_kind="learning_evidence",
        dedupe_key=f"bench_evt_{index}",
        created_at=created_at,
        payload_json={
            "event_type": "learning_evidence",
            "question_id": f"bench_q_{index % 200:03d}",
            "question_stem": f"题目 {index} 的题干",
            "user_answer": "A",
            "correct_answer": "B",
            "score_awarded": 0 if index % 3 else 1,
            "max_score": 1,
            "error_events": [
                {"error_code": code, "concept_tag": concept, "diagnosis": "bench"}
            ],
            "next_training_signal": {"concept": concept, "focus": "bench", "mode": "practice"},
        },
    )


def _generate_events(count: int) -> list[LearnerStateEvent]:
    return [_make_event(i, total=count) for i in range(count)]


def _timed_run(events: list[LearnerStateEvent], event_limit: int | None) -> float:
    start = time.perf_counter()
    synthesize_learning_truth(events, event_limit=event_limit)
    return (time.perf_counter() - start) * 1000.0  # ms


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    # Linear interpolation, matches numpy default.
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    frac = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * frac


def benchmark(events: list[LearnerStateEvent], *, iterations: int) -> dict[str, dict[str, float]]:
    """Run synthesis several times under several windows; return stats."""
    scenarios: list[tuple[str, int | None]] = [
        ("full (no window)", None),
        ("window=500", 500),
        ("window=200", 200),
    ]
    results: dict[str, dict[str, float]] = {}
    for label, limit in scenarios:
        samples: list[float] = []
        for _ in range(iterations):
            samples.append(_timed_run(events, limit))
        results[label] = {
            "p50_ms": _percentile(samples, 50),
            "p95_ms": _percentile(samples, 95),
            "p99_ms": _percentile(samples, 99),
            "min_ms": min(samples),
            "max_ms": max(samples),
            "iterations": float(iterations),
        }
    return results


def render(events_count: int, iterations: int, results: dict[str, dict[str, float]]) -> str:
    today = _dt.date.today().isoformat()
    full_stats = results.get("full (no window)", {})
    full_p95 = full_stats.get("p95_ms", 0.0)
    gate_status = "PASS (≤ 200ms)" if full_p95 <= 200 else "FAIL (exceeds 200ms budget)"

    lines: list[str] = []
    lines.append("# Learning State Synthesis Performance Baseline")
    lines.append("")
    lines.append(f"Generated: {today}")
    lines.append(
        f"Workload: {events_count} synthetic LearnerStateEvents, "
        f"{iterations} iterations per scenario, single-threaded."
    )
    lines.append(
        "Method: ``time.perf_counter`` around ``synthesize_learning_truth``; "
        "all events held in memory; no Supabase or network I/O."
    )
    lines.append("")
    lines.append("## Budget gate")
    lines.append("")
    lines.append(
        f"- synthesize_learning_truth p95 (no window) = **{full_p95:.1f} ms** — {gate_status}"
    )
    lines.append("- Budget per plan §Phase -1.D: p95 ≤ 200ms on 2000 events.")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| scenario | p50 (ms) | p95 (ms) | p99 (ms) | min | max | iterations |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for label, stats in results.items():
        lines.append(
            f"| {label} | {stats['p50_ms']:.1f} | {stats['p95_ms']:.1f} | "
            f"{stats['p99_ms']:.1f} | {stats['min_ms']:.1f} | {stats['max_ms']:.1f} | "
            f"{int(stats['iterations'])} |"
        )
    lines.append("")
    lines.append("## Window flag behavior")
    lines.append("")
    lines.append(
        "When ``event_limit`` is set and exceeded, ``synthesize_learning_truth`` "
        "returns a projection with ``window_truncated=True``; ``synthesis_run.input_event_count`` "
        "reflects the windowed count. Read model consumers must honor this flag and "
        "show a 'covered N most-recent attempts' hint in the UI."
    )
    lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```bash")
    lines.append("python scripts/bench_learning_synthesis.py --events 2000 \\")
    lines.append("    --out docs/qa/$(date -u +%F)-learning-state-performance-baseline.md")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("Generated by `scripts/bench_learning_synthesis.py` (read-only).")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=2000, help="number of synthetic events")
    parser.add_argument(
        "--iterations",
        type=int,
        default=20,
        help="iterations per scenario for p95/p99 stability",
    )
    parser.add_argument(
        "--out",
        default=str(
            REPO_ROOT / "docs" / "qa" / f"{_dt.date.today().isoformat()}-learning-state-performance-baseline.md"
        ),
        help="markdown output path",
    )
    args = parser.parse_args()

    print(f"generating {args.events} synthetic events...", file=sys.stderr)
    events = _generate_events(args.events)

    print(f"running synthesis {args.iterations} iterations × 3 scenarios...", file=sys.stderr)
    results = benchmark(events, iterations=args.iterations)

    report = render(args.events, args.iterations, results)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
