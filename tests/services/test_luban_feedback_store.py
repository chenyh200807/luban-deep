"""LubanFeedbackStore 纯逻辑单测：归一化脱敏、统计聚合、跟进校验。

不触碰 Supabase/pg —— 只验证读模型的纯函数，DB 路径由生产端到端验收覆盖。
"""

from __future__ import annotations

import pytest

from deeptutor.services.luban_feedback_store import (
    compute_luban_feedback_stats,
    normalize_luban_feedback,
    validate_luban_feedback_patch,
)


def _row(**overrides):
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "created_at": "2026-05-29T10:00:00+00:00",
        "source_page": "luban-html-js-wechat-required",
        "survey_version": "v1",
        "nps": 4,
        "overall_satisfaction": 2,
        "most_valuable": "case_grading",
        "will_continue": "depends",
        "pay_willingness": "if_priced_right",
        "would_recommend": "maybe",
        "revisit_willingness": "very_willing",
        "attempt_count": "second",
        "exam_timeframe": "1to3m",
        "top_suggestion": "加真题模考",
        "unsolved_pain": "网络图计算没人纠错",
        "phone": "13812345678",
        "wechat_id": "luban_user",
        "status": "submitted",
        "operator_note": "",
        "raw_payload": {
            "one_word": "差点意思",
            "feat_case_grading": "5",
            "feat_error_coach": "4",
            "feat_qa": "na",
            "ease_of_use": "3",
            "accuracy": "4",
            "speed": "2",
            "problems": ["slow_loading", "cant_find"],
            "problems__other": "偶尔跳登录",
            "wanted_features": ["mock_exam", "mistake_book"],
            "wanted_features__other": "班主任跟进",
        },
    }
    base.update(overrides)
    return base


# ---------- normalize ----------

def test_normalize_masks_contact_by_default():
    out = normalize_luban_feedback(_row())
    assert out["phone"] == "138****78"
    assert out["wechat_id"] == "l********r"
    assert out["contact_revealed"] is False


def test_normalize_reveals_contact_for_admin():
    out = normalize_luban_feedback(_row(), reveal_contact=True)
    assert out["phone"] == "13812345678"
    assert out["wechat_id"] == "luban_user"
    assert out["contact_revealed"] is True


def test_normalize_parses_nps_and_one_word():
    out = normalize_luban_feedback(_row(nps="7"))
    assert out["nps"] == 7
    assert out["one_word"] == "差点意思"


def test_normalize_exposes_complete_survey_payload_for_bi_detail_and_export():
    out = normalize_luban_feedback(_row())
    assert out["feat_case_grading"] == "5"
    assert out["feat_error_coach"] == "4"
    assert out["feat_qa"] == "na"
    assert out["ease_of_use"] == "3"
    assert out["accuracy"] == "4"
    assert out["speed"] == "2"
    assert out["problems"] == ["slow_loading", "cant_find"]
    assert out["problems_other"] == "偶尔跳登录"
    assert out["wanted_features"] == ["mock_exam", "mistake_book"]
    assert out["wanted_features_other"] == "班主任跟进"


def test_normalize_handles_null_nps_and_empty_contact():
    out = normalize_luban_feedback(_row(nps=None, phone="", wechat_id=""))
    assert out["nps"] is None
    assert out["phone"] == ""
    assert out["wechat_id"] == ""


def test_normalize_int_phone_masking_short():
    out = normalize_luban_feedback(_row(phone="+852 9123 4567"))
    # 规范化已在写入侧完成；这里仅按数字脱敏
    assert out["phone"] == "852****67"


# ---------- stats ----------

def test_stats_empty_is_safe():
    stats = compute_luban_feedback_stats([])
    assert stats["summary"]["total_responses"] == 0
    assert stats["summary"]["nps_score"] == 0.0
    assert stats["summary"]["avg_satisfaction"] == 0.0
    assert stats["nps_breakdown"] == []


def test_stats_nps_score_promoters_minus_detractors():
    # 3 promoters(10,9,9), 1 passive(7), 1 detractor(3) → (3-1)/5*100 = 40.0
    rows = [
        normalize_luban_feedback(_row(nps=10)),
        normalize_luban_feedback(_row(nps=9)),
        normalize_luban_feedback(_row(nps=9)),
        normalize_luban_feedback(_row(nps=7)),
        normalize_luban_feedback(_row(nps=3)),
    ]
    stats = compute_luban_feedback_stats(rows)
    s = stats["summary"]
    assert s["promoters"] == 3
    assert s["passives"] == 1
    assert s["detractors"] == 1
    assert s["nps_base"] == 5
    assert s["nps_score"] == 40.0


def test_stats_avg_satisfaction_ignores_nulls():
    rows = [
        normalize_luban_feedback(_row(overall_satisfaction=5)),
        normalize_luban_feedback(_row(overall_satisfaction=3)),
        normalize_luban_feedback(_row(overall_satisfaction=None)),
    ]
    stats = compute_luban_feedback_stats(rows)
    assert stats["summary"]["avg_satisfaction"] == 4.0
    assert stats["summary"]["satisfaction_base"] == 2


def test_stats_revisit_and_contact_rates():
    rows = [
        normalize_luban_feedback(_row(revisit_willingness="very_willing", phone="13800000000")),
        normalize_luban_feedback(_row(revisit_willingness="ok", phone="", wechat_id="")),
        normalize_luban_feedback(_row(revisit_willingness="no", phone="", wechat_id="")),
    ]
    stats = compute_luban_feedback_stats(rows)
    s = stats["summary"]
    assert s["revisit_willing_count"] == 2
    assert s["with_contact_count"] == 1  # 仅第一条有联系方式


def test_stats_segmentation_breakdowns():
    rows = [
        normalize_luban_feedback(_row(attempt_count="first", exam_timeframe="within_1m")),
        normalize_luban_feedback(_row(attempt_count="first", exam_timeframe="passed")),
        normalize_luban_feedback(_row(attempt_count="second", exam_timeframe="within_1m")),
    ]
    stats = compute_luban_feedback_stats(rows)
    attempt = {r["attempt_count"]: r["count"] for r in stats["attempt_count_breakdown"]}
    assert attempt == {"first": 2, "second": 1}
    timeframe = {r["exam_timeframe"]: r["count"] for r in stats["exam_timeframe_breakdown"]}
    assert timeframe == {"within_1m": 2, "passed": 1}


# ---------- patch 校验 ----------

def test_validate_patch_accepts_known_status():
    assert validate_luban_feedback_patch({"status": "Contacted"}) == {"status": "contacted"}


def test_validate_patch_rejects_unknown_status():
    with pytest.raises(ValueError):
        validate_luban_feedback_patch({"status": "bogus"})


def test_validate_patch_truncates_operator_note():
    patch = validate_luban_feedback_patch({"operator_note": "x" * 5000})
    assert len(patch["operator_note"]) == 1000


def test_validate_patch_requires_editable_field():
    with pytest.raises(ValueError):
        validate_luban_feedback_patch({"nps": 9})
