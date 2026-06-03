from __future__ import annotations

from scripts.calculation_validator_poc import expected_from_label, student_value


def test_expected_from_label_extracts_pure_numeric_result() -> None:
    assert expected_from_label("设计配合比 水泥用量 = 400kg") == (400.0, "kg")
    assert expected_from_label("预付款计算:=(18060-300)×10%=17760×10%=1776万元") == (1776.0, "万元")
    assert expected_from_label("主体施工阶段劳动力计算:取整275名") == (275.0, "名")


def test_expected_from_label_returns_none_for_text_term_point() -> None:
    # text_term style label has no numeric result -> validator must not fabricate an expected value
    assert expected_from_label("不妥1:见证记录应由'见证人员'记录与制作,而非'试验员'") is None


def test_student_value_numeric_correct_within_tolerance() -> None:
    value, how = student_value("经计算水泥用量400kg，中砂680kg", "kg", 400.0)
    assert value == 400.0
    assert abs(value - 400.0) <= 0.5  # numeric_correct
    assert how == "unit_adjacent"


def test_student_value_numeric_wrong_outside_tolerance() -> None:
    value, _ = student_value("水泥用量算成了 380 kg", "kg", 400.0)
    assert value == 380.0
    assert abs(value - 400.0) > 0.5  # numeric_wrong


def test_student_value_unverifiable_when_no_number() -> None:
    value, reason = student_value("这道题我不会算，没写出数值", "kg", 400.0)
    assert value is None
    assert reason == "no_number"
