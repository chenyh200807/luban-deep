"""DAG+ECF 计算图引擎金标测试。

金标 = 真题 EXAM_1A432000_P0016_02 小问3 造价费用构成 6 步链(采分点自带公式+官方值,
从编译库 v_case_rubric_scored 直读,非编造):
  分部分项48000 → 措施=×15%=7200 → 其他=1500+1200+1200×3%=2736
  → 规费=(和)×2.2%=1274.59 → 税金=(和)×9%=5328.95 → 合同价=64539.54
官方链每步四舍五入到2位再供下游。ECF:学员上游错、下游在其错值上自洽算对 → 给过程分。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from deeptutor.services.construction_grading.case_calc_dag import (
    SCHEMA_ID,
    CalcError,
    CalcRole,
    CalcStep,
    grade_calc_dag,
    solve_calc_dag,
)

_REGISTRY = Path(__file__).resolve().parents[3] / "contracts" / "schema_registry.yaml"


def test_dataclass_fields_match_registry():
    payload = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
    entry = next(e for e in payload["tier2_canonical_contracts"] if e.get("name") == SCHEMA_ID)
    assert list(CalcStep.__dataclass_fields__.keys()) == list(entry["canonical_fields"])


def _chain():
    return [
        CalcStep("Q3_1", "48000", (), 0.01, 2, 1.0, CalcRole.PROCESS),
        CalcStep("Q3_2", "Q3_1 * 0.15", ("Q3_1",), 0.01, 2, 1.0, CalcRole.PROCESS),
        CalcStep("Q3_3", "1500 + 1200 + 1200 * 0.03", (), 0.01, 2, 1.0, CalcRole.PROCESS),
        CalcStep("Q3_4", "(Q3_1 + Q3_2 + Q3_3) * 0.022", ("Q3_1", "Q3_2", "Q3_3"), 0.01, 2, 1.0, CalcRole.PROCESS),
        CalcStep("Q3_5", "(Q3_1 + Q3_2 + Q3_3 + Q3_4) * 0.09", ("Q3_1", "Q3_2", "Q3_3", "Q3_4"), 0.01, 2, 1.0, CalcRole.PROCESS),
        CalcStep("Q3_6", "Q3_1 + Q3_2 + Q3_3 + Q3_4 + Q3_5", ("Q3_1", "Q3_2", "Q3_3", "Q3_4", "Q3_5"), 0.01, 2, 1.0, CalcRole.RESULT),
    ]


_OFFICIAL = {"Q3_1": 48000.0, "Q3_2": 7200.0, "Q3_3": 2736.0, "Q3_4": 1274.59, "Q3_5": 5328.95, "Q3_6": 64539.54}


def test_golden_canonical_matches_official():
    got = solve_calc_dag(_chain(), {})
    for k, v in _OFFICIAL.items():
        assert got[k] == pytest.approx(v, abs=1e-6), f"{k}: {got[k]} != official {v}"


def test_all_correct_full_score():
    r = grade_calc_dag(_chain(), {}, _OFFICIAL)
    assert r.total_awarded == 6.0
    assert r.result_awarded == 1.0  # Q3_6
    assert r.process_awarded == 5.0


def test_ecf_upstream_wrong_downstream_self_consistent_gets_credit():
    # 学员 Q3_2 算错(7000 而非 7200),但 Q3_4/5/6 在其错值上正确套公式。
    q2 = 7000.0
    q4 = round((48000 + q2 + 2736) * 0.022, 2)          # 1270.19
    q5 = round((48000 + q2 + 2736 + q4) * 0.09, 2)       # 5310.56
    q6 = round(48000 + q2 + 2736 + q4 + q5, 2)           # 64316.75
    student = {"Q3_1": 48000.0, "Q3_2": q2, "Q3_3": 2736.0, "Q3_4": q4, "Q3_5": q5, "Q3_6": q6}

    r = grade_calc_dag(_chain(), {}, student)
    assert r.verdicts["Q3_2"].correct is False   # 上游错步本身不得分
    # 下游在学员错值上自洽 → ECF 给分(不连坐):
    assert r.verdicts["Q3_4"].correct is True
    assert r.verdicts["Q3_5"].correct is True
    assert r.verdicts["Q3_6"].correct is True
    assert r.total_awarded == 5.0                # 6 步只错 Q3_2
    # ECF 期望是学员错值链上的自洽值,不是官方值
    assert r.verdicts["Q3_4"].ecf_expected == pytest.approx(1270.19, abs=1e-6)


def test_without_ecf_downstream_would_be_wrong_but_ecf_credits():
    # 反证:若学员 Q3_4 填官方值 1274.59(没在自己错的 Q3_2 上重算),ECF 判它错。
    student = {"Q3_1": 48000.0, "Q3_2": 7000.0, "Q3_3": 2736.0, "Q3_4": 1274.59}
    r = grade_calc_dag(_chain(), {}, student)
    assert r.verdicts["Q3_4"].correct is False  # 1274.59 != ECF 1270.19


def test_missing_student_step_is_incorrect():
    r = grade_calc_dag(_chain(), {}, {"Q3_1": 48000.0})
    assert r.verdicts["Q3_2"].correct is False
    assert r.verdicts["Q3_2"].student_value is None


def test_unsafe_formula_rejected():
    with pytest.raises(CalcError):
        solve_calc_dag([CalcStep("x", "__import__('os').system('ls')", (), 0.0, None, 1.0, CalcRole.RESULT)], {})
    with pytest.raises(CalcError):
        solve_calc_dag([CalcStep("x", "abs(-5)", (), 0.0, None, 1.0, CalcRole.RESULT)], {})  # no calls


# ── 2026-07-09 Codex 对抗核回归 ──────────────────────────────────────────────


def test_ecf_missing_upstream_is_not_credited():
    # 学员只填下游官方值、上游全不填 → 不得按官方链回落当自洽过程分。
    r = grade_calc_dag(_chain(), {}, {"Q3_4": 1274.59})
    assert r.verdicts["Q3_4"].correct is False


def test_ecf_rounds_upstream_per_step_rounding():
    steps = [
        CalcStep("A", "10.004", (), 0.01, 2, 1.0, CalcRole.PROCESS),          # 官方 A=10.0
        CalcStep("B", "A * 1000", ("A",), 0.01, 2, 1.0, CalcRole.RESULT),      # 官方 B=10000.0
    ]
    # 学员上游填未取整 10.004,但下游用取整口径 → ECF 归一后 B=10000 判对
    r = grade_calc_dag(steps, {}, {"A": 10.004, "B": 10000.0})
    assert r.verdicts["A"].correct is True
    assert r.verdicts["B"].correct is True
    # 若学员按未取整链算 B=10004 → 违反官方"取整后供下游"口径 → 判错
    r2 = grade_calc_dag(steps, {}, {"A": 10.004, "B": 10004.0})
    assert r2.verdicts["B"].correct is False


def test_formula_referencing_undeclared_name_rejected():
    # formula 引用了没在 depends_on 声明、也不是 given 的名字 → fail-closed
    with pytest.raises(CalcError):
        solve_calc_dag([
            CalcStep("A", "10", (), 0.0, None, 1.0, CalcRole.PROCESS),
            CalcStep("B", "A + 1", (), 0.0, None, 1.0, CalcRole.RESULT),  # 用了 A 但没声明
        ], {})


def test_inf_nan_tolerance_rejected():
    with pytest.raises(CalcError):
        CalcStep("x", "1", (), float("inf"), None, 1.0, CalcRole.RESULT)
    with pytest.raises(CalcError):
        CalcStep("x", "1", (), float("nan"), None, 1.0, CalcRole.RESULT)


def test_role_must_be_enum():
    with pytest.raises(CalcError):
        CalcStep("x", "1", (), 0.0, None, 1.0, "result")  # 字符串会让账目错分


def test_non_numeric_student_value_marks_incorrect_not_crash():
    r = grade_calc_dag(_chain(), {}, {"Q3_1": "abc", "Q3_2": 7200.0})
    assert r.verdicts["Q3_1"].correct is False
    # Q3_2 依赖 Q3_1(非数字)→ 不可核验 → 判错(不崩溃)
    assert r.verdicts["Q3_2"].correct is False


def test_arithmetic_hazards_are_calcerror():
    with pytest.raises(CalcError):  # 除零
        solve_calc_dag([CalcStep("x", "1/0", (), 0.0, None, 1.0, CalcRole.RESULT)], {})
    with pytest.raises(CalcError):  # Pow 不允许
        solve_calc_dag([CalcStep("x", "2 ** 999999999", (), 0.0, None, 1.0, CalcRole.RESULT)], {})
    with pytest.raises(CalcError):  # 超深表达式
        solve_calc_dag([CalcStep("x", "+".join(["1"] * 200), (), 0.0, None, 1.0, CalcRole.RESULT)], {})


def test_malformed_graphs_raise():
    with pytest.raises(CalcError):  # cycle
        solve_calc_dag([
            CalcStep("a", "b", ("b",), 0.0, None, 1.0, CalcRole.PROCESS),
            CalcStep("b", "a", ("a",), 0.0, None, 1.0, CalcRole.PROCESS),
        ], {})
    with pytest.raises(CalcError):  # unknown dependency
        solve_calc_dag([CalcStep("a", "ghost", ("ghost",), 0.0, None, 1.0, CalcRole.RESULT)], {})
    with pytest.raises(CalcError):  # duplicate step_id
        solve_calc_dag([
            CalcStep("a", "1", (), 0.0, None, 1.0, CalcRole.PROCESS),
            CalcStep("a", "2", (), 0.0, None, 1.0, CalcRole.RESULT),
        ], {})
    with pytest.raises(CalcError):  # negative points
        CalcStep("a", "1", (), 0.0, None, -1.0, CalcRole.RESULT)
