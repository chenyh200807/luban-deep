"""Harness hit-rate ledger (9+ roadmap H4 / C3 — the real world-class judge).

A world-class harness is proven by *what it actually catches*, not by a
self-graded capability rubric. This ledger is the canonical place that answer
lives: each entry records whether a harness gate caught a regression, of what
kind, and on which gate — so "is the net actually working?" is a number, not an
opinion.

Two honest categories:
- ``injected``  — a deliberately introduced regression caught in a teeth-proof
  test/demo. Proves *capability* (the gate has teeth). NOT evidence of a real
  incident catch.
- ``real``      — an unintended regression in a real change/incident that the
  gate caught (pre-merge) or missed. This is the metric that actually matters
  for 9+; it accrues over time as the harness is used.

The ledger is append-only and tracked in git (``eval/harness_hit_ledger.json``)
so the catch-rate accumulates across the team.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LEDGER_PATH = PROJECT_ROOT / "eval" / "harness_hit_ledger.json"

_KINDS = {"injected", "real"}


@dataclass(frozen=True)
class HarnessHit:
    """One harness gate outcome against a regression."""

    gate: str          # e.g. "harness_authority_guard"
    regression: str    # short description of the regression
    caught: bool       # did the gate catch it?
    kind: str          # "injected" (capability proof) | "real" (actual incident)
    date: str          # ISO date
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"kind must be one of {_KINDS}, got {self.kind!r}")


def load_ledger(path: Path | None = None) -> list[HarnessHit]:
    p = path or DEFAULT_LEDGER_PATH
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [HarnessHit(**entry) for entry in raw]


def save_ledger(hits: list[HarnessHit], path: Path | None = None) -> None:
    p = path or DEFAULT_LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(hit) for hit in hits]
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_hit(hit: HarnessHit, path: Path | None = None) -> list[HarnessHit]:
    hits = load_ledger(path)
    hits.append(hit)
    save_ledger(hits, path)
    return hits


def catch_rate_summary(hits: list[HarnessHit]) -> dict[str, Any]:
    """Compute the catch-rate metric. ``real`` is the figure that matters for 9+;
    ``injected`` is capability evidence only."""
    real = [h for h in hits if h.kind == "real"]
    injected = [h for h in hits if h.kind == "injected"]
    real_caught = sum(1 for h in real if h.caught)
    injected_caught = sum(1 for h in injected if h.caught)
    by_gate: dict[str, dict[str, int]] = {}
    for h in hits:
        slot = by_gate.setdefault(h.gate, {"caught": 0, "total": 0})
        slot["total"] += 1
        slot["caught"] += 1 if h.caught else 0

    def _rate(caught: int, total: int) -> float | None:
        return round(caught / total, 4) if total else None

    return {
        "real_total": len(real),
        "real_caught": real_caught,
        "real_catch_rate": _rate(real_caught, len(real)),
        "injected_total": len(injected),
        "injected_caught": injected_caught,
        "injected_catch_rate": _rate(injected_caught, len(injected)),
        "by_gate": by_gate,
    }
