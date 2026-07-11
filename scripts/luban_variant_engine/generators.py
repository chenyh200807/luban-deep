"""判定原语生成器：spec → variants（生成侧判定；与 verdict.py 独立第二实现互证）。

v0 覆盖试点 X02 所需三形态 + dual_membership（对偶强制成对, F16 试点用）;
sequence/predicate/cases 随 F16/G03/E05 试点补齐——添加时同步 verdict.py。
生成顺序 = spec 声明顺序 × 取值域声明顺序（确定性; variant_id 流水号与
旧 builder 语义一致——迁移期保 ID 连续性, 用户当日抽题不漂移）。
"""
from __future__ import annotations

from itertools import product
from typing import Any

from .spec import SpecError, _threshold_ok


def generate(spec: dict[str, Any]) -> list[dict[str, Any]]:
    pack_id = spec["pack_id"]
    variants: list[dict[str, Any]] = []

    def add(group_id: str, surface: str, params: dict[str, Any], ok: bool,
            correct: str, anchor: str, extension: bool = False) -> None:
        variants.append({
            "variant_id": f"{pack_id}-{group_id}-{len(variants):03d}",
            "rule_group": group_id,
            "surface": surface,
            "params": params,
            "expected_ok": bool(ok),
            "correct_statement": correct,
            "anchor": anchor,
            "extension": bool(extension),
        })

    skins = tuple(spec.get("site_skins") or ("",))
    for group in spec["rule_groups"]:
        kind = group["kind"]
        if kind == "threshold":
            _gen_threshold(group, skins, add)
        elif kind == "enum_exact":
            _gen_enum_exact(group, skins, add)
        elif kind == "dual_membership":
            _gen_dual_membership(group, skins, add)
        elif kind == "cases":
            _gen_cases(group, add)
        else:
            raise SpecError(f"kind {kind!r} 生成器尚未实现(随试点补齐, 禁静默跳过)")
    return variants


def _fmt(template: str, skin: str, value: Any, extra: dict[str, Any] | None = None) -> str:
    fields = {"skin": skin, "value": value}
    fields.update(extra or {})
    return template.format(**fields)


def _gen_threshold(group: dict[str, Any], skins: tuple, add) -> None:
    rows = (group.get("params_axis") or {}).get("rows") or [group]
    op = group.get("verdict_op") or ">="
    for row in rows:
        thr = row.get("thr", group.get("thr"))
        values = row.get("values", group.get("values")) or []
        surface_tpl = row.get("surface", group.get("surface"))
        param_key = row.get("param_key", group.get("param_key") or "value")
        extra = {k: row[k] for k in ("label", "unit") if k in row}
        for skin, value in product(skins, values):
            add(group["id"], _fmt(surface_tpl, skin, value, extra),
                {param_key: value}, _threshold_ok(op, value, thr),
                group["correct_statement"], group["anchor"],
                group.get("extension", False))


def _gen_enum_exact(group: dict[str, Any], skins: tuple, add) -> None:
    param_key = group.get("param_key") or "value"
    for skin, member in product(skins, group["enum"]):
        add(group["id"], _fmt(group["surface"], skin, member),
            {param_key: member}, member == group["correct_value"],
            group["correct_statement"], group["anchor"],
            group.get("extension", False))


def _gen_dual_membership(group: dict[str, Any], skins: tuple, add) -> None:
    """对偶强制成对（红队工单核心）：每 item 必出 正例(列入=妥) + 反例(认为无需=不妥)。

    引擎层保证成对——句式壳与答案的相关性因此归零（"认为"句不再恒错）。"""
    param_key = group.get("param_key") or "item"
    for skin, item in product(skins, group["enum"]):
        add(group["id"], _fmt(group["surface_pos"], skin, item),
            {param_key: item, "polarity": "pos"}, True,
            group["correct_statement"], group["anchor"], group.get("extension", False))
        add(group["id"], _fmt(group["surface_neg"], skin, item),
            {param_key: item, "polarity": "neg"}, False,
            group["correct_statement"], group["anchor"], group.get("extension", False))


def _gen_cases(group: dict[str, Any], add) -> None:
    for case in group["cases"]:
        add(group["id"], case["surface"],
            dict(case.get("params") or {"case": case.get("case", "")}),
            bool(case["expected_ok"]),
            case.get("correct_statement", group["correct_statement"]),
            case.get("anchor", group["anchor"]),
            case.get("extension", group.get("extension", False)))
