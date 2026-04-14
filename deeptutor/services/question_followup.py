from __future__ import annotations

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
    "不要给答案",
    "别给答案",
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
    if resolve_submission(message, normalized)[1] is not None:
        return True
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _FOLLOWUP_MARKERS)


def extract_submission_answer(message: str, question_context: dict[str, Any] | None) -> str | None:
    return resolve_submission(message, question_context)[1]


def resolve_submission(
    message: str,
    question_context: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return None, None

    numbered = _parse_numbered_submission(message)
    items = normalized.get("items") or []
    if numbered and items:
        item_index, item_message = numbered
        if 1 <= item_index <= len(items):
            narrowed = normalize_question_followup_context(items[item_index - 1])
            if narrowed:
                answer = _extract_single_submission(item_message, narrowed)
                if answer is not None:
                    return narrowed, answer

    answer = _extract_single_submission(message, normalized)
    if answer is None:
        return normalized, None
    return normalized, answer


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


def build_question_followup_context_from_summary(
    summary: dict[str, Any] | None,
    rendered_response: str,
    *,
    reveal_answers: bool = False,
    reveal_explanations: bool = False,
) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None

    items: list[dict[str, Any]] = []
    for index, result in enumerate(summary.get("results", []) or [], 1):
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


def _extract_single_submission(message: str, question_context: dict[str, Any]) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None

    compact_upper = re.sub(r"\s+", "", text).upper().rstrip("。.!！?")
    letter_patterns = [
        r"^(?:我选|我觉得选|选|答案是|答案|就是)?([ABCD])$",
        r"^(?:我手滑选了|我看错选了|我粗心选了)([ABCD])$",
        r"^(?:OPTION|ANSWER)[:：]?([ABCD])$",
        r"^([ABCD])$",
    ]
    for pattern in letter_patterns:
        match = re.fullmatch(pattern, compact_upper)
        if match:
            return match.group(1)

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


def _normalize_options(options: Any) -> dict[str, str] | None:
    if not isinstance(options, dict):
        return None
    normalized = {
        str(key).strip().upper()[:1]: str(value or "").strip()
        for key, value in options.items()
        if str(value or "").strip()
    }
    return normalized or None


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
