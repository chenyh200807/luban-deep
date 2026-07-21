from __future__ import annotations

import hashlib

import pytest

from deeptutor.services.learner_state.evidence_lifecycle import (
    canonical_retest_completion_role,
    validate_immediate_confirm_parent,
)
from deeptutor.services.learner_state.service import LearnerStateEvent
from deeptutor.services.learner_state.station_journey_projection import (
    STATION_JOURNEY_AUTHORITY,
    project_station_journeys,
)


def _event(event_id: str, created_at: str, payload: dict) -> LearnerStateEvent:
    completion_id = str(payload.get("retest_completion_id") or "")
    terminal = payload.get("completion_terminal") is True
    return LearnerStateEvent(
        event_id=event_id,
        user_id="student",
        source_feature="assessment_testset" if completion_id else "luban_lesson",
        source_id=(f"{completion_id}:terminal" if terminal else f"{completion_id}:q")
        if completion_id
        else "lesson_viewed:N01:lesson",
        source_bot_id=None,
        memory_kind="learning_evidence",
        dedupe_key=event_id,
        created_at=created_at,
        payload_json=payload,
    )


def _completion(
    completion_id: str,
    *,
    at: str,
    mode: str = "forward",
    correct: bool = False,
    probe_role: str = "anchor",
    fact_id: str = "fact-n01",
    feedback: bool = True,
    cycle_anchor: str = "",
) -> list[LearnerStateEvent]:
    item_id = f"item_{completion_id}"
    request_hash = hashlib.sha256(completion_id.encode("utf-8")).hexdigest()
    status = "verified" if mode == "review" and correct else "not_verified"
    item_payload = {
        "event_type": "learning_evidence",
        "retest_completion_id": completion_id,
        "request_hash": request_hash,
        "request_hash_version": 3,
        "practice_mode": mode,
        "pack_id": "N01",
        "target_pack_id": "N01",
        "question_id": f"q_{completion_id}",
        "is_correct": correct,
        "score_awarded": 1.0 if correct else 0.0,
        "max_score": 1.0,
        "fact_id": fact_id,
        "probe_role": probe_role,
        "probe_id": f"probe-{completion_id}" if mode == "review" else "",
        "cycle_anchor": cycle_anchor,
    }
    if feedback:
        item_payload["answer_feedback"] = {
            "temptation": "常见陷阱",
            "loss_reason": "常见失分点",
            "fix": "一句修正",
        }
    terminal_payload = {
        "event_type": "learning_evidence",
        "evidence_source": "assessment_testset",
        "assessment_type": f"luban_{mode}_completion",
        "retest_completion_id": completion_id,
        "completion_terminal": True,
        "request_hash": request_hash,
        "request_hash_version": 3,
        "practice_mode": mode,
        "pack_id": "N01",
        "target_pack_id": "N01",
        "score_awarded": 1.0 if correct else 0.0,
        "max_score": 1.0,
        "item_event_refs": [item_id],
        "probe_id": f"probe-{completion_id}" if mode == "review" else "",
        "cycle_anchor": cycle_anchor,
        "claim_promotion_allowed": mode == "review",
        "prescription_result": {"status": status, "score_ratio": 1.0 if correct else 0.0},
        "quality": {
            "authority": "signed_variant_server_rescore",
            "writeback_eligible": True,
            "measurement_confidence": "high" if mode == "review" else "medium",
            "evidence_level": "L2_real_retest" if mode == "review" else "L0_observed",
        },
    }
    return [
        _event(item_id, at, item_payload),
        _event(f"terminal_{completion_id}", at, terminal_payload),
    ]


def _lifecycle(*, exposed: bool = True) -> dict:
    return {
        "packs": {
            "N01": {
                "lifecycle_state": "exposed" if exposed else "unlearned",
                "exposure": {"lesson": 1} if exposed else {},
            }
        }
    }


def _review(*, due: list[dict] | None = None, enabled: bool | None = True) -> dict:
    return {"enabled": enabled, "due": list(due or [])}


def _journey(events: list[LearnerStateEvent], **kwargs) -> dict:
    projection = project_station_journeys(
        events=events,
        pack_lifecycle=_lifecycle(),
        pack_review=_review(**kwargs),
        confirm_fact_resolver=lambda _pack: {"fact-n01"},
    )
    assert projection["authority"] == STATION_JOURNEY_AUTHORITY
    return projection["packs"]["N01"]


def _statuses(journey: dict) -> dict[str, str]:
    return {step["id"]: step["status"] for step in journey["steps"]}


def test_lesson_only_waits_for_five_questions() -> None:
    journey = _journey([])
    statuses = _statuses(journey)
    assert statuses["lesson"] == "completed"
    assert statuses["practice"] == "current"
    assert journey["current_step_id"] == "practice"


def test_full_score_skips_diagnosis_and_confirmation_then_schedules_d1() -> None:
    journey = _journey(_completion("forward", at="2026-07-18T09:00:00+08:00", correct=True))
    statuses = _statuses(journey)
    assert statuses["practice"] == "completed"
    assert statuses["diagnosis"] == "not_applicable"
    assert statuses["immediate_confirm"] == "not_applicable"
    assert statuses["due_validation"] == "scheduled"
    assert journey["current_step_id"] == "due_validation"


def test_wrong_answer_projects_diagnosis_and_safe_confirmation() -> None:
    journey = _journey(_completion("forward", at="2026-07-18T09:00:00+08:00"))
    statuses = _statuses(journey)
    assert statuses["diagnosis"] == "completed"
    assert statuses["immediate_confirm"] == "current"
    assert journey["current_step_id"] == "immediate_confirm"


def test_actionable_confirm_exposes_reentry_facts_and_anchor() -> None:
    """confirm=current 时投影暴露重入口只读字段:错题∩供给交集 + forward 锚。

    交集必须只含本轮错题命中的 fact(供给超集不得泄进来),锚必须是本轮
    forward canonical terminal event_id(retest 确认会话 confirm_anchor 输入)。
    """
    projection = project_station_journeys(
        events=_completion("forward", at="2026-07-18T09:00:00+08:00"),
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),
        confirm_fact_resolver=lambda _pack: {"fact-n01", "fact-unrelated-supply"},
    )
    confirm = next(
        step
        for step in projection["packs"]["N01"]["steps"]
        if step["id"] == "immediate_confirm"
    )
    assert confirm["status"] == "current"
    assert confirm["reason"] == "safe_confirm_available"
    assert confirm["confirm_facts"] == ["fact-n01"]
    assert confirm["confirm_anchor"] == "terminal_forward"


def test_non_actionable_confirm_steps_never_carry_reentry_fields() -> None:
    """非 current 的 confirm 步(unavailable/not_applicable/completed)不得
    出现 confirm_facts/confirm_anchor——客户端缺字段一律 fail-closed 不亮 CTA。
    """
    # unavailable:供给空
    unavailable = project_station_journeys(
        events=_completion("forward", at="2026-07-18T09:00:00+08:00"),
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),
        confirm_fact_resolver=lambda _pack: set(),
    )
    # not_applicable:全对
    all_correct = project_station_journeys(
        events=_completion("forward", at="2026-07-18T09:00:00+08:00", correct=True),
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),
        confirm_fact_resolver=lambda _pack: {"fact-n01"},
    )
    # completed:同轮已有 canonical confirm terminal
    forward = _completion("forward", at="2026-07-18T09:00:00+08:00")
    confirm_events = _completion(
        "confirm",
        at="2026-07-18T09:20:00+08:00",
        correct=True,
        probe_role="immediate_confirm",
        cycle_anchor="terminal_forward",
    )
    completed = project_station_journeys(
        events=forward + confirm_events,
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),
        confirm_fact_resolver=lambda _pack: {"fact-n01"},
    )
    expected = {"unavailable": unavailable, "not_applicable": all_correct, "completed": completed}
    for status, projection in expected.items():
        confirm = next(
            step
            for step in projection["packs"]["N01"]["steps"]
            if step["id"] == "immediate_confirm"
        )
        assert confirm["status"] == status
        assert "confirm_facts" not in confirm
        assert "confirm_anchor" not in confirm


def test_missing_fact_or_safe_supply_is_unavailable_but_non_blocking() -> None:
    projection = project_station_journeys(
        events=_completion(
            "forward",
            at="2026-07-18T09:00:00+08:00",
            fact_id="",
        ),
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),
        confirm_fact_resolver=lambda _pack: set(),
    )
    journey = projection["packs"]["N01"]
    confirm = next(step for step in journey["steps"] if step["id"] == "immediate_confirm")
    assert confirm["status"] == "unavailable"
    assert confirm["blocking"] is False
    assert journey["current_step_id"] == "due_validation"


def test_confirm_supply_failure_keeps_distinct_degraded_provenance() -> None:
    def unavailable_resolver(_pack: str) -> set[str]:
        raise RuntimeError("supply unavailable")

    projection = project_station_journeys(
        events=_completion("forward", at="2026-07-18T09:00:00+08:00"),
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),
        confirm_fact_resolver=unavailable_resolver,
    )
    confirm = next(
        step
        for step in projection["packs"]["N01"]["steps"]
        if step["id"] == "immediate_confirm"
    )
    assert confirm["status"] == "unavailable"
    assert confirm["reason"] == "confirm_supply_projection_unavailable"
    assert projection["degraded"] is True
    assert projection["degraded_sources"] == ["variant_probe_supply"]


def test_confirm_unavailable_reads_as_covered_when_due_validation_on_track() -> None:
    """确认供给未开但到期验证已在轨(scheduled)时,confirm reason 改发
    `confirm_covered_by_due_validation`——语义是「并入到期验证」而非「不可用」。
    status 仍留 unavailable(不造新相位),blocking 仍 False,不误挡学下一站。"""
    projection = project_station_journeys(
        events=_completion("forward", at="2026-07-18T09:00:00+08:00"),
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),  # enabled → due_validation 落 scheduled
        confirm_fact_resolver=lambda _pack: set(),  # 供给空 → safe_confirm_unavailable
    )
    journey = projection["packs"]["N01"]
    statuses = _statuses(journey)
    confirm = next(step for step in journey["steps"] if step["id"] == "immediate_confirm")
    assert statuses["due_validation"] == "scheduled"
    assert confirm["status"] == "unavailable"
    assert confirm["reason"] == "confirm_covered_by_due_validation"
    assert confirm["blocking"] is False
    assert projection["degraded"] is False


def test_confirm_unavailable_keeps_original_reason_when_due_validation_off_track() -> None:
    """到期验证也不在轨(复习投影降级 unavailable)时,confirm 不得谎报「已并入」——
    保持原 `safe_confirm_unavailable`,让呈现层如实降级。"""
    projection = project_station_journeys(
        events=_completion("forward", at="2026-07-18T09:00:00+08:00"),
        pack_lifecycle=_lifecycle(),
        pack_review=_review(enabled=False),  # 复习不可用 → due_validation unavailable
        confirm_fact_resolver=lambda _pack: set(),
    )
    journey = projection["packs"]["N01"]
    statuses = _statuses(journey)
    confirm = next(step for step in journey["steps"] if step["id"] == "immediate_confirm")
    assert statuses["due_validation"] == "unavailable"
    assert confirm["status"] == "unavailable"
    assert confirm["reason"] == "safe_confirm_unavailable"


def test_confirm_then_d1_then_followup_use_chained_canonical_terminals() -> None:
    forward = _completion("forward", at="2026-07-18T09:00:00+08:00")
    confirm = _completion(
        "confirm",
        at="2026-07-18T09:05:00+08:00",
        correct=True,
        probe_role="immediate_confirm",
        cycle_anchor="terminal_forward",
    )
    review_1 = _completion(
        "reviewone",
        at="2026-07-19T09:00:00+08:00",
        mode="review",
        correct=True,
        probe_role="anchor",
        cycle_anchor="terminal_forward",
    )
    review_2 = _completion(
        "reviewtwo",
        at="2026-07-22T09:00:00+08:00",
        mode="review",
        correct=True,
        probe_role="d1_probe",
        cycle_anchor="terminal_reviewone",
    )

    after_confirm = _statuses(_journey([*forward, *confirm]))
    assert after_confirm["immediate_confirm"] == "completed"
    assert after_confirm["due_validation"] == "scheduled"

    after_d1 = _statuses(_journey([*forward, *confirm, *review_1]))
    assert after_d1["due_validation"] == "completed"
    assert after_d1["followup"] == "scheduled"

    after_followup = _statuses(_journey([*forward, *confirm, *review_1, *review_2]))
    assert after_followup["followup"] == "completed"


@pytest.mark.parametrize(
    ("stored_item_id", "item_ref"),
    [
        (
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "AAAAAAAAAAAA4AAA8AAAAAAAAAAAAAAA",
        ),
        (
            "aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa",
            "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
        ),
    ],
)
def test_item_event_refs_bind_across_uuid_representations(
    stored_item_id: str,
    item_ref: str,
) -> None:
    events = _completion("uuidrefs", at="2026-07-18T09:00:00+08:00", correct=True)
    events[0].event_id = stored_item_id
    events[1].payload_json["item_event_refs"] = [item_ref]

    assert canonical_retest_completion_role(events, terminal=events[1]) == "forward_practice"
    assert _statuses(_journey(events))["practice"] == "completed"


def test_cycle_anchor_and_terminal_identity_bind_across_uuid_representations() -> None:
    forward = _completion("uuidforward", at="2026-07-18T09:00:00+08:00")
    forward[1].event_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    confirm = _completion(
        "uuidconfirm",
        at="2026-07-18T09:05:00+08:00",
        correct=True,
        probe_role="immediate_confirm",
        cycle_anchor="AAAAAAAAAAAA4AAA8AAAAAAAAAAAAAAA",
    )

    statuses = _statuses(_journey([*forward, *confirm]))

    assert statuses["immediate_confirm"] == "completed"
    assert validate_immediate_confirm_parent(
        forward,
        pack_id="N01",
        parent_terminal_id="AAAAAAAAAAAA4AAA8AAAAAAAAAAAAAAA",
        fact_ids={"fact-n01"},
    ) is True


def test_exact_due_item_controls_current_validation_stage() -> None:
    forward = _completion("forward", at="2026-07-18T09:00:00+08:00", correct=True)
    due = [{"pack_id": "N01", "state": "fresh", "probe_id": "rvp", "due_at": "now"}]
    statuses = _statuses(_journey(forward, due=due))
    assert statuses["due_validation"] == "current"


def test_unrelated_confirm_fact_cannot_close_current_episode() -> None:
    forward = _completion("forward", at="2026-07-18T09:00:00+08:00", fact_id="fact-n01")
    unrelated = _completion(
        "confirm",
        at="2026-07-18T09:05:00+08:00",
        correct=True,
        probe_role="immediate_confirm",
        fact_id="fact-b",
        cycle_anchor="terminal_forward",
    )
    statuses = _statuses(_journey([*forward, *unrelated]))
    assert statuses["immediate_confirm"] == "current"


def test_late_confirm_from_older_same_fact_episode_cannot_close_latest() -> None:
    first = _completion(
        "first",
        at="2026-07-18T09:00:00+08:00",
        fact_id="fact-n01",
    )
    latest = _completion(
        "latest",
        at="2026-07-18T10:00:00+08:00",
        fact_id="fact-n01",
    )
    late_confirm = _completion(
        "lateconfirm",
        at="2026-07-18T10:05:00+08:00",
        correct=True,
        probe_role="immediate_confirm",
        fact_id="fact-n01",
        cycle_anchor="terminal_first",
    )
    statuses = _statuses(_journey([*first, *latest, *late_confirm]))
    assert statuses["immediate_confirm"] == "current"
    assert validate_immediate_confirm_parent(
        [*first, *latest],
        pack_id="N01",
        parent_terminal_id="terminal_first",
        fact_ids={"fact-n01"},
    ) is False
    assert validate_immediate_confirm_parent(
        [*first, *latest],
        pack_id="N01",
        parent_terminal_id="terminal_latest",
        fact_ids={"fact-n01"},
    ) is True


def test_mixed_blank_and_confirm_roles_fail_closed() -> None:
    forward = _completion("forward", at="2026-07-18T09:00:00+08:00")
    confirm = _completion(
        "mixedconfirm",
        at="2026-07-18T09:05:00+08:00",
        correct=True,
        probe_role="immediate_confirm",
        cycle_anchor="terminal_forward",
    )
    extra = _event(
        "item_mixedconfirm_blank",
        "2026-07-18T09:05:00+08:00",
        {
            **confirm[0].payload_json,
            "question_id": "q_blank",
            "probe_role": "",
            "score_awarded": 1.0,
            "max_score": 1.0,
        },
    )
    confirm[1].payload_json["item_event_refs"].append(extra.event_id)
    confirm[1].payload_json["score_awarded"] = 2.0
    confirm[1].payload_json["max_score"] = 2.0
    statuses = _statuses(_journey([*forward, confirm[0], extra, confirm[1]]))
    assert statuses["immediate_confirm"] == "current"


def test_historical_mixed_forward_without_cycle_anchor_restores_base_episode() -> None:
    mixed = _completion(
        "mixedforward",
        at="2026-07-18T09:00:00+08:00",
        correct=True,
        probe_role="anchor",
    )
    extra = _event(
        "item_mixedforward_probe",
        "2026-07-18T09:00:00+08:00",
        {
            **mixed[0].payload_json,
            "question_id": "q_probe",
            "probe_role": "d1_probe",
            "score_awarded": 1.0,
            "max_score": 1.0,
        },
    )
    mixed[1].payload_json["item_event_refs"].append(extra.event_id)
    mixed[1].payload_json["score_awarded"] = 2.0
    mixed[1].payload_json["max_score"] = 2.0

    event_history = [mixed[0], extra, mixed[1]]
    statuses = _statuses(_journey(event_history))

    assert statuses["practice"] == "completed"
    assert statuses["diagnosis"] == "not_applicable"
    assert statuses["immediate_confirm"] == "not_applicable"
    assert _statuses(_journey(event_history)) == statuses


def test_empty_anchor_homogeneous_confirm_keeps_identity_but_cannot_bind() -> None:
    confirm = _completion(
        "orphan_confirm",
        at="2026-07-18T09:00:00+08:00",
        correct=True,
        probe_role="immediate_confirm",
        cycle_anchor="",
    )

    assert canonical_retest_completion_role(
        confirm,
        terminal=confirm[1],
    ) == "immediate_confirm"
    statuses = _statuses(_journey(confirm))
    assert statuses["practice"] == "current"
    assert statuses["due_validation"] == "upcoming"


@pytest.mark.parametrize("probe_role", ["d1_probe", "unknown_role", ""])
def test_empty_anchor_without_anchor_role_fails_closed(probe_role: str) -> None:
    completion = _completion(
        f"orphan_{probe_role or 'blank'}",
        at="2026-07-18T09:00:00+08:00",
        correct=True,
        probe_role=probe_role,
        cycle_anchor="",
    )

    assert canonical_retest_completion_role(
        completion,
        terminal=completion[1],
    ) == ""
    statuses = _statuses(_journey(completion))
    assert statuses["practice"] == "current"
    assert statuses["due_validation"] == "upcoming"


def test_review_with_wrong_cycle_anchor_cannot_advance_validation() -> None:
    forward = _completion("forward", at="2026-07-18T09:00:00+08:00", correct=True)
    wrong_cycle = _completion(
        "review",
        at="2026-07-19T09:00:00+08:00",
        mode="review",
        correct=True,
        cycle_anchor="terminal-from-another-cycle",
    )
    statuses = _statuses(_journey([*forward, *wrong_cycle]))
    assert statuses["due_validation"] == "scheduled"
    assert statuses["followup"] == "future"


def test_failed_first_review_stays_on_due_validation() -> None:
    forward = _completion("forward", at="2026-07-18T09:00:00+08:00", correct=True)
    failed = _completion(
        "review",
        at="2026-07-19T09:00:00+08:00",
        mode="review",
        correct=False,
        cycle_anchor="terminal_forward",
    )
    journey = _journey([*forward, *failed])
    statuses = _statuses(journey)
    assert statuses["due_validation"] == "current"
    assert statuses["followup"] == "future"
    assert journey["current_step_id"] == "due_validation"


def test_incomplete_feedback_does_not_claim_diagnosis_completed() -> None:
    events = _completion("forward", at="2026-07-18T09:00:00+08:00", feedback=False)
    events[0].payload_json["answer_feedback"] = {"loss_reason": "只有失分原因"}
    assert _statuses(_journey(events))["diagnosis"] == "unavailable"


def test_review_projection_unavailable_has_no_fake_current_step() -> None:
    journey = _journey(
        _completion("forward", at="2026-07-18T09:00:00+08:00", correct=True),
        enabled=False,
    )
    assert _statuses(journey)["due_validation"] == "unavailable"
    assert journey["current_step_id"] == ""
    assert journey["journey_state"] == "unavailable"


def test_unavailable_event_source_fails_closed_without_pack_progress() -> None:
    projection = project_station_journeys(
        events=[],
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),
        events_available=False,
    )
    assert projection["degraded"] is True
    assert projection["packs"] == {}


def test_wrong_fact_with_real_compiled_probe_supply_enters_confirm_current() -> None:
    """六步第 4 步供给收权集成锚（2026-07-20）：真实 resolver 链
    （variant_probe_fact_ids → compiled v3 per-Pack artifact）对 compiled pack
    必须能把「有错题且供给覆盖」投影成 immediate_confirm current——
    此前该链只认 legacy bank，40 个 compiled 站里 38 个供给面为空。"""
    from deeptutor.services.luban_lesson.variant_eligibility import (
        variant_probe_fact_ids,
    )

    facts = variant_probe_fact_ids("N01", probe_role="immediate_confirm")
    assert facts  # compiled 工件 fact 三件套已签发上线
    projection = project_station_journeys(
        events=_completion(
            "forward", at="2026-07-18T09:00:00+08:00", fact_id=sorted(facts)[0]
        ),
        pack_lifecycle=_lifecycle(),
        pack_review=_review(),
        confirm_fact_resolver=lambda pack: variant_probe_fact_ids(
            pack, probe_role="immediate_confirm"
        ),
    )
    journey = projection["packs"]["N01"]
    statuses = {step["id"]: step["status"] for step in journey["steps"]}
    assert statuses["immediate_confirm"] == "current"
    assert journey["current_step_id"] == "immediate_confirm"
    assert projection["degraded"] is False
