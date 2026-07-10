"""切分质量闸 —— 教研切分进白名单前的确定性结构校验(§1限制②"过切分质量闸")。

分工:**教研判语义**(采分点是否原子/独立可判/互斥/可证伪、锚是否到教材真题)——这是
双教研 verdict 的活,不可自动化;**本闸判结构**(确定性、教研-independent):
  - 每个采分点都标了 proposed_sub_no(未标 = 切分未定,不许进);
  - 合取组(conjunction_group)必须 ≥2 个成员(找错∧改正需两半;单成员 = 坏切分);
  - 列举封顶(list_cap)若有,必须是正整数;
  - 无重复 point_id;
  - consensus 必须 passed(双教研过了才谈进白名单)。

过闸 = 结构 OK + consensus passed → 该 qid 才允许进白名单。任一结构病 → 拦下,不进。
只读校验,不改采分点、不改生产。Deterministic: no LLM。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class QualityGateResult:
    passed: bool
    issues: tuple[str, ...]  # 结构病清单(空=过闸)


def check_segmentation_quality(review: Mapping[str, object]) -> QualityGateResult:
    """对一份 review.json 做确定性结构校验。返回 passed + issues。"""
    issues: list[str] = []

    consensus = review.get("consensus") or {}
    if consensus.get("status") != "passed":
        issues.append(f"consensus 未 passed(={consensus.get('status')!r}),双教研未验收")

    points: Sequence[Mapping[str, object]] = review.get("points") or []
    if not points:
        issues.append("review 无采分点")

    seen: set[str] = set()
    conj_members: dict[str, int] = {}
    for p in points:
        pid = str(p.get("point_id") or "")
        if not pid:
            issues.append("存在无 point_id 的采分点")
            continue
        if pid in seen:
            issues.append(f"重复 point_id: {pid}")
        seen.add(pid)

        if p.get("proposed_sub_no") is None:
            issues.append(f"采分点 {pid} 未标 proposed_sub_no(切分未定)")

        cg = p.get("conjunction_group")
        if cg:
            conj_members[str(cg)] = conj_members.get(str(cg), 0) + 1

        lc = p.get("list_cap")
        if lc is not None and (not isinstance(lc, int) or isinstance(lc, bool) or lc <= 0):
            issues.append(f"采分点 {pid} 的 list_cap={lc!r} 非正整数")

    for cg, n in conj_members.items():
        if n < 2:
            issues.append(f"合取组 {cg!r} 只有 {n} 个成员(找错∧改正需 ≥2 半)")

    return QualityGateResult(passed=not issues, issues=tuple(issues))


def passes_quality_gate(review: Mapping[str, object]) -> bool:
    return check_segmentation_quality(review).passed


__all__ = ["QualityGateResult", "check_segmentation_quality", "passes_quality_gate"]
