from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from deeptutor.services.assessment.session_repository import (
    AssessmentLeaseConflict,
    AssessmentSessionConflict,
    AssessmentSessionExpired,
    AssessmentSessionNotFound,
    InMemoryAssessmentSessionRepository,
    SupabaseAssessmentSessionRepository,
)


TZ = timezone.utc


def _now() -> datetime:
    return datetime(2026, 5, 24, 12, 0, tzinfo=TZ)


def _repo() -> InMemoryAssessmentSessionRepository:
    return InMemoryAssessmentSessionRepository(now_fn=_now)


def _create(repo: InMemoryAssessmentSessionRepository, *, user_id: str = "u1", device_id: str = "d1") -> dict:
    return repo.create_session(
        user_id=user_id,
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        client_questions_public=[{"question_id": "q1", "question_stem": "防水题", "options": [{"key": "A"}]}],
        session_questions_private=[{"question_id": "q1", "answer": "A"}],
        device_id=device_id,
        trace_id="trace_1",
    )


def test_session_repository_stores_private_and_public_artifacts_separately() -> None:
    session = _create(_repo())

    assert "answer" not in session["client_questions_public"][0]
    assert session["session_questions_private"][0]["answer"] == "A"
    assert session["status"] == "in_progress"
    assert session["schema_version"] == "assessment_session_v1"


def test_resume_returns_redacted_public_payload() -> None:
    repo = _repo()
    session = _create(repo)

    resume = repo.get_session_for_resume("u1", session["quiz_id"], device_id="d1")

    assert resume["quiz_id"] == session["quiz_id"]
    assert "session_questions_private" not in resume
    assert "answer" not in str(resume["questions"]).lower()


def test_duplicate_submit_returns_existing_result() -> None:
    repo = _repo()
    session = _create(repo)
    submitted = repo.mark_submitted_once(
        "u1",
        session["quiz_id"],
        submitted_answer_snapshot={"q1": "A"},
        result_report_json={"schema_version": "p0a-v1", "score_summary": {"score_pct": 100}},
        device_id="d1",
    )

    retry = repo.mark_submitted_once(
        "u1",
        session["quiz_id"],
        submitted_answer_snapshot={"q1": "A"},
        result_report_json={"schema_version": "p0a-v1", "score_summary": {"score_pct": 0}},
        device_id="d1",
    )

    assert retry["result_report_json"] == submitted["result_report_json"]
    assert retry["submit_idempotency_key"] == submitted["submit_idempotency_key"]


def test_different_submit_body_with_same_quiz_id_returns_conflict() -> None:
    repo = _repo()
    session = _create(repo)
    repo.mark_submitted_once(
        "u1",
        session["quiz_id"],
        submitted_answer_snapshot={"q1": "A"},
        result_report_json={"schema_version": "p0a-v1"},
        device_id="d1",
    )

    with pytest.raises(AssessmentSessionConflict):
        repo.mark_submitted_once(
            "u1",
            session["quiz_id"],
            submitted_answer_snapshot={"q1": "B"},
            result_report_json={"schema_version": "p0a-v1"},
            device_id="d1",
        )


def test_device_lease_blocks_conflicting_writer() -> None:
    repo = _repo()
    session = _create(repo)

    with pytest.raises(AssessmentLeaseConflict):
        repo.mark_submitted_once(
            "u1",
            session["quiz_id"],
            submitted_answer_snapshot={"q1": "A"},
            result_report_json={"schema_version": "p0a-v1"},
            device_id="d2",
        )


def test_expired_in_progress_session_cannot_be_submitted() -> None:
    now = _now()
    repo = InMemoryAssessmentSessionRepository(now_fn=lambda: now)
    session = _create(repo)
    repo._now_fn = lambda: now + timedelta(hours=25)

    with pytest.raises(AssessmentSessionExpired):
        repo.mark_submitted_once(
            "u1",
            session["quiz_id"],
            submitted_answer_snapshot={"q1": "A"},
            result_report_json={"schema_version": "p0a-v1"},
            device_id="d1",
        )


def test_lease_renews_on_heartbeat_within_default_window() -> None:
    repo = _repo()
    session = _create(repo)
    before = session["lease_expires_at"]

    renewed = repo.renew_lease("u1", session["quiz_id"], device_id="d1", heartbeat_seconds=300)

    assert renewed["lease_expires_at"] >= before


def test_idle_lease_expires_after_30_minutes_and_second_device_can_claim() -> None:
    now = _now()
    repo = InMemoryAssessmentSessionRepository(now_fn=lambda: now)
    session = _create(repo)
    repo._now_fn = lambda: now + timedelta(minutes=31)

    claimed = repo.get_session_for_resume("u1", session["quiz_id"], device_id="d2")

    assert claimed["device_id"] == "d2"


def test_explicit_take_over_appends_to_lease_history_and_invalidates_old_device_writes() -> None:
    repo = _repo()
    session = _create(repo)

    taken = repo.take_over_lease("u1", session["quiz_id"], device_id="d2", reason="manual")

    assert taken["device_id"] == "d2"
    assert taken["lease_history"][-1]["device_id"] == "d2"
    with pytest.raises(AssessmentLeaseConflict):
        repo.renew_lease("u1", session["quiz_id"], device_id="d1")


def test_server_wins_draft_drops_client_value_for_existing_server_answer() -> None:
    repo = _repo()
    session = _create(repo)

    patched = repo.patch_draft_answers("u1", session["quiz_id"], {"q1": "B", "q2": "C"}, device_id="d1")

    assert patched["draft_answer_snapshot"] == {"q1": "B", "q2": "C"}
    patched_again = repo.patch_draft_answers("u1", session["quiz_id"], {"q1": "C"}, device_id="d1")
    assert patched_again["draft_answer_snapshot"]["q1"] == "B"


def test_server_draft_patch_does_not_promote_to_submitted_state() -> None:
    repo = _repo()
    session = _create(repo)

    patched = repo.patch_draft_answers("u1", session["quiz_id"], {"q1": "B"}, device_id="d1")

    assert patched["status"] == "in_progress"
    assert patched["submitted_answer_snapshot"] is None


def test_owner_check_blocks_user_a_from_reading_user_b_session_via_repository_layer() -> None:
    repo = _repo()
    session = _create(repo, user_id="u2")

    with pytest.raises(AssessmentSessionNotFound):
        repo.get_session_for_resume("u1", session["quiz_id"], device_id="d1")


def test_owner_check_blocks_cross_user_submit_attempt() -> None:
    repo = _repo()
    session = _create(repo, user_id="u2")

    with pytest.raises(AssessmentSessionNotFound):
        repo.mark_submitted_once(
            "u1",
            session["quiz_id"],
            submitted_answer_snapshot={"q1": "A"},
            result_report_json={"schema_version": "p0a-v1"},
            device_id="d1",
        )


def test_degraded_status_records_explicit_reason_and_is_recoverable_via_writeback_retry() -> None:
    repo = _repo()
    session = _create(repo)

    degraded = repo.record_degraded("u1", session["quiz_id"], reason="writeback_failed")
    assert degraded["status"] == "degraded"
    assert degraded["degraded_reason"] == "writeback_failed"

    recovered = repo.attach_writeback_refs(
        "u1",
        session["quiz_id"],
        learning_event_refs=[{"event_id": "evt1"}],
        mistake_book_refs=[],
        mark_scored=True,
    )
    assert recovered["status"] == "scored"
    assert recovered["degraded_reason"] is None


def test_supabase_submit_uses_atomic_unsubmitted_status_filter() -> None:
    calls: list[tuple[str, dict]] = []
    row = {
        "quiz_id": "quiz_atomic",
        "user_id": "u1",
        "assessment_type": "topic_diagnostic",
        "subject_id": "construction_exam",
        "topic_ids": ["waterproof"],
        "blueprint_version": "topic_waterproof_v1",
        "form_id": "topic_waterproof_v1_form_1",
        "status": "in_progress",
        "submitted_answer_snapshot": None,
        "submit_idempotency_key": None,
        "result_report_json": None,
        "session_questions_private": [{"question_id": "q1", "answer": "A"}],
        "client_questions_public": [{"question_id": "q1", "question_stem": "防水题"}],
        "device_id": "d1",
        "lease_expires_at": "2026-05-24T12:30:00Z",
        "expires_at": "2026-05-25T12:00:00Z",
    }

    class _Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def get(self, url, *, headers, params):
            calls.append(("get", dict(params)))
            return _Response([dict(row)])

        def patch(self, url, *, headers, params, json):
            calls.append(("patch", dict(params)))
            return _Response([{**row, **dict(json or {})}])

    repo = SupabaseAssessmentSessionRepository(
        base_url="https://supabase.example",
        service_key="service-role",
        client=_Client(),
        now_fn=_now,
    )

    repo.mark_submitted_once(
        "u1",
        "quiz_atomic",
        submitted_answer_snapshot={"q1": "A"},
        result_report_json={"schema_version": "p0a-v1"},
        device_id="d1",
    )

    patch_params = [params for name, params in calls if name == "patch"][0]
    assert patch_params["user_id"] == "eq.u1"
    assert patch_params["quiz_id"] == "eq.quiz_atomic"
    assert patch_params["status"] == "eq.in_progress"
    assert patch_params["submitted_answer_snapshot"] == "is.null"
    assert patch_params["expires_at"] == "gt.2026-05-24T12:00:00Z"


def test_supabase_create_reuses_active_session_after_insert_conflict() -> None:
    calls: list[tuple[str, dict]] = []
    row = {
        "quiz_id": "quiz_existing",
        "user_id": "u1",
        "assessment_type": "topic_diagnostic",
        "subject_id": "construction_exam",
        "topic_ids": ["waterproof"],
        "blueprint_version": "topic_waterproof_v1",
        "form_id": "topic_waterproof_v1_form_1",
        "status": "in_progress",
        "schema_version": "assessment_session_v1",
        "submitted_answer_snapshot": None,
        "result_report_json": None,
        "session_questions_private": [{"question_id": "q1", "answer": "A"}],
        "client_questions_public": [{"question_id": "q1", "question_stem": "防水题"}],
        "device_id": "d1",
        "lease_expires_at": "2026-05-24T12:30:00Z",
        "expires_at": "2026-05-25T12:00:00Z",
    }

    class _Response:
        def __init__(self, payload, *, status_code: int = 200):
            self._payload = payload
            self.status_code = status_code
            self.request = httpx.Request("POST", "https://supabase.example/rest/v1/assessment_sessions")

        def raise_for_status(self):
            if self.status_code >= 400:
                response = httpx.Response(self.status_code, request=self.request, json={"code": "23505"})
                raise httpx.HTTPStatusError("duplicate key", request=self.request, response=response)

        def json(self):
            return self._payload

    class _Client:
        def __init__(self):
            self.get_count = 0

        def get(self, url, *, headers, params):
            calls.append(("get", dict(params)))
            self.get_count += 1
            if self.get_count < 3:
                return _Response([])
            return _Response([dict(row)])

        def post(self, url, *, headers, json):
            calls.append(("post", {"url": url}))
            return _Response({"code": "23505"}, status_code=409)

    repo = SupabaseAssessmentSessionRepository(
        base_url="https://supabase.example",
        service_key="service-role",
        client=_Client(),
        now_fn=_now,
    )

    created = repo.create_session(
        user_id="u1",
        assessment_type="topic_diagnostic",
        subject_id="construction_exam",
        topic_ids=["waterproof"],
        blueprint_version="topic_waterproof_v1",
        form_id="topic_waterproof_v1_form_1",
        client_questions_public=[{"question_id": "q1", "question_stem": "防水题"}],
        session_questions_private=[{"question_id": "q1", "answer": "A"}],
        device_id="d1",
    )

    assert created["quiz_id"] == "quiz_existing"
    assert created["reuse_reason"] == "active_session_insert_conflict"
    assert [name for name, _params in calls].count("post") == 1
    assert [name for name, _params in calls].count("get") == 3


def test_supabase_transport_error_maps_to_assessment_session_error() -> None:
    class _Client:
        def get(self, url, *, headers, params):
            raise httpx.ConnectError("connect failed")

    repo = SupabaseAssessmentSessionRepository(
        base_url="https://supabase.example",
        service_key="service-role",
        client=_Client(),
        now_fn=_now,
    )

    with pytest.raises(Exception) as exc_info:
        repo.private_session("u1", "quiz_unavailable")

    assert exc_info.type.__name__ == "AssessmentSessionError"
    assert str(exc_info.value) == "assessment_sessions_unavailable"
