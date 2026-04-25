from __future__ import annotations


def test_normalize_exam_track_accepts_canonical_and_chinese_aliases() -> None:
    from deeptutor.services.exam_track import normalize_exam_track

    assert normalize_exam_track("first_cost") == "first_cost"
    assert normalize_exam_track("一造") == "first_cost"
    assert normalize_exam_track("一级造价工程师") == "first_cost"
    assert normalize_exam_track("一建") == "first_construction"
    assert normalize_exam_track("二建") == "second_construction"


def test_infer_exam_track_from_user_text_prefers_explicit_cost_over_construction() -> None:
    from deeptutor.services.exam_track import infer_exam_track_from_text

    assert infer_exam_track_from_text("不是一建，是一造案例题") == "first_cost"
    assert infer_exam_track_from_text("不是一造，是一建案例题") == "first_construction"
    assert infer_exam_track_from_text("请按一级造价工程师考试口径回答") == "first_cost"
    assert infer_exam_track_from_text("一建建筑实务这题怎么答") == "first_construction"
    assert infer_exam_track_from_text("普通防水题怎么答") == ""


def test_infer_exam_track_from_user_text_ignores_negated_track_mentions() -> None:
    from deeptutor.services.exam_track import infer_denied_exam_tracks_from_text, infer_exam_track_from_text

    assert infer_exam_track_from_text("不是一造，是一建案例题") == "first_construction"
    assert infer_exam_track_from_text("不是一建，是二建") == "second_construction"
    assert infer_exam_track_from_text("不是二造，是一造") == "first_cost"
    assert infer_exam_track_from_text("别按一建，按二建建筑实务") == "second_construction"
    assert infer_exam_track_from_text("不是一造") == ""
    assert infer_denied_exam_tracks_from_text("不是一造") == {"first_cost"}
    assert infer_denied_exam_tracks_from_text("别按一建，按二建建筑实务") == {"first_construction"}


def test_infer_exam_track_from_user_text_does_not_persist_comparison_queries() -> None:
    from deeptutor.services.exam_track import has_multiple_exam_track_mentions, infer_exam_track_from_text

    assert infer_exam_track_from_text("一建和一造有什么区别") == ""
    assert infer_exam_track_from_text("一造和一建有什么区别") == ""
    assert infer_exam_track_from_text("我该考一建还是一造") == ""
    assert infer_exam_track_from_text("一级建造师和一级造价工程师哪个更适合我") == ""
    assert has_multiple_exam_track_mentions("一建和一造有什么区别") is True
    assert has_multiple_exam_track_mentions("我该考一建还是一造") is True
    assert has_multiple_exam_track_mentions("不是一建，是一造案例题") is False
