from __future__ import annotations

from deeptutor.tutorbot.utils.helpers import normalize_message_content


def test_normalize_message_content_extracts_text_parts_and_image_placeholder() -> None:
    content = [
        {"type": "text", "text": "先看这张图。"},
        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
        {"content": "继续解释。"},
    ]

    assert normalize_message_content(content) == "先看这张图。 [image] 继续解释。"


def test_normalize_message_content_prefers_text_fields_over_json_dump() -> None:
    assert normalize_message_content({"type": "text", "text": "标准答案"}) == "标准答案"
    assert normalize_message_content({"message": "工具结果"}) == "工具结果"
