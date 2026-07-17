from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

import pytest

from deeptutor.services.learner_state.evidence_lifecycle import (
    canonical_retest_item_events,
)
from deeptutor.services.learner_state.learning_report_read_model import (
    _aggregate_learning_evidence,
    _learning_evidence_events,
)
from deeptutor.services.learner_state.learning_synthesis import synthesize_learning_truth
from deeptutor.services.learner_state.pack_lifecycle_projection import (
    project_pack_lifecycle,
)
from deeptutor.services.luban_lesson import retest_writeback as module
from deeptutor.services.luban_lesson.retest_selection import issue_retest_selection
from deeptutor.services.luban_lesson.retest_writeback import (
    RetestCompletionInProgress,
    RetestIdempotencyConflict,
    RetestProbeClaimUnavailable,
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
    def __init__(
        self,
        *,
        fail_on_append_call: int = 0,
        events: list[_Event] | None = None,
        by_dedupe: dict[str, _Event] | None = None,
        probe_claims: dict[tuple[str, str, str], dict[str, str]] | None = None,
        probe_claim_lock: Lock | None = None,
        claim_available: bool = True,
    ) -> None:
        self.events = events if events is not None else []
        self.by_dedupe = by_dedupe if by_dedupe is not None else {}
        self.probe_claims = probe_claims if probe_claims is not None else {}
        self.probe_claim_lock = probe_claim_lock or Lock()
        self.claim_available = claim_available
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

    def list_retest_completion_events_authoritative(
        self, user_id: str, completion_id: str
    ) -> list[_Event]:
        return [
            event
            for event in self.events
            if event.payload_json.get("retest_completion_id") == completion_id
            or event.payload_json.get("completion_id") == completion_id
        ]

    def claim_retest_probe(
        self,
        *,
        user_id: str,
        probe_id: str,
        cycle_anchor: str,
        completion_id: str,
        request_hash: str,
    ) -> dict[str, str]:
        if not self.claim_available:
            raise RuntimeError("retest_probe_atomic_authority_unavailable")
        key = (user_id, probe_id, cycle_anchor)
        with self.probe_claim_lock:
            existing = self.probe_claims.get(key)
            if existing is None:
                existing = {
                    "status": "acquired",
                    "completion_id": completion_id,
                    "request_hash": request_hash,
                }
                self.probe_claims[key] = existing
                return dict(existing)
            return {
                **existing,
                "status": (
                    "conflict"
                    if existing["request_hash"] != request_hash
                    else "acquired"
                    if existing["completion_id"] == completion_id
                    else "replay"
                ),
            }


class _NonLexicalEventIdLearnerState(_LearnerState):
    """Mimic UUID ordering that does not preserve append/question order."""

    _ids = ("evt-claim", "evt-z", "evt-a", "evt-y", "evt-b")

    def append_memory_event(self, user_id: str, **kwargs: Any) -> _Event:
        before = len(self.events)
        event = super().append_memory_event(user_id, **kwargs)
        if len(self.events) > before:
            event.event_id = self._ids[before]
        return event


@pytest.fixture(autouse=True)
def signed_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUBAN_REVIEW_MODULE_ENABLED", "1")
    monkeypatch.setenv("LUBAN_LIGHT_PRACTICE_ENABLED", "1")
    # These cases model the legacy / compiled_html dispatch (faked signed_variant
    # supply). Pin is_compiled_practice_pack=False so the kind-aware dispatch takes
    # the retest_supply_identity path bit-for-bit (variant-probe cases patch it True).
    monkeypatch.setattr(module, "is_compiled_practice_pack", lambda pack_id: False)
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
    monkeypatch.setattr(module, "resolve_retest_items", lambda *args, **kwargs: list(items))
    monkeypatch.setattr(
        module,
        "retest_supply_identity",
        lambda *args, **kwargs: {"kind": "signed_variant", "digest": "f" * 64},
    )
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
            supply_kind="signed_variant",
            supply_digest="f" * 64,
            probe_id=str(payload.get("probe_id") or ""),
            cycle_anchor="cycle-f16-v1" if canonical_mode == "review" else "",
        )
    return service.complete(**payload)


def _service(learner: _LearnerState) -> RetestWritebackService:
    return RetestWritebackService(
        learner_state_service=learner,
        review_probe_resolver=lambda **_kwargs: {
            "due": True,
            "cycle_anchor": "cycle-f16-v1",
        },
        training_intent_validator=lambda **_kwargs: True,
    )


def test_forward_practice_is_server_rescored_idempotent_and_short_term() -> None:
    learner = _LearnerState()
    service = _service(learner)

    first = _complete(service, answers=_answers(first=True, second=True))
    replay = _complete(service, answers=_answers(first=True, second=True))

    assert first == replay
    assert first["score"] == {"correct_count": 1, "question_count": 2}
    assert len(learner.events) == 5
    assert all(
        event.payload_json.get("event_type") != "retest_completion_claim"
        for event in _learning_evidence_events(learner.events)
    )
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

    assert len(learner.events) == 5


def test_completed_request_replays_after_supply_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learner = _LearnerState()
    service = _service(learner)
    first = _complete(service, answers=_answers(first=True, second=True))
    monkeypatch.setattr(
        module,
        "retest_supply_identity",
        lambda *args, **kwargs: {"kind": "signed_variant", "digest": "0" * 64},
    )

    assert _complete(service, answers=_answers(first=True, second=True)) == first


def test_noncanonical_terminal_cannot_be_replayed_or_seed_station() -> None:
    learner = _LearnerState()
    service = _service(learner)
    answers = _answers(first=True)
    selection_id = issue_retest_selection(
        user_id="qa_eval_first_run_loop",
        pack_id="F16",
        day_index=2026192,
        mode="forward",
        variant_ids=[item["variant_id"] for item in answers],
        supply_kind="signed_variant",
        supply_digest="f" * 64,
    )
    normalized_answers = module._normalize_answers(answers)
    request_hash = module._request_hash(
        {
            "completion_id": "forged-completion",
            "pack_id": "F16",
            "mode": "forward",
            "day_index": 2026192,
            "selection_id": selection_id,
            "answers": normalized_answers,
            "training_intent_id": "lti_first_run_f16",
            "probe_id": "",
        }
    )
    learner.append_memory_event(
        "qa_eval_first_run_loop",
        source_feature="client_import",
        source_id="forged-completion:terminal",
        memory_kind="learning_evidence",
        payload_json={
            "event_type": "learning_evidence",
            "evidence_source": "assessment_testset",
            "retest_completion_id": "forged-completion",
            "completion_terminal": True,
            "request_hash": request_hash,
            "practice_mode": "forward",
            "pack_id": "F16",
            "target_pack_id": "F16",
            "score_awarded": 99,
            "max_score": 99,
            "claim_promotion_allowed": False,
            "learning_change": {"status": "practice_recorded"},
            "quality": {"authority": "client_claimed_complete"},
        },
        dedupe_key="forged-terminal",
    )

    with pytest.raises(RetestIdempotencyConflict):
        _complete(
            service,
            completion_id="forged-completion",
            answers=answers,
            selection_id=selection_id,
        )

    assert len(learner.events) == 1
    assert not any(
        event.payload_json.get("learning_signal_type") == "station_completed"
        for event in learner.events
    )


def test_replay_item_order_is_question_order_not_event_uuid_order() -> None:
    learner = _NonLexicalEventIdLearnerState()
    service = _service(learner)

    first = _complete(service, answers=_answers(first=True, second=True))
    replay = _complete(service, answers=_answers(first=True, second=True))

    assert replay == first
    assert [item["variant_id"] for item in replay["items"]] == ["F16-v1", "F16-v2"]


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


def test_review_due_revalidation_uses_same_member_exam_horizon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def _projection(**kwargs):
        captured.update(kwargs)
        return {
            "due": [
                {
                    "pack_id": "F16",
                    "probe_id": "probe-f16",
                    "cycle_anchor": "cycle-f16-v1",
                    "retest_available": True,
                }
            ]
        }

    monkeypatch.setattr(module, "build_review_due_projection", _projection)
    service = RetestWritebackService(
        learner_state_service=_LearnerState(),
        review_exam_date_resolver=lambda _user_id: "2026-09-19",
    )

    due = service._require_due_probe(
        user_id="qa_eval_first_run_loop",
        pack_id="F16",
        probe_id="probe-f16",
    )

    assert due["cycle_anchor"] == "cycle-f16-v1"
    assert captured["exam_date_iso"] == "2026-09-19"


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
    assert any(event.payload_json.get("event_type") == "retest_completion_claim" for event in learner.events)
    assert not any(event.payload_json.get("completion_terminal") for event in learner.events)
    assert not any(event.payload_json.get("learning_signal_type") == "station_completed" for event in learner.events)
    partial_projection = synthesize_learning_truth(learner.events)
    assert partial_projection["weak_points"] == []
    assert partial_projection["improvement_signals"] == []
    assert partial_projection["typed_graph"]["edges"] == []

    result = _complete(service, completion_id="partial-completion")

    assert result["sync_status"] == "synced"
    assert sum(bool(event.payload_json.get("completion_terminal")) for event in learner.events) == 1
    assert sum(event.payload_json.get("learning_signal_type") == "station_completed" for event in learner.events) == 1


def test_partial_completion_claim_rejects_a_different_retry_request() -> None:
    learner = _LearnerState(fail_on_append_call=3)
    service = _service(learner)

    with pytest.raises(RuntimeError, match="synthetic_terminal_failure"):
        _complete(
            service,
            completion_id="partial-conflict",
            answers=_answers(first=True, second=True),
        )

    with pytest.raises(RetestIdempotencyConflict):
        _complete(
            service,
            completion_id="partial-conflict",
            answers=_answers(first=False, second=True),
        )

    assert not any(event.payload_json.get("completion_terminal") for event in learner.events)


def test_replay_reads_only_terminal_item_refs() -> None:
    learner = _LearnerState()
    service = _service(learner)
    first = _complete(service, completion_id="closed-replay")
    terminal = next(event for event in learner.events if event.payload_json.get("completion_terminal"))
    learner.append_memory_event(
        "qa_eval_first_run_loop",
        source_feature="assessment_testset",
        source_id="closed-replay:orphan",
        memory_kind="learning_evidence",
        payload_json={
            "event_type": "learning_evidence",
            "retest_completion_id": "closed-replay",
            "request_hash": terminal.payload_json["request_hash"],
            "question_id": "orphan-from-interrupted-request",
            "answer_type": "boolean",
            "is_correct": False,
        },
        dedupe_key="synthetic-orphan",
    )

    assert _complete(service, completion_id="closed-replay") == first


def test_learner_truth_reads_only_terminal_item_refs() -> None:
    learner = _LearnerState()
    service = _service(learner)
    _complete(
        service,
        completion_id="closed-learning-truth",
        mode="review",
        probe_id="probe-f16",
        answers=_answers(first=False, second=True),
    )
    terminal = next(
        event for event in learner.events if event.payload_json.get("completion_terminal")
    )
    item = next(
        event
        for event in learner.events
        if event.source_feature == "assessment_testset"
        and not event.payload_json.get("completion_terminal")
    )
    orphan_payload = dict(item.payload_json)
    orphan_payload.update(
        {
            "question_id": "orphan-not-in-terminal-refs",
            "source_question_id": "orphan-not-in-terminal-refs",
            "is_correct": False,
            "error_codes": ["unknown_error"],
            "error_events": [
                {
                    "error_code": "unknown_error",
                    "concept_tag": "pack:F16:rule:orphan",
                    "diagnosis": "synthetic orphan must not become learner truth",
                }
            ],
            "next_training_signal": {
                "concept": "pack:F16:rule:orphan",
                "concept_label": "orphan",
                "error_code": "unknown_error",
                "target_error_code": "unknown_error",
            },
        }
    )
    orphan = learner.append_memory_event(
        "qa_eval_first_run_loop",
        source_feature="assessment_testset",
        source_id="closed-learning-truth:orphan",
        memory_kind="learning_evidence",
        payload_json=orphan_payload,
        dedupe_key="synthetic-orphan-not-in-terminal-refs",
    )

    projection = synthesize_learning_truth(learner.events)

    assert projection["weak_points"] == []
    assert all(
        edge.get("evidence_event_id") != orphan.event_id
        for edge in projection["typed_graph"]["edges"]
    )
    assert orphan.event_id not in terminal.payload_json["item_event_refs"]


@pytest.mark.parametrize("invalid_max_score", [float("nan"), float("inf")])
def test_non_finite_terminal_score_fails_closed_without_projection_crash(
    invalid_max_score,
) -> None:
    learner = _LearnerState()
    service = _service(learner)
    _complete(
        service,
        completion_id="invalid-terminal-score",
        mode="review",
        probe_id="probe-f16",
        answers=_answers(first=True),
    )
    terminal = next(
        event for event in learner.events if event.payload_json.get("completion_terminal")
    )
    terminal.payload_json["max_score"] = invalid_max_score

    projection = synthesize_learning_truth(learner.events)

    assert projection["weak_points"] == []
    assert projection["typed_graph"]["edges"] == []


@pytest.mark.parametrize(
    ("field", "malformed_value"),
    [
        ("score_awarded", "broken"),
        ("score_awarded", True),
        ("is_correct", "false"),
    ],
)
def test_malformed_item_scoring_fields_fail_closed(
    field,
    malformed_value,
) -> None:
    learner = _LearnerState()
    service = _service(learner)
    _complete(
        service,
        completion_id="invalid-item-score",
        mode="review",
        probe_id="probe-f16",
        answers=_answers(first=True),
    )
    item = next(
        event
        for event in learner.events
        if event.source_feature == "assessment_testset"
        and not event.payload_json.get("completion_terminal")
    )
    item.payload_json[field] = malformed_value

    projection = synthesize_learning_truth(learner.events)

    assert projection["weak_points"] == []
    assert projection["typed_graph"]["edges"] == []


def test_review_replay_succeeds_after_original_probe_is_no_longer_due() -> None:
    learner = _LearnerState()
    probe_calls = []

    def _probe(**_kwargs):
        probe_calls.append(True)
        return {"due": True, "cycle_anchor": "cycle-f16-v1"} if len(probe_calls) == 1 else None

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
    learner = _LearnerState(fail_on_append_call=5)
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


def test_signed_selection_identity_ignores_client_day_tampering() -> None:
    learner = _LearnerState()
    service = _service(learner)
    token = issue_retest_selection(
        user_id="qa_eval_first_run_loop",
        pack_id="F16",
        day_index=2026192,
        mode="forward",
        variant_ids=["F16-v1", "F16-v2"],
        supply_kind="signed_variant",
        supply_digest="f" * 64,
    )

    result = _complete(service, day_index=2026193, selection_id=token)

    terminal = next(
        event for event in learner.events if event.payload_json.get("completion_terminal")
    )
    assert result["sync_status"] == "synced"
    assert terminal.payload_json["day_index"] == 2026192


def test_two_service_instances_close_same_probe_cycle_only_once() -> None:
    events: list[_Event] = []
    by_dedupe: dict[str, _Event] = {}
    claims: dict[tuple[str, str, str], dict[str, str]] = {}
    claim_lock = Lock()
    learner_a = _LearnerState(
        events=events,
        by_dedupe=by_dedupe,
        probe_claims=claims,
        probe_claim_lock=claim_lock,
    )
    learner_b = _LearnerState(
        events=events,
        by_dedupe=by_dedupe,
        probe_claims=claims,
        probe_claim_lock=claim_lock,
    )

    winner = _complete(
        _service(learner_a),
        completion_id="device-a",
        mode="review",
        probe_id="probe-f16",
    )
    replay = _complete(
        _service(learner_b),
        completion_id="device-b",
        mode="review",
        probe_id="probe-f16",
    )

    terminals = [event for event in events if event.payload_json.get("completion_terminal")]
    assert len(terminals) == 1
    assert winner == replay
    assert replay["completion_id"] == "device-a"


def test_probe_replay_bypasses_stale_general_event_cache_for_winner_terminal() -> None:
    events: list[_Event] = []
    by_dedupe: dict[str, _Event] = {}
    claims: dict[tuple[str, str, str], dict[str, str]] = {}
    claim_lock = Lock()
    learner_a = _LearnerState(
        events=events,
        by_dedupe=by_dedupe,
        probe_claims=claims,
        probe_claim_lock=claim_lock,
    )
    learner_b = _LearnerState(
        events=events,
        by_dedupe=by_dedupe,
        probe_claims=claims,
        probe_claim_lock=claim_lock,
    )
    winner = _complete(
        _service(learner_a),
        completion_id="device-a",
        mode="review",
        probe_id="probe-f16",
    )
    learner_b.list_memory_events = lambda *_args, **_kwargs: []  # type: ignore[method-assign]

    replay = _complete(
        _service(learner_b),
        completion_id="device-b",
        mode="review",
        probe_id="probe-f16",
    )

    assert replay == winner
    assert sum(bool(event.payload_json.get("completion_terminal")) for event in events) == 1


def test_probe_claim_owner_can_resume_after_crash_but_other_completion_cannot_steal() -> None:
    learner = _LearnerState(fail_on_append_call=1)
    service = _service(learner)

    with pytest.raises(RuntimeError, match="synthetic_terminal_failure"):
        _complete(
            service,
            completion_id="owner-device",
            mode="review",
            probe_id="probe-f16",
        )
    assert learner.events == []

    with pytest.raises(RetestCompletionInProgress, match="owner-device"):
        _complete(
            service,
            completion_id="other-device",
            mode="review",
            probe_id="probe-f16",
        )
    assert learner.events == []

    resumed = _complete(
        service,
        completion_id="owner-device",
        mode="review",
        probe_id="probe-f16",
    )

    assert resumed["completion_id"] == "owner-device"
    assert sum(bool(event.payload_json.get("completion_terminal")) for event in learner.events) == 1


def test_same_probe_cycle_with_different_answers_conflicts_before_second_write() -> None:
    learner = _LearnerState()
    first_service = _service(learner)
    second_service = _service(learner)
    _complete(
        first_service,
        completion_id="device-a",
        mode="review",
        probe_id="probe-f16",
        answers=_answers(first=True, second=True),
    )

    with pytest.raises(RetestIdempotencyConflict):
        _complete(
            second_service,
            completion_id="device-b",
            mode="review",
            probe_id="probe-f16",
            answers=_answers(first=False, second=True),
        )

    assert sum(bool(event.payload_json.get("completion_terminal")) for event in learner.events) == 1


def test_review_fails_closed_without_atomic_probe_authority_before_any_write() -> None:
    learner = _LearnerState(claim_available=False)

    with pytest.raises(RetestProbeClaimUnavailable, match="retest_probe_atomic_authority_unavailable"):
        _complete(
            _service(learner),
            completion_id="review-no-authority",
            mode="review",
            probe_id="probe-f16",
        )

    assert learner.events == []


def test_v3_review_terminal_closure_rejects_item_from_another_probe_cycle() -> None:
    learner = _LearnerState()
    _complete(
        _service(learner),
        completion_id="cycle-bound",
        mode="review",
        probe_id="probe-f16",
    )
    terminal = next(
        event for event in learner.events if event.payload_json.get("completion_terminal")
    )
    item = next(
        event
        for event in learner.events
        if event.source_feature == "assessment_testset"
        and event.payload_json.get("completion_terminal") is not True
    )
    item.payload_json["cycle_anchor"] = "forged-cycle"

    assert canonical_retest_item_events(learner.events, terminal=terminal) is None


def test_forward_compiled_html_mcq_is_server_rescored_and_written_as_l0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [
        {
            "answer_type": "single_choice",
            "variant_id": "F16-html-q1-a",
            "rule_group": "分档·条件维",
            "stem": "怎样分档？",
            "model_answer": "按100mm分档。",
            "anchor": "compiled_html:f16/practice.html#Q1",
            "source_html_sha256": "html-sha",
            "options": [
                {"option_id": "q1:a", "text": "正确", "is_correct": True, "fix": "分档"},
                {
                    "option_id": "q1:b", "text": "错误", "is_correct": False,
                    "source_error_code": "E10", "temptation": "一刀切",
                    "loss_reason": "没有分档", "fix": "按100mm分档",
                },
            ],
        },
        {
            "answer_type": "single_choice",
            "variant_id": "F16-html-q2-b",
            "rule_group": "割补工序·程序维",
            "stem": "完整工序？",
            "model_answer": "八环工序。",
            "anchor": "compiled_html:f16/practice.html#Q2",
            "source_html_sha256": "html-sha",
            "options": [
                {"option_id": "q2:a", "text": "正确", "is_correct": True, "fix": "八环"},
                {"option_id": "q2:b", "text": "错误", "is_correct": False, "fix": "补齐"},
            ],
        },
    ]
    monkeypatch.setattr(module, "resolve_retest_items", lambda *args, **kwargs: items)
    monkeypatch.setattr(
        module,
        "build_lesson_viewmodel",
        lambda pack_id: {
            "pack_id": pack_id,
            "title": "屋面防水起鼓割补",
            "content_sha256": "pack-sha",
        },
    )
    learner = _LearnerState()
    answers = [
        {
            "variant_id": "F16-html-q1-a",
            "selected_option_id": "q1:b",
            "is_correct": True,
            "score": 1,
        },
        {"variant_id": "F16-html-q2-b", "selected_option_id": "q2:a"},
    ]

    result = _complete(_service(learner), answers=answers, training_intent_id="")
    replay = _complete(_service(learner), answers=answers, training_intent_id="")

    assert result == replay
    assert result["score"] == {"correct_count": 1, "question_count": 2}
    assert result["learning_change"]["reason"] == "compiled_html_server_rescore"
    assert result["items"][0]["correct_option_id"]
    item_events = [
        event for event in learner.events
        if event.source_feature == "assessment_testset"
        and not event.payload_json.get("completion_terminal")
    ]
    wrong = next(event for event in item_events if not event.payload_json["is_correct"])
    assert wrong.payload_json["learner_answer"] == "q1:b"
    assert wrong.payload_json["correct_answer"] == "q1:a"
    assert wrong.payload_json["source_error_code"] == "E10"
    assert wrong.payload_json["error_codes"] == ["unknown_error"]
    assert wrong.payload_json["quality"]["authority"] == "compiled_html_server_rescore"
    assert wrong.payload_json["claim_promotion_allowed"] is False
    terminal = next(event for event in learner.events if event.payload_json.get("completion_terminal"))
    assert terminal.payload_json["quality"]["authority"] == "compiled_html_server_rescore"
    assert terminal.payload_json["claim_promotion_allowed"] is False
    assert terminal.payload_json["quality"]["progress_countable"] is False

    lifecycle = project_pack_lifecycle(events=learner.events, claims=[], pack_ids=["F16"])
    assert lifecycle["packs"]["F16"]["lifecycle_state"] == "practiced"
    assert lifecycle["packs"]["F16"]["practice_event_count"] == len(items)
    assert lifecycle["packs"]["F16"]["last_completion_at"] == terminal.created_at
    assert lifecycle["packs"]["F16"]["terminal_evidence_refs"] == [terminal.event_id]
    assert lifecycle["unassigned_practice"] == []

    evidence = [
        event
        for event in learner.events
        if event.source_feature == "assessment_testset"
    ]
    progress = _aggregate_learning_evidence(evidence)
    assert progress["attempt_count"] == len(items)
    assert progress["unique_question_count"] == len(items)


def test_due_review_accepts_only_server_rescored_compiled_canonical_supply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = {
        "answer_type": "single_choice",
        "variant_id": "F16-html-review-q1",
        "rule_group": "分档·条件维",
        "stem": "怎样分档？",
        "model_answer": "按100mm分档。",
        "anchor": "compiled_html:f16/practice.html#Q1",
        "source_html_sha256": "html-sha",
        "options": [
            {"option_id": "q1:a", "text": "正确", "is_correct": True},
            {"option_id": "q1:b", "text": "错误", "is_correct": False},
        ],
    }
    monkeypatch.setattr(module, "resolve_retest_items", lambda *args, **kwargs: [item])
    learner = _LearnerState()

    result = _complete(
        _service(learner),
        completion_id="compiled-review",
        mode="review",
        probe_id="probe-f16",
        answers=[
            {
                "variant_id": "F16-html-review-q1",
                "selected_option_id": "q1:a",
            }
        ],
    )

    terminal = next(
        event for event in learner.events if event.payload_json.get("completion_terminal")
    )
    assert result["learning_change"]["reason"] == "compiled_html_server_rescore"
    assert terminal.payload_json["quality"]["evidence_level"] == "L2_real_retest"
    assert canonical_retest_item_events(learner.events, terminal=terminal) is not None


def test_non_f16_unreviewed_compiled_surface_fails_closed_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.services.luban_lesson.practice_html import (
        load_compiled_practice as real_load_compiled_practice,
    )
    from deeptutor.services.luban_lesson.read_model import (
        build_lesson_viewmodel as real_build_lesson_viewmodel,
    )
    from deeptutor.services.luban_lesson.read_model import (
        resolve_retest_items as real_resolve_retest_items,
    )

    monkeypatch.setattr(module, "resolve_retest_items", real_resolve_retest_items)
    monkeypatch.setattr(module, "build_lesson_viewmodel", real_build_lesson_viewmodel)
    authority = real_load_compiled_practice("S05")
    assert authority is not None
    wanted = set(authority["surfaces"][0]["variant_ids"])
    items = [item for item in authority["items"] if item["variant_id"] in wanted]
    answers = [
        {
            "variant_id": item["variant_id"],
            "selected_option_id": item["options"][0]["option_id"],
        }
        for item in items
    ]
    learner = _LearnerState()

    with pytest.raises(ValueError, match="retest_answer_set_mismatch"):
        _complete(
            _service(learner),
            pack_id="S05",
            answers=answers,
            training_intent_id="",
        )

    assert learner.events == []


def test_forward_compiled_html_rejects_unknown_option_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = {
        "answer_type": "single_choice",
        "variant_id": "F16-html-q1-a",
        "rule_group": "分档",
        "stem": "题",
        "model_answer": "答",
        "anchor": "compiled_html:f16#Q1",
        "source_html_sha256": "html-sha",
        "options": [
            {"option_id": "q1:a", "text": "A", "is_correct": True},
            {"option_id": "q1:b", "text": "B", "is_correct": False},
        ],
    }
    monkeypatch.setattr(module, "resolve_retest_items", lambda *args, **kwargs: [item])
    monkeypatch.setattr(
        module,
        "build_lesson_viewmodel",
        lambda pack_id: {"title": "F16", "content_sha256": "pack-sha"},
    )
    learner = _LearnerState()

    with pytest.raises(ValueError, match="retest_selected_option_invalid"):
        _complete(
            _service(learner),
            answers=[{"variant_id": item["variant_id"], "selected_option_id": "q1:forged"}],
            training_intent_id="",
        )

    assert learner.events == []


# ---------------------------------------- signed_variant-on-compiled 变体探针消费（切片二）

_PROBE_DIGEST = "ab" * 32


def _probe_rows() -> list[dict[str, Any]]:
    return [
        {
            "variant_id": "S05-A-ic-000",
            "rule_group": "A-send",
            "surface": "送电顺序：总配电箱→分配电箱→开关箱",
            "expected_ok": True,
            "correct_statement": "送电顺序应为总配电箱→分配电箱→开关箱",
            "anchor": "kc:s05:1",
            "fact_id": "s05-fact-send-order",
            "skeleton_id": "skel-a1",
            "probe_role": "immediate_confirm",
            "temptation": "送电与停电顺序容易记反。",
            "loss_reason": "顺序判错阅卷零分。",
        },
        {
            "variant_id": "S05-A-ic-001",
            "rule_group": "A-send",
            "surface": "送电顺序：总配电箱→开关箱→分配电箱",
            "expected_ok": False,
            "correct_statement": "送电顺序应为总配电箱→分配电箱→开关箱",
            "anchor": "kc:s05:1",
            "fact_id": "s05-fact-send-order",
            "skeleton_id": "skel-a2",
            "probe_role": "immediate_confirm",
            "temptation": "把开关箱提前了。",
            "loss_reason": "违反送电总→分→开关顺序。",
        },
    ]


def _pin_variant_probe(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rows: list[dict[str, Any]] | None,
    digest: str = _PROBE_DIGEST,
    identity_digest: str | None = None,
) -> None:
    monkeypatch.setattr(module, "is_compiled_practice_pack", lambda pack_id: True)
    monkeypatch.setattr(
        module,
        "variant_probe_supply_identity",
        lambda *a, **k: {"kind": "signed_variant", "digest": identity_digest or digest},
    )
    monkeypatch.setattr(
        module,
        "resolve_variant_probe_items",
        lambda *a, **k: (list(rows) if rows is not None else None),
    )
    monkeypatch.setattr(
        module,
        "build_lesson_viewmodel",
        lambda pack_id: {"pack_id": pack_id, "title": "S05 送电停电顺序"},
    )


def _probe_answers(*, first: bool, second: bool) -> list[dict[str, Any]]:
    return [
        {"variant_id": "S05-A-ic-000", "choice_ok": first},
        {"variant_id": "S05-A-ic-001", "choice_ok": second},
    ]


def _complete_probe(
    service: RetestWritebackService, *, mode: str, answers: list[dict[str, Any]], **over: Any
) -> dict[str, Any]:
    canonical_mode = "review" if over.get("probe_id") else mode
    token = issue_retest_selection(
        user_id="qa_eval_first_run_loop",
        pack_id="S05",
        day_index=2026192,
        mode=canonical_mode,
        variant_ids=[a["variant_id"] for a in answers],
        supply_kind="signed_variant",
        supply_digest=_PROBE_DIGEST,
        probe_id=str(over.get("probe_id") or ""),
        cycle_anchor="cycle-s05-v1" if canonical_mode == "review" else "",
    )
    payload = {
        "user_id": "qa_eval_first_run_loop",
        "completion_id": over.get("completion_id", "probe-completion-1"),
        "pack_id": "S05",
        "mode": mode,
        "day_index": 2026192,
        "answers": answers,
        "training_intent_id": over.get("training_intent_id", ""),
        "probe_id": str(over.get("probe_id") or ""),
        "selection_id": token,
    }
    return service.complete(**payload)


def _probe_service(learner: _LearnerState) -> RetestWritebackService:
    return RetestWritebackService(
        learner_state_service=learner,
        review_probe_resolver=lambda **_kwargs: {
            "due": True,
            "cycle_anchor": "cycle-s05-v1",
        },
        training_intent_validator=lambda **_kwargs: True,
    )


def test_variant_probe_forward_completes_full_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pin_variant_probe(monkeypatch, rows=_probe_rows())
    learner = _LearnerState()
    result = _complete_probe(
        _probe_service(learner), mode="forward", answers=_probe_answers(first=True, second=False)
    )
    assert result["score"] == {"correct_count": 2, "question_count": 2}
    assert result["learning_change"]["reason"] == "signed_variant_server_rescore"
    # public_item 带错后诊断文案（无 fix，不造）。
    pub = {item["variant_id"]: item for item in result["items"]}
    assert pub["S05-A-ic-000"]["feedback"] == {
        "correct_statement": "送电顺序应为总配电箱→分配电箱→开关箱",
        "temptation": "送电与停电顺序容易记反。",
        "loss_reason": "顺序判错阅卷零分。",
    }
    assert "fix" not in pub["S05-A-ic-000"]["feedback"]
    # item event 带 fact/probe_role 溯源；boolean 判分权威。
    item_events = [
        e
        for e in learner.events
        if e.source_feature == "assessment_testset"
        and not e.payload_json.get("completion_terminal")
    ]
    assert all(e.payload_json["probe_role"] == "immediate_confirm" for e in item_events)
    assert all(e.payload_json["fact_id"] == "s05-fact-send-order" for e in item_events)
    assert all(
        e.payload_json["quality"]["authority"] == "signed_variant_server_rescore"
        for e in item_events
    )
    assert all(e.payload_json["claim_promotion_allowed"] is False for e in item_events)


def test_variant_probe_supply_drift_rejects_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 供给 identity 漂移（digest 变）→ selection 失配 → fail-closed 不写。
    _pin_variant_probe(monkeypatch, rows=_probe_rows(), identity_digest="cd" * 32)
    learner = _LearnerState()
    with pytest.raises(ValueError, match="retest_selection_invalid"):
        _complete_probe(
            _probe_service(learner), mode="forward", answers=_probe_answers(first=True, second=False)
        )
    assert learner.events == []


def test_variant_probe_revoked_after_signing_fails_answer_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # identity 未变（token 有效）但 canonical 解析 None（撤发/不再 eligible）
    # → answer_set_mismatch（fail-closed）。
    _pin_variant_probe(monkeypatch, rows=None)
    learner = _LearnerState()
    with pytest.raises(ValueError, match="retest_answer_set_mismatch"):
        _complete_probe(
            _probe_service(learner), mode="forward", answers=_probe_answers(first=True, second=False)
        )
    assert learner.events == []


def test_variant_probe_review_d1_promotes_l2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [dict(row, probe_role="d1_probe") for row in _probe_rows()]
    _pin_variant_probe(monkeypatch, rows=rows)
    learner = _LearnerState()
    result = _complete_probe(
        _probe_service(learner),
        mode="review",
        probe_id="probe-s05",
        answers=_probe_answers(first=True, second=False),
    )
    terminal = next(
        e for e in learner.events if e.payload_json.get("completion_terminal")
    )
    assert terminal.payload_json["quality"]["evidence_level"] == "L2_real_retest"
    assert terminal.payload_json["prescription_result"]["status"] == "verified"
    assert terminal.payload_json["quality"]["authority"] == "signed_variant_server_rescore"
    assert result["learning_change"]["status"] == "verification_passed"
