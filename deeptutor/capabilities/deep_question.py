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
    apply_followup_action_to_context,
    answers_match,
    build_question_followup_context_from_presentation,
    build_question_followup_context_from_result_summary,
    normalize_question_followup_context,
    resolve_submission_attempt,
)
from deeptutor.services.render_presentation import build_canonical_presentation
from deeptutor.services.semantic_router import (
    apply_active_object_transition,
    build_active_object_from_question_context,
    build_turn_semantic_decision,
    normalize_active_object,
    normalize_suspended_object_stack,
    normalize_turn_semantic_decision,
    question_context_from_active_object,
)
from deeptutor.tutorbot.teaching_modes import looks_like_practice_generation_request


_GENERATION_TOPIC_ANCHOR_MARKERS = (
    "刚才",
    "上面",
    "这些",
    "这几个",
    "这个概念",
    "几个概念",
    "类似",
    "同类",
    "继续",
    "再来",
    "不要超纲",
    "围绕这个",
    "围绕刚才",
)
_GENERATION_REQUEST_STRIP_PATTERNS = (
    r"好[,，]?",
    r"那你现在",
    r"现在",
    r"请",
    r"麻烦你",
    r"麻烦",
    r"给我",
    r"帮我",
    r"我想",
    r"想",
    r"继续出",
    r"继续来一道",
    r"继续",
    r"再来一道",
    r"再来一题",
    r"再来",
    r"再出一道",
    r"再出",
    r"来一道",
    r"来一题",
    r"来",
    r"出题",
    r"出",
    r"考我",
    r"刷题",
    r"测我",
    r"[0-9一二两三四五六七八九十几]+(?:道|题|个题目|个小题)?",
    r"单选题",
    r"多选题",
    r"选择题",
    r"判断题",
    r"案例题",
    r"简答题",
    r"题目",
    r"很简单的",
    r"简单的",
    r"很简单",
    r"简单",
    r"容易的",
    r"容易",
)
_CURRENT_QUESTION_ANCHOR_MARKERS = (
    "这道题",
    "这题",
    "同类题",
    "类似题",
    "同类型题",
    "按这题",
    "围绕这题",
    "照着这题",
)


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clip_text(value: Any, *, limit: int = 280) -> str:
    text = _compact_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _append_unique(parts: list[str], candidate: Any) -> None:
    text = _compact_text(candidate)
    if not text or text in parts:
        return
    parts.append(text)


def _question_context_generation_anchor(question_context: dict[str, Any] | None) -> str:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return ""

    items = normalized.get("items") or []
    contexts = [normalized, *[item for item in items if isinstance(item, dict)]]
    concentrations: list[str] = []
    knowledge_parts: list[str] = []
    question_parts: list[str] = []

    for item in contexts:
        _append_unique(concentrations, item.get("concentration"))
        _append_unique(knowledge_parts, _clip_text(item.get("knowledge_context"), limit=220))
        _append_unique(question_parts, _clip_text(item.get("question"), limit=160))

    anchor_lines: list[str] = []
    if concentrations:
        anchor_lines.append(f"当前考点：{'；'.join(concentrations[:4])}")
    if knowledge_parts:
        anchor_lines.append(f"当前知识锚点：{'；'.join(knowledge_parts[:2])}")
    elif question_parts:
        anchor_lines.append(f"当前题目内容：{'；'.join(question_parts[:2])}")
    return "\n".join(anchor_lines)


def _active_object_generation_anchor(active_object: dict[str, Any] | None) -> str:
    normalized = normalize_active_object(active_object)
    if not normalized:
        return ""

    question_anchor = _question_context_generation_anchor(
        question_context_from_active_object(normalized)
    )
    if question_anchor:
        return question_anchor

    snapshot = normalized.get("state_snapshot") if isinstance(normalized.get("state_snapshot"), dict) else {}
    object_type = str(normalized.get("object_type") or "").strip()
    anchor_lines: list[str] = []

    if object_type == "open_chat_topic":
        title = _clip_text(snapshot.get("title"), limit=80)
        summary = _clip_text(snapshot.get("compressed_summary"), limit=220)
        if summary:
            anchor_lines.append(f"当前会话摘要：{summary}")
        elif title:
            anchor_lines.append(f"当前会话主题：{title}")
        return "\n".join(anchor_lines)

    if object_type in {"guide_page", "study_plan"}:
        current_page = snapshot.get("current_page") if isinstance(snapshot.get("current_page"), dict) else {}
        knowledge_title = _clip_text(current_page.get("knowledge_title"), limit=80)
        knowledge_summary = _clip_text(current_page.get("knowledge_summary"), limit=220)
        summary = _clip_text(snapshot.get("summary"), limit=180)
        if knowledge_title:
            anchor_lines.append(f"当前学习主题：{knowledge_title}")
        if knowledge_summary:
            anchor_lines.append(f"当前学习摘要：{knowledge_summary}")
        if summary:
            anchor_lines.append(f"计划上下文：{summary}")
        return "\n".join(anchor_lines)

    return ""


def _conversation_generation_anchor(conversation_context_text: str) -> str:
    text = _clip_text(conversation_context_text, limit=240)
    if not text:
        return ""
    return f"最近对话摘要：{text}"


def _suspended_stack_generation_anchor(
    suspended_object_stack: list[dict[str, Any]] | None,
) -> str:
    for item in normalize_suspended_object_stack(suspended_object_stack):
        normalized = normalize_active_object(item)
        if not normalized:
            continue
        object_type = str(normalized.get("object_type") or "").strip()
        if object_type in {"question_set", "single_question"}:
            continue
        anchor = _active_object_generation_anchor(normalized)
        if anchor:
            return anchor
    return ""


def _topic_needs_authoritative_anchor(topic: str) -> bool:
    normalized = _compact_text(topic).lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in _GENERATION_TOPIC_ANCHOR_MARKERS):
        return True
    if not looks_like_practice_generation_request(normalized):
        return False
    residue = normalized
    for pattern in _GENERATION_REQUEST_STRIP_PATTERNS:
        residue = re.sub(pattern, " ", residue, flags=re.IGNORECASE)
    residue = re.sub(r"[，。！？、,.!?\-:：\s]+", "", residue)
    return not residue


def _prefers_current_question_anchor(topic: str) -> bool:
    normalized = _compact_text(topic).lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in _CURRENT_QUESTION_ANCHOR_MARKERS):
        return True
    if "概念" in normalized or "知识点" in normalized:
        return False
    return looks_like_practice_generation_request(normalized)


def _resolve_generation_topic(
    *,
    raw_topic: str,
    active_object: dict[str, Any] | None,
    suspended_object_stack: list[dict[str, Any]] | None,
    followup_question_context: dict[str, Any] | None,
    conversation_context_text: str,
) -> str:
    topic = _compact_text(raw_topic)
    if not topic:
        return ""
    if not _topic_needs_authoritative_anchor(topic):
        return topic

    normalized_active_object = normalize_active_object(active_object)
    active_object_type = str((normalized_active_object or {}).get("object_type") or "").strip()
    question_anchor = _question_context_generation_anchor(followup_question_context)
    if not question_anchor and active_object_type in {"question_set", "single_question"}:
        question_anchor = _active_object_generation_anchor(normalized_active_object)

    broader_anchor = _suspended_stack_generation_anchor(suspended_object_stack)
    if not broader_anchor and active_object_type not in {"question_set", "single_question"}:
        broader_anchor = _active_object_generation_anchor(normalized_active_object)
    if not broader_anchor:
        broader_anchor = _conversation_generation_anchor(conversation_context_text)

    anchor = (
        question_anchor or broader_anchor
        if _prefers_current_question_anchor(topic)
        else broader_anchor or question_anchor
    )
    if not anchor:
        return topic
    return (
        f"{topic}\n\n"
        "请严格围绕以下当前学习锚点出题，不要偏题，不要超纲；如果锚点里没有出现某个新概念，不要自行引入：\n"
        f"{anchor}"
    )


def _should_use_followup_anchor_generation(
    *,
    raw_topic: str,
    mode: str,
    num_questions: int,
    followup_question_context: dict[str, Any] | None,
) -> bool:
    if str(mode or "").strip().lower() != "custom":
        return False
    if int(num_questions or 1) > 3:
        return False
    normalized_context = normalize_question_followup_context(followup_question_context)
    if not normalized_context:
        return False
    items = normalized_context.get("items") if isinstance(normalized_context.get("items"), list) else []
    if not items:
        return False
    return _topic_needs_authoritative_anchor(raw_topic)


def _should_use_lightweight_followup_generation(
    *,
    selected_mode: str,
    raw_topic: str,
    num_questions: int,
    followup_question_context: dict[str, Any] | None,
) -> bool:
    if str(selected_mode or "").strip().lower() != "fast":
        return False
    return _should_use_followup_anchor_generation(
        raw_topic=raw_topic,
        mode="custom",
        num_questions=num_questions,
        followup_question_context=followup_question_context,
    )


def _should_use_lightweight_topic_generation(
    *,
    selected_mode: str,
    raw_topic: str,
    resolved_topic: str,
    num_questions: int,
    question_type: str,
    followup_question_context: dict[str, Any] | None,
) -> bool:
    if str(selected_mode or "").strip().lower() != "fast":
        return False
    if normalize_question_followup_context(followup_question_context):
        return False
    if int(num_questions or 1) > 3:
        return False
    normalized_question_type = str(question_type or "").strip().lower()
    if normalized_question_type and normalized_question_type not in {"choice", "judge", "judgment"}:
        return False
    if not _topic_needs_authoritative_anchor(raw_topic):
        return False
    return resolved_topic != _compact_text(raw_topic)


def _grading_items(question_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    normalized = normalize_question_followup_context(question_context) or {}
    raw_items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    items = [
        item
        for item in (
            normalize_question_followup_context(candidate)
            for candidate in raw_items
            if isinstance(candidate, dict)
        )
        if item
    ]
    return items or ([normalized] if normalized else [])


def _should_use_deterministic_grading_feedback(
    *,
    selected_mode: str,
    question_context: dict[str, Any] | None,
) -> bool:
    if str(selected_mode or "").strip().lower() != "fast":
        return False
    items = _grading_items(question_context)
    if not items:
        return False
    for item in items:
        question_type = str(item.get("question_type") or "").strip().lower()
        if question_type not in {"choice", "judge", "judgment"}:
            return False
        if item.get("is_correct") is None:
            return False
        if not str(item.get("correct_answer") or "").strip():
            return False
    return True


def _render_deterministic_grading_feedback(question_context: dict[str, Any] | None) -> str:
    items = _grading_items(question_context)
    if not items:
        return ""
    if len(items) == 1:
        item = items[0]
        is_correct = item.get("is_correct") is True
        lines = [
            "## 📊 阅卷结论",
            f"**结果：** {'正确' if is_correct else '错误'}",
            f"**你的答案：** {str(item.get('user_answer') or '未作答').strip()}",
            f"**正确答案：** {str(item.get('correct_answer') or '未提供').strip()}",
        ]
        explanation = str(item.get("explanation") or "").strip()
        if explanation:
            lines.extend(["", "## 🧐 解析", explanation])
        return "\n".join(lines).strip()

    total = len(items)
    correct_count = sum(1 for item in items if item.get("is_correct") is True)
    lines = [
        "## 📊 阅卷结论",
        f"**得分：** {correct_count}/{total}题",
        (
            "**整体判断：** 全部答对。"
            if correct_count == total
            else "**整体判断：** 重点回看错题。"
        ),
    ]
    for index, item in enumerate(items, 1):
        is_correct = item.get("is_correct") is True
        lines.extend(
            [
                "",
                f"### 第{index}题：{'正确' if is_correct else '错误'}",
                f"- 你的答案：{str(item.get('user_answer') or '未作答').strip()}",
                f"- 正确答案：{str(item.get('correct_answer') or '未提供').strip()}",
            ]
        )
        explanation = str(item.get("explanation") or "").strip()
        if explanation and not is_correct:
            lines.append(f"- 解析：{explanation}")
    return "\n".join(lines).strip()


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
        force_generate_questions = bool(overrides.get("force_generate_questions", False))
        active_object = normalize_active_object(context.metadata.get("active_object")) or (
            build_active_object_from_question_context(
                context.metadata.get("question_followup_context"),
                source_turn_id=turn_id,
            )
        )
        suspended_object_stack = normalize_suspended_object_stack(
            context.metadata.get("suspended_object_stack")
        )
        turn_semantic_decision = normalize_turn_semantic_decision(
            context.metadata.get("turn_semantic_decision")
        ) or {}
        followup_question_context = question_context_from_active_object(active_object) or (
            context.metadata.get("question_followup_context", {}) or {}
        )
        followup_action = (
            context.metadata.get("question_followup_action")
            if isinstance(context.metadata.get("question_followup_action"), dict)
            else None
        )
        semantic_router_mode = str(context.metadata.get("semantic_router_mode") or "").strip().lower()
        selected_mode = str(context.metadata.get("selected_mode") or "").strip().lower()
        allow_legacy_followup_fallback = semantic_router_mode != "primary"
        next_action = str(turn_semantic_decision.get("next_action") or "").strip()
        if (
            not force_generate_questions
            and isinstance(followup_question_context, dict)
            and followup_question_context.get(
            "question"
            )
            and next_action != "route_to_generation"
        ):
            action_context = None
            if next_action == "route_to_grading":
                action_context = apply_followup_action_to_context(
                    followup_question_context,
                    followup_action,
                )
            if action_context is not None:
                from deeptutor.agents.question.agents.submission_grader_agent import (
                    SubmissionGraderAgent,
                )

                if (action_context.get("items") or []) and len(action_context.get("items") or []) > 1:
                    graded_context = self._build_batch_submission_context(
                        action_context,
                        None,
                    )
                else:
                    graded_context = self._build_submission_context(
                        action_context,
                        str(action_context.get("user_answer") or "").strip(),
                        raw_submission=context.user_message,
                    )
                async with stream.stage("generation", source=self.name):
                    if _should_use_deterministic_grading_feedback(
                        selected_mode=selected_mode,
                        question_context=graded_context,
                    ):
                        answer = _render_deterministic_grading_feedback(graded_context)
                    else:
                        agent = SubmissionGraderAgent(
                            language=context.language,
                            api_key=llm_config.api_key,
                            base_url=llm_config.base_url,
                            api_version=llm_config.api_version,
                        )
                        agent.set_trace_callback(self._build_trace_bridge(stream))
                        answer = await agent.process(
                            user_message=context.user_message,
                            question_context=graded_context,
                            history_context=str(
                                context.metadata.get("conversation_context_text", "") or ""
                            ).strip(),
                        )
                    if answer:
                        await stream.content(answer, source=self.name, stage="generation")
                    result_active_object = build_active_object_from_question_context(
                        graded_context,
                        source_turn_id=turn_id,
                        previous_active_object=active_object,
                    )
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
                        "active_object": result_active_object or {},
                        "suspended_object_stack": suspended_object_stack,
                        "turn_semantic_decision": turn_semantic_decision
                        or self._default_turn_semantic_decision(
                            next_action="route_to_grading",
                            active_object=result_active_object or active_object,
                            question_context=graded_context,
                            user_message=context.user_message,
                        ),
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        result_payload["metadata"] = {"cost_summary": cost_meta}
                    await stream.result(result_payload, source=self.name)
                return

            if next_action == "route_to_followup_explainer":
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
                    result_active_object = build_active_object_from_question_context(
                        followup_question_context,
                        source_turn_id=turn_id,
                        previous_active_object=active_object,
                    )
                    followup_payload: dict[str, Any] = {
                        "response": answer or "",
                        "mode": "followup",
                        "question_id": followup_question_context.get("question_id", ""),
                        "question_followup_context": normalize_question_followup_context(
                            followup_question_context
                        )
                        or {},
                        "active_object": result_active_object or {},
                        "suspended_object_stack": suspended_object_stack,
                        "turn_semantic_decision": turn_semantic_decision
                        or self._default_turn_semantic_decision(
                            next_action="route_to_followup_explainer",
                            active_object=result_active_object or active_object,
                            question_context=followup_question_context,
                            user_message=context.user_message,
                        ),
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        followup_payload["metadata"] = {"cost_summary": cost_meta}
                    await stream.result(followup_payload, source=self.name)
                return

            if allow_legacy_followup_fallback and self._prefer_followup_without_semantic_decision(
                turn_semantic_decision=turn_semantic_decision,
                followup_action=followup_action,
                question_context=followup_question_context,
                user_message=context.user_message,
            ):
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
                    result_active_object = build_active_object_from_question_context(
                        followup_question_context,
                        source_turn_id=turn_id,
                        previous_active_object=active_object,
                    )
                    followup_payload: dict[str, Any] = {
                        "response": answer or "",
                        "mode": "followup",
                        "question_id": followup_question_context.get("question_id", ""),
                        "question_followup_context": normalize_question_followup_context(
                            followup_question_context
                        )
                        or {},
                        "active_object": result_active_object or {},
                        "suspended_object_stack": suspended_object_stack,
                        "turn_semantic_decision": self._default_turn_semantic_decision(
                            next_action="route_to_followup_explainer",
                            active_object=result_active_object or active_object,
                            question_context=followup_question_context,
                            user_message=context.user_message,
                        ),
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        followup_payload["metadata"] = {"cost_summary": cost_meta}
                    await stream.result(followup_payload, source=self.name)
                return

            if allow_legacy_followup_fallback:
                target_context, submission = resolve_submission_attempt(
                    context.user_message,
                    followup_question_context,
                )
                if target_context and submission:
                    from deeptutor.agents.question.agents.submission_grader_agent import (
                        SubmissionGraderAgent,
                    )

                    if submission.get("kind") == "batch":
                        graded_context = self._build_batch_submission_context(
                            target_context,
                            submission.get("answers"),
                        )
                    else:
                        user_answer = str(submission.get("answer") or "").strip()
                        graded_context = self._build_submission_context(
                            target_context,
                            user_answer,
                            raw_submission=context.user_message,
                        )
                    async with stream.stage("generation", source=self.name):
                        if _should_use_deterministic_grading_feedback(
                            selected_mode=selected_mode,
                            question_context=graded_context,
                        ):
                            answer = _render_deterministic_grading_feedback(graded_context)
                        else:
                            agent = SubmissionGraderAgent(
                                language=context.language,
                                api_key=llm_config.api_key,
                                base_url=llm_config.base_url,
                                api_version=llm_config.api_version,
                            )
                            agent.set_trace_callback(self._build_trace_bridge(stream))
                            answer = await agent.process(
                                user_message=context.user_message,
                                question_context=graded_context,
                                history_context=str(
                                    context.metadata.get("conversation_context_text", "") or ""
                                ).strip(),
                            )
                        if answer:
                            await stream.content(answer, source=self.name, stage="generation")
                        result_active_object = build_active_object_from_question_context(
                            graded_context,
                            source_turn_id=turn_id,
                            previous_active_object=active_object,
                        )
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
                            "active_object": result_active_object or {},
                            "suspended_object_stack": suspended_object_stack,
                            "turn_semantic_decision": turn_semantic_decision
                            or self._default_turn_semantic_decision(
                                next_action="route_to_grading",
                                active_object=result_active_object or active_object,
                                question_context=graded_context,
                                user_message=context.user_message,
                            ),
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
                    result_active_object = build_active_object_from_question_context(
                        followup_question_context,
                        source_turn_id=turn_id,
                        previous_active_object=active_object,
                    )
                    followup_payload: dict[str, Any] = {
                        "response": answer or "",
                        "mode": "followup",
                        "question_id": followup_question_context.get("question_id", ""),
                        "question_followup_context": normalize_question_followup_context(
                            followup_question_context
                        )
                        or {},
                        "active_object": result_active_object or {},
                        "suspended_object_stack": suspended_object_stack,
                        "turn_semantic_decision": turn_semantic_decision
                        or self._default_turn_semantic_decision(
                            next_action="route_to_followup_explainer",
                            active_object=result_active_object or active_object,
                            question_context=followup_question_context,
                            user_message=context.user_message,
                        ),
                    }
                    cost_meta = self._collect_cost_summary("question")
                    if cost_meta:
                        followup_payload["metadata"] = {"cost_summary": cost_meta}
                    await stream.result(followup_payload, source=self.name)
                return

        mode = str(overrides.get("mode", "custom") or "custom").strip().lower()
        raw_topic = str(overrides.get("topic") or context.user_message or "").strip()
        topic = _resolve_generation_topic(
            raw_topic=raw_topic,
            active_object=active_object,
            suspended_object_stack=suspended_object_stack,
            followup_question_context=(
                followup_question_context if isinstance(followup_question_context, dict) else None
            ),
            conversation_context_text=str(
                context.metadata.get("conversation_context_text", "") or ""
            ).strip(),
        )
        num_questions = int(overrides.get("num_questions", 1) or 1)
        difficulty = str(overrides.get("difficulty", "") or "")
        question_type = str(overrides.get("question_type", "") or "")
        preference = str(overrides.get("preference", "") or "")
        reveal_answers = bool(overrides.get("reveal_answers", False))
        reveal_explanations = bool(overrides.get("reveal_explanations", reveal_answers))
        lightweight_generation = bool(overrides.get("lightweight_generation", False))
        lightweight_followup_generation = _should_use_lightweight_followup_generation(
            selected_mode=selected_mode,
            raw_topic=raw_topic,
            num_questions=num_questions,
            followup_question_context=(
                followup_question_context if isinstance(followup_question_context, dict) else None
            ),
        )
        lightweight_topic_generation = _should_use_lightweight_topic_generation(
            selected_mode=selected_mode,
            raw_topic=raw_topic,
            resolved_topic=topic,
            num_questions=num_questions,
            question_type=question_type,
            followup_question_context=(
                followup_question_context if isinstance(followup_question_context, dict) else None
            ),
        )
        lightweight_generation = (
            lightweight_generation
            or lightweight_followup_generation
            or lightweight_topic_generation
        )
        require_explanation = reveal_explanations
        history_context = str(
            context.metadata.get("conversation_context_text", "") or ""
        ).strip()
        enabled_tools = set(
            self.manifest.tools_used
            if context.enabled_tools is None
            else context.enabled_tools
        )
        if lightweight_followup_generation or lightweight_topic_generation:
            tool_flags_override = {
                "rag": False,
                "web_search": False,
                "code_execution": False,
            }
        else:
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

            if _should_use_followup_anchor_generation(
                raw_topic=raw_topic,
                mode=mode,
                num_questions=num_questions,
                followup_question_context=(
                    followup_question_context if isinstance(followup_question_context, dict) else None
                ),
            ):
                result = await coordinator.generate_from_followup_context(
                    user_topic=topic,
                    preference=preference,
                    num_questions=num_questions,
                    followup_question_context=followup_question_context,
                    difficulty=difficulty,
                    question_type=question_type,
                    history_context=history_context,
                    require_explanation=require_explanation,
                    lightweight_generation=lightweight_followup_generation,
                )
            else:
                result = await coordinator.generate_from_topic(
                    user_topic=topic,
                    preference=preference,
                    num_questions=num_questions,
                    difficulty=difficulty,
                    question_type=question_type,
                    history_context=history_context,
                    lightweight_generation=lightweight_generation,
                    require_explanation=require_explanation,
                )

        content = self._render_summary_markdown(
            result,
            reveal_answers=reveal_answers,
            reveal_explanations=reveal_explanations,
        )
        if content:
            await stream.content(content, source=self.name, stage="generation")

        presentation = build_canonical_presentation(
            content=content or "",
            result_summary=result,
        )
        result_payload: dict[str, Any] = {
            "response": content or "No questions generated.",
            "mode": mode,
            "question_followup_context": (
                build_question_followup_context_from_presentation(
                    presentation,
                    content or "",
                    reveal_answers=reveal_answers,
                    reveal_explanations=reveal_explanations,
                )
                or build_question_followup_context_from_result_summary(
                    result,
                    content or "",
                    reveal_answers=reveal_answers,
                    reveal_explanations=reveal_explanations,
                )
                or {}
            ),
        }
        result_payload["active_object"] = (
            build_active_object_from_question_context(
                result_payload["question_followup_context"],
                source_turn_id=turn_id,
                previous_active_object=active_object,
            )
            or {}
        )
        result_payload["turn_semantic_decision"] = turn_semantic_decision or self._default_turn_semantic_decision(
            next_action="route_to_generation",
            active_object=result_payload["active_object"] or active_object,
            question_context=result_payload["question_followup_context"],
            user_message=context.user_message,
        )
        transitioned_active_object, transitioned_stack = apply_active_object_transition(
            previous_active_object=active_object,
            previous_suspended_object_stack=suspended_object_stack,
            turn_semantic_decision=result_payload["turn_semantic_decision"],
            resolved_active_object=result_payload["active_object"],
        )
        result_payload["active_object"] = transitioned_active_object or {}
        result_payload["suspended_object_stack"] = transitioned_stack
        if presentation:
            result_payload["presentation"] = presentation
        cost_meta = self._collect_cost_summary("question")
        if cost_meta:
            result_payload["metadata"] = {"cost_summary": cost_meta}
        await stream.result(result_payload, source=self.name)

    @staticmethod
    def _default_turn_semantic_decision(
        *,
        next_action: str,
        active_object: dict[str, Any] | None,
        question_context: dict[str, Any] | None,
        user_message: str,
    ) -> dict[str, Any]:
        items = (question_context or {}).get("items") or []
        if next_action == "route_to_grading":
            relation = (
                "revise_answer_on_active_object"
                if any(marker in str(user_message or "") for marker in ("改", "更正", "修正", "订正"))
                else "answer_active_object"
            )
            allowed_patch = "append_answer_slots" if len(items) > 1 else "update_answer_slot"
            reason = "deep_question 按当前 active object 完成答题/批改。"
        elif next_action == "route_to_followup_explainer":
            relation = "ask_about_active_object"
            allowed_patch = "no_state_change"
            reason = "deep_question 按当前 active object 完成题目追问解释。"
        else:
            relation = (
                "continue_same_learning_flow" if active_object is not None else "switch_to_new_object"
            )
            allowed_patch = "set_active_object"
            reason = "deep_question 生成了新的题目对象并更新 active object。"
        return build_turn_semantic_decision(
            relation_to_active_object=relation,
            next_action=next_action,
            allowed_patch=allowed_patch,
            confidence=1.0,
            reason=reason,
            active_object=active_object,
        )

    @staticmethod
    def _prefer_followup_without_semantic_decision(
        *,
        turn_semantic_decision: dict[str, Any] | None,
        followup_action: dict[str, Any] | None,
        question_context: dict[str, Any] | None,
        user_message: str,
    ) -> bool:
        if turn_semantic_decision or followup_action:
            return False
        if not isinstance(question_context, dict) or not question_context.get("question"):
            return False
        if not (
            question_context.get("user_answer")
            or question_context.get("is_correct") is not None
            or question_context.get("explanation")
        ):
            return False
        text = str(user_message or "").strip().lower()
        if not text:
            return False
        followup_markers = (
            "why",
            "wrong",
            "explain",
            "because",
            "?",
            "为什么",
            "错在哪",
            "解析",
            "讲解",
            "思路",
            "哪里不对",
        )
        return any(marker in text for marker in followup_markers)

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
    def _build_batch_submission_context(
        question_context: dict[str, Any],
        answers: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        graded_context = dict(question_context)
        if answers:
            graded_context = apply_followup_action_to_context(
                question_context,
                {
                    "intent": "answer_questions",
                    "answers": answers,
                    "preserve_other_answers": False,
                },
            ) or dict(question_context)
        items = graded_context.get("items") or []
        correct_count = sum(1 for item in items if isinstance(item, dict) and item.get("is_correct") is True)
        total_count = len(items)
        graded_context["score"] = int((correct_count / total_count) * 100) if total_count else 0
        if total_count and correct_count == total_count:
            graded_context["diagnosis"] = "CORRECT"
        elif correct_count:
            graded_context["diagnosis"] = "PARTIAL"
        else:
            graded_context["diagnosis"] = "CONFUSION"
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
