from __future__ import annotations

import hashlib
import json
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
