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
    annotate_submission_context_from_message,
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_result_summary,
    detect_answer_reveal_preference,
    extract_choice_result_summary_from_text,
    normalize_question_followup_context,
    resolve_submission_attempt,
)
from deeptutor.services.question_lifecycle_skills import (
    build_question_lifecycle_clarification_response,
    build_question_lifecycle_exam_catalog_response,
)
from deeptutor.services.query_intent import query_requires_current_info
from deeptutor.services.render_presentation import build_canonical_presentation
from deeptutor.services.security.tutorbot_guardrails import guard_tutorbot_output
from deeptutor.services.security.tool_access import filter_end_user_tools
from deeptutor.services.semantic_router import (
    apply_active_object_transition,
    build_active_object_from_question_context,
)
from deeptutor.services.citations import (
    CitationPolicy,
    answer_citations_enabled,
    apply_answer_citation_metadata,
)
from deeptutor.services.tutorbot import get_tutorbot_manager
from deeptutor.services.tutorbot.manager import BotConfig
from deeptutor.tutorbot.response_mode import (
    build_mode_execution_policy,
    normalize_requested_response_mode,
    resolve_requested_response_mode,
    select_response_mode,
)
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request


class TutorBotCapability(BaseCapability):
    manifest = CapabilityManifest(
        name="tutorbot",
        description="Full TutorBot runtime bridge backed by TutorBotManager.",
        stages=["responding"],
        tools_used=["rag", "web_search", "reason", "brainstorm", "paper_search"],
        cli_aliases=["tutorbot"],
        request_schema=get_capability_request_schema("chat"),
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        bot_id = self._bot_id(context)
        if not bot_id:
            await stream.error("TutorBot capability requires bot_id.", source=self.name)
            return
        runtime_defaults = resolve_bot_runtime_defaults(bot_id=bot_id)
        policy = self._mode_policy(context)
        response_mode = policy.effective_mode
        hide_generated_answers = self._should_hide_generated_answers(context)
        runtime_default_tools = list(runtime_defaults.default_tools or []) if runtime_defaults else []
        runtime_default_kbs = list(runtime_defaults.default_knowledge_bases or []) if runtime_defaults else []
        effective_knowledge_bases = list(context.knowledge_bases or []) or runtime_default_kbs

        manager = get_tutorbot_manager()
        await manager.ensure_bot_running(bot_id, config=self._default_bot_config(context))

        chunks: list[str] = []
        citation_sources: list[dict[str, Any]] = []
        turn_summary: dict[str, Any] = {
            "authority_applied": False,
            "exact_question": {},
            "rag_rounds": [],
            "rag_saturation": {},
        }
        citation_enabled = answer_citations_enabled()
        stream_public_deltas = (
            self._stream_public_deltas_enabled()
            and not hide_generated_answers
        )
        public_stream_buffer = ""
        streamed_public_text = ""
        public_stream_started = False
        public_stream_disabled = False
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
            "default_tools": self._session_default_tools(
                context,
                response_mode=response_mode,
                runtime_default_tools=runtime_default_tools,
                effective_knowledge_bases=effective_knowledge_bases,
            ),
            "knowledge_bases": effective_knowledge_bases,
            "answer_citations_required": citation_enabled,
            "requested_response_mode": policy.requested_mode,
            "selected_mode": policy.selected_mode,
            "effective_response_mode": policy.effective_mode,
            "response_mode_degrade_reason": policy.response_mode_degrade_reason,
            "response_mode_selection_reason": policy.selection_reason,
            "execution_path": policy.execution_path,
            "mode_execution_policy": {
                "max_tool_rounds": policy.max_tool_rounds,
                "allow_deep_stage": policy.allow_deep_stage,
                "response_density": policy.response_density,
                "latency_budget_ms": policy.latency_budget_ms,
                "knowledge_strategy": policy.knowledge_strategy,
                "workflow": policy.workflow,
                "model_fallback_allowed": policy.model_fallback_allowed,
                "web_search_allowed": policy.web_search_allowed,
                "execution_path": policy.execution_path,
            },
        }
        if policy.preferred_model:
            session_metadata["preferred_model"] = policy.preferred_model
        if runtime_defaults:
            session_metadata["kb_aliases"] = list(runtime_defaults.supabase_kb_aliases or [])
            if runtime_default_kbs:
                session_metadata["default_knowledge_bases"] = runtime_default_kbs
        session_metadata["suppress_answer_reveal_on_generate"] = (
            self._suppress_answer_reveal_on_generate(context)
        )
        if self._current_info_required(context):
            session_metadata["current_info_required"] = True
        general_knowledge_context_flag = context.config_overrides.get("general_knowledge_context")
        if isinstance(general_knowledge_context_flag, bool):
            session_metadata["general_knowledge_context"] = general_knowledge_context_flag
        for metadata_key in (
            "question_lifecycle_decision",
            "decision_source",
            "scene_confidence",
            "required_anchor_status",
            "exact_question_blocked_reason",
            "selected_skill_names",
            "llm_scene_candidate",
            "business_gate_result",
            "question_lifecycle_scene",
            "question_lifecycle_scene_source",
            "question_lifecycle_scene_confidence",
            "question_lifecycle_scene_reason",
            "question_lifecycle_skill_names",
            "question_lifecycle_clarification",
            "general_knowledge_context",
        ):
            if metadata_key in context.metadata:
                session_metadata[metadata_key] = context.metadata[metadata_key]
        memory_context = str(context.memory_context or "").strip()
        if memory_context:
            session_metadata["memory_context"] = memory_context
        compiled_learning_truth = (
            context.metadata.get("compiled_learning_truth")
            if isinstance(context.metadata, dict)
            else None
        )
        if isinstance(compiled_learning_truth, dict) and compiled_learning_truth:
            session_metadata["compiled_learning_truth"] = dict(compiled_learning_truth)
        turn_id = str((context.metadata or {}).get("turn_id") or "").strip()
        if turn_id:
            session_metadata["turn_id"] = turn_id
        if effective_knowledge_bases:
            session_metadata["default_kb"] = effective_knowledge_bases[0]
        if user_id:
            session_metadata["user_id"] = user_id
        active_object = (
            context.metadata.get("active_object")
            if isinstance(context.metadata, dict) and isinstance(context.metadata.get("active_object"), dict)
            else None
        )
        if active_object:
            session_metadata["active_object"] = dict(active_object)
        conversation_context_text = str(
            (context.metadata or {}).get("conversation_context_text") if isinstance(context.metadata, dict) else ""
        ).strip()
        if conversation_context_text:
            session_metadata["conversation_context_text"] = conversation_context_text

        exam_catalog_response = ""
        if str(context.metadata.get("question_lifecycle_scene") or "").strip() == "exam_catalog_query":
            exam_catalog_response = build_question_lifecycle_exam_catalog_response(
                self._raw_user_message(context),
                context.metadata if isinstance(context.metadata, dict) else {},
            )
        if exam_catalog_response:
            async with stream.stage(
                "responding",
                source=self.name,
                metadata={"execution_engine": "tutorbot_runtime", "bot_id": bot_id},
            ):
                content_metadata = {
                    "execution_engine": "tutorbot_runtime",
                    "call_kind": "exam_catalog_query",
                }
                if not citation_enabled:
                    await stream.content(
                        exam_catalog_response,
                        source=self.name,
                        stage="responding",
                        metadata=content_metadata,
                    )
                result_payload = {
                    "response": exam_catalog_response,
                    "bot_id": bot_id,
                    "execution_engine": "tutorbot_runtime",
                    "authority_applied": False,
                    "exact_question": {},
                    "rag_rounds": [],
                    "rag_saturation": {},
                    "requested_response_mode": policy.requested_mode,
                    "selected_mode": policy.selected_mode,
                    "effective_response_mode": policy.effective_mode,
                    "execution_path": "tutorbot_exam_catalog_query",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                    "reveal_answers": False,
                    "reveal_explanations": False,
                }
                for metadata_key in (
                    "question_lifecycle_decision",
                    "decision_source",
                    "scene_confidence",
                    "required_anchor_status",
                    "exact_question_blocked_reason",
                    "selected_skill_names",
                    "llm_scene_candidate",
                    "business_gate_result",
                    "question_lifecycle_scene",
                    "question_lifecycle_scene_source",
                    "question_lifecycle_scene_confidence",
                    "question_lifecycle_scene_reason",
                    "question_lifecycle_skill_names",
                    "question_lifecycle_clarification",
                    "active_object",
                    "release_id",
                    "git_sha",
                    "deployment_environment",
                    "grading_engine_version",
                    "v1_case_graded",
                    "score_authority",
                    "grading_rubric_provenance",
                    "case_grading_stream_mode",
                    "case_grading_adjudication_strategy",
                    "case_grading_adjudication_group_count",
                    "case_grading_adjudication_point_count",
                    "llm_stream_telemetry",
                ):
                    if metadata_key in session_metadata:
                        result_payload[metadata_key] = session_metadata[metadata_key]
                citation_metadata: dict[str, Any] = {}
                result_payload["response"] = apply_answer_citation_metadata(
                    citation_metadata,
                    response=str(result_payload.get("response") or ""),
                    sources=[],
                    policy=CitationPolicy(surface="student"),
                    enabled=citation_enabled,
                )
                result_payload.update(citation_metadata)
                if citation_enabled:
                    await stream.content(
                        str(result_payload["response"] or ""),
                        source=self.name,
                        stage="responding",
                        metadata=content_metadata,
                    )
                await stream.result(result_payload, source=self.name)
            return

        clarification_response = build_question_lifecycle_clarification_response(
            self._raw_user_message(context),
            str(context.metadata.get("exact_question_blocked_reason") or "").strip(),
        )
        if clarification_response:
            async with stream.stage(
                "responding",
                source=self.name,
                metadata={"execution_engine": "tutorbot_runtime", "bot_id": bot_id},
            ):
                content_metadata = {
                    "execution_engine": "tutorbot_runtime",
                    "call_kind": "lifecycle_clarification",
                }
                if not citation_enabled:
                    await stream.content(
                        clarification_response,
                        source=self.name,
                        stage="responding",
                        metadata=content_metadata,
                    )
                result_payload = {
                    "response": clarification_response,
                    "bot_id": bot_id,
                    "execution_engine": "tutorbot_runtime",
                    "authority_applied": False,
                    "exact_question": {},
                    "rag_rounds": [],
                    "rag_saturation": {},
                    "requested_response_mode": policy.requested_mode,
                    "selected_mode": policy.selected_mode,
                    "effective_response_mode": policy.effective_mode,
                    "execution_path": "tutorbot_lifecycle_clarification",
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                    "reveal_answers": False,
                    "reveal_explanations": False,
                }
                for metadata_key in (
                    "question_lifecycle_decision",
                    "decision_source",
                    "scene_confidence",
                    "required_anchor_status",
                    "exact_question_blocked_reason",
                    "selected_skill_names",
                    "llm_scene_candidate",
                    "business_gate_result",
                    "question_lifecycle_scene",
                    "question_lifecycle_scene_source",
                    "question_lifecycle_scene_confidence",
                    "question_lifecycle_scene_reason",
                    "question_lifecycle_skill_names",
                    "question_lifecycle_clarification",
                    "active_object",
                    "release_id",
                    "git_sha",
                    "deployment_environment",
                    "grading_engine_version",
                    "v1_case_graded",
                    "score_authority",
                    "grading_rubric_provenance",
                    "case_grading_stream_mode",
                    "case_grading_adjudication_strategy",
                    "case_grading_adjudication_group_count",
                    "case_grading_adjudication_point_count",
                    "llm_stream_telemetry",
                ):
                    if metadata_key in session_metadata:
                        result_payload[metadata_key] = session_metadata[metadata_key]
                citation_metadata: dict[str, Any] = {}
                result_payload["response"] = apply_answer_citation_metadata(
                    citation_metadata,
                    response=str(result_payload.get("response") or ""),
                    sources=[],
                    policy=CitationPolicy(surface="student"),
                    enabled=citation_enabled,
                )
                result_payload.update(citation_metadata)
                if citation_enabled:
                    await stream.content(
                        str(result_payload["response"] or ""),
                        source=self.name,
                        stage="responding",
                        metadata=content_metadata,
                    )
                await stream.result(result_payload, source=self.name)
            return

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
            nonlocal public_stream_buffer
            nonlocal streamed_public_text
            nonlocal public_stream_started
            nonlocal public_stream_disabled
            if not text:
                return
            chunks.append(text)
            if not stream_public_deltas or public_stream_disabled:
                return
            public_stream_buffer += text
            if self._should_block_public_delta_stream(public_stream_buffer):
                public_stream_disabled = True
                return
            if not public_stream_started:
                if not self._should_start_public_delta_stream(public_stream_buffer):
                    return
                public_stream_started = True
            delta = public_stream_buffer[len(streamed_public_text):]
            if not delta:
                return
            streamed_public_text += delta
            await stream.content(
                delta,
                source=self.name,
                stage="responding",
                metadata={
                    "execution_engine": "tutorbot_runtime",
                    "call_kind": "llm_final_response",
                    "streaming_delta": True,
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
                citation_sources.extend(item for item in sources if isinstance(item, dict))
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
            exact_state_summary = build_choice_result_summary_from_exact_question(
                turn_summary["exact_question"]
            )
            if turn_summary["authority_applied"]:
                display_result_summary = None
                state_result_summary = exact_state_summary
            else:
                state_result_summary = exact_state_summary
                # TutorBot free text is not grading authority. Only render
                # submit-able MCQ presentation when the answer key came from an
                # exact authoritative question source.
                display_result_summary = state_result_summary
            # Fix 2026-05-24 (post-merge with hermes edu-skills booster):
            # when the response is free-text MCQ-shaped but no exact_question
            # authority exists, parse the text into a presentation summary for
            # *rendering only*. Per contracts/capability.md §硬约束 26 this
            # summary MUST NOT feed question_followup_context / active_object
            # (those stay authority-gated below); it only powers presentation
            # blocks and lets _build_visible_response honor reveal_explanations
            # when the answer/explanation lives inside the LLM-emitted text.
            #
            # Post-review HIGH guard (code-review 2026-05-24): the free-text
            # parser MUST NOT run on authority responses. Authority text is
            # canonical and should follow the pre-existing
            # _strip_reference_sections path inside _build_visible_response.
            # Without this gate, _render_question_only_response would rebuild
            # authority output from a re-parsed summary and silently drop
            # authority-emitted framing. See
            # test_tutorbot_authority_response_not_rebuilt_by_freetext_parser.
            free_text_render_summary: dict[str, Any] | None = None
            if display_result_summary is None and not turn_summary["authority_applied"]:
                free_text_render_summary = extract_choice_result_summary_from_text(final_response)
            render_summary = display_result_summary or free_text_render_summary
            reveal_answers, reveal_explanations = self._reveal_reference_flags(context)
            exact_authority_revealed = bool(
                turn_summary["authority_applied"] and state_result_summary
            )
            state_reveal_answers = True if exact_authority_revealed else reveal_answers
            state_reveal_explanations = True if exact_authority_revealed else reveal_explanations
            visible_response = self._build_visible_response(
                context=context,
                final_response=final_response,
                parsed_result_summary=render_summary,
                reveal_answers=reveal_answers,
                reveal_explanations=reveal_explanations,
            )
            citation_metadata: dict[str, Any] = {}
            visible_response = apply_answer_citation_metadata(
                citation_metadata,
                response=visible_response,
                sources=citation_sources,
                policy=CitationPolicy(surface="student"),
                enabled=citation_enabled,
            )
            final_visible_delta = visible_response
            if streamed_public_text:
                if visible_response.startswith(streamed_public_text):
                    final_visible_delta = visible_response[len(streamed_public_text):]
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
                "requested_response_mode": policy.requested_mode,
                "selected_mode": policy.selected_mode,
                "effective_response_mode": policy.effective_mode,
                "execution_path": str(session_metadata.get("execution_path") or "").strip()
                or policy.execution_path,
                "exact_fast_path_hit": bool(session_metadata.get("exact_fast_path_hit", False)),
                "actual_tool_rounds": int(session_metadata.get("actual_tool_rounds") or 0),
                "reveal_answers": state_reveal_answers,
                "reveal_explanations": state_reveal_explanations,
            }
            result_payload.update(citation_metadata)
            # Propagate hermes question-lifecycle telemetry fields out of
            # session_metadata (set by tutorbot/agent/loop.py when the
            # question lifecycle builder ran). Diagnostic only; per
            # contracts/capability.md §硬约束 27 these must not feed
            # downstream routing or be student-visible.
            for metadata_key in (
                "question_lifecycle_decision",
                "decision_source",
                "scene_confidence",
                "required_anchor_status",
                "exact_question_blocked_reason",
                "selected_skill_names",
                "llm_scene_candidate",
                "business_gate_result",
                "question_lifecycle_scene",
                "skill_stack",
                "skill_trace",
                "loader_source",
                "skill_source_status",
                "rag_retrieval_degraded",
                "rag_retrieval_status",
                "rag_retrieval_error_type",
                "degraded_exact_answer_guard_applied",
                "degraded_mcq_grading_guard_applied",
                "grading_to_brain_loop",
                "learning_evidence_event_id",
                "release_id",
                "git_sha",
                "deployment_environment",
                "grading_engine_version",
                "v1_case_graded",
                "score_authority",
                "grading_rubric_provenance",
                "case_grading_stream_mode",
                "case_grading_adjudication_strategy",
                "case_grading_adjudication_group_count",
                "case_grading_adjudication_point_count",
                "luban_general_knowledge_context",
                "luban_general_knowledge_context_status",
                "llm_stream_telemetry",
                "presentation",
            ):
                if metadata_key in session_metadata:
                    result_payload[metadata_key] = session_metadata[metadata_key]
            # Grading-to-Brain 公开投影（与练题入口同口径）：PCP/intent 是服务端
            # 内部权威数据，只在 runtime/session metadata 供渲染与观测，不随
            # result 下发；next_best_action 只下发展示级字段。
            if "next_best_action" in session_metadata:
                from deeptutor.services.construction_grading.writeback import (
                    public_grading_to_brain_meta,
                )

                result_payload.update(
                    public_grading_to_brain_meta(
                        {"next_best_action": session_metadata.get("next_best_action")}
                    )
                )
            # Presentation gating — three orthogonal contracts (regression
            # matrix in tests/core/test_capabilities_runtime.py + tests/
            # capabilities/test_tutorbot_authority.py):
            #
            # 1. Practice generation requests (free-text MCQ) → emit a
            #    rendering-only presentation block; question_followup_context
            #    and active_object stay absent because TutorBot free text is
            #    not grading authority. See
            #    test_tutorbot_capability_emits_structured_mcq_summary_for_plain_text_generation.
            # 2. Non-practice chat with incidental MCQ-shaped text (e.g.
            #    "讲一下施工缝，顺便举个选择题例子") → no presentation;
            #    presentation would mislead the renderer into showing a
            #    question card. See
            #    test_tutorbot_does_not_turn_free_text_mcq_into_submitable_presentation.
            # 3. Exact-question authority responses flow through
            #    deep_question's main path; TutorBot must not re-render them
            #    as a presentation here. See
            #    test_tutorbot_capability_does_not_turn_exact_authority_answer_into_mcq_presentation.
            #
            # Per contracts/capability.md §硬约束 26 question_followup_context
            # + active_object remain authority-gated even when presentation is
            # emitted (Camp 1 above).
            is_practice_generation_request = looks_like_practice_generation_request(
                context.user_message
            )
            if (
                render_summary
                and is_practice_generation_request
                and not turn_summary["authority_applied"]
            ):
                presentation = build_canonical_presentation(
                    content=visible_response,
                    result_summary=render_summary,
                    reveal_answers=reveal_answers,
                    reveal_explanations=reveal_explanations,
                )
                if presentation:
                    result_payload["presentation"] = presentation
            if state_result_summary:
                # Authority-gated: question_followup_context + active_object
                # only emitted when exact_question authority is present.
                question_followup_context = build_question_followup_context_from_result_summary(
                    state_result_summary,
                    final_response,
                    reveal_answers=state_reveal_answers,
                    reveal_explanations=state_reveal_explanations,
                )
                question_followup_context = (
                    annotate_submission_context_from_message(
                        self._raw_user_message(context),
                        question_followup_context,
                    )
                    or question_followup_context
                )
                result_payload["question_followup_context"] = question_followup_context
                if result_payload["question_followup_context"]:
                    next_active_object = (
                        build_active_object_from_question_context(
                            result_payload["question_followup_context"],
                            source_turn_id=turn_id,
                            previous_active_object=active_object,
                        )
                        or {}
                    )
                    transitioned_active_object, transitioned_stack = apply_active_object_transition(
                        previous_active_object=active_object,
                        previous_suspended_object_stack=context.metadata.get("suspended_object_stack"),
                        turn_semantic_decision={
                            "relation_to_active_object": "switch_to_new_object",
                            "next_action": "route_to_grading",
                            "allowed_patch": ["set_active_object"],
                            "confidence": 1.0,
                            "reason": "exact-question authority emitted a new active question object.",
                            "target_object_ref": {},
                        },
                        resolved_active_object=next_active_object,
                    )
                    result_payload["active_object"] = transitioned_active_object or next_active_object
                    result_payload["suspended_object_stack"] = transitioned_stack
                    context.metadata["question_followup_context"] = dict(
                        result_payload["question_followup_context"]
                    )
                    context.metadata["active_object"] = dict(result_payload["active_object"])
                    context.metadata["suspended_object_stack"] = list(transitioned_stack)
            await stream.result(result_payload, source=self.name)

    @staticmethod
    def _stream_public_deltas_enabled() -> bool:
        raw = str(os.getenv("TUTORBOT_STREAM_PUBLIC_DELTAS", "1") or "1").strip().lower()
        return raw not in {"0", "false", "no", "off"}

    @staticmethod
    def _should_block_public_delta_stream(text: str) -> bool:
        source = str(text or "").strip()
        if not source:
            return False
        if guard_tutorbot_output(source).blocked:
            return True
        return TutorBotCapability._looks_like_internal_process_delta(source)

    @staticmethod
    def _should_start_public_delta_stream(text: str) -> bool:
        source = str(text or "").strip()
        if not source:
            return False
        if TutorBotCapability._should_block_public_delta_stream(source):
            return False
        compact = re.sub(r"\s+", "", source)
        if len(compact) >= 80:
            return True
        return "\n" in source or bool(
            re.match(r"^(?:#{1,6}\s*)?(?:最终答案|结论|第\s*[0-9一二两三四五六七八九十]+题)", source)
        )

    @staticmethod
    def _looks_like_internal_process_delta(text: str) -> bool:
        compact = re.sub(r"[\s，,。.!！?？：:；;]+", "", str(text or "").strip())
        lower = compact.lower()
        if not compact or len(compact) > 220:
            return False
        if any(marker in compact for marker in ("采分点", "易错点", "核心考点", "自查", "答案", "判断", "第1题", "第2题")):
            return False
        if any(marker in lower for marker in ("skill", "reference", "agents.md", "soul.md")):
            return True
        return bool(
            re.match(r"^(好的|好|可以)?(我)?先(看|看看|查看|检索|查询|结合|梳理|分析|加载|读取|调取)", compact)
            or re.match(r"^(好的|好|可以)?我(先|来)(看|查看|检索|查询|结合|梳理|分析|加载|读取|调取)", compact)
            or re.match(r"^正在(查看|检索|查询|加载|读取|调取|分析)", compact)
        )

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
        return TutorBotCapability._mode_policy(context).requested_mode

    @staticmethod
    def _mode_policy(context: UnifiedContext):
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        hints = (
            metadata.get("interaction_hints")
            if isinstance(metadata.get("interaction_hints"), dict)
            else {}
        )
        requested_mode = normalize_requested_response_mode(
            metadata.get("requested_response_mode")
            or resolve_requested_response_mode(
                chat_mode=context.config_overrides.get("chat_mode"),
                interaction_hints=hints if isinstance(hints, dict) else None,
            )
        )
        selected_mode = normalize_requested_response_mode(
            metadata.get("selected_mode") or context.config_overrides.get("chat_mode")
        )
        selection_reason = str(
            metadata.get("response_mode_selection_reason")
            or (hints.get("response_mode_selection_reason") if isinstance(hints, dict) else "")
            or ""
        ).strip()
        if selected_mode == "smart":
            selected_mode, inferred_reason = select_response_mode(
                requested_mode,
                user_message=context.user_message,
                interaction_hints=hints if isinstance(hints, dict) else None,
                has_active_object=TutorBotCapability._active_object_requires_deep(context),
            )
            if not selection_reason:
                selection_reason = inferred_reason
        return build_mode_execution_policy(
            requested_mode,
            selected_mode=selected_mode,
            selection_reason=selection_reason,
        )

    @staticmethod
    def _active_object_requires_deep(context: UnifiedContext) -> bool:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        active_object = metadata.get("active_object") if isinstance(metadata.get("active_object"), dict) else {}
        if not active_object:
            return False
        object_type = str(active_object.get("object_type") or "").strip()
        if object_type == "open_chat_topic":
            return False

        followup_context = normalize_question_followup_context(
            metadata.get("question_followup_context")
            if isinstance(metadata.get("question_followup_context"), dict)
            else None
        )
        if object_type in {"question_set", "single_question"} and followup_context:
            if looks_like_practice_generation_request(context.user_message):
                return False
            _, submission = resolve_submission_attempt(context.user_message, followup_context)
            if submission:
                return False
            text = str(context.user_message or "").strip()
            if (
                any(marker in text for marker in ("我答", "我选", "批改", "判分", "打分"))
                and re.search(r"第\s*[0-9一二两三四五六七八九十]+\s*[题问]", text)
            ):
                return False
        return True

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @classmethod
    def _session_default_tools(
        cls,
        context: UnifiedContext,
        *,
        response_mode: str,
        runtime_default_tools: list[str] | None = None,
        effective_knowledge_bases: list[str] | None = None,
    ) -> list[str]:
        enabled_tools = filter_end_user_tools(context.enabled_tools or [])
        runtime_tools = filter_end_user_tools(runtime_default_tools or [])
        knowledge_bases = list(effective_knowledge_bases or [])
        if response_mode == "fast":
            tools: list[str] = []
            if "rag" in enabled_tools or "rag" in runtime_tools or knowledge_bases:
                tools.append("rag")
            if "web_search" in enabled_tools:
                tools.append("web_search")
            return cls._dedupe_strings(tools)
        return cls._dedupe_strings([*enabled_tools, *runtime_tools])

    @staticmethod
    def _current_info_required(context: UnifiedContext) -> bool:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        if bool(metadata.get("current_info_required")):
            return True
        hints = metadata.get("interaction_hints") if isinstance(metadata.get("interaction_hints"), dict) else {}
        if bool(hints.get("current_info_required")):
            return True
        enabled_tools = {
            str(tool or "").strip()
            for tool in (context.enabled_tools or [])
        }
        return "web_search" in enabled_tools and query_requires_current_info(context.user_message)

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

    @staticmethod
    def _raw_user_message(context: UnifiedContext) -> str:
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        raw = str(metadata.get("raw_user_message") or "").strip()
        return raw or str(context.user_message or "").strip()

    def _suppress_answer_reveal_on_generate(self, context: UnifiedContext) -> bool:
        explicit_preference = detect_answer_reveal_preference(context.user_message)
        if explicit_preference is False:
            return True
        if explicit_preference is True:
            return False
        hints = context.metadata.get("interaction_hints", {}) if isinstance(context.metadata, dict) else {}
        if isinstance(hints, dict) and "suppress_answer_reveal_on_generate" in hints:
            return bool(hints.get("suppress_answer_reveal_on_generate"))
        return self._billing_source(context) == "wx_miniprogram"

    @staticmethod
    def _reveal_reference_flags(context: UnifiedContext) -> tuple[bool, bool]:
        overrides = context.config_overrides if isinstance(context.config_overrides, dict) else {}
        explicit_preference = detect_answer_reveal_preference(context.user_message)
        reveal_answers = bool(overrides.get("reveal_answers", False)) or explicit_preference is True
        if "reveal_explanations" in overrides:
            reveal_explanations = bool(overrides.get("reveal_explanations"))
        else:
            reveal_explanations = reveal_answers
        return reveal_answers, reveal_explanations

    def _should_hide_generated_answers(self, context: UnifiedContext) -> bool:
        reveal_answers, reveal_explanations = self._reveal_reference_flags(context)
        if reveal_answers or reveal_explanations:
            return False
        if not self._suppress_answer_reveal_on_generate(context):
            return False
        return looks_like_practice_generation_request(context.user_message)

    def _build_visible_response(
        self,
        *,
        context: UnifiedContext,
        final_response: str,
        parsed_result_summary: dict[str, Any] | None,
        reveal_answers: bool = False,
        reveal_explanations: bool = False,
    ) -> str:
        if reveal_answers or reveal_explanations:
            if parsed_result_summary:
                return (
                    self._render_question_response(
                        parsed_result_summary,
                        reveal_answers=reveal_answers,
                        reveal_explanations=reveal_explanations,
                    )
                    or final_response
                )
            if reveal_answers and reveal_explanations:
                return final_response
            return self._strip_reference_sections(final_response) or final_response
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
        return TutorBotCapability._render_question_response(
            summary,
            reveal_answers=False,
            reveal_explanations=False,
        )

    @staticmethod
    def _render_question_response(
        summary: dict[str, Any],
        *,
        reveal_answers: bool = False,
        reveal_explanations: bool = False,
    ) -> str:
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
            answer = str(qa_pair.get("correct_answer", "") or "").strip()
            explanation = str(
                qa_pair.get("explanation")
                or qa_pair.get("knowledge_context")
                or ""
            ).strip()
            if reveal_answers and answer:
                lines.append(f"**答案**：{answer}")
            if reveal_explanations and explanation:
                lines.append(f"**解析**：{explanation}")
            lines.append("")
        return "\n".join(lines).strip()

    def _default_bot_config(self, context: UnifiedContext) -> BotConfig | None:
        bot_id = self._bot_id(context)
        if bot_id != "construction-exam-coach":
            return None
        return BotConfig(name="Construction Exam Coach")
