#!/usr/bin/env python
"""
Single-call grading feedback agent for quiz answer submissions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
from typing import Any

from deeptutor.agents.base_agent import BaseAgent
from deeptutor.agents.question.agents._anchor_terms import (
    extract_anchor_terms,
    render_anchor_contract,
)
from deeptutor.agents.question.agents.submission_grader_schema import (
    apply_fallback_templates,
    parse_explanation_sections,
)
from deeptutor.core.grounding import prepend_grounding
from deeptutor.core.trace import build_trace_metadata, new_call_id


class SubmissionGraderAgent(BaseAgent):
    """Grade a learner's quiz submission and return teaching feedback."""

    def __init__(self, language: str = "zh", **kwargs: Any) -> None:
        super().__init__(
            module_name="question",
            agent_name="submission_grader_agent",
            language=language,
            **kwargs,
        )

    async def process(
        self,
        *,
        user_message: str,
        question_context: dict[str, Any],
        history_context: str = "",
        grounding_context: str = "",
        on_content_chunk: Callable[[str], Awaitable[None]] | None = None,
        trace_collector: dict[str, Any] | None = None,
    ) -> str:
        system_prompt = prepend_grounding(self.get_prompt("system", ""))
        user_prompt_template = self.get_prompt("grade_submission", "")
        if not user_prompt_template:
            user_prompt_template = (
                "Question context:\n{question_context}\n\n"
                "Conversation history:\n{history_context}\n\n"
                "Learner submission:\n{user_message}\n"
            )

        user_prompt = user_prompt_template.format(
            question_context=self._render_question_context(question_context),
            history_context=history_context or "(none)",
            user_message=user_message.strip() or "(empty)",
            grounding_context=grounding_context.strip() or "(none)",
        )
        anchor_contract = render_anchor_contract(
            self.language,
            extract_anchor_terms(
                user_message,
                question_context.get("question"),
                *((item or {}).get("question") for item in question_context.get("items") or []),
            ),
        )
        if anchor_contract:
            user_prompt = f"{user_prompt.rstrip()}\n\n{anchor_contract}"

        _chunks: list[str] = []
        async for _c in self.stream_llm(
            user_prompt=user_prompt,
            system_prompt=system_prompt or "",
            stage="submission_grading",
            trace_meta=build_trace_metadata(
                call_id=new_call_id(
                    f"quiz-grading-{question_context.get('question_id', 'question')}"
                ),
                phase="generation",
                label=f"Grade {self._humanize_question_id(question_context.get('question_id', 'question'))}",
                call_kind="llm_generation",
                trace_id=str(question_context.get("question_id", "question")),
                question_id=str(question_context.get("question_id", "")),
            ),
        ):
            _chunks.append(_c)
            if on_content_chunk is not None and _c:
                await on_content_chunk(_c)
        explanation_text = "".join(_chunks)

        # plan §Phase 4 Step 4.2 / Batch D.2 Gap 4 — schema validate +
        # template fallback. ``trace_collector`` is an opt-in dict that the
        # caller (capability) provides; we write ``explanation_section_miss``
        # so the turn_runtime can flush it into single-writer trace metadata.
        # 重要：``process`` 返回 LLM 首轮原文（兼容下游 markdown 直接渲染契约）；
        # self-repair 与 fallback 的修复结果通过 trace_collector 暴露，
        # 由 capability 组装 progressive_disclosure 后再呈现给用户。
        if trace_collector is None:
            return explanation_text

        question_type = str(question_context.get("question_type") or "").strip().lower()
        is_correct = question_context.get("is_correct")
        # 开放世界判分（无题库 grading_result authority）时，fallback 模板必须用诚实措辞，
        # 不得声称服务端 grading_result / grading_key（contracts/capability.md §硬约束 40）。
        grading_result = question_context.get("construction_grading_result")
        authority_present = isinstance(grading_result, dict) and bool(grading_result)
        parsed = parse_explanation_sections(
            explanation_text,
            question_type=question_type,
            is_correct=is_correct if isinstance(is_correct, bool) else None,
        )
        missing = parsed.missing_required()
        section_miss_after_repair: list[str] = list(missing)
        if missing:
            repair_prompt = (
                f"{user_prompt.rstrip()}\n\n"
                f"上次输出缺以下段落：{', '.join(missing)}。请补齐这些缺段；"
                "保持已经写好的段落不变，输出 markdown 含 `### 段标题` heading。"
            )
            _repair_chunks: list[str] = []
            try:
                async for _c in self.stream_llm(
                    user_prompt=repair_prompt,
                    system_prompt=system_prompt or "",
                    stage="submission_grading_repair",
                    trace_meta=build_trace_metadata(
                        call_id=new_call_id(
                            f"quiz-grading-repair-{question_context.get('question_id', 'question')}"
                        ),
                        phase="generation",
                        label=f"Repair grade {self._humanize_question_id(question_context.get('question_id', 'question'))}",
                        call_kind="llm_generation",
                        trace_id=str(question_context.get("question_id", "question")),
                        question_id=str(question_context.get("question_id", "")),
                    ),
                ):
                    _repair_chunks.append(_c)
            except Exception:
                _repair_chunks = []
            repaired_text = "".join(_repair_chunks).strip()
            if repaired_text:
                parsed = parse_explanation_sections(
                    explanation_text + "\n\n" + repaired_text,
                    question_type=question_type,
                    is_correct=is_correct if isinstance(is_correct, bool) else None,
                )
                section_miss_after_repair = parsed.missing_required()

        if section_miss_after_repair:
            # 仍缺：用模板兜底，保证 capability 拿到的 sections 不会有空段；
            # trace 仍记录原始缺段名单，便于 release gate 计算完整率。
            repaired = apply_fallback_templates(
                parsed,
                missing=section_miss_after_repair,
                authority_present=authority_present,
            )
            parsed = repaired

        trace_collector["explanation_section_miss"] = list(section_miss_after_repair)
        trace_collector["explanation_sections"] = dict(parsed.sections)

        return explanation_text

    @staticmethod
    def _humanize_question_id(question_id: Any) -> str:
        raw = str(question_id or "").strip()
        if raw.lower().startswith("q_") and raw[2:].isdigit():
            return f"Question {raw[2:]}"
        return raw or "question"

    @staticmethod
    def _render_question_context(question_context: dict[str, Any]) -> str:
        options = question_context.get("options") or {}
        option_lines: list[str] = []
        if isinstance(options, dict):
            for key, value in options.items():
                if str(value or "").strip():
                    option_lines.append(f"{key}. {value}")

        grading_result = question_context.get("construction_grading_result")
        has_authoritative_grading = isinstance(grading_result, dict) and bool(grading_result)
        correctness = question_context.get("is_correct")
        diagnosis = str(question_context.get("diagnosis", "") or "").strip() or (
            "CORRECT"
            if correctness is True
            else "CONFUSION"
            if correctness is False
            else "INVALID"
        )

        lines = [
            f"Question ID: {question_context.get('question_id') or '(none)'}",
            f"Question type: {question_context.get('question_type') or '(none)'}",
            f"Difficulty: {question_context.get('difficulty') or '(none)'}",
            f"Concentration: {question_context.get('concentration') or '(none)'}",
            f"Diagnosis: {diagnosis}",
            "",
            "Question:",
            str(question_context.get("question", "") or "(none)"),
        ]
        if not has_authoritative_grading and isinstance(correctness, bool):
            lines.insert(5, f"Score: {100 if correctness else 0}")
        if option_lines:
            lines.extend(["", "Options:", *option_lines])
        lines.extend(
            [
                "",
                f"Learner answer: {question_context.get('user_answer') or '(not provided)'}",
                f"Reference answer: {question_context.get('correct_answer') or '(none)'}",
                f"Is correct: {correctness}",
                "",
                "Explanation:",
                str(question_context.get("explanation", "") or "(none)"),
            ]
        )
        items = question_context.get("items") or []
        if isinstance(items, list) and items:
            lines.extend(["", "Question set items:"])
            for index, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    continue
                item_options = item.get("options") or {}
                item_option_lines: list[str] = []
                if isinstance(item_options, dict):
                    for key, value in item_options.items():
                        if str(value or "").strip():
                            item_option_lines.append(f"{key}. {value}")
                lines.extend(
                    [
                        "",
                        f"Item {index} ID: {item.get('question_id') or '(none)'}",
                        f"Item {index} type: {item.get('question_type') or '(none)'}",
                        f"Item {index} prompt:",
                        str(item.get("question", "") or "(none)"),
                    ]
                )
                if item_option_lines:
                    lines.extend(["Options:", *item_option_lines])
                lines.extend(
                    [
                        f"Learner answer: {item.get('user_answer') or '(not provided)'}",
                        f"Reference answer: {item.get('correct_answer') or '(none)'}",
                        f"Is correct: {item.get('is_correct')}",
                        "Explanation:",
                        str(item.get("explanation", "") or "(none)"),
                    ]
                )
        knowledge_context = str(question_context.get("knowledge_context", "") or "").strip()
        if knowledge_context:
            lines.extend(["", "Knowledge context:", knowledge_context])
        item_dicts = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
        missing_answer_authority = not has_authoritative_grading and (
            any(not str(item.get("correct_answer") or "").strip() for item in item_dicts)
            if item_dicts
            else not str(question_context.get("correct_answer") or "").strip()
        )
        if missing_answer_authority:
            lines.extend(
                [
                    "",
                    "Open-world adjudication directive:",
                    "缺少参考答案的条目没有题库标准答案 authority。对这些条目，你必须基于"
                    " grounding 证据 + 专业推理独立裁决哪个选项/答案正确，再据此明确判定学员答案的对错。"
                    "专业推理只用于判断逻辑（哪个对、为什么），不得用于杜撰硬事实——"
                    "判定依据里的每一个具体数值、阈值、比例、规范编号、条文号、法定术语，仍受上文事实溯源约束，"
                    "只能引用 grounding 证据（教材/规范检索）里实际给出的；grounding 证据没有给出的具体硬事实，"
                    "一律不得当作依据写出，改作定性说明或明说该具体数值待教材核实，"
                    "绝不可用专业推理臆造一个具体值充当规范依据。",
                    "禁止以缺少标准答案为由拒绝判分或要求重新生成题目；"
                    "禁止把你的裁决表述为“题库标准答案/真题官方答案”，表述用“依据教材/规范判定”。"
                    "已带参考答案（Reference answer）的条目仍以该参考答案为准。",
                    # Lock answer letters to the learner's shown option surface. The
                    # grounding evidence may carry a question-bank version whose option
                    # ORDER differs (e.g. value 5% is D in the bank but A here); using the
                    # bank letter marks a correct answer wrong. Decide the correct VALUE,
                    # then report the letter from THESE options whose value matches.
                    "选项字母只认上面 Options 里列出的、学员当前看到的选项："
                    "先裁决正确的“值/内容”，再回到这些 Options 找出值正确的那个字母作为正确答案；"
                    "grounding 证据里的任何题库编号/字母只能用于取“值”，绝不可直接当作答案字母输出。"
                    "判定学员对错，也按学员所选字母在这些 Options 中对应的值来比对。",
                ]
            )
        if has_authoritative_grading:
            lines.extend(
                [
                    "",
                    "Authoritative construction grading result:",
                    json.dumps(grading_result, ensure_ascii=False, indent=2, sort_keys=True),
                    "",
                    (
                        "Use this grading result as final authority. Do not recalculate, "
                        "revise, or override score_awarded, max_score, correctness, rubric "
                        "matches, missed options, or error events. Explain them to the learner."
                    ),
                ]
            )
        return "\n".join(lines)
