#!/usr/bin/env python3
"""Remap a v2.3 near-live shadow A/B artifact onto a frozen-axis runtime token pack.

The taxonomy axis was rebuilt (v2.3 leaf ids -> frozen v1 leaf ids) while
``unit_id`` stayed stable across packs. This runner rewrites each
``rich_leaf_v23_context`` row's ``leaf_id`` to the frozen-axis placement of the
same runtime unit so the candidate bridge can join rows to frozen-axis units.

Review-only: outcomes (answerable / matches_expected / evidence_cited) are
inherited from the v2.3 near-live proxy run and are NOT re-evaluated against
recompiled context. The output records this in ``remap_lineage`` and
``not_exercised``. No learner memory, canonical truth, or runtime install.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
PACK_SCHEMA = "luban_rich_leaf_runtime_token_pack.v2.3"
PACK_STATUS = "candidate_ready_for_shadow_ab_full_accounted"
AB_SCHEMA = "luban_rich_leaf_v23_near_live_shadow_ab.v1"
RICH_ARM = "rich_leaf_v23_context"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _pack_blockers(name: str, pack: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if pack.get("schema") != PACK_SCHEMA:
        blockers.append(f"{name}:schema_mismatch:{pack.get('schema')}")
    if pack.get("status") != PACK_STATUS:
        blockers.append(f"{name}:bad_status:{pack.get('status')}")
    return blockers


def build_frozen_axis_near_live_ab_remap(
    *,
    near_live_ab: dict[str, Any],
    source_pack: dict[str, Any],
    target_pack: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if near_live_ab.get("schema") != AB_SCHEMA:
        blockers.append(f"near_live_ab:schema_mismatch:{near_live_ab.get('schema')}")
    blockers.extend(_pack_blockers("source_pack", source_pack))
    blockers.extend(_pack_blockers("target_pack", target_pack))

    source_units = [u for u in source_pack.get("runtime_token_pack_units") or [] if isinstance(u, dict)]
    target_units = [u for u in target_pack.get("runtime_token_pack_units") or [] if isinstance(u, dict)]
    source_ids = [str(u.get("unit_id") or "") for u in source_units]
    target_ids = [str(u.get("unit_id") or "") for u in target_units]
    if set(source_ids) != set(target_ids) or len(source_ids) != len(target_ids):
        blockers.append("unit_id_sets_differ_between_packs")

    rows = [row for row in near_live_ab.get("rows") or [] if isinstance(row, dict)]
    rich_rows = [row for row in rows if row.get("arm") == RICH_ARM]
    other_rows = [row for row in rows if row.get("arm") != RICH_ARM]
    if not rich_rows:
        blockers.append("no_rich_leaf_rows")

    remapped: list[dict[str, Any]] = []
    if not blockers:
        units_by_leaf: dict[str, list[dict[str, Any]]] = {}
        for unit in source_units:
            units_by_leaf.setdefault(str(unit.get("leaf_id") or ""), []).append(unit)
        target_by_unit_id = {str(u.get("unit_id") or ""): u for u in target_units}
        target_order = {unit_id: index for index, unit_id in enumerate(target_ids)}
        leaf_offsets: dict[str, int] = {}
        pairs: list[tuple[int, dict[str, Any]]] = []
        for row in rich_rows:
            leaf_id = str(row.get("leaf_id") or "")
            leaf_units = units_by_leaf.get(leaf_id) or []
            offset = leaf_offsets.get(leaf_id, 0)
            leaf_offsets[leaf_id] = offset + 1
            if offset >= len(leaf_units):
                blockers.append(f"row_without_source_unit:{row.get('case_id')}:{leaf_id}")
                continue
            unit_id = str(leaf_units[offset].get("unit_id") or "")
            target_unit = target_by_unit_id.get(unit_id)
            if target_unit is None:
                blockers.append(f"unit_missing_in_target_pack:{unit_id}")
                continue
            new_row = dict(row)
            new_row["leaf_id"] = str(target_unit.get("leaf_id") or "")
            new_row["remapped_from_leaf_id"] = leaf_id
            new_row["remapped_unit_id"] = unit_id
            pairs.append((target_order.get(unit_id, len(target_ids)), new_row))
        # Per-leaf row order must follow target pack unit order so the bridge's
        # sequential per-leaf join pairs each row with its own unit.
        remapped = [row for _, row in sorted(pairs, key=lambda item: item[0])]

    if blockers:
        return {
            "schema": AB_SCHEMA,
            "verdict": "FAIL_FROZEN_AXIS_REMAP",
            "blockers": blockers,
            "rows": [],
            "quality_claim_allowed": False,
        }

    report = {key: value for key, value in near_live_ab.items() if key != "rows"}
    report["rows"] = other_rows + remapped
    report["remap_lineage"] = {
        "remapped_by": "run_luban_rich_leaf_frozen_axis_near_live_ab_remap",
        "remapped_rich_leaf_row_count": len(remapped),
        "source_pack_version": str(source_pack.get("version") or ""),
        "target_pack_version": str(target_pack.get("version") or ""),
        "outcomes_inherited_from_v23_proxy": True,
    }
    report["not_exercised"] = sorted(
        set(list(near_live_ab.get("not_exercised") or []))
        | {"frozen_axis_near_live_rerun_with_recompiled_context"}
    )
    report["blockers"] = list(near_live_ab.get("blockers") or [])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--near-live-ab", type=Path, required=True)
    parser.add_argument("--source-pack", type=Path, required=True)
    parser.add_argument("--target-pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    report = build_frozen_axis_near_live_ab_remap(
        near_live_ab=_read_json(args.near_live_ab),
        source_pack=_read_json(args.source_pack),
        target_pack=_read_json(args.target_pack),
    )
    _write_json(args.output, report)
    summary = {
        "output": str(args.output),
        "verdict": report.get("verdict"),
        "row_count": len(report.get("rows") or []),
        "blocker_count": len(report.get("blockers") or []),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if report.get("verdict") != "FAIL_FROZEN_AXIS_REMAP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
