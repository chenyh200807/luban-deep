from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "backfill_wallet_identity_canonical.py"
SPEC = importlib.util.spec_from_file_location("backfill_wallet_identity_canonical", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class _FakeIdentityStore:
    def __init__(self, rows: dict[tuple[str, str], dict[str, str]] | None = None) -> None:
        self.rows = rows or {}

    def resolve_alias(self, *, alias_type: str, alias_value: str):
        return self.rows.get((alias_type, alias_value))


class _FakeWalletService:
    is_configured = True

    def __init__(self, existing_wallets: set[str] | None = None) -> None:
        self.existing_wallets = set(existing_wallets or set())
        self.seed_calls: list[dict[str, object]] = []
        self.ledger_keys: set[tuple[str, str]] = set()

    def get_wallet(self, user_id: str):
        if user_id in self.existing_wallets:
            return {"user_id": user_id}
        return None

    def find_wallet_ledger_by_idempotency_key(self, user_id: str, *, idempotency_key: str):
        if (user_id, idempotency_key) in self.ledger_keys:
            return {"user_id": user_id, "idempotency_key": idempotency_key}
        return None

    def ensure_wallet_seeded(self, **kwargs):
        user_id = str(kwargs["user_id"])
        self.existing_wallets.add(user_id)
        key = str(kwargs.get("idempotency_key") or "").strip()
        if key:
            self.ledger_keys.add((user_id, key))
        self.seed_calls.append(dict(kwargs))
        return {"user_id": user_id}


class _FakeAdminClient:
    is_configured = True

    def __init__(
        self,
        *,
        users: set[str] | None = None,
        aliases: set[tuple[str, str, str]] | None = None,
    ) -> None:
        self.users = set(users or set())
        self.aliases = set(aliases or set())
        self.created_users: list[dict[str, object]] = []
        self.created_aliases: list[dict[str, object]] = []

    def user_exists(self, user_id: str) -> bool:
        return user_id in self.users

    def create_user(self, *, user_id: str, identifier: str, metadata: dict[str, object]) -> None:
        if user_id in self.users:
            return
        self.users.add(user_id)
        self.created_users.append(
            {
                "user_id": user_id,
                "identifier": identifier,
                "metadata": dict(metadata),
            }
        )

    def alias_exists(self, *, alias_type: str, alias_value: str, user_id: str) -> bool:
        return (alias_type, alias_value, user_id) in self.aliases

    def ensure_alias(self, *, alias_type: str, alias_value: str, user_id: str, metadata: dict[str, object]) -> None:
        key = (alias_type, alias_value, user_id)
        if key in self.aliases:
            return
        self.aliases.add(key)
        self.created_aliases.append(
            {
                "alias_type": alias_type,
                "alias_value": alias_value,
                "user_id": user_id,
                "metadata": dict(metadata),
            }
        )


class _FakeMemberService:
    def __init__(self, members: list[dict[str, object]]) -> None:
        self.members = [dict(item) for item in members]

    def _ensure_member(self, data: dict[str, object], user_id: str) -> dict[str, object]:
        for member in data["members"]:
            if member["user_id"] == user_id:
                return member
        raise KeyError(user_id)

    def _mutate(self, mutator):
        data = {"members": self.members}
        result = mutator(data)
        self.members = [dict(item) for item in data["members"]]
        return result


def test_build_backfill_actions_mints_uuid_for_unmapped_wx_member() -> None:
    member = {
        "user_id": "wx_legacy_1",
        "points_balance": 120,
        "tier": "trial",
        "wx_openid": "openid_1",
    }
    report = module.build_backfill_actions(
        members=[member],
        identity_store=_FakeIdentityStore(),
        wallet_service=_FakeWalletService(),
        admin_client=_FakeAdminClient(),
    )

    assert report["summary"]["wx_total"] == 1
    assert report["summary"]["planned_actions"] == 1
    assert report["summary"]["minted_canonical_uid"] == 1
    action = report["actions"][0]
    assert action["canonical_uid"] == module._mint_canonical_uid(member)
    assert action["resolution_source"] == "minted_uuid"
    assert action["needs_user_insert"] is True
    assert action["needs_wallet_seed"] is True
    assert action["needs_local_member_link"] is True
    assert ("legacy_user_id", "wx_legacy_1") in action["alias_inserts"]
    assert ("wx_openid", "openid_1") in action["alias_inserts"]


def test_build_backfill_actions_reuses_existing_alias_resolution() -> None:
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    wallet_service = _FakeWalletService(existing_wallets={canonical_uid})
    wallet_service.ledger_keys.add(
        (
            canonical_uid,
            module._migration_opening_balance_key(canonical_uid),
        )
    )
    report = module.build_backfill_actions(
        members=[
            {
                "user_id": "wx_legacy_2",
                "points_balance": 60,
                "wx_openid": "openid_2",
            }
        ],
        identity_store=_FakeIdentityStore(
            {
                ("wx_openid", "openid_2"): {"user_id": canonical_uid},
            }
        ),
        wallet_service=wallet_service,
        admin_client=_FakeAdminClient(
            users={canonical_uid},
            aliases={
                ("wx_openid", "openid_2", canonical_uid),
            },
        ),
    )

    assert report["summary"]["resolved_via_existing_alias"] == 1
    action = report["actions"][0]
    assert action["canonical_uid"] == canonical_uid
    assert action["needs_user_insert"] is False
    assert action["needs_wallet_seed"] is False
    assert action["needs_local_member_link"] is True
    assert action["alias_inserts"] == (("legacy_user_id", "wx_legacy_2"),)


def test_apply_backfill_actions_is_idempotent_on_second_run() -> None:
    member_service = _FakeMemberService(
        [
            {
                "user_id": "wx_legacy_3",
                "points_balance": 40,
                "tier": "trial",
                "wx_openid": "openid_3",
                "external_auth_user_id": "",
            }
        ]
    )
    admin_client = _FakeAdminClient()
    wallet_service = _FakeWalletService()
    report = module.build_backfill_actions(
        members=member_service.members,
        identity_store=_FakeIdentityStore(),
        wallet_service=wallet_service,
        admin_client=admin_client,
    )

    first_result = module.apply_backfill_actions(
        actions=report["actions"],
        member_service=member_service,
        wallet_service=wallet_service,
        admin_client=admin_client,
    )

    assert first_result["user_rows_inserted"] == 1
    assert first_result["alias_rows_inserted"] == 2
    assert first_result["wallets_seeded"] == 1
    assert first_result["local_members_linked"] == 1
    canonical_uid = member_service.members[0]["external_auth_user_id"]
    assert module.is_uuid_like(canonical_uid)

    second_report = module.build_backfill_actions(
        members=member_service.members,
        identity_store=_FakeIdentityStore(
            {
                ("legacy_user_id", "wx_legacy_3"): {"user_id": canonical_uid},
                ("wx_openid", "openid_3"): {"user_id": canonical_uid},
            }
        ),
        wallet_service=wallet_service,
        admin_client=admin_client,
    )

    assert second_report["summary"]["planned_actions"] == 0


def test_build_backfill_actions_marks_existing_wallet_without_opening_ledger_for_repair() -> None:
    canonical_uid = "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    wallet_service = _FakeWalletService(existing_wallets={canonical_uid})
    report = module.build_backfill_actions(
        members=[
            {
                "user_id": "wx_legacy_4",
                "points_balance": 120,
                "tier": "trial",
                "wx_openid": "openid_4",
                "external_auth_user_id": canonical_uid,
            }
        ],
        identity_store=_FakeIdentityStore(),
        wallet_service=wallet_service,
        admin_client=_FakeAdminClient(users={canonical_uid}),
    )

    assert report["summary"]["planned_actions"] == 1
    action = report["actions"][0]
    assert action["needs_wallet_seed"] is True
    assert action["needs_local_member_link"] is False
