"""独立一致性判定（双推互证的第二实现）：从 variant.params 重推 expected_ok。

与 generators.py 的关键差异：不走生成路径, 只看 params + spec 规则声明——
生成器的模板/参数错配、取值域漂移在 gate 比对时现形（继承 18 个旧 builder
的 `_independent_verdict` 机制, 收敛为按 kind 的通用解释器）。
返回 None = 判定不出（域外值/未知组）→ gate 记 mismatch（fail-closed）。
"""
from __future__ import annotations

from typing import Any

from .spec import _threshold_ok


def independent_verdict(spec: dict[str, Any], variant: dict[str, Any]) -> bool | None:
    group = next(
        (g for g in spec["rule_groups"] if g["id"] == variant.get("rule_group")), None)
    if group is None:
        return None
    params = variant.get("params") or {}
    kind = group["kind"]

    if kind == "threshold":
        rows = (group.get("params_axis") or {}).get("rows") or [group]
        op = group.get("verdict_op") or ">="
        for row in rows:
            key = row.get("param_key", group.get("param_key") or "value")
            if key in params:
                thr = row.get("thr", group.get("thr"))
                value = params[key]
                values = row.get("values", group.get("values")) or []
                if value not in values:
                    return None  # 封闭取值域外不许出现
                return _threshold_ok(op, value, thr)
        return None

    if kind == "enum_exact":
        key = group.get("param_key") or "value"
        member = params.get(key)
        if member not in (group.get("enum") or []):
            return None
        return member == group["correct_value"]

    if kind == "dual_membership":
        key = group.get("param_key") or "item"
        if params.get(key) not in (group.get("enum") or []):
            return None
        polarity = params.get("polarity")
        if polarity not in ("pos", "neg"):
            return None
        return polarity == "pos"

    if kind == "cases":
        # cases 的判定真值在 spec 声明本身——独立核验=按 surface 回查声明
        for case in group.get("cases") or []:
            if case["surface"] == variant.get("surface"):
                return bool(case["expected_ok"])
        return None

    return None
