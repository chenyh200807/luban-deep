from __future__ import annotations

import os
import re
from typing import Any

from deeptutor.capabilities.request_contracts import get_capability_request_schema
from deeptutor.contracts.bot_runtime_defaults import resolve_bot_runtime_defaults
from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus
from deeptutor.core.terminal_result_assembler import TerminalResultAssembler
from deeptutor.services.citations import (
    CitationPolicy,
    answer_citations_enabled,
    apply_answer_citation_metadata,
)
from deeptutor.services.construction_grading.case_output_policy import (
    copy_current_case_grading_turn_metadata,
)
from deeptutor.services.query_intent import query_requires_current_info
from deeptutor.services.question_followup import (
    annotate_submission_context_from_message,
    build_canonical_represent_response,
    build_choice_result_summary_from_exact_question,
    build_question_followup_context_from_presentation,
    build_question_followup_context_from_result_summary,
    detect_answer_reveal_preference,
    extract_choice_result_summary_from_text,
    normalize_question_followup_context,
    requested_question_item_index,
    resolve_reveal_decision,
    resolve_submission_attempt,
    should_block_unanswered_reference_reveal,
)
from deeptutor.services.question_lifecycle_skills import (
    build_question_lifecycle_clarification_response,
    build_question_lifecycle_exam_catalog_response,
    build_question_lifecycle_study_assistant_degraded_response,
    study_assistant_has_learning_evidence,
)
from deeptutor.services.render_presentation import build_canonical_presentation
from deeptutor.services.security.tool_access import filter_end_user_tools
from deeptutor.services.security.tutorbot_guardrails import guard_tutorbot_output
from deeptutor.services.active_object_builder import (
    extract_question_context_from_active_object,
)
from deeptutor.services.semantic_router import (
    apply_active_object_transition,
    build_active_object_from_question_context,
)
from deeptutor.services.tutorbot import get_tutorbot_manager
from deeptutor.services.tutorbot.manager import BotConfig
from deeptutor.tutorbot.response_mode import (
    active_object_requires_deep_mode,
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

        async def _emit_lifecycle_terminal_response(
            response_text: str,
            *,
            execution_path: str,
            call_kind: str,
            extra_payload: dict[str, Any] | None = None,
        ) -> None:
            async with stream.stage(
                "responding",
                source=self.name,
                metadata={"execution_engine": "tutorbot_runtime", "bot_id": bot_id},
            ):
                content_metadata = {
                    "execution_engine": "tutorbot_runtime",
                    "call_kind": call_kind,
                }
                if not citation_enabled:
                    await stream.content(
                        response_text,
                        source=self.name,
                        stage="responding",
                        metadata=content_metadata,
                    )
                result_payload = {
                    "response": response_text,
                    "bot_id": bot_id,
                    "execution_engine": "tutorbot_runtime",
                    "authority_applied": False,
                    "exact_question": {},
                    "rag_rounds": [],
                    "rag_saturation": {},
                    "requested_response_mode": policy.requested_mode,
                    "selected_mode": policy.selected_mode,
                    "effective_response_mode": policy.effective_mode,
                    "execution_path": execution_path,
                    "exact_fast_path_hit": False,
                    "actual_tool_rounds": 0,
                    "reveal_answers": False,
                    "reveal_explanations": False,
                    **dict(extra_payload or {}),
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
                    "llm_stream_telemetry",
                ):
                    if metadata_key in session_metadata:
                        result_payload[metadata_key] = session_metadata[metadata_key]
                copy_current_case_grading_turn_metadata(session_metadata, result_payload)
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
                # Control-plane Task 5 Slice 3: the lifecycle degraded terminal
                # RESULT frame is owned by TerminalResultAssembler (single
                # contentful visible-output authority). Behaviour-preserving:
                # build_event reproduces stream.result framing byte-identically
                # (type=RESULT / source / stage="" / visibility="public" /
                # merge_trace_metadata copy). Reveal flags pass through
                # result_payload unchanged — the assembler only emits.
                await stream.emit(
                    TerminalResultAssembler.build_event(
                        source=self.name,
                        metadata=result_payload,
                    )
                )

        exam_catalog_response = ""
        if str(context.metadata.get("question_lifecycle_scene") or "").strip() == "exam_catalog_query":
            exam_catalog_response = build_question_lifecycle_exam_catalog_response(
                self._raw_user_message(context),
                context.metadata if isinstance(context.metadata, dict) else {},
            )
        if exam_catalog_response:
            await _emit_lifecycle_terminal_response(
                exam_catalog_response,
                execution_path="tutorbot_exam_catalog_query",
                call_kind="exam_catalog_query",
            )
            return

        clarification_response = build_question_lifecycle_clarification_response(
            self._raw_user_message(context),
            str(context.metadata.get("exact_question_blocked_reason") or "").strip(),
        )
        if clarification_response:
            await _emit_lifecycle_terminal_response(
                clarification_response,
                execution_path="tutorbot_lifecycle_clarification",
                call_kind="lifecycle_clarification",
            )
            return

        study_assistant_degraded_response = ""
        if (
            str(context.metadata.get("question_lifecycle_scene") or "").strip() == "study_assistant"
            and not study_assistant_has_learning_evidence(
                context.metadata if isinstance(context.metadata, dict) else {}
            )
        ):
            study_assistant_degraded_response = build_question_lifecycle_study_assistant_degraded_response(
                self._raw_user_message(context),
                context.metadata if isinstance(context.metadata, dict) else {},
            )
        if study_assistant_degraded_response:
            await _emit_lifecycle_terminal_response(
                study_assistant_degraded_response,
                execution_path="tutorbot_study_assistant_degraded_no_evidence",
                call_kind="study_assistant_degraded_no_evidence",
                extra_payload={
                    "study_assistant_degraded_no_evidence": True,
                    "study_assistant_authority": "construction-study-assistant",
                },
            )
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

        # SEV anti-cheat — deterministic short-circuit for unanswered-question
        # references. When the learner points at a still-unattempted question
        # inside a batch ("第2题怎么做"), the free-text LLM agent loop would solve
        # it from model knowledge and leak the answer. Prompt-level soft
        # instructions proved insufficient in live eval (2/3 leaked). The only
        # reliable fix is to NOT route this turn through a free LLM at all:
        # re-present the referenced question deterministically (stem + options,
        # answer stays hidden in grading_key) plus a fixed nudge to attempt it
        # first. Authority reused, not rebuilt — should_block_unanswered_reference_reveal
        # + requested_question_item_index are the existing single authorities for
        # "is this an unanswered reference" and "which item"; zero new adjudication,
        # no answer regex/blocklist. The safety belt (already-attempted question,
        # answer concession, topic switch) is preserved because all three make
        # should_block_unanswered_reference_reveal return False / requested index
        # None, so this block does not fire for them.
        unanswered_reference_response = self._build_unanswered_reference_response(context)
        if unanswered_reference_response is not None:
            # Control-plane: the deterministic RESULT frame is owned by
            # TerminalResultAssembler (single contentful visible-output authority,
            # via _emit_lifecycle_terminal_response). Do NOT emit a raw stream.result
            # here — that would register a second visible_result writer. Reuse the
            # lifecycle terminal helper (same path as exam_catalog / clarification).
            await _emit_lifecycle_terminal_response(
                unanswered_reference_response,
                execution_path="tutorbot_unanswered_reference_reprompt",
                call_kind="unanswered_reference_reprompt",
            )
            return

        # M4(i) 方案②: deterministic canonical re-present of an active single MCQ.
        # When the learner asks to re-show / reshuffle the active question, the
        # free LLM would emit a divergent option surface (letters reshuffled) that
        # state_snapshot — and the prose grader — never capture, so a subsequent
        # letter answer is graded against the original surface (倒诬). Re-present
        # deterministically from the single authority (active_object.state_snapshot,
        # original order) instead of the free LLM, so presented surface == grading
        # surface. Fail-safe: build_canonical_represent_response returns None unless
        # an active single MCQ + an explicit re-present marker are both present, so
        # answer / explanation / new-question turns fall through unchanged. Sibling
        # of the unanswered-reference anti-cheat; reuses the same terminal helper.
        canonical_represent_response = build_canonical_represent_response(
            active_object,
            context.user_message,
            question_context=(
                context.metadata.get("question_followup_context")
                if isinstance(context.metadata, dict)
                else None
            ),
        )
        if canonical_represent_response is not None:
            await _emit_lifecycle_terminal_response(
                canonical_represent_response,
                execution_path="tutorbot_canonical_mcq_represent",
                call_kind="canonical_mcq_represent",
            )
            return

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
                raw_user_content=self._raw_user_message(context),
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
                # ② content-truth review loop (observe-only): export the low-confidence
                # regulation claims from session metadata into the result event so the
                # terminal observation event + offline review agent can see them. Same
                # diagnostic-only channel as the degraded_* flags above; never routes.
                "content_truth_guard_applied",
                "content_truth_low_confidence_claims",
                "release_id",
                "git_sha",
                "deployment_environment",
                "luban_general_knowledge_context",
                "luban_general_knowledge_context_status",
                "llm_stream_telemetry",
                "presentation",
            ):
                if metadata_key in session_metadata:
                    result_payload[metadata_key] = session_metadata[metadata_key]
            copy_current_case_grading_turn_metadata(session_metadata, result_payload)
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
                # 收权（inline 多题集注册病）：inline 自由文本出题（含多题）必须经
                # 唯一 builder build_active_object_from_question_context 注册成可
                # resolve 的 question_set active_object（items[]），与 deep_question
                # 出题链路同一 writer / 同一 persist（turn_runtime set_active_object）。
                # 否则下一轮学员作答在 deep_question 端绑不到题面 → "你还没作答" 拒判。
                # 注册题面 ≠ 判分权威：§硬约束 26 只禁 TutorBot 用 free text 自行判分 /
                # 补官方扣分理由；分值/扣分仍只来自鲁班 V1 / rubric / 开放世界裁决。
                # exact-question authority 命中时由下方 state_result_summary 块注册
                # （更高权威），故此处只在无 exact 摘要时兜底，避免双写。
                if presentation and not state_result_summary:
                    practice_followup_context = (
                        build_question_followup_context_from_presentation(
                            presentation,
                            final_response,
                            reveal_answers=reveal_answers,
                            reveal_explanations=reveal_explanations,
                        )
                    )
                    if practice_followup_context:
                        practice_active_object = (
                            build_active_object_from_question_context(
                                practice_followup_context,
                                source_turn_id=turn_id,
                                previous_active_object=active_object,
                            )
                            or {}
                        )
                        (
                            practice_transitioned_active_object,
                            practice_transitioned_stack,
                        ) = apply_active_object_transition(
                            previous_active_object=active_object,
                            previous_suspended_object_stack=context.metadata.get(
                                "suspended_object_stack"
                            ),
                            turn_semantic_decision={
                                "relation_to_active_object": "switch_to_new_object",
                                "next_action": "route_to_grading",
                                "allowed_patch": ["set_active_object"],
                                "confidence": 1.0,
                                "reason": "inline practice generation registered a new question_set active object.",
                                "target_object_ref": {},
                            },
                            resolved_active_object=practice_active_object,
                        )
                        result_payload["question_followup_context"] = practice_followup_context
                        result_payload["active_object"] = (
                            practice_transitioned_active_object or practice_active_object
                        )
                        result_payload["suspended_object_stack"] = practice_transitioned_stack
                        context.metadata["question_followup_context"] = dict(
                            practice_followup_context
                        )
                        context.metadata["active_object"] = dict(result_payload["active_object"])
                        context.metadata["suspended_object_stack"] = list(
                            practice_transitioned_stack
                        )
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
            # Control-plane Task 5 Slice 3: the main terminal RESULT frame is
            # owned by TerminalResultAssembler (single contentful visible-output
            # authority). Behaviour-preserving: build_event reproduces
            # stream.result framing byte-identically (type=RESULT / source /
            # stage="" / visibility="public" / merge_trace_metadata copy). The
            # reveal flags + presentation + question_followup_context + active_object
            # blocks already live in result_payload (capability-owned in this
            # slice) — the assembler only emits, it never decides reveal.
            await stream.emit(
                TerminalResultAssembler.build_event(
                    source=self.name,
                    metadata=result_payload,
                )
            )

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
                has_active_object=active_object_requires_deep_mode(
                    active_object=metadata.get("active_object")
                    if isinstance(metadata.get("active_object"), dict)
                    else None,
                    followup_context=metadata.get("question_followup_context")
                    if isinstance(metadata.get("question_followup_context"), dict)
                    else None,
                    user_message=context.user_message,
                ),
            )
            if not selection_reason:
                selection_reason = inferred_reason
        return build_mode_execution_policy(
            requested_mode,
            selected_mode=selected_mode,
            selection_reason=selection_reason,
        )

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
        # Single reveal authority (Task 5 Slice 4): construct the facets and read
        # the adjudicated decision from resolve_reveal_decision. RED-LINE FIX —
        # the old branch returned (True, True) the instant preference was True,
        # BEFORE the unanswered-block check, leaking answers on un-attempted
        # practice questions. The resolver now routes preference=True through the
        # unanswered-block red line.
        overrides = context.config_overrides if isinstance(context.config_overrides, dict) else {}
        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        followup_context = metadata.get("question_followup_context")
        normalized = normalize_question_followup_context(
            followup_context if isinstance(followup_context, dict) else None
        ) or {}
        overrides_reveal = (
            bool(overrides.get("reveal_answers"))
            if "reveal_answers" in overrides
            else None
        )
        overrides_reveal_explanations = (
            bool(overrides.get("reveal_explanations"))
            if "reveal_explanations" in overrides
            else None
        )
        decision = resolve_reveal_decision(
            preference=detect_answer_reveal_preference(context.user_message),
            is_review=False,
            is_unanswered_block=should_block_unanswered_reference_reveal(
                context.user_message, normalized
            ),
            overrides_reveal=overrides_reveal,
            context_reveal_flags=bool(
                normalized.get("reveal_explanations") or normalized.get("reveal_answers")
            ),
            explicit_request=False,
            overrides_reveal_explanations=overrides_reveal_explanations,
        )
        return decision.reveal_answers, decision.reveal_explanations

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
        start_index: int = 1,
    ) -> str:
        results = summary.get("results", []) if isinstance(summary, dict) else []
        if not isinstance(results, list) or not results:
            return ""

        lines: list[str] = []
        for idx, item in enumerate(results, start_index):
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

    # Fixed, deterministic nudge appended to the re-presented unanswered
    # question. Static text — never LLM-generated — so it cannot leak.
    _UNANSWERED_REFERENCE_NUDGE = (
        "这道题你还没作答，先试着做做——你的初步思路或选哪个？我再帮你看。"
    )

    # P1（2026-06-30）：未答题「隐式求助」结构化提示的 nudge。明示如何显式拿答案
    # （"公布答案"），尊重"不能不输出"——anti-peek 只压隐式，显式一律放行。
    _UNANSWERED_STRUCTURED_HINT_NUDGE = (
        "先按这个思路试着作答，把你的选择或想法发我，我再帮你逐项详细讲解；"
        "如果确实想直接看答案，可以说「公布答案」。"
    )

    @classmethod
    def _build_unanswered_reference_response(
        cls, context: UnifiedContext
    ) -> str | None:
        """Deterministic re-presentation of a referenced *unanswered* question.

        Returns the rendered stem + options (answer hidden) + a fixed nudge when,
        and only when, the turn is an unanswered-question reference to a specific
        item in a batch. Returns None otherwise (caller falls through to the
        normal LLM path), preserving the safety belt:

        - already-attempted question  -> should_block_... False -> None
        - answer concession           -> should_block_... False -> None
        - topic switch / no "第N题"    -> requested index None    -> None
        - no active batch context     -> normalize None          -> None

        Reuses the two existing single authorities verbatim
        (should_block_unanswered_reference_reveal + requested_question_item_index);
        no new adjudication, no answer regex. The correct_answer / grading_key on
        the item is intentionally NOT read — _render_question_response is called
        with reveal_answers=False / reveal_explanations=False.
        """

        metadata = context.metadata if isinstance(context.metadata, dict) else {}
        followup_context = metadata.get("question_followup_context")
        normalized = normalize_question_followup_context(
            followup_context if isinstance(followup_context, dict) else None
        )
        if not normalized:
            # reachability 收口（2026-06-30，修第一刀 green-on-unreachable）：
            # question_followup_context 只在 orchestrator 的 followup/submission 分支注入；
            # 通用求助轮（"给点提示/还是不会"→ tutorbot_kb_first）不注入它 → 短路读不到
            # 活跃题 → 落自由 LLM 泄底。active_object 是始终恢复的单一 relation 权威
            # （turn_runtime 每轮恢复），从它派生题面，让短路对这些泄露轮真正可达。
            normalized = extract_question_context_from_active_object(
                metadata.get("active_object")
            )
        if not normalized:
            return None

        message = context.user_message
        # Single authority #1: is this an unanswered-reference reveal attempt?
        if not should_block_unanswered_reference_reveal(message, normalized):
            return None
        # Single authority #2: which specific batch item is referenced?
        requested_index = requested_question_item_index(message, normalized)
        if requested_index is None:
            # P1（2026-06-30）：无具体「第N题」指代的隐式求助（"给点提示/还是不会/
            # 这题怎么想"）。should_block 已为 True（未答 + 非显式 reveal + 非 concession，
            # 显式要答案在 should_block 内已放行）。真泄露根因=这类轮 fall-through 到自由
            # LLM(tutorbot_kb_first)，LLM 用建造师知识自己推出答案（软指令/遮蔽已证伪）。
            # 治本=结构上不走自由 LLM：确定性结构化提示（考点+解题思路+nudge，绝不含
            # 答案/选项评价）。动作1 proven 治本扩面到通用求助。
            return cls._build_structured_hint_for_unanswered(normalized)

        items = normalized.get("items") or []
        if not isinstance(items, list) or not (1 <= requested_index <= len(items)):
            return None
        item = items[requested_index - 1]
        if not isinstance(item, dict):
            return None

        # Reuse the existing renderer. reveal flags hard-False so neither the
        # hidden correct_answer nor the explanation is emitted.
        rendered = cls._render_question_response(
            {"results": [{"qa_pair": item}]},
            reveal_answers=False,
            reveal_explanations=False,
            start_index=requested_index,
        )
        if not rendered:
            return None
        return f"{rendered}\n\n{cls._UNANSWERED_REFERENCE_NUDGE}"

    @classmethod
    def _build_structured_hint_for_unanswered(
        cls, normalized: dict[str, Any]
    ) -> str | None:
        """确定性结构化提示（P1，2026-06-30）：未答题隐式求助轮，结构上不走自由 LLM
        （它会用建造师知识推出答案 → 泄底），只确定性拼「考点 + 通用解题思路 + nudge」。

        只读保证无答案的字段：``concentration``（考点/知识点标签，与 correct_answer 是
        不同字段）。**绝不读** correct_answer / grading_key / explanation /
        knowledge_context（后者含「题库参考答案」明文，见 P2a）。无考点也给通用思路 nudge。
        """
        # 只用通用、确定性、保证无答案的内容拼提示。不读 concentration（实测它常被
        # 写成用户原话=垃圾，不可靠）、不读 correct_answer/explanation/knowledge_context
        # （含答案）、不逐项评价选项。这是 leak-proof 的下限：宁可通用，绝不泄底。
        lines = [
            "这道题先自己推一推，我给你一个通用的判断框架：",
            "解题思路：①先圈出题干里的关键词和限定条件（比如「正确的/错误的」、具体"
            "数值、特定情形或工序）；②回顾这个知识点对应的规范要求或基本原则；③再逐一"
            "对照每个选项，看哪个和你回顾到的原则最吻合——别急着核对答案，自己先推一遍"
            "印象最深。",
            cls._UNANSWERED_STRUCTURED_HINT_NUDGE,
        ]
        return "\n\n".join(lines)

    def _default_bot_config(self, context: UnifiedContext) -> BotConfig | None:
        bot_id = self._bot_id(context)
        if bot_id != "construction-exam-coach":
            return None
        return BotConfig(name="Construction Exam Coach")
