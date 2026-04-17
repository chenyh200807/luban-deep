from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import threading

import bcrypt
import pytest

from deeptutor.services.member_console.service import MemberConsoleService


@pytest.mark.asyncio
async def test_login_with_wechat_code_issues_signed_token_and_persists_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "openid_123456789012",
            "unionid": "unionid_abcdef",
            "session_key": "session_key_value",
        }

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)

    result = await service.login_with_wechat_code("wx-code")

    assert result["openid"] == "openid_123456789012"
    assert result["unionid"] == "unionid_abcdef"
    assert result["token"].startswith("dtm.")
    assert "session_key" not in result

    resolved_user_id = service.resolve_user_id(f"Bearer {result['token']}")
    assert resolved_user_id == result["user"]["user_id"]

    data = service._load()
    member = service._find_member(data, resolved_user_id)
    assert member["wx_openid"] == "openid_123456789012"
    assert member["wx_unionid"] == "unionid_abcdef"
    assert member["wx_session_key"] == "session_key_value"


@pytest.mark.asyncio
async def test_login_with_wechat_code_supports_dev_fallback_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _raise_missing(_code: str) -> dict[str, str]:
        raise RuntimeError("Missing WeChat Mini Program credentials.")

    monkeypatch.setattr(service, "_exchange_wechat_code", _raise_missing)

    result = await service.login_with_wechat_code("dev-local-user")

    assert result["token"].startswith("dtm.")
    assert result["openid"].startswith("dev_openid_")
    assert service.resolve_user_id(f"Bearer {result['token']}") == result["user"]["user_id"]


def test_resolve_user_id_accepts_signed_access_token(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    token = service._issue_access_token(
        user_id="student_demo",
        openid="openid_demo",
        unionid="unionid_demo",
    )

    assert service.resolve_user_id(f"Bearer {token}") == "student_demo"


def test_login_with_password_accepts_external_fastapi_auth_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    password_hash = bcrypt.hashpw(
        hashlib.sha256("Chen9028".encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    users_file.write_text(
        (
            '{\n'
            '  "chenyh2008": {\n'
            '    "id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",\n'
            f'    "password_hash": "{password_hash}",\n'
            '    "username": "chenyh2008"\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._mutate(
        lambda data: data["members"].append(
            {
                **data["members"][0],
                "user_id": "user_2008",
                "display_name": "chenyh2008",
                "phone": "2008",
            }
        )
    )

    result = service.login_with_password("chenyh2008", "Chen9028")

    assert result["token"].startswith("dtm.")
    assert result["user"]["user_id"] == "user_2008"
    assert result["user"]["username"] == "chenyh2008"


def test_login_with_password_rejects_unknown_or_invalid_external_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    password_hash = bcrypt.hashpw(
        hashlib.sha256("StrongPass123".encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    users_file.write_text(
        json.dumps(
            {
                "student_demo": {
                    "id": "user_demo",
                    "username": "student_demo",
                    "password_hash": password_hash,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    with pytest.raises(ValueError, match="用户名或密码错误"):
        service.login_with_password("student_demo", "wrong-password")

    with pytest.raises(ValueError, match="用户名或密码错误"):
        service.login_with_password("unknown-user", "StrongPass123")


def test_register_with_external_auth_creates_external_user_and_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    result = service.register_with_external_auth("new_student", "StrongPass123", "13812345678")
    external_users = json.loads(users_file.read_text(encoding="utf-8"))

    assert result["token"].startswith("dtm.")
    assert result["user"]["username"] == "new_student"
    assert "new_student" in external_users
    assert external_users["new_student"]["phone"] == "+8613812345678"


def test_member_console_serializes_multi_step_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    audit_started = threading.Event()
    allow_finish = threading.Event()
    second_write_done = threading.Event()
    note_holder: dict[str, object] = {}
    errors: list[BaseException] = []

    original_append_audit = service._append_audit

    def _gated_append_audit(data, **kwargs):
        if kwargs.get("action") == "note":
            audit_started.set()
            allow_finish.wait(timeout=2)
        return original_append_audit(data, **kwargs)

    monkeypatch.setattr(service, "_append_audit", _gated_append_audit)

    def _add_note() -> None:
        try:
            note_holder["note"] = service.add_note("student_demo", "并发写入测试")
        except BaseException as exc:  # pragma: no cover - surfaced by assertion below
            errors.append(exc)

    def _update_subscription() -> None:
        try:
            service.update_subscription("student_demo", auto_renew=False, reason="concurrency_test")
            second_write_done.set()
        except BaseException as exc:  # pragma: no cover - surfaced by assertion below
            errors.append(exc)

    writer_one = threading.Thread(target=_add_note)
    writer_two = threading.Thread(target=_update_subscription)

    writer_one.start()
    assert audit_started.wait(timeout=1.0)

    writer_two.start()
    assert not second_write_done.wait(timeout=0.1)

    allow_finish.set()
    writer_one.join(timeout=2.0)
    writer_two.join(timeout=2.0)

    assert not errors
    data = service._load()
    member = service._find_member(data, "student_demo")
    assert member["auto_renew"] is False
    assert any(note["id"] == note_holder["note"]["id"] for note in member["notes"])


def test_capture_points_updates_balance_and_prepends_ledger(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    wallet_before = service.get_wallet("student_demo")
    result = service.capture_points("student_demo", amount=20)
    wallet_after = service.get_wallet("student_demo")
    ledger = service.get_ledger("student_demo", limit=5, offset=0)

    assert result["captured"] == 20
    assert wallet_after["balance"] == wallet_before["balance"] - 20
    assert ledger["entries"][0]["reason"] == "capture"
    assert ledger["entries"][0]["delta"] == -20


def test_create_assessment_uses_unique_question_ids_per_quiz(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    payload = service.create_assessment("student_demo", count=10)
    question_ids = [item["question_id"] for item in payload["questions"]]

    assert len(question_ids) == 10
    assert len(set(question_ids)) == 10

    stored = service._load()["assessment_sessions"][payload["quiz_id"]]["questions"]
    stored_ids = [item["question_id"] for item in stored]
    assert stored_ids == question_ids


def test_member_360_includes_learner_state_heartbeat_and_bot_overlays(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            assert event_limit == 10
            event = type(
                "Event",
                (),
                {
                    "event_id": "evt_1",
                    "source_feature": "heartbeat",
                    "source_id": "job_1",
                    "source_bot_id": "review-bot",
                    "memory_kind": "heartbeat_delivery",
                    "payload_json": {"status": "sent"},
                    "created_at": "2026-04-16T09:00:00+08:00",
                },
            )()
            return type(
                "Snapshot",
                (),
                {
                    "user_id": user_id,
                    "profile": {"display_name": "陈同学"},
                    "summary": "正在复习地基基础。",
                    "progress": {"knowledge_map": {"weak_points": ["防火间距"]}},
                    "memory_events": [event],
                    "profile_updated_at": "2026-04-16T08:00:00+08:00",
                    "summary_updated_at": "2026-04-16T08:10:00+08:00",
                    "progress_updated_at": "2026-04-16T08:20:00+08:00",
                    "memory_events_updated_at": "2026-04-16T09:00:00+08:00",
                },
            )()

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 10
            assert include_arbitration is True
            return [{"event_id": "hb_1", "memory_kind": "heartbeat_delivery"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [{"event_id": "arb_1", "payload_json": {"winner_bot_id": "review-bot"}}]

    class FakeOverlayService:
        def list_user_overlays(self, user_id: str, *, limit: int | None = None):
            assert user_id == "student_demo"
            assert limit == 20
            return [{"bot_id": "review-bot", "version": 3}]

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: FakeOverlayService()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert payload["learner_state"]["summary"] == "正在复习地基基础。"
    assert payload["learner_state"]["recent_memory_events"][0]["memory_kind"] == "heartbeat_delivery"
    assert payload["heartbeat"]["history"][0]["event_id"] == "hb_1"
    assert payload["heartbeat"]["arbitration_history"][0]["payload_json"]["winner_bot_id"] == "review-bot"
    assert payload["bot_overlays"][0]["bot_id"] == "review-bot"


def test_member_console_learner_state_panel_and_controls(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            return type(
                "Snapshot",
                (),
                {
                    "user_id": user_id,
                    "profile": {"display_name": "陈同学"},
                    "summary": "正在复习案例题。",
                    "progress": {"knowledge_map": {"weak_points": ["网络计划"]}},
                    "memory_events": [],
                    "profile_updated_at": "2026-04-16T08:00:00+08:00",
                    "summary_updated_at": "2026-04-16T08:10:00+08:00",
                    "progress_updated_at": "2026-04-16T08:20:00+08:00",
                    "memory_events_updated_at": "2026-04-16T08:30:00+08:00",
                },
            )()

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            active = type(
                "Job",
                (),
                {
                    "job_id": "job_1",
                    "user_id": user_id,
                    "bot_id": "review-bot",
                    "channel": "heartbeat",
                    "policy_json": {"enabled": True},
                    "next_run_at": datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
                    "last_run_at": None,
                    "last_result_json": None,
                    "failure_count": 0,
                    "status": "active",
                    "created_at": datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
                },
            )()
            return [active]

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            return [{"event_id": "hb_1"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            return [{"event_id": "arb_1"}]

        def pause_heartbeat_job(self, user_id: str, job_id: str):
            assert user_id == "student_demo"
            assert job_id == "job_1"
            return type(
                "Job",
                (),
                {
                    "job_id": job_id,
                    "user_id": user_id,
                    "bot_id": "review-bot",
                    "channel": "heartbeat",
                    "policy_json": {"enabled": True},
                    "next_run_at": datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
                    "last_run_at": None,
                    "last_result_json": None,
                    "failure_count": 0,
                    "status": "paused",
                    "created_at": datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 16, 9, 5, tzinfo=timezone.utc),
                },
            )()

        def resume_heartbeat_job(self, user_id: str, job_id: str):
            assert user_id == "student_demo"
            assert job_id == "job_1"
            return type(
                "Job",
                (),
                {
                    "job_id": job_id,
                    "user_id": user_id,
                    "bot_id": "review-bot",
                    "channel": "heartbeat",
                    "policy_json": {"enabled": True},
                    "next_run_at": datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
                    "last_run_at": None,
                    "last_result_json": None,
                    "failure_count": 0,
                    "status": "active",
                    "created_at": datetime(2026, 4, 16, 9, 0, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 4, 16, 9, 10, tzinfo=timezone.utc),
                },
            )()

    class FakeOverlayService:
        def list_user_overlays(self, user_id: str, *, limit: int | None = None):
            return [{"bot_id": "review-bot", "version": 4}]

        def read_overlay(self, bot_id: str, user_id: str):
            return {"bot_id": bot_id, "user_id": user_id, "version": 4}

        def list_overlay_events(self, bot_id: str, user_id: str, *, limit: int | None = None, event_type: str | None = None):
            return [{"event_id": "evt_1"}]

        def list_overlay_audit(self, bot_id: str, user_id: str, *, limit: int | None = None):
            return [{"event_id": "audit_1"}]

        def patch_overlay(self, bot_id: str, user_id: str, patch, *, source_feature: str, source_id: str):
            return {"bot_id": bot_id, "user_id": user_id, "version": 5, "patch": patch}

        def apply_promotions(self, bot_id: str, user_id: str, *, learner_state_service, min_confidence: float = 0.7, max_candidates: int = 10):
            return {"acked_ids": ["cand_1"], "dropped_ids": []}

        def ack_promotions(self, bot_id: str, user_id: str, candidate_ids, *, reason: str = ""):
            return {"affected_count": len(candidate_ids), "reason": reason}

        def drop_promotions(self, bot_id: str, user_id: str, candidate_ids, *, reason: str = ""):
            return {"affected_count": len(candidate_ids), "reason": reason}

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: FakeOverlayService()  # type: ignore[method-assign]

    panel = service.get_member_learner_state_panel("student_demo", limit=5)
    jobs = service.list_member_heartbeat_jobs("student_demo")
    paused = service.pause_member_heartbeat_job("student_demo", "job_1", operator="admin_demo")
    resumed = service.resume_member_heartbeat_job("student_demo", "job_1", operator="admin_demo")
    overlay = service.get_member_overlay("student_demo", "review-bot")
    events = service.get_member_overlay_events("student_demo", "review-bot", limit=5)
    audit = service.get_member_overlay_audit("student_demo", "review-bot", limit=5)
    patched = service.patch_member_overlay(
        "student_demo",
        "review-bot",
        [{"op": "merge", "field": "heartbeat_override", "value": {"suppress": True}}],
        operator="admin_demo",
    )
    applied = service.apply_member_overlay_promotions(
        "student_demo",
        "review-bot",
        operator="admin_demo",
        min_confidence=0.8,
        max_candidates=3,
    )
    acked = service.ack_member_overlay_promotions(
        "student_demo",
        "review-bot",
        ["cand_1"],
        operator="admin_demo",
        reason="confirmed",
    )
    dropped = service.drop_member_overlay_promotions(
        "student_demo",
        "review-bot",
        ["cand_2"],
        operator="admin_demo",
        reason="noise",
    )

    assert panel["learner_state"]["summary"] == "正在复习案例题。"
    assert panel["heartbeat_jobs"][0]["job_id"] == "job_1"
    assert panel["bot_overlays"][0]["bot_id"] == "review-bot"
    assert jobs["items"][0]["status"] == "active"
    assert paused["status"] == "paused"
    assert resumed["status"] == "active"
    assert overlay["version"] == 4
    assert events["items"][0]["event_id"] == "evt_1"
    assert audit["items"][0]["event_id"] == "audit_1"
    assert patched["version"] == 5
    assert applied["acked_ids"] == ["cand_1"]
    assert acked["affected_count"] == 1
    assert dropped["affected_count"] == 1


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_merges_into_existing_phone_user(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    result = await service.bind_phone_for_wechat("student_demo", "13800000002")

    assert result["bound"] is True
    assert result["merged"] is True
    assert result["user"]["user_id"] == "student_risk"


def test_submit_assessment_updates_today_progress_and_chapter_practice(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    payload = service.create_assessment("student_demo", count=5)
    stored = service._load()["assessment_sessions"][payload["quiz_id"]]["questions"]
    answers = {item["question_id"]: item["answer"] for item in stored}

    service.submit_assessment("student_demo", payload["quiz_id"], answers, time_spent_seconds=60)

    today = service.get_today_progress("student_demo")
    chapters = service.get_chapter_progress("student_demo")

    assert today["today_done"] >= 5
    assert any(item["done"] >= 1 for item in chapters)


def test_verify_phone_code_bootstraps_clean_new_member_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    send_result = service.send_phone_code("13955556666")
    result = service.verify_phone_code("13955556666", send_result["debug_code"])
    profile = result["user"]
    today = service.get_today_progress(profile["user_id"])
    external_users = json.loads(users_file.read_text(encoding="utf-8"))
    external_user = next(iter(external_users.values()))

    assert profile["tier"] == "trial"
    assert profile["points"] == 120
    assert profile["level"] == 1
    assert today["today_done"] == 0
    assert today["streak_days"] == 0
    assert external_user["phone"] == "+8613955556666"
    assert str(profile["username"]).startswith("user_6666")


def test_verify_phone_code_rejects_invalid_code(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service.send_phone_code("13955556666")

    with pytest.raises(ValueError, match="验证码错误"):
        service.verify_phone_code("13955556666", "000000")


def test_send_phone_code_fails_closed_in_production_without_sms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("ALIYUN_SMS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ALIYUN_SMS_ACCESS_KEY_SECRET", raising=False)
    monkeypatch.delenv("MEMBER_CONSOLE_USE_REAL_SMS", raising=False)

    with pytest.raises(RuntimeError, match="短信服务未配置，生产环境已禁止调试验证码"):
        service.send_phone_code("13955556666")


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_accepts_phone_code_exchange(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13911112222"

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)

    result = await service.bind_phone_for_wechat("student_demo", "phone-code-123")

    assert result["bound"] is True
    assert result["phone"] == "13911112222"
