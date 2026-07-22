from __future__ import annotations

from deeptutor.services.observability.product_behavior_projection import (
    project_product_behavior_rows,
)


def test_projection_uses_canonical_first_run_question_label() -> None:
    row = project_product_behavior_rows(
        [{"key": "question:first_run.v1:qigu_gebu", "object_type": "question"}]
    )[0]

    assert row["display_label"] == "首次体验题｜屋面卷材起鼓"
    assert row["display_context"] == "微信小程序 · 首次体验 · 答题"
    assert row["content_kind"] == "question"


def test_projection_fails_closed_for_unknown_content() -> None:
    row = project_product_behavior_rows(
        [{"key": "future-content", "object_type": "future"}]
    )[0]

    assert row["display_label"] == "未识别内容（原始 ID：future-content）"
    assert row["content_kind"] == "unknown"


def test_projection_humanizes_wechat_module() -> None:
    row = project_product_behavior_rows([{"key": "history", "object_type": ""}])[0]

    assert row["display_label"] == "微信小程序 · 历史记录"
