from __future__ import annotations

import re
from typing import Any


_HARD_SCORE_RE = re.compile(
    r"(预计得分|满分\s*\d+(?:\.\d+)?\s*分|\d+(?:\.\d+)?\s*分\s*/|"
    r"/\s*(?:满分)?\s*\d+(?:\.\d+)?\s*分|给\s*\d+(?:\.\d+)?\s*分|"
    r"扣\s*\d+(?:\.\d+)?\s*分)"
)
_OFFICIAL_GRADING_RE = re.compile(
    r"(采分点批改|采分点拆解|命中采分点|漏分点|漏采分点|缺一个采分点|"
    r"判错|阅卷|给分|扣分|满分)"
)
_DIAGNOSTIC_ONLY_MARKER = "本次不硬估标准分"
_CASE_SCORE_AUTHORITY_KINDS = {"case", "case_study", "case_bundle", "written", "subjective"}


def case_grading_score_authority_available(runtime_metadata: dict[str, Any] | None) -> bool:
    """Return True only when the current case turn owns score authority."""

    metadata = runtime_metadata if isinstance(runtime_metadata, dict) else {}
    if str(metadata.get("question_lifecycle_scene") or "").strip() != "case_grading":
        return False
    for key in ("_prefetched_exact_question", "exact_question"):
        exact_question = metadata.get(key)
        if not isinstance(exact_question, dict) or not exact_question:
            continue
        if _exact_question_has_case_score_authority(exact_question):
            return True
    return False


def _exact_question_has_case_score_authority(exact_question: dict[str, Any]) -> bool:
    answer_kind = str(exact_question.get("answer_kind") or "").strip().lower()
    case_bundle = exact_question.get("case_bundle")
    if isinstance(case_bundle, dict) and case_bundle:
        return True
    if exact_question.get("grading_key") or exact_question.get("covered_subquestions"):
        return True
    if answer_kind not in _CASE_SCORE_AUTHORITY_KINDS:
        return False
    return bool(exact_question.get("correct_answer") or exact_question.get("authoritative_answer"))


def should_demote_case_grading_hard_score(
    response: str | None,
    *,
    runtime_metadata: dict[str, Any] | None,
) -> bool:
    """Detect a case-grading official-score claim produced without authority."""

    metadata = runtime_metadata if isinstance(runtime_metadata, dict) else {}
    if str(metadata.get("question_lifecycle_scene") or "").strip() != "case_grading":
        return False
    if case_grading_score_authority_available(metadata):
        return False
    text = str(response or "")
    if _DIAGNOSTIC_ONLY_MARKER in text:
        return False
    return _HARD_SCORE_RE.search(text) is not None or _OFFICIAL_GRADING_RE.search(text) is not None


def build_case_grading_diagnostic_only_response(user_message: str) -> str:
    """Student-facing fail-open answer when case score authority is missing."""

    answer = _extract_user_answer(user_message)
    answer_line = f"\n\n你当前作答：{answer}" if answer else ""
    return (
        "## 评分口径\n"
        "提分诊断（本轮没有命中题库原题、标准答案或结构化采分点）\n\n"
        "## 预计得分\n"
        "本次不硬估标准分。"
        f"{answer_line}\n\n"
        "## 先看你的作答\n"
        "- 可以先保留你已经写出的判断和关键参数。\n"
        "- 但案例题是否给分，必须以原题标准答案、分值和采分点为准；本轮没有这份 authority，不能把诊断包装成官方阅卷。\n\n"
        "## 下一步\n"
        "把题卡、题号、标准答案或采分点一起发来，我再按标准采分点逐条批改；如果只有题面和你的作答，我可以继续帮你改成更像考试得分表达。"
    )


def _extract_user_answer(user_message: str) -> str:
    text = str(user_message or "").strip()
    if not text:
        return ""
    match = re.search(r"(?:我的答案|我答|答案)\s*[：:]\s*(.*)", text, flags=re.S)
    if not match:
        return ""
    answer = match.group(1).strip()
    answer = re.split(r"(?:请|帮我|麻烦)?(?:按|帮|给|批改|估分|打分|判分)", answer, maxsplit=1)[0]
    return answer.strip(" \n\t，。；;")[:160]
