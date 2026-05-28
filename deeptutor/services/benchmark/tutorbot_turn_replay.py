"""TutorBot turn-outcome replay — walking skeleton (9+ roadmap §0.11 phase 1).

The full agent-loop event-sourcing replay (capture every iteration's thought
+ tool_call + observation, then deterministically rerun) is a multi-PR effort
(requires new capture inside ``AgentLoop`` plus loop-level cassette wiring).
This module is the *first composable layer*: use the existing turn-level
``TurnEventLog`` (already capturing real production turns) as the
**ground-truth oracle** for outcome-parity replay assertions —

  for each historical turn → run the same turn input again → assert outcome
  matches (status, error_type, retrieval_hit, latency/token within band).

This catches "tutorbot turn that used to succeed now fails" regressions before
any iteration-level capture exists. Phase 2 adds iteration capture; phase 3
adds full step-by-step replay (see roadmap §0.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from deeptutor.services.observability.turn_event_log import (
    TurnEventLog,
    get_turn_event_log,
)

# Default capability filter — focus on tutorbot, which is what §2 of the
# gap analysis is about; the same machinery works on any capability label.
TUTORBOT_CAPABILITY = "tutorbot"


@dataclass(frozen=True)
class TurnOutcome:
    """The replay-assertable subset of one historical turn's outcome."""

    turn_id: str
    session_id: str
    capability: str
    status: str
    error_type: str
    retrieval_hit: bool | None
    latency_ms: float
    token_total: int

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "TurnOutcome":
        return cls(
            turn_id=str(event.get("turn_id") or ""),
            session_id=str(event.get("session_id") or ""),
            capability=str(event.get("capability") or ""),
            status=str(event.get("status") or ""),
            error_type=str(event.get("error_type") or ""),
            retrieval_hit=event.get("retrieval_hit") if isinstance(event.get("retrieval_hit"), bool) else None,
            latency_ms=float(event.get("latency_ms") or 0.0),
            token_total=int(event.get("token_total") or 0),
        )


def load_tutorbot_outcomes(
    *,
    log: TurnEventLog | None = None,
    days: int = 1,
    capability: str = TUTORBOT_CAPABILITY,
) -> list[TurnOutcome]:
    """Load recent historical outcomes for one capability (default: tutorbot)."""
    log = log or get_turn_event_log()
    events = log.load_events_range(days=max(int(days or 1), 1))
    return [
        TurnOutcome.from_event(e)
        for e in events
        if str(e.get("capability") or "") == capability and str(e.get("turn_id") or "")
    ]


@dataclass(frozen=True)
class OutcomeMismatch:
    """One field's drift between historical baseline and a fresh rerun."""

    turn_id: str
    field: str
    baseline: Any
    candidate: Any


def diff_outcomes(
    baseline: TurnOutcome,
    candidate: TurnOutcome,
    *,
    latency_tolerance_ms: float = 1500.0,
    token_tolerance_ratio: float = 0.30,
) -> list[OutcomeMismatch]:
    """Compare two outcomes, flagging meaningful regressions only.

    - status / error_type / retrieval_hit / capability: strict equality (these
      are the *correctness* slots; any drift is a regression).
    - latency_ms: within ``latency_tolerance_ms`` band (noisy by nature).
    - token_total: within ``token_tolerance_ratio`` (provider sampling drift).
    """
    out: list[OutcomeMismatch] = []
    for field in ("capability", "status", "error_type", "retrieval_hit"):
        b, c = getattr(baseline, field), getattr(candidate, field)
        if b != c:
            out.append(OutcomeMismatch(baseline.turn_id, field, b, c))
    if abs(candidate.latency_ms - baseline.latency_ms) > latency_tolerance_ms:
        out.append(
            OutcomeMismatch(baseline.turn_id, "latency_ms", baseline.latency_ms, candidate.latency_ms)
        )
    base_tok = max(int(baseline.token_total), 1)
    if abs(candidate.token_total - baseline.token_total) / base_tok > token_tolerance_ratio:
        out.append(
            OutcomeMismatch(baseline.turn_id, "token_total", baseline.token_total, candidate.token_total)
        )
    return out


def outcome_summary(outcomes: Iterable[TurnOutcome]) -> dict[str, Any]:
    """Quick stats on a collection — useful to verify replay coverage."""
    outs = list(outcomes)
    statuses: dict[str, int] = {}
    for o in outs:
        statuses[o.status] = statuses.get(o.status, 0) + 1
    return {
        "total": len(outs),
        "by_status": statuses,
        "with_error": sum(1 for o in outs if o.error_type),
        "unique_sessions": len({o.session_id for o in outs if o.session_id}),
    }
