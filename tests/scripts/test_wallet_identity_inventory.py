from __future__ import annotations

from pathlib import Path

from scripts.audit_wallet_identity_inventory import export_identity_inventory


def test_export_identity_inventory_writes_expected_csv_files(tmp_path: Path) -> None:
    member_console_path = tmp_path / "member_console.json"
    member_console_path.write_text(
        """
{
  "members": [
    {
      "user_id": "user_2008",
      "auth_username": "chenyh2008",
      "external_auth_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
      "wx_openid": "openid_123",
      "wx_unionid": "union_123",
      "phone": "13812345678"
    }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    summary = export_identity_inventory(
        output_dir=tmp_path / "out",
        member_console_path=member_console_path,
    )

    assert summary["row_count"] == 6
    assert (tmp_path / "out" / "identity_inventory.csv").exists()
    assert (tmp_path / "out" / "alias_coverage.csv").exists()
    assert (tmp_path / "out" / "alias_conflicts.csv").exists()
