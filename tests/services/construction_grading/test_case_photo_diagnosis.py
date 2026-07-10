"""拍照诊断骨架:读图↔判分解耦 + 证据回显 + 诊断非评分(§1.5D 红线)。"""
from __future__ import annotations

import pytest

from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant,
    LubanCaseScoringPoint,
    PointType,
    SourceRef,
)
from deeptutor.services.construction_grading.case_photo_diagnosis import (
    PhotoExtraction,
    RecognizedSpan,
    diagnose_photo,
)

_REF = SourceRef("exam_reference_answer", "起鼓割补")


def _point(pid, *terms, variants=()):
    return LubanCaseScoringPoint(
        point_id=pid, sub_no="起鼓割补", qid="Q::sub1", sub_qid="Q::sub1",
        statement=f"statement-{pid}", authority_source="official_answer",
        point_type=PointType.PROCEDURE, required_terms=tuple(terms),
        acceptable_variants=tuple(AcceptableVariant(v, _REF) for v in variants) or (AcceptableVariant("_", _REF),),
        max_score=0.3, textbook_source_refs=(_REF,), answer_key_authority="official_answer",
    )


_POINTS = [_point("a5", "分层剥开"), _point("a4", "喷灯烘烤")]


def test_matched_point_carries_evidence_span():
    ext = PhotoExtraction((
        RecognizedSpan("先喷灯烘烤旧卷材槎口", (10, 20, 200, 30), 0.92),
        RecognizedSpan("再分层剥开旧卷材", (10, 60, 200, 30), 0.88),
    ))
    r = diagnose_photo(ext, _POINTS)
    assert set(r.matched_point_ids) == {"a5", "a4"}
    a5 = next(d for d in r.diagnoses if d.point_id == "a5")
    # 证据回显:命中出现在哪段识别文本 + 原图区域 + 置信度
    assert a5.matched_term == "分层剥开"
    assert a5.evidence_span.text == "再分层剥开旧卷材"
    assert a5.evidence_span.region == (10, 60, 200, 30)
    assert a5.confidence == 0.88


def test_diagnosis_is_never_official_score():
    ext = PhotoExtraction((RecognizedSpan("分层剥开", (0, 0, 1, 1), 1.0),))
    assert diagnose_photo(ext, _POINTS).official_score_allowed is False


def test_decoupling_recognition_error_only_fixed_in_front_link():
    # OCR 把「分层剥开」误识成「分层剥离」(剥离≠剥开)→ a5 未命中。
    garbled = PhotoExtraction((RecognizedSpan("再分层剥离旧卷材", (10, 60, 200, 30), 0.7),))
    r1 = diagnose_photo(garbled, _POINTS)
    assert "a5" in r1.missed_point_ids

    # 学员纠正识别文本(只修前链)→ 重跑 diagnose 即命中,评分逻辑一字未变。
    corrected = PhotoExtraction((RecognizedSpan("再分层剥开旧卷材", (10, 60, 200, 30), 0.7),))
    r2 = diagnose_photo(corrected, _POINTS)
    assert "a5" in r2.matched_point_ids
    # 判分 = f(识别文本):同一采分点,唯一变量是文本,不是图像。


def test_missed_point_has_zero_confidence_and_no_evidence():
    ext = PhotoExtraction((RecognizedSpan("完全无关的文字", (0, 0, 1, 1), 0.9),))
    r = diagnose_photo(ext, _POINTS)
    for d in r.diagnoses:
        assert d.matched is False
        assert d.evidence_span is None
        assert d.confidence == 0.0


def test_acceptable_variant_matches():
    pts = [_point("a6", "重新粘贴", variants=("重贴新卷材",))]
    ext = PhotoExtraction((RecognizedSpan("最后重贴新卷材压实", (0, 0, 1, 1), 0.8),))
    r = diagnose_photo(ext, pts)
    assert r.matched_point_ids == ["a6"]
    assert next(d for d in r.diagnoses if d.point_id == "a6").matched_term == "重贴新卷材"


# ── 2026-07-09 Codex 复核回归 ────────────────────────────────────────────────


def test_required_terms_all_must_be_present():
    # required_terms 全需:只写出部分要素 → 不算命中(避免假阳送分)。
    pts = [_point("p", "找坡", "排水坡度")]
    only_one = PhotoExtraction((RecognizedSpan("基层应先找坡然后施工", (0, 0, 1, 1), 0.9),))
    assert diagnose_photo(only_one, pts).matched_point_ids == []
    both = PhotoExtraction((RecognizedSpan("找坡并控制排水坡度不小于2%", (0, 0, 1, 1), 0.9),))
    assert diagnose_photo(both, pts).matched_point_ids == ["p"]


def test_negation_context_not_matched():
    # 否定语境不算命中:"没有分层剥开" / "不应分层剥开" 不命中"分层剥开"。
    for txt in ("没有分层剥开旧卷材", "不应分层剥开旧卷材", "未做分层剥开"):
        ext = PhotoExtraction((RecognizedSpan(txt, (0, 0, 1, 1), 0.9),))
        r = diagnose_photo(ext, [_point("a5", "分层剥开")])
        assert r.missed_point_ids == ["a5"], f"{txt} 应因否定不命中"
    # 正常语境仍命中
    ok = PhotoExtraction((RecognizedSpan("并分层剥开旧卷材", (0, 0, 1, 1), 0.9),))
    assert diagnose_photo(ok, [_point("a5", "分层剥开")]).matched_point_ids == ["a5"]


def test_evidence_prefers_highest_confidence_span():
    # 多 span 含命中词 → 取最高置信 span 作证据(不再取第一个题干复述/低质量 span)。
    ext = PhotoExtraction((
        RecognizedSpan("题干复述: 喷灯烘烤这一步", (0, 0, 1, 1), 0.41),
        RecognizedSpan("作答: 喷灯烘烤旧卷材槎口", (0, 40, 1, 1), 0.95),
    ))
    r = diagnose_photo(ext, [_point("a4", "喷灯烘烤")])
    a4 = next(d for d in r.diagnoses if d.point_id == "a4")
    assert a4.confidence == 0.95
    assert a4.evidence_span.text == "作答: 喷灯烘烤旧卷材槎口"


def test_recognized_span_confidence_bounds():
    with pytest.raises(ValueError):
        RecognizedSpan("x", (0, 0, 1, 1), 1.5)
    with pytest.raises(ValueError):
        RecognizedSpan("x", (0, 0, 1, 1), -0.1)


def test_real_f16_points_under_realistic_ocr_and_front_link_correction():
    """反自证·真数据:用**真 F16 采分点**(load_dev_fixture,非玩具点)端到端验
    文→诊断,在**模拟真实 OCR 误差**下行为正确;并证明"识别错→纠正文本→重跑即正确"。

    范围诚实:图→文 OCR 是上游注入边界(生产 photo_answer 做,§1.5 defer 到 OCR 全闭环
    轨),本测试注入 PhotoExtraction=OCR 之后的文本,验的是本相位在范围内的"文→诊断"半。
    """
    from deeptutor.services.construction_grading.case_light_practice_generator import (
        load_dev_fixture,
    )

    _qid, points = load_dev_fixture("F16_qigu_gebu")

    # 模拟一份学员手写作答的 OCR 抽取:多数点写对,但关键点 a5「分层剥开」被 OCR
    # 低置信误识成「分层剥离」(剥离≠剥开);a1 只写了「割开」漏「放气」(多要素点半写)。
    ocr = PhotoExtraction((
        RecognizedSpan("用刀把鼓泡割开", (0, 0, 200, 30), 0.90),          # a1: 有割开、无放气
        RecognizedSpan("擦干水分后", (0, 40, 200, 30), 0.93),            # a2 命中
        RecognizedSpan("喷灯烘烤旧卷材槎口", (0, 80, 200, 30), 0.88),      # a4 命中
        RecognizedSpan("分层剥离旧卷材", (0, 120, 200, 30), 0.55),        # a5 近义误识(低置信)
        RecognizedSpan("重新粘贴新卷材压实刮平", (0, 160, 220, 30), 0.91),  # a6 + a7 命中
    ))
    r = diagnose_photo(ocr, points)

    # ① 真 OCR 误差下 fail-closed:a5 关键点因「剥离≠剥开」未命中(不假阳送分)
    assert "a5" not in r.matched_point_ids, "OCR 近义误识必须 fail-closed"
    # ② 多要素点 a1「割开∧放气」只写一半 → 未命中(required_terms 全需)
    assert "a1" not in r.matched_point_ids, "半写多要素点不得假阳命中"
    # ③ 写对的点真命中,且置信度从 OCR span 透传(证据回显)
    assert {"a2", "a4", "a6", "a7"} <= set(r.matched_point_ids)
    a4 = next(d for d in r.diagnoses if d.point_id == "a4")
    assert a4.matched and a4.confidence == 0.88 and a4.evidence_span is not None
    # ④ 诊断永不铸官方分
    assert r.official_score_allowed is False

    # ⑤ 前链纠错:学员把「分层剥离」改回「分层剥开」→ 重跑,评分逻辑一字未改 → a5 命中
    fixed = PhotoExtraction(tuple(
        RecognizedSpan(s.text.replace("分层剥离", "分层剥开"), s.region, s.confidence)
        for s in ocr.spans
    ))
    assert "a5" in diagnose_photo(fixed, points).matched_point_ids, (
        "识别错只在前链修:纠正文本重跑即正确,评分逻辑不变"
    )
