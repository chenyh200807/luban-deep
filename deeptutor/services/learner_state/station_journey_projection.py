"""Read-only six-stage station journey over canonical learner evidence.

This projection owns no writes, scheduling or CTA arbitration.  It only turns
the existing lesson evidence, committed retest closures and pack-review due
slice into a student-facing workflow view.  Unknown historical provenance is
kept unavailable rather than reconstructed from mutable current supply.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from deeptutor.services.learner_state.evidence_lifecycle import (
    EPISODE_BINDING_EXACT,
    EPISODE_BINDING_LEGACY,
    RETEST_ROLE_FORWARD_PRACTICE,
    RETEST_ROLE_IMMEDIATE_CONFIRM,
    RETEST_ROLE_REVIEW,
    CanonicalRetestEpisodeRecord,
    canonical_retest_episode_records,
)

STATION_JOURNEY_AUTHORITY = "station_journey_projection.read_model"
STATION_JOURNEY_SCHEMA_VERSION = 1
STATION_JOURNEY_STEP_IDS = (
    "lesson",
    "practice",
    "diagnosis",
    "immediate_confirm",
    "due_validation",
    "followup",
)


def project_station_journeys(
    *,
    events: Iterable[Any] | None,
    pack_lifecycle: dict[str, Any] | None,
    pack_review: dict[str, Any] | None,
    confirm_fact_resolver: Callable[[str], Iterable[str]] | None = None,
    events_available: bool = True,
    episode_records: Iterable[CanonicalRetestEpisodeRecord] | None = None,
) -> dict[str, Any]:
    if not events_available:
        return _projection(packs={}, degraded=True, degraded_sources=["learner_events"])

    event_list = list(events or [])
    records = tuple(
        episode_records
        if episode_records is not None
        else canonical_retest_episode_records(event_list)
    )
    bound_records = [
        record
        for record in records
        if record.role
        and record.episode_id
        and record.binding in {EPISODE_BINDING_EXACT, EPISODE_BINDING_LEGACY}
    ]

    lifecycle = _dict(pack_lifecycle)
    lifecycle_packs = _dict(lifecycle.get("packs"))
    review = _dict(pack_review)
    review_available = review.get("enabled") is True and review.get("degraded") is not True
    due_by_pack = {
        _clean(row.get("pack_id")).upper(): row
        for row in list(review.get("due") or [])
        if isinstance(row, dict) and _clean(row.get("pack_id"))
    }
    records_by_pack: dict[str, list[CanonicalRetestEpisodeRecord]] = {}
    for record in bound_records:
        if record.pack_id:
            records_by_pack.setdefault(record.pack_id, []).append(record)

    pack_ids = sorted(set(lifecycle_packs) | set(records_by_pack))
    packs = {
        pack_id: _project_pack(
            pack_id=pack_id,
            lifecycle=_dict(lifecycle_packs.get(pack_id)),
            records=records_by_pack.get(pack_id, []),
            due=_dict(due_by_pack.get(pack_id)),
            review_available=review_available,
            confirm_fact_resolver=confirm_fact_resolver,
        )
        for pack_id in pack_ids
    }
    confirm_supply_degraded = any(
        step.get("reason") == "confirm_supply_projection_unavailable"
        for pack in packs.values()
        for step in list(pack.get("steps") or [])
        if isinstance(step, dict)
    )
    degraded_sources = []
    if lifecycle.get("degraded"):
        degraded_sources.append("pack_lifecycle")
    if confirm_supply_degraded:
        degraded_sources.append("variant_probe_supply")
    return _projection(
        packs=packs,
        degraded=bool(degraded_sources),
        degraded_sources=degraded_sources,
    )


def _project_pack(
    *,
    pack_id: str,
    lifecycle: dict[str, Any],
    records: list[CanonicalRetestEpisodeRecord],
    due: dict[str, Any],
    review_available: bool,
    confirm_fact_resolver: Callable[[str], Iterable[str]] | None,
) -> dict[str, Any]:
    base_indexes = [
        index
        for index, record in enumerate(records)
        if record.role == RETEST_ROLE_FORWARD_PRACTICE
    ]
    base_index = base_indexes[-1] if base_indexes else -1
    base_candidate = records[base_index] if base_index >= 0 else None
    cycle = [
        record
        for record in records[base_index:]
        if base_candidate is not None and record.episode_id == base_candidate.episode_id
    ] if base_index >= 0 else []
    base = cycle[0] if cycle else None
    confirms = [
        record for record in cycle[1:] if record.role == RETEST_ROLE_IMMEDIATE_CONFIRM
    ]
    reviews = [record for record in cycle[1:] if record.role == RETEST_ROLE_REVIEW]

    exposed = bool(_dict(lifecycle.get("exposure")))
    lesson_step = _step(
        "lesson",
        "completed" if exposed else "current" if base is None else "available",
        evidence_refs=[],
        blocking=base is None,
        reason="lesson_viewed" if exposed else "lesson_not_observed",
    )

    if base is None:
        steps = [
            lesson_step,
            _step("practice", "current" if exposed else "upcoming", blocking=True),
            _step("diagnosis", "upcoming"),
            _step("immediate_confirm", "upcoming", blocking=False),
            _step("due_validation", "upcoming"),
            _step("followup", "future"),
        ]
        return _pack_payload(pack_id, "practice" if exposed else "lesson", steps)

    base_terminal = base.terminal
    base_items = base.items
    base_ref = _event_id(base_terminal)
    wrong_items = [item for item in base_items if _payload(item).get("is_correct") is False]
    practice_step = _step("practice", "completed", evidence_refs=[base_ref])

    if not wrong_items:
        diagnosis_step = _step("diagnosis", "not_applicable", blocking=False, reason="all_correct")
        confirm_step = _step(
            "immediate_confirm", "not_applicable", blocking=False, reason="all_correct"
        )
    else:
        diagnosis_ready = all(_feedback_ready(_payload(item)) for item in wrong_items)
        diagnosis_step = _step(
            "diagnosis",
            "completed" if diagnosis_ready else "unavailable",
            evidence_refs=[_event_id(item) for item in wrong_items],
            blocking=False,
            reason="canonical_feedback_ready" if diagnosis_ready else "feedback_unavailable",
        )
        if confirms:
            confirm_step = _step(
                "immediate_confirm",
                "completed",
                evidence_refs=[_event_id(record.terminal) for record in confirms],
                blocking=False,
                reason="canonical_confirm_terminal",
            )
        else:
            wrong_facts = {
                _clean(_payload(item).get("fact_id")) for item in wrong_items
            }
            wrong_facts.discard("")
            ready_facts: set[str] = set()
            supply_projection_failed = False
            if wrong_facts and confirm_fact_resolver is not None:
                try:
                    ready_facts = {
                        _clean(fact) for fact in confirm_fact_resolver(pack_id) if _clean(fact)
                    }
                except Exception:
                    supply_projection_failed = True
                    ready_facts = set()
            actionable_facts = sorted(wrong_facts & ready_facts)
            actionable = bool(actionable_facts)
            confirm_step = _step(
                "immediate_confirm",
                "current" if actionable else "unavailable",
                evidence_refs=[_event_id(item) for item in wrong_items],
                blocking=False,
                reason=(
                    "safe_confirm_available"
                    if actionable
                    else "confirm_supply_projection_unavailable"
                    if supply_projection_failed
                    else "safe_confirm_unavailable"
                ),
            )
            if actionable and base_ref:
                # 轻练确认重入口(只读):回执现场之外重建同一合法确认会话所需
                # 的最小输入——本轮错题 facts ∩ 安全供给 facts(本投影判定
                # current 时已算出的同一交集,零第二权威)+ 本轮 forward
                # canonical terminal(retest 确认会话 confirm_anchor 输入,
                # 服务端 admission 仍逐项复核,此处不签发任何新事实)。
                confirm_step["confirm_facts"] = actionable_facts
                confirm_step["confirm_anchor"] = base_ref

    due_state = _clean(due.get("state"))
    successful_reviews = [
        record
        for record in reviews
        if _clean(_dict(_payload(record.terminal).get("prescription_result")).get("status"))
        == "verified"
    ]
    review_streak = 0
    for record in reviews:
        status = _clean(
            _dict(_payload(record.terminal).get("prescription_result")).get("status")
        )
        review_streak = review_streak + 1 if status == "verified" else 0

    if successful_reviews:
        validation_step = _step(
            "due_validation",
            "completed",
            evidence_refs=[_event_id(successful_reviews[0].terminal)],
            blocking=False,
            reason="canonical_review_passed",
        )
    elif reviews:
        validation_step = _step(
            "due_validation",
            "current",
            evidence_refs=[_event_id(record.terminal) for record in reviews],
            blocking=True,
            reason="canonical_review_failed",
        )
    elif review_available and due and due_state == "fresh":
        validation_step = _due_step("due_validation", due)
    elif review_available:
        validation_step = _step("due_validation", "scheduled", blocking=False)
    else:
        validation_step = _step(
            "due_validation", "unavailable", blocking=False, reason="review_projection_unavailable"
        )

    # 轻练确认是错后加分项,不是记忆闭环的唯一兜底:本站确认供给未开
    # (safe_confirm_unavailable)但到期验证已在轨(scheduled/current/completed)
    # 时,本轮错题 fact 由第 5 步到期验证卷兜底必考——语义是「并入到期验证」而非
    # 「不可用」。发精确 reason 供呈现层映射(status 仍留 unavailable,不造新相位,
    # 防契约面扩散)。到期验证不在轨(降级 unavailable)时保持原 reason,不误报。
    # 只改 safe_confirm_unavailable;confirm_supply_projection_unavailable 的降级
    # 溯源(variant_probe_supply)不并入。
    if (
        confirm_step["status"] == "unavailable"
        and confirm_step["reason"] == "safe_confirm_unavailable"
        and validation_step["status"] in {"scheduled", "current", "completed"}
    ):
        confirm_step["reason"] = "confirm_covered_by_due_validation"

    if review_streak >= 2:
        followup_step = _step(
            "followup",
            "completed",
            evidence_refs=[_event_id(record.terminal) for record in reviews[1:]],
            blocking=False,
            reason="canonical_followup_passed",
        )
    elif successful_reviews and reviews and _clean(
        _dict(_payload(reviews[-1].terminal).get("prescription_result")).get("status")
    ) != "verified":
        followup_step = _step(
            "followup",
            "current",
            evidence_refs=[_event_id(reviews[-1].terminal)],
            blocking=True,
            reason="canonical_followup_failed",
        )
    elif successful_reviews and review_available and due:
        followup_step = _due_step("followup", due)
    elif successful_reviews and review_available:
        followup_step = _step("followup", "scheduled", blocking=False)
    elif reviews:
        followup_step = _step("followup", "future", blocking=False)
    elif review_available:
        followup_step = _step("followup", "future", blocking=False)
    else:
        followup_step = _step(
            "followup", "unavailable", blocking=False, reason="review_projection_unavailable"
        )

    steps = [
        lesson_step,
        practice_step,
        diagnosis_step,
        confirm_step,
        validation_step,
        followup_step,
    ]
    current_step_id = next(
        (
            step["id"]
            for step in steps
            if step["status"] in {"current", "scheduled"}
        ),
        "",
    )
    journey_state = (
        "completed"
        if followup_step["status"] == "completed"
        else "active"
        if current_step_id
        else "unavailable"
    )
    return _pack_payload(pack_id, current_step_id, steps, journey_state=journey_state)


def _due_step(step_id: str, due: dict[str, Any]) -> dict[str, Any]:
    step = _step(
        step_id,
        "current",
        blocking=True,
        reason="revalidation_due",
    )
    step["probe_id"] = _clean(due.get("probe_id"))
    step["due_at"] = _clean(due.get("due_at"))
    return step


def _step(
    step_id: str,
    status: str,
    *,
    evidence_refs: Iterable[str] = (),
    blocking: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "id": step_id,
        "status": status,
        "evidence_refs": [ref for ref in (_clean(item) for item in evidence_refs) if ref],
        "blocking": bool(blocking),
        "reason": reason,
    }


def _pack_payload(
    pack_id: str,
    current_step_id: str,
    steps: list[dict[str, Any]],
    *,
    journey_state: str = "active",
) -> dict[str, Any]:
    return {
        "pack_id": pack_id,
        "journey_state": journey_state,
        "current_step_id": current_step_id,
        "steps": steps,
    }


def _projection(*, packs: dict[str, Any], degraded: bool, degraded_sources: list[str]) -> dict[str, Any]:
    return {
        "authority": STATION_JOURNEY_AUTHORITY,
        "schema_version": STATION_JOURNEY_SCHEMA_VERSION,
        "degraded": degraded,
        "degraded_sources": degraded_sources,
        "step_ids": list(STATION_JOURNEY_STEP_IDS),
        "packs": packs,
    }


def _feedback_ready(payload: dict[str, Any]) -> bool:
    feedback = _dict(payload.get("answer_feedback"))
    return all(_clean(feedback.get(key)) for key in ("temptation", "loss_reason", "fix"))


def _event_id(event: Any) -> str:
    return _clean(getattr(event, "event_id", ""))


def _payload(event: Any) -> dict[str, Any]:
    return _dict(getattr(event, "payload_json", {}))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "STATION_JOURNEY_AUTHORITY",
    "STATION_JOURNEY_SCHEMA_VERSION",
    "STATION_JOURNEY_STEP_IDS",
    "project_station_journeys",
]
