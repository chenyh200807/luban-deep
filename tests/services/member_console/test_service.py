from __future__ import annotations

from pathlib import Path
import threading

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


def test_login_with_password_requires_matching_hash(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.set_password("student_demo", "StrongPass123")

    result = service.login_with_password("student_demo", "StrongPass123")

    assert result["token"].startswith("dtm.")
    assert result["user"]["user_id"] == "student_demo"


def test_login_with_password_rejects_unknown_or_invalid_password(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service.set_password("student_demo", "StrongPass123")

    with pytest.raises(ValueError, match="用户名或密码错误"):
        service.login_with_password("student_demo", "wrong-password")

    with pytest.raises(ValueError, match="用户名或密码错误"):
        service.login_with_password("unknown-user", "StrongPass123")


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


def test_verify_phone_code_bootstraps_clean_new_member_state(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    send_result = service.send_phone_code("13955556666")
    result = service.verify_phone_code("13955556666", send_result["debug_code"])
    profile = result["user"]
    today = service.get_today_progress(profile["user_id"])

    assert profile["tier"] == "trial"
    assert profile["points"] == 120
    assert profile["level"] == 1
    assert today["today_done"] == 0
    assert today["streak_days"] == 0


def test_verify_phone_code_rejects_invalid_code(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service.send_phone_code("13955556666")

    with pytest.raises(ValueError, match="验证码错误"):
        service.verify_phone_code("13955556666", "000000")


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
