from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from types import SimpleNamespace

import bcrypt
import httpx
import pytest

import deeptutor.services.member_console.service as member_service_module
from deeptutor.services.member_console.service import MemberConsoleService
from deeptutor.services.member_console import external_auth as external_auth_module
from deeptutor.services.session.sqlite_store import SQLiteSessionStore, build_user_owner_key


@pytest.fixture(autouse=True)
def _enable_demo_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_MEMBER_CONSOLE_ENABLE_DEMO_SEED", "1")


class _FakeWalletBootstrapService:
    is_configured = True

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.snapshots: dict[str, SimpleNamespace] = {}

    def ensure_wallet_seeded(self, **kwargs):
        self.calls.append(dict(kwargs))
        user_id = str(kwargs["user_id"])
        opening_points = int(kwargs.get("opening_points") or 0)
        snapshot = self.snapshots.get(user_id)
        if snapshot is None:
            snapshot = SimpleNamespace(
                user_id=user_id,
                balance_micros=opening_points * 1_000_000,
                frozen_micros=0,
                plan_id=str(kwargs.get("plan_id") or ""),
                version=1,
                created_at="2026-04-21T10:00:00+08:00",
            )
            self.snapshots[user_id] = snapshot
        return snapshot


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
    assert result["user_id"] == result["user"]["user_id"]
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
async def test_login_with_wechat_code_promotes_phone_backed_member_to_canonical_wallet_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("wx_O4aNJg7O_wRk"),
                "user_id": "wx_O4aNJg7O_wRk",
                "phone": "34277511499",
                "wx_openid": "oTHl5610QTUB2maCO4aNJg7O-wRk",
            }
        ]

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "oTHl5610QTUB2maCO4aNJg7O-wRk",
            "unionid": "unionid_live_user",
            "session_key": "session_key_value",
        }

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)
    monkeypatch.setattr(
        member_service_module,
        "ensure_external_auth_user_for_phone",
        lambda phone: {"id": canonical_uid, "username": "user_1499", "phone": phone},
    )
    service._mutate(_seed)

    result = await service.login_with_wechat_code("wx-code")
    claims = service.verify_access_token(result["token"])
    snapshot = service._load_member_snapshot("wx_O4aNJg7O_wRk")["member"]

    assert claims is not None
    assert claims["canonical_uid"] == canonical_uid
    assert result["user_id"] == "wx_O4aNJg7O_wRk"
    assert snapshot["external_auth_user_id"] == canonical_uid
    assert snapshot["auth_username"] == "user_1499"
    assert wallet_service.calls[0]["user_id"] == canonical_uid
    assert wallet_service.calls[0]["opening_points"] == 120


@pytest.mark.asyncio
async def test_login_with_wechat_code_uses_existing_wx_openid_alias_as_canonical_wallet_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    class _FakeAliasStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "wx_openid" and alias_value == "oTHl5610QTUB2maCO4aNJg7O-wRk":
                return {"user_id": canonical_uid}
            return None

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("wx_O4aNJg7O_wRk"),
                "user_id": "wx_O4aNJg7O_wRk",
                "phone": "34277511499",
                "wx_openid": "oTHl5610QTUB2maCO4aNJg7O-wRk",
            }
        ]

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "oTHl5610QTUB2maCO4aNJg7O-wRk",
            "unionid": "",
            "session_key": "session_key_value",
        }

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)
    monkeypatch.setattr(
        "deeptutor.services.wallet.identity.get_wallet_identity_store",
        lambda: _FakeAliasStore(),
    )
    service._mutate(_seed)

    result = await service.login_with_wechat_code("wx-code")
    claims = service.verify_access_token(result["token"])
    canonical_snapshot = service._load_member_snapshot(canonical_uid)["member"]
    legacy_snapshot = service._load_member_snapshot("wx_O4aNJg7O_wRk")["member"]

    assert claims is not None
    assert claims["canonical_uid"] == canonical_uid
    assert wallet_service.calls[0]["user_id"] == canonical_uid
    assert canonical_snapshot["display_name"] == "wx_O4aNJg7O_wRk"
    assert canonical_snapshot["wx_openid"] == "oTHl5610QTUB2maCO4aNJg7O-wRk"
    assert legacy_snapshot["external_auth_user_id"] == canonical_uid


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


@pytest.mark.asyncio
async def test_login_with_wechat_code_fails_closed_in_production_even_for_dev_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_ALLOW_DEV_WECHAT_LOGIN", "1")

    async def _raise_missing(_code: str) -> dict[str, str]:
        raise RuntimeError("Missing WeChat Mini Program credentials.")

    monkeypatch.setattr(service, "_exchange_wechat_code", _raise_missing)

    with pytest.raises(RuntimeError, match="Missing WeChat Mini Program credentials."):
        await service.login_with_wechat_code("dev-local-user")


@pytest.mark.asyncio
async def test_login_with_wechat_code_maps_upstream_timeout_to_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _raise_timeout(_code: str) -> dict[str, str]:
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(service, "_exchange_wechat_code", _raise_timeout)

    with pytest.raises(RuntimeError, match="WeChat code2Session request timed out"):
        await service.login_with_wechat_code("wx-code")


def test_resolve_user_id_accepts_signed_access_token(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    token = service._issue_access_token(
        user_id="student_demo",
        openid="openid_demo",
        unionid="unionid_demo",
    )

    assert service.resolve_user_id(f"Bearer {token}") == "student_demo"


def test_resolve_user_id_accepts_lowercase_bearer_prefix(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    token = service._issue_access_token(user_id="student_demo")

    assert service.resolve_user_id(f"bearer {token}") == "student_demo"


def test_issue_access_token_uses_configured_ttl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("MEMBER_CONSOLE_ACCESS_TOKEN_TTL_SECONDS", "900")

    token = service._issue_access_token(user_id="student_demo")
    claims = service.verify_access_token(token)

    assert claims is not None
    assert int(claims["exp"]) - int(claims["iat"]) == 900


def test_refresh_access_token_reissues_valid_token_without_second_credential(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("MEMBER_CONSOLE_ACCESS_TOKEN_TTL_SECONDS", "600")
    monkeypatch.setenv("MEMBER_CONSOLE_MAX_SESSION_AGE_SECONDS", "1800")

    base = datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    current = {"value": base}

    def _fake_now() -> datetime:
        return current["value"]

    monkeypatch.setattr(member_service_module, "_now", _fake_now)

    token = service._issue_access_token(user_id="student_demo")
    initial_claims = service.verify_access_token(token)
    assert initial_claims is not None

    current["value"] = base + timedelta(seconds=120)
    refreshed = service.refresh_access_token(f"Bearer {token}")
    refreshed_claims = service.verify_access_token(refreshed["token"])

    assert refreshed["user_id"] == "student_demo"
    assert refreshed_claims is not None
    assert refreshed_claims["uid"] == "student_demo"
    assert int(refreshed_claims["orig_iat"]) == int(initial_claims["orig_iat"])
    assert refreshed["token"] != token
    assert int(refreshed_claims["exp"]) > int(initial_claims["exp"])
    assert refreshed["expires_at"] == int(refreshed_claims["exp"])
    assert refreshed["expires_in"] == 600


def test_refresh_access_token_honors_absolute_session_age_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("MEMBER_CONSOLE_ACCESS_TOKEN_TTL_SECONDS", "600")
    monkeypatch.setenv("MEMBER_CONSOLE_MAX_SESSION_AGE_SECONDS", "900")

    base = datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    current = {"value": base}

    def _fake_now() -> datetime:
        return current["value"]

    monkeypatch.setattr(member_service_module, "_now", _fake_now)

    token = service._issue_access_token(user_id="student_demo")

    current["value"] = base + timedelta(seconds=360)
    refreshed = service.refresh_access_token(f"Bearer {token}")
    refreshed_claims = service.verify_access_token(refreshed["token"])

    assert refreshed_claims is not None
    assert int(refreshed_claims["exp"]) - int(refreshed_claims["orig_iat"]) == 900
    assert refreshed["expires_in"] == 540

    current["value"] = base + timedelta(seconds=900)
    with pytest.raises(ValueError, match="Session refresh window expired"):
        service.refresh_access_token(f"Bearer {refreshed['token']}")


def test_production_bootstrap_starts_without_demo_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")

    data = service._load()

    assert data["members"] == []
    assert data["audit_log"] == []
    assert {package["id"] for package in data["packages"]} == {
        "starter",
        "standard",
        "pro",
        "ultimate",
    }


def test_non_production_bootstrap_defaults_to_empty_members_without_demo_seed_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.delenv("DEEPTUTOR_MEMBER_CONSOLE_ENABLE_DEMO_SEED", raising=False)
    monkeypatch.delenv("DEEPTUTOR_ENV", raising=False)

    data = service._load()

    assert data["members"] == []
    assert data["audit_log"] == []


def test_production_bootstrap_can_create_first_real_member_without_seed_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")

    profile = service.get_profile("prod_first_user")

    assert profile["user_id"] == "prod_first_user"
    assert profile["tier"] == "trial"
    assert profile["points"] == 120


def test_get_profile_persists_first_real_member(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    profile = service.get_profile("ghost_user")
    data = service._load()

    assert profile["user_id"] == "ghost_user"
    assert any(member["user_id"] == "ghost_user" for member in data["members"])


def test_home_dashboard_exposes_structured_study_plan_and_progress_feedback_from_learner_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    profile = service.get_profile("student_plan")
    assert profile["user_id"] == "student_plan"

    def _apply(data: dict[str, object]) -> None:
        for member in data["members"]:
            if member["user_id"] != "student_plan":
                continue
            member["focus_topic"] = "施工管理"
            member["daily_target"] = 8
            member["review_due"] = 2
            member["study_days"] = 3
            member["daily_practice_counts"] = {
                "2026-04-19": 6,
                "2026-04-18": 7,
                "2026-04-17": 5,
            }
            member["chapter_practice_stats"] = {
                "防水工程": {"done": 9, "correct": 6, "last_activity_at": "2026-04-21T09:00:00+08:00"}
            }
            break

    service._mutate(_apply)

    class _FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_plan"
            assert event_limit == 20
            return type(
                "Snapshot",
                (),
                {
                    "profile": {
                        "focus_topic": "防水工程",
                    },
                    "progress": {
                        "today": {"today_done": 4, "daily_target": 8},
                        "knowledge_map": {
                            "weak_points": ["防水工程"],
                            "guided_learning_history": [
                                {
                                    "completed_titles": ["屋面卷材铺贴", "节点收头"],
                                }
                            ],
                        },
                    },
                    "memory_events": [
                        SimpleNamespace(
                            memory_kind="heartbeat_delivery",
                            payload_json={"delivery": {"message": "这是一条 heartbeat 提醒，不应该出现在进步反馈里"}},
                        ),
                        SimpleNamespace(
                            memory_kind="guide_completion",
                            payload_json={
                                "payload_json": {
                                    "knowledge_points": [
                                        {"knowledge_title": "屋面卷材铺贴"},
                                        {"knowledge_title": "节点收头"},
                                    ]
                                }
                            },
                        ),
                    ],
                },
            )()

    monkeypatch.setattr(service, "_get_learner_state_service", lambda: _FakeLearnerStateService())

    dashboard = service.get_home_dashboard("student_plan")

    assert dashboard["study_plan"]["focus_topic"] == "防水工程"
    assert "待复习点" in dashboard["study_plan"]["priority_task"]
    assert dashboard["study_plan"]["study_method"].startswith("先看“防水工程”")
    assert "近 3 天" in dashboard["progress_feedback"]["summary"]
    assert "防水工程" in dashboard["progress_feedback"]["insight"]
    assert dashboard["progress_feedback"]["cards"][2]["value"] == "9题"
    assert any(
        item["title"] == "刚完成一次专题梳理"
        for item in dashboard["progress_feedback"]["milestones"]
    )
    assert not any(
        "heartbeat" in item["detail"]
        for item in dashboard["progress_feedback"]["milestones"]
    )


@pytest.mark.asyncio
async def test_production_bootstrap_persists_first_wechat_user_without_demo_seed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_AUTH_SECRET", "prod_auth_secret")

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "openid_prod_first_user",
            "unionid": "unionid_prod_first_user",
            "session_key": "session_key_prod_first_user",
        }

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)

    result = await service.login_with_wechat_code("wx-prod-code")
    data = service._load()

    assert result["user"]["user_id"].startswith("wx_")
    assert [member["user_id"] for member in data["members"]] == [result["user"]["user_id"]]


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
                "auth_username": "chenyh2008",
                "external_auth_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "phone": "2008",
            }
        )
    )

    result = service.login_with_password("chenyh2008", "Chen9028")

    assert result["token"].startswith("dtm.")
    assert result["user_id"] == "user_2008"
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


def test_canonical_member_snapshot_merges_legacy_external_auth_learning_state(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_user_id = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            service._build_default_member(canonical_user_id),
            {
                **service._build_default_member("user_2008"),
                "user_id": "user_2008",
                "display_name": "chenyh2008",
                "auth_username": "chenyh2008",
                "external_auth_user_id": canonical_user_id,
                "points_balance": 360,
                "focus_topic": "地基基础",
                "focus_query": "我想练习地基基础相关的题目",
                "study_days": 3,
                "chapter_mastery": {
                    "建筑构造": {"name": "建筑构造", "mastery": 50},
                    "地基基础": {"name": "地基基础", "mastery": 50},
                    "防水工程": {"name": "防水工程", "mastery": 50},
                    "施工管理": {"name": "施工管理", "mastery": 50},
                    "主体结构": {"name": "主体结构", "mastery": 50},
                },
                "daily_practice_counts": {"2026-04-14": 2},
                "chapter_practice_stats": {
                    "地基基础": {
                        "done": 2,
                        "correct": 1,
                        "last_activity_at": "2026-04-14T10:00:00+08:00",
                    }
                },
            },
        ]

    service._mutate(_seed)

    assessment = service.get_assessment_profile(canonical_user_id)
    canonical_profile = service.get_profile(canonical_user_id)
    legacy_profile = service.get_profile("user_2008")
    chapter_progress = service.get_chapter_progress(canonical_user_id)
    data = service._load()
    canonical_member = service._find_member(data, canonical_user_id)
    legacy_member = service._find_member(data, "user_2008")
    foundation_progress = next(item for item in chapter_progress if item["chapter_name"] == "地基基础")

    assert assessment["score"] == 50
    assert assessment["chapter_mastery"]["地基基础"]["mastery"] == 50
    assert canonical_profile["user_id"] == canonical_user_id
    assert canonical_profile["username"] == "chenyh2008"
    assert legacy_profile["user_id"] == canonical_user_id
    assert legacy_member["merged_into"] == canonical_user_id
    assert canonical_member["focus_topic"] == "地基基础"
    assert canonical_member["study_days"] == 3
    assert foundation_progress["done"] == 2
    assert foundation_progress["total"] == 30


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
    assert result["user_id"] == result["user"]["user_id"]
    assert result["user"]["username"] == "new_student"
    assert "new_student" in external_users
    assert external_users["new_student"]["phone"] == "+8613812345678"


def test_register_with_external_auth_does_not_match_existing_display_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users_file = tmp_path / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users_file))

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._mutate(
        lambda data: data["members"].append(
            {
                **service._build_default_member("wx_attacker"),
                "display_name": "victimname",
                "phone": "13800001111",
            }
        )
    )

    result = service.register_with_external_auth("victimname", "StrongPass123", "13800002222")
    data = service._load()
    attacker = service._find_member(data, "wx_attacker")

    assert result["user"]["user_id"] != "wx_attacker"
    assert attacker.get("auth_username") in {None, ""}
    assert attacker["phone"] == "13800001111"


def test_external_auth_production_default_does_not_read_legacy_luban_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_users = tmp_path / "app" / "users.json"
    legacy_users = tmp_path / "luban" / "users.json"
    legacy_users.parent.mkdir(parents=True, exist_ok=True)
    password_hash = bcrypt.hashpw(
        hashlib.sha256("StrongPass123".encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    legacy_users.write_text(
        json.dumps(
            {
                "legacy_user": {
                    "id": "legacy-user-id",
                    "username": "legacy_user",
                    "password_hash": password_hash,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", raising=False)
    monkeypatch.setattr(external_auth_module, "_PRIMARY_USERS_FILE", primary_users)
    monkeypatch.setattr(external_auth_module, "_LEGACY_USERS_FILE", legacy_users)

    assert external_auth_module.get_external_auth_user("legacy_user") is None
    assert external_auth_module._resolve_users_file_for_write() == primary_users


def test_external_auth_production_explicit_legacy_env_still_allows_compat_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_users = tmp_path / "luban" / "users.json"
    legacy_users.parent.mkdir(parents=True, exist_ok=True)
    password_hash = bcrypt.hashpw(
        hashlib.sha256("StrongPass123".encode("utf-8")).hexdigest().encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    legacy_users.write_text(
        json.dumps(
            {
                "legacy_user": {
                    "id": "legacy-user-id",
                    "username": "legacy_user",
                    "password_hash": password_hash,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(legacy_users))

    user = external_auth_module.get_external_auth_user("legacy_user")

    assert user is not None
    assert user["username"] == "legacy_user"


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

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            return []

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

    assert payload["learner_state"]["available"] is True
    assert payload["learner_state"]["summary"] == "正在复习地基基础。"
    assert payload["learner_state"]["recent_memory_events"][0]["memory_kind"] == "heartbeat_delivery"
    assert payload["heartbeat"]["history"][0]["event_id"] == "hb_1"
    assert payload["heartbeat"]["arbitration_history"][0]["payload_json"]["winner_bot_id"] == "review-bot"
    assert payload["bot_overlays"][0]["bot_id"] == "review-bot"


def test_member_360_includes_recent_conversation_messages(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    asyncio.run(
        service._store.create_session(
            title="地基基础答疑",
            session_id="tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("tb_student_demo", "user", "帮我看看地基基础怎么复习"))
    asyncio.run(service._store.add_message("tb_student_demo", "assistant", "先按承载力、验槽和防水节点拆开复习。"))
    asyncio.run(
        service._store.create_session(
            title="TutorBot mirror",
            session_id="tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(
        service._store.add_message(
            "tutorbot:bot:construction-exam-coach:user:student_demo:chat:tb_student_demo",
            "user",
            "镜像会话不应该重复展示",
        )
    )
    asyncio.run(
        service._store.create_session(
            title="空会话",
            session_id="tb_empty",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )

    service._get_learner_state_service = lambda: type(  # type: ignore[method-assign]
        "LearnerStateService",
        (),
        {
            "read_snapshot": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "list_heartbeat_jobs": lambda *_args, **_kwargs: [],
            "list_heartbeat_history": lambda *_args, **_kwargs: [],
            "list_heartbeat_arbitration_history": lambda *_args, **_kwargs: [],
            "read_profile": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "read_summary": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "read_progress": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
            "list_memory_events": lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("not configured")),
        },
    )()
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert len(payload["recent_conversations"]) == 1
    assert payload["recent_conversations"][0]["session_id"] == "tb_student_demo"
    assert payload["recent_conversations"][0]["title"] == "地基基础答疑"
    assert payload["recent_conversations"][0]["message_count"] == 2
    assert [message["role"] for message in payload["recent_conversations"][0]["messages"]] == ["user", "assistant"]
    assert payload["recent_conversations"][0]["messages"][0]["content"] == "帮我看看地基基础怎么复习"
    assert payload["recent_conversations"][0]["messages"][1]["content"] == "先按承载力、验槽和防水节点拆开复习。"


def test_record_conversation_view_writes_privacy_audit(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._store = SQLiteSessionStore(db_path=tmp_path / "chat_history.db")

    asyncio.run(
        service._store.create_session(
            title="地基基础答疑",
            session_id="tb_student_demo",
            owner_key=build_user_owner_key("student_demo"),
            source="wx_miniprogram",
        )
    )
    asyncio.run(service._store.add_message("tb_student_demo", "user", "帮我看看地基基础怎么复习"))
    asyncio.run(service._store.add_message("tb_student_demo", "assistant", "先按承载力、验槽和防水节点拆开复习。"))

    result = service.record_conversation_view(
        "student_demo",
        "tb_student_demo",
        operator="admin_demo",
    )

    assert result["session_id"] == "tb_student_demo"
    assert result["title"] == "地基基础答疑"
    assert result["message_count"] == 2

    audit = service.list_audit_log(target_user="student_demo", action="conversation_view")
    assert audit["total"] == 1
    assert audit["items"][0]["operator"] == "admin_demo"
    assert audit["items"][0]["after"]["session_id"] == "tb_student_demo"
    assert audit["items"][0]["after"]["message_count"] == 2


def test_member_360_keeps_learner_state_when_heartbeat_jobs_fail(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            assert event_limit == 10
            return type(
                "Snapshot",
                (),
                {
                    "user_id": user_id,
                    "profile": {"display_name": "陈同学"},
                    "summary": "正在复习地基基础。",
                    "progress": {"knowledge_map": {"weak_points": ["防火间距"]}},
                    "memory_events": [],
                    "profile_updated_at": "2026-04-16T08:00:00+08:00",
                    "summary_updated_at": "2026-04-16T08:10:00+08:00",
                    "progress_updated_at": "2026-04-16T08:20:00+08:00",
                    "memory_events_updated_at": "2026-04-16T09:00:00+08:00",
                },
            )()

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            raise RuntimeError("jobs unavailable")

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 10
            assert include_arbitration is True
            return [{"event_id": "hb_1"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [{"event_id": "arb_1"}]

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert payload["learner_state"]["available"] is True
    assert payload["learner_state"]["summary"] == "正在复习地基基础。"
    assert payload["heartbeat"]["jobs"] == []
    assert payload["heartbeat"]["history"] == [{"event_id": "hb_1"}]
    assert payload["heartbeat"]["arbitration_history"] == [{"event_id": "arb_1"}]


def test_member_360_loads_partial_learner_state_when_snapshot_fails(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            assert event_limit == 10
            raise RuntimeError("snapshot unavailable")

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 10
            assert include_arbitration is True
            return [{"event_id": "hb_1"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [{"event_id": "arb_1"}]

        def read_profile(self, user_id: str):
            assert user_id == "student_demo"
            return {"display_name": "陈同学"}

        def read_summary(self, user_id: str):
            assert user_id == "student_demo"
            return "正在复习地基基础。"

        def read_progress(self, user_id: str):
            assert user_id == "student_demo"
            return {"knowledge_map": {"weak_points": ["防火间距"]}}

        def list_memory_events(self, user_id: str, limit: int | None = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [
                type(
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
            ]

        def _file_updated_at(self, user_id: str, section: str):
            assert user_id == "student_demo"
            return {
                "profile": "2026-04-16T08:00:00+08:00",
                "summary": "2026-04-16T08:10:00+08:00",
                "progress": "2026-04-16T08:20:00+08:00",
                "events": "2026-04-16T09:00:00+08:00",
            }[section]

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert payload["learner_state"]["available"] is True
    assert payload["learner_state"]["profile"] == {"display_name": "陈同学"}
    assert payload["learner_state"]["summary"] == "正在复习地基基础。"
    assert payload["learner_state"]["progress"] == {"knowledge_map": {"weak_points": ["防火间距"]}}
    assert payload["learner_state"]["recent_memory_events"][0]["event_id"] == "evt_1"
    assert payload["learner_state"]["memory_events_updated_at"] == "2026-04-16T09:00:00+08:00"
    assert payload["heartbeat"]["history"] == [{"event_id": "hb_1"}]
    assert payload["heartbeat"]["arbitration_history"] == [{"event_id": "arb_1"}]


def test_member_360_returns_empty_learner_state_payload_when_snapshot_and_partial_reads_fail(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    class FakeLearnerStateService:
        def read_snapshot(self, user_id: str, *, event_limit: int = 5):
            assert user_id == "student_demo"
            assert event_limit == 10
            raise RuntimeError("snapshot unavailable")

        def read_profile(self, user_id: str):
            assert user_id == "student_demo"
            raise RuntimeError("profile unavailable")

        def read_summary(self, user_id: str):
            assert user_id == "student_demo"
            raise RuntimeError("summary unavailable")

        def read_progress(self, user_id: str):
            assert user_id == "student_demo"
            raise RuntimeError("progress unavailable")

        def list_memory_events(self, user_id: str, limit: int | None = 20):
            assert user_id == "student_demo"
            assert limit == 10
            raise RuntimeError("events unavailable")

        def list_heartbeat_jobs(self, user_id: str):
            assert user_id == "student_demo"
            return []

        def list_heartbeat_history(self, user_id: str, *, limit: int = 20, include_arbitration: bool = True):
            assert user_id == "student_demo"
            assert limit == 10
            assert include_arbitration is True
            return [{"event_id": "hb_1"}]

        def list_heartbeat_arbitration_history(self, user_id: str, *, limit: int = 20):
            assert user_id == "student_demo"
            assert limit == 10
            return [{"event_id": "arb_1"}]

    service._get_learner_state_service = lambda: FakeLearnerStateService()  # type: ignore[method-assign]
    service._get_overlay_service = lambda: type("OverlayService", (), {"list_user_overlays": lambda *_args, **_kwargs: []})()  # type: ignore[method-assign]

    payload = service.get_member_360("student_demo")

    assert payload["learner_state"] == {
        "user_id": "student_demo",
        "available": False,
        "profile": {},
        "summary": "",
        "progress": {},
        "recent_memory_events": [],
        "profile_updated_at": None,
        "summary_updated_at": None,
        "progress_updated_at": None,
        "memory_events_updated_at": None,
    }
    assert payload["heartbeat"]["history"] == [{"event_id": "hb_1"}]
    assert payload["heartbeat"]["arbitration_history"] == [{"event_id": "arb_1"}]


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


def test_member_console_overlay_promotion_apply_uses_real_services_and_audits_skips(tmp_path: Path) -> None:
    from deeptutor.services.learner_state.overlay_service import BotLearnerOverlayService
    from deeptutor.services.learner_state.service import LearnerStateService

    class PathServiceStub:
        @property
        def project_root(self):
            return tmp_path

        def get_user_root(self):
            return tmp_path

        def get_learner_state_root(self):
            path = tmp_path / "learner_state"
            path.mkdir(parents=True, exist_ok=True)
            return path

        def get_learner_state_outbox_db(self):
            return tmp_path / "runtime" / "outbox.db"

        def get_guide_dir(self):
            path = tmp_path / "workspace" / "guide"
            path.mkdir(parents=True, exist_ok=True)
            return path

    class MemberServiceStub:
        def get_profile(self, user_id: str):
            return {
                "user_id": user_id,
                "display_name": "陈同学",
                "difficulty_preference": "medium",
                "explanation_style": "detailed",
                "focus_topic": "案例题",
                "daily_target": 30,
            }

        def get_today_progress(self, _user_id: str):
            return {"today_done": 0, "daily_target": 30, "streak_days": 0}

        def get_chapter_progress(self, _user_id: str):
            return []

    class DisabledCoreStore:
        is_configured = False

    path_service = PathServiceStub()
    learner_state_service = LearnerStateService(
        path_service=path_service,
        member_service=MemberServiceStub(),
        core_store=DisabledCoreStore(),
    )
    overlay_service = BotLearnerOverlayService(path_service=path_service)
    valid_candidate = overlay_service.promote_candidate(
        "review-bot",
        "student_demo",
        "possible_weak_point",
        {"topic": "防火间距", "confidence": 0.92, "promotion_basis": "structured_result"},
        source_feature="quiz",
        source_id="quiz_1",
    )["promotion_candidates"][0]
    skipped_candidate = overlay_service.promote_candidate(
        "review-bot",
        "student_demo",
        "possible_weak_point",
        {"topic": "施工缝", "confidence": 0.91},
        source_feature="chat",
        source_id="turn_2",
    )["promotion_candidates"][-1]
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    service._get_learner_state_service = lambda: learner_state_service  # type: ignore[method-assign]
    service._get_overlay_service = lambda: overlay_service  # type: ignore[method-assign]

    result = service.apply_member_overlay_promotions(
        "student_demo",
        "review-bot",
        operator="ops_admin",
        min_confidence=0.7,
        max_candidates=10,
    )

    progress = learner_state_service.read_progress("student_demo")
    weak_points = list((progress.get("knowledge_map") or {}).get("weak_points") or [])
    remaining_candidates = overlay_service.read_overlay("review-bot", "student_demo")["promotion_candidates"]
    audit = service.list_audit_log(action="overlay_promotion_apply", page_size=1)["items"][0]

    assert result["acked_ids"] == [valid_candidate["candidate_id"]]
    assert result["skipped_ids"] == [skipped_candidate["candidate_id"]]
    assert result["skipped"][0]["reasons"] == ["missing_promotion_basis"]
    assert weak_points == ["防火间距"]
    assert [item["candidate_id"] for item in remaining_candidates] == [skipped_candidate["candidate_id"]]
    assert audit["operator"] == "ops_admin"
    assert audit["after"]["acked_ids"] == [valid_candidate["candidate_id"]]
    assert audit["after"]["skipped_ids"] == [skipped_candidate["candidate_id"]]
    assert audit["after"]["skipped"][0]["reasons"] == ["missing_promotion_basis"]


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_merges_into_existing_phone_user(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13800000002"

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)
    try:
        result = await service.bind_phone_for_wechat("student_demo", "phone-code-merge")
    finally:
        monkeypatch.undo()

    assert result["bound"] is True
    assert result["merged"] is True
    assert result["user_id"] == result["user"]["user_id"]
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


def test_report_analytics_stay_empty_before_any_assessment_or_practice(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    radar = service.get_radar_data("blank_user")
    dashboard = service.get_mastery_dashboard("blank_user")
    profile = service.get_assessment_profile("blank_user")

    assert radar["dimensions"] == []
    assert dashboard["overall_mastery"] == 0
    assert dashboard["groups"] == []
    assert dashboard["hotspots"] == []
    assert profile["score"] == 0
    assert profile["chapter_mastery"] == {}


def test_chat_learning_builds_provisional_report_analytics_without_assessment(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service.record_learning_activity(
        "blank_user",
        count=12,
        chapter="建筑构造",
        source="chat",
    )

    radar = service.get_radar_data("blank_user")
    dashboard = service.get_mastery_dashboard("blank_user")
    profile = service.get_assessment_profile("blank_user")

    assert any(item["label"] == "建筑构造" and item["score"] > 0 for item in radar["dimensions"])
    assert dashboard["overall_mastery"] > 0
    assert any(
        chapter["name"] == "建筑构造" and chapter["mastery"] > 0
        for group in dashboard["groups"]
        for chapter in group["chapters"]
    )
    assert profile["score"] > 0
    assert profile["chapter_mastery"]["建筑构造"]["mastery"] > 0


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
    assert result["user_id"] == profile["user_id"]
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


def test_send_phone_code_rejects_invalid_phone_input(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    with pytest.raises(ValueError, match="手机号格式不正确"):
        service.send_phone_code("dev-phone-code")


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


def test_auth_secret_rejects_wechat_secret_fallback_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("DEEPTUTOR_AUTH_SECRET", raising=False)
    monkeypatch.delenv("MEMBER_CONSOLE_AUTH_SECRET", raising=False)
    monkeypatch.setenv("WECHAT_MP_APP_SECRET", "wx_secret_only")

    with pytest.raises(RuntimeError, match="DEEPTUTOR_AUTH_SECRET must be configured in production"):
        service._auth_secret()


def test_auth_secret_allows_explicit_member_console_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MemberConsoleService()
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.delenv("DEEPTUTOR_AUTH_SECRET", raising=False)
    monkeypatch.setenv("MEMBER_CONSOLE_AUTH_SECRET", "member_console_secret")

    assert service._auth_secret() == "member_console_secret"


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
    assert result["user_id"] == result["user"]["user_id"]
    assert result["phone"] == "13911112222"


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_accepts_normalized_phone_for_legacy_clients(
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    result = await service.bind_phone_for_wechat("student_demo", "13911112222")

    assert result["bound"] is True
    assert result["user_id"] == result["user"]["user_id"]
    assert result["phone"] == "13911112222"


@pytest.mark.asyncio
async def test_login_with_wechat_code_reuses_merged_canonical_member_after_phone_bind(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    wallet_service = _FakeWalletBootstrapService()
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    async def _fake_exchange(_code: str) -> dict[str, str]:
        return {
            "openid": "openid_123456789012",
            "unionid": "unionid_abcdef",
            "session_key": "session_key_value",
        }

    async def _fake_exchange_phone_code(_phone_code: str) -> str:
        return "13800000002"

    monkeypatch.setattr(service, "_exchange_wechat_code", _fake_exchange)
    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _fake_exchange_phone_code)
    monkeypatch.setattr(service, "_get_wallet_service", lambda: wallet_service)
    monkeypatch.setattr(
        member_service_module,
        "ensure_external_auth_user_for_phone",
        lambda phone: {"id": canonical_uid, "username": "user_0002", "phone": phone},
    )

    first_login = await service.login_with_wechat_code("wx-code")
    bind_result = await service.bind_phone_for_wechat(first_login["user_id"], "phone-code-merge")
    second_login = await service.login_with_wechat_code("wx-code")
    second_claims = service.verify_access_token(second_login["token"])

    assert bind_result["merged"] is True
    assert bind_result["user_id"] == "student_risk"
    assert second_login["user_id"] == "student_risk"
    assert second_login["user"]["user_id"] == "student_risk"
    assert second_claims is not None
    assert second_claims["canonical_uid"] == canonical_uid
    assert second_claims["uid"] == canonical_uid
    assert wallet_service.calls[-1]["user_id"] == canonical_uid


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_maps_upstream_timeout_to_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    async def _raise_timeout(_phone_code: str) -> str:
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _raise_timeout)

    with pytest.raises(RuntimeError, match="WeChat getuserphonenumber request timed out"):
        await service.bind_phone_for_wechat("student_demo", "phone-code-123")


@pytest.mark.asyncio
async def test_bind_phone_for_wechat_fails_closed_in_production_even_for_dev_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    monkeypatch.setenv("DEEPTUTOR_ENV", "production")
    monkeypatch.setenv("DEEPTUTOR_ALLOW_DEV_WECHAT_LOGIN", "1")

    async def _raise_exchange(_phone_code: str) -> str:
        raise RuntimeError("wechat phone exchange failed")

    monkeypatch.setattr(service, "_exchange_wechat_phone_code", _raise_exchange)

    with pytest.raises(RuntimeError, match="wechat phone exchange failed"):
        await service.bind_phone_for_wechat("student_demo", "dev-phone-code")


def test_list_members_supports_expiry_window_and_operational_flags(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("vip_soon"),
                "display_name": "即将到期会员",
                "phone": "15558866501",
                "tier": "vip",
                "status": "active",
                "risk_level": "high",
                "expire_at": "2026-04-25T00:00:00+08:00",
                "last_active_at": "2026-04-20T10:00:00+08:00",
                "auto_renew": False,
            },
            {
                **service._build_default_member("svip_safe"),
                "display_name": "稳定会员",
                "phone": "15558866502",
                "tier": "svip",
                "status": "active",
                "risk_level": "low",
                "expire_at": "2026-08-01T00:00:00+08:00",
                "last_active_at": "2026-04-22T09:00:00+08:00",
                "auto_renew": True,
            },
        ]

    service._mutate(_seed)

    result = service.list_members(
        page=1,
        page_size=20,
        tier="vip",
        risk_level="high",
        expire_within_days=7,
        auto_renew=False,
    )

    assert [item["user_id"] for item in result["items"]] == ["vip_soon"]
    assert result["filters"]["expire_within_days"] == 7


def test_list_members_and_dashboard_use_canonical_phone_backed_members(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {
                **service._build_default_member("wx_live_alias"),
                "display_name": "微信入口会员",
                "phone": "15558866508",
                "external_auth_user_id": canonical_uid,
                "last_active_at": "2026-04-21T09:00:00+08:00",
                "points_balance": 80,
            },
            {
                **service._build_default_member(canonical_uid),
                "display_name": "正式注册会员",
                "phone": "15558866508",
                "external_auth_user_id": canonical_uid,
                "last_active_at": "2026-04-22T10:00:00+08:00",
                "points_balance": 260,
                "ledger": [{"id": "ledger_live", "created_at": "2026-04-22T10:00:00+08:00"}],
            },
            {
                **service._build_default_member("codex_probe_user"),
                "display_name": "codex 测试账号",
                "phone": "16600000001",
            },
            {
                **service._build_default_member("casefix_1776476492"),
                "display_name": "casefix 内部回归账号",
                "phone": "13976476492",
            },
            {
                **service._build_default_member("anonymous_no_phone"),
                "display_name": "未绑手机号账号",
                "phone": "",
            },
            {
                **service._build_default_member("student_lapsed"),
                "display_name": "内置演示会员",
                "phone": "13800000004",
            },
        ]

    service._mutate(_seed)

    result = service.list_members(page=1, page_size=20, sort="last_active_at", order="desc")
    dashboard = service.get_dashboard()

    assert result["total"] == 1
    assert [item["user_id"] for item in result["items"]] == [canonical_uid]
    assert result["items"][0]["display_name"] == "正式注册会员"
    assert result["items"][0]["phone"] == "15558866508"
    assert result["items"][0]["points_balance"] == 260
    assert dashboard["total_count"] == 1
    assert dashboard["active_count"] == 1


def test_batch_update_members_returns_success_and_failure_buckets(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    def _seed(data: dict[str, object]) -> None:
        data["members"] = [
            {**service._build_default_member("u1"), "tier": "trial"},
            {**service._build_default_member("u2"), "tier": "trial"},
        ]

    service._mutate(_seed)

    result = service.batch_update_members(
        user_ids=["u1", "u2", "missing"],
        action="grant",
        tier="vip",
        days=30,
        operator="admin_demo",
        reason="批量开通",
    )

    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert result["failed"][0]["user_id"] == "missing"


def test_list_audit_log_supports_target_user_and_action_filters(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    service._append_audit_log(
        {
            "id": "audit_1",
            "target_user": "u1",
            "operator": "admin_demo",
            "action": "grant",
            "reason": "manual",
            "created_at": "2026-04-22T10:00:00+08:00",
        }
    )
    service._append_audit_log(
        {
            "id": "audit_2",
            "target_user": "u2",
            "operator": "admin_demo",
            "action": "revoke",
            "reason": "manual",
            "created_at": "2026-04-22T11:00:00+08:00",
        }
    )

    result = service.list_audit_log(page=1, page_size=20, target_user="u1", action="grant")

    assert [item["id"] for item in result["items"]] == ["audit_1"]


def test_record_ops_action_result_writes_note_and_audit_loop(tmp_path: Path) -> None:
    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"

    result = service.record_ops_action_result(
        "student_demo",
        status="done",
        result="已电话回访，确认本周续费",
        action_title="即将到期会员",
        next_follow_up_at="2026-04-26",
        operator="admin_demo",
    )

    assert result["status"] == "done"
    assert result["result"] == "已电话回访，确认本周续费"
    assert result["note"]["channel"] == "ops_action"
    assert "处理状态：done" in result["note"]["content"]
    assert "处理结果：已电话回访，确认本周续费" in result["note"]["content"]

    detail = service.get_member_360("student_demo")
    assert detail["recent_notes"][0]["id"] == result["note"]["id"]

    audit = service.list_audit_log(target_user="student_demo", action="ops_action_result")
    assert audit["total"] == 1
    assert audit["items"][0]["operator"] == "admin_demo"
    assert audit["items"][0]["after"]["status"] == "done"
    assert audit["items"][0]["after"]["note_id"] == result["note"]["id"]
    assert audit["items"][0]["after"]["next_follow_up_at"] == "2026-04-26"
