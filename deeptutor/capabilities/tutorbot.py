from __future__ import annotations

import os
import re
from typing import Any

from deeptutor.capabilities.request_contracts import get_capability_request_schema
from deeptutor.contracts.bot_runtime_defaults import resolve_bot_runtime_defaults
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.question_followup import (
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_presentation,
    build_question_followup_context_from_result_summary,
    detect_answer_reveal_preference,
    extract_choice_result_summary_from_text,
)
from deeptutor.services.render_presentation import build_canonical_presentation
from deeptutor.services.tutorbot import get_tutorbot_manager
from deeptutor.services.tutorbot.manager import BotConfig
from deeptutor.tutorbot.response_mode import (
    build_mode_execution_policy,
    resolve_requested_response_mode,
)
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request


def _stream_public_deltas_enabled() -> bool:
    raw = str(os.getenv("TUTORBOT_STREAM_PUBLIC_DELTAS", "1") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class TutorBotCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="tutorbot",
        description="Full TutorBot runtime bridge backed by TutorBotManager.",
        stages=["responding"],
        tools_used=["rag", "web_search", "code_execution", "reason", "brainstorm", "paper_search"],
        cli_aliases=["tutorbot"],
        request_schema=get_capability_request_schema("chat"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        bot_id = self._bot_id(context)
        if not bot_id:
            await stream.error("TutorBot capability requires bot_id.", source=self.name)
            return
        runtime_defaults = resolve_bot_runtime_defaults(bot_id=bot_id)
        requested_mode = self._response_mode(context)
        policy = build_mode_execution_policy(requested_mode)
        teaching_mode = policy.effective_mode
        hide_generated_answers = self._should_hide_generated_answers(context)

        manager = get_tutorbot_manager()
        await manager.ensure_bot_running(bot_id, config=self._default_bot_config(context))

        chunks: list[str] = []
        streamed_chunks: list[str] = []
        turn_summary: dict[str, Any] = {
            "authority_applied": False,
            "exact_question": {},
            "rag_rounds": [],
            "rag_saturation": {},
        }
        user_id = self._billing_user_id(context)
        conversation_id = str(context.session_id or "").strip() or "web"
        session_key = manager.build_chat_session_key(
            bot_id,
            conversation_id,
            user_id=user_id or None,
        )
        session_metadata = {
            "conversation_id": conversation_id,
            "session_id": conversation_id,
            "source": self._billing_source(context) or "ws",
            "title": manager._infer_conversation_title(context.user_message),
            "bot_id": bot_id,
            "default_tools": self._session_default_tools(context, teaching_mode=teaching_mode),
            "knowledge_bases": list(context.knowledge_bases or []),
            "requested_response_mode": policy.requested_mode,
            "effective_response_mode": policy.effective_mode,
            "response_mode_degrade_reason": policy.response_mode_degrade_reason,
            "teaching_mode": policy.effective_mode,
            "mode_execution_policy": {
                "max_tool_rounds": policy.max_tool_rounds,
                "allow_deep_stage": policy.allow_deep_stage,
                "response_density": policy.response_density,
                "latency_budget_ms": policy.latency_budget_ms,
            },
        }
        if runtime_defaults:
            session_metadata["kb_aliases"] = list(runtime_defaults.supabase_kb_aliases or [])
        session_metadata["suppress_answer_reveal_on_generate"] = (
            self._suppress_answer_reveal_on_generate(context)
        )
        if self._current_info_required(context):
            session_metadata["current_info_required"] = True
        turn_id = str((context.metadata or {}).get("turn_id") or "").strip()
        if turn_id:
            session_metadata["turn_id"] = turn_id
        if context.knowledge_bases:
            session_metadata["default_kb"] = context.knowledge_bases[0]
        if user_id:
            session_metadata["user_id"] = user_id

        async def _on_progress(text: str) -> None:
            if not str(text or "").strip():
                return
            await stream.progress(
                str(text),
                source=self.name,
                stage="responding",
                metadata={"execution_engine": "tutorbot_runtime"},
            )

        async def _on_content_delta(text: str) -> None:
            if not text:
                return
            chunks.append(text)
            if hide_generated_answers or not _stream_public_deltas_enabled():
                return
            streamed_chunks.append(text)
            await stream.content(
                text,
                source=self.name,
                stage="responding",
                metadata={
                    "execution_engine": "tutorbot_runtime",
                    "call_kind": "llm_stream_delta",
                },
            )

        async def _on_tool_call(tool_name: str, args: dict[str, Any]) -> None:
            await stream.tool_call(
                tool_name,
                args,
                source=self.name,
                stage="responding",
                metadata={"execution_engine": "tutorbot_runtime"},
            )

        async def _on_tool_result(
            tool_name: str,
            result: str,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            merged_metadata = {"execution_engine": "tutorbot_runtime", **dict(metadata or {})}
            if merged_metadata.get("authority_applied") is True:
                turn_summary["authority_applied"] = True
            if isinstance(merged_metadata.get("exact_question"), dict) and merged_metadata.get("exact_question"):
                turn_summary["exact_question"] = dict(merged_metadata["exact_question"])
            if isinstance(merged_metadata.get("rag_rounds"), list) and merged_metadata.get("rag_rounds"):
                turn_summary["rag_rounds"] = [
                    dict(item) for item in merged_metadata["rag_rounds"] if isinstance(item, dict)
                ]
            if isinstance(merged_metadata.get("rag_saturation"), dict) and merged_metadata.get("rag_saturation"):
                turn_summary["rag_saturation"] = dict(merged_metadata["rag_saturation"])
            await stream.tool_result(
                tool_name,
                result,
                source=self.name,
                stage="responding",
                metadata=merged_metadata,
            )
            sources = metadata.get("sources") if isinstance(metadata, dict) else None
            if isinstance(sources, list) and sources:
                await stream.sources(
                    sources,
                    source=self.name,
                    stage="responding",
                    metadata=merged_metadata,
                )

        async with stream.stage(
            "responding",
            source=self.name,
            metadata={"execution_engine": "tutorbot_runtime", "bot_id": bot_id},
        ):
            response = await manager.send_message(
                bot_id=bot_id,
                content=context.user_message,
                chat_id=conversation_id,
                on_progress=_on_progress,
                on_content_delta=_on_content_delta,
                on_tool_call=_on_tool_call,
                on_tool_result=_on_tool_result,
                mode=policy.effective_mode,
                session_key=session_key,
                session_metadata=session_metadata,
            )
            final_response = response or "".join(chunks)
            parsed_result_summary = build_choice_result_summary_from_exact_question(
                turn_summary["exact_question"]
            ) or extract_choice_result_summary_from_text(final_response)
            visible_response = self._build_visible_response(
                context=context,
                final_response=final_response,
                parsed_result_summary=parsed_result_summary,
            )
            streamed_visible_response = "".join(streamed_chunks)
            final_visible_delta = visible_response
            if streamed_visible_response:
                if visible_response.startswith(streamed_visible_response):
                    final_visible_delta = visible_response[len(streamed_visible_response):]
                else:
                    final_visible_delta = ""
            if final_visible_delta:
                await stream.content(
                    final_visible_delta,
                    source=self.name,
                    stage="responding",
                    metadata={
                        "execution_engine": "tutorbot_runtime",
                        "call_kind": "llm_final_response",
                    },
                )
            result_payload = {
                "response": visible_response,
                "bot_id": bot_id,
                "execution_engine": "tutorbot_runtime",
                "authority_applied": turn_summary["authority_applied"],
                "exact_question": turn_summary["exact_question"],
                "rag_rounds": turn_summary["rag_rounds"],
                "rag_saturation": turn_summary["rag_saturation"],
            }
            if parsed_result_summary:
                presentation = build_canonical_presentation(
                    content=visible_response,
                    result_summary=parsed_result_summary,
                )
                result_payload["question_followup_context"] = (
                    build_question_followup_context_from_presentation(
                        presentation,
                        final_response,
                        reveal_answers=False,
                        reveal_explanations=False,
                    )
                    or build_question_followup_context_from_result_summary(
                        parsed_result_summary,
                        final_response,
                        reveal_answers=False,
                        reveal_explanations=False,
                    )
                )
                if presentation:
                    result_payload["presentation"] = presentation
            await stream.result(result_payload, source=self.name)

    @staticmethod
    def _bot_id(context: UnifiedContext) -> str:
        for container in (context.config_overrides, context.metadata):
            if not isinstance(container, dict):
                continue
            value = str(container.get("bot_id") or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _response_mode(context: UnifiedContext) -> str:
        hints = context.metadata.get("interaction_hints", {}) if isinstance(context.metadata, dict) else {}
        return resolve_requested_response_mode(
            chat_mode=context.config_overrides.get("chat_mode"),
            interaction_hints=hints if isinstance(hints, dict) else None,
        )

    @staticmethod
    def _session_default_tools(context: UnifiedContext, *, teaching_mode: str) -> list[str]:
        return list(context.enabled_tools or [])

    @staticmethod
    def _current_info_required(context: UnifiedContext) -> bool:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        if bool(metadata.get("current_info_required")):
            return True
        hints = metadata.get("interaction_hints") if isinstance(metadata.get("interaction_hints"), dict) else {}
        return bool(hints.get("current_info_required"))

    @staticmethod
    def _billing_user_id(context: UnifiedContext) -> str:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        billing_context = metadata.get("billing_context") if isinstance(metadata.get("billing_context"), dict) else {}
        return str(billing_context.get("user_id") or "").strip()

    @staticmethod
    def _billing_source(context: UnifiedContext) -> str:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        billing_context = metadata.get("billing_context") if isinstance(metadata.get("billing_context"), dict) else {}
        return str(billing_context.get("source") or "").strip().lower()

    def _suppress_answer_reveal_on_generate(self, context: UnifiedContext) -> bool:
        explicit_preference = detect_answer_reveal_preference(context.user_message)
        if explicit_preference is False:
            return True
        hints = context.metadata.get("interaction_hints", {}) if isinstance(context.metadata, dict) else {}
        if isinstance(hints, dict) and "suppress_answer_reveal_on_generate" in hints:
            return bool(hints.get("suppress_answer_reveal_on_generate"))
        return self._billing_source(context) == "wx_miniprogram"

    def _should_hide_generated_answers(self, context: UnifiedContext) -> bool:
        if not self._suppress_answer_reveal_on_generate(context):
            return False
        return looks_like_practice_generation_request(context.user_message)

    def _build_visible_response(
        self,
        *,
        context: UnifiedContext,
        final_response: str,
        parsed_result_summary: dict[str, Any] | None,
    ) -> str:
        if not self._should_hide_generated_answers(context):
            return final_response
        if parsed_result_summary:
            return self._render_question_only_response(parsed_result_summary) or final_response
        return self._strip_reference_sections(final_response) or final_response

    @staticmethod
    def _strip_reference_sections(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        marker_re = re.compile(
            r"^\s*(?:\*\*)?(?:answer|explanation|标准答案|参考答案|正确答案|答案|解析)(?:\*\*)?\s*[:：]",
            re.IGNORECASE,
        )
        lines = raw.splitlines()
        kept: list[str] = []
        for line in lines:
            if marker_re.match(line):
                break
            kept.append(line)
        return "\n".join(kept).rstrip()

    @staticmethod
    def _render_question_only_response(summary: dict[str, Any]) -> str:
        results = summary.get("results", []) if isinstance(summary, dict) else []
        if not isinstance(results, list) or not results:
            return ""

        lines: list[str] = []
        for idx, item in enumerate(results, 1):
            qa_pair = item.get("qa_pair", {}) if isinstance(item, dict) else {}
            question = str(qa_pair.get("question", "") or "").strip()
            options = qa_pair.get("options")
            if not question:
                continue
            lines.append(f"**第{idx}题**")
            lines.append(question)
            if isinstance(options, dict):
                for key, value in options.items():
                    option_key = str(key or "").strip().upper()
                    option_text = str(value or "").strip()
                    if option_key and option_text:
                        lines.append(f"{option_key}. {option_text}")
            lines.append("")
        return "\n".join(lines).strip()

    def _default_bot_config(self, context: UnifiedContext) -> BotConfig | None:
        bot_id = self._bot_id(context)
        if bot_id != "construction-exam-coach":
            return None
        return BotConfig(name="Construction Exam Coach")
