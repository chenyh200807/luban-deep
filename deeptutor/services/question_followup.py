from __future__ import annotations

import json
import re
from typing import Any

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
    r"^(?:我答(?:案)?(?:是)?|答案(?:是)?|我选|我觉得选|选|就是|应该是|option|answer)[:：]?",
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
    numbered = _parse_numbered_batch_submission(message, items)
    if numbered:
        return numbered
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
    normalized = _strip_submission_prefix(fragment)
    if not normalized:
        return None
    if not re.fullmatch(r"[A-Ea-e]+", normalized):
        return None
    letters = [letter.upper() for letter in normalized]
    if len(letters) != len(items):
        return None
    return letters


def _strip_submission_prefix(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    stripped = _LEADING_SUBMISSION_PREFIX.sub("", text).strip()
    return stripped.strip("。.!！?；;，,：:、 ")


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
