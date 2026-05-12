from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from deeptutor.services.wallet.identity import IdentityInventoryRow, collect_identity_inventory_rows
    from scripts.wallet_authority_common import discover_repo_root, ensure_output_dir
except ModuleNotFoundError:
    import sys

    CURRENT_DIR = Path(__file__).resolve().parent
    REPO_ROOT = CURRENT_DIR.parent
    for name in list(sys.modules):
        if name == "deeptutor" or name.startswith("deeptutor."):
            sys.modules.pop(name, None)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from deeptutor.services.wallet.identity import IdentityInventoryRow, collect_identity_inventory_rows
    from wallet_authority_common import discover_repo_root, ensure_output_dir


def _load_member_console_members(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    members = payload.get("members") if isinstance(payload, dict) else []
    return [dict(item) for item in members or [] if isinstance(item, dict)]


def _write_inventory_csv(path: Path, rows: list[IdentityInventoryRow]) -> None:
    ensure_output_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["alias_type", "alias_value", "member_user_id", "canonical_user_id", "source"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "alias_type": row.alias_type,
                    "alias_value": row.alias_value,
                    "member_user_id": row.member_user_id,
                    "canonical_user_id": row.canonical_user_id,
                    "source": row.source,
                }
            )


def _write_coverage_csv(path: Path, rows: list[IdentityInventoryRow]) -> None:
    ensure_output_dir(path.parent)
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "resolved": 0, "unresolved": 0})
    for row in rows:
        grouped[row.alias_type]["total"] += 1
        if row.canonical_user_id:
            grouped[row.alias_type]["resolved"] += 1
        else:
            grouped[row.alias_type]["unresolved"] += 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["alias_type", "total", "resolved", "unresolved"])
        writer.writeheader()
        for alias_type in sorted(grouped):
            writer.writerow({"alias_type": alias_type, **grouped[alias_type]})


def _write_conflicts_csv(path: Path, rows: list[IdentityInventoryRow]) -> None:
    ensure_output_dir(path.parent)
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        grouped[(row.alias_type, row.alias_value)].add(row.member_user_id)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["alias_type", "alias_value", "member_user_ids", "member_count"])
        writer.writeheader()
        for (alias_type, alias_value), member_ids in sorted(grouped.items()):
            if len(member_ids) <= 1:
                continue
            writer.writerow(
                {
                    "alias_type": alias_type,
                    "alias_value": alias_value,
                    "member_user_ids": ",".join(sorted(member_ids)),
                    "member_count": len(member_ids),
                }
            )


def export_identity_inventory(*, output_dir: Path, member_console_path: Path) -> dict[str, Any]:
    ensure_output_dir(output_dir)
    rows = collect_identity_inventory_rows(members=_load_member_console_members(member_console_path))
    inventory_path = output_dir / "identity_inventory.csv"
    coverage_path = output_dir / "alias_coverage.csv"
    conflicts_path = output_dir / "alias_conflicts.csv"
    _write_inventory_csv(inventory_path, rows)
    _write_coverage_csv(coverage_path, rows)
    _write_conflicts_csv(conflicts_path, rows)
    return {
        "output_dir": str(output_dir),
        "row_count": len(rows),
        "artifacts": {
            "identity_inventory_csv": str(inventory_path),
            "alias_coverage_csv": str(coverage_path),
            "alias_conflicts_csv": str(conflicts_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export wallet identity alias inventory from local member_console data.")
    parser.add_argument("--output-dir", default="", help="Directory for generated CSVs.")
    parser.add_argument("--member-console-path", default="", help="Path to member_console.json")
    args = parser.parse_args()
    repo_root = discover_repo_root()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else repo_root / "artifacts" / "wallet_authority" / "identity"
    member_console_path = (
        Path(args.member_console_path).expanduser()
        if args.member_console_path
        else repo_root / "data" / "member_console.json"
    )
    summary = export_identity_inventory(output_dir=output_dir, member_console_path=member_console_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
