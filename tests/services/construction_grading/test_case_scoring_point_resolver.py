"""轻练采分点源 resolver:教研 consensus + 编译库投影;fail-closed 到教研 verdict。"""
from __future__ import annotations

import pytest

import json

from deeptutor.services.construction_grading.case_light_practice_contract import (
    PointType,
    WhitelistError,
    score_conjunction_group,
)
from deeptutor.services.construction_grading.case_scoring_point_resolver import (
    project_scoring_points,
    resolve_scoring_points,
)

_RUBRIC = [
    {"qid": "Q::E0", "point_id": "p1", "text": "分层剥开旧卷材", "required_terms": ["分层剥开"], "score": 0.3},
    {"qid": "Q::E0", "point_id": "p2", "text": "喷灯烘烤槎口", "required_terms": ["喷灯烘烤"], "score": 0.2},
]


def _review(status, points):
    return {"qid": "Q::E0", "consensus": {"status": status}, "points": points}


def test_consensus_passed_projects_points():
    review = _review("passed", [
        {"point_id": "p1", "proposed_sub_no": 1, "point_type": "程序"},
        {"point_id": "p2", "proposed_sub_no": 1, "point_type": "程序", "conjunction_group": "g1"},
    ])
    pts = project_scoring_points("Q::E0", review, _RUBRIC)
    assert len(pts) == 2
    p1 = next(p for p in pts if p.point_id == "p1")
    assert p1.statement == "分层剥开旧卷材"
    assert p1.sub_no == "1" and p1.sub_qid == "Q::E0::sub1"
    assert p1.required_terms == ("分层剥开",) and p1.max_score == 0.3
    assert p1.authority_source == "official_answer"
    assert next(p for p in pts if p.point_id == "p2").conjunction_group == "g1"


def test_consensus_not_passed_yields_empty():
    review = _review("pending", [{"point_id": "p1", "proposed_sub_no": 1}])
    assert project_scoring_points("Q::E0", review, _RUBRIC) == []
    review2 = {"qid": "Q::E0", "consensus": None, "points": [{"point_id": "p1", "proposed_sub_no": 1}]}
    assert project_scoring_points("Q::E0", review2, _RUBRIC) == []


def test_missing_sub_no_or_missing_rubric_point_skipped():
    review = _review("passed", [
        {"point_id": "p1"},                              # 无 sub_no → 跳
        {"point_id": "p2", "proposed_sub_no": 2},        # 有 sub_no + 编译库有 → 出
        {"point_id": "ghost", "proposed_sub_no": 3},     # 编译库无此点 → 跳
    ])
    pts = project_scoring_points("Q::E0", review, _RUBRIC)
    assert [p.point_id for p in pts] == ["p2"]


def test_resolve_fail_closed_on_empty_whitelist():
    # 生产白名单为空(教研未验收)→ 任何 qid 被白名单门拒。
    with pytest.raises(WhitelistError):
        resolve_scoring_points("EXAM_1A434000_P0011_01::E0")


def test_filled_verdict_lights_up_whole_chain_end_to_end(tmp_path):
    """人门前证明:一旦教研填了 verdict,白名单门就打开、resolver 出真采分点、
    判分引擎就能算——「一动手门就开」是**证明**的,不是**声称**的(反自证)。

    模拟教研验收落盘(不动生产白名单),走 `resolve_scoring_points` 的**白名单门入口**
    (非内层 project_*),端到端:verdict passed → 白名单 allowed → 出采分点 → 合取门判分。
    """
    qid = "EXAM_LIGHTUP_PROOF::E0"

    # ① 模拟教研 verdict 落盘:consensus passed + 两个原子采分点带 sub_no
    review_dir = tmp_path / "segmentation_gold"
    review_dir.mkdir()
    (review_dir / f"{qid.replace('::', '__')}.review.json").write_text(
        json.dumps({
            "qid": qid,
            "consensus": {"status": "passed"},
            "points": [
                {"point_id": "k", "proposed_sub_no": 1, "point_type": "程序"},   # 关键点
                {"point_id": "s", "proposed_sub_no": 1, "point_type": "程序"},
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    # ② 编译库原文(采分点唯一真值,resolver 只搬运)
    rubric_file = tmp_path / "case_rubric_scored.json"
    rubric_file.write_text(
        json.dumps({"records": [
            {"qid": qid, "point_id": "k", "text": "分层剥开旧卷材", "required_terms": ["分层剥开"], "score": 0.3},
            {"qid": qid, "point_id": "s", "text": "喷灯烘烤槎口", "required_terms": ["喷灯烘烤"], "score": 0.2},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )

    # ③ 教研填完 → 白名单 allowed(fill_case_whitelist_from_review 的落盘形态)
    whitelist_file = tmp_path / "whitelist.v0.json"
    whitelist_file.write_text(
        json.dumps({"entries": [{"qid": qid, "status": "allowed"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    # ④ 走白名单门入口:门此刻**打开**(不再 fail-closed)→ 出真采分点
    pts = resolve_scoring_points(
        qid, review_dir=review_dir, rubric_path=rubric_file, whitelist_path=whitelist_file,
    )
    assert {p.point_id for p in pts} == {"k", "s"}
    assert next(p for p in pts if p.point_id == "k").statement == "分层剥开旧卷材"
    assert all(p.authority_source == "official_answer" for p in pts)  # 通道①

    # ⑤ 真采分点直接喂判分引擎:漏关键点判更低分(复现 live 语义,端到端闭合)
    full = score_conjunction_group(pts, {"k", "s"})
    missing_key = score_conjunction_group(pts, {"s"})
    assert abs(full - 0.5) < 1e-9
    assert abs(missing_key - 0.2) < 1e-9  # 漏『分层剥开』只得 0.2 < 满分 0.5


def test_resolver_to_orchestrator_conjunction_end_to_end(tmp_path):
    """capstone:证明整条**红线安全**链 resolver→编排器 在白名单-OPEN 路径真跑通。

    模拟教研 verdict(判断改正小问,带 conjunction_group/role/point_type=合取子)→ 白名单开 →
    resolve_scoring_points 出真采分点 → grade_ready_subquestion 编排合取门判分。
    证明:owner 一填 verdict(A)+确认 tag(E),从教研切分→采分点→确定性判分整条链活,
    **只差层③那一个生产调用点**(§3 红线 + Q1/Q2,owner 门)。
    """
    from deeptutor.services.construction_grading.case_grading_composition import (
        grade_ready_subquestion,
    )

    qid = "EXAM_CONJ_CAPSTONE::E0"
    review_dir = tmp_path / "segmentation_gold"
    review_dir.mkdir()
    (review_dir / f"{qid.replace('::', '__')}.review.json").write_text(
        json.dumps({
            "qid": qid,
            "consensus": {"status": "passed"},
            "points": [
                {"point_id": "flaw", "proposed_sub_no": 1, "point_type": "合取子",
                 "conjunction_group": "g1", "conjunction_role": "flaw"},
                {"point_id": "fix", "proposed_sub_no": 1, "point_type": "合取子",
                 "conjunction_group": "g1", "conjunction_role": "correction"},
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    rubric_file = tmp_path / "case_rubric_scored.json"
    rubric_file.write_text(
        json.dumps({"records": [
            {"qid": qid, "point_id": "flaw", "text": "指出防水层未做附加层", "required_terms": [], "score": 0.5},
            {"qid": qid, "point_id": "fix", "text": "阴阳角应做附加增强层", "required_terms": [], "score": 0.5},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    whitelist_file = tmp_path / "whitelist.v0.json"
    whitelist_file.write_text(
        json.dumps({"entries": [{"qid": qid, "status": "allowed"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    pts = resolve_scoring_points(
        qid, review_dir=review_dir, rubric_path=rubric_file, whitelist_path=whitelist_file,
    )
    assert {p.point_id for p in pts} == {"flaw", "fix"}
    assert all(p.point_type is PointType.CONJUNCTION_MEMBER for p in pts)

    # 编排器合取门:找错∧改正都命中给满分;只找错不改正 → 0(§4 红线)
    both = grade_ready_subquestion(pts, {"flaw": True, "fix": True})
    only_flaw = grade_ready_subquestion(pts, {"flaw": True, "fix": False})
    assert both.awarded == pytest.approx(1.0) and both.max_score == pytest.approx(1.0)
    assert only_flaw.awarded == 0.0
    assert both.official_score_allowed is False  # 金标 kappa 转正前不铸官方分
