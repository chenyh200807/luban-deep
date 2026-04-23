from __future__ import annotations

import re
from typing import Any


def _normalize_mcq_answer_letters(answer: Any) -> str:
    if isinstance(answer, list):
        raw = "".join(str(item or "") for item in answer)
    elif isinstance(answer, dict):
        raw = "".join(str(value or "") for value in answer.values())
    else:
        raw = str(answer or "")
    letters = "".join(ch for ch in raw.upper() if "A" <= ch <= "E")
    return "".join(sorted(set(letters)))


def _compact_text(text: Any) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE).upper()


def _extract_marked_mcq_answers(text: str) -> list[str]:
    answers: list[str] = []
    for match in re.finditer(
        r"(?:标准答案|正确答案|参考答案|答案)\s*[：:]\s*([A-E](?:\s*[、，,/／\s]?\s*[A-E])*)",
        str(text or ""),
        flags=re.IGNORECASE,
    ):
        normalized = _normalize_mcq_answer_letters(match.group(1))
        if normalized:
            answers.append(normalized)
    return answers


def exact_authority_response_matches(
    exact_question: dict[str, Any],
    response: str,
) -> bool:
    answer_kind = str(exact_question.get("answer_kind") or "").strip().lower()
    if answer_kind != "mcq":
        return True
    expected_answer = _normalize_mcq_answer_letters(exact_question.get("correct_answer"))
    if not expected_answer:
        return False
    marked_answers = _extract_marked_mcq_answers(response)
    if not marked_answers or any(answer != expected_answer for answer in marked_answers):
        return False
    if re.search(r"(?:题干|选项)\s*[：:]", str(response or "")):
        return False

    authority_text_parts = [
        str(exact_question.get("stem") or ""),
        str(exact_question.get("correct_answer") or ""),
        str(exact_question.get("analysis") or ""),
    ]
    response_compact = _compact_text(response)
    option_values: dict[str, str] = {}
    raw_options = exact_question.get("options")
    if isinstance(raw_options, dict):
        option_values = {
            str(key or "").strip().upper(): str(value or "").strip()
            for key, value in raw_options.items()
        }
    elif isinstance(raw_options, list):
        for item in raw_options:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or item.get("label") or "").strip().upper()
            value = str(item.get("value") or item.get("text") or "").strip()
            if key and value:
                option_values[key] = value

    authority_text_parts.extend(option_values.values())
    authority_text = "".join(authority_text_parts)
    max_rendered_chars = max(480, len(authority_text) * 4)
    if len(str(response or "")) > max_rendered_chars:
        return False

    for letter in expected_answer:
        value = option_values.get(letter, "")
        if value and _compact_text(value) not in response_compact:
            return False
    return True


def extract_exact_question_authority_from_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    exact = metadata.get("exact_question") if isinstance(metadata, dict) else None
    if not isinstance(exact, dict):
        return None

    normalized = dict(exact)
    normalized["confidence"] = float(exact.get("confidence") or 0.0)
    case_bundle = normalized.get("case_bundle")
    covered_subquestions = normalized.get("covered_subquestions") or []
    answer_kind = str(normalized.get("answer_kind") or "").strip().lower()

    if case_bundle or covered_subquestions or answer_kind in {"case_study", "case_bundle"}:
        if isinstance(case_bundle, dict):
            normalized["covered_subquestions"] = (
                case_bundle.get("covered_subquestions") or covered_subquestions or []
            )
            normalized["missing_subquestions"] = (
                case_bundle.get("missing_subquestions")
                or normalized.get("missing_subquestions")
                or []
            )
            normalized["query_subquestions"] = (
                case_bundle.get("query_subquestions")
                or normalized.get("query_subquestions")
                or []
            )
            normalized["coverage_ratio"] = float(
                case_bundle.get("coverage_ratio")
                or normalized.get("coverage_ratio")
                or 0.0
            )
            normalized["coverage_state"] = str(
                case_bundle.get("coverage_state")
                or normalized.get("coverage_state")
                or "partial"
            )
        if normalized.get("covered_subquestions"):
            normalized["authority_kind"] = "case_study"
            return normalized

    authoritative_answer = _normalize_mcq_answer_letters(exact.get("correct_answer"))
    if authoritative_answer:
        normalized["authority_kind"] = "mcq"
        normalized["authoritative_answer"] = authoritative_answer
        return normalized

    free_text_answer = str(exact.get("correct_answer") or "").strip()
    if free_text_answer:
        normalized["authority_kind"] = "free_text"
        normalized["authoritative_answer"] = free_text_answer
        return normalized
    return None


def should_force_exact_authority(exact_question: dict[str, Any]) -> bool:
    answer_kind = str(exact_question.get("answer_kind") or "").strip().lower()
    if answer_kind in {"mcq", "free_text"}:
        return True
    if answer_kind == "case_study":
        coverage_ratio = float(exact_question.get("coverage_ratio") or 0.0)
        missing_subquestions = exact_question.get("missing_subquestions")
        if coverage_ratio >= 0.999:
            return True
        if isinstance(missing_subquestions, list) and not missing_subquestions:
            return True
        if str(exact_question.get("coverage_state") or "").strip() == "multi_subquestion_exact":
            return True
    return False


def _strip_internal_markers(text: Any) -> str:
    return re.sub(r"\s*\[[A-Za-z_][A-Za-z0-9_-]*\]", "", str(text or "")).strip()


def _clean_exact_analysis_for_display(text: Any) -> str:
    clean = _strip_internal_markers(text)
    clean = re.sub(r"^\s*【解析】\s*", "", clean)
    clean = re.sub(r"\n\s*【选项分析】\s*", "\n选项分析：\n", clean)
    clean = re.sub(r"(?m)^(\s*[A-E][\.、．\)]\s*)[✓✔✗×]\s*", r"\1", clean)
    clean = re.sub(r"(?m)^\s+([A-E][\.、．\)])", r"\1", clean)
    return clean.strip()


def _mcq_option_value_map(options: Any) -> dict[str, str]:
    option_values: dict[str, str] = {}
    if isinstance(options, dict):
        iterable = [{"key": key, "value": value} for key, value in options.items()]
    elif isinstance(options, list):
        iterable = options
    else:
        return option_values

    for item in iterable:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("label") or "").strip().upper()
        value = str(item.get("value") or item.get("text") or "").strip()
        if key and value:
            option_values[key] = value
    return option_values


def _split_mcq_analysis(analysis: str) -> tuple[str, dict[str, str]]:
    parts = re.split(r"\n\s*选项分析\s*[：:]\s*\n?", str(analysis or ""), maxsplit=1)
    summary = parts[0].strip()
    option_analysis: dict[str, str] = {}
    if len(parts) < 2:
        return summary, option_analysis

    option_block = parts[1].strip()
    for match in re.finditer(
        r"(?ms)^\s*([A-E])[\.\、．\)]\s*(.*?)(?=^\s*[A-E][\.\、．\)]|\Z)",
        option_block,
    ):
        letter = match.group(1).upper()
        text = re.sub(r"\s+", " ", match.group(2)).strip()
        if text:
            option_analysis[letter] = text
    return summary, option_analysis


def _format_mcq_answer_with_options(answer: str, option_values: dict[str, str]) -> str:
    normalized_answer = _normalize_mcq_answer_letters(answer)
    selected_options = [
        f"{letter}. {option_values[letter]}"
        for letter in normalized_answer
        if option_values.get(letter)
    ]
    if selected_options:
        return f"{normalized_answer}（{'、'.join(selected_options)}）"
    return normalized_answer or str(answer or "").strip()


def _sentence(text: str) -> str:
    clean = str(text or "").strip()
    if not clean:
        return ""
    return clean if clean[-1] in "。！？.!?" else f"{clean}。"


def _build_mcq_pitfall_section(
    *,
    normalized_answer: str,
    option_values: dict[str, str],
    option_analysis: dict[str, str],
) -> str:
    wrong_letters = [letter for letter in sorted(option_values) if letter not in normalized_answer]
    rows: list[str] = []
    for letter in wrong_letters:
        reason = option_analysis.get(letter)
        label = f"{letter}. {option_values.get(letter, '').strip()}".strip()
        if reason:
            rows.append(f"| {label} | {reason} |")
    if rows:
        return "\n".join(["| 易错项 | 题库依据 |", "| :--- | :--- |", *rows])

    if wrong_letters:
        wrong_labels = [
            f"{letter}. {option_values[letter]}"
            for letter in wrong_letters
            if option_values.get(letter)
        ]
        wrong_text = "、".join(wrong_labels) if wrong_labels else "其他选项"
        return "\n".join(
            [
                "| 易错点 | 正确抓手 |",
                "| :--- | :--- |",
                f"| 答案范围扩大 | 标准答案只包含 {normalized_answer}，不要把 {wrong_text} 误并入答案。 |",
            ]
        )

    return "\n".join(
        [
            "| 易错点 | 正确抓手 |",
            "| :--- | :--- |",
            f"| 自行改判 | 以题库标准答案 {normalized_answer} 为准，不要脱离原题解析扩写。 |",
        ]
    )


def build_exact_authority_response(exact_question: dict[str, Any]) -> str:
    answer_kind = str(exact_question.get("answer_kind") or "").strip().lower()
    if answer_kind == "mcq":
        answer = str(exact_question.get("correct_answer") or "").strip()
        normalized_answer = _normalize_mcq_answer_letters(answer)
        option_values = _mcq_option_value_map(exact_question.get("options"))
        analysis = _clean_exact_analysis_for_display(exact_question.get("analysis"))
        summary, option_analysis = _split_mcq_analysis(analysis)
        answer_text = _format_mcq_answer_with_options(answer, option_values)
        if not answer_text:
            return _sentence(summary)

        correct_labels = [
            f"{letter}. {option_values[letter]}"
            for letter in normalized_answer
            if option_values.get(letter)
        ]
        wrong_labels = [
            f"{letter}. {option_values[letter]}"
            for letter in sorted(option_values)
            if letter not in normalized_answer and option_values.get(letter)
        ]
        correct_text = "、".join(correct_labels) if correct_labels else normalized_answer
        wrong_text = "、".join(wrong_labels) if wrong_labels else "非标准答案选项"
        core_rule = summary or f"本题以题库标准答案 {answer_text} 为准。"
        memory_hook = (
            " + ".join(option_values[letter] for letter in normalized_answer if option_values.get(letter))
            or normalized_answer
        )

        sections = [
            "## 📊 阅卷结论",
            f"这道题已命中题库原题。标准答案：{answer_text}。本题核心是先锁定题库给出的标准选项，再围绕原解析理解判断依据。",
            "",
            "## 🧐 解析",
            _sentence(core_rule),
            "",
            "## ⚠️ 易错点",
            _build_mcq_pitfall_section(
                normalized_answer=normalized_answer,
                option_values=option_values,
                option_analysis=option_analysis,
            ),
            "",
            "## 🎯 核心要点",
            f"- ✅ 命中：{correct_text}是本题题库标准答案。",
            f"- ❌ 遗漏：不要把{wrong_text}当作本题标准答案；判断时要回到题库解析给出的范围。",
            "",
            "## 🚀 下一步建议",
            f"现在把“{memory_hook}”这个答案抓手抄写 1 遍，再做 1 道同类多选题。",
            "",
            f"📌 收尾提醒：本题最终以题库原题的标准答案为 {answer_text}，解释只能服务于这个结论。",
        ]
        return "\n".join(sections).strip()
    if answer_kind == "free_text":
        answer = str(exact_question.get("correct_answer") or "").strip()
        analysis = str(exact_question.get("analysis") or "").strip()
        return "\n\n".join([item for item in [answer, analysis] if item]).strip()
    if answer_kind == "case_study":
        covered = exact_question.get("covered_subquestions")
        if not isinstance(covered, list) or not covered:
            return ""
        lines: list[str] = []
        for item in covered:
            if not isinstance(item, dict):
                continue
            display_index = str(item.get("display_index") or "").strip()
            answer = str(item.get("authoritative_answer") or "").strip()
            analysis = str(item.get("analysis") or "").strip()
            prefix = f"{display_index}. " if display_index else ""
            if answer:
                lines.append(f"{prefix}{answer}")
            if analysis:
                lines.append(f"解析：{analysis}")
        return "\n".join(lines).strip()
    return ""


def render_case_exact_authority_response(authority: dict[str, Any]) -> str:
    covered = authority.get("covered_subquestions") or []
    lines: list[str] = []
    for item in covered:
        if not isinstance(item, dict):
            continue
        display_index = str(item.get("display_index") or "").strip() or "?"
        answer = str(item.get("authoritative_answer") or "").strip()
        if not answer:
            continue
        lines.append(f"{display_index}. {answer}")
    return "\n\n".join(lines).strip()


def resolve_exact_authority_response_from_authority(
    authority: dict[str, Any] | None,
) -> str | None:
    if not isinstance(authority, dict):
        return None
    authority_kind = str(authority.get("authority_kind") or "").strip().lower()
    if authority_kind != "case_study":
        return None
    missing = authority.get("missing_subquestions") or []
    coverage_ratio = float(authority.get("coverage_ratio") or 0.0)
    covered = authority.get("covered_subquestions") or []
    if not covered:
        return None
    if missing and coverage_ratio < 0.999:
        return None
    rendered = render_case_exact_authority_response(authority)
    return rendered or None
