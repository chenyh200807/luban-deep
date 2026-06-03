from __future__ import annotations

from deeptutor.services.citations.schema import CitationSourceRef


def format_citation_footer(refs: list[CitationSourceRef]) -> str:
    if not refs:
        return (
            "依据\n"
            "本轮未使用可公开引用的教材、规范、题库或学习证据；"
            "以上内容仅为通用对话说明，不进入学习事实或评分依据。"
        )
    lines = ["依据"]
    for ref in refs:
        locator = f"｜{ref.locator}" if ref.locator else ""
        lines.append(f"{ref.marker}{ref.title}{locator}")
    return "\n".join(lines)
