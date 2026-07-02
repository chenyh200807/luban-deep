from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
from deeptutor.services.learner_state.mistake_book import (
    InMemoryMistakeBookStore,
    MistakeBookConflict,
    MistakeBookService,
    SupabaseMistakeBookStore,
)
from deeptutor.services.path_service import PathService


@pytest.fixture(autouse=True)
def _enable_mistake_book_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_ENABLED", "true")
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED", "true")


def test_mistake_book_service_flags_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MistakeBookService(store=InMemoryMistakeBookStore())
    attempt_ref = sign_attempt_ref(user_id="u1", event_id="evt1", question_id="q1")

    monkeypatch.delenv("DEEPTUTOR_MISTAKE_BOOK_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="mistake_book_disabled"):
        service.list_items(user_id="u1")

    monkeypatch.delenv("DEEPTUTOR_MISTAKE_BOOK_WRITE_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="mistake_book_write_disabled"):
        service.save_item(user_id="u1", attempt_ref=attempt_ref, subject_id="construction_exam_1")


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
    assert reviewed["review_due_at"] is None

    mastered = service.mark_mastered(user_id="u1", attempt_ref=attempt_ref, if_match=reviewed["etag"])
    assert mastered["mastered_at"]
    assert service.list_items(user_id="u1")["count"] == 0
    assert service.list_items(user_id="u1", include_mastered=True)["count"] == 1


def test_record_review_does_not_fabricate_schedule_and_clears_stale_due() -> None:
    """record_review 只写观测(last_reviewed_at), 不产调度结论。

    到期/调度真值唯一归 revalidation_queue 投影; 本服务硬编码 due 日期
    属第二调度权威(双轮设计 v3 §10-①), 本测试钉死收权后的行为:
    1) 复习不再捏造 review_due_at;
    2) 存量行里的历史假日期在下一次复习时被清空。
    """
    store = InMemoryMistakeBookStore()
    service = MistakeBookService(store=store)
    attempt_ref = sign_attempt_ref(user_id="u1", event_id="evt1", question_id="q1")

    saved = service.save_item(user_id="u1", attempt_ref=attempt_ref, subject_id="construction_exam_1")
    assert saved["review_due_at"] is None

    # 模拟收权前遗留的假调度日期(生产存量行)。
    store.update_item("u1", "evt1", {"review_due_at": "2020-01-01T08:00:00+08:00"})

    reviewed = service.record_review(user_id="u1", attempt_ref=attempt_ref)
    assert reviewed["last_reviewed_at"]
    assert reviewed["review_due_at"] is None

    listed = service.list_items(user_id="u1")["items"][0]
    assert listed["review_due_at"] is None


def test_mistake_book_module_never_touches_learner_truth_writers() -> None:
    """mastered_at/复习动作只是呈现层旗标, 不得写学情/证据/掌握真值。

    静态钉死: 本模块源码不得引用证据写入口或掌握推断器
    (防止未来把"标记掌握"按钮接回 learner truth, 违反 M0 reality-lock)。
    """
    import re

    source = (
        Path(__file__).resolve().parents[3]
        / "deeptutor"
        / "services"
        / "learner_state"
        / "mistake_book.py"
    ).read_text(encoding="utf-8")
    forbidden = re.compile(
        r"append_memory_event|build_learning_evidence|mastery_estimator|refresh_from_turn"
    )
    match = forbidden.search(source)
    assert match is None, f"mistake_book.py 不得触碰学情真值写入口: {match.group(0)}"


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


def test_local_fallback_store_is_shared_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    monkeypatch.setenv("DEEPTUTOR_MISTAKE_BOOK_LOCAL_FALLBACK", "true")
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    PathService.reset_instance()

    writer = MistakeBookService()
    reader = MistakeBookService()
    attempt_ref = sign_attempt_ref(user_id="u1", event_id="evt-local", question_id="q-local")

    saved = writer.save_item(
        user_id="u1",
        attempt_ref=attempt_ref,
        subject_id="construction_exam_1",
        title="本地错题",
    )

    listed = reader.list_items(user_id="u1")

    assert saved["event_id"] == "evt-local"
    assert listed["count"] == 1
    assert listed["items"][0]["event_id"] == "evt-local"
    PathService.reset_instance()


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
        service_key="service-key",  # pragma: allowlist secret
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


def test_supabase_mistake_book_list_items_pushes_read_filters_to_postgrest() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append({"method": request.method, "params": dict(request.url.params)})
        return httpx.Response(200, json=[], request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.supabase.co")
    store = SupabaseMistakeBookStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )

    assert store.list_items("u1", subject_id="construction_exam_1") == []

    assert requests[0]["method"] == "GET"
    assert requests[0]["params"]["user_id"] == "eq.u1"
    assert requests[0]["params"]["subject_id"] == "eq.construction_exam_1"
    assert requests[0]["params"]["archived_at"] == "is.null"
    assert requests[0]["params"]["mastered_at"] == "is.null"
    assert requests[0]["params"]["order"] == "saved_at.desc"


def test_supabase_mistake_book_list_items_include_mastered_does_not_filter_mastered_at() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append({"method": request.method, "params": dict(request.url.params)})
        return httpx.Response(200, json=[], request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.supabase.co")
    store = SupabaseMistakeBookStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        client=client,
    )

    assert store.list_items("u1", subject_id="construction_exam_1", include_mastered=True) == []

    assert requests[0]["params"]["subject_id"] == "eq.construction_exam_1"
    assert requests[0]["params"]["archived_at"] == "is.null"
    assert "mastered_at" not in requests[0]["params"]
