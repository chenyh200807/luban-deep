from deeptutor.tutorbot.markdown_style import (
    get_markdown_style_instruction,
    normalize_markdown_for_tutorbot,
)


def test_markdown_style_instruction_requires_single_level_lists_and_label_format() -> None:
    instruction = get_markdown_style_instruction()

    assert "单层有序列表或单层无序列表" in instruction
    assert "`- **标签：** 内容`" in instruction
    assert "不要嵌套列表" in instruction


def test_normalize_markdown_for_tutorbot_rewrites_labelled_items_and_flattens_nested_lists() -> None:
    raw = (
        "**拿分要点**：\n\n"
        "1. **时间限制**：必须记住24小时\n"
        "  - 屋面一级防水→**3道**\n"
        "  - 屋面二级防水  →  **2道**\n\n\n"
        "```markdown\n"
        "  - fenced block stays untouched\n"
        "```\n"
    )

    normalized = normalize_markdown_for_tutorbot(raw)

    assert "**拿分要点：**" in normalized
    assert "1. **时间限制：** 必须记住24小时" in normalized
    assert "- 屋面一级防水 → **3道**" in normalized
    assert "- 屋面二级防水 → **2道**" in normalized
    assert "\n\n\n" not in normalized
    assert "  - fenced block stays untouched" in normalized
