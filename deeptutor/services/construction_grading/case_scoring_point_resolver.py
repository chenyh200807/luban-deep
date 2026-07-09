"""轻练采分点源 resolver —— 把"教研验收的切分 + 编译库采分点原文"投影成 LubanCaseScoringPoint。

§3 新造:把采分点接上**真数据源**(不再只吃 dev fixture / 传参)。优先级(§1限制②):
母题作答层 signed > 编译库切干净(通道①)> 开放世界现抽。本 resolver 实现**编译库通道①**
投影:采分点原文(statement/required_terms/分值)来自编译库,**sub_no / 原子性 / 非平点结构
来自教研 consensus 的 `segmentation_gold/<qid>.review.json`**(教研 verdict 才是真值)。

**根因**:编译库采分点缺 `sub_no`(欠切分);sub_no 是教研切分验收才产生的源事实。所以
本 resolver **fail-closed**:qid 不在白名单 → 拒;review 未 consensus-passed → 返回空。
教研填完 verdict 前,它一个采分点都不出(未过教研的 qid 不许出给学员,§4 红线)。

只读投影:读编译库落盘 JSON + review.json + 白名单,**不改任何生产模块**(review-only)。
采分点是唯一真值,resolver 只搬运不改写。Deterministic: no LLM。
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    PracticeGradingKind,
    SourceRef,
    WHITELIST_PATH,
    assert_qid_allowed,
    load_whitelist,
)

# 教研在 review.json 标的确定性 kind(字符串 → 枚举);未标/非法 → None(走默认点选)。
_KIND_BY_VALUE = {k.value: k for k in PracticeGradingKind}

_RUBRIC_SUPPLY = (
    Path(__file__).resolve().parent
    / "runtime_supply"
    / "v_case_rubric_scored"
    / "case_rubric_scored.json"
)
_REVIEW_DIR = (
    Path(__file__).resolve().parents[3] / "docs/原始数据/考点原料/segmentation_gold"
)

# 教研 review 里 point_type 中文 → PointType(缺省按程序)。
_POINT_TYPE_BY_LABEL = {t.value: t for t in PointType}


def project_scoring_points(
    qid: str,
    review: Mapping[str, object],
    rubric_records: Sequence[Mapping[str, object]],
) -> list[LubanCaseScoringPoint]:
    """纯投影:join 教研 review(sub_no/原子/非平点)+ 编译库 records(原文/required_terms/分值)
    → LubanCaseScoringPoint。仅 review.consensus.status=="passed" 才投影;否则返回空。"""
    consensus = review.get("consensus") or {}
    if consensus.get("status") != "passed":
        return []  # fail-closed:未过双教研 consensus,一个采分点都不出

    text_by_id = {str(r.get("point_id")): r for r in rubric_records if r.get("qid") == qid}
    points: list[LubanCaseScoringPoint] = []
    for rp in review.get("points") or []:
        pid = str(rp.get("point_id"))
        sub_no = rp.get("proposed_sub_no")
        if sub_no is None:
            continue  # 未标 sub_no 的点不出(切分未定)
        rec = text_by_id.get(pid)
        if rec is None:
            continue  # 编译库无此点(溯源断链)→ 不出
        ref = SourceRef("exam_reference_answer", qid)
        ptype = _POINT_TYPE_BY_LABEL.get(str(rp.get("point_type") or ""), PointType.PROCEDURE)
        points.append(
            LubanCaseScoringPoint(
                point_id=pid,
                sub_no=str(sub_no),
                qid=qid,
                sub_qid=f"{qid}::sub{sub_no}",
                statement=str(rec.get("text", "")),
                authority_source="official_answer",  # 通道①
                point_type=ptype,
                required_terms=tuple(rec.get("required_terms") or ()),
                acceptable_variants=(AcceptableVariant("_", ref),),
                max_score=float(rec.get("score") or 0.0),
                textbook_source_refs=(ref,),
                answer_key_authority="exam_reference_answer",
                conjunction_group=(str(rp["conjunction_group"]) if rp.get("conjunction_group") else None),
                ordering_group=(str(rp["ordering_group"]) if rp.get("ordering_group") else None),
                list_cap=(int(rp["list_cap"]) if rp.get("list_cap") is not None else None),
                practice_grading_kind=_KIND_BY_VALUE.get(str(rp.get("practice_grading_kind") or "")),
            )
        )
    return points


def _load_rubric_records(rubric_path: Path = _RUBRIC_SUPPLY) -> list[dict]:
    data = json.loads(Path(rubric_path).read_text(encoding="utf-8"))
    return list(data.get("records") or [])


def resolve_scoring_points(
    qid: str,
    *,
    review_dir: Path = _REVIEW_DIR,
    rubric_path: Path = _RUBRIC_SUPPLY,
    whitelist_path: Path = WHITELIST_PATH,
) -> list[LubanCaseScoringPoint]:
    """白名单门 + 读 review.json + 编译库 → 投影采分点。qid 未过白名单 → WhitelistError。"""
    assert_qid_allowed(qid, load_whitelist(whitelist_path))  # 未过教研验收 → 拒(fail-closed)
    review_file = Path(review_dir) / f"{qid.replace('::', '__')}.review.json"
    if not review_file.exists():
        return []
    review = json.loads(review_file.read_text(encoding="utf-8"))
    return project_scoring_points(qid, review, _load_rubric_records(rubric_path))


__all__ = ["project_scoring_points", "resolve_scoring_points"]
