"""
Deep Question Capability
========================

Multi-agent question generation pipeline: Idea -> Evaluate -> Generate -> Validate.
Wraps the existing ``AgentCoordinator``.
"""

from __future__ import annotations

import base64
import re
import tempfile
from typing import Any

from deeptutor.capabilities.request_contracts import get_capability_request_schema
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.trace import merge_trace_metadata
from deeptutor.services.question_followup import (
    answers_match,
    build_question_followup_context_from_summary,
    extract_submission_answer,
    normalize_question_followup_context,
    resolve_submission,
)


class DeepQuestionCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="deep_question",
        description="Fast question generation (Template batches -> Generate).",
        stages=["ideation", "generation"],
        tools_used=["rag", "web_search", "code_execution"],
        cli_aliases=["quiz"],
        request_schema=get_capability_request_schema("deep_question"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        from deeptutor.agents.question.coordinator import AgentCoordinator
        from deeptutor.services.llm.config import get_llm_config
        from deeptutor.services.path_service import get_path_service

        llm_config = get_llm_config()
        kb_name = context.knowledge_bases[0] if context.knowledge_bases else None
        turn_id = str(context.metadata.get("turn_id", "") or context.session_id or "deep-question")
        output_dir = get_path_service().get_task_workspace("deep_question", turn_id)

        overrides = context.config_overrides
        followup_question_context = (
            context.metadata.get("question_followup_context", {}) or {}
        )
        if isinstance(followup_question_context, dict) and followup_question_context.get(
            "question"
        ):
            narrowed_context, submission_answer = resolve_submission(
                context.user_message,
                followup_question_context,
            )
            if narrowed_context and submission_answer is not None:
                from deeptutor.agents.question.agents.submission_grader_agent import (
                    SubmissionGraderAgent,
                )

                graded_context = self._build_submission_context(
                    narrowed_context,
                    submission_answer,
                    raw_submission=context.user_message,
                )
                agent = SubmissionGraderAgent(
                    language=context.language,
                    api_key=llm_config.api_key,
                    base_url=llm_config.base_url,
                    api_version=llm_config.api_version,
                )
                agent.set_trace_callback(self._build_trace_bridge(stream))
                async with stream.stage("generation", source=self.name):
                    answer = await agent.process(
                        user_message=context.user_message,
                        question_context=graded_context,
                        history_context=str(
                            context.metadata.get("conversation_context_text", "") or ""
                        ).strip(),
                    )
                    if answer:
                        await stream.content(answer, source=self.name, stage="generation")
                    result_payload: dict[str, Any] = {
                        "response": answer or "",
                        "mode": "grading",
                        "question_id": graded_context.get("question_id", ""),
                        "user_answer": graded_context.get("user_answer", ""),
                        "is_correct": graded_context.get("is_correct"),
                        "question_followup_context": normalize_question_followup_context(
                            graded_context
                        )
                        or {},
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        result_payload["metadata"] = {"cost_summary": cost_meta}
                    await stream.result(result_payload, source=self.name)
                return

            from deeptutor.agents.question.agents.followup_agent import FollowupAgent

            agent = FollowupAgent(
                language=context.language,
                api_key=llm_config.api_key,
                base_url=llm_config.base_url,
                api_version=llm_config.api_version,
            )
            agent.set_trace_callback(self._build_trace_bridge(stream))
            async with stream.stage("generation", source=self.name):
                answer = await agent.process(
                    user_message=context.user_message,
                    question_context=followup_question_context,
                    history_context=str(
                        context.metadata.get("conversation_context_text", "") or ""
                    ).strip(),
                )
                if answer:
                    await stream.content(answer, source=self.name, stage="generation")
                followup_payload: dict[str, Any] = {
                    "response": answer or "",
                    "mode": "followup",
                    "question_id": followup_question_context.get("question_id", ""),
                    "question_followup_context": normalize_question_followup_context(
                        followup_question_context
                    )
                    or {},
                }
                cost_meta = self._collect_cost_summary("question")
                if cost_meta:
                    followup_payload["metadata"] = {"cost_summary": cost_meta}
                await stream.result(followup_payload, source=self.name)
            return

        mode = str(overrides.get("mode", "custom") or "custom").strip().lower()
        topic = str(overrides.get("topic") or context.user_message or "").strip()
        num_questions = int(overrides.get("num_questions", 1) or 1)
        difficulty = str(overrides.get("difficulty", "") or "")
        question_type = str(overrides.get("question_type", "") or "")
        preference = str(overrides.get("preference", "") or "")
        reveal_answers = bool(overrides.get("reveal_answers", False))
        reveal_explanations = bool(overrides.get("reveal_explanations", reveal_answers))
        history_context = str(
            context.metadata.get("conversation_context_text", "") or ""
        ).strip()
        enabled_tools = set(
            self.manifest.tools_used
            if context.enabled_tools is None
            else context.enabled_tools
        )
        tool_flags_override = {
            "rag": "rag" in enabled_tools,
            "web_search": "web_search" in enabled_tools,
            "code_execution": "code_execution" in enabled_tools,
        }

        coordinator = AgentCoordinator(
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            api_version=llm_config.api_version,
            kb_name=kb_name,
            language=context.language,
            output_dir=str(output_dir),
            tool_flags_override=tool_flags_override,
            enable_idea_rag="rag" in enabled_tools,
        )

        _trace_bridge = self._build_trace_bridge(stream)

        # Bridge ws_callback to StreamBus
        async def _ws_bridge(update: dict[str, Any]) -> None:
            update_type = update.get("type", "")
            inner = str(update.get("stage", "") or "")
            if update_type == "result" or inner in {"generation", "complete"}:
                stage = "generation"
            elif inner in {"parsing", "extracting", "ideation"}:
                stage = "ideation"
            else:
                stage = "generation" if update_type == "question_update" else "ideation"
            message = self._format_bridge_message(update_type, update)
            metadata = {
                key: value
                for key, value in update.items()
                if key not in {"type", "message"}
            }
            if "question_id" in update:
                metadata.setdefault("trace_id", str(update.get("question_id")))
                metadata.setdefault(
                    "label",
                    f"Generate {self._humanize_question_id(update.get('question_id'))}",
                )
            elif "batch" in update:
                metadata.setdefault("trace_id", f"batch-{update.get('batch')}")
                metadata.setdefault("label", f"Batch {update.get('batch')}")
            metadata["update_type"] = update_type
            metadata.setdefault("phase", stage)
            await stream.progress(
                message=message,
                source=self.name,
                stage=stage,
                metadata=merge_trace_metadata(metadata, {"trace_kind": "progress"}),
            )

        coordinator.set_ws_callback(_ws_bridge)
        if hasattr(coordinator, "set_trace_callback"):
            coordinator.set_trace_callback(_trace_bridge)

        if mode == "mimic":
            result = await self._run_mimic_mode(
                coordinator=coordinator,
                context=context,
                stream=stream,
                overrides=overrides,
            )
            if not result:
                return
        else:
            if not topic:
                await stream.error("Topic is required for custom question generation.", source=self.name)
                return

            async with stream.stage("ideation", source=self.name):
                await stream.thinking("Generating question templates...", source=self.name, stage="ideation")

            result = await coordinator.generate_from_topic(
                user_topic=topic,
                preference=preference,
                num_questions=num_questions,
                difficulty=difficulty,
                question_type=question_type,
                history_context=history_context,
            )

        content = self._render_summary_markdown(
            result,
            reveal_answers=reveal_answers,
            reveal_explanations=reveal_explanations,
        )
        if content:
            await stream.content(content, source=self.name, stage="generation")

        result_payload: dict[str, Any] = {
            "response": content or "No questions generated.",
            "summary": result,
            "mode": mode,
            "question_followup_context": build_question_followup_context_from_summary(
                result,
                content or "",
                reveal_answers=reveal_answers,
                reveal_explanations=reveal_explanations,
            )
            or {},
        }
        cost_meta = self._collect_cost_summary("question")
        if cost_meta:
            result_payload["metadata"] = {"cost_summary": cost_meta}
        await stream.result(result_payload, source=self.name)

    @staticmethod
    def _build_submission_context(
        question_context: dict[str, Any],
        user_answer: str,
        *,
        raw_submission: str = "",
    ) -> dict[str, Any]:
        graded_context = dict(question_context)
        correct_answer = str(question_context.get("correct_answer", "") or "").strip()
        is_correct = answers_match(user_answer, correct_answer, graded_context)
        graded_context["user_answer"] = str(user_answer or "").strip()
        graded_context["is_correct"] = is_correct
        graded_context["score"] = 100 if is_correct else 0
        graded_context["diagnosis"] = DeepQuestionCapability._diagnose_choice_submission(
            question_context=question_context,
            user_answer=user_answer,
            raw_submission=raw_submission,
        )
        return graded_context

    @staticmethod
    def _diagnose_choice_submission(
        *,
        question_context: dict[str, Any],
        user_answer: str,
        raw_submission: str = "",
    ) -> str:
        correct_answer = str(question_context.get("correct_answer", "") or "").strip().upper()
        normalized_answer = str(user_answer or "").strip().upper()
        if not normalized_answer:
            return "INVALID"
        if not correct_answer:
            return "INVALID"
        if answers_match(normalized_answer, correct_answer, question_context):
            return "CORRECT"
        if normalized_answer not in {"A", "B", "C", "D"} and correct_answer not in {"A", "B", "C", "D"}:
            return "CONFUSION"

        raw_text = str(raw_submission or "").strip().lower()
        if any(marker in raw_text for marker in ("手滑", "看错", "粗心", "点错", "写错")):
            return "SLIP"

        combined = " ".join(
            str(question_context.get(key, "") or "")
            for key in ("question", "explanation", "knowledge_context", "concentration")
        ).lower()

        negative_stem_markers = (
            "不应",
            "不宜",
            "不得",
            "不能",
            "错误",
            "不正确",
            "除外",
            "不属于",
            "不是",
            "严禁",
        )
        has_numeric_signal = bool(
            re.search(r"\d+(?:\.\d+)?\s*(?:%|‰|℃|mm|cm|m|km|kg|kN|MPa|d|h|min|天|小时|分钟|万元|元)", combined)
            or re.search(r"第[一二三四五六七八九十0-9]+", combined)
        )
        calc_markers = (
            "计算",
            "合计",
            "总工期",
            "持续时间",
            "流水节拍",
            "流水步距",
            "费用",
            "金额",
            "面积",
            "体积",
            "概率",
            "比率",
            "产值",
        )
        if has_numeric_signal and any(marker in combined for marker in calc_markers):
            return "CALC_ERROR"
        if has_numeric_signal:
            return "MEMORY_DECAY"
        if any(marker in combined for marker in negative_stem_markers):
            return "OVERSIGHT"
        return "CONFUSION"

    @staticmethod
    def _collect_cost_summary(module_name: str) -> dict[str, Any] | None:
        from deeptutor.agents.base_agent import BaseAgent
        stats = BaseAgent._shared_stats.get(module_name)
        if not stats or not stats.calls:
            return None
        s = stats.get_summary()
        stats.reset()
        return {
            "total_cost_usd": s.get("cost_usd", 0),
            "total_tokens": s.get("total_tokens", 0),
            "total_calls": s.get("calls", 0),
        }

    async def _run_mimic_mode(
        self,
        coordinator,
        context: UnifiedContext,
        stream: StreamBus,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        paper_path = str(overrides.get("paper_path", "") or "").strip()
        max_questions = int(overrides.get("max_questions", 10) or 10)
        pdf_attachment = next(
            (
                attachment
                for attachment in context.attachments
                if attachment.filename.lower().endswith(".pdf")
                or attachment.type == "pdf"
                or attachment.mime_type == "application/pdf"
            ),
            None,
        )

        if pdf_attachment and pdf_attachment.base64:
            async with stream.stage("ideation", source=self.name):
                await stream.thinking(
                    "Parsing uploaded exam paper and extracting templates...",
                    source=self.name,
                    stage="ideation",
                )

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as temp_pdf:
                temp_pdf.write(base64.b64decode(pdf_attachment.base64))
                temp_pdf.flush()
                return await coordinator.generate_from_exam(
                    exam_paper_path=temp_pdf.name,
                    max_questions=max_questions,
                    paper_mode="upload",
                    history_context=str(
                        context.metadata.get("conversation_context_text", "") or ""
                    ).strip(),
                )

        if paper_path:
            async with stream.stage("ideation", source=self.name):
                await stream.thinking(
                    "Loading parsed exam paper and extracting templates...",
                    source=self.name,
                    stage="ideation",
                )
            return await coordinator.generate_from_exam(
                exam_paper_path=paper_path,
                max_questions=max_questions,
                paper_mode="parsed",
                history_context=str(
                    context.metadata.get("conversation_context_text", "") or ""
                ).strip(),
            )

        await stream.error(
            "Mimic mode requires either an uploaded PDF or a parsed exam directory.",
            source=self.name,
        )
        return {}

    @staticmethod
    def _format_bridge_message(update_type: str, update: dict[str, Any]) -> str:
        """Build a human-readable progress line from a coordinator ws_callback."""
        if update_type == "progress":
            stage = update.get("stage", "")
            status = update.get("status", "")
            cur = update.get("current", "")
            tot = update.get("total", "")
            qid = update.get("question_id", "")
            batch = update.get("batch", "")
            parts = [f"[{stage}]" if stage else ""]
            if status:
                parts.append(status)
            if cur != "" and tot:
                parts.append(f"({cur}/{tot})")
            if batch:
                parts.append(f"batch={batch}")
            if qid:
                parts.append(f"question={qid}")
            return " ".join(p for p in parts if p) or update_type

        if update_type == "templates_ready":
            count = update.get("count", 0)
            batch = update.get("batch", "")
            templates = update.get("templates", [])
            prefix = f"Templates ready (batch {batch}): {count}" if batch else f"Templates ready: {count}"
            lines = [prefix]
            for t in templates:
                if isinstance(t, dict):
                    lines.append(
                        f"  [{t.get('question_id','')}] {t.get('concentration','')[:80]} "
                        f"({t.get('question_type','')}/{t.get('difficulty','')})"
                    )
            return "\n".join(lines)

        if update_type == "question_update":
            qid = DeepQuestionCapability._humanize_question_id(update.get("question_id", ""))
            current = update.get("current", "")
            total = update.get("total", "")
            return f"Generating {qid} ({current}/{total})"

        if update_type == "result":
            qid = DeepQuestionCapability._humanize_question_id(update.get("question_id", ""))
            idx = update.get("index", "")
            q = update.get("question", {})
            qt = q.get("question_type", "") if isinstance(q, dict) else ""
            diff = q.get("difficulty", "") if isinstance(q, dict) else ""
            success = update.get("success", True)
            ordinal = ""
            if isinstance(idx, int):
                ordinal = f"#{idx + 1}, "
            return f"{qid} done ({ordinal}{qt}/{diff}, success={success})"

        return update.get("message", update_type)

    @staticmethod
    def _humanize_question_id(question_id: Any) -> str:
        raw = str(question_id or "").strip()
        match = re.fullmatch(r"q_(\d+)", raw.lower())
        if match:
            return f"Question {match.group(1)}"
        return raw or "Question"

    def _render_summary_markdown(
        self,
        summary: dict[str, Any],
        *,
        reveal_answers: bool = False,
        reveal_explanations: bool = False,
    ) -> str:
        results = summary.get("results", []) if isinstance(summary, dict) else []
        if not results:
            return ""

        lines: list[str] = []
        for idx, item in enumerate(results, 1):
            qa_pair = item.get("qa_pair", {}) if isinstance(item, dict) else {}
            question = qa_pair.get("question", "")
            if not question:
                continue

            lines.append(f"### Question {idx}\n")
            lines.append(question)

            options = qa_pair.get("options", {})
            if isinstance(options, dict) and options:
                for key, value in options.items():
                    lines.append(f"- {key}. {value}")

            answer = qa_pair.get("correct_answer", "")
            if reveal_answers and answer:
                lines.append(f"\n**Answer:** {answer}")

            explanation = qa_pair.get("explanation", "")
            if reveal_explanations and explanation:
                lines.append(f"\n**Explanation:** {explanation}")

            lines.append("")

        return "\n".join(lines).strip()

    def _build_trace_bridge(self, stream: StreamBus):
        async def _trace_bridge(update: dict[str, Any]) -> None:
            event = str(update.get("event", "") or "")
            stage = str(update.get("phase") or update.get("stage") or "generation")
            base_metadata = {
                key: value
                for key, value in update.items()
                if key
                not in {"event", "state", "response", "chunk", "result", "tool_name", "tool_args"}
            }

            if event == "llm_call":
                state = str(update.get("state", "running"))
                label = str(update.get("label", "") or "")
                if state == "running":
                    await stream.progress(
                        message=label,
                        source=self.name,
                        stage=stage,
                        metadata=merge_trace_metadata(
                            base_metadata,
                            {"trace_kind": "call_status", "call_state": "running"},
                        ),
                    )
                    return
                if state == "streaming":
                    chunk = str(update.get("chunk", "") or "")
                    if chunk:
                        await stream.thinking(
                            chunk,
                            source=self.name,
                            stage=stage,
                            metadata=merge_trace_metadata(
                                base_metadata,
                                {"trace_kind": "llm_chunk"},
                            ),
                        )
                    return
                if state == "complete":
                    was_streaming = update.get("streaming", False)
                    if not was_streaming:
                        response = str(update.get("response", "") or "")
                        if response:
                            await stream.thinking(
                                response,
                                source=self.name,
                                stage=stage,
                                metadata=merge_trace_metadata(
                                    base_metadata,
                                    {"trace_kind": "llm_output"},
                                ),
                            )
                    await stream.progress(
                        message="",
                        source=self.name,
                        stage=stage,
                        metadata=merge_trace_metadata(
                            base_metadata,
                            {"trace_kind": "call_status", "call_state": "complete"},
                        ),
                    )
                    return
                if state == "error":
                    await stream.error(
                        str(update.get("response", "") or "LLM call failed."),
                        source=self.name,
                        stage=stage,
                        metadata=merge_trace_metadata(
                            base_metadata,
                            {"trace_kind": "call_status", "call_state": "error"},
                        ),
                    )
                    return

            if event == "tool_call":
                await stream.tool_call(
                    tool_name=str(update.get("tool_name", "") or "tool"),
                    args=update.get("tool_args", {}) or {},
                    source=self.name,
                    stage=stage,
                    metadata=merge_trace_metadata(
                        base_metadata,
                        {"trace_kind": "tool_call"},
                    ),
                )
                return

            if event == "tool_result":
                state = str(update.get("state", "complete"))
                result = str(update.get("result", "") or "")
                if state == "error":
                    await stream.error(
                        result,
                        source=self.name,
                        stage=stage,
                        metadata=merge_trace_metadata(
                            base_metadata,
                            {"trace_kind": "tool_result"},
                        ),
                    )
                    return
                await stream.tool_result(
                    tool_name=str(update.get("tool_name", "") or "tool"),
                    result=result,
                    source=self.name,
                    stage=stage,
                    metadata=merge_trace_metadata(
                        base_metadata,
                        {"trace_kind": "tool_result"},
                    ),
                )

        return _trace_bridge
