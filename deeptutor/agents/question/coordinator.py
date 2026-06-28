#!/usr/bin/env python
"""
Question Coordinator

Simplified architecture:
1) Template generation in batches (max 5 per batch)
2) Single-pass question generation per template
"""

from __future__ import annotations

import ast
import asyncio
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
from deeptutor.services.rag.exact_authority import build_mcq_review_notes_from_exact_question
from deeptutor.services.search import is_web_search_runtime_available
from deeptutor.tools.question.pdf_parser import parse_pdf_with_mineru
from deeptutor.tools.question.question_extractor import extract_questions_from_paper
from deeptutor.tools.rag_tool import rag_search
from deeptutor.tutorbot.teaching_modes import (
    practice_generation_request_needs_context_anchor,
    practice_generation_topic_block_decision,
    practice_generation_topic_domain_status,
)

_CONSTRUCTION_EXAM_KB_ALIASES = {
    "construction-exam",
    "construction_exam",
    "construction-exam-coach",
    "construction-exam-tutor",
    "construction_exam_tutor",
}


def _uses_construction_exam_scope(kb_name: str | None) -> bool:
    normalized = str(kb_name or "").strip().lower()
    return normalized in _CONSTRUCTION_EXAM_KB_ALIASES


def _qa_pair_template_dict(qa_pair: QAPair, templates: list[QuestionTemplate]) -> dict[str, Any]:
    """Look up the original template dict for a generated QA pair.

    Falls back to a stub when the template is missing (e.g. bank short-circuit).
    """
    for template in templates:
        if template.question_id == qa_pair.question_id:
            return template.__dict__
    return {
        "question_id": qa_pair.question_id,
        "concentration": qa_pair.concentration,
        "question_type": qa_pair.question_type,
        "difficulty": qa_pair.difficulty,
        "source": "synthetic",
        "metadata": dict(qa_pair.metadata or {}),
    }


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
        reveal_answers: bool = False,
        allow_lightweight_fallback: bool = True,
        allow_similar_source_variant: bool = False,
        avoid_current_question: bool = False,
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

        # plan §Phase 2 Batch B — lightweight 路径短路 idea_agent，
        # 命中 questions_bank 时跳过 LLM。trace 计数器累加到 batch_trace[].counters。
        bank_qa_pairs: list[QAPair] = []
        lightweight_trace_counters: dict[str, Any] = {
            "llm_calls": 0,
            "retriever_calls": 0,
            "bank_hits": 0,
            "deduped_bank_hits": 0,
            "lightweight_batch_fallback": "none",
            "generated_explanation": False,
        }
        batch_number = 0
        if _uses_construction_exam_scope(self.kb_name):
            topic_domain_status = practice_generation_topic_domain_status(user_topic)
            block_decision = practice_generation_topic_block_decision(topic_domain_status)
            if block_decision != "allow":
                blocked_reason = (
                    "blocked_out_of_scope_topic"
                    if block_decision == "block_out_of_scope"
                    else "blocked_unresolved_anchor"
                )
                if lightweight_generation:
                    lightweight_trace_counters["lightweight_batch_fallback"] = blocked_reason
                batch_trace.append(
                    {
                        "mode": (
                            "lightweight_topic_generation"
                            if lightweight_generation
                            else "topic_generation"
                        ),
                        "requested": requested,
                        "generated": 0,
                        "knowledge_context": "",
                        "retrieval": {"used_rag": False},
                        "bank_short_circuit": False,
                        "anchor_resolution_status": blocked_reason,
                        "topic_domain_status": topic_domain_status,
                    }
                )
                return self._build_summary(
                    source="topic",
                    requested=requested,
                    templates=[],
                    qa_pairs=[],
                    trace={
                        "batches": batch_trace,
                        "lightweight_generation": lightweight_generation,
                        "lightweight_counters": dict(lightweight_trace_counters)
                        if lightweight_generation
                        else None,
                        "topic_domain_status": topic_domain_status,
                    },
                )
        if lightweight_generation:
            if avoid_current_question:
                anchor_payload = self._current_question_exclusion_anchor_payload(
                    user_topic=user_topic,
                )
                retrieval_trace = {
                    "used_rag": False,
                    "skipped": "current_question_exclusion",
                }
            else:
                anchor_payload, retrieval_trace = await self._resolve_lightweight_topic_knowledge_anchor(
                    user_topic=user_topic,
                )
                # retriever_calls 计数：调过 rag_search 即算一次（成功/失败都计入）。
                lightweight_trace_counters["retriever_calls"] = 1
            if self._should_block_unresolved_lightweight_anchor(
                user_topic=user_topic,
                anchor_payload=anchor_payload,
            ):
                lightweight_trace_counters["lightweight_batch_fallback"] = "blocked_unresolved_anchor"
                batch_trace.append(
                    {
                        "mode": "lightweight_topic_generation",
                        "requested": requested,
                        "generated": 0,
                        "knowledge_context": str(anchor_payload.get("knowledge_context") or ""),
                        "retrieval": retrieval_trace,
                        "bank_short_circuit": False,
                        "anchor_resolution_status": "blocked_unresolved_anchor",
                    }
                )
                return self._build_summary(
                    source="topic",
                    requested=requested,
                    templates=[],
                    qa_pairs=[],
                    trace={
                        "batches": batch_trace,
                        "lightweight_generation": lightweight_generation,
                        "lightweight_counters": dict(lightweight_trace_counters),
                    },
                )
            templates = self._build_lightweight_topic_templates(
                user_topic=user_topic,
                requested=requested,
                difficulty=target_difficulty or "easy",
                question_type=target_question_type or "choice",
                anchor_payload=anchor_payload,
            )
            # plan §Phase 2 Step 2.4 (B1) — questions_bank 命中且字段完整时
            # 跳过 LLM，直接组装 QAPair；anchor 不足时进入下面的并行 batch path。
            bank_qa_pairs, bank_skip_reason = self._build_bank_hit_qa_pairs(
                anchor_payload=anchor_payload,
                templates=templates,
                question_type=target_question_type or "choice",
                history_context=history_context,
                reveal_answers=reveal_answers,
                require_explanation=require_explanation,
            )
            if bank_skip_reason == "duplicate_recent_question":
                lightweight_trace_counters["deduped_bank_hits"] += 1
            lightweight_trace_counters["bank_hits"] = len(bank_qa_pairs)
            batch_trace.append(
                {
                    "mode": "lightweight_topic_generation",
                    "requested": requested,
                    "generated": len(templates),
                    "knowledge_context": str(anchor_payload.get("knowledge_context") or ""),
                    "retrieval": retrieval_trace,
                    "bank_short_circuit": bool(bank_qa_pairs),
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

        # plan §Phase 2 Step 2.2 (A1) — lightweight 路径优先 questions_bank 短路，
        # 否则并行调用 generator（asyncio.gather）一次性出 N 题，物理时间 ≈ max(单题)，
        # llm_calls = max(0, requested - bank_hits)。
        if lightweight_generation and bank_qa_pairs:
            # bank 命中数 < requested 时，剩余进入 batch generator。
            covered_ids = {pair.question_id for pair in bank_qa_pairs}
            remaining_templates = [t for t in templates[:requested] if t.question_id not in covered_ids]
            qa_pairs_objects = list(bank_qa_pairs)
            if remaining_templates and allow_lightweight_fallback:
                fallback_pairs = await self._lightweight_batch_generate(
                    templates=remaining_templates,
                    user_topic=user_topic,
                    preference=preference,
                    history_context=history_context,
                    counters=lightweight_trace_counters,
                )
                qa_pairs_objects.extend(fallback_pairs)
            qa_pairs = [
                {"template": _qa_pair_template_dict(pair, templates), "qa_pair": pair.__dict__, "success": True}
                for pair in qa_pairs_objects
            ]
        elif lightweight_generation:
            use_similar_source_variant = (
                allow_similar_source_variant
                and self._has_similar_source_variant_anchor(anchor_payload)
            )
            if allow_lightweight_fallback or use_similar_source_variant:
                qa_pair_objects = await self._lightweight_batch_generate(
                    templates=templates[:requested],
                    user_topic=user_topic,
                    preference=preference,
                    history_context=history_context,
                    counters=lightweight_trace_counters,
                )
                if use_similar_source_variant:
                    self._mark_similar_source_variant(
                        qa_pairs=qa_pair_objects,
                        anchor_payload=anchor_payload,
                        counters=lightweight_trace_counters,
                    )
                qa_pairs = [
                    {"template": _qa_pair_template_dict(pair, templates), "qa_pair": pair.__dict__, "success": True}
                    for pair in qa_pair_objects
                ]
            else:
                lightweight_trace_counters["lightweight_batch_fallback"] = "disabled"
                qa_pairs = []
        else:
            qa_pairs = await self._generation_loop(
                templates=templates[:requested],
                user_topic=user_topic,
                preference=preference,
                history_context=history_context,
                require_explanation=require_explanation,
                lightweight_generation=lightweight_generation,
            )
        # 出口科目门（owner=只建筑）：construction-exam 生成题全部跑偏到非建筑
        # （汉字/外国常识/纯他科）时诚实拒答 subject_unavailable。非 construction KB
        # 不使用这道出口门，避免把其它知识库的合法题误拦。
        if _uses_construction_exam_scope(self.kb_name) and not self._generated_questions_in_construction_scope(
            templates[:requested],
            qa_pairs,
        ):
            if lightweight_generation:
                lightweight_trace_counters["lightweight_batch_fallback"] = "blocked_out_of_scope_topic"
            return self._build_summary(
                source="topic",
                requested=requested,
                templates=[],
                qa_pairs=[],
                trace={
                    "batches": batch_trace,
                    "lightweight_generation": lightweight_generation,
                    "lightweight_counters": dict(lightweight_trace_counters)
                    if lightweight_generation
                    else None,
                    "subject_scope_blocked": "subject_unavailable",
                    "topic_domain_status": "out_of_scope_topic",
                },
            )
        return self._build_summary(
            source="topic",
            requested=requested,
            templates=templates[:requested],
            qa_pairs=qa_pairs,
            trace={
                "batches": batch_trace,
                "lightweight_generation": lightweight_generation,
                "lightweight_counters": dict(lightweight_trace_counters)
                if lightweight_generation
                else None,
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

    def _build_bank_hit_qa_pairs(
        self,
        *,
        anchor_payload: dict[str, Any] | None,
        templates: list[QuestionTemplate],
        question_type: str,
        history_context: str = "",
        reveal_answers: bool = False,
        require_explanation: bool = False,
    ) -> tuple[list[QAPair], str]:
        """plan §Phase 2 Step 2.4 (B1) — questions_bank 命中且字段完整时，
        直接组装 QAPair（含 hidden grading_key），跳过 LLM。

        仅当 anchor 含 reference_question + reference_answer + 完整选项时短路。
        当前命中只能覆盖 1 道题（anchor 只暴露 1 个 exact_question），所以仅
        给 templates[0] 提供 short-circuit；其余进 batch generator。
        """
        payload = dict(anchor_payload or {})
        anchor_source = str(payload.get("anchor_source") or "").strip().lower()
        if anchor_source not in {
            "exact_question",
            "question_exact_text",
            "question_evidence_bundle",
            "rag_answer_bundle",
        }:
            return [], ""
        reference_question = str(payload.get("reference_question") or "").strip()
        reference_answer = str(payload.get("reference_answer") or "").strip()
        if not reference_question or not reference_answer:
            return [], ""
        if not templates:
            return [], ""
        # 从 evidence_refs 反查完整 options（如果上游已经压扁，就跳过）。
        options = self._extract_bank_options_from_payload(payload)
        if not options or len(options) < 2:
            return [], ""
        template = templates[0]
        if not self._bank_hit_matches_question_contract(
            question_type=question_type or template.question_type,
            options=options,
            reference_answer=reference_answer,
        ):
            return [], "contract_mismatch"
        analysis = str(payload.get("analysis") or "").strip()
        if require_explanation and not analysis:
            return [], "missing_explanation"
        if self._recent_history_contains_question(
            history_context=history_context,
            question=reference_question,
        ):
            return [], "duplicate_recent_question"
        review_notes = build_mcq_review_notes_from_exact_question(
            {
                "answer_kind": "mcq",
                "stem": reference_question,
                "options": options,
                "correct_answer": reference_answer,
                "analysis": analysis,
            }
        )
        grading_key = {
            "correct_answer": reference_answer,
            "scoring_points": review_notes.get("scoring_points") or [],
            "common_traps": review_notes.get("pitfalls") or [],
            "minimal_rationale": analysis or "题库精确命中，参考答案与解析来自 questions_bank。",
            "source": "questions_bank",
        }
        knowledge_context = str(payload.get("knowledge_context") or "").strip()
        evidence_refs = list(payload.get("evidence_refs") or [])
        return [
            QAPair(
                question_id=template.question_id,
                question=reference_question,
                correct_answer=reference_answer if reveal_answers else "",
                explanation=analysis,
                question_type=question_type or "choice",
                options=dict(options),
                concentration=template.concentration,
                difficulty=template.difficulty,
                validation={"schema_ok": True, "source": "questions_bank_short_circuit"},
                metadata={
                    "source": "questions_bank",
                    "source_group": str(payload.get("source_group") or anchor_source).strip(),
                    "source_id": str(payload.get("source_id") or "").strip(),
                    "reference_question": reference_question,
                    "knowledge_context": knowledge_context,
                    "lightweight_generation": True,
                    "evidence_refs": evidence_refs,
                    **review_notes,
                },
                grading_key=grading_key,
            )
        ], ""

    @staticmethod
    def _bank_hit_matches_question_contract(
        *,
        question_type: str,
        options: dict[str, str],
        reference_answer: str,
    ) -> bool:
        normalized_type = str(question_type or "").strip().lower()
        option_keys = {str(key).strip().upper() for key in options if str(key).strip()}
        answer_letters = re.findall(r"[A-E]", str(reference_answer or "").upper())
        if normalized_type in {"choice", "single_choice", "mcq"}:
            return option_keys == {"A", "B", "C", "D"} and len(answer_letters) == 1
        if normalized_type in {"multiple_choice", "multi_choice"}:
            return option_keys in (
                {"A", "B", "C", "D"},
                {"A", "B", "C", "D", "E"},
            ) and len(answer_letters) > 1
        return False

    @staticmethod
    def _recent_history_contains_question(*, history_context: str, question: str) -> bool:
        needle = AgentCoordinator._normalize_question_text_for_dedupe(question)
        if len(needle) < 8:
            return False
        haystack = AgentCoordinator._normalize_question_text_for_dedupe(history_context)
        return bool(haystack and needle in haystack)

    @staticmethod
    def _normalize_question_text_for_dedupe(value: str) -> str:
        text = re.sub(r"\s+", "", str(value or ""))
        return re.sub(r"[，。！？、,.!?；;：:（）()【】\[\]\"'“”‘’`*_\-]+", "", text)

    @staticmethod
    def _has_similar_source_variant_anchor(anchor_payload: dict[str, Any] | None) -> bool:
        payload = dict(anchor_payload or {})
        anchor_source = str(payload.get("anchor_source") or "").strip().lower()
        if anchor_source not in {"rag_answer_text", "rag_evidence_text"}:
            return False
        knowledge_context = str(payload.get("knowledge_context") or "").strip()
        return "题库参考资料：" in knowledge_context

    @staticmethod
    def _mark_similar_source_variant(
        *,
        qa_pairs: list[QAPair],
        anchor_payload: dict[str, Any] | None,
        counters: dict[str, Any],
    ) -> None:
        payload = dict(anchor_payload or {})
        knowledge_context = str(payload.get("knowledge_context") or "").strip()
        evidence_refs = list(payload.get("evidence_refs") or [])
        counters["lightweight_batch_fallback"] = "similar_source_variant"
        counters["variant_hits"] = len(qa_pairs)
        for qa_pair in qa_pairs:
            metadata = dict(qa_pair.metadata or {})
            metadata.update(
                {
                    "source": "similar_question_variant",
                    "question_review_variant_mode": True,
                    "variant_from_similar_source": True,
                    "variant_source": str(payload.get("anchor_source") or "").strip(),
                    "variant_notice": "基于题库/知识库相似来源生成的变式题，不是原题复刻。",
                    "lightweight_generation": True,
                }
            )
            if knowledge_context:
                metadata["knowledge_context"] = knowledge_context
            if evidence_refs:
                metadata["evidence_refs"] = evidence_refs
            qa_pair.metadata = metadata

            validation = dict(qa_pair.validation or {})
            validation["source"] = "similar_question_variant"
            validation["variant_from_similar_source"] = True
            qa_pair.validation = validation

            grading_key = dict(qa_pair.grading_key or {})
            if qa_pair.correct_answer and not grading_key.get("correct_answer"):
                grading_key["correct_answer"] = qa_pair.correct_answer
            grading_key["source"] = "similar_question_variant"
            if not str(grading_key.get("minimal_rationale") or "").strip():
                grading_key["minimal_rationale"] = (
                    qa_pair.explanation
                    or "基于相似题库/知识库来源生成的变式题；不声明为题库原题。"
                )
            qa_pair.grading_key = grading_key

    @staticmethod
    def _extract_bank_options_from_payload(payload: dict[str, Any]) -> dict[str, str]:
        """Best-effort extract options dict from anchor evidence_refs."""
        direct_options = AgentCoordinator._parse_reference_options(payload.get("options"))
        if direct_options:
            return direct_options
        for ref in list(payload.get("evidence_refs") or []):
            if not isinstance(ref, dict):
                continue
            content = ref.get("content")
            if isinstance(content, dict):
                opts = content.get("options")
                if isinstance(opts, dict) and opts:
                    return {str(k).upper(): str(v) for k, v in opts.items() if str(v).strip()}
        # 兜底：从 anchor knowledge_context 文本里 parse 选项（A. xxx 形式）
        ctx = str(payload.get("knowledge_context") or "")
        options: dict[str, str] = {}
        for match in re.finditer(r"([A-E])[\.\、:：]\s*([^\n]+)", ctx):
            options[match.group(1)] = match.group(2).strip()[:200]
        return options

    async def _lightweight_batch_generate(
        self,
        *,
        templates: list[QuestionTemplate],
        user_topic: str,
        preference: str,
        history_context: str,
        counters: dict[str, Any],
    ) -> list[QAPair]:
        """plan §Phase 2 Step 2.2 / Batch B Gap 1 — true single-call LLM batch.

        主路径：调用 ``Generator.process_batch_lightweight(templates)`` 一次性出 N 题。
          * 1-3 题：1 次 LLM。
          * 4-5 题：先尝试 1 次 LLM 出 5；schema/数量 fail 时把 templates 拆成
            ≤3 + 剩余两个 batch，最多 2 次 LLM。
          * 仍 fail 时 fallback 到逐题并行（asyncio.gather），trace 标记
            ``lightweight_batch_fallback="parallel"``。
        """
        if not templates:
            return []
        generator = self._create_generator()
        counters["generated_explanation"] = False
        counters.setdefault("lightweight_batch_fallback", "none")

        # 主路径：单次 LLM 出 N 题。
        if len(templates) <= 3:
            counters["llm_calls"] += 1
            batch = await generator.process_batch_lightweight(
                templates=templates,
                user_topic=user_topic,
                preference=preference,
                history_context=history_context,
            )
            if batch is not None and len(batch) == len(templates):
                counters["lightweight_batch_fallback"] = "none"
                return list(batch)

        # 二次路径（仅 4-5 题）：拆成两个 ≤3 题 batch，最多再 1 次 LLM。
        if 4 <= len(templates) <= 5:
            half = 3
            first, second = templates[:half], templates[half:]
            counters["llm_calls"] += 2  # split path 实际两次 batch (3+rest)
            batch_a = await generator.process_batch_lightweight(
                templates=first,
                user_topic=user_topic,
                preference=preference,
                history_context=history_context,
            )
            batch_b = await generator.process_batch_lightweight(
                templates=second,
                user_topic=user_topic,
                preference=preference,
                history_context=history_context,
            )
            if (
                batch_a is not None
                and batch_b is not None
                and len(batch_a) == len(first)
                and len(batch_b) == len(second)
            ):
                counters["lightweight_batch_fallback"] = "split_batch"
                # llm_calls 已经计了 2（主 batch fail + 1 = 1，加这里 +1 = 2）
                return list(batch_a) + list(batch_b)

        # 最后 fallback：并行逐题（plan §B Gap 1 允许 fallback 但 trace 必须标记）。
        counters["lightweight_batch_fallback"] = "parallel"

        async def _one(template: QuestionTemplate) -> QAPair:
            try:
                qa = await generator.process(
                    template=template,
                    user_topic=user_topic,
                    preference=preference,
                    history_context=history_context,
                    previous_questions=None,
                    require_explanation=False,
                    lightweight_generation=True,
                )
            except Exception as exc:
                self.logger.warning(
                    f"Lightweight parallel fallback failed for {template.question_id}: {exc}"
                )
                return QAPair(
                    question_id=template.question_id,
                    question=f"[Generation failed] {template.concentration}",
                    correct_answer="N/A",
                    explanation=str(exc),
                    question_type=template.question_type,
                    concentration=template.concentration,
                    difficulty=template.difficulty,
                    metadata={"error": str(exc), "lightweight_generation": True},
                )
            grading_key = {
                "correct_answer": qa.correct_answer,
                "scoring_points": [],
                "common_traps": [],
                "minimal_rationale": qa.explanation[:120] if qa.explanation else "",
                "source": "lightweight_parallel_fallback",
            }
            qa.grading_key = grading_key
            return qa

        counters["llm_calls"] += len(templates)
        results = await asyncio.gather(*[_one(t) for t in templates], return_exceptions=False)
        return list(results)

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
        fallback = self._base_lightweight_anchor_payload(user_topic=user_topic)
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
                f"Lightweight topic RAG anchor failed for '{user_topic}': {exc}"
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
    def _base_lightweight_anchor_payload(*, user_topic: str) -> dict[str, Any]:
        embedded_anchor = AgentCoordinator._extract_embedded_generation_anchor(user_topic)
        if embedded_anchor:
            return {
                "knowledge_context": embedded_anchor,
                "concentration": AgentCoordinator._derive_lightweight_anchor_label(
                    user_topic=embedded_anchor
                ),
                "anchor_source": "resolved_topic_anchor",
            }
        anchor_label = AgentCoordinator._derive_lightweight_anchor_label(user_topic=user_topic)
        return {
            "knowledge_context": f"当前学习锚点：{anchor_label}",
            "concentration": anchor_label,
        }

    @staticmethod
    def _current_question_exclusion_anchor_payload(*, user_topic: str) -> dict[str, Any]:
        topic = str(user_topic or "").strip()
        anchor_label = AgentCoordinator._current_question_exclusion_anchor_label(
            user_topic=topic
        )
        return {
            "knowledge_context": topic or "请从建筑实务/建造师考试高频考点中选择一个不同小考点出题。",
            "concentration": anchor_label or "建筑实务高频考点",
            "anchor_source": "current_question_exclusion",
        }

    @staticmethod
    def _current_question_exclusion_anchor_label(*, user_topic: str) -> str:
        topic = str(user_topic or "").strip()
        if not topic:
            return "建筑实务高频考点"

        generation_scope = topic.split("排除当前题", 1)[0].strip()
        invalid_markers = (
            "排除当前题",
            "需避开",
            "不得作为新题考点",
            "题干",
            "选项面",
            "不同考点",
            "刚才那题",
            "重复",
        )

        def _clean_label(value: str) -> str:
            label = re.sub(r"\s+", " ", str(value or "")).strip()
            label = re.sub(r"^[：:，,。；;\s]+", "", label).strip()
            label = re.sub(r"[：:，,。；;\s]+$", "", label).strip()
            if not label or label in {"新对话", "当前会话主题", "当前学习主题"}:
                return ""
            if any(marker in label for marker in invalid_markers):
                return ""
            return label[:32]

        for line in generation_scope.splitlines():
            match = re.search(
                r"(?:当前(?:会话|学习)主题|当前学习锚点|最近对话摘要)[:：](?P<label>.+)",
                line,
            )
            if not match:
                continue
            label = _clean_label(match.group("label"))
            if label:
                return label

        first_paragraph = generation_scope.split("\n\n", 1)[0]
        derived = _clean_label(
            AgentCoordinator._derive_lightweight_anchor_label(user_topic=first_paragraph)
        )
        if derived and practice_generation_topic_domain_status(derived) == "construction_topic":
            return derived
        return "建筑实务高频考点"

    @staticmethod
    def _extract_embedded_generation_anchor(user_topic: str) -> str:
        text = str(user_topic or "").strip()
        marker = "请严格围绕以下当前学习锚点出题"
        marker_index = text.find(marker)
        if marker_index < 0:
            return ""
        tail = text[marker_index + len(marker) :]
        if "：" in tail:
            tail = tail.split("：", 1)[1]
        elif ":" in tail:
            tail = tail.split(":", 1)[1]
        return re.sub(r"\s+", " ", tail).strip()[:500]

    @staticmethod
    def _lightweight_anchor_has_grounding(anchor_payload: dict[str, Any] | None) -> bool:
        payload = anchor_payload if isinstance(anchor_payload, dict) else {}
        if str(payload.get("anchor_source") or "").strip():
            return True
        if str(payload.get("reference_question") or "").strip():
            return True
        if str(payload.get("source_group") or "").strip() or str(payload.get("source_id") or "").strip():
            return True
        evidence_refs = payload.get("evidence_refs")
        return isinstance(evidence_refs, list) and any(isinstance(ref, dict) for ref in evidence_refs)

    @staticmethod
    def _should_block_unresolved_lightweight_anchor(
        *,
        user_topic: str,
        anchor_payload: dict[str, Any] | None,
    ) -> bool:
        if AgentCoordinator._lightweight_anchor_has_grounding(anchor_payload):
            return False
        payload = anchor_payload if isinstance(anchor_payload, dict) else {}
        label = str(payload.get("concentration") or "").strip() or AgentCoordinator._derive_lightweight_anchor_label(
            user_topic=user_topic
        )
        return practice_generation_request_needs_context_anchor(label)

    @staticmethod
    def _build_lightweight_rag_anchor_payload(
        *,
        user_topic: str,
        result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base = AgentCoordinator._base_lightweight_anchor_payload(user_topic=user_topic)
        anchor_label = str(base.get("concentration") or "").strip()
        if not isinstance(result, dict):
            return base

        exact_question = (
            result.get("exact_question")
            if isinstance(result.get("exact_question"), dict)
            else {}
        )
        evidence_refs = AgentCoordinator._compact_rag_evidence_refs(result)
        stem = str(exact_question.get("stem") or "").strip()
        analysis = str(exact_question.get("analysis") or "").strip()
        correct_answer = str(exact_question.get("correct_answer") or "").strip()
        options = exact_question.get("options")

        evidence_anchor = AgentCoordinator._extract_structured_anchor_from_evidence_bundle(
            user_topic=user_topic,
            result=result,
        )
        if evidence_anchor:
            if not str(evidence_anchor.get("reference_answer") or "").strip():
                return base
            evidence_parts: list[str] = [base["knowledge_context"]]
            evidence_parts.append(f"题库参考题目：{evidence_anchor['reference_question']}")
            evidence_option_lines = AgentCoordinator._format_reference_options(
                evidence_anchor.get("options")
            )
            if evidence_option_lines:
                evidence_parts.append("题库选项风格参考：\n" + "\n".join(evidence_option_lines[:5]))
            if evidence_anchor.get("reference_answer"):
                evidence_parts.append(
                    f"题库参考答案（仅内部生成锚点）：{evidence_anchor['reference_answer']}"
                )
            if evidence_anchor.get("analysis"):
                clipped_analysis = evidence_anchor["analysis"][:280] + (
                    "..." if len(evidence_anchor["analysis"]) > 280 else ""
                )
                evidence_parts.append(f"题库解析要点：{clipped_analysis}")
            evidence_ref = evidence_anchor.get("evidence_ref")
            return {
                "knowledge_context": "\n".join(evidence_parts),
                "concentration": anchor_label or evidence_anchor["reference_question"][:32] or "当前学习主题",
                "reference_question": evidence_anchor["reference_question"],
                "reference_answer": evidence_anchor.get("reference_answer"),
                "analysis": evidence_anchor.get("analysis"),
                "options": evidence_anchor.get("options"),
                "anchor_source": "question_evidence_bundle",
                "source_group": evidence_anchor.get("source_group"),
                "source_id": evidence_anchor.get("source_id"),
                "evidence_refs": [evidence_ref] if isinstance(evidence_ref, dict) else evidence_refs,
            }

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
            if not correct_answer:
                return base
            # Topic-relevance gate (Bug#1 主因): only adopt this RAG hit as the
            # canonical generation anchor when it actually matches the user's topic.
            # Otherwise an off-topic top hit (e.g. SMA query → 垂直运输 question) would
            # become a hard anchor and the generator, told to "stay within the anchor",
            # produces an off-topic question. Fall back to the pure topic anchor.
            if not AgentCoordinator._structured_anchor_matches_topic(
                user_topic, f"{stem}\n{analysis}\n{correct_answer}"
            ):
                return base
            return {
                "knowledge_context": "\n".join(parts),
                "concentration": anchor_label or stem or "当前学习主题",
                "reference_question": stem,
                "reference_answer": correct_answer,
                "analysis": analysis,
                "options": AgentCoordinator._parse_reference_options(options),
                "anchor_source": str(exact_question.get("source_group") or "").strip() or "exact_question",
                "anchor_confidence": exact_question.get("confidence"),
                "evidence_refs": evidence_refs,
            }

        answer = str(result.get("answer") or "").strip()
        if not answer:
            if not evidence_refs:
                return base
            evidence_texts: list[str] = []
            for ref in evidence_refs[:2]:
                if not isinstance(ref, dict):
                    continue
                content = ref.get("content")
                if isinstance(content, dict):
                    content = content.get("content") or content.get("text") or content.get("source_id")
                text = str(content or "").strip()
                if text:
                    evidence_texts.append(text)
            if not evidence_texts:
                return base
            clipped_evidence = "\n".join(evidence_texts)[:280]
            if len("\n".join(evidence_texts)) > 280:
                clipped_evidence += "..."
            if not AgentCoordinator._structured_anchor_matches_topic(user_topic, clipped_evidence):
                return base
            return {
                "knowledge_context": f"{base['knowledge_context']}\n题库参考资料：{clipped_evidence}",
                "concentration": anchor_label,
                "anchor_source": "rag_evidence_text",
                "evidence_refs": evidence_refs,
            }

        parsed_bundle = AgentCoordinator._extract_structured_anchor_from_answer(answer)
        if parsed_bundle and not AgentCoordinator._structured_anchor_matches_topic(
            user_topic,
            f"{parsed_bundle.get('reference_question') or ''}\n{parsed_bundle.get('analysis') or ''}",
        ):
            return base
        if parsed_bundle:
            if not str(parsed_bundle.get("reference_answer") or "").strip():
                return base
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
                "analysis": parsed_bundle.get("analysis"),
                "options": parsed_bundle.get("options"),
                "anchor_source": "rag_answer_bundle",
                "evidence_refs": evidence_refs,
            }

        clipped_answer = answer[:280] + ("..." if len(answer) > 280 else "")
        if not AgentCoordinator._structured_anchor_matches_topic(user_topic, clipped_answer):
            return base
        return {
            "knowledge_context": f"{base['knowledge_context']}\n题库参考资料：{clipped_answer}",
            "concentration": anchor_label,
            "anchor_source": "rag_answer_text",
            "evidence_refs": evidence_refs,
        }

    @staticmethod
    def _compact_rag_evidence_refs(result: dict[str, Any]) -> list[dict[str, Any]]:
        bundle = result.get("evidence_bundle") if isinstance(result.get("evidence_bundle"), dict) else {}
        if not bundle:
            return []
        refs: list[dict[str, Any]] = []
        retrieval_status = str(bundle.get("retrieval_status") or "").strip()
        for source in list(bundle.get("sources") or [])[:3]:
            if not isinstance(source, dict):
                continue
            source_group = str(
                source.get("_source_group")
                or source.get("source_group")
                or source.get("_source_table")
                or source.get("source_type")
                or "retrieval"
            ).strip()
            source_id = str(source.get("chunk_id") or source.get("id") or source.get("question_id") or "").strip()
            content = (
                source.get("content")
                or source.get("text")
                or source.get("answer")
                or source.get("stem")
                or source.get("title")
                or source_id
            )
            if content in (None, "", [], {}):
                continue
            value = {"source_group": source_group, "source_id": source_id, "content": str(content)[:500]}
            if retrieval_status:
                value["retrieval_status"] = retrieval_status
            refs.append({"source": "evidence_bundle", "field": source_group or "source", "content": value})
        if refs:
            return refs
        content_blocks = [str(item).strip() for item in list(bundle.get("content_blocks") or []) if str(item).strip()]
        if not content_blocks:
            return []
        value: dict[str, Any] = {"content": content_blocks[0][:500]}
        if retrieval_status:
            value["retrieval_status"] = retrieval_status
        return [{"source": "evidence_bundle", "field": "content_blocks", "content": value}]

    @staticmethod
    def _extract_structured_anchor_from_evidence_bundle(
        *,
        user_topic: str,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        bundle = result.get("evidence_bundle") if isinstance(result.get("evidence_bundle"), dict) else {}
        for source in list(bundle.get("sources") or [])[:5]:
            if not isinstance(source, dict):
                continue
            raw = (
                source.get("content")
                or source.get("text")
                or source.get("answer")
                or source.get("stem")
                or ""
            )
            parsed = AgentCoordinator._extract_structured_anchor_from_answer(str(raw or ""))
            if not parsed:
                continue
            searchable = "\n".join(
                str(parsed.get(key) or "") for key in ("reference_question", "analysis")
            )
            if not AgentCoordinator._structured_anchor_matches_topic(user_topic, searchable):
                continue
            source_group = str(
                source.get("_source_group")
                or source.get("source_group")
                or source.get("_source_table")
                or source.get("source_type")
                or "retrieval"
            ).strip()
            source_id = str(source.get("chunk_id") or source.get("id") or source.get("question_id") or "").strip()
            evidence_ref = {
                "source": "evidence_bundle",
                "field": source_group or "source",
                "content": {
                    "source_group": source_group,
                    "source_id": source_id,
                    "content": str(raw or "")[:500],
                },
            }
            return {
                **parsed,
                "source_group": source_group,
                "source_id": source_id,
                "evidence_ref": evidence_ref,
            }
        return None

    @staticmethod
    def _structured_anchor_matches_topic(user_topic: str, content: str) -> bool:
        text = re.sub(r"\s+", "", str(user_topic or ""))
        haystack = str(content or "")
        known_terms = (
            "钢筋",
            "保护层",
            "混凝土",
            "验槽",
            "防火门",
            "防水",
            "保温",
            "脚手架",
            "模板",
            "进度",
            "流水",
        )
        terms = [term for term in known_terms if term in text]
        if terms:
            if "保护层" in terms and "保护层" not in haystack:
                return False
            matched = sum(1 for term in terms if term in haystack)
            return matched >= min(2, len(terms))
        cleaned = re.sub(
            r"(分析|讲解|解析|讲|再出|再来|出几道|出一?[道题]|来一?[道题]|换一?[道题]|一道|一题|几道|"
            r"真题|题目|考一?下|考一?考|考我|考|一下|关于|帮我|麻烦|请|的|题)",
            " ",
            text,
        )
        loose_terms = [part for part in re.split(r"[\s，。！？、,.;；:：0-9]+", cleaned) if len(part) >= 2]
        if not loose_terms:
            return False
        if any(term in haystack for term in loose_terms[:3]):
            return True
        # Finer-grained fallback: a shared distinctive 2-gram between the (cleaned)
        # topic terms and the anchor means same subject with different wording
        # (e.g. topic "法律基础" vs stem "属于法律" share 法律). An off-topic anchor
        # (SMA topic vs 垂直运输/井架 stem) shares none and is rejected.
        topic_bigrams = {t[i : i + 2] for t in loose_terms for i in range(len(t) - 1)}
        return any(bigram in haystack for bigram in topic_bigrams)

    @staticmethod
    def _generated_questions_in_construction_scope(
        templates: list[QuestionTemplate], qa_pairs: list[dict[str, Any]]
    ) -> bool:
        """出口科目门（owner 决策=现阶段只服务建筑实务）：复用单一建筑判据
        practice_generation_topic_domain_status（入口出口同源，不另造科目权威），判生成题
        考点+题面是否建筑实务。

        口径与入口门 practice_generation_topic_block_decision **对称**：只在生成题**确有
        他科证据（out_of_scope_topic 命中法语/数学等）且无任何建筑证据**时才判
        subject_unavailable。``unknown_topic``（关键词白名单未覆盖的建筑长尾，如"水泥/沟槽
        开挖"）一律视为 in-scope 放行——禁止重蹈入口门已修正过的 ``!= construction_topic``
        误拒（白名单永远不全，正向命中口径会把同主题的不同表述当跑题，见 teaching_modes.py
        practice_generation_topic_block_decision 的修正注释）。无题面可判时不拦（避免空判误拒）。
        """
        texts: list[str] = []
        for qp in qa_pairs or []:
            pair = qp.get("qa_pair") if isinstance(qp, dict) else None
            if isinstance(pair, dict):
                texts.append(f"{pair.get('concentration') or ''} {pair.get('question') or ''}")
        for template in templates or []:
            texts.append(str(getattr(template, "concentration", "") or ""))
        candidates = [text for text in texts if text.strip()]
        if not candidates:
            return True
        statuses = [
            practice_generation_topic_domain_status(text) for text in candidates
        ]
        if any(status == "construction_topic" for status in statuses):
            return True
        return not any(status == "out_of_scope_topic" for status in statuses)

    @staticmethod
    def _derive_lightweight_anchor_label(
        *,
        user_topic: str,
    ) -> str:
        text = re.sub(r"\s+", " ", str(user_topic or "")).strip()
        if not text:
            return "当前学习主题"
        explicit_topic = AgentCoordinator._extract_explicit_lightweight_topic_label(text)
        if explicit_topic:
            return explicit_topic[:32]
        patterns = (
            r"^(我现在学到|我学到|现在学到|学到)",
            r"^(我现在在学|我在学|现在在学|最近在学|正在学)",
            r"^(先|请|麻烦你|麻烦)",
            r"(先|请|麻烦你|麻烦)?给我",
            r"来[一1]?道",
            r"出[一1]?道",
            r"建筑实务",
            r"(单选题|多选题|选择题|判断题|简答题|案例题)",
            r"(题目?|练习)$",
            r"(不要给答案|别给答案|先不要答案|只出题|不要解析|别解析)",
            r"(很短的小题|很短的小测|小题|小测)",
            r"(考我|刷题)",
        )

        def _clean_clause(raw: str) -> str:
            cleaned = raw
            for pattern in patterns:
                cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"[，。！？、,.!?\-:：\s]+", " ", cleaned).strip()
            cleaned = re.sub(r"(吧|了|呢|呀)$", "", cleaned).strip()
            return cleaned

        for clause in re.split(r"[，,。!?！？；;]", text):
            cleaned = _clean_clause(clause)
            if not cleaned or cleaned in {"先", "题", "一道", "一题"}:
                continue
            if practice_generation_topic_domain_status(cleaned) == "construction_topic":
                return cleaned[:32]

        first_clause = re.split(r"[，,。!?！？]", text, maxsplit=1)[0].strip() or text
        cleaned = _clean_clause(first_clause)
        if cleaned and cleaned not in {"先", "题", "一道", "一题"}:
            return cleaned[:32]
        return text[:32] or "当前学习主题"

    @staticmethod
    def _extract_explicit_lightweight_topic_label(text: str) -> str:
        for pattern in (
            r"(?:围绕|关于|针对)(?P<label>[^，,。!?！？；;:：]+)",
            r"考(?!我|点|试)(?P<label>[^，,。!?！？；;:：]+)",
        ):
            match = re.search(pattern, text)
            if not match:
                continue
            label = re.sub(r"\s+", " ", match.group("label")).strip()
            label = re.sub(r"^(一下|下|一?道|建筑实务|实务|的)+", "", label).strip()
            label = re.split(
                r"(?:给我)?(?:出|来|生成|编)[一1]?(?:道|个|题)?|带[A-DABCD\-]+选项|带选项",
                label,
                maxsplit=1,
            )[0].strip()
            label = re.sub(
                r"的?(单选题|多选题|选择题|判断题|简答题|案例题|题目|练习|小测|小题)(吧)?$",
                "",
                label,
            ).strip()
            label = re.sub(r"[，。！？、,.!?\-:：\s]+", " ", label).strip()
            label = re.sub(r"(吧|了|呢|呀)$", "", label).strip()
            if label:
                return label
        return ""

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
        stem, inline_options = AgentCoordinator._split_reference_question_and_inline_options(
            str(match.group("stem") or "").strip()
        )
        if not stem:
            return None
        reference_answer = re.sub(r"\s+", " ", str(match.group("answer") or "")).strip() or None
        analysis = re.sub(r"\s+", " ", str(match.group("analysis") or "")).strip()
        options = (
            AgentCoordinator._parse_reference_options(match.group("options"))
            or AgentCoordinator._parse_reference_options(inline_options)
        )
        return {
            "reference_question": stem,
            "reference_answer": reference_answer,
            "analysis": analysis,
            "options": options,
        }

    @staticmethod
    def _split_reference_question_and_inline_options(stem: str) -> tuple[str, str]:
        text = str(stem or "").strip()
        if not text:
            return "", ""
        match = re.search(r"(?:^|\n)\s*A[\.\):、]\s+", text)
        if not match:
            return text, ""
        question = text[: match.start()].strip()
        inline_options = text[match.start() :].strip()
        return question, inline_options

    @staticmethod
    def _parse_reference_options(raw_options: Any) -> dict[str, str] | None:
        if isinstance(raw_options, dict):
            options = {
                str(key or "").strip().upper()[:1]: str(value or "").strip()
                for key, value in raw_options.items()
                if str(key or "").strip() and str(value or "").strip()
            }
            return options or None
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
                if isinstance(item, dict):
                    key = str(item.get("key") or item.get("label") or "").strip().upper()[:1]
                    value = str(item.get("value") or item.get("text") or item.get("content") or "").strip()
                else:
                    match = re.match(r"^([A-E])[\.\):、]?\s*(.+)$", str(item or "").strip(), flags=re.IGNORECASE)
                    if not match:
                        continue
                    key = match.group(1).upper()
                    value = match.group(2).strip()
                if key and value:
                    options[key] = value
            return options or None

        option_text = re.split(r"【答案】|【解析】|【题目】", raw_text, maxsplit=1)[0]
        matches = re.findall(r"([A-E])[\.\):、]\s*([^\n]+)", option_text, flags=re.IGNORECASE)
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
        grading_result = (
            item.get("construction_grading_result")
            if isinstance(item.get("construction_grading_result"), dict)
            else {}
        )
        next_training_signal = (
            grading_result.get("next_training_signal")
            if isinstance(grading_result, dict)
            else {}
        )
        if concentration:
            sections.append(f"当前知识点：{concentration}")
        if question:
            sections.append(f"参考题目：{question}")
        if explanation:
            sections.append(f"参考解析：{explanation}")
        if knowledge_context and knowledge_context not in explanation:
            sections.append(f"补充知识：{knowledge_context}")
        if isinstance(next_training_signal, dict) and next_training_signal:
            signal_parts = [
                f"{key}={value}"
                for key, value in (
                    ("concept", next_training_signal.get("concept")),
                    ("focus", next_training_signal.get("focus")),
                    ("mode", next_training_signal.get("mode")),
                )
                if str(value or "").strip()
            ]
            error_codes = [
                str(error.get("error_code") or "").strip()
                for error in list(grading_result.get("error_events") or [])
                if isinstance(error, dict) and str(error.get("error_code") or "").strip()
            ]
            if error_codes:
                signal_parts.append(f"error_codes={','.join(error_codes[:4])}")
            if signal_parts:
                sections.append(
                    "下一题训练信号："
                    + "；".join(signal_parts)
                    + "。优先从现有题库选择同考点、同错因的相似题，不要泄露答案。"
                )
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
