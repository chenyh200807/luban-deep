"""Deterministic CPM (Critical Path Method) solver for network-schedule case questions.

判分正确性引擎——**算错 = 判分错 = 误判学员**。计算类判分**绝不走 LLM**(§4 红线):
CPM 是纯确定性图算。顺推 ES/EF → 逆推 LS/LF → 总时差 TF=LS−ES → 自由时差 FF →
关键线路 = TF=0 的连续路径(可多条)。ground truth 与判分同一份:solver 既算官方答案、
又判学员选择(集合/路径精确匹配 + 数值容差),不依赖任何 LLM 判读。

一建口径:总时差 TF = 最迟开始 − 最早开始;自由时差 FF = min(紧后最早开始) − 本工作最早完成;
关键线路 = 从开始到结束、全线 TF=0 且相邻边紧凑(EF_pred==ES_succ)的连续线路;总工期 = max EF。

Validated against the build-validated N01 golden network (independent SVG-baked answer,
tests/services/construction_grading/test_case_cpm_solver.py). Pure: no LLM, no network, no DB.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

# 一建 CPM 工期是整数(天/月/周)。整数工期下 ES/EF/LS/LF/TF 全为精确整数,
# 关键判据用精确 `tf == 0` —— 不用绝对容差(容差会把 TF≈5e-10 的真正非关键工作
# 误判为关键 = 假关键线路 = 误判学员;Codex 2026-07-09 对抗核证伪)。工期非整在
# 构造期拒绝,从源头消除浮点 TF 歧义(0.1+0.2≠0.3 那类陷阱一并根除)。
# 仅在"学员数值答案容差"这类 grading 比较上保留一个极小 epsilon。
_EPS = 1e-9


@dataclass(frozen=True)
class Activity:
    """一个工作:名称 + 持续时间 + 紧前工作名列表(开始节点紧前为空)。"""

    name: str
    duration: float
    predecessors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActivityTiming:
    name: str
    duration: float
    es: float  # 最早开始
    ef: float  # 最早完成
    ls: float  # 最迟开始
    lf: float  # 最迟完成
    total_float: float  # 总时差 TF
    free_float: float  # 自由时差 FF
    critical: bool


@dataclass(frozen=True)
class CpmResult:
    timings: dict[str, ActivityTiming]
    project_duration: float
    critical_activities: frozenset[str]
    critical_paths: tuple[tuple[str, ...], ...]


class CpmError(ValueError):
    """Raised on a malformed network (unknown predecessor, cycle, dup name)."""


def _topo_order(acts: dict[str, Activity]) -> list[str]:
    """Kahn topological sort; raises CpmError on a cycle or unknown predecessor."""
    for a in acts.values():
        for p in a.predecessors:
            if p not in acts:
                raise CpmError(f"activity {a.name!r} references unknown predecessor {p!r}")
    indeg = {n: 0 for n in acts}
    succ: dict[str, list[str]] = {n: [] for n in acts}
    for a in acts.values():
        for p in a.predecessors:
            indeg[a.name] += 1
            succ[p].append(a.name)
    queue = sorted(n for n, d in indeg.items() if d == 0)
    order: list[str] = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in succ[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                # keep deterministic order
                queue.append(m)
                queue.sort()
    if len(order) != len(acts):
        raise CpmError("network has a cycle (not a DAG)")
    return order


def solve_cpm(activities: Sequence[Activity]) -> CpmResult:
    """Compute ES/EF/LS/LF/TF/FF for every activity, the project duration, and all
    critical paths (TF=0, tight-edge chains from a start node to an end node)."""
    acts: dict[str, Activity] = {}
    for a in activities:
        if a.name in acts:
            raise CpmError(f"duplicate activity name {a.name!r}")
        if not math.isfinite(a.duration):
            raise CpmError(f"activity {a.name!r} has non-finite duration {a.duration!r}")
        if a.duration < 0:
            raise CpmError(f"activity {a.name!r} has negative duration")
        if a.duration != int(a.duration):
            raise CpmError(
                f"activity {a.name!r} duration {a.duration!r} must be integral "
                f"(一建 CPM 工期为整数天/月/周;非整工期会引入浮点 TF 歧义)"
            )
        acts[a.name] = a
    if not acts:
        raise CpmError("empty network")

    order = _topo_order(acts)
    succ: dict[str, list[str]] = {n: [] for n in acts}
    for a in acts.values():
        for p in a.predecessors:
            succ[p].append(a.name)

    # ── forward pass ──
    es: dict[str, float] = {}
    ef: dict[str, float] = {}
    for n in order:
        preds = acts[n].predecessors
        es[n] = max((ef[p] for p in preds), default=0.0)
        ef[n] = es[n] + acts[n].duration
    project_duration = max(ef.values())

    # ── backward pass ──
    ls: dict[str, float] = {}
    lf: dict[str, float] = {}
    for n in reversed(order):
        outs = succ[n]
        lf[n] = min((ls[s] for s in outs), default=project_duration)
        ls[n] = lf[n] - acts[n].duration

    timings: dict[str, ActivityTiming] = {}
    for n in order:
        tf = ls[n] - es[n]
        # free float = min(ES of successors) − EF; end nodes use project_duration
        ff = min((es[s] for s in succ[n]), default=project_duration) - ef[n]
        timings[n] = ActivityTiming(
            name=n, duration=acts[n].duration,
            es=es[n], ef=ef[n], ls=ls[n], lf=lf[n],
            total_float=tf, free_float=ff, critical=(tf == 0),
        )

    critical = frozenset(n for n, t in timings.items() if t.critical)
    paths = _enumerate_critical_paths(acts, succ, ef, es, critical)
    return CpmResult(
        timings=timings, project_duration=project_duration,
        critical_activities=critical, critical_paths=paths,
    )


def _enumerate_critical_paths(acts, succ, ef, es, critical) -> tuple[tuple[str, ...], ...]:
    """All start→end chains through critical activities whose edges are tight
    (EF(pred)==ES(succ)). Handles multiple parallel critical paths (e.g. 2015 真题)."""
    starts = sorted(n for n in critical if not acts[n].predecessors)
    ends = {n for n in critical if not succ[n]}
    paths: list[tuple[str, ...]] = []

    def walk(node, acc):
        if node in ends:
            paths.append(tuple(acc))
            return
        nxt = sorted(
            s for s in succ[node]
            if s in critical and ef[node] == es[s]  # tight edge (exact; integer durations)
        )
        if not nxt:
            # a critical node whose critical successors are all slack-broken: still a
            # terminal of a critical chain only if it is an end node (handled above).
            return
        for s in nxt:
            walk(s, acc + [s])

    for s in starts:
        walk(s, [s])
    return tuple(paths)


# ── Deterministic judging helpers (采分点是真值;solver 判学员选择) ──


def matches_critical_path(result: CpmResult, selected: Sequence[str]) -> bool:
    """True iff the student's node sequence exactly equals one official critical path."""
    return tuple(selected) in result.critical_paths


def grade_project_duration(result: CpmResult, answer: float, tolerance: float = 0.0) -> bool:
    """True iff the student's 总工期 is within tolerance of the computed value."""
    return abs(result.project_duration - answer) <= tolerance + _EPS


def total_float_of(result: CpmResult, activity: str) -> float:
    t = result.timings.get(activity)
    if t is None:
        raise CpmError(f"unknown activity {activity!r}")
    return t.total_float


def delay_affects_duration(result: CpmResult, activity: str, delay: float) -> bool:
    """一建时差判读:延误 > 该工作总时差 ⇒ 影响总工期(关键工作 TF=0 则任何延误都影响)。"""
    return delay > total_float_of(result, activity) + _EPS


__all__ = [
    "Activity", "ActivityTiming", "CpmResult", "CpmError",
    "solve_cpm", "matches_critical_path", "grade_project_duration",
    "total_float_of", "delay_affects_duration",
]
