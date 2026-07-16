"""首跑处方解析——question→pack 映射必须对齐当前供给真值。

契约（contracts/learner-state.md · First Run §7）：question→pack 映射由
source-backed resolver 与当前 green+signed-retest supply **共同验证**。
映射表只声明候选序列（source-backed 的教研映射），可用性由
``list_green_lessons()`` 的 ``retest_available`` 真值过滤——不硬编码任何
pack 字面特权；候选全不可用时诚实返回无 pack 绑定（空 target），
不臆造第二真值（2026-07-16 QA 死证：F16/X03 停发后旧的单 pack 硬映射
恒产空 target，新用户首跑处方永不可执行）。
"""

from __future__ import annotations

from typing import Any

from deeptutor.services.luban_lesson.read_model import list_green_lessons

# 每题一个候选序列（有序）：首位是教研最贴题的 source-backed pack，
# 后位是供给停发时的次选。resolver 取第一个 supply-ready 的候选。
_SOURCE_BACKED_PACKS: dict[str, list[dict[str, Any]]] = {
    "first_run.v1:qigu_gebu": [
        {
            "target_pack_id": "F16",
            "source_refs": ["docs/原始数据/考点原料/成品/F16_屋面防水起鼓割补.md"],
        },
        {
            "target_pack_id": "N01",
            "source_refs": ["docs/原始数据/考点原料/成品/N01_网络计划关键线路.md"],
        },
    ],
    "first_run.v1:zhuangpeishi_laji": [
        {
            "target_pack_id": "X03",
            "source_refs": ["docs/原始数据/考点原料/成品/X03_文明绿色环保施工措施.md"],
        },
        {
            "target_pack_id": "N01",
            "source_refs": ["docs/原始数据/考点原料/成品/N01_网络计划关键线路.md"],
        },
    ],
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
        candidates = _SOURCE_BACKED_PACKS.get(str(item.get("question_id") or "").strip())
        for mapping in candidates or []:
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
