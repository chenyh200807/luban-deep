from __future__ import annotations

import importlib


auth_module = importlib.import_module("deeptutor.api.dependencies.auth")


def test_resolve_auth_context_prefers_canonical_uid(monkeypatch) -> None:
    class _FakeMemberService:
        @staticmethod
        def verify_access_token(_token: str) -> dict[str, str]:
            return {
                "uid": "user_2008",
                "canonical_uid": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                "provider": "wechat_mp",
            }

        @staticmethod
        def is_admin_user(user_id: str) -> bool:
            return user_id == "admin_demo"

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberService())

    context = auth_module.resolve_auth_context("Bearer test-token")

    assert context is not None
    assert context.user_id == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert context.provider == "wechat_mp"
    assert context.claims["uid"] == "user_2008"


def test_resolve_auth_context_uses_alias_store_for_legacy_uid(monkeypatch) -> None:
    class _FakeMemberService:
        @staticmethod
        def verify_access_token(_token: str) -> dict[str, str]:
            return {"uid": "user_2008", "provider": "wechat_mp"}

        @staticmethod
        def is_admin_user(_user_id: str) -> bool:
            return False

    class _FakeStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            assert alias_value == "user_2008"
            if alias_type == "legacy_user_id":
                return {"user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"}
            return None

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberService())
    monkeypatch.setattr(auth_module, "get_wallet_identity_store", lambda: _FakeStore())

    context = auth_module.resolve_auth_context("Bearer test-token")

    assert context is not None
    assert context.user_id == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"


def test_resolve_wallet_user_id_uses_alias_store_for_legacy_uid(monkeypatch) -> None:
    class _FakeMemberService:
        @staticmethod
        def verify_access_token(_token: str) -> dict[str, str]:
            return {"uid": "user_2008"}

    class _FakeStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            assert alias_value == "user_2008"
            if alias_type == "legacy_user_id":
                return {"user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"}
            return None

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberService())
    monkeypatch.setattr(auth_module, "get_wallet_identity_store", lambda: _FakeStore())

    assert (
        auth_module.resolve_wallet_user_id("Bearer test-token")
        == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    )


def test_resolve_wallet_user_id_checks_auth_username_when_legacy_alias_misses(monkeypatch) -> None:
    class _FakeMemberService:
        @staticmethod
        def verify_access_token(_token: str) -> dict[str, str]:
            return {"uid": "chenyh2008"}

    class _FakeStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "legacy_user_id":
                return None
            if alias_type == "auth_username":
                if alias_value == "auth_2d9eac155d264e93941b9ec6":
                    return None
                assert alias_value == "chenyh2008"
                return {"user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"}
            return None

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberService())
    monkeypatch.setattr(auth_module, "get_wallet_identity_store", lambda: _FakeStore())

    assert (
        auth_module.resolve_wallet_user_id("Bearer test-token")
        == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    )


def test_resolve_wallet_user_id_falls_back_to_raw_legacy_uid_when_alias_store_unavailable(
    monkeypatch,
) -> None:
    class _FakeMemberService:
        @staticmethod
        def verify_access_token(_token: str) -> dict[str, str]:
            return {"uid": "user_2008"}

    class _FakeStore:
        is_configured = False

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            raise AssertionError("should not query alias store when it is not configured")

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberService())
    monkeypatch.setattr(auth_module, "get_wallet_identity_store", lambda: _FakeStore())

    assert auth_module.resolve_wallet_user_id("Bearer test-token") == "user_2008"


def test_resolve_wallet_user_id_reads_member_snapshot_for_legacy_auth_user(monkeypatch) -> None:
    class _FakeMemberService:
        @staticmethod
        def verify_access_token(_token: str) -> dict[str, str]:
            return {"uid": "auth_2d9eac155d264e93941b9ec6"}

        @staticmethod
        def _load_member_snapshot(user_id: str) -> dict[str, object]:
            assert user_id == "auth_2d9eac155d264e93941b9ec6"
            return {
                "member": {
                    "user_id": user_id,
                    "auth_username": "chenyh2008",
                    "external_auth_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
                }
            }

    class _FakeStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "legacy_user_id":
                return None
            if alias_type == "auth_username":
                if alias_value == "auth_2d9eac155d264e93941b9ec6":
                    return None
                assert alias_value == "chenyh2008"
                return {"user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"}
            return None

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberService())
    monkeypatch.setattr(auth_module, "get_wallet_identity_store", lambda: _FakeStore())

    assert (
        auth_module.resolve_wallet_user_id("Bearer test-token")
        == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    )


def test_resolve_wallet_user_id_reads_member_store_when_snapshot_loader_missing(monkeypatch) -> None:
    class _FakeMemberService:
        @staticmethod
        def verify_access_token(_token: str) -> dict[str, str]:
            return {"uid": "auth_2d9eac155d264e93941b9ec6"}

        @staticmethod
        def _load() -> dict[str, object]:
            return {
                "members": [
                    {
                        "user_id": "auth_2d9eac155d264e93941b9ec6",
                        "auth_username": "chenyh2008",
                    }
                ]
            }

    class _FakeStore:
        is_configured = True

        @staticmethod
        def resolve_alias(*, alias_type: str, alias_value: str):
            if alias_type == "legacy_user_id":
                return None
            if alias_type == "auth_username":
                if alias_value == "auth_2d9eac155d264e93941b9ec6":
                    return None
                assert alias_value == "chenyh2008"
                return {"user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"}
            return None

    monkeypatch.setattr(auth_module, "get_member_console_service", lambda: _FakeMemberService())
    monkeypatch.setattr(auth_module, "get_wallet_identity_store", lambda: _FakeStore())

    assert (
        auth_module.resolve_wallet_user_id("Bearer test-token")
        == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    )
