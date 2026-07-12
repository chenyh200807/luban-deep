from __future__ import annotations

from typing import Any

from deeptutor.services.luban_lesson.read_model import list_green_lessons

_SOURCE_BACKED_PACKS = {
    "first_run.v1:qigu_gebu": {
        "target_pack_id": "F16",
        "source_refs": ["docs/原始数据/考点原料/成品/F16_屋面防水起鼓割补.md"],
    },
    "first_run.v1:zhuangpeishi_laji": {
        "target_pack_id": "X03",
        "source_refs": ["docs/原始数据/考点原料/成品/X03_文明绿色环保施工措施.md"],
    },
}


def resolve_first_run_prescription(
    scored_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve one honest first station from diagnostic evidence and live supply."""

    green_supply = {
        str(row.get("pack_id") or "").strip().upper(): dict(row)
        for row in list_green_lessons()
        if isinstance(row, dict)
    }
    missed = [dict(item) for item in scored_items if not item.get("is_correct")]
    focus_pool = missed or [dict(item) for item in scored_items]
    for item in focus_pool:
        mapping = _SOURCE_BACKED_PACKS.get(str(item.get("question_id") or "").strip())
        if not mapping:
            continue
        target = str(mapping["target_pack_id"]).upper()
        supply = green_supply.get(target) or {}
        if not supply.get("retest_available"):
            continue
        return {
            "focus_item": item,
            "target_pack_id": target,
            "mapping_refs": list(mapping["source_refs"]),
            "supply_verified": True,
        }
    return {
        "focus_item": focus_pool[0],
        "target_pack_id": "",
        "mapping_refs": [],
        "supply_verified": False,
    }


__all__ = ["resolve_first_run_prescription"]
