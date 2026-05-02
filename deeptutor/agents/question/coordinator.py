#!/usr/bin/env python
"""
Question Coordinator

Simplified architecture:
1) Template generation in batches (max 5 per batch)
2) Single-pass question generation per template
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from deeptutor.agents.question.agents.generator import Generator
from deeptutor.agents.question.agents.idea_agent import BATCH_SIZE, IdeaAgent
from deeptutor.agents.question.models import QAPair, QuestionTemplate
from deeptutor.logging import Logger, get_logger
from deeptutor.services.config import PROJECT_ROOT, load_config_with_main
from deeptutor.services.path_service import get_path_service
from deeptutor.services.question_followup import normalize_question_followup_context
from deeptutor.services.search import is_web_search_runtime_available
from deeptutor.tools.rag_tool import rag_search
from deeptutor.tools.question.pdf_parser import parse_pdf_with_mineru
from deeptutor.tools.question.question_extractor import extract_questions_from_paper


class AgentCoordinator:
    """Coordinate topic-driven and paper-driven quiz generation."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        kb_name: str | None = None,
        output_dir: str | None = None,
        language: str = "en",
        tool_flags_override: dict[str, bool] | None = None,
        enable_idea_rag: bool = True,
    ) -> None:
        self.kb_name = kb_name
        self.output_dir = output_dir
        self.language = language
        self._api_key = api_key
        self._base_url = base_url
        self._api_version = api_version
        self._ws_callback: Callable | None = None
        self._trace_callback: Callable | None = None
        self.enable_idea_rag = enable_idea_rag

        self.config = load_config_with_main("main.yaml", PROJECT_ROOT)
        log_dir = self.config.get("paths", {}).get("user_log_dir") or self.config.get(
            "logging", {}
        ).get("log_dir")
        self.logger: Logger = get_logger("QuestionCoordinator", log_dir=log_dir)

        question_cfg = self.config.get("capabilities", {}).get("question", {})
        generation_cfg = question_cfg.get("generation", {})
        default_tool_flags = generation_cfg.get(
            "tools",
            {"web_search": False, "rag": True, "code_execution": True},
        )
        if isinstance(default_tool_flags, dict) and not is_web_search_runtime_available():
            default_tool_flags = {**default_tool_flags, "web_search": False}
        self.tool_flags = (
            tool_flags_override
            if isinstance(tool_flags_override, dict)
            else default_tool_flags
        )
        self._current_batch_dir: Path | None = None

    def set_ws_callback(self, callback: Callable) -> None:
        self._ws_callback = callback

    def set_trace_callback(self, callback: Callable | None) -> None:
        self._trace_callback = callback

    async def _send_ws_update(self, update_type: str, data: dict[str, Any]) -> None:
        if self._ws_callback:
            try:
                await self._ws_callback({"type": update_type, **data})
            except Exception as exc:
                self.logger.debug(f"WS update failed: {exc}")

    def _create_idea_agent(self) -> IdeaAgent:
        agent = IdeaAgent(
            kb_name=self.kb_name,
            enable_rag=self.enable_idea_rag,
            language=self.language,
            api_key=self._api_key,
            base_url=self._base_url,
            api_version=self._api_version,
        )
        agent.set_trace_callback(self._trace_callback)
        return agent

    def _create_generator(self) -> Generator:
        agent = Generator(
            kb_name=self.kb_name,
            language=self.language,
            tool_flags=self.tool_flags,
            api_key=self._api_key,
            base_url=self._base_url,
            api_version=self._api_version,
        )
        agent.set_trace_callback(self._trace_callback)
        return agent

    async def generate_from_topic(
        self,
        user_topic: str,
        preference: str,
        num_questions: int,
        difficulty: str = "",
        question_type: str = "",
        history_context: str = "",
        lightweight_generation: bool = False,
        require_explanation: bool = True,
    ) -> dict[str, Any]:
        self._current_batch_dir = self._create_batch_dir("custom")
        requested = max(1, int(num_questions or 1))
        templates: list[QuestionTemplate] = []
        batch_trace: list[dict[str, Any]] = []
        existing_concentrations: list[str] = []

        normalized_difficulty = difficulty.strip().lower()
        normalized_question_type = question_type.strip().lower()
        target_difficulty = (
            normalized_difficulty
            if normalized_difficulty and normalized_difficulty != "auto"
            else ""
        )
        target_question_type = (
            normalized_question_type
            if normalized_question_type and normalized_question_type != "auto"
            else ""
        )

        batch_number = 0
        if lightweight_generation:
            anchor_payload, retrieval_trace = await self._resolve_lightweight_topic_knowledge_anchor(
                user_topic=user_topic,
            )
            templates = self._build_lightweight_topic_templates(
                user_topic=user_topic,
                requested=requested,
                difficulty=target_difficulty or "easy",
                question_type=target_question_type or "choice",
                anchor_payload=anchor_payload,
            )
            batch_trace.append(
                {
                    "mode": "lightweight_topic_generation",
                    "requested": requested,
                    "generated": len(templates),
                    "knowledge_context": str(anchor_payload.get("knowledge_context") or ""),
                    "retrieval": retrieval_trace,
                }
            )
            await self._send_ws_update(
                "templates_ready",
                {
                    "stage": "ideation",
                    "count": len(templates),
                    "generated_total": len(templates),
                    "requested_total": requested,
                    "lightweight_generation": True,
                    "templates": [t.__dict__ for t in templates],
                },
            )
        else:
            idea_agent = self._create_idea_agent()
            while len(templates) < requested:
                batch_number += 1
                batch_size = min(BATCH_SIZE, requested - len(templates))
                await self._send_ws_update(
                    "progress",
                    {
                        "stage": "ideation",
                        "status": "running",
                        "batch": batch_number,
                        "current": len(templates),
                        "total": requested,
                        "batch_size": batch_size,
                    },
                )

                idea_result = await idea_agent.process(
                    user_topic=user_topic,
                    preference=preference,
                    num_ideas=batch_size,
                    target_difficulty=target_difficulty,
                    target_question_type=target_question_type,
                    existing_concentrations=existing_concentrations,
                    batch_number=batch_number,
                )
                batch_templates = idea_result.get("templates", [])
                if not isinstance(batch_templates, list):
                    batch_templates = []

                for template in batch_templates:
                    if not isinstance(template, QuestionTemplate):
                        continue
                    template.question_id = f"q_{len(templates) + 1}"
                    templates.append(template)
                    existing_concentrations.append(template.concentration)

                batch_trace.append(
                    {
                        "batch": batch_number,
                        "requested": batch_size,
                        "generated": len(batch_templates),
                        "knowledge_context": idea_result.get("knowledge_context", ""),
                    }
                )
                await self._send_ws_update(
                    "templates_ready",
                    {
                        "stage": "ideation",
                        "batch": batch_number,
                        "count": len(batch_templates),
                        "generated_total": len(templates),
                        "requested_total": requested,
                        "templates": [t.__dict__ for t in batch_templates],
                    },
                )

                if not batch_templates:
                    self.logger.warning(
                        "Template generation returned an empty batch; stopping early."
                    )
                    break

        await self._send_ws_update(
            "progress",
            {
                "stage": "ideation",
                "status": "complete",
                "current": len(templates),
                "total": requested,
                "batches": batch_number,
            },
        )

        qa_pairs = await self._generation_loop(
            templates=templates[:requested],
            user_topic=user_topic,
            preference=preference,
            history_context=history_context,
            require_explanation=require_explanation,
            lightweight_generation=lightweight_generation,
        )
        return self._build_summary(
            source="topic",
            requested=requested,
            templates=templates[:requested],
            qa_pairs=qa_pairs,
            trace={
                "batches": batch_trace,
                "lightweight_generation": lightweight_generation,
            },
        )

    async def generate_from_followup_context(
        self,
        user_topic: str,
        preference: str,
        num_questions: int,
        followup_question_context: dict[str, Any] | None,
        difficulty: str = "",
        question_type: str = "",
        history_context: str = "",
        require_explanation: bool = True,
        lightweight_generation: bool = False,
    ) -> dict[str, Any]:
        self._current_batch_dir = self._create_batch_dir("custom")
        requested = max(1, int(num_questions or 1))
        templates = self._build_templates_from_followup_context(
            followup_question_context=followup_question_context,
            requested=requested,
            difficulty=difficulty,
            question_type=question_type,
        )

        await self._send_ws_update(
            "progress",
            {
                "stage": "ideation",
                "status": "complete",
                "current": len(templates),
                "total": requested,
                "anchor_generation": True,
            },
        )
        await self._send_ws_update(
            "templates_ready",
            {
                "stage": "ideation",
                "count": len(templates),
                "generated_total": len(templates),
                "requested_total": requested,
                "anchor_generation": True,
                "templates": [t.__dict__ for t in templates],
            },
        )

        qa_pairs = await self._generation_loop(
            templates=templates,
            user_topic=user_topic,
            preference=preference,
            history_context=history_context,
            require_explanation=require_explanation,
            lightweight_generation=lightweight_generation,
        )
        return self._build_summary(
            source="topic",
            requested=requested,
            templates=templates,
            qa_pairs=qa_pairs,
            trace={
                "anchor_generation": True,
                "lightweight_generation": lightweight_generation,
                "anchor_item_count": len(
                    (normalize_question_followup_context(followup_question_context) or {}).get("items")
                    or ([1] if normalize_question_followup_context(followup_question_context) else [])
                ),
            },
        )

    async def generate_from_exam(
        self,
        exam_paper_path: str,
        max_questions: int,
        paper_mode: str = "upload",
        history_context: str = "",
    ) -> dict[str, Any]:
        if self._current_batch_dir is None:
            self._current_batch_dir = self._create_batch_dir("mimic")
        templates, parse_trace = await self._parse_exam_to_templates(
            exam_paper_path=exam_paper_path,
            max_questions=max_questions,
            paper_mode=paper_mode,
        )
        for idx, template in enumerate(templates, 1):
            template.question_id = f"q_{idx}"

        await self._send_ws_update(
            "templates_ready",
            {
                "stage": "ideation",
                "count": len(templates),
                "generated_total": len(templates),
                "requested_total": max_questions,
                "templates": [t.__dict__ for t in templates],
            },
        )

        qa_pairs = await self._generation_loop(
            templates=templates,
            user_topic="",
            preference="",
            history_context=history_context,
        )
        return self._build_summary(
            source="exam",
            requested=max_questions,
            templates=templates,
            qa_pairs=qa_pairs,
            trace=parse_trace,
        )

    async def _generation_loop(
        self,
        templates: list[QuestionTemplate],
        user_topic: str,
        preference: str,
        history_context: str = "",
        require_explanation: bool = True,
        lightweight_generation: bool = False,
    ) -> list[dict[str, Any]]:
        generator = self._create_generator()
        results: list[dict[str, Any]] = []
        total = len(templates)
        generated_questions: list[str] = []

        for idx, template in enumerate(templates, 1):
            await self._send_ws_update(
                "question_update",
                {
                    "question_id": template.question_id,
                    "status": "generating",
                    "current": idx,
                    "total": total,
                },
            )

            success = True
            try:
                qa_pair = await generator.process(
                    template=template,
                    user_topic=user_topic,
                    preference=preference,
                    history_context=history_context,
                    previous_questions=generated_questions or None,
                    require_explanation=require_explanation,
                    lightweight_generation=lightweight_generation,
                )
            except Exception as exc:
                success = False
                self.logger.warning(f"Generation failed for {template.question_id}: {exc}")
                qa_pair = QAPair(
                    question_id=template.question_id,
                    question=f"[Generation failed] {template.concentration}",
                    correct_answer="N/A",
                    explanation=str(exc),
                    question_type=template.question_type,
                    concentration=template.concentration,
                    difficulty=template.difficulty,
                    metadata={"error": str(exc)},
                )

            result = {
                "template": template.__dict__,
                "qa_pair": qa_pair.__dict__,
                "success": success,
            }
            results.append(result)

            # Track successfully generated question text for diversity enforcement
            if success and qa_pair.question:
                generated_questions.append(qa_pair.question)

            await self._send_ws_update(
                "result",
                {
                    "question_id": template.question_id,
                    "index": idx - 1,
                    "question": qa_pair.__dict__,
                    "success": success,
                },
            )
            await self._send_ws_update(
                "progress",
                {
                    "stage": "generation",
                    "status": "running",
                    "current": idx,
                    "total": total,
                    "question_id": template.question_id,
                },
            )

        await self._send_ws_update(
            "progress",
            {"stage": "complete", "completed": len(results), "total": total},
        )
        return results

    @staticmethod
    def _build_lightweight_topic_templates(
        *,
        user_topic: str,
        requested: int,
        difficulty: str,
        question_type: str,
        anchor_payload: dict[str, Any] | None = None,
    ) -> list[QuestionTemplate]:
        payload = dict(anchor_payload or {})
        concentration = (
            str(payload.get("concentration") or "").strip()
            or str(user_topic or "").strip()
            or "当前学习主题"
        )
        resolved_question_type = str(question_type or "").strip().lower() or "choice"
        resolved_difficulty = str(difficulty or "").strip().lower() or "easy"
        knowledge_anchor = str(payload.get("knowledge_context") or "").strip() or f"当前学习锚点：{concentration}"
        reference_question = str(payload.get("reference_question") or "").strip() or None
        reference_answer = str(payload.get("reference_answer") or "").strip() or None
        anchor_metadata = {
            key: value
            for key, value in payload.items()
            if key
            not in {
                "knowledge_context",
                "concentration",
                "reference_question",
                "reference_answer",
            }
            and value not in (None, "", [], {})
        }
        return [
            QuestionTemplate(
                question_id=f"q_{index}",
                concentration=concentration,
                question_type=resolved_question_type,
                difficulty=resolved_difficulty,
                source="lightweight_topic",
                reference_question=reference_question,
                reference_answer=reference_answer,
                metadata={
                    "knowledge_context": knowledge_anchor,
                    "lightweight_generation": True,
                    **anchor_metadata,
                },
            )
            for index in range(1, requested + 1)
        ]

    async def _resolve_lightweight_topic_knowledge_anchor(
        self,
        *,
        user_topic: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        anchor_label = self._derive_lightweight_anchor_label(user_topic=user_topic)
        fallback = {
            "knowledge_context": f"当前学习锚点：{anchor_label}",
            "concentration": anchor_label,
        }
        trace: dict[str, Any] = {"used_rag": False}
        if not self.enable_idea_rag or not self.kb_name:
            return fallback, trace

        try:
            result = await rag_search(
                query=user_topic,
                kb_name=self.kb_name,
                only_need_context=True,
            )
        except Exception as exc:
            self.logger.warning(
                "Lightweight topic RAG anchor failed for '%s': %s",
                user_topic,
                exc,
            )
            trace["error"] = str(exc)
            return fallback, trace

        anchor = self._build_lightweight_rag_anchor_payload(
            user_topic=user_topic,
            result=result,
        )
        trace.update(
            {
                "used_rag": anchor != fallback,
                "provider": str((result or {}).get("provider") or "").strip(),
                "kb_name": str((result or {}).get("kb_name") or self.kb_name or "").strip(),
                "exact_question": bool(
                    isinstance((result or {}).get("exact_question"), dict)
                    and (result or {}).get("exact_question")
                ),
                "anchor_source": str(anchor.get("anchor_source") or "").strip(),
            }
        )
        return anchor, trace

    @staticmethod
    def _build_lightweight_rag_anchor_payload(
        *,
        user_topic: str,
        result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        anchor_label = AgentCoordinator._derive_lightweight_anchor_label(user_topic=user_topic)
        base = {
            "knowledge_context": f"当前学习锚点：{anchor_label}",
            "concentration": anchor_label,
        }
        if not isinstance(result, dict):
            return base

        exact_question = (
            result.get("exact_question")
            if isinstance(result.get("exact_question"), dict)
            else {}
        )
        stem = str(exact_question.get("stem") or "").strip()
        analysis = str(exact_question.get("analysis") or "").strip()
        correct_answer = str(exact_question.get("correct_answer") or "").strip()
        options = exact_question.get("options")

        parts: list[str] = [base["knowledge_context"]]
        if stem:
            parts.append(f"题库参考题目：{stem}")
        option_lines = AgentCoordinator._format_reference_options(options)
        if option_lines:
            parts.append("题库选项风格参考：\n" + "\n".join(option_lines[:4]))
        if correct_answer:
            parts.append(f"题库参考答案（仅内部生成锚点）：{correct_answer}")
        if analysis:
            clipped_analysis = analysis[:280] + ("..." if len(analysis) > 280 else "")
            parts.append(f"题库解析要点：{clipped_analysis}")
        if len(parts) > 1:
            return {
                "knowledge_context": "\n".join(parts),
                "concentration": anchor_label or stem or "当前学习主题",
                "reference_question": stem,
                "reference_answer": correct_answer,
                "anchor_source": str(exact_question.get("source_group") or "").strip() or "exact_question",
                "anchor_confidence": exact_question.get("confidence"),
            }

        answer = str(result.get("answer") or "").strip()
        if not answer:
            return base

        parsed_bundle = AgentCoordinator._extract_structured_anchor_from_answer(answer)
        if parsed_bundle:
            bundle_parts: list[str] = [base["knowledge_context"]]
            bundle_parts.append(f"题库参考题目：{parsed_bundle['reference_question']}")
            parsed_option_lines = AgentCoordinator._format_reference_options(
                parsed_bundle.get("options")
            )
            if parsed_option_lines:
                bundle_parts.append("题库选项风格参考：\n" + "\n".join(parsed_option_lines[:4]))
            if parsed_bundle.get("reference_answer"):
                bundle_parts.append(
                    f"题库参考答案（仅内部生成锚点）：{parsed_bundle['reference_answer']}"
                )
            if parsed_bundle.get("analysis"):
                clipped_analysis = parsed_bundle["analysis"][:280] + (
                    "..." if len(parsed_bundle["analysis"]) > 280 else ""
                )
                bundle_parts.append(f"题库解析要点：{clipped_analysis}")
            return {
                "knowledge_context": "\n".join(bundle_parts),
                "concentration": anchor_label or parsed_bundle["reference_question"][:32] or "当前学习主题",
                "reference_question": parsed_bundle["reference_question"],
                "reference_answer": parsed_bundle.get("reference_answer"),
                "anchor_source": "rag_answer_bundle",
            }

        clipped_answer = answer[:280] + ("..." if len(answer) > 280 else "")
        return {
            "knowledge_context": f"{base['knowledge_context']}\n题库参考资料：{clipped_answer}",
            "concentration": anchor_label,
            "anchor_source": "rag_answer_text",
        }

    @staticmethod
    def _derive_lightweight_anchor_label(
        *,
        user_topic: str,
    ) -> str:
        text = re.sub(r"\s+", " ", str(user_topic or "")).strip()
        if not text:
            return "当前学习主题"
        first_clause = re.split(r"[，,。!?！？]", text, maxsplit=1)[0].strip() or text
        patterns = (
            r"^(我现在学到|我学到|现在学到|学到)",
            r"^(我现在在学|我在学|现在在学|最近在学|正在学)",
            r"(先|请|麻烦你|麻烦)?给我",
            r"来[一1]?道",
            r"出[一1]?道",
            r"建筑实务",
            r"(单选题|多选题|选择题|判断题|简答题|案例题)",
            r"(不要给答案|别给答案|先不要答案|只出题|不要解析|别解析)",
            r"(很短的小题|很短的小测|小题|小测)",
            r"(考我|刷题)",
        )
        cleaned = first_clause
        for pattern in patterns:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[，。！？、,.!?\-:：\s]+", " ", cleaned).strip()
        cleaned = re.sub(r"(了|呢|呀)$", "", cleaned).strip()
        if cleaned:
            return cleaned[:32]
        return text[:32] or "当前学习主题"

    @staticmethod
    def _extract_structured_anchor_from_answer(answer: str) -> dict[str, Any] | None:
        text = str(answer or "").strip()
        if "【题目】" not in text:
            return None
        match = re.search(
            r"【题目】(?P<stem>.*?)(?:\n【选项】(?P<options>.*?))?(?:\n【答案】(?P<answer>.*?))?(?:\n【解析】(?P<analysis>.*?))?(?=\n【题目】|$)",
            text,
            flags=re.DOTALL,
        )
        if not match:
            return None
        stem = str(match.group("stem") or "").strip()
        if not stem:
            return None
        reference_answer = re.sub(r"\s+", " ", str(match.group("answer") or "")).strip() or None
        analysis = re.sub(r"\s+", " ", str(match.group("analysis") or "")).strip()
        return {
            "reference_question": stem,
            "reference_answer": reference_answer,
            "analysis": analysis,
            "options": AgentCoordinator._parse_reference_options(match.group("options")),
        }

    @staticmethod
    def _parse_reference_options(raw_options: Any) -> dict[str, str] | None:
        raw_text = str(raw_options or "").strip()
        if not raw_text:
            return None
        parsed: Any = None
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(raw_text)
                break
            except Exception:
                continue
        if isinstance(parsed, dict):
            options = {
                str(key or "").strip().upper()[:1]: str(value or "").strip()
                for key, value in parsed.items()
                if str(key or "").strip() and str(value or "").strip()
            }
            return options or None
        if isinstance(parsed, list):
            options: dict[str, str] = {}
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("key") or item.get("label") or "").strip().upper()[:1]
                value = str(item.get("value") or item.get("text") or "").strip()
                if key and value:
                    options[key] = value
            return options or None

        matches = re.findall(r"([A-D])[\.\):、]\s*([^\n]+)", raw_text, flags=re.IGNORECASE)
        if not matches:
            return None
        return {
            str(key).upper(): str(value).strip()
            for key, value in matches
            if str(value).strip()
        } or None

    @staticmethod
    def _format_reference_options(options: Any) -> list[str]:
        if not isinstance(options, dict) or not options:
            return []
        return [
            f"{str(key or '').strip().upper()[:1]}. {str(value or '').strip()}"
            for key, value in options.items()
            if str(key or '').strip() and str(value or '').strip()
        ]

    def _build_templates_from_followup_context(
        self,
        *,
        followup_question_context: dict[str, Any] | None,
        requested: int,
        difficulty: str = "",
        question_type: str = "",
    ) -> list[QuestionTemplate]:
        normalized = normalize_question_followup_context(followup_question_context) or {}
        raw_items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
        anchor_items = [
            item
            for item in raw_items
            if normalize_question_followup_context(item)
        ] or ([normalized] if normalized else [])
        if not anchor_items:
            anchor_items = [{"question": "当前学习锚点", "question_type": "choice"}]

        normalized_difficulty = str(difficulty or "").strip().lower()
        normalized_question_type = str(question_type or "").strip().lower()
        templates: list[QuestionTemplate] = []

        for index in range(requested):
            item = normalize_question_followup_context(anchor_items[index % len(anchor_items)]) or {}
            concentration = (
                str(item.get("concentration") or "").strip()
                or str(item.get("question") or "").strip()[:120]
                or "当前学习锚点"
            )
            reference_question = str(item.get("question") or "").strip()
            knowledge_context = self._compose_followup_anchor_context(item)
            templates.append(
                QuestionTemplate(
                    question_id=f"q_{index + 1}",
                    concentration=concentration,
                    question_type=normalized_question_type or str(item.get("question_type") or "choice").strip().lower() or "choice",
                    difficulty=normalized_difficulty or str(item.get("difficulty") or "").strip().lower() or "medium",
                    source="followup_anchor",
                    reference_question=reference_question or None,
                    reference_answer=str(item.get("correct_answer") or "").strip() or None,
                    metadata={
                        "knowledge_context": knowledge_context,
                        "anchor_source": "followup_question_context",
                        "anchor_question_id": str(item.get("question_id") or "").strip(),
                    },
                )
            )
        return templates

    @staticmethod
    def _compose_followup_anchor_context(item: dict[str, Any]) -> str:
        sections: list[str] = []
        concentration = str(item.get("concentration") or "").strip()
        question = str(item.get("question") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        knowledge_context = str(item.get("knowledge_context") or "").strip()
        if concentration:
            sections.append(f"当前知识点：{concentration}")
        if question:
            sections.append(f"参考题目：{question}")
        if explanation:
            sections.append(f"参考解析：{explanation}")
        if knowledge_context and knowledge_context not in explanation:
            sections.append(f"补充知识：{knowledge_context}")
        return "\n".join(sections)

    async def _parse_exam_to_templates(
        self,
        exam_paper_path: str,
        max_questions: int,
        paper_mode: str,
    ) -> tuple[list[QuestionTemplate], dict[str, Any]]:
        await self._send_ws_update(
            "progress", {"stage": "parsing", "status": "running"}
        )

        paper_path = Path(exam_paper_path)
        output_base = (
            self._current_batch_dir
            or (Path(self.output_dir) if self.output_dir else None)
            or get_path_service().get_question_dir()
        )
        output_base.mkdir(parents=True, exist_ok=True)

        if paper_mode == "parsed":
            working_dir = paper_path
        else:
            parse_success = parse_pdf_with_mineru(str(paper_path), str(output_base))
            if not parse_success:
                raise RuntimeError("Failed to parse exam paper with MinerU")
            subdirs = sorted(
                [d for d in output_base.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            if not subdirs:
                raise RuntimeError("No parsed exam directory found after MinerU parsing")
            working_dir = subdirs[0]

        await self._send_ws_update(
            "progress",
            {"stage": "extracting", "status": "running", "paper_dir": str(working_dir)},
        )

        json_files = list(working_dir.glob("*_questions.json"))
        if not json_files:
            extract_success = extract_questions_from_paper(
                str(working_dir), output_dir=None
            )
            if not extract_success:
                raise RuntimeError("Failed to extract questions from parsed exam")
            json_files = list(working_dir.glob("*_questions.json"))
        if not json_files:
            raise RuntimeError("Question extraction output not found")

        with open(json_files[0], encoding="utf-8") as f:
            payload = json.load(f)
        questions = payload.get("questions", [])
        if max_questions > 0:
            questions = questions[:max_questions]

        templates: list[QuestionTemplate] = []
        for i, item in enumerate(questions, 1):
            if not isinstance(item, dict):
                continue
            q_text = str(item.get("question_text", "")).strip()
            if not q_text:
                continue
            templates.append(
                QuestionTemplate(
                    question_id=f"q_{i}",
                    concentration=q_text[:240],
                    question_type=str(item.get("question_type", "written")).lower(),
                    difficulty="medium",
                    source="mimic",
                    reference_question=q_text,
                    reference_answer=str(item.get("answer", "")).strip() or None,
                    metadata={
                        "question_number": item.get("question_number", str(i)),
                        "images": item.get("images", []),
                    },
                )
            )

        await self._send_ws_update(
            "progress",
            {"stage": "extracting", "status": "complete", "templates": len(templates)},
        )
        return templates, {
            "paper_dir": str(working_dir),
            "question_file": str(json_files[0]),
            "template_count": len(templates),
        }

    def _build_summary(
        self,
        source: str,
        requested: int,
        templates: list[QuestionTemplate],
        qa_pairs: list[dict[str, Any]],
        trace: dict[str, Any],
    ) -> dict[str, Any]:
        completed = sum(1 for item in qa_pairs if item.get("success"))
        failed = len(qa_pairs) - completed
        summary = {
            "success": completed > 0 and failed == 0,
            "source": source,
            "requested": requested,
            "template_count": len(templates),
            "completed": completed,
            "failed": failed,
            "templates": [t.__dict__ for t in templates],
            "results": qa_pairs,
            "trace": trace,
            "batch_dir": str(self._current_batch_dir) if self._current_batch_dir else None,
        }
        self._persist_summary(summary)
        return summary

    def _create_batch_dir(self, prefix: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = (
            Path(self.output_dir)
            if self.output_dir
            else get_path_service().get_question_dir()
        )
        batch_dir = base / f"{prefix}_{timestamp}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        return batch_dir

    def _persist_summary(self, summary: dict[str, Any]) -> None:
        if self._current_batch_dir is None:
            return
        summary_file = self._current_batch_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
