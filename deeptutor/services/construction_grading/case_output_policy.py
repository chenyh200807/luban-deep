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
# An explicit case-style score *verdict* (not a bare 采分点 teaching label, a
# rubric like "满分100分", or a unit price like "5分/平米"). Used only as the
# safety net for unclassified turns that escaped case_grading scene derivation;
# matches "不得分", "得 4 分", "4分/满分5分", "0分/5分", "**0分。**", "0 个采分点",
# "预计得分". The bolded ``**N分**`` arm catches a forced-score verdict like
# R3-16 ("**0分。**") while leaving unbolded rubric/unit-price text alone.
_NO_AUTHORITY_CASE_SCORE_RE = re.compile(
    r"(不得分"
    r"|得\s*\d+(?:\.\d+)?\s*分"
    r"|\d+(?:\.\d+)?\s*分\s*[/／]\s*(?:满分\s*)?\d"
    r"|\*\*\s*\d+(?:\.\d+)?\s*分\s*[。.！!]"
    r"|\d+\s*个?\s*采分点"
    r"|得分\s*[:：]\s*\d"
    r"|预计得分)"
)


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
    if _has_case_score_evidence(exact_question.get("case_bundle")):
        return True
    if _has_case_score_evidence(exact_question.get("grading_key")):
        return True
    if _has_case_score_evidence(exact_question.get("covered_subquestions")):
        return True
    if answer_kind not in _CASE_SCORE_AUTHORITY_KINDS:
        return False
    return bool(exact_question.get("correct_answer") or exact_question.get("authoritative_answer"))


def _has_case_score_evidence(value: Any) -> bool:
    if isinstance(value, list):
        return any(_has_case_score_evidence(item) for item in value)
    if not isinstance(value, dict) or not value:
        return False

    for key in ("authoritative_answer", "correct_answer", "standard_answer", "reference_answer"):
        if str(value.get(key) or "").strip():
            return True

    for key in ("scoring_points", "grading_points", "score_points"):
        if _has_non_empty_collection(value.get(key)):
            return True

    for key in ("rubric", "grading_rubric", "grading_key", "covered_subquestions", "case_bundle"):
        if _has_case_score_evidence(value.get(key)):
            return True

    return False


def _has_non_empty_collection(value: Any) -> bool:
    if isinstance(value, list):
        return any(item not in (None, "", [], {}) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return False


def _has_any_grading_authority(metadata: dict[str, Any]) -> bool:
    """True when the turn owns a real graded-question authority of any kind.

    Protects legitimate MCQ/active-object grading (which carries an authoritative
    exact question or a single-question active object) from the unclassified-turn
    safety net below.
    """

    if metadata.get("authority_applied") is True:
        return True
    for key in ("_prefetched_exact_question", "exact_question"):
        exact_question = metadata.get(key)
        if isinstance(exact_question, dict) and exact_question:
            return True
    active_object = metadata.get("active_object")
    if isinstance(active_object, dict) and str(active_object.get("object_type") or "").strip() == "single_question":
        return True
    return False


def should_demote_case_grading_hard_score(
    response: str | None,
    *,
    runtime_metadata: dict[str, Any] | None,
) -> bool:
    """Detect a case-grading official-score claim produced without authority."""

    metadata = runtime_metadata if isinstance(runtime_metadata, dict) else {}
    text = str(response or "")
    if _DIAGNOSTIC_ONLY_MARKER in text:
        return False

    scene = str(metadata.get("question_lifecycle_scene") or "").strip()
    if scene == "case_grading":
        if case_grading_score_authority_available(metadata):
            return False
        return _HARD_SCORE_RE.search(text) is not None or _OFFICIAL_GRADING_RE.search(text) is not None

    # Safety net for the P1-A leak: an unclassified turn (no lifecycle scene) that
    # still asserts an official case-style score verdict while owning no grading
    # authority of any kind — e.g. an out-of-bank pasted case the lifecycle did
    # not tag as case_grading. Recognized non-case scenes (mcq_grading, …) are
    # handled by their own guards and are intentionally excluded here.
    if not scene and not _has_any_grading_authority(metadata):
        return _NO_AUTHORITY_CASE_SCORE_RE.search(text) is not None
    return False


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
