"""切分质量闸:确定性结构校验(§1限制② 过闸才进白名单)。"""
from __future__ import annotations

from deeptutor.services.construction_grading.case_segmentation_quality_gate import (
    check_segmentation_quality,
    passes_quality_gate,
)


def _review(points, status="passed"):
    return {"qid": "Q::E0", "consensus": {"status": status}, "points": points}


def test_well_formed_segmentation_passes():
    r = _review([
        {"point_id": "p1", "proposed_sub_no": 1},
        {"point_id": "p2", "proposed_sub_no": 2, "conjunction_group": "g1"},
        {"point_id": "p3", "proposed_sub_no": 2, "conjunction_group": "g1"},
    ])
    assert passes_quality_gate(r) is True
    assert check_segmentation_quality(r).issues == ()


def test_missing_sub_no_fails():
    r = _review([{"point_id": "p1"}])
    res = check_segmentation_quality(r)
    assert res.passed is False
    assert any("proposed_sub_no" in i for i in res.issues)


def test_conjunction_group_single_member_fails():
    # 合取组只有 1 个成员 = 坏切分(找错∧改正需两半)
    r = _review([{"point_id": "p1", "proposed_sub_no": 1, "conjunction_group": "g1"}])
    res = check_segmentation_quality(r)
    assert res.passed is False
    assert any("合取组" in i for i in res.issues)


def test_consensus_not_passed_fails():
    r = _review([{"point_id": "p1", "proposed_sub_no": 1}], status="pending")
    assert passes_quality_gate(r) is False


def test_duplicate_point_id_and_bad_list_cap_fail():
    r = _review([
        {"point_id": "p1", "proposed_sub_no": 1, "list_cap": 0},   # list_cap 非正
        {"point_id": "p1", "proposed_sub_no": 1},                  # 重复 point_id
    ])
    res = check_segmentation_quality(r)
    assert res.passed is False
    assert any("重复 point_id" in i for i in res.issues)
    assert any("list_cap" in i for i in res.issues)


def test_empty_points_fails():
    assert passes_quality_gate(_review([])) is False
