"""Integration: the M10 deterministic spec matcher must resist false positives.

Directly exercises the matcher + attack generator on representative specs to prove the
hard gate genuinely discriminates (exact accepted; partial/contradiction/off-by-one/
denominator-mismatch/near-synonym/irrelevant rejected) — this is the safety property that
lets non-textbook specs grade in beta_shadow without auto-certifying garbage.
"""
from __future__ import annotations

import scripts.build_luban_non_textbook_rubric_authority_factory_m10 as m10


def _attack(spec, is_list):
    res = m10.attack_spec(spec, is_list=is_list)
    accepted = {a["vector"]: a["accepted"] for a in res}
    fp = sum(1 for a in res if a["false_positive"])
    return accepted, fp, res


def test_numeric_value_spec_rejects_off_by_one_and_contradiction():
    spec = {"kind": "numeric_value", "expected": 25.0, "unit": "个月",
            "acceptance_range": [25.0, 25.0], "negative_controls": []}
    accepted, fp, _ = _attack(spec, is_list=False)
    assert accepted["exact_hit"] is True
    assert accepted["numeric_off_by_one"] is False
    assert accepted["contradiction"] is False
    assert accepted["irrelevant"] is False
    assert fp == 0


def test_numeric_judgment_requires_value_and_polarity():
    spec = {"kind": "numeric_judgment", "expected": 27.2, "unit": "万元", "judgment": True,
            "acceptance_range": [27.2, 27.2], "negative_controls": []}
    # right value, wrong polarity must be rejected
    assert m10.matcher_accepts(spec, {"value": 27.2, "judgment": True}) is True
    assert m10.matcher_accepts(spec, {"value": 27.2, "judgment": False}) is False
    assert m10.matcher_accepts(spec, {"value": 28.2, "judgment": True}) is False
    _, fp, _ = _attack(spec, is_list=False)
    assert fp == 0


def test_boolean_judgment_rejects_flip():
    spec = {"kind": "boolean_judgment", "expected_bool": False, "negative_controls": []}
    assert m10.matcher_accepts(spec, {"judgment": False}) is True
    assert m10.matcher_accepts(spec, {"judgment": True}) is False
    assert m10.matcher_accepts(spec, {"judgment": None}) is False
    _, fp, _ = _attack(spec, is_list=False)
    assert fp == 0


def test_numeric_range_rejects_outside():
    spec = {"kind": "numeric_range", "lo": 0.001, "hi": 0.003, "unit": "m", "negative_controls": []}
    assert m10.matcher_accepts(spec, {"value": 0.002}) is True
    assert m10.matcher_accepts(spec, {"value": 0.0009}) is False
    assert m10.matcher_accepts(spec, {"value": 0.004}) is False
    _, fp, _ = _attack(spec, is_list=False)
    assert fp == 0


def test_list_full_coverage_rejects_partial_and_overclaim():
    spec = m10._list_spec({"list_spec": {"item_set": ["甲项", "乙项", "丙项"]}})
    assert spec is not None and spec["full_coverage"] is True
    # exact set accepted
    assert m10.matcher_accepts(spec, {"items": ["甲项", "乙项", "丙项"]}) is True
    # partial rejected (coverage < 1.0)
    assert m10.matcher_accepts(spec, {"items": ["甲项", "乙项"]}) is False
    # over-claim (denominator mismatch) rejected
    assert m10.matcher_accepts(spec, {"items": ["甲项", "乙项", "丙项", "丁项"]}) is False
    accepted, fp, _ = _attack(spec, is_list=True)
    assert accepted["exact_hit"] is True
    assert accepted["denominator_mismatch"] is False
    assert accepted["partial"] is False
    assert fp == 0


def test_official_answer_text_is_not_a_textbook_source_object():
    # the matcher never consults a textbook; it grades a student candidate against the rubric seed
    spec = {"kind": "numeric_value", "expected": 4.0, "unit": "m",
            "acceptance_range": [4.0, 4.0], "negative_controls": []}
    # a candidate that merely quotes the official answer text (no value) is NOT auto-accepted
    assert m10.matcher_accepts(spec, {"text": "官方答案原文"}) is False
