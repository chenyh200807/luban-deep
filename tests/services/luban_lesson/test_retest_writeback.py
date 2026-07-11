from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.luban_lesson import retest_writeback as module
from deeptutor.services.luban_lesson.retest_selection import issue_retest_selection
from deeptutor.services.luban_lesson.retest_writeback import (
    RetestIdempotencyConflict,
    RetestWritebackService,
)


@dataclass
class _Event:
    event_id: str
    user_id: str
    source_feature: str
    source_id: str
    memory_kind: str
    payload_json: dict[str, Any]
    dedupe_key: str
    created_at: str


class _LearnerState:
    def __init__(self, *, fail_on_append_call: int = 0) -> None:
        self.events: list[_Event] = []
        self.by_dedupe: dict[str, _Event] = {}
        self.append_calls = 0
        self.fail_on_append_call = fail_on_append_call

    def append_memory_event(self, user_id: str, **kwargs: Any) -> _Event:
        self.append_calls += 1
        key = str(kwargs["dedupe_key"])
        if key in self.by_dedupe:
            return self.by_dedupe[key]
        if self.fail_on_append_call and self.append_calls == self.fail_on_append_call:
            self.fail_on_append_call = 0
            raise RuntimeError("synthetic_terminal_failure")
        event = _Event(
            event_id=f"evt_{len(self.events) + 1}",
            user_id=user_id,
            source_feature=str(kwargs["source_feature"]),
            source_id=str(kwargs["source_id"]),
            memory_kind=str(kwargs["memory_kind"]),
            payload_json=dict(kwargs["payload_json"]),
            dedupe_key=key,
            created_at="2026-07-11T10:00:00+08:00",
        )
        self.events.append(event)
        self.by_dedupe[key] = event
        return event

    def list_memory_events(self, user_id: str, limit=None) -> list[_Event]:
        return list(self.events)


@pytest.fixture(autouse=True)
def signed_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_REVIEW_MODULE_ENABLED", "1")
    monkeypatch.setenv("LUBAN_LIGHT_PRACTICE_ENABLED", "1")
    items = [
        {
            "variant_id": "F16-v1",
            "rule_group": "diameter",
            "surface": "直径120mm仍用抽气灌胶法",
            "expected_ok": False,
            "correct_statement": "直径达到100mm应割补",
            "anchor": "kc:F16",
        },
        {
            "variant_id": "F16-v2",
            "rule_group": "sequence",
            "surface": "割补前先清理吹干",
            "expected_ok": True,
            "correct_statement": "应先清理吹干",
            "anchor": "kc:F16",
        },
    ]
    monkeypatch.setattr(module, "build_retest_items", lambda *args, **kwargs: list(items))
    monkeypatch.setattr(
        module,
        "build_lesson_viewmodel",
        lambda pack_id: {"pack_id": pack_id, "title": "屋面防水起鼓割补"},
    )


def _answers(*, first: bool = False, second: bool = True) -> list[dict[str, Any]]:
    return [
        {"variant_id": "F16-v1", "choice_ok": first},
        {"variant_id": "F16-v2", "choice_ok": second},
    ]


def _complete(service: RetestWritebackService, **overrides: Any) -> dict[str, Any]:
    payload = {
        "user_id": "qa_eval_first_run_loop",
        "completion_id": "retest-completion-1",
        "pack_id": "F16",
        "mode": "forward",
        "day_index": 2026192,
        "answers": _answers(first=True),
        "training_intent_id": "lti_first_run_f16",
        "probe_id": "",
    }
    payload.update(overrides)
    if "selection_id" not in payload:
        canonical_mode = "review" if payload.get("probe_id") else payload["mode"]
        payload["selection_id"] = issue_retest_selection(
            user_id=payload["user_id"],
            pack_id=payload["pack_id"],
            day_index=payload["day_index"],
            mode=canonical_mode,
            variant_ids=[item["variant_id"] for item in payload["answers"]],
        )
    return service.complete(**payload)


def _service(learner: _LearnerState) -> RetestWritebackService:
    return RetestWritebackService(
        learner_state_service=learner,
        review_probe_resolver=lambda **_kwargs: {"due": True},
        training_intent_validator=lambda **_kwargs: True,
    )


def test_forward_practice_is_server_rescored_idempotent_and_short_term() -> None:
    learner = _LearnerState()
    service = _service(learner)

    first = _complete(service, answers=_answers(first=True, second=True))
    replay = _complete(service, answers=_answers(first=True, second=True))

    assert first == replay
    assert first["score"] == {"correct_count": 1, "question_count": 2}
    assert len(learner.events) == 4
    item_events = [event for event in learner.events if event.source_feature == "assessment_testset" and not event.payload_json.get("completion_terminal")]
    assert len(item_events) == 2
    assert all(event.payload_json["prescription_phase"] == "transfer_case" for event in item_events)
    assert all(event.payload_json["claim_promotion_allowed"] is False for event in item_events)
    projection = synthesize_learning_truth(learner.events)
    assert projection["weak_points"] == []
    assert projection["observed_candidates"][0]["memory_lifecycle_stage"] == "short_term_learning_memory"


def test_same_completion_id_with_different_answers_conflicts() -> None:
    learner = _LearnerState()
    service = _service(learner)
    _complete(service, answers=_answers(first=True, second=False))

    with pytest.raises(RetestIdempotencyConflict):
        _complete(service, answers=_answers(first=False, second=False))

    assert len(learner.events) == 4


def test_real_retest_wrong_confirms_weakness_and_correct_records_improvement() -> None:
    wrong_learner = _LearnerState()
    wrong_service = _service(wrong_learner)
    _complete(wrong_service, answers=_answers(first=True), completion_id="forward-wrong")
    _complete(
        wrong_service,
        answers=_answers(first=True),
        completion_id="review-wrong",
        mode="review",
        training_intent_id="rvp_f16",
        probe_id="probe-f16",
    )
    wrong_projection = synthesize_learning_truth(wrong_learner.events)
    assert wrong_projection["weak_points"][0]["evidence_level"] == "L2_real_retest"

    improved_learner = _LearnerState()
    improved_service = _service(improved_learner)
    _complete(improved_service, answers=_answers(first=True), completion_id="forward-wrong")
    _complete(
        improved_service,
        answers=_answers(first=False),
        completion_id="review-correct",
        mode="review",
        training_intent_id="rvp_f16",
        probe_id="probe-f16",
    )
    improved_projection = synthesize_learning_truth(improved_learner.events)
    assert improved_projection["weak_points"] == []
    assert improved_projection["improvement_signals"] == []


def test_answer_set_must_match_server_selected_signed_variants() -> None:
    service = _service(_LearnerState())

    with pytest.raises(ValueError, match="retest_answer_set_mismatch"):
        _complete(service, answers=[{"variant_id": "F16-v1", "choice_ok": False}])


def test_review_requires_canonical_due_probe() -> None:
    service = RetestWritebackService(
        learner_state_service=_LearnerState(),
        review_probe_resolver=lambda **_kwargs: None,
    )

    with pytest.raises(ValueError, match="retest_probe_not_due"):
        _complete(service, mode="review", probe_id="forged-probe")


def test_item_events_never_publish_completion_outcome() -> None:
    learner = _LearnerState()
    result = _complete(
        _service(learner),
        mode="review",
        probe_id="probe-f16",
        answers=_answers(first=False, second=True),
    )

    item_events = [event for event in learner.events if event.source_feature == "assessment_testset" and not event.payload_json.get("completion_terminal")]
    terminal = next(event for event in learner.events if event.payload_json.get("completion_terminal"))
    assert all("prescription_result" not in event.payload_json for event in item_events)
    assert terminal.payload_json["prescription_result"]["status"] == "verified"
    assert result["terminal_event_id"] == terminal.event_id


def test_station_completion_dedupes_per_completion_not_forever() -> None:
    learner = _LearnerState()
    service = _service(learner)
    _complete(service, completion_id="completion-a")
    _complete(service, completion_id="completion-a")
    _complete(service, completion_id="completion-b")

    stations = [event for event in learner.events if event.payload_json.get("learning_signal_type") == "station_completed"]
    assert [event.payload_json["completion_id"] for event in stations] == ["completion-a", "completion-b"]


def test_partial_item_append_never_commits_terminal_until_retry() -> None:
    learner = _LearnerState(fail_on_append_call=3)
    service = _service(learner)

    with pytest.raises(RuntimeError, match="synthetic_terminal_failure"):
        _complete(service, completion_id="partial-completion")

    assert len(learner.events) == 2
    assert not any(event.payload_json.get("completion_terminal") for event in learner.events)
    assert not any(event.payload_json.get("learning_signal_type") == "station_completed" for event in learner.events)
    partial_projection = synthesize_learning_truth(learner.events)
    assert partial_projection["weak_points"] == []
    assert partial_projection["improvement_signals"] == []

    result = _complete(service, completion_id="partial-completion")

    assert result["sync_status"] == "synced"
    assert sum(bool(event.payload_json.get("completion_terminal")) for event in learner.events) == 1
    assert sum(event.payload_json.get("learning_signal_type") == "station_completed" for event in learner.events) == 1


def test_review_replay_succeeds_after_original_probe_is_no_longer_due() -> None:
    learner = _LearnerState()
    probe_calls = []

    def _probe(**_kwargs):
        probe_calls.append(True)
        return {"due": True} if len(probe_calls) == 1 else None

    service = RetestWritebackService(
        learner_state_service=learner,
        review_probe_resolver=_probe,
        training_intent_validator=lambda **_kwargs: True,
    )
    payload = {
        "completion_id": "review-replay",
        "mode": "review",
        "probe_id": "probe-f16",
        "answers": _answers(first=False, second=True),
    }

    first = _complete(service, **payload)
    replay = _complete(service, **payload)

    assert replay == first
    assert len(probe_calls) == 1


def test_retry_heals_terminal_committed_but_station_write_failed() -> None:
    learner = _LearnerState(fail_on_append_call=4)
    service = _service(learner)

    with pytest.raises(RuntimeError, match="synthetic_terminal_failure"):
        _complete(service, completion_id="station-partial")

    assert any(event.payload_json.get("completion_terminal") for event in learner.events)
    assert not any(event.payload_json.get("learning_signal_type") == "station_completed" for event in learner.events)

    result = _complete(service, completion_id="station-partial")

    assert result["station_event_id"]
    assert sum(event.payload_json.get("learning_signal_type") == "station_completed" for event in learner.events) == 1


def test_rollout_flag_off_fails_before_any_write(monkeypatch: pytest.MonkeyPatch) -> None:
    learner = _LearnerState()
    monkeypatch.setenv("LUBAN_LIGHT_PRACTICE_ENABLED", "0")

    with pytest.raises(ValueError, match="luban_light_practice_disabled"):
        _complete(_service(learner))

    assert learner.events == []


def test_review_uses_probe_as_canonical_intent_and_ignores_client_intent() -> None:
    learner = _LearnerState()

    _complete(
        _service(learner),
        mode="forward",
        probe_id="probe-f16",
        training_intent_id="forged-intent",
        answers=_answers(first=False, second=True),
    )

    review_events = [
        event
        for event in learner.events
        if event.source_feature == "assessment_testset"
    ]
    assert review_events
    assert all(event.payload_json["practice_mode"] == "review" for event in review_events)
    assert all(event.payload_json["training_intent_id"] == "probe-f16" for event in review_events)


def test_selection_identity_prevents_day_or_variant_tampering_before_write() -> None:
    learner = _LearnerState()
    service = _service(learner)
    token = issue_retest_selection(
        user_id="qa_eval_first_run_loop",
        pack_id="F16",
        day_index=2026192,
        mode="forward",
        variant_ids=["F16-v1", "F16-v2"],
    )

    with pytest.raises(ValueError, match="retest_selection_invalid"):
        _complete(service, day_index=2026193, selection_id=token)

    assert learner.events == []
