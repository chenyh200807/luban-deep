"""Markdown style contract and normalizer for TutorBot answers."""

from __future__ import annotations

import re

_LABELLED_ORDERED_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+\*\*([^*\n]+?)\*\*([：:])\s*(.+)$")
_LABELLED_BULLET_ITEM_RE = re.compile(r"^\s*([-*+])\s+\*\*([^*\n]+?)\*\*([：:])\s*(.+)$")
_LABELLED_PARAGRAPH_RE = re.compile(r"^\s*\*\*([^*\n]+?)\*\*([：:])\s*(.+)$")
_LABELLED_ORDERED_ONLY_RE = re.compile(r"^\s*(\d+)\.\s+\*\*([^*\n]+?)\*\*([：:])\s*$")
_LABELLED_BULLET_ONLY_RE = re.compile(r"^\s*([-*+])\s+\*\*([^*\n]+?)\*\*([：:])\s*$")
_LABELLED_PARAGRAPH_ONLY_RE = re.compile(r"^\s*\*\*([^*\n]+?)\*\*([：:])\s*$")
_INDENTED_LIST_RE = re.compile(r"^\s{2,}((?:[-*+])|\d+\.)\s+")

_MARKDOWN_STYLE_INSTRUCTION = """
输出排版必须遵守以下 Markdown 样式约束：
- 优先使用稳定区块，常用结构为 `## 结论`、`## 判断依据`、`## 踩分点`、`## 易错点`。
- 列表只使用单层有序列表或单层无序列表，不要嵌套列表，不要在某个 bullet 下继续缩进子列表。
- 若列表项里需要小标签，统一写成 `- **标签：** 内容` 或 `1. **标签：** 内容`，把冒号放进加粗标签内。
- 举例、对比、口诀等需要继续列点时，直接另起同层列表，不要写成“某个列表项下面再缩进 2 层”。
- 箭头表达统一写成 `文本 → **结论**`，箭头前后保留空格。
- 每个区块之间空一行，不要连续输出 3 个及以上空行。
- 直接输出纯 Markdown 正文，不要使用 HTML，不要把正文包进 ```markdown 代码块。
- 非必要不要用复杂表格；移动端优先短段落、短列表、强结论。
""".strip()


def get_markdown_style_instruction() -> str:
    return _MARKDOWN_STYLE_INSTRUCTION


def normalize_markdown_for_tutorbot(text: str | None) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return ""

    lines = normalized.split("\n")
    out: list[str] = []
    in_fence = False
    previous_blank = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.lstrip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            previous_blank = False
            continue

        if in_fence:
            out.append(line)
            previous_blank = False
            continue

        line = line.replace("\t", "  ")
        if not line.strip():
            if previous_blank:
                continue
            out.append("")
            previous_blank = True
            continue

        previous_blank = False
        line = _INDENTED_LIST_RE.sub(r"\1 ", line)
        line = re.sub(r"\s*→\s*", " → ", line)
        line = _normalize_labelled_item(line)
        out.append(line.rstrip())

    return "\n".join(out).strip()


def _normalize_labelled_item(line: str) -> str:
    ordered_only_match = _LABELLED_ORDERED_ONLY_RE.match(line)
    if ordered_only_match:
        return f"{ordered_only_match.group(1)}. **{ordered_only_match.group(2).strip()}：**"

    ordered_match = _LABELLED_ORDERED_ITEM_RE.match(line)
    if ordered_match:
        return f"{ordered_match.group(1)}. **{ordered_match.group(2).strip()}：** {ordered_match.group(4).strip()}"

    bullet_only_match = _LABELLED_BULLET_ONLY_RE.match(line)
    if bullet_only_match:
        return f"{bullet_only_match.group(1)} **{bullet_only_match.group(2).strip()}：**"

    bullet_match = _LABELLED_BULLET_ITEM_RE.match(line)
    if bullet_match:
        return f"{bullet_match.group(1)} **{bullet_match.group(2).strip()}：** {bullet_match.group(4).strip()}"

    paragraph_only_match = _LABELLED_PARAGRAPH_ONLY_RE.match(line)
    if paragraph_only_match:
        return f"**{paragraph_only_match.group(1).strip()}：**"

    paragraph_match = _LABELLED_PARAGRAPH_RE.match(line)
    if paragraph_match:
        return f"**{paragraph_match.group(1).strip()}：** {paragraph_match.group(3).strip()}"

    return line


__all__ = [
    "get_markdown_style_instruction",
    "normalize_markdown_for_tutorbot",
]
