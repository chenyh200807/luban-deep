from __future__ import annotations

import json
import logging
import re
from typing import Any

from deeptutor.services.llm.factory import complete

logger = logging.getLogger(__name__)

_CHOICE_MARKERS = (
    "单选题",
    "多选题",
    "选择题",
    "单选",
    "多选",
    "选择",
    "判断题",
    "判断",
    "选项",
    "mcq",
    "choice",
)
_WRITTEN_MARKERS = (
    "案例题",
    "案例分析题",
    "案例",
    "实务题",
    "情景题",
    "材料题",
    "简答题",
    "简答",
    "问答题",
    "问答",
    "论述题",
    "论述",
    "essay",
    "written",
    "short answer",
)
_CODING_MARKERS = (
    "编程题",
    "代码题",
    "代码",
    "编程",
    "伪代码",
    "algorithm",
    "coding",
    "code",
)
_SUPPRESS_ANSWER_MARKERS = (
    "先别给答案",
    "先不要给答案",
    "先别直接给答案",
    "先不要直接给答案",
    "不要给答案",
    "不要直接给答案",
    "别给答案",
    "别直接给答案",
    "不要答案",
    "先别解析",
    "先不要解析",
    "不要解析",
    "别解析",
    "只出题",
    "只提问",
    "只问我",
    "只问第",
)
_REVEAL_ANSWER_MARKERS = (
    "给答案",
    "带答案",
    "附答案",
    "公布答案",
    "参考答案",
    "给解析",
    "带解析",
    "附解析",
    "详细解析",
    "讲解一下",
    "解析一下",
)
_FOLLOWUP_MARKERS = (
    "批改",
    "判分",
    "打分",
    "讲解",
    "解析",
    "为什么",
    "错在哪",
    "这题",
    "这道题",
    "上一题",
    "第1题",
    "第1问",
    "下一问",
    "继续问",
    "继续",
    "我答",
)
_JUDGMENT_TRUE_TOKENS = {"对", "正确", "是", "true", "yes", "√", "t"}
_JUDGMENT_FALSE_TOKENS = {"错", "错误", "否", "false", "no", "×", "x", "f"}
_LEADING_SUBMISSION_PREFIX = re.compile(
    r"^(?:我答(?:案)?(?:是)?|我的(?:答案)?(?:是)?|答案(?:是)?|我选|我觉得选|选|就是|应该是|option|answer)[:：]?",
    re.IGNORECASE,
)
_NUMBERED_SUBMISSION_RE = re.compile(
    r"^第?\s*([0-9一二两三四五六七八九十]+)\s*[题问][：:,.，、 ]*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_NUMBERED_BATCH_MARKER_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s；;，,\n]))"
    r"(?:第\s*([0-9一二两三四五六七八九十]+)\s*(?:题|问)?|([0-9]+)\s*(?:题|问)?)"
    r"\s*(?:[:：、.)）．]|(?=\s*[A-Ea-e对错正确错误√×TFtf]))",
    re.IGNORECASE,
)
_MCQ_OPTION_RE = re.compile(r"^\s*(?:[-*+]\s*)?[(（]?([A-E])[)）.、:：]\s*(.+?)\s*$", re.IGNORECASE)
_MCQ_MULTI_RE = re.compile(r"多选|不定项|可多选|正确的有|错误的有|哪些说法|下列说法正确的有")
_MCQ_QUESTION_LABEL = r"[一二两三四五六七八九十百零\d]+"
_MCQ_QUESTION_MARKER = (
    rf"(?:例题\s*{_MCQ_QUESTION_LABEL}|第\s*{_MCQ_QUESTION_LABEL}\s*[题道]|"
    rf"题目(?:\s*{_MCQ_QUESTION_LABEL})?|问题|[\(（]\s*\d+\s*[\)）]|\d+\s*[.、．])"
)
_MCQ_QUESTION_LINE_RE = re.compile(
    rf"^\s*(?:\*\*)?\s*{_MCQ_QUESTION_MARKER}(?:\s*[（(][^()（）]{{0,40}}[)）])?"
    rf"\s*(?:[:：]\s*.*)?\s*(?:\*\*)?\s*$",
    re.IGNORECASE,
)
_MCQ_GENERIC_NUMBERED_RE = re.compile(r"^\s*(?:\*\*)?\d+\s*[.、．]\s+.*$", re.IGNORECASE)
_MCQ_STEM_MARKER_RE = re.compile(
    rf"^\s*(?:题目|例题\s*{_MCQ_QUESTION_LABEL}|第\s*{_MCQ_QUESTION_LABEL}\s*[题道]|"
    rf"[\(（]\s*\d+\s*[\)）]|问题)\s*[:：]?\s*$",
    re.IGNORECASE,
)
_MCQ_STEM_INLINE_MARKER_RE = re.compile(
    rf"^\s*(?:题目(?:\s*{_MCQ_QUESTION_LABEL})?|例题\s*{_MCQ_QUESTION_LABEL}|"
    rf"第\s*{_MCQ_QUESTION_LABEL}\s*[题道]|[\(（]\s*\d+\s*[\)）]|问题)"
    rf"(?:\s*[（(][^()（）]{{0,40}}[)）])?\s*[:：]\s*.+$",
    re.IGNORECASE,
)
_MCQ_ANSWER_MARKERS = (
    "答案与核心解析",
    "答案与解析",
    "标准答案",
    "参考答案",
    "正确答案",
    "答案解析",
    "答案",
)
_MCQ_CORRECT_ANSWER_RE = re.compile(
    r"(?:\*\*)?(?:标准答案|参考答案|正确答案|答案)(?:\*\*)?\s*[：:]\s*([A-E](?:\s*[、，,/／\s]\s*[A-E])*)",
    re.IGNORECASE,
)
_MCQ_EXPLANATION_RE = re.compile(
    r"(?:\*\*)?(?:答案与核心解析|答案与解析|答案解析|解析)(?:\*\*)?\s*[：:]\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
_FOLLOWUP_ACTION_INTENTS = {
    "answer_questions",
    "revise_answers",
    "ask_followup",
    "generate_more_questions",
    "unknown",
    "unrelated",
}
_FOLLOWUP_ACTION_SUBMISSION_INTENTS = {"answer_questions", "revise_answers"}
_FOLLOWUP_ACTION_FOLLOWUP_INTENTS = {"ask_followup"}
_FOLLOWUP_ACTION_GENERATION_INTENTS = {"generate_more_questions"}
_FOLLOWUP_ACTION_INTENT_ALIASES = {
    "answer": "answer_questions",
    "answer_question": "answer_questions",
    "answer_questions": "answer_questions",
    "submit_answer": "answer_questions",
    "submit_answers": "answer_questions",
    "grading": "answer_questions",
    "grade_submission": "answer_questions",
    "revise": "revise_answers",
    "revise_answers": "revise_answers",
    "correct_answers": "revise_answers",
    "change_answers": "revise_answers",
    "correction": "revise_answers",
    "ask_followup": "ask_followup",
    "followup": "ask_followup",
    "explanation": "ask_followup",
    "ask_explanation": "ask_followup",
    "question_followup": "ask_followup",
    "generate_more": "generate_more_questions",
    "generate_more_questions": "generate_more_questions",
    "more_questions": "generate_more_questions",
    "continue_practice": "generate_more_questions",
    "practice": "generate_more_questions",
    "unknown": "unknown",
    "none": "unknown",
    "unrelated": "unrelated",
}


def normalize_question_followup_context(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    question = str(raw.get("question", "") or "").strip()
    items = _normalize_question_items(raw.get("items"))
    if not question and not items:
        return None

    options = _normalize_options(raw.get("options"))
    normalized: dict[str, Any] = {
        "parent_quiz_session_id": str(raw.get("parent_quiz_session_id", "") or "").strip(),
        "question_id": str(raw.get("question_id", "") or "").strip(),
        "question": question,
        "question_type": _normalize_question_type(raw.get("question_type")),
        "options": options,
        "correct_answer": str(raw.get("correct_answer", "") or "").strip(),
        "explanation": str(raw.get("explanation", "") or "").strip(),
        "difficulty": str(raw.get("difficulty", "") or "").strip(),
        "concentration": str(raw.get("concentration", "") or "").strip(),
        "knowledge_context": str(raw.get("knowledge_context", "") or "").strip(),
        "user_answer": str(raw.get("user_answer", "") or "").strip(),
        "is_correct": raw.get("is_correct"),
        "multi_select": bool(raw.get("multi_select", False)),
        "reveal_answers": bool(raw.get("reveal_answers", False)),
        "reveal_explanations": bool(raw.get("reveal_explanations", False)),
        "items": items,
    }
    return normalized


def detect_requested_question_type(message: str) -> tuple[str, bool]:
    text = str(message or "").strip().lower()
    if not text:
        return "choice", False
    if any(marker in text for marker in _CODING_MARKERS):
        return "coding", True
    if any(marker in text for marker in _WRITTEN_MARKERS):
        return "written", True
    if any(marker in text for marker in _CHOICE_MARKERS):
        return "choice", True
    return "choice", False


def detect_answer_reveal_preference(message: str) -> bool | None:
    text = str(message or "").strip().lower()
    if not text:
        return None
    if any(marker in text for marker in _SUPPRESS_ANSWER_MARKERS):
        return False
    if any(marker in text for marker in _REVEAL_ANSWER_MARKERS):
        return True
    return None


async def interpret_question_followup_action(
    message: str,
    question_context: dict[str, Any] | None,
    *,
    history_context: str = "",
) -> dict[str, Any] | None:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return None

    prompt = _build_followup_action_prompt(
        user_message=message,
        question_context=normalized,
        history_context=history_context,
    )
    try:
        raw = await complete(
            prompt=prompt,
            system_prompt=(
                "你是 DeepTutor 的题目 follow-up 判定器。"
                "你的唯一任务是根据当前用户消息和题目上下文，输出结构化 JSON，"
                "判断这是答题、改答案、问解析、继续出题，还是无关内容。"
            ),
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=500,
        )
    except Exception:
        logger.debug("LLM followup interpretation failed", exc_info=True)
        return None

    parsed = _parse_followup_action_payload(raw)
    if parsed is None:
        return None
    return _normalize_followup_action(parsed, normalized)


def followup_action_route(action: dict[str, Any] | None) -> str | None:
    if not isinstance(action, dict):
        return None
    intent = _normalize_followup_action_intent(action.get("intent"))
    if intent in _FOLLOWUP_ACTION_SUBMISSION_INTENTS:
        return "submission"
    if intent in _FOLLOWUP_ACTION_FOLLOWUP_INTENTS:
        return "followup"
    if intent in _FOLLOWUP_ACTION_GENERATION_INTENTS:
        return "practice_generation"
    return None


def apply_followup_action_to_context(
    question_context: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return None
    if followup_action_route(action) != "submission":
        return None

    answers = _normalized_followup_action_answers(action, normalized)
    if not answers:
        return None
    preserve_other_answers = bool((action or {}).get("preserve_other_answers"))
    items = normalized.get("items") or []
    if items:
        answer_map = {int(answer["index"]): dict(answer) for answer in answers}
        if preserve_other_answers:
            for index, item in enumerate(items, 1):
                if index in answer_map:
                    continue
                existing = str(item.get("user_answer") or "").strip()
                if not existing:
                    continue
                answer_map[index] = {
                    "index": index,
                    "question_id": str(item.get("question_id") or "").strip(),
                    "user_answer": existing,
                }
        ordered_answers = [answer_map[index] for index in sorted(answer_map)]
        return annotate_batch_submission_context(normalized, ordered_answers)

    answer = str(answers[0].get("user_answer") or "").strip()
    if not answer:
        return None
    graded_context = dict(normalized)
    graded_context["user_answer"] = answer
    graded_context["is_correct"] = answers_match(
        answer,
        str(normalized.get("correct_answer") or "").strip(),
        graded_context,
    )
    return graded_context


def looks_like_question_followup(message: str, question_context: dict[str, Any] | None) -> bool:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return False
    if resolve_submission_attempt(message, normalized)[1] is not None:
        return True
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _FOLLOWUP_MARKERS)


def extract_submission_answer(message: str, question_context: dict[str, Any] | None) -> str | None:
    return resolve_submission(message, question_context)[1]


def resolve_submission_attempt(
    message: str,
    question_context: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return None, None

    items = normalized.get("items") or []
    if len(items) > 1:
        batch_answers = _parse_batch_submission(message, items)
        if batch_answers:
            return normalized, {"kind": "batch", "answers": batch_answers}

    numbered = _parse_numbered_submission(message)
    if numbered and items:
        item_index, item_message = numbered
        if 1 <= item_index <= len(items):
            narrowed = normalize_question_followup_context(items[item_index - 1])
            if narrowed:
                answer = _extract_single_submission(item_message, narrowed)
                if answer is not None:
                    return narrowed, {
                        "kind": "single",
                        "answer": answer,
                        "question_id": narrowed.get("question_id", ""),
                    }

    answer = _extract_single_submission(message, normalized)
    if answer is None:
        return normalized, None
    return normalized, {
        "kind": "single",
        "answer": answer,
        "question_id": normalized.get("question_id", ""),
    }


def resolve_submission(
    message: str,
    question_context: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    normalized, submission = resolve_submission_attempt(message, question_context)
    if not submission or submission.get("kind") != "single":
        return normalized, None
    return normalized, str(submission.get("answer") or "").strip() or None


def annotate_batch_submission_context(
    question_context: dict[str, Any] | None,
    answers: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return None
    items = normalized.get("items") or []
    if not items or not isinstance(answers, list):
        return None

    answer_map: dict[int, dict[str, Any]] = {}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        index = answer.get("index")
        if isinstance(index, int) and index >= 1:
            answer_map[index] = answer

    if not answer_map:
        return None

    graded_items: list[dict[str, Any]] = []
    correct_count = 0
    user_answer_parts: list[str] = []
    for index, item in enumerate(items, 1):
        graded_item = dict(item)
        answer_payload = answer_map.get(index)
        if answer_payload is not None:
            user_answer = str(answer_payload.get("user_answer") or "").strip()
            graded_item["user_answer"] = user_answer
            graded_item["is_correct"] = answers_match(
                user_answer,
                str(graded_item.get("correct_answer") or "").strip(),
                graded_item,
            )
            if user_answer:
                user_answer_parts.append(f"第{index}题：{user_answer}")
            if graded_item["is_correct"] is True:
                correct_count += 1
        graded_items.append(graded_item)

    graded_context = dict(normalized)
    graded_context["items"] = graded_items
    graded_context["user_answer"] = "；".join(user_answer_parts)
    graded_context["is_correct"] = bool(graded_items) and correct_count == len(graded_items)
    return graded_context


def answers_match(
    user_answer: str,
    correct_answer: str,
    question_context: dict[str, Any] | None = None,
) -> bool:
    normalized = normalize_question_followup_context(question_context)
    left = str(user_answer or "").strip()
    right = str(correct_answer or "").strip()
    if not left or not right:
        return False
    normalized_left_option = _normalize_option_answer(left, normalized or {})
    normalized_right_option = _normalize_option_answer(right, normalized or {})
    if normalized_left_option and normalized_right_option:
        return normalized_left_option == normalized_right_option
    if left.upper() == right.upper():
        return True

    left_judgment = _normalize_judgment_token(left)
    right_judgment = _normalize_judgment_token(right)
    if left_judgment and right_judgment:
        return left_judgment == right_judgment

    options = (normalized or {}).get("options") or {}
    if isinstance(options, dict):
        left_option = _match_option_key_by_value(left, options)
        right_option = _match_option_key_by_value(right, options)
        if left_option and right_option:
            return left_option == right_option
    return False


def should_reveal_reference_material(
    message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    preference = detect_answer_reveal_preference(message)
    if preference is not None:
        return preference
    normalized = normalize_question_followup_context(question_context) or {}
    if normalized.get("reveal_explanations") or normalized.get("reveal_answers"):
        return True
    text = str(message or "").strip().lower()
    explicit_request_markers = ("参考答案", "标准答案", "解析", "讲解", "为什么", "错因")
    return any(marker in text for marker in explicit_request_markers)


def build_question_followup_context_from_result_summary(
    result_summary: dict[str, Any] | None,
    rendered_response: str,
    *,
    reveal_answers: bool = False,
    reveal_explanations: bool = False,
) -> dict[str, Any] | None:
    # This consumes legacy per-message result_summary, not the session-level compressed_summary.
    if not isinstance(result_summary, dict):
        return None

    items: list[dict[str, Any]] = []
    for index, result in enumerate(result_summary.get("results", []) or [], 1):
        if not isinstance(result, dict):
            continue
        qa_pair = result.get("qa_pair") or {}
        if not isinstance(qa_pair, dict):
            continue
        metadata = qa_pair.get("metadata") if isinstance(qa_pair.get("metadata"), dict) else {}
        question = str(qa_pair.get("question", "") or "").strip()
        if not question:
            continue
        items.append(
            {
                "question_id": str(qa_pair.get("question_id", "") or f"q_{index}").strip(),
                "question": question,
                "question_type": _normalize_question_type(qa_pair.get("question_type")),
                "options": _normalize_options(qa_pair.get("options")),
                "correct_answer": str(qa_pair.get("correct_answer", "") or "").strip(),
                "explanation": str(qa_pair.get("explanation", "") or "").strip(),
                "difficulty": str(qa_pair.get("difficulty", "") or "").strip(),
                "concentration": str(qa_pair.get("concentration", "") or "").strip(),
                "knowledge_context": str(
                    qa_pair.get("knowledge_context")
                    or metadata.get("knowledge_context")
                    or ""
                ).strip(),
                "multi_select": bool(qa_pair.get("multi_select", False)),
            }
        )

    if not items:
        question = str(rendered_response or "").strip()
        if not question:
            return None
        items = [
            {
                "question_id": "q_1",
                "question": question,
                "question_type": "written",
                "options": None,
                "correct_answer": "",
                "explanation": "",
                "difficulty": "",
                "concentration": "",
            }
        ]

    primary = dict(items[0])
    if len(items) > 1:
        primary["question_id"] = primary.get("question_id") or "question_set"
        primary["question"] = str(rendered_response or primary.get("question") or "").strip()
        primary["options"] = None
        primary["correct_answer"] = ""
        primary["explanation"] = ""

    primary["reveal_answers"] = reveal_answers
    primary["reveal_explanations"] = reveal_explanations
    primary["items"] = items
    return normalize_question_followup_context(primary)


def build_choice_result_summary_from_exact_question(
    exact_question: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(exact_question, dict):
        return None
    if str(exact_question.get("answer_kind") or "").strip().lower() != "mcq":
        return None

    stem = str(exact_question.get("stem") or "").strip()
    options = _normalize_exact_question_options(exact_question.get("options"))
    if not stem or not isinstance(options, dict) or len(options) < 2:
        return None

    correct_answer = "".join(
        re.findall(r"[A-E]", str(exact_question.get("correct_answer") or "").upper())
    )
    qa_pair = {
        "question_id": str(exact_question.get("id") or exact_question.get("chunk_id") or "tb_q_1").strip(),
        "question": stem,
        "question_type": "choice",
        "options": options,
        "correct_answer": correct_answer,
        "explanation": str(exact_question.get("analysis") or "").strip(),
        "difficulty": "",
        "concentration": "",
        "multi_select": bool(len(correct_answer) > 1 or len(options) >= 5),
    }
    return {"results": [{"qa_pair": qa_pair}]}


def build_question_followup_context_from_presentation(
    presentation: dict[str, Any] | None,
    rendered_response: str,
    *,
    reveal_answers: bool = False,
    reveal_explanations: bool = False,
) -> dict[str, Any] | None:
    if not isinstance(presentation, dict):
        return None

    items: list[dict[str, Any]] = []
    blocks = presentation.get("blocks") if isinstance(presentation.get("blocks"), list) else []
    for index, block in enumerate(blocks, 1):
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "").strip() != "mcq":
            continue
        questions = block.get("questions") if isinstance(block.get("questions"), list) else []
        for question_index, question in enumerate(questions, 1):
            if not isinstance(question, dict):
                continue
            followup = (
                question.get("followup_context")
                if isinstance(question.get("followup_context"), dict)
                else {}
            )
            stem = str(question.get("stem") or followup.get("question") or "").strip()
            if not stem:
                continue
            raw_options = followup.get("options")
            if not raw_options:
                raw_options = {
                    str(option.get("key") or "").strip(): str(option.get("text") or "").strip()
                    for option in (question.get("options") or [])
                    if isinstance(option, dict) and str(option.get("key") or "").strip()
                }
            items.append(
                {
                    "question_id": str(
                        question.get("question_id")
                        or followup.get("question_id")
                        or f"q_{index}_{question_index}"
                    ).strip(),
                    "question": stem,
                    "question_type": _normalize_question_type(
                        followup.get("question_type") or question.get("question_type")
                    ),
                    "options": _normalize_options(raw_options),
                    "correct_answer": str(followup.get("correct_answer", "") or "").strip(),
                    "explanation": str(followup.get("explanation", "") or "").strip(),
                    "difficulty": str(followup.get("difficulty", "") or "").strip(),
                    "concentration": str(followup.get("concentration", "") or "").strip(),
                    "knowledge_context": str(followup.get("knowledge_context", "") or "").strip(),
                    "multi_select": bool(
                        followup.get("multi_select")
                        or question.get("multi_select")
                        or str(question.get("question_type") or "").strip().lower()
                        in {"multi_choice", "multiple_choice"}
                    ),
                }
            )

    if not items:
        return None

    primary = dict(items[0])
    if len(items) > 1:
        primary["question_id"] = primary.get("question_id") or "question_set"
        primary["question"] = str(rendered_response or primary.get("question") or "").strip()
        primary["options"] = None
        primary["correct_answer"] = ""
        primary["explanation"] = ""

    primary["reveal_answers"] = reveal_answers
    primary["reveal_explanations"] = reveal_explanations
    primary["items"] = items
    return normalize_question_followup_context(primary)


def extract_choice_result_summary_from_text(text: str) -> dict[str, Any] | None:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return None

    lines = raw.split("\n")
    blocks = _split_choice_question_blocks(lines) or [raw]
    results: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, 1):
        qa_pair = _extract_choice_qa_pair(block, index)
        if qa_pair:
            results.append({"qa_pair": qa_pair})
    if not results:
        return None
    return {"results": results}


def _extract_single_submission(message: str, question_context: dict[str, Any]) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None

    option_answer = _extract_option_submission(text, question_context)
    if option_answer is not None:
        return option_answer

    stripped = _LEADING_SUBMISSION_PREFIX.sub("", text).strip().strip("。.!！?，,：:")
    judgment = _normalize_judgment_token(stripped)
    if judgment is None:
        for fragment in re.split(r"[，,。.!！?；;\s]+", stripped):
            judgment = _normalize_judgment_token(fragment)
            if judgment is not None:
                break
    if judgment is None:
        return None

    options = question_context.get("options") or {}
    option_key = _match_option_key_by_value(judgment, options)
    if option_key:
        return option_key

    correct_answer = str(question_context.get("correct_answer", "") or "").strip()
    if _normalize_judgment_token(correct_answer):
        return correct_answer

    return judgment


def _parse_numbered_submission(message: str) -> tuple[int, str] | None:
    text = str(message or "").strip()
    if not text:
        return None
    match = _NUMBERED_SUBMISSION_RE.fullmatch(text)
    if not match:
        return None
    value = _parse_small_zh_number(match.group(1))
    if value is None:
        return None
    return value, match.group(2).strip()


def _parse_batch_submission(
    message: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    corrected = _parse_batch_correction_submission(message, items)
    if corrected:
        return corrected
    numbered = _parse_numbered_batch_submission(message, items)
    if numbered:
        return numbered
    compact_numbered = _parse_compact_numbered_batch_submission(message, items)
    if compact_numbered:
        return compact_numbered
    return _parse_positional_batch_submission(message, items)


def _parse_numbered_batch_submission(
    message: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    text = str(message or "").strip()
    if not text:
        return None
    matches = list(_NUMBERED_BATCH_MARKER_RE.finditer(text))
    if len(matches) < 2:
        return None

    answers: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for idx, match in enumerate(matches):
        raw_index = match.group(1) or match.group(2) or ""
        item_index = _parse_small_zh_number(raw_index)
        if item_index is None or item_index < 1 or item_index > len(items):
            return None
        if item_index in seen_indexes:
            return None
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        fragment = text[match.end() : next_start].strip(" \t\r\n；;，,。.!！?")
        if not fragment:
            return None
        answer = _extract_single_submission(fragment, items[item_index - 1])
        if answer is None:
            return None
        seen_indexes.add(item_index)
        answers.append(
            {
                "index": item_index,
                "question_id": str(items[item_index - 1].get("question_id") or "").strip(),
                "user_answer": answer,
            }
        )
    return answers or None


def _parse_compact_numbered_batch_submission(
    message: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    text = _strip_submission_prefix(message)
    if not text:
        return None

    marker_re = re.compile(
        r"(?:第\s*([0-9一二两三四五六七八九十]+)\s*(?:题|问)?|([0-9]+)\s*(?:题|问)?|([一二两三四五六七八九十])(?=[A-Ea-e]))",
        re.IGNORECASE,
    )
    matches = list(marker_re.finditer(text))
    if len(matches) < 2:
        return None

    answers: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for idx, match in enumerate(matches):
        raw_index = match.group(1) or match.group(2) or match.group(3) or ""
        item_index = _parse_small_zh_number(raw_index)
        if item_index is None or item_index < 1 or item_index > len(items):
            return None
        if item_index in seen_indexes:
            return None
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        fragment = text[match.end() : next_start].strip(" \t\r\n；;，,。.!！?：:、")
        if not fragment:
            return None
        answer = _extract_single_submission(fragment, items[item_index - 1])
        if answer is None:
            return None
        seen_indexes.add(item_index)
        answers.append(
            {
                "index": item_index,
                "question_id": str(items[item_index - 1].get("question_id") or "").strip(),
                "user_answer": answer,
            }
        )
    return answers or None


def _parse_batch_correction_submission(
    message: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    text = str(message or "").strip()
    if not text:
        return None
    if "不变" not in text and "不改" not in text:
        return None

    existing_answers = _existing_batch_answers(items)
    if len(existing_answers) != len(items):
        return None

    change_re = re.compile(
        r"第?\s*([0-9一二两三四五六七八九十]+)\s*[题问]?\s*(?:答案)?\s*(?:改成|改为|改|换成|换为|换)\s*([A-Ea-e]+)",
        re.IGNORECASE,
    )
    matches = list(change_re.finditer(text))
    if not matches:
        return None

    updated_answers = dict(existing_answers)
    for match in matches:
        item_index = _parse_small_zh_number(match.group(1))
        if item_index is None or item_index < 1 or item_index > len(items):
            return None
        normalized = _normalize_option_answer(match.group(2), items[item_index - 1])
        if normalized is None:
            return None
        updated_answers[item_index] = normalized

    return [
        {
            "index": index,
            "question_id": str(item.get("question_id") or "").strip(),
            "user_answer": updated_answers[index],
        }
        for index, item in enumerate(items, 1)
    ]


def _parse_positional_batch_submission(
    message: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    text = str(message or "").strip()
    if not text:
        return None

    fragments = [fragment.strip() for fragment in re.split(r"[；;，,\n]+", text) if fragment.strip()]
    if len(fragments) == 1:
        fragments = [fragment.strip() for fragment in re.split(r"\s+", text) if fragment.strip()]
    if len(fragments) == 1:
        compact = _split_compact_positional_answers(fragments[0], items)
        if compact:
            fragments = compact
    if len(fragments) != len(items):
        return None

    answers: list[dict[str, Any]] = []
    for index, (fragment, item) in enumerate(zip(fragments, items, strict=False), 1):
        answer = _extract_single_submission(fragment, item)
        if answer is None:
            return None
        answers.append(
            {
                "index": index,
                "question_id": str(item.get("question_id") or "").strip(),
                "user_answer": answer,
            }
        )
    return answers or None


def _extract_option_submission(message: str, question_context: dict[str, Any]) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None

    option_keys = _available_option_keys(question_context)
    compact_upper = re.sub(r"\s+", "", text).upper().rstrip("。.!！?")
    letter_patterns = [
        rf"^(?:我选|我觉得选|选|答案是|答案|就是)?([{option_keys}](?:[、，,/／\s]*[{option_keys}])*)$",
        rf"^(?:我手滑选了|我看错选了|我粗心选了)([{option_keys}](?:[、，,/／\s]*[{option_keys}])*)$",
        rf"^(?:OPTION|ANSWER)[:：]?([{option_keys}](?:[、，,/／\s]*[{option_keys}])*)$",
        rf"^([{option_keys}](?:[、，,/／\s]*[{option_keys}])*)$",
    ]
    for pattern in letter_patterns:
        match = re.fullmatch(pattern, compact_upper)
        if match:
            normalized = _normalize_option_answer(match.group(1), question_context)
            if normalized is not None:
                return normalized

    stripped = _LEADING_SUBMISSION_PREFIX.sub("", text).strip().strip("。.!！?，,：:")
    for fragment in re.split(r"[，,。.!！?；;\s]+", stripped):
        normalized = _normalize_option_answer(fragment, question_context)
        if normalized is not None:
            return normalized
    return None


def _available_option_keys(question_context: dict[str, Any]) -> str:
    options = question_context.get("options") or {}
    keys = [
        str(key).strip().upper()[:1]
        for key in options.keys()
        if str(key).strip().upper()[:1] in {"A", "B", "C", "D", "E"}
    ]
    return "".join(sorted(set(keys))) or "ABCDE"


def _normalize_option_answer(value: str, question_context: dict[str, Any]) -> str | None:
    token = str(value or "").strip().upper()
    if not token:
        return None
    letters = re.findall(r"[A-E]", token)
    if not letters:
        return None
    available = set(_available_option_keys(question_context))
    if any(letter not in available for letter in letters):
        return None
    if len(set(letters)) > 1 and not _question_allows_multi_option_answer(question_context):
        return None
    normalized_letters: list[str] = []
    for letter in sorted(set(letters)):
        normalized_letters.append(letter)
    return "".join(normalized_letters)


def _split_compact_positional_answers(
    fragment: str,
    items: list[dict[str, Any]],
) -> list[str] | None:
    if not items or not all(_question_prefers_single_option_answer(item) for item in items):
        return None
    normalized = _extract_compact_answer_core(fragment, expected_len=len(items))
    if not normalized:
        return None
    return [letter.upper() for letter in normalized]


def _strip_submission_prefix(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    stripped = _LEADING_SUBMISSION_PREFIX.sub("", text).strip()
    return stripped.strip("。.!！?；;，,：:、 ")


def _extract_compact_answer_core(value: str, *, expected_len: int) -> str:
    text = _strip_submission_prefix(value)
    if not text:
        return ""

    context_prefix_re = re.compile(
        r"^(?:前面(?:[一二两三四五六七八九十0-9]+)?题|前[一二两三四五六七八九十0-9]+题|前三题|前五题|这(?:几|[一二两三四五六七八九十0-9]+)?题|上面(?:[一二两三四五六七八九十0-9]+)?题)\s*",
        re.IGNORECASE,
    )
    text = context_prefix_re.sub("", text).strip()
    text = _strip_submission_prefix(text)
    if not text:
        return ""

    text = re.sub(r"(?:吧|呢|呀|啊|哈|哦|喔|噢)$", "", text, flags=re.IGNORECASE).strip()
    compact = re.sub(r"[，,；;\s/:：、.\-]+", "", text)
    if re.fullmatch(rf"[A-Ea-e]{{{expected_len}}}", compact):
        return compact.upper()
    return ""


def _existing_batch_answers(items: list[dict[str, Any]]) -> dict[int, str]:
    answers: dict[int, str] = {}
    for index, item in enumerate(items, 1):
        normalized = _normalize_option_answer(str(item.get("user_answer") or "").strip(), item)
        if normalized:
            answers[index] = normalized
    return answers


def _build_followup_action_prompt(
    *,
    user_message: str,
    question_context: dict[str, Any],
    history_context: str = "",
) -> str:
    items = question_context.get("items") or []
    if not isinstance(items, list) or not items:
        items = [question_context]

    question_snapshot: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        question_snapshot.append(
            {
                "question_index": index,
                "question_id": str(item.get("question_id") or "").strip(),
                "question_type": str(item.get("question_type") or "").strip(),
                "question": str(item.get("question") or "").strip(),
                "options": item.get("options") or {},
                "user_answer": str(item.get("user_answer") or "").strip(),
                "multi_select": bool(item.get("multi_select", False)),
            }
        )

    prompt_payload = {
        "history_context": str(history_context or "").strip(),
        "user_message": str(user_message or "").strip(),
        "active_question_set": question_snapshot,
    }
    return (
        "请根据当前用户消息和题目上下文，判断用户意图。"
        "只能从以下 intent 中选择一个："
        "answer_questions, revise_answers, ask_followup, generate_more_questions, unknown, unrelated。\n"
        "规则：\n"
        "1. 如果用户是在提交当前题目/题组答案，intent=answer_questions。\n"
        "2. 如果用户是在修改已经提交过的答案，如“第2题改成C，其他不变”，intent=revise_answers。\n"
        "3. 如果用户是在问解析/讲解/为什么/哪题错了，intent=ask_followup。\n"
        "4. 如果用户是在要求继续出题/再来几题，intent=generate_more_questions。\n"
        "5. 如果无法有把握地判断为题目 follow-up，返回 unknown 或 unrelated，不要猜。\n"
        "6. 只有在上下文足够支持时，才能把紧凑字母串解释成答案。\n"
        "7. 如果需要输出答案，请放在 answers 数组里，每项包含 question_index、question_id、answer。\n"
        "8. 如果用户表达“其他不变”，preserve_other_answers=true，否则 false。\n"
        "9. 输出必须是 JSON 对象，键固定为 intent, confidence, preserve_other_answers, answers, reason。\n\n"
        f"{json.dumps(prompt_payload, ensure_ascii=False)}"
    )


def _parse_followup_action_payload(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _normalize_followup_action(
    raw: dict[str, Any],
    question_context: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    intent = _normalize_followup_action_intent(raw.get("intent"))
    confidence = raw.get("confidence")
    try:
        normalized_confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        normalized_confidence = 0.0

    answers = _normalize_followup_action_answers(raw.get("answers"), question_context)
    action = {
        "intent": intent,
        "confidence": normalized_confidence,
        "preserve_other_answers": bool(raw.get("preserve_other_answers", False)),
        "answers": answers,
        "reason": str(raw.get("reason") or "").strip(),
    }
    if intent in _FOLLOWUP_ACTION_SUBMISSION_INTENTS and not answers:
        action["intent"] = "unknown"
    return action


def _normalize_followup_action_intent(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    intent = _FOLLOWUP_ACTION_INTENT_ALIASES.get(normalized, normalized)
    if intent in _FOLLOWUP_ACTION_INTENTS:
        return intent
    return "unknown"


def _normalize_followup_action_answers(
    raw_answers: Any,
    question_context: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(raw_answers, list):
        return []
    items = question_context.get("items") or []
    normalized_answers: list[dict[str, Any]] = []
    for raw in raw_answers:
        if not isinstance(raw, dict):
            continue
        item_index = _resolve_followup_action_item_index(raw, items, question_context)
        if item_index is None:
            continue
        target_context = (
            normalize_question_followup_context(items[item_index - 1])
            if items and 1 <= item_index <= len(items)
            else question_context
        )
        if not target_context:
            continue
        answer = _normalize_followup_action_answer(raw.get("answer"), target_context)
        if answer is None:
            continue
        normalized_answers.append(
            {
                "index": item_index,
                "question_id": str(target_context.get("question_id") or "").strip(),
                "user_answer": answer,
            }
        )
    return normalized_answers


def _normalized_followup_action_answers(
    action: dict[str, Any] | None,
    question_context: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(action, dict):
        return []
    answers = action.get("answers")
    if isinstance(answers, list) and answers and isinstance(answers[0], dict) and "user_answer" in answers[0]:
        return [
            {
                "index": int(answer["index"]),
                "question_id": str(answer.get("question_id") or "").strip(),
                "user_answer": str(answer.get("user_answer") or "").strip(),
            }
            for answer in answers
            if isinstance(answer, dict) and str(answer.get("user_answer") or "").strip()
        ]
    return _normalize_followup_action_answers(answers, question_context)


def _resolve_followup_action_item_index(
    raw_answer: dict[str, Any],
    items: list[dict[str, Any]],
    question_context: dict[str, Any],
) -> int | None:
    raw_index = raw_answer.get("question_index")
    try:
        item_index = int(raw_index)
    except (TypeError, ValueError):
        item_index = None
    if item_index is not None:
        if items and 1 <= item_index <= len(items):
            return item_index
        if not items and item_index == 1:
            return 1

    raw_question_id = str(raw_answer.get("question_id") or "").strip()
    if raw_question_id and items:
        for index, item in enumerate(items, 1):
            if str(item.get("question_id") or "").strip() == raw_question_id:
                return index
    if raw_question_id and not items and raw_question_id == str(question_context.get("question_id") or "").strip():
        return 1
    return 1 if not items else None


def _normalize_followup_action_answer(value: Any, question_context: dict[str, Any]) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    option_answer = _normalize_option_answer(text, question_context)
    if option_answer is not None:
        return option_answer
    judgment = _normalize_judgment_token(text)
    if judgment is not None:
        options = question_context.get("options") or {}
        option_key = _match_option_key_by_value(judgment, options)
        if option_key:
            return option_key
        return judgment
    return text


def _question_allows_multi_option_answer(question_context: dict[str, Any] | None) -> bool:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return False
    if bool(normalized.get("multi_select")):
        return True
    question_type = str(normalized.get("question_type") or "").strip().lower()
    if question_type in {"multi_choice", "multiple_choice"}:
        return True
    correct_answer = str(normalized.get("correct_answer") or "").strip().upper()
    if len(re.findall(r"[A-E]", correct_answer)) > 1:
        return True
    question_text = str(normalized.get("question") or "").strip().lower()
    return bool(_MCQ_MULTI_RE.search(question_text))


def _question_prefers_single_option_answer(question_context: dict[str, Any] | None) -> bool:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return False
    return not _question_allows_multi_option_answer(normalized)


def _normalize_options(options: Any) -> dict[str, str] | None:
    if not isinstance(options, dict):
        return None
    normalized = {
        str(key).strip().upper()[:1]: str(value or "").strip()
        for key, value in options.items()
        if str(value or "").strip()
    }
    return normalized or None


def _normalize_exact_question_options(raw: Any) -> dict[str, str] | None:
    normalized = _normalize_options(raw)
    if normalized:
        return normalized

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        normalized = _normalize_options(parsed)
        if normalized:
            return normalized
        candidates: dict[str, str] = {}
        for line in text.splitlines():
            match = _MCQ_OPTION_RE.match(line)
            if not match:
                continue
            key = match.group(1).upper()
            if key in candidates:
                continue
            candidates[key] = str(match.group(2) or "").strip()
        return candidates or None

    if isinstance(raw, list):
        candidates: dict[str, str] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip().upper()[:1]
            value = str(item.get("text") or item.get("value") or "").strip()
            if not key or not value or key in candidates:
                continue
            candidates[key] = value
        return candidates or None

    return None


def _normalize_question_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized_items: list[dict[str, Any]] = []
    for item in raw:
        normalized = normalize_question_followup_context(item)
        if normalized:
            normalized_items.append(normalized)
    return normalized_items


def _normalize_question_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"choice", "written", "coding"}:
        return normalized
    return normalized or "written"


def _normalize_judgment_token(value: str) -> str | None:
    token = str(value or "").strip().lower()
    token = token.rstrip("。.!！?，,：:")
    if token in _JUDGMENT_TRUE_TOKENS:
        return "对"
    if token in _JUDGMENT_FALSE_TOKENS:
        return "错"
    return None


def _match_option_key_by_value(answer: str, options: dict[str, Any]) -> str | None:
    normalized_answer = _normalize_judgment_token(answer)
    if normalized_answer is None:
        return None
    for key, value in options.items():
        if _normalize_judgment_token(str(value or "").strip()) == normalized_answer:
            return str(key).strip().upper()[:1]
    return None


def _parse_small_zh_number(value: str) -> int | None:
    raw = str(value or "").strip()
    if raw.isdigit():
        return int(raw)
    mapping = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    return mapping.get(raw)


def _normalize_mcq_line(line: str) -> str:
    return re.sub(r"^#{1,6}\s*", "", str(line or "").replace("**", "")).strip()


def _is_mcq_question_marker_line(line: str) -> bool:
    normalized = _normalize_mcq_line(line)
    if not normalized or re.search(r"答案|解析", normalized):
        return False
    return bool(_MCQ_QUESTION_LINE_RE.match(normalized))


def _find_choice_question_starts(lines: list[str]) -> list[int]:
    starts: list[int] = []
    for index, line in enumerate(lines):
        if not _is_mcq_question_marker_line(line):
            continue
        normalized = _normalize_mcq_line(line)
        if _MCQ_GENERIC_NUMBERED_RE.match(normalized):
            option_hits = 0
            for next_index in range(index + 1, min(len(lines), index + 7)):
                if _MCQ_OPTION_RE.match(lines[next_index]):
                    option_hits += 1
            if option_hits < 2:
                continue
        starts.append(index)
    return starts


def _split_choice_question_blocks(lines: list[str]) -> list[str]:
    starts = _find_choice_question_starts(lines)
    if not starts:
        return []
    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if block:
            blocks.append(block)
    return blocks


def _strip_choice_answer_section(block: str) -> str:
    cleaned = str(block or "")
    cut_index = -1
    for marker in _MCQ_ANSWER_MARKERS:
        idx = cleaned.find(marker)
        if idx > 0 and (cut_index < 0 or idx < cut_index):
            cut_index = idx
    if cut_index > 0:
        cleaned = cleaned[:cut_index]
    return cleaned.strip()


def _extract_choice_correct_answer(block: str) -> str:
    match = _MCQ_CORRECT_ANSWER_RE.search(str(block or ""))
    if not match:
        return ""
    return "".join(re.findall(r"[A-E]", match.group(1).upper()))


def _extract_choice_explanation(block: str) -> str:
    match = _MCQ_EXPLANATION_RE.search(str(block or ""))
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def _strip_choice_stem_marker(text: str) -> str:
    lines = str(text or "").split("\n")
    if not lines:
        return str(text or "").strip()

    marker_re = re.compile(
        rf"^\s*(?:例题\s*{_MCQ_QUESTION_LABEL}|第\s*{_MCQ_QUESTION_LABEL}\s*[题道]|"
        rf"题目(?:\s*{_MCQ_QUESTION_LABEL})?|问题|[\(（]\s*\d+\s*[\)）]|\d+\s*[.、．])"
        rf"(?:\s*[（(][^()（）]+[)）])?\s*[:：]?\s*",
        re.IGNORECASE,
    )
    first = _normalize_mcq_line(lines[0]).strip("* ").strip()
    stripped_first = marker_re.sub("", first).strip()
    if _is_mcq_question_marker_line(first):
        return "\n".join([stripped_first] + lines[1:]).strip()
    return marker_re.sub("", _normalize_mcq_line(text)).strip()


def _extract_choice_qa_pair(block: str, index: int) -> dict[str, Any] | None:
    raw_block = str(block or "").strip()
    if not raw_block:
        return None

    correct_answer = _extract_choice_correct_answer(raw_block)
    explanation = _extract_choice_explanation(raw_block)
    cleaned_block = _strip_choice_answer_section(raw_block)
    lines = cleaned_block.split("\n")

    options: dict[str, str] = {}
    first_option_index = -1
    for line_index, line in enumerate(lines):
        match = _MCQ_OPTION_RE.match(line)
        if not match:
            continue
        if first_option_index < 0:
            first_option_index = line_index
        key = match.group(1).upper()
        if key in options:
            continue
        options[key] = str(match.group(2) or "").strip()

    if len(options) < 2 or first_option_index < 0:
        return None

    prefix_lines = lines[:first_option_index]
    prefix_text = "\n".join(prefix_lines).strip()
    has_explicit_question_signal = any(
        _is_mcq_question_marker_line(line)
        or _MCQ_STEM_MARKER_RE.match(_normalize_mcq_line(line))
        or _MCQ_STEM_INLINE_MARKER_RE.match(_normalize_mcq_line(line))
        for line in prefix_lines
    )
    if prefix_text and not has_explicit_question_signal:
        if _MCQ_CORRECT_ANSWER_RE.search(prefix_text) or any(
            marker in prefix_text for marker in _MCQ_ANSWER_MARKERS
        ):
            return None

    stem_lines = prefix_lines
    for line_index, line in enumerate(prefix_lines):
        normalized_line = _normalize_mcq_line(line)
        if _MCQ_STEM_MARKER_RE.match(normalized_line) or _MCQ_STEM_INLINE_MARKER_RE.match(normalized_line):
            stem_lines = prefix_lines[line_index:]
    stem = _strip_choice_stem_marker("\n".join(stem_lines)).strip() or "请选择正确选项"
    stem_parts = [part.strip() for part in stem.split("\n") if part.strip()]
    if len(stem_parts) > 1:
        heading = stem_parts[0]
        if len(heading) <= 12 and not re.search(r"[。？！?（）()]", heading):
            stem = "\n".join(stem_parts[1:]).strip()
    if not has_explicit_question_signal and re.match(r"^(?:标准答案|参考答案|正确答案|答案|解析)\b", stem):
        return None
    multi_select = bool(
        _MCQ_MULTI_RE.search(raw_block)
        or len(correct_answer) > 1
        or len(options) >= 5
    )

    return {
        "question_id": f"tb_q_{index}",
        "question": stem,
        "question_type": "choice",
        "options": options,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "difficulty": "",
        "concentration": "",
        "multi_select": multi_select,
    }
