from __future__ import annotations

import pytest

from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
from deeptutor.services.learner_state.mistake_book import (
    InMemoryMistakeBookStore,
    MistakeBookConflict,
    MistakeBookService,
)


def test_save_remove_and_list_mistake_book_item() -> None:
    service = MistakeBookService(store=InMemoryMistakeBookStore())
    attempt_ref = sign_attempt_ref(user_id="u1", event_id="evt1", question_id="q1")

    saved = service.save_item(
        user_id="u1",
        attempt_ref=attempt_ref,
        subject_id="construction_exam_1",
        title="题1",
    )
    assert saved["is_bookmarked"] is True
    assert saved["event_id"] == "evt1"
    assert service.list_items(user_id="u1")["count"] == 1

    removed = service.remove_item(user_id="u1", attempt_ref=attempt_ref, if_match=saved["etag"])
    assert removed["is_bookmarked"] is False
    assert service.list_items(user_id="u1")["count"] == 0


def test_mistake_book_isolates_subject_and_bot() -> None:
    service = MistakeBookService(store=InMemoryMistakeBookStore())

    ref_a = sign_attempt_ref(user_id="u1", event_id="evt-a", question_id="q-a")
    ref_b = sign_attempt_ref(user_id="u1", event_id="evt-b", question_id="q-b")
    service.save_item(user_id="u1", attempt_ref=ref_a, subject_id="construction_exam_1", bot_id="bot-a")
    service.save_item(user_id="u1", attempt_ref=ref_b, subject_id="construction_exam_2", bot_id="bot-b")

    assert service.list_items(user_id="u1")["count"] == 2
    subject_a = service.list_items(user_id="u1", subject_id="construction_exam_1")
    assert subject_a["count"] == 1
    assert subject_a["items"][0]["bot_id"] == "bot-a"


def test_mistake_book_mastered_and_review_updates_are_filtered_by_default() -> None:
    service = MistakeBookService(store=InMemoryMistakeBookStore())
    attempt_ref = sign_attempt_ref(user_id="u1", event_id="evt1", question_id="q1")

    saved = service.save_item(user_id="u1", attempt_ref=attempt_ref, subject_id="construction_exam_1")
    reviewed = service.record_review(user_id="u1", attempt_ref=attempt_ref, if_match=saved["etag"])
    assert reviewed["last_reviewed_at"]
    assert reviewed["review_due_at"]

    mastered = service.mark_mastered(user_id="u1", attempt_ref=attempt_ref, if_match=reviewed["etag"])
    assert mastered["mastered_at"]
    assert service.list_items(user_id="u1")["count"] == 0
    assert service.list_items(user_id="u1", include_mastered=True)["count"] == 1


def test_mistake_book_stale_etag_raises_conflict() -> None:
    service = MistakeBookService(store=InMemoryMistakeBookStore())
    attempt_ref = sign_attempt_ref(user_id="u1", event_id="evt1", question_id="q1")
    service.save_item(user_id="u1", attempt_ref=attempt_ref, subject_id="construction_exam_1")

    with pytest.raises(MistakeBookConflict) as exc:
        service.remove_item(user_id="u1", attempt_ref=attempt_ref, if_match="stale")

    assert exc.value.latest["is_bookmarked"] is True


def test_mistake_book_rejects_missing_subject_id() -> None:
    service = MistakeBookService(store=InMemoryMistakeBookStore())
    attempt_ref = sign_attempt_ref(user_id="u1", event_id="evt1", question_id="q1")

    with pytest.raises(ValueError):
        service.save_item(user_id="u1", attempt_ref=attempt_ref, subject_id="")
