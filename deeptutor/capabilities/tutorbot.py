from __future__ import annotations

from typing import Any

from deeptutor.capabilities.request_contracts import get_capability_request_schema
from deeptutor.contracts.bot_runtime_defaults import resolve_bot_runtime_defaults
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.services.question_followup import (
    build_question_followup_context_from_summary,
    extract_choice_summary_from_text,
)
from deeptutor.services.tutorbot import get_tutorbot_manager
from deeptutor.services.tutorbot.manager import BotConfig


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

        manager = get_tutorbot_manager()
        await manager.ensure_bot_running(bot_id, config=self._default_bot_config(context))

        chunks: list[str] = []
        turn_summary: dict[str, Any] = {
            "authority_applied": False,
            "exact_question": {},
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
            "default_tools": list(context.enabled_tools or []),
            "knowledge_bases": list(context.knowledge_bases or []),
        }
        if runtime_defaults:
            session_metadata["kb_aliases"] = list(runtime_defaults.supabase_kb_aliases or [])
        session_metadata["suppress_answer_reveal_on_generate"] = (
            self._suppress_answer_reveal_on_generate(context)
        )
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
            await stream.content(
                text,
                source=self.name,
                stage="responding",
                metadata={"execution_engine": "tutorbot_runtime"},
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
                mode=self._teaching_mode(context),
                session_key=session_key,
                session_metadata=session_metadata,
            )
            if response and not chunks:
                await stream.content(
                    response,
                    source=self.name,
                    stage="responding",
                    metadata={"execution_engine": "tutorbot_runtime"},
                )
            final_response = response or "".join(chunks)
            result_payload = {
                "response": final_response,
                "bot_id": bot_id,
                "execution_engine": "tutorbot_runtime",
                "authority_applied": turn_summary["authority_applied"],
                "exact_question": turn_summary["exact_question"],
            }
            parsed_summary = extract_choice_summary_from_text(final_response)
            if parsed_summary:
                result_payload["summary"] = parsed_summary
                result_payload["question_followup_context"] = build_question_followup_context_from_summary(
                    parsed_summary,
                    final_response,
                    reveal_answers=False,
                    reveal_explanations=False,
                )
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
    def _teaching_mode(context: UnifiedContext) -> str:
        hints = context.metadata.get("interaction_hints", {}) if isinstance(context.metadata, dict) else {}
        mode = (
            str(context.config_overrides.get("chat_mode") or "").strip().lower()
            or str((hints or {}).get("teaching_mode") or "").strip().lower()
        )
        if mode in {"fast", "deep"}:
            return mode
        return "smart"

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
        hints = context.metadata.get("interaction_hints", {}) if isinstance(context.metadata, dict) else {}
        if isinstance(hints, dict) and "suppress_answer_reveal_on_generate" in hints:
            return bool(hints.get("suppress_answer_reveal_on_generate"))
        return self._billing_source(context) == "wx_miniprogram"

    def _default_bot_config(self, context: UnifiedContext) -> BotConfig | None:
        bot_id = self._bot_id(context)
        if bot_id != "construction-exam-coach":
            return None
        return BotConfig(name="Construction Exam Coach")
