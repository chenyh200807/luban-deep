"""变体 spec 加载与校验（数据即规则；spec 不合格 = fail-closed 拒绝生成）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SPEC_DIR = REPO / "docs" / "原始数据" / "考点原料" / "variant_specs"

_KINDS = {"threshold", "enum_exact", "dual_membership", "sequence", "cases", "predicate"}
_REQUIRED_GROUP_FIELDS = {"id", "kind", "anchor", "correct_statement"}


class SpecError(Exception):
    """spec 结构/健康检查不过：不生成（宁缺勿假）。"""


def load_spec(pack_id: str, spec_dir: Path | None = None) -> dict[str, Any]:
    path = (spec_dir or SPEC_DIR) / f"{pack_id.upper()}.variant.json"
    if not path.exists():
        raise SpecError(f"spec 不存在: {path}")
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SpecError(f"spec 解析失败: {path} ({exc})")
    validate_spec(spec)
    return spec


def validate_spec(spec: dict[str, Any]) -> None:
    for key in ("pack_id", "pack_file", "schema_version", "rule_groups"):
        if not spec.get(key):
            raise SpecError(f"spec 缺必填字段: {key}")
    seen_ids: set[str] = set()
    for group in spec["rule_groups"]:
        missing = _REQUIRED_GROUP_FIELDS - set(group)
        if missing:
            raise SpecError(f"rule_group {group.get('id')!r} 缺字段 {sorted(missing)}")
        if group["kind"] not in _KINDS:
            raise SpecError(f"rule_group {group['id']} 未知 kind: {group['kind']}")
        if group["id"] in seen_ids:
            raise SpecError(f"rule_group id 重复: {group['id']}")
        seen_ids.add(group["id"])
        _validate_group_health(group)


def _validate_group_health(group: dict[str, Any]) -> None:
    """健康检查——收敛谱第四节:防"退化单极"病（J01 样板的机制保证）。"""
    kind = group["kind"]
    if kind == "threshold":
        for row in (group.get("params_axis") or {}).get("rows") or [{}]:
            thr = row.get("thr", group.get("thr"))
            values = row.get("values", group.get("values")) or []
            op = group.get("verdict_op") or ">="
            if thr is None or not values:
                raise SpecError(f"threshold 组 {group['id']} 缺 thr/values")
            oks = [_threshold_ok(op, v, thr) for v in values]
            if all(oks) or not any(oks):
                raise SpecError(
                    f"threshold 组 {group['id']} 取值域未横跨阈值(全 {'妥' if all(oks) else '不妥'})"
                    f"——退化单极, 违反健康样板机制: values={values} thr={thr} op={op}")
    if kind == "enum_exact":
        enum = group.get("enum") or []
        correct = group.get("correct_value")
        if correct not in enum:
            raise SpecError(f"enum_exact 组 {group['id']} correct_value 不在 enum 内")
        if len(enum) < 2:
            raise SpecError(f"enum_exact 组 {group['id']} enum 少于 2 值=无判别力")
    if kind == "dual_membership":
        if not group.get("enum") or not group.get("surface_pos") or not group.get("surface_neg"):
            raise SpecError(f"dual_membership 组 {group['id']} 缺 enum/surface_pos/surface_neg")
    if kind == "predicate":
        if not group.get("predicate") or not group.get("cases"):
            raise SpecError(f"predicate 组 {group['id']} 缺 predicate/cases")
    if kind == "cases":
        for i, case in enumerate(group.get("cases") or []):
            if "surface" not in case or "expected_ok" not in case:
                raise SpecError(f"cases 组 {group['id']} 第{i}条缺 surface/expected_ok")


def _threshold_ok(op: str, value: Any, thr: Any) -> bool:
    if op == ">=":
        return value >= thr
    if op == "<=":
        return value <= thr
    if op == ">":
        return value > thr
    if op == "<":
        return value < thr
    raise SpecError(f"threshold 未知 verdict_op: {op}")
