from __future__ import annotations

import pytest
import httpx

from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
from deeptutor.services.learner_state.mistake_book import (
    InMemoryMistakeBookStore,
    MistakeBookConflict,
    MistakeBookService,
    SupabaseMistakeBookStore,
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


def test_supabase_mistake_book_store_uses_user_event_authority_filters() -> None:
    requests: list[dict[str, object]] = []
    rows: dict[tuple[str, str], dict[str, object]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8") if request.content else ""
        requests.append({"method": request.method, "params": dict(request.url.params), "json": body})
        params = dict(request.url.params)
        if request.method == "POST":
            import json

            row = json.loads(body)[0]
            rows[(row["user_id"], row["event_id"])] = dict(row)
            return httpx.Response(200, json=[row], request=request)
        if request.method == "GET":
            user_id = str(params.get("user_id", "")).replace("eq.", "")
            event_id = str(params.get("event_id", "")).replace("eq.", "")
            found = [
                dict(row)
                for (row_user, row_event), row in rows.items()
                if row_user == user_id and (not event_id or row_event == event_id)
            ]
            return httpx.Response(200, json=found, request=request)
        if request.method == "PATCH":
            user_id = str(params.get("user_id", "")).replace("eq.", "")
            event_id = str(params.get("event_id", "")).replace("eq.", "")
            import json

            rows[(user_id, event_id)].update(json.loads(body))
            return httpx.Response(200, json=[rows[(user_id, event_id)]], request=request)
        return httpx.Response(400, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.supabase.co")
    store = SupabaseMistakeBookStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )
    saved = store.upsert_item({"user_id": "u1", "event_id": "evt1", "attempt_ref": "ref", "saved_at": "t"})
    assert saved["event_id"] == "evt1"
    assert store.get_item("u1", "evt1")["attempt_ref"] == "ref"
    store.update_item("u1", "evt1", {"archived_at": "done"})

    assert requests[0]["method"] == "POST"
    assert requests[0]["params"]["on_conflict"] == "user_id,event_id"
    assert requests[1]["method"] == "GET"
    assert requests[1]["params"]["user_id"] == "eq.u1"
    assert requests[1]["params"]["event_id"] == "eq.evt1"
    assert requests[2]["method"] == "PATCH"
    assert requests[2]["params"]["user_id"] == "eq.u1"
    assert requests[2]["params"]["event_id"] == "eq.evt1"
