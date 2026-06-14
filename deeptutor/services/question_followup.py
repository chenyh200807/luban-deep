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
_GRADING_AUTHORITY_FIELDS = (
    "node_code",
    "testing_focus",
    "grading_keywords",
    "grading_rubric",
    "structured_rules",
    "source_meta",
    # plan §Phase 3 (Batch C / A5) — hidden grading authority field.
    # 只能在 question_followup_context.items[i] 与 active_object.state_snapshot 内出现，
    # public serializer 必须 drop。
    "grading_key",
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
    "不要先给答案",
    "别先给答案",
    "先不给答案",
    "不先给答案",
    "不要给答案",
    "不要直接给答案",
    "别给答案",
    "别直接给答案",
    "不要答案",
    "先不公布答案",
    "不公布答案",
    "不要公布答案",
    "别公布答案",
    "先别公布答案",
    "暂不公布答案",
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
    "告诉我答案",
    "答案是什么",
    "正确答案是什么",
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
_ANSWER_CONCESSION_MARKERS = (
    "我放弃",
    "放弃这题",
    "放弃这一题",
    "跳过这题",
    "跳过这一题",
    "这题跳过",
    "不会做",
    "不做了",
    "我不会",
)
_FOLLOWUP_MARKERS = (
    "批改",
    "判分",
    "打分",
    "讲解",
    "解析",
    "为什么",
    "错在哪",
    "答案是什么",
    "正确答案是什么",
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
    r"^(?:我答(?:案)?(?:是)?|我的(?:答案)?(?:是)?|答案(?:是)?|我选|我觉得选|选(?!择)|就是|应该是|option|answer)[:：]?",
    re.IGNORECASE,
)
_SUBJECTIVE_QUESTION_TYPES = {"case", "written", "subjective", "short_answer", "essay"}
_TRAILING_GRADING_REQUEST_RE = re.compile(
    r"(?:[。.!！?；;，,、 ]*)"
    r"(?:请)?(?:按[^。.!！?；;]{0,40})?"
    r"(?:批改|判分|打分|阅卷)"
    r"(?:一下|下)?(?:[。.!！?；;，,、 ]*)$",
    re.IGNORECASE,
)
_NUMBERED_SUBMISSION_RE = re.compile(
    r"^第?\s*([0-9一二两三四五六七八九十]+)\s*[题问][：:,.，、 ]*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_Q_NUMBERED_SUBMISSION_RE = re.compile(
    r"^[Qq]\s*([0-9]+)\s*(?:题|问)?[：:,.，、 ]*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_NUMBERED_BATCH_MARKER_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s；;，,\n]))"
    r"(?:第\s*([0-9一二两三四五六七八九十]+)\s*(?:题|问)?|([0-9]+)\s*(?:题|问)?|[Qq]\s*([0-9]+)\s*(?:题|问)?)"
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
    unmatched_refs = _normalize_unmatched_answer_refs(raw.get("unmatched_answer_refs"))
    if unmatched_refs:
        normalized["unmatched_answer_refs"] = unmatched_refs
    evidence_refs = _normalize_followup_evidence_refs(raw.get("evidence_refs"))
    if evidence_refs:
        normalized["evidence_refs"] = evidence_refs
    normalized.update(_followup_grading_authority_fields(raw))
    grading_result = raw.get("construction_grading_result")
    if isinstance(grading_result, dict) and grading_result:
        normalized["construction_grading_result"] = grading_result
    return normalized


def _normalize_followup_evidence_refs(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, Any]] = []
    passthrough_keys = (
        "title",
        "source_type",
        "source_table",
        "source_id",
        "stable_source_id",
        "stable_id",
        "chunk_id",
        "id",
        "source_span",
        "taxonomy_path",
        "node_code",
        "taxonomy_code",
        "chapter",
        "section",
        "page",
        "standard_code",
        "article_code",
        "authority_rank",
        "evidence_level",
        "content_hash",
        "quote_hash",
        "public_quote",
        "metadata",
    )
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or item.get("source_type") or "").strip()
        field = str(item.get("field") or item.get("content_type") or "").strip()
        content = item.get("content")
        if content in (None, ""):
            content = item.get("text")
        if content in (None, ""):
            content = item.get("rag_content")
        if content in (None, ""):
            content = item.get("value")
        if not source or not field or content in (None, "", [], {}):
            continue
        ref = {"source": source, "field": field, "content": content}
        for key in passthrough_keys:
            value = item.get(key)
            if value not in (None, "", [], {}):
                ref[key] = value
        if "source_type" not in ref:
            ref["source_type"] = source
        if "public_quote" not in ref:
            ref["public_quote"] = content
        refs.append(ref)
        if len(refs) >= 8:
            break
    return refs


def _normalize_unmatched_answer_refs(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if index < 1:
            continue
        user_answer = str(item.get("user_answer") or "").strip()
        if not user_answer:
            continue
        refs.append(
            {
                "index": index,
                "question_id": str(item.get("question_id") or "").strip(),
                "user_answer": user_answer,
            }
        )
    return refs


_PUBLIC_REDACTED_KEYS = (
    "grading_key",
    "correct_answer",
    "explanation",
    "scoring_points",
    "official_slice",
    "atomic_official_slice",
    "official_sub_answer_verbatim",
    "official_analysis",
    "term_provenance",
    "flaw_span",
    "correction_span",
    "base_rule",
    "exception_items",
)

# plan §Phase 3 Step 3.2 — evidence-style entries describe which source field
# produced the evidence value. If the named field is a hidden authority
# (correct_answer / grading_key / scoring_points / explanation), the sibling
# ``value`` / ``content`` slot leaks the hidden value. Drop the whole entry.
_EVIDENCE_FIELD_KEYS = ("field", "source_field", "source_key", "name")


def _is_public_redacted_key(value: str) -> bool:
    return any(part in _PUBLIC_REDACTED_KEYS for part in value.split("."))


def _is_hidden_evidence_entry(value: dict[str, Any]) -> bool:
    for key in _EVIDENCE_FIELD_KEYS:
        sibling = value.get(key)
        if isinstance(sibling, str) and _is_public_redacted_key(sibling):
            return True
    return False


def _drop_hidden_value(value: Any) -> Any:
    """Recursively drop hidden authority from any nested dict/list.

    Three structural rules at the public boundary (plan §Phase 3 Step 3.2):

      1. Drop any dict key in ``_PUBLIC_REDACTED_KEYS`` (e.g.
         ``items[i].construction_grading_result.correct_answer``).
      2. Drop an entire dict if its evidence-field slot names a hidden
         authority — e.g. ``{"source":"qb","field":"correct_answer","value":"B"}``
         leaks the standard answer through ``value``.
      3. Filter ``source_fields`` lists down to non-hidden entries; if every
         entry was hidden, drop the slot entirely.

    Scalars pass through untouched — only dictionary keys / list entries are
    dropped, so user-visible markdown bodies are preserved.

    The signal value ``None`` returned from this helper means "drop this entry"
    when the caller is iterating a list; callers wanting a normal recursion
    treat ``None`` as identity-passthrough at scalar level (the only way
    ``None`` flows up is via an evidence-entry drop, and lists explicitly
    filter on it).
    """
    if isinstance(value, dict):
        if _is_hidden_evidence_entry(value):
            return None  # caller list-filter drops this entry
        clean: dict[str, Any] = {}
        for key, sub in value.items():
            if key in _PUBLIC_REDACTED_KEYS:
                continue
            if key == "source_fields" and isinstance(sub, list):
                kept = [
                    item
                    for item in sub
                    if not (isinstance(item, str) and _is_public_redacted_key(item))
                ]
                if not kept:
                    continue
                clean[key] = kept
                continue
            cleaned = _drop_hidden_value(sub)
            if cleaned is None and isinstance(sub, dict):
                # nested dict was a hidden evidence entry — drop the slot
                continue
            clean[key] = cleaned
        return clean
    if isinstance(value, list):
        out: list[Any] = []
        for item in value:
            cleaned = _drop_hidden_value(item)
            if cleaned is None and isinstance(item, dict):
                continue
            out.append(cleaned)
        return out
    return value


def redact_question_followup_context_for_public(
    context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """plan §Phase 3 (Batch C) — public payload 必须 drop hidden grading authority.

    保留：question_id, question, question_type, options, difficulty, concentration,
    items[i] 的公开字段。Drop（任意嵌套深度）：grading_key, correct_answer,
    explanation, scoring_points，包括 ``items[i].construction_grading_result.*``
    这类二级嵌套形态。

    这是一个纯函数；输入不被修改。
    """
    if not isinstance(context, dict):
        return None
    return _drop_hidden_value(context)


def _followup_grading_authority_fields(*sources: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in _GRADING_AUTHORITY_FIELDS:
            if key in fields:
                continue
            value = source.get(key)
            if value not in (None, "", [], {}):
                fields[key] = value
    return fields


def reset_question_submission_state(question_context: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized = normalize_question_followup_context(question_context)
    if normalized is None:
        return None
    reset_context = dict(normalized)
    reset_context["user_answer"] = ""
    reset_context["is_correct"] = None
    reset_items: list[dict[str, Any]] = []
    for item in reset_context.get("items") or []:
        if not isinstance(item, dict):
            continue
        reset_item = dict(item)
        reset_item["user_answer"] = ""
        reset_item["is_correct"] = None
        reset_items.append(reset_item)
    reset_context["items"] = reset_items
    return reset_context


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


def annotate_submission_context_from_message(
    message: str,
    question_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized, submission = resolve_submission_attempt(message, question_context)
    if not normalized or not submission:
        return normalized
    kind = str(submission.get("kind") or "").strip()
    if kind == "batch":
        answers = submission.get("answers")
        return annotate_batch_submission_context(
            normalized,
            answers if isinstance(answers, list) else None,
        ) or normalized
    if kind != "single":
        return normalized

    user_answer = str(submission.get("answer") or "").strip()
    if not user_answer:
        return normalized
    target_question_id = str(submission.get("question_id") or "").strip()
    graded_context = dict(normalized)
    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    if items:
        graded_items: list[dict[str, Any]] = []
        matched_item: dict[str, Any] | None = None
        for item in items:
            if not isinstance(item, dict):
                continue
            graded_item = dict(item)
            item_question_id = str(graded_item.get("question_id") or "").strip()
            should_update = (
                bool(target_question_id and item_question_id == target_question_id)
                or len(items) == 1
            )
            if should_update:
                graded_item["user_answer"] = user_answer
                graded_item["is_correct"] = answers_match(
                    user_answer,
                    str(graded_item.get("correct_answer") or "").strip(),
                    graded_item,
                )
                matched_item = graded_item
            graded_items.append(graded_item)
        if matched_item is not None:
            graded_context["user_answer"] = user_answer
            graded_context["is_correct"] = matched_item.get("is_correct")
            if len(graded_items) == 1:
                for key in (
                    "question_id",
                    "question",
                    "question_type",
                    "options",
                    "correct_answer",
                    "explanation",
                    "difficulty",
                    "concentration",
                    "knowledge_context",
                    "multi_select",
                    "grading_key",
                    "evidence_refs",
                ):
                    if key in matched_item:
                        graded_context[key] = matched_item[key]
        graded_context["items"] = graded_items
        return normalize_question_followup_context(graded_context) or graded_context

    graded_context["user_answer"] = user_answer
    graded_context["is_correct"] = answers_match(
        user_answer,
        str(graded_context.get("correct_answer") or "").strip(),
        graded_context,
    )
    return normalize_question_followup_context(graded_context) or graded_context


def looks_like_question_followup(message: str, question_context: dict[str, Any] | None) -> bool:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return False
    if _looks_like_option_challenge_followup(message, normalized):
        return True
    if _looks_like_option_value_challenge_followup(message, normalized):
        return True
    submission = resolve_submission_attempt(message, normalized)[1]
    if submission is not None and submission.get("kind") != "ambiguous":
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
                if _numbered_tail_looks_like_followup_question(item_message):
                    return narrowed, None
                answer = _extract_single_submission(
                    item_message,
                    narrowed,
                    allow_invalid_multi_option=True,
                )
                if answer is not None:
                    return narrowed, {
                        "kind": "single",
                        "answer": answer,
                        "question_id": narrowed.get("question_id", ""),
                    }

    if len(items) > 1:
        answer = _extract_single_submission(message, normalized)
        if answer is not None:
            return normalized, {
                "kind": "ambiguous",
                "answer": answer,
                "requires_question_index": True,
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
    unmatched_refs: list[dict[str, Any]] = []
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        index = answer.get("index")
        if isinstance(index, int) and index >= 1:
            if bool(answer.get("unmatched")) or index > len(items):
                unmatched_refs.append(
                    {
                        "index": index,
                        "question_id": str(answer.get("question_id") or "").strip(),
                        "user_answer": str(answer.get("user_answer") or "").strip(),
                    }
                )
            else:
                answer_map[index] = answer

    if not answer_map and not unmatched_refs:
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
    if unmatched_refs:
        graded_context["unmatched_answer_refs"] = unmatched_refs
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

    options = (normalized or {}).get("options") or {}
    if isinstance(options, dict):
        left_option = normalized_left_option or _match_option_key_by_value(left, options)
        right_option = normalized_right_option or _match_option_key_by_value(right, options)
        if left_option and right_option:
            return left_option == right_option

    left_judgment = _normalize_judgment_token(left)
    right_judgment = _normalize_judgment_token(right)
    if left_judgment and right_judgment:
        return left_judgment == right_judgment
    return False


def should_reveal_reference_material(
    message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    preference = detect_answer_reveal_preference(message)
    normalized = normalize_question_followup_context(question_context) or {}
    if preference is True:
        if should_block_unanswered_reference_reveal(message, normalized):
            return False
        return True
    if preference is False:
        return False
    if normalized.get("reveal_explanations") or normalized.get("reveal_answers"):
        return True
    text = str(message or "").strip().lower()
    explicit_request_markers = (
        "参考答案",
        "标准答案",
        "正确答案",
        "答案",
        "解析",
        "讲解",
        "为什么",
        "错因",
        "扣分",
        "怎么扣",
        "怎么判",
        "怎么评分",
        "评分",
    )
    if any(marker in text for marker in explicit_request_markers):
        if should_block_unanswered_reference_reveal(message, normalized):
            return False
        return True
    return False


def should_block_unanswered_reference_reveal(
    message: str,
    question_context: dict[str, Any] | None,
) -> bool:
    normalized = normalize_question_followup_context(question_context) or {}
    if not normalized:
        return False
    if normalized.get("reveal_explanations") or normalized.get("reveal_answers"):
        return False
    requested_index = requested_question_item_index(message, normalized)
    if requested_index is not None:
        items = normalized.get("items") or []
        if isinstance(items, list) and 1 <= requested_index <= len(items):
            item = items[requested_index - 1]
            if isinstance(item, dict) and _question_has_learner_attempt(item):
                return False
        return not _looks_like_answer_concession(message)
    if _question_has_learner_attempt(normalized):
        return False
    return not _looks_like_answer_concession(message)


def _question_has_learner_attempt(question_context: dict[str, Any]) -> bool:
    if str(question_context.get("user_answer") or "").strip():
        return True
    if isinstance(question_context.get("is_correct"), bool):
        return True
    items = question_context.get("items") or []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("user_answer") or "").strip():
                return True
            if isinstance(item.get("is_correct"), bool):
                return True
    return False


def _looks_like_answer_concession(message: str) -> bool:
    text = str(message or "").strip()
    return any(marker in text for marker in _ANSWER_CONCESSION_MARKERS)


def requested_question_item_index(
    message: str,
    question_context: dict[str, Any] | None,
) -> int | None:
    normalized = normalize_question_followup_context(question_context)
    if not normalized:
        return None
    items = normalized.get("items") or []
    if not isinstance(items, list) or len(items) < 2:
        return None
    text = str(message or "").strip()
    if not text:
        return None
    match = re.search(r"第\s*([0-9一二两三四五六七八九十]+)\s*[题问]", text)
    if not match:
        return None
    index = _parse_small_zh_number(match.group(1))
    if index is None or index < 1 or index > len(items):
        return None
    return index


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
        evidence_refs = _normalize_followup_evidence_refs(
            qa_pair.get("evidence_refs") or metadata.get("evidence_refs")
        )
        question = str(qa_pair.get("question", "") or "").strip()
        if not question:
            continue
        grading_key = qa_pair.get("grading_key") if isinstance(qa_pair.get("grading_key"), dict) else None
        hidden_correct_answer = str(
            qa_pair.get("correct_answer")
            or ((grading_key or {}).get("correct_answer"))
            or ""
        ).strip()
        item = {
            "question_id": str(qa_pair.get("question_id", "") or f"q_{index}").strip(),
            "question": question,
            "question_type": _normalize_question_type(qa_pair.get("question_type")),
            "options": _normalize_options(qa_pair.get("options")),
            "correct_answer": hidden_correct_answer,
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
        # plan §Phase 3 (Batch C / A5) — copy hidden grading_key into item.
        if grading_key:
            item["grading_key"] = dict(grading_key)
        item.update(_followup_grading_authority_fields(qa_pair, metadata))
        if evidence_refs:
            item["evidence_refs"] = evidence_refs
        items.append(item)

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
        # plan §Phase 3 — multi-item primary 是 collection 顶层，
        # 不应携带 hidden grading_key（只能在 items[i] 内）。
        primary.pop("grading_key", None)

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

    metadata = exact_question.get("metadata") if isinstance(exact_question.get("metadata"), dict) else {}
    correct_answer = "".join(
        re.findall(
            r"[A-E]",
            str(
                exact_question.get("correct_answer")
                or exact_question.get("answer")
                or metadata.get("canonical_correct_answer")
                or ""
            ).upper(),
        )
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
            item = {
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
            item.update(_followup_grading_authority_fields(followup, question))
            evidence_refs = _normalize_followup_evidence_refs(
                followup.get("evidence_refs") or question.get("evidence_refs")
            )
            if evidence_refs:
                item["evidence_refs"] = evidence_refs
            items.append(item)

    if not items:
        return None

    primary = dict(items[0])
    if len(items) > 1:
        primary["question_id"] = primary.get("question_id") or "question_set"
        primary["question"] = str(rendered_response or primary.get("question") or "").strip()
        primary["options"] = None
        primary["correct_answer"] = ""
        primary["explanation"] = ""
        # plan §Phase 3 — multi-item primary 是 collection 顶层，
        # 不应携带 hidden grading_key（只能在 items[i] 内）。
        primary.pop("grading_key", None)

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


def _extract_single_submission(
    message: str,
    question_context: dict[str, Any],
    *,
    allow_invalid_multi_option: bool = False,
) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None

    option_answer = _extract_option_submission(
        text,
        question_context,
        allow_invalid_multi_option=allow_invalid_multi_option,
    )
    if option_answer is not None:
        return option_answer

    subjective_answer = _extract_subjective_submission(text, question_context)
    if subjective_answer is not None:
        return subjective_answer

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


def _extract_subjective_submission(message: str, question_context: dict[str, Any]) -> str | None:
    question_type = str(question_context.get("question_type") or "").strip().lower()
    if question_type not in _SUBJECTIVE_QUESTION_TYPES:
        return None

    text = str(message or "").strip()
    if not text:
        return None
    explicit_answer = bool(_LEADING_SUBMISSION_PREFIX.match(text))
    prestrip_lowered = text.lower()
    prestrip_question_markers = (
        "答案是什么",
        "我的答案是什么",
        "为什么",
        "解析",
        "讲解",
        "思路",
        "标准答案",
        "参考答案",
        "正确答案",
        "是什么",
        "什么是",
        "讲讲",
        "讲一下",
        "说说",
        "介绍一下",
        "怎么",
        "如何",
        "怎样",
        "能不能",
        "是否",
    )
    if not explicit_answer and (
        any(marker in prestrip_lowered for marker in prestrip_question_markers)
        or ("？" in text or "?" in text)
    ):
        return None
    stripped = _strip_submission_prefix(text)
    stripped = _TRAILING_GRADING_REQUEST_RE.sub("", stripped).strip()
    stripped = stripped.strip("。.!！?；;，,：:、 ")
    if not stripped:
        return None
    if explicit_answer and "答案" in prestrip_lowered and stripped in {"什么", "啥"}:
        return None

    lowered = stripped.lower()
    explanation_markers = (
        "为什么",
        "解析",
        "讲解",
        "思路",
        "标准答案",
        "参考答案",
        "正确答案",
        "答案是什么",
        "是什么",
        "什么是",
        "讲讲",
        "讲一下",
        "说说",
        "介绍一下",
        "怎么",
        "如何",
        "怎样",
        "能不能",
        "是否",
        "怎么写",
        "怎么做",
    )
    if not explicit_answer and any(marker in lowered for marker in explanation_markers):
        return None
    generation_markers = (
        "出题",
        "出一道",
        "来一道",
        "来一题",
        "选择题",
        "单选题",
        "多选题",
        "判断题",
        "案例题",
        "简答题",
        "刷题",
        "练题",
        "练习",
    )
    if not explicit_answer and any(marker in lowered for marker in generation_markers):
        return None
    if not explicit_answer and len(stripped) < 6:
        return None
    return stripped


def _parse_numbered_submission(message: str) -> tuple[int, str] | None:
    text = str(message or "").strip()
    if not text:
        return None
    match = _Q_NUMBERED_SUBMISSION_RE.fullmatch(text) or _NUMBERED_SUBMISSION_RE.fullmatch(text)
    if not match:
        return None
    value = _parse_small_zh_number(match.group(1))
    if value is None:
        return None
    return value, match.group(2).strip()


def _numbered_tail_looks_like_followup_question(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    markers = (
        "为什么",
        "为啥",
        "原因是什么",
        "错在哪",
        "哪里错",
        "不对",
        "答案是什么",
        "正确答案是什么",
        "解析",
        "讲解",
        "讲讲",
        "怎么理解",
        "什么意思",
    )
    return any(marker in text for marker in markers)


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
    if _parse_numbered_submission(message):
        return None
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
        raw_index = match.group(1) or match.group(2) or match.group(3) or ""
        item_index = _parse_small_zh_number(raw_index)
        if item_index in seen_indexes:
            return None
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        fragment = text[match.end() : next_start].strip(" \t\r\n；;，,。.!！?")
        if not fragment:
            return None
        if item_index is None or item_index < 1 or item_index > len(items):
            answer = _extract_unmatched_batch_answer(fragment)
            if answer is None or item_index is None:
                return None
            seen_indexes.add(item_index)
            answers.append(
                {
                    "index": item_index,
                    "question_id": "",
                    "user_answer": answer,
                    "unmatched": True,
                }
            )
            continue
        answer = _extract_single_submission(
            fragment,
            items[item_index - 1],
            allow_invalid_multi_option=True,
        )
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
        r"(?:第\s*([0-9一二两三四五六七八九十]+)\s*(?:题|问)?|([0-9]+)\s*(?:题|问)?|[Qq]\s*([0-9]+)\s*(?:题|问)?|([一二两三四五六七八九十])(?=[A-Ea-e]))",
        re.IGNORECASE,
    )
    matches = list(marker_re.finditer(text))
    if len(matches) < 2:
        return None

    answers: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for idx, match in enumerate(matches):
        raw_index = match.group(1) or match.group(2) or match.group(3) or match.group(4) or ""
        item_index = _parse_small_zh_number(raw_index)
        if item_index in seen_indexes:
            return None
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        fragment = text[match.end() : next_start].strip(" \t\r\n；;，,。.!！?：:、")
        if not fragment:
            return None
        if item_index is None or item_index < 1 or item_index > len(items):
            answer = _extract_unmatched_batch_answer(fragment)
            if answer is None or item_index is None:
                return None
            seen_indexes.add(item_index)
            answers.append(
                {
                    "index": item_index,
                    "question_id": "",
                    "user_answer": answer,
                    "unmatched": True,
                }
            )
            continue
        answer = _extract_single_submission(
            fragment,
            items[item_index - 1],
            allow_invalid_multi_option=True,
        )
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


def _extract_unmatched_batch_answer(fragment: str) -> str | None:
    text = _strip_submission_prefix(fragment).strip(" \t\r\n；;，,。.!！?：:、")
    compact = re.sub(r"\s+", "", text).upper()
    match = re.fullmatch(r"[A-E](?:[、，,/／]*[A-E])*", compact)
    if not match:
        return None
    return _normalize_option_answer(
        compact,
        {"question_type": "choice", "options": {key: key for key in "ABCDE"}},
        allow_multi=True,
    )


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


def _extract_option_submission(
    message: str,
    question_context: dict[str, Any],
    *,
    allow_invalid_multi_option: bool = False,
) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None
    options = question_context.get("options") if isinstance(question_context, dict) else None
    question_type = str(question_context.get("question_type") or "").strip().lower()
    if not options and question_type not in {
        "choice",
        "single_choice",
        "multiple_choice",
        "multi_choice",
        "mcq",
    }:
        return None

    option_keys = _available_option_keys(question_context)
    if _looks_like_option_challenge_followup(text, question_context):
        return None
    if _looks_like_option_value_challenge_followup(text, question_context):
        return None

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
            normalized = _normalize_option_answer(
                match.group(1),
                question_context,
                allow_multi=allow_invalid_multi_option,
            )
            if normalized is not None:
                return normalized

    letter_answer = _extract_explicit_option_letter_submission(
        text,
        question_context,
        allow_invalid_multi_option=allow_invalid_multi_option,
    )
    if letter_answer is not None:
        return letter_answer

    value_answer = _extract_explicit_option_value_submission(text, question_context)
    if value_answer is not None:
        return value_answer

    if _message_contains_option_table(text, question_context):
        return None

    stripped = _LEADING_SUBMISSION_PREFIX.sub("", text).strip().strip("。.!！?，,：:")
    for fragment in re.split(r"[，,。.!！?；;\s]+", stripped):
        normalized = _normalize_option_answer(
            fragment,
            question_context,
            allow_multi=allow_invalid_multi_option,
        )
        if normalized is not None:
            return normalized
    return None


def _looks_like_option_challenge_followup(
    message: str,
    question_context: dict[str, Any],
) -> bool:
    text = str(message or "").strip()
    if not text:
        return False

    option_keys = _available_option_keys(question_context)
    compact = re.sub(r"\s+", "", text).upper().strip("。.!！?？；;，,")
    if not compact:
        return False

    letter = rf"[{option_keys}]"
    negative_markers = (
        r"(?:错在哪(?:里)?|哪(?:里)?错(?:了)?|哪里错(?:了)?|错因|问题在哪(?:里)?|"
        r"不对|错误|错|不是|不选|不能选|不该选|不行|不可以|为什么|为啥|怎么|咋)"
    )
    question_markers = r"(?:为什么|为啥|怎么|咋|哪里|哪)"
    response_constraint_tail = (
        r"(?:[。.!！?？；;，,、]*"
        r"(?:一句话|一两句话|简短(?:说|点)?|简单(?:说|点)?|说简单点|"
        r"(?:[0-9一二两三四五六七八九十]+)个字以内))?"
    )

    patterns = [
        rf"{question_markers}.{{0,12}}?(?:不是|不选|不能选|不该选|不对|错|错误)?{letter}.*",
        rf".{{0,20}}?{letter}.{{0,12}}?{question_markers}.{{0,12}}?(?:不对|错|错误|不是|不选|不能选|不行|不可以|对|正确){response_constraint_tail}",
        rf"{letter}.{{0,12}}?{question_markers}.{{0,12}}?(?:不对|错|错误|不是|不选|不能选|不行|不可以|对|正确){response_constraint_tail}",
        rf"{letter}.{{0,8}}?{negative_markers}{response_constraint_tail}",
        rf"{letter}.{{0,8}}?(?:不对吗|对吗|错吗|是不是错|是否错|是不是不对)",
        rf"{letter}.{{0,8}}?(?:怎么扣|怎么判|怎么评分|扣几|扣分|给几分|得几分|会扣|会判|会算).*",
        rf"(?:那|这个|这|那么|如果是|要是)?{letter}呢{response_constraint_tail}",
        rf".*?(?:不是要|不要|别|不想).{{0,12}}?(?:重新)?(?:提交|作答|回答|答|选|改成|改为){letter}.*",
        rf".*?(?:不是|不要|别|不想|不是要).{{0,12}}?(?:重新)?(?:提交|作答|回答|答|选|改成|改为){letter}.*?(?:想知道|解释|为什么|为啥|怎么|不对|错).*",
        rf".*?(?:不是|不要|别|不想|不是要).{{0,20}}?{letter}.{{0,20}}?(?:答案|提交|作答|回答|答|选|改成|改为).*?(?:想知道|解释|为什么|为啥|怎么|不对|错|扣分).*",
        rf".*?(?:如果|假如|要是|若).{{0,8}}?(?:我)?(?:选|答|填|写|是)?{letter}.{{0,20}}?(?:怎么扣|怎么判|怎么评分|扣几|扣分|给几分|得几分|能得|能拿|会扣|会判|会算|算错|得分|拿分).*",
        rf".*?(?:如果|假如|要是|若).{{0,8}}?(?:我)?(?:选|答|填|写|是)?{letter}.{{0,20}}?(?:对不对|是不是|是否|为什么|为啥|不对|错).*",
        rf".*?(?:不选|别选|不能选|不该选){letter}.{{0,20}}?(?:为什么|为啥|怎么|咋|不行|不对|错).*",
    ]
    return any(re.fullmatch(pattern, compact, flags=re.IGNORECASE) for pattern in patterns)


def _looks_like_option_value_challenge_followup(
    message: str,
    question_context: dict[str, Any],
) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    if _LEADING_SUBMISSION_PREFIX.match(text):
        return False
    if not re.search(
        r"(?:行不行|可不可以|可以吗|能不能|对不对|是不是|是否|为什么|为啥|怎么|咋|"
        r"错在哪(?:里)?|哪(?:里)?错(?:了)?|哪里错(?:了)?|问题在哪(?:里)?|不对|不行|不可以)",
        text,
    ):
        return False
    options = question_context.get("options") if isinstance(question_context, dict) else None
    if not isinstance(options, dict) or not options:
        return False

    normalized_text = _normalize_option_value_text(text)
    if not normalized_text:
        return False
    numeric_tokens = [
        _normalize_option_value_text(token)
        for token in re.findall(r"\d+(?:\.\d+)?(?:%|m|mm|cm|℃|°|年|d|天)?", text, flags=re.IGNORECASE)
    ]
    value_tokens = [token for token in numeric_tokens if len(token) >= 2]
    for value in options.values():
        normalized_option = _normalize_option_value_text(value)
        if not normalized_option:
            continue
        if normalized_option in normalized_text and len(normalized_option) >= 2:
            return True
        if any(token and token in normalized_option for token in value_tokens):
            return True
    return False


def _extract_explicit_option_letter_submission(
    message: str,
    question_context: dict[str, Any],
    *,
    allow_invalid_multi_option: bool = False,
) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None
    option_keys = _available_option_keys(question_context)
    letter_group = rf"([{option_keys}](?:[、，,/／\s]*[{option_keys}])*)"
    patterns = [
        rf"(?:我(?:实际|真正|就)?|实际|真正)?\s*(?:答案)?\s*"
        rf"(?<!多)(?<!单)(?<!项)(?<!候)"
        rf"(?:选了|选(?!择)|答了|答|回答了|回答|勾了|勾|填了|填|写了|写|圈了|圈)"
        rf"(?:的是|是|的)?\s*{letter_group}",
        rf"(?:我)?\s*(?:是不是|是否)\s*{letter_group}",
        rf"(?:答案|正确答案|标准答案)\s*(?:是|为)?\s*{letter_group}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        normalized = _normalize_option_answer(
            match.group(1),
            question_context,
            allow_multi=allow_invalid_multi_option,
        )
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


def _message_contains_option_table(message: str, question_context: dict[str, Any]) -> bool:
    text = str(message or "")
    if not text:
        return False
    hits = 0
    for key in _available_option_keys(question_context):
        if re.search(
            rf"(?:^|[\s\n\r，,。；;:：]){re.escape(key)}\s*[.、．\)]",
            text,
            flags=re.IGNORECASE,
        ):
            hits += 1
    return hits >= 2


def _normalize_option_answer(
    value: str,
    question_context: dict[str, Any],
    *,
    allow_multi: bool = False,
) -> str | None:
    token = str(value or "").strip().upper()
    if not token:
        return None
    letters = re.findall(r"[A-E]", token)
    if not letters:
        return None
    available = set(_available_option_keys(question_context))
    if any(letter not in available for letter in letters):
        return None
    if (
        len(set(letters)) > 1
        and not allow_multi
        and not _question_allows_multi_option_answer(question_context)
    ):
        return None
    normalized_letters: list[str] = []
    for letter in sorted(set(letters)):
        normalized_letters.append(letter)
    return "".join(normalized_letters)


def _extract_explicit_option_value_submission(
    message: str,
    question_context: dict[str, Any],
) -> str | None:
    options = question_context.get("options") if isinstance(question_context, dict) else None
    if not isinstance(options, dict) or not options:
        return None
    text = str(message or "").strip()
    if not text:
        return None

    match = re.search(
        r"(?:我(?:实际|真正|就)?|实际|真正)?\s*"
        r"(?:只)?\s*"
        r"(?<!多)(?<!单)(?<!项)(?<!候)"
        r"(?:勾选|勾了|勾|选了|选(?!择)|答了|答|回答了|回答|答案(?:是|为)?|填了|填|写了|写|圈了|圈)"
        r"(?:的是|是|的)?\s*"
        r"(.+)$",
        text,
    )
    if match:
        selected_text = match.group(1).strip()
    elif _LEADING_SUBMISSION_PREFIX.match(text):
        selected_text = _strip_submission_prefix(text)
    else:
        return None
    selected_text = re.split(
        r"(?:能拿满|能满|拿满|对吗|对不对|是不是|是否|直接判|判一下|判下|判|"
        r"直接批改|批改|打分|一句话|简短|别把|别算|漏没漏|错因|为什么|[？?])",
        selected_text,
        maxsplit=1,
    )[0].strip("。.!！?；;，,、 ")
    if not selected_text:
        return None

    option_value_by_key = {
        str(key).strip().upper()[:1]: _normalize_option_value_text(value)
        for key, value in options.items()
        if str(key).strip().upper()[:1] in {"A", "B", "C", "D", "E"}
    }
    if not option_value_by_key:
        return None

    selected_keys: list[str] = []
    unmatched: list[str] = []
    fragments = re.split(r"(?:[+＋、，,；;/／\s]+|和|与|以及|及)", selected_text)
    for fragment in fragments:
        normalized_fragment = _normalize_option_value_text(fragment)
        if not normalized_fragment:
            continue
        matched_key = ""
        for key, normalized_option in option_value_by_key.items():
            if not normalized_option:
                continue
            if (
                normalized_fragment == normalized_option
                or (len(normalized_fragment) >= 2 and normalized_fragment in normalized_option)
                or (len(normalized_option) >= 2 and normalized_option in normalized_fragment)
            ):
                matched_key = key
                break
        if matched_key:
            selected_keys.append(matched_key)
        elif len(normalized_fragment) >= 2:
            unmatched.append(normalized_fragment)

    if not selected_keys or unmatched:
        return None
    return _normalize_option_answer("".join(selected_keys), question_context)


def _normalize_option_value_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^[A-Ea-e][\.、．\)]\s*", "", text)
    return re.sub(
        r"[\s　，,。.!！?；;：:、/／+\-—_（）()【】\[\]<>《》\"'“”‘’]+",
        "",
        text,
    )


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
        "   包括前端交互生成的“提交作答，请批改：第1题：B；第2题：C”、"
        "“我已完成作答，请按当前题组逐题批改”等表述。\n"
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
    if normalized_answer is not None:
        for key, value in options.items():
            if _normalize_judgment_token(str(value or "").strip()) == normalized_answer:
                return str(key).strip().upper()[:1]
        return None

    normalized_value = _normalize_option_value_text(answer)
    if len(normalized_value) < 2:
        return None
    matched_keys: list[str] = []
    for key, value in options.items():
        normalized_option = _normalize_option_value_text(value)
        if not normalized_option:
            continue
        if (
            normalized_value == normalized_option
            or (len(normalized_value) >= 2 and normalized_value in normalized_option)
            or (len(normalized_option) >= 2 and normalized_option in normalized_value)
        ):
            matched_keys.append(str(key).strip().upper()[:1])
    unique_keys = sorted({key for key in matched_keys if key})
    return unique_keys[0] if len(unique_keys) == 1 else None


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


def _is_mcq_problem_submarker_line(line: str) -> bool:
    normalized = _normalize_mcq_line(line)
    return bool(
        re.match(
            r"^问题(?:\s*[一二两三四五六七八九十百零\d]+)?"
            r"(?:\s*[（(][^()（）]{0,40}[)）])?\s*(?:[:：]\s*.*)?$",
            normalized,
        )
    )


def _is_mcq_context_submarker_line(line: str) -> bool:
    normalized = _normalize_mcq_line(line).strip("【】[]")
    return bool(
        re.match(
            r"^(?:题目|题干|材料题|材料|案例背景|案例|背景资料|背景|情境|场景)"
            r"(?:\s*[一二两三四五六七八九十百零\d]+)?\s*(?:[:：]\s*.*)?$",
            normalized,
        )
    )


def _has_open_choice_context_before_problem(lines: list[str], problem_index: int) -> bool:
    for previous_index in range(problem_index - 1, -1, -1):
        previous_line = lines[previous_index]
        if _MCQ_OPTION_RE.match(previous_line):
            return False
        if _is_mcq_context_submarker_line(previous_line):
            return True
    return False


def _find_choice_question_starts(lines: list[str]) -> list[int]:
    starts: list[int] = []
    for index, line in enumerate(lines):
        if not _is_mcq_question_marker_line(line):
            continue
        if _is_mcq_problem_submarker_line(line) and _has_open_choice_context_before_problem(lines, index):
            continue
        if starts and _is_mcq_problem_submarker_line(line):
            previous_start = starts[-1]
            has_options_before_problem = any(
                _MCQ_OPTION_RE.match(candidate)
                for candidate in lines[previous_start + 1 : index]
            )
            if not has_options_before_problem:
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
            if _is_mcq_problem_submarker_line(line) and _has_open_choice_context_before_problem(prefix_lines, line_index):
                continue
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
