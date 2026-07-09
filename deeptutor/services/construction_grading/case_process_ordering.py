"""工序排序判分 —— 拖拽重排的确定性判分(§1① 计算类,排序子类)。

判分正确性引擎:**算错=判分错=误判学员**。工序排序(拖拽重排)判分:
  - **唯一序** → 学员排列必须精确等于官方序(线性紧前链);
  - **多合法拓扑序** → 学员排列须满足全部紧前约束(a 必须在 b 前)即给分。

统一实现:学员排列**是全体工序的一个合法拓扑序**(集合对得上 + 每条紧前约束满足)
才给分。线性唯一序是"约束把拓扑序卡成唯一"的特例。计算/顺序判分**绝不走 LLM**(§4)。

采分点 = 有序工序列表 / 紧前约束(运行时判定结构,同 CPM Activity 不另注册 schema——
真值仍归编译库的有序 list 采分点)。Deterministic: no LLM, no network, no DB.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass


class OrderingError(ValueError):
    """Malformed ordering spec."""


def _norm(name: str) -> str:
    """工序名归一:NFKC + 去所有空白 + 去零宽/控制字符(Cf/Cc)+ casefold。
    2026-07-09 Codex 对抗核:零宽/内部空格曾让视觉同一工序名判不等。"""
    s = unicodedata.normalize("NFKC", str(name))
    return "".join(
        c for c in s if not c.isspace() and unicodedata.category(c) not in ("Cf", "Cc")
    ).casefold()


def _has_cycle(activities: list[str], edges: set[tuple[str, str]]) -> bool:
    """precedence 是否含环(多跳环 A→B→C→A)——坏 spec 会让所有学员序判错。"""
    succ: dict[str, list[str]] = {a: [] for a in activities}
    indeg = {a: 0 for a in activities}
    for a, b in edges:
        succ[a].append(b)
        indeg[b] += 1
    queue = [a for a in activities if indeg[a] == 0]
    seen = 0
    while queue:
        n = queue.pop()
        seen += 1
        for m in succ[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    return seen != len(activities)


@dataclass(frozen=True)
class OrderingSpec:
    """全体工序 + 紧前约束 (before, after)。"""

    activities: tuple[str, ...]
    precedence: frozenset[tuple[str, str]]

    def __post_init__(self) -> None:
        norm = [_norm(a) for a in self.activities]
        if len(set(norm)) != len(norm):
            raise OrderingError(f"duplicate activity in spec: {self.activities}")
        acts = set(norm)
        norm_edges: set[tuple[str, str]] = set()
        for a, b in self.precedence:
            if _norm(a) not in acts or _norm(b) not in acts:
                raise OrderingError(f"precedence {a!r}->{b!r} references unknown activity")
            if _norm(a) == _norm(b):
                raise OrderingError(f"precedence self-loop on {a!r}")
            norm_edges.add((_norm(a), _norm(b)))
        # 多跳环(A→B→C→A)= 坏 spec:无合法拓扑序,会把所有学员序判错(2026-07-09 Codex)。
        if _has_cycle(norm, norm_edges):
            raise OrderingError(f"precedence has a cycle (not a DAG): {sorted(self.precedence)}")

    @classmethod
    def from_sequence(cls, sequence: Sequence[str]) -> "OrderingSpec":
        """线性唯一序:相邻对即紧前约束(排列里 a<b<c ⇒ 传递性自动成立,唯一合法序)。"""
        seq = tuple(sequence)
        if len(seq) < 1:
            raise OrderingError("empty sequence")
        prec = frozenset((seq[i], seq[i + 1]) for i in range(len(seq) - 1))
        return cls(activities=seq, precedence=prec)


@dataclass(frozen=True)
class OrderingResult:
    correct: bool
    reason: str  # "" if correct; else why (set mismatch / constraint violated)


def grade_ordering(spec: OrderingSpec, student_order: Sequence[str]) -> OrderingResult:
    """学员排列是合法拓扑序(集合对 + 全部紧前满足)→ correct;否则给出原因。"""
    if not isinstance(spec, OrderingSpec):
        raise OrderingError(f"spec must be an OrderingSpec, got {type(spec).__name__}")

    # None / str(会被逐字符拆)/ 非序列 → fail-closed 判错,不崩(2026-07-09 Codex)。
    if student_order is None or isinstance(student_order, (str, bytes)):
        return OrderingResult(False, "学员排列缺失或格式非法")
    try:
        student = [_norm(x) for x in student_order]
    except TypeError:
        return OrderingResult(False, "学员排列不是工序序列")
    if len(set(student)) != len(student):
        return OrderingResult(False, "学员排列有重复工序")
    if set(student) != {_norm(a) for a in spec.activities}:
        return OrderingResult(False, "学员排列的工序集合与官方不一致(多/漏/换项)")

    pos = {name: i for i, name in enumerate(student)}
    for a, b in spec.precedence:
        na, nb = _norm(a), _norm(b)
        if pos[na] >= pos[nb]:
            return OrderingResult(False, f"违反紧前约束:{a} 应在 {b} 之前")
    return OrderingResult(True, "")


__all__ = ["OrderingError", "OrderingSpec", "OrderingResult", "grade_ordering"]
