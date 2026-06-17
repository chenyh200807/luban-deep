"""
SubmissionGraderAgent explanation schema (plan §Phase 4 Step 4.2 / Batch D.2).

定义错题解释必须包含的 7 段（plus 题型特定段），并提供：
  * 提取（best-effort）函数：从自由文本 LLM 输出中按 heading 抽段。
  * 程序化校验：返回缺段列表（trace 字段 ``explanation_section_miss``）。
  * 模板兜底：缺段时填充安全模板，保证用户不会看到空段。

刻意不引入 pydantic 依赖（项目当前的轻量风格），保持 stdlib 实现，
便于在 turn runtime 任何位置调用。

This file is purely additive — existing SubmissionGraderAgent 行为不变；
新增 ``validate_explanation_sections()`` 由 capability 调用方使用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable


# 7 个必备段（plan §Phase 4 Step 4.2）。
REQUIRED_SECTION_KEYS: tuple[str, ...] = (
    "verdict",            # 阅卷结论
    "correct_answer",     # 正确答案或采分点
    "why_wrong",          # 为什么用户答案错
    "knowledge_point",    # 对应知识点讲解
    "common_pitfall",     # 易错点
    "mnemonic",           # 记忆口诀 / 记忆抓手
    "next_practice",      # 下一步练什么
)

# 选择题额外段。
CHOICE_EXTRA_KEYS: tuple[str, ...] = ("option_analysis",)
# 案例题额外段。
CASE_EXTRA_KEYS: tuple[str, ...] = ("scoring_points_hit", "scoring_points_missed", "rewritten_answer")


# 中文别名 → schema key。允许 LLM 用自然 heading 输出。
_SECTION_ALIASES: dict[str, str] = {
    "阅卷结论": "verdict",
    "判分结论": "verdict",
    "结论": "verdict",
    "正确答案": "correct_answer",
    "采分点": "correct_answer",
    "标准答案": "correct_answer",
    "参考答案": "correct_answer",
    "为什么错": "why_wrong",
    "错因": "why_wrong",
    "知识点": "knowledge_point",
    "知识点讲解": "knowledge_point",
    "考点": "knowledge_point",
    "易错点": "common_pitfall",
    "常见陷阱": "common_pitfall",
    "记忆口诀": "mnemonic",
    "记忆抓手": "mnemonic",
    "口诀": "mnemonic",
    "下一步": "next_practice",
    "下一步练什么": "next_practice",
    "下一步练习": "next_practice",
    "建议": "next_practice",
    "逐项解析": "option_analysis",
    "选项解析": "option_analysis",
    "采分点命中": "scoring_points_hit",
    "命中点": "scoring_points_hit",
    "漏点": "scoring_points_missed",
    "丢分点": "scoring_points_missed",
    "得分表达改写": "rewritten_answer",
    "改写": "rewritten_answer",
}

# Fallback 模板（"仍缺时模板兜底"，plan §Phase 4 Step 4.2）。
# 默认模板假设本轮存在服务端 grading_result / grading_key authority。
_FALLBACK_TEMPLATES: dict[str, str] = {
    "verdict": "本题判定见服务端 grading_result。",
    "correct_answer": "正确答案以服务端 grading_key.correct_answer 为准。",
    "why_wrong": "本题答案与标准不一致；具体偏差请见 grading_result.error_events。",
    "knowledge_point": "本题所属知识点见 grading_result.next_training_signal.focus。",
    "common_pitfall": "本题暂无系统化易错点说明，建议结合 grading_keywords 自查。",
    "mnemonic": "本题暂无现成记忆口诀，可按错因关键词自建。",
    "next_practice": "建议针对当前错因继续做 3 题同类训练。",
    "option_analysis": "暂无逐项解析，请参考 grading_key.scoring_points。",
    "scoring_points_hit": "暂无采分点命中明细。",
    "scoring_points_missed": "暂无漏点明细，请参考 grading_result.error_events。",
    "rewritten_answer": "暂无得分表达改写示例。",
}

# 开放世界判分（无题库标准答案 authority）专用兜底模板。根因修复 2026-06-11：
# 此路径没有服务端 grading_result / grading_key，措辞必须诚实，不得声称题库官方结论，
# 否则会把开放裁决洗白成 authority（contracts/capability.md §硬约束 40）。
_OPEN_WORLD_FALLBACK_TEMPLATES: dict[str, str] = {
    "verdict": "本题暂无题库标准答案，判定以本轮基于教材/规范的开放裁决为准，非题库官方结论。",
    "correct_answer": "本题暂无题库标准答案；参考答案以本轮教材/规范推理为准，不是题库官方答案。",
    "why_wrong": "本题答案与本轮教材/规范判定不一致；具体偏差请见上文解析。",
    "knowledge_point": "本题所属知识点请见上文解析。",
    "common_pitfall": "本题暂无系统化易错点说明，建议结合题干与教材/规范自查。",
    "mnemonic": "本题暂无现成记忆口诀，可按错因关键词自建。",
    "next_practice": "建议针对当前错因继续做 3 题同类训练。",
    "option_analysis": "暂无逐项解析，请结合题干与教材/规范自查。",
    "scoring_points_hit": "暂无采分点命中明细。",
    "scoring_points_missed": "暂无漏点明细，请结合教材/规范自查。",
    "rewritten_answer": "暂无得分表达改写示例。",
}


@dataclass
class ExplanationSections:
    """Parsed sections of a learner-facing explanation."""

    sections: dict[str, str] = field(default_factory=dict)
    question_type: str = ""
    is_correct: bool | None = None

    def missing_required(self) -> list[str]:
        required = list(REQUIRED_SECTION_KEYS)
        if str(self.question_type or "").lower() in {"choice", "single_choice", "multi_choice"} and (
            self.is_correct is False
        ):
            required.extend(CHOICE_EXTRA_KEYS)
        if str(self.question_type or "").lower() in {"case", "written", "subjective"}:
            required.extend(CASE_EXTRA_KEYS)
        return [key for key in required if not str(self.sections.get(key, "")).strip()]


def parse_explanation_sections(
    explanation_text: str,
    *,
    question_type: str = "",
    is_correct: bool | None = None,
) -> ExplanationSections:
    """Best-effort 提取段落。LLM 输出可能用 ``### 阅卷结论`` 或 ``**阅卷结论**：`` 等。

    解析规则：
      * 寻找形如 ``[#]+ 标题`` 或 ``标题：`` 的 anchor。
      * 用别名映射成 schema key。
      * 段落正文 = 下一 anchor 之前的连续文本。
    """
    text = str(explanation_text or "").strip()
    sections: dict[str, str] = {}
    if not text:
        return ExplanationSections(sections=sections, question_type=question_type, is_correct=is_correct)

    # 标准化换行。
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 先 try heading 形式：`### 标题` / `## 标题` / `#### 标题`。
    heading_pattern = re.compile(r"^\s*#+\s*([^\n#：:]+?)\s*(?::|：)?\s*$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))
    if matches:
        for index, match in enumerate(matches):
            raw_title = match.group(1).strip()
            key = _resolve_alias(raw_title)
            if not key:
                continue
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body and key not in sections:
                sections[key] = body
        if sections:
            return ExplanationSections(
                sections=sections, question_type=question_type, is_correct=is_correct
            )

    # Fallback：`标题：xxx` 同行形式。
    inline_pattern = re.compile(r"^\s*[*\-]?\s*([一-鿿]+?)\s*[:：]\s*(.+?)\s*$", re.MULTILINE)
    for match in inline_pattern.finditer(text):
        raw_title = match.group(1).strip()
        body = match.group(2).strip()
        key = _resolve_alias(raw_title)
        if key and body and key not in sections:
            sections[key] = body

    return ExplanationSections(sections=sections, question_type=question_type, is_correct=is_correct)


def validate_explanation_sections(
    explanation_text: str,
    *,
    question_type: str = "",
    is_correct: bool | None = None,
) -> tuple[ExplanationSections, list[str]]:
    """Parse + 计算缺段。

    返回 ``(parsed, missing_keys)``。``missing_keys`` 即 trace 字段
    ``explanation_section_miss`` 的内容。
    """
    parsed = parse_explanation_sections(
        explanation_text, question_type=question_type, is_correct=is_correct
    )
    return parsed, parsed.missing_required()


def apply_fallback_templates(
    parsed: ExplanationSections,
    *,
    missing: Iterable[str] | None = None,
    authority_present: bool = True,
) -> ExplanationSections:
    """Self-repair 仍失败时调用：用模板填充缺段，保证用户不会看到空段。

    ``authority_present=False`` 表示本轮是开放世界判分（无题库 grading_result /
    grading_key），改用诚实模板，避免把开放裁决洗白成题库官方结论
    （contracts/capability.md §硬约束 40）。

    返回新的 ExplanationSections（不修改入参）。
    """
    templates = _FALLBACK_TEMPLATES if authority_present else _OPEN_WORLD_FALLBACK_TEMPLATES
    keys = list(missing) if missing is not None else parsed.missing_required()
    sections = dict(parsed.sections)
    for key in keys:
        if key in templates and not str(sections.get(key, "")).strip():
            sections[key] = templates[key]
    return ExplanationSections(
        sections=sections, question_type=parsed.question_type, is_correct=parsed.is_correct
    )


def _resolve_alias(title: str) -> str:
    """Map 中文标题/英文 key 到 schema key。"""
    raw = str(title or "").strip()
    if not raw:
        return ""
    # 直接 hit schema key
    lowered = raw.lower()
    all_keys = set(REQUIRED_SECTION_KEYS) | set(CHOICE_EXTRA_KEYS) | set(CASE_EXTRA_KEYS)
    if lowered in all_keys:
        return lowered
    # 中文别名
    for alias, key in _SECTION_ALIASES.items():
        if alias in raw:
            return key
    return ""


__all__ = (
    "REQUIRED_SECTION_KEYS",
    "CHOICE_EXTRA_KEYS",
    "CASE_EXTRA_KEYS",
    "ExplanationSections",
    "parse_explanation_sections",
    "validate_explanation_sections",
    "apply_fallback_templates",
)
