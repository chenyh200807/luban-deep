"""荷载组合集合判分 —— set-membership 确定性判分(§1① 计算类,组合子类)。

判分正确性引擎:**算错=判分错=误判学员**。荷载组合(整体稳定/立杆/底模各算哪些
G/Q)是**矩阵勾选**(行=计算项 bin、列=荷载 chip)+ **每计算项集合精确匹配**——
学员对某计算项选的荷载集合**精确等于**官方集合才给该计算项分,多选/漏选/换项皆 0
(§1① "干扰=别计算项的荷载,不撞车" 是生成侧的事;判分侧只做集合精确相等)。

采分点存 `{bin: correct_set}` + per-bin points(set_membership schema,register-before-use)。
计算类判分**绝不走 LLM**(§4 红线)。Deterministic: no LLM, no network, no DB.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

SCHEMA_ID = "luban_case_set_membership.v1"


class SetMembershipError(ValueError):
    """Malformed set-membership scoring point."""


def _norm_chip(chip: str) -> str:
    """归一化一个荷载 chip(G1/Q1…):NFKC + 去空白 + 去零宽/控制字符 + casefold。
    2026-07-09 Codex 对抗核:零宽/BOM(Q\\u200b1)曾让视觉同一 chip 判不等。"""
    s = unicodedata.normalize("NFKC", str(chip))
    # 去所有空白 + Cf(格式,含零宽/BOM)+ Cc(控制)字符
    s = "".join(c for c in s if not c.isspace() and unicodedata.category(c) not in ("Cf", "Cc"))
    return s.casefold()


def _coerce_selection(raw: object) -> frozenset[str]:
    """把学员对某 bin 的选择归一成 chip 集合。**只接受 chip 序列(list/tuple/set)**;
    str/bytes(会被逐字符拆)、Mapping(dict 只迭代 key、忽略 False 值)、None → 空集
    (fail-closed 判错)。2026-07-09 Codex 对抗核:``{"G1":False,...}`` 曾被判满分。"""
    from collections.abc import Mapping as _Mapping

    if raw is None or isinstance(raw, (str, bytes, _Mapping)):
        return frozenset()
    try:
        items = list(raw)  # type: ignore[arg-type]
    except TypeError:
        return frozenset()
    return frozenset(_norm_chip(c) for c in items if str(c).strip())


@dataclass(frozen=True)
class SetMembershipPoint:
    """一个计算项(bin)的正确荷载集合 + 分值。字段 == registry canonical_fields。"""

    bin: str  # 计算项(底面模板承载力 / 支架立杆承载力 / 整体稳定…)
    correct_set: frozenset[str]  # 官方参与荷载项集合(G1/G2/Q1…)
    points: float

    def __post_init__(self) -> None:
        if not isinstance(self.bin, str) or not self.bin.strip():
            raise SetMembershipError(f"bin must be a non-empty str, got {self.bin!r}")
        if not isinstance(self.points, (int, float)) or self.points < 0:
            raise SetMembershipError(f"bin {self.bin!r}: points must be non-negative")
        if not isinstance(self.correct_set, frozenset):
            raise SetMembershipError(f"bin {self.bin!r}: correct_set must be a frozenset")
        if not self.correct_set:
            raise SetMembershipError(f"bin {self.bin!r}: correct_set must be non-empty")


@dataclass(frozen=True)
class BinVerdict:
    bin: str
    correct: bool
    awarded: float
    expected: frozenset[str]
    student: frozenset[str]


@dataclass(frozen=True)
class SetMembershipResult:
    verdicts: dict[str, BinVerdict]
    total_awarded: float


def grade_set_membership(
    points: Sequence[SetMembershipPoint],
    student_selections: Mapping[str, Iterable[str]],
) -> SetMembershipResult:
    """每计算项**集合精确匹配**判分:学员该 bin 选的(归一化)荷载集合 == 官方集合 → 给分;
    多选/漏选/未答皆 0(集合精确相等,无部分分)。重复 bin fail-closed。"""
    seen: set[str] = set()
    verdicts: dict[str, BinVerdict] = {}
    total = 0.0
    for p in points:
        # authority integrity:非 SetMembershipPoint(duck-typed 绕过 __post_init__ 的
        # 空集/负分/mutable set)一律拒绝(2026-07-09 Codex 对抗核)。
        if not isinstance(p, SetMembershipPoint):
            raise SetMembershipError(f"points must be SetMembershipPoint, got {type(p).__name__}")
        if p.bin in seen:
            raise SetMembershipError(f"duplicate bin {p.bin!r}")
        seen.add(p.bin)

        expected = frozenset(_norm_chip(c) for c in p.correct_set)
        student = _coerce_selection(student_selections.get(p.bin))
        correct = student == expected and bool(expected)
        awarded = p.points if correct else 0.0
        verdicts[p.bin] = BinVerdict(
            bin=p.bin, correct=correct, awarded=awarded, expected=expected, student=student
        )
        total += awarded
    return SetMembershipResult(verdicts=verdicts, total_awarded=total)


__all__ = [
    "SCHEMA_ID",
    "SetMembershipError",
    "SetMembershipPoint",
    "BinVerdict",
    "SetMembershipResult",
    "grade_set_membership",
]
