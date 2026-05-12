from __future__ import annotations

from pathlib import Path

from scripts.backfill_wallet_identity_aliases import build_alias_upserts, export_alias_backfill
from scripts.wallet_authority_common import load_json


def test_build_alias_upserts_promotes_uuid_and_skips_conflicts() -> None:
    rows = [
        {
            "alias_type": "legacy_user_id",
            "alias_value": "user_2008",
            "member_user_id": "user_2008",
            "canonical_user_id": "",
            "source": "member_console",
        },
        {
            "alias_type": "external_auth_user_id",
            "alias_value": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "member_user_id": "user_2008",
            "canonical_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "source": "member_console",
        },
        {
            "alias_type": "auth_username",
            "alias_value": "chenyh2008",
            "member_user_id": "user_2008",
            "canonical_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "source": "member_console",
        },
        {
            "alias_type": "auth_username",
            "alias_value": "chenyh2008",
            "member_user_id": "user_shadow",
            "canonical_user_id": "11111111-1111-4111-8111-111111111111",
            "source": "member_console",
        },
    ]

    upserts = build_alias_upserts(rows)

    assert {
        "alias_type": "external_auth_user_id",
        "alias_value": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        "source": "member_console_backfill",
        "confidence": 1.0,
        "metadata": {"member_user_id": "user_2008"},
    } in upserts
    assert {
        "alias_type": "legacy_user_id",
        "alias_value": "user_2008",
        "user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
        "source": "member_console_backfill",
        "confidence": 0.9,
        "metadata": {"member_user_id": "user_2008"},
    } in upserts
    assert not any(item["alias_type"] == "auth_username" and item["alias_value"] == "chenyh2008" for item in upserts)


def test_export_alias_backfill_writes_json_and_sql(tmp_path: Path) -> None:
    inventory_path = tmp_path / "identity_inventory.csv"
    inventory_path.write_text(
        "\n".join(
            [
                "alias_type,alias_value,member_user_id,canonical_user_id,source",
                "external_auth_user_id,2d9eac15-5d26-4e93-941b-9ec6345ce6d9,user_2008,2d9eac15-5d26-4e93-941b-9ec6345ce6d9,member_console",
                "auth_username,chenyh2008,user_2008,2d9eac15-5d26-4e93-941b-9ec6345ce6d9,member_console",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = export_alias_backfill(output_dir=tmp_path / "out", inventory_path=inventory_path)

    payload = load_json(Path(summary["artifacts"]["alias_upserts_json"]))
    assert len(payload["upserts"]) == 3
    assert Path(summary["artifacts"]["alias_upserts_sql"]).exists()
