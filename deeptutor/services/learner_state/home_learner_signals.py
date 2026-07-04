"""Canonical home-dashboard learner signals (``review`` + ``weak_nodes``).

Single-authority collapse (2026-07): the home dashboard's ``review`` and
``weak_nodes`` used to be computed by member-local heuristics inside
``member_console.service`` (member["review_due"] scalar arithmetic and a
member chapter_mastery filter). Those heuristics were then read back by
``learning_report_read_model`` (``home_dashboard.review.due_today`` /
``home_dashboard.mastery.weak_nodes``) as if canonical — an authority drift.

This module is the single derivation point for those two signals. It does NOT
create a scheduler, a second prescription authority, or a reconciliation gate.
It is a thin pure function that reads existing canonical projections:

- ``review`` is derived from :func:`build_revalidation_queue_projection` (the
  ARRS revalidation queue over canonical ``learner_memory_events``). This is
  the same canonical projection ``learning_report_read_model`` consumes, so the
  home dashboard's review is now a *derivation* of that queue, not an
  independent member-local guess.

- ``weak_nodes`` is derived from canonical per-chapter mastery *numbers*. As of
  this collapse, the deepest available source of a per-chapter mastery number
  is still the member snapshot's ``chapter_mastery`` / ``last_assessment``
  (learning_brain ``weak_points`` carry concept/error semantics but no mastery
  number). So the weak_nodes half is honestly NOT yet collapsed to a lower
  canonical source; it is passed in as ``mastery_items`` and filtered/sorted
  here. See ``mastery_source`` in the returned ``source_status``.

Import discipline: this module lives in ``learner_state`` and imports only
sibling learner_state projections. ``member_console.service`` imports THIS
module; this module never imports ``member_console`` or
``learning_report_read_model`` — so no import cycle and no
home_dashboard ↔ learning_report cycle is created.
"""
from __future__ import annotations

from typing import Any, Iterable

from deeptutor.services.learner_state.revalidation_queue import (
    build_revalidation_queue_projection,
    dispute_candidates_from_events,
)


_WEAK_MASTERY_THRESHOLD = 60


def build_home_learner_signals(
    *,
    user_id: str,
    memory_events: Iterable[Any] | None = None,
    mastery_items: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive the home dashboard's ``review`` and ``weak_nodes`` from canonical
    projections.

    Returns a dict with the exact downstream shape:
    ``{"review": {"overdue": int, "due_today": int},
       "weak_nodes": [{"name": str, "mastery": int}, ...],
       "source_status": {...}}``.
    """
    review, review_status = _build_review_from_revalidation_queue(
        user_id=user_id,
        memory_events=list(memory_events or []),
    )
    weak_nodes = _build_weak_nodes(mastery_items=list(mastery_items or []))
    return {
        "review": review,
        "weak_nodes": weak_nodes,
        "source_status": {
            "review": review_status,
            "weak_nodes": {
                # HONEST NOTE: canonical mastery numbers have no source below the
                # member snapshot chapter_mastery yet. This half is not collapsed.
                "authority": "member_snapshot.chapter_mastery",
                "mastery_source": "member_chapter_mastery",
                "collapsed": False,
            },
        },
    }


def _build_review_from_revalidation_queue(
    *,
    user_id: str,
    memory_events: list[Any],
) -> tuple[dict[str, int], dict[str, Any]]:
    projection = build_revalidation_queue_projection(
        user_id=user_id,
        events=memory_events,
        dispute_candidates=dispute_candidates_from_events(memory_events),
    )
    items = list(projection.get("items") or [])
    status = dict(projection.get("source_status") or {})
    # v0 daily capacity is 1: at most one probe is emitted, the rest are
    # suppressed-but-due. Keep the historical {overdue, due_today} shape:
    #   due_today = whether a probe is due right now (0/1, matches capacity)
    #   overdue   = additional due probes beyond today's capacity
    due_today = 1 if items else 0
    overdue = max(0, int(status.get("suppressed_due_count") or 0))
    return {"overdue": overdue, "due_today": due_today}, status


def _build_weak_nodes(*, mastery_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weak = [
        {"name": item["name"], "mastery": int(item.get("mastery") or 0)}
        for item in mastery_items
        if isinstance(item, dict)
        and item.get("name")
        and int(item.get("mastery") or 0) < _WEAK_MASTERY_THRESHOLD
    ]
    weak.sort(key=lambda item: item["mastery"])
    return weak


__all__ = ["build_home_learner_signals"]
