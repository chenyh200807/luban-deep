"""计算图(DAG)+ ECF 重算引擎 —— 计算类案例题判分(造价链式/挣值等)。

判分正确性引擎:**算错=判分错=误判学员**。计算类判分**绝不走 LLM**(§4 红线),
是纯确定性图算。每个计算步存 `{step_id, formula, depends_on[], tolerance, rounding,
points, role: process|result}`;公式是"只含四则运算 + 上游 step_id + 数字"的表达式,
用**安全 AST 求值**(禁 eval / 禁函数调用 / 禁属性)。

**ECF(Error Carried Forward,上游错下游不连坐)**:判每一步时,用**学员本步依赖的
上游实填值**(缺则回落官方值)现算该步期望,再按 tolerance 容差比对学员本步答案 ——
**上游算错、但下游在其错值上正确套用公式 → 给该步过程分**。官方链每步按 rounding
四舍五入后再供下游(与真题口径一致)。

金标验:真题 EXAM_1A432000_P0016_02 小问3 造价费用构成 6 步链(见测试)。
Deterministic: no LLM, no network, no DB.
"""
from __future__ import annotations

import ast
import math
import operator
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

SCHEMA_ID = "luban_case_calc_step.v1"

# NOTE: Pow (**) is deliberately NOT allowed — 造价/挣值链无需幂运算,而 `2**999999999`
# 是确定性 DoS 面(2026-07-09 Codex 对抗核证伪)。四则运算足够;需要平方等再受控加入。
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_AST_DEPTH = 64  # 反超深表达式 RecursionError DoS


class CalcRole(str, Enum):
    PROCESS = "process"  # 过程分:中间步骤
    RESULT = "result"  # 结果分:最终答案步


class CalcError(ValueError):
    """Malformed step graph or unsafe formula."""


@dataclass(frozen=True)
class CalcStep:
    """一个计算步。字段清单 == schema_registry ``luban_case_calc_step.v1`` canonical_fields。"""

    step_id: str
    formula: str  # 四则表达式,变量名 = 上游 step_id 或 given_input 名
    depends_on: tuple[str, ...]
    tolerance: float
    rounding: int | None
    points: float
    role: CalcRole

    def __post_init__(self) -> None:
        if not isinstance(self.role, CalcRole):
            raise CalcError(
                f"step {self.step_id!r}: role must be a CalcRole, got {self.role!r} "
                f"(字符串会让 result/process 账目错分)"
            )
        if self.points < 0 or not math.isfinite(self.points):
            raise CalcError(f"step {self.step_id!r}: points must be finite and non-negative")
        if self.tolerance < 0 or not math.isfinite(self.tolerance):
            raise CalcError(
                f"step {self.step_id!r}: tolerance {self.tolerance!r} must be finite and non-negative "
                f"(inf 容差会把任何答案判对)"
            )


def _formula_names(expr: str) -> set[str]:
    """The set of variable names a formula references (for depends_on/given consistency)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise CalcError(f"unparseable formula {expr!r}: {e}") from e
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def _safe_eval(expr: str, variables: Mapping[str, float]) -> float:
    """Evaluate a four-operation arithmetic expression over ``variables``.

    Hardened (2026-07-09 Codex 对抗核): no eval/calls/attrs; no Pow; bounded AST depth;
    division-by-zero / overflow wrapped to CalcError; result must be finite. Variable
    names must already be present in ``variables`` (ASCII/step-id whitelist upstream).
    """
    try:
        node = ast.parse(expr, mode="eval").body
    except SyntaxError as e:
        raise CalcError(f"unparseable formula {expr!r}: {e}") from e

    def ev(n, depth):
        if depth > _MAX_AST_DEPTH:
            raise CalcError(f"formula too deep (>{_MAX_AST_DEPTH}): {expr!r}")
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool) or not isinstance(n.value, (int, float)):
                raise CalcError(f"non-numeric constant in formula: {n.value!r}")
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id not in variables:
                raise CalcError(f"formula references unknown name {n.id!r}")
            return float(variables[n.id])
        if isinstance(n, ast.BinOp) and type(n.op) in _ALLOWED_BINOPS:
            try:
                return _ALLOWED_BINOPS[type(n.op)](ev(n.left, depth + 1), ev(n.right, depth + 1))
            except (ZeroDivisionError, OverflowError, ValueError) as e:
                raise CalcError(f"arithmetic error in {expr!r}: {e}") from e
        if isinstance(n, ast.UnaryOp) and type(n.op) in _ALLOWED_UNARY:
            return _ALLOWED_UNARY[type(n.op)](ev(n.operand, depth + 1))
        raise CalcError(f"disallowed expression node {type(n).__name__} in {expr!r}")

    result = ev(node, 0)
    if not math.isfinite(result):
        raise CalcError(f"formula {expr!r} produced non-finite result {result!r}")
    return result


def _round(value: float, rounding: int | None) -> float:
    return value if rounding is None else round(value, rounding)


def _as_num(x: object) -> float | None:
    """Coerce a student/input value to a finite float, or None if not a valid number.

    A non-numeric student input must make that step INCORRECT — never crash the whole
    grading run (2026-07-09 Codex 对抗核: ``"abc"`` used to raise ValueError mid-grade)."""
    if isinstance(x, bool):
        return None
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _validate_names(steps: Sequence[CalcStep], given_keys: frozenset[str]) -> None:
    """Every name a formula references must be a declared dependency or a given input —
    otherwise solve() (which sees all prior values) and grade() (which sees only declared
    deps) diverge, and an undeclared name can silently resolve to the official value,
    bypassing ECF (2026-07-09 Codex 对抗核证伪)."""
    for s in steps:
        allowed = set(s.depends_on) | given_keys
        for name in _formula_names(s.formula):
            if name not in allowed:
                raise CalcError(
                    f"step {s.step_id!r} formula references {name!r} which is neither a "
                    f"declared dependency nor a given input {sorted(allowed)}"
                )


def _ordered(steps: Sequence[CalcStep]) -> list[CalcStep]:
    by_id: dict[str, CalcStep] = {}
    for s in steps:
        if s.step_id in by_id:
            raise CalcError(f"duplicate step_id {s.step_id!r}")
        by_id[s.step_id] = s
    # Kahn topo sort over depends_on (deterministic)
    indeg = {sid: 0 for sid in by_id}
    succ: dict[str, list[str]] = {sid: [] for sid in by_id}
    for s in steps:
        for d in s.depends_on:
            if d not in by_id:
                raise CalcError(f"step {s.step_id!r} depends on unknown step {d!r}")
            indeg[s.step_id] += 1
            succ[d].append(s.step_id)
    queue = sorted(sid for sid, dg in indeg.items() if dg == 0)
    order: list[str] = []
    while queue:
        sid = queue.pop(0)
        order.append(sid)
        for m in succ[sid]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
                queue.sort()
    if len(order) != len(by_id):
        raise CalcError("calc graph has a cycle")
    return [by_id[sid] for sid in order]


def solve_calc_dag(
    steps: Sequence[CalcStep], given_inputs: Mapping[str, float]
) -> dict[str, float]:
    """Compute the CANONICAL (official) value of every step, rounding each per its
    ``rounding`` and feeding the ROUNDED value downstream (真题口径)."""
    ordered = _ordered(steps)
    _validate_names(steps, frozenset(given_inputs))
    values: dict[str, float] = dict(given_inputs)
    for s in ordered:
        raw = _safe_eval(s.formula, values)
        values[s.step_id] = _round(raw, s.rounding)
    return {s.step_id: values[s.step_id] for s in steps}


@dataclass(frozen=True)
class StepVerdict:
    step_id: str
    role: CalcRole
    correct: bool
    ecf_expected: float
    student_value: float | None
    awarded: float


@dataclass(frozen=True)
class CalcGradeResult:
    verdicts: dict[str, StepVerdict]
    total_awarded: float
    process_awarded: float
    result_awarded: float


def grade_calc_dag(
    steps: Sequence[CalcStep],
    given_inputs: Mapping[str, float],
    student_values: Mapping[str, float],
) -> CalcGradeResult:
    """ECF 判分(2026-07-09 Codex 对抗核加固):每步用**学员本步依赖的实填值**现算期望,
    容差比对学员本步答案;上游错、下游在其错值上自洽套公式 → 给该步分(不连坐)。

    Fail-closed 边界:
      - 声明的上游依赖**缺失或非数字** → 本步不可 ECF 核验 → 判错(决不回落官方值当自洽,
        否则学员只填下游官方值就能拿过程分)。
      - 上游学员值按**该上游步的 rounding 归一**再入公式(与官方"每步取整后供下游"口径一致)。
      - 学员本步值非数字 → 判错(不崩溃)。"""
    canonical = solve_calc_dag(steps, given_inputs)  # also validates graph + names
    ordered = _ordered(steps)
    step_by_id = {s.step_id: s for s in ordered}

    verdicts: dict[str, StepVerdict] = {}
    total = process = result = 0.0
    for s in ordered:
        # ECF env: given inputs + each declared dependency's ROUNDED student value.
        env: dict[str, float] = dict(given_inputs)
        deps_ok = True
        for d in s.depends_on:
            raw = _as_num(student_values.get(d)) if d in student_values else None
            if raw is None:
                deps_ok = False  # missing/non-numeric upstream → cannot verify this step
                break
            env[d] = _round(raw, step_by_id[d].rounding)

        sv = _as_num(student_values.get(s.step_id))
        if not deps_ok or sv is None:
            ecf_expected = canonical[s.step_id]  # for display only; step is NOT credited
            correct = False
        else:
            ecf_expected = _round(_safe_eval(s.formula, env), s.rounding)
            correct = abs(sv - ecf_expected) <= s.tolerance

        awarded = s.points if correct else 0.0
        verdicts[s.step_id] = StepVerdict(
            step_id=s.step_id, role=s.role, correct=correct,
            ecf_expected=ecf_expected, student_value=sv, awarded=awarded,
        )
        total += awarded
        if s.role is CalcRole.RESULT:
            result += awarded
        else:
            process += awarded
    return CalcGradeResult(
        verdicts=verdicts, total_awarded=total,
        process_awarded=process, result_awarded=result,
    )


__all__ = [
    "SCHEMA_ID", "CalcRole", "CalcError", "CalcStep",
    "solve_calc_dag", "grade_calc_dag", "StepVerdict", "CalcGradeResult",
]
