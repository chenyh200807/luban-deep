from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.wallet_authority_common import discover_repo_root, ensure_output_dir, write_json
except ModuleNotFoundError:
    from wallet_authority_common import discover_repo_root, ensure_output_dir, write_json


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _read_inventory_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _confidence_for_alias(alias_type: str) -> float:
    if alias_type == "external_auth_user_id":
        return 1.0
    if alias_type in {"wx_unionid", "wx_openid"}:
        return 0.95
    if alias_type in {"legacy_user_id", "auth_username", "phone"}:
        return 0.9
    return 0.8


def build_alias_upserts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    canonical_by_member: dict[str, str] = {}
    conflict_members: set[str] = set()
    for row in rows or []:
        member_user_id = _normalize_text(row.get("member_user_id"))
        canonical_user_id = _normalize_text(row.get("canonical_user_id"))
        if not member_user_id or not canonical_user_id:
            continue
        existing = canonical_by_member.get(member_user_id)
        if existing and existing != canonical_user_id:
            conflict_members.add(member_user_id)
            continue
        canonical_by_member[member_user_id] = canonical_user_id

    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows or []:
        alias_type = _normalize_text(row.get("alias_type"))
        alias_value = _normalize_text(row.get("alias_value"))
        member_user_id = _normalize_text(row.get("member_user_id"))
        if not alias_type or not alias_value or not member_user_id or member_user_id in conflict_members:
            continue
        canonical_user_id = _normalize_text(row.get("canonical_user_id")) or canonical_by_member.get(member_user_id, "")
        if not canonical_user_id:
            continue
        grouped[(alias_type, alias_value)].add(canonical_user_id)

    upserts: list[dict[str, Any]] = []
    for row in rows or []:
        alias_type = _normalize_text(row.get("alias_type"))
        alias_value = _normalize_text(row.get("alias_value"))
        member_user_id = _normalize_text(row.get("member_user_id"))
        canonical_user_id = _normalize_text(row.get("canonical_user_id")) or canonical_by_member.get(member_user_id, "")
        if not alias_type or not alias_value or not member_user_id or not canonical_user_id:
            continue
        if member_user_id in conflict_members:
            continue
        if len(grouped[(alias_type, alias_value)]) != 1:
            continue
        candidate = {
            "alias_type": alias_type,
            "alias_value": alias_value,
            "user_id": canonical_user_id,
            "source": "member_console_backfill",
            "confidence": _confidence_for_alias(alias_type),
            "metadata": {"member_user_id": member_user_id},
        }
        if candidate not in upserts:
            upserts.append(candidate)
        if alias_type != "legacy_user_id":
            legacy_alias = {
                "alias_type": "legacy_user_id",
                "alias_value": member_user_id,
                "user_id": canonical_user_id,
                "source": "member_console_backfill",
                "confidence": 0.9,
                "metadata": {"member_user_id": member_user_id},
            }
            if len(grouped[(legacy_alias["alias_type"], legacy_alias["alias_value"])]) <= 1 and legacy_alias not in upserts:
                upserts.append(legacy_alias)
    upserts.sort(key=lambda item: (item["alias_type"], item["alias_value"], item["user_id"]))
    return upserts


def _render_upsert_sql(upserts: list[dict[str, Any]]) -> list[str]:
    lines = [
        "begin;",
        "insert into public.user_identity_aliases (alias_type, alias_value, user_id, source, confidence, metadata)",
        "values",
    ]
    values: list[str] = []
    for item in upserts:
        values.append(
            "  ({alias_type}, {alias_value}, {user_id}::uuid, {source}, {confidence}, {metadata}::jsonb)".format(
                alias_type=json.dumps(item["alias_type"], ensure_ascii=False),
                alias_value=json.dumps(item["alias_value"], ensure_ascii=False),
                user_id=json.dumps(item["user_id"], ensure_ascii=False),
                source=json.dumps(item["source"], ensure_ascii=False),
                confidence=item["confidence"],
                metadata=json.dumps(item["metadata"], ensure_ascii=False),
            )
        )
    if values:
        lines.append(",\n".join(values))
        lines.append("on conflict (alias_type, alias_value) do update")
        lines.append("set user_id = excluded.user_id,")
        lines.append("    source = excluded.source,")
        lines.append("    confidence = excluded.confidence,")
        lines.append("    metadata = excluded.metadata,")
        lines.append("    updated_at = now();")
    else:
        lines.append("  -- no alias rows eligible for upsert")
        lines.append("select 1;")
    lines.append("commit;")
    return lines


def _write_sql(path: Path, lines: list[str]) -> None:
    ensure_output_dir(path.parent)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_alias_backfill(*, output_dir: Path, inventory_path: Path) -> dict[str, Any]:
    ensure_output_dir(output_dir)
    rows = _read_inventory_rows(inventory_path)
    upserts = build_alias_upserts(rows)
    upserts_json_path = output_dir / "user_identity_aliases_upserts.json"
    upserts_sql_path = output_dir / "user_identity_aliases_upserts.sql"
    write_json(upserts_json_path, {"upserts": upserts})
    _write_sql(upserts_sql_path, _render_upsert_sql(upserts))
    return {
        "row_count": len(rows),
        "upsert_count": len(upserts),
        "artifacts": {
            "alias_upserts_json": str(upserts_json_path),
            "alias_upserts_sql": str(upserts_sql_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build user_identity_aliases backfill payloads from identity inventory CSV.")
    parser.add_argument("--output-dir", default="", help="Directory for generated artifacts.")
    parser.add_argument("--inventory-path", default="", help="Path to identity_inventory.csv")
    args = parser.parse_args()
    repo_root = discover_repo_root()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else repo_root / "artifacts" / "wallet_authority" / "identity_backfill"
    inventory_path = (
        Path(args.inventory_path).expanduser()
        if args.inventory_path
        else repo_root / "artifacts" / "wallet_authority" / "identity" / "identity_inventory.csv"
    )
    summary = export_alias_backfill(output_dir=output_dir, inventory_path=inventory_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
