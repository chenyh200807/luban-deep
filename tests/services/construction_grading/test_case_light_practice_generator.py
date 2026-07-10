"""Generator tests with an injected stub complete_fn (no LLM, no network).

Proves the deterministic orchestration: dev-fixture load, correct-option-is-verbatim,
RTG gate integration, regenerate-on-BLOCK, degrade-when-exhausted, and the qid
whitelist gate for non-dev callers.
"""
from __future__ import annotations

import json

import pytest

from deeptutor.services.construction_grading.case_light_practice_contract import (
    WhitelistError,
)
from deeptutor.services.construction_grading.case_light_practice_generator import (
    GenStatus,
    generate_point_select_item,
    load_dev_fixture,
)


def _stub(distractors):
    return lambda _prompt: json.dumps({"distractors": distractors})


F16_QID = "EXAM_1A434000_P0011_01::E0"


def test_load_dev_fixture_f16():
    qid, points = load_dev_fixture("F16_qigu_gebu")
    assert qid == F16_QID
    assert len(points) == 7
    assert {p.point_id for p in points} == {"a1", "a2", "a3", "a4", "a5", "a6", "a7"}
    assert next(p for p in points if p.point_id == "a5").statement.startswith("分层剥开")


def test_generates_ok_with_valid_distractors():
    _, points = load_dev_fixture("F16_qigu_gebu")
    fn = _stub([
        {"text": "喷灯烘烤后直接重贴不剥开", "error_code": "E06"},
        {"text": "用水泥砂浆抹平鼓泡即可", "error_code": "E01"},
        {"text": "整片屋面铲除重做防水层", "error_code": "E05"},
    ])
    res = generate_point_select_item(points, complete_fn=fn, target_point_id="a5", dev_fixture=True)
    assert res.status == GenStatus.OK, res.report
    # correct option is the scoring point原文 verbatim (LLM never touched it)
    assert res.item["correct_options"][0]["text"] == "分层剥开旧卷材(关键区分点)"
    assert res.item["correct_options"][0]["source_scoring_point_id"] == "a5"


def test_collision_distractor_exhausts_to_degraded():
    _, points = load_dev_fixture("F16_qigu_gebu")
    # distractor equals the correct option → RTG1 BLOCK every attempt
    fn = _stub([
        {"text": "分层剥开旧卷材(关键区分点)", "error_code": "E06"},
        {"text": "用水泥砂浆抹平鼓泡即可", "error_code": "E01"},
    ])
    res = generate_point_select_item(points, complete_fn=fn, target_point_id="a5", dev_fixture=True)
    assert res.status == GenStatus.DEGRADED
    assert res.item is None
    assert res.attempts == 3  # 1 + max_regen(2)


def test_bad_error_code_degrades():
    _, points = load_dev_fixture("F16_qigu_gebu")
    fn = _stub([{"text": "喷灯烘烤后直接重贴不剥开", "error_code": "E99"}])
    res = generate_point_select_item(points, complete_fn=fn, target_point_id="a5", dev_fixture=True)
    assert res.status == GenStatus.DEGRADED


def test_needs_review_routes_human():
    _, points = load_dev_fixture("F16_qigu_gebu")
    fn = _stub([
        {"text": "喷灯烘烤后直接重贴不剥开", "error_code": "NEEDS_REVIEW"},
        {"text": "用水泥砂浆抹平鼓泡即可", "error_code": "E01"},
    ])
    res = generate_point_select_item(points, complete_fn=fn, target_point_id="a5", dev_fixture=True)
    assert res.status == GenStatus.NEEDS_HUMAN


def test_regenerate_then_pass():
    _, points = load_dev_fixture("F16_qigu_gebu")
    good = [
        {"text": "喷灯烘烤后直接重贴不剥开", "error_code": "E06"},
        {"text": "用水泥砂浆抹平鼓泡即可", "error_code": "E01"},
    ]
    bad = [{"text": "分层剥开旧卷材(关键区分点)", "error_code": "E06"}]  # collision → BLOCK
    calls = {"n": 0}

    def fn(_prompt):
        calls["n"] += 1
        return json.dumps({"distractors": bad if calls["n"] == 1 else good})

    res = generate_point_select_item(points, complete_fn=fn, target_point_id="a5", dev_fixture=True)
    assert res.status == GenStatus.OK
    assert res.attempts == 2


def test_non_dev_requires_whitelisted_qid():
    _, points = load_dev_fixture("F16_qigu_gebu")
    fn = _stub([{"text": "x", "error_code": "E01"}])
    # non-dev call with an un-whitelisted qid → refused (production whitelist is empty)
    with pytest.raises(WhitelistError):
        generate_point_select_item(points, complete_fn=fn, qid=F16_QID, dev_fixture=False)
