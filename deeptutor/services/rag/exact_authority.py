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
        r"(?:标准答案|正确答案|参考答案|答案)\s*(?:[是为]|[：:])\s*([A-E](?:\s*[、，,/／\s]?\s*[A-E])*)",
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
        # Case-study exact hits are content authority, not presentation authority.
        # The final responding layer must synthesize them into a user-facing answer.
        return False
    return False


def normalize_exact_authority_display_text(text: Any) -> str:
    value = str(text or "")
    value = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _strip_internal_markers(text: Any) -> str:
    return re.sub(
        r"\s*\[[A-Za-z_][A-Za-z0-9_-]*\]",
        "",
        normalize_exact_authority_display_text(text),
    ).strip()


def _clean_exact_analysis_for_display(text: Any) -> str:
    clean = _strip_internal_markers(text)
    clean = re.sub(r"^\s*【解析】\s*", "", clean)
    clean = re.sub(r"\n\s*【选项分析】\s*", "\n选项分析：\n", clean)
    clean = re.sub(r"(?m)^(\s*[A-E][\.、．\)]\s*)[✓✔✗×]\s*", r"\1", clean)
    clean = re.sub(r"(?m)^\s+([A-E][\.、．\)])", r"\1", clean)
    return clean.strip()


def _clean_case_answer_for_display(text: Any) -> str:
    clean = normalize_exact_authority_display_text(text)
    if clean.startswith("[") and clean.endswith("]"):
        clean = re.sub(r"^\[\s*['\"]?", "", clean)
        clean = re.sub(r"['\"]?\s*\]$", "", clean)
        clean = clean.replace("', '", "\n").replace('", "', "\n")
    return clean.strip()


def _clean_case_analysis_for_display(text: Any) -> str:
    clean = _clean_exact_analysis_for_display(text)
    clean = re.split(r"\n\s*选项分析\s*[：:]", clean, maxsplit=1)[0].strip()
    clean = re.sub(r"(?m)^\s*[A-E][\.、．\)]\s*本题为.*(?:无选项|无ABCD选项).*$", "", clean)
    return re.sub(r"\n{3,}", "\n\n", clean).strip()


def _case_score_point_hint(answer: str) -> str:
    if re.search(r"\d", answer):
        return "列式、代入数据、最终数值和单位都要完整。"
    return "关键词、判断结论和依据要同时写全。"


def _case_pitfall_hint(answer: str, analysis: str) -> str:
    source = f"{answer}\n{analysis}"
    if re.search(r"\d", source):
        return "不要漏写计价基数、税费/规费口径或最终单位。"
    if any(word in source for word in ("正确", "不正确", "不得", "禁止", "不妥")):
        return "不要只写对错，要补上对应理由。"
    return "不要照抄材料，必须落到题目要求的关键词。"


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


def _wants_brief_exact_authority_response(user_message: Any) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "一句话",
            "一两句",
            "别展开",
            "不要展开",
            "不用展开",
            "别废话",
            "少废话",
            "只说答案",
            "只要答案",
            "直接说",
            "不用解析",
            "不要解析",
            "不需要解析",
            "别讲全题",
            "不要讲全题",
            "不用讲全题",
            "别讲整题",
            "不用讲整题",
            "one sentence",
            "just answer",
            "no explanation",
        )
    )


def _extract_user_mcq_answer(user_message: Any) -> str:
    text = str(user_message or "").strip()
    patterns = (
        r"(?:我(?:实际|真正|就)?|实际|真正)?\s*(?:答案)?\s*(?:选了|选|答|填|写)(?:的是|是|的)?\s*([A-E](?:\s*[、，,/／\s]?\s*[A-E])*)",
        r"(?:我\s*)?(?:选|答|答案是|答案为)\s*([A-E](?:\s*[、，,/／\s]?\s*[A-E])*)",
        r"([A-E](?:\s*[、，,/／\s]?\s*[A-E])*)\s*(?:对不对|是不是|是否正确)",
        r"\b(?:choose|answer)\s*([A-E](?:\s*[,/ ]?\s*[A-E])*)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            normalized = _normalize_mcq_answer_letters(match.group(1))
            if normalized:
                return normalized
    return ""


def _build_brief_mcq_exact_authority_response(
    *,
    normalized_answer: str,
    answer_text: str,
    core_rule: str,
    user_message: Any,
) -> str:
    user_answer = _extract_user_mcq_answer(user_message)
    explanation = _sentence(core_rule)
    if user_answer:
        verdict = "对" if user_answer == normalized_answer else "不对"
        return f"{verdict}，标准答案是 {answer_text}，题库解析依据是：{explanation}".strip()
    return f"标准答案是 {answer_text}，题库解析依据是：{explanation}".strip()


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


def _numeric_value(text: str) -> int | None:
    match = re.search(r"\d+", str(text or ""))
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _mcq_review_option_rows(
    *,
    normalized_answer: str,
    option_values: dict[str, str],
    option_analysis: dict[str, str],
    summary: str,
) -> list[dict[str, str]]:
    correct_numbers = [
        _numeric_value(option_values.get(letter, ""))
        for letter in normalized_answer
        if option_values.get(letter)
    ]
    correct_numbers = [value for value in correct_numbers if value is not None]
    target_number = correct_numbers[0] if len(correct_numbers) == 1 else None
    rows: list[dict[str, str]] = []
    for letter in sorted(option_values):
        option_text = option_values[letter]
        is_correct = letter in normalized_answer
        source_reason = option_analysis.get(letter, "").strip()
        if source_reason:
            analysis = source_reason
        elif is_correct:
            analysis = f"{option_text} 对应题库标准答案；{_sentence(summary)}"
        else:
            option_number = _numeric_value(option_text)
            if target_number is not None and option_number is not None:
                relation = "低于" if option_number < target_number else "高于"
                analysis = (
                    f"{option_text} {relation}标准值 {target_number}，"
                    "不能满足题干中的“不应小于”要求。"
                )
            else:
                analysis = f"{option_text} 与题库标准答案 {normalized_answer} 不一致，不能作为本题结论。"
        rows.append(
            {
                "key": letter,
                "verdict": "正确" if is_correct else "不正确",
                "analysis": analysis,
            }
        )
    return rows


def build_mcq_review_notes_from_exact_question(exact_question: dict[str, Any]) -> dict[str, Any]:
    """Project exact-question facts into the structured question-review payload.

    This is a read projection of qbank/RAG authority. It does not decide scoring
    truth; it only prevents the UI from inventing generic option explanations.
    """

    answer = str(exact_question.get("correct_answer") or "").strip()
    normalized_answer = _normalize_mcq_answer_letters(answer)
    option_values = _mcq_option_value_map(exact_question.get("options"))
    analysis = _clean_exact_analysis_for_display(exact_question.get("analysis"))
    summary, option_analysis = _split_mcq_analysis(analysis)
    if not normalized_answer or not option_values:
        return {}

    correct_labels = [
        f"{letter}. {option_values[letter]}"
        for letter in normalized_answer
        if option_values.get(letter)
    ]
    correct_text = "、".join(correct_labels) if correct_labels else normalized_answer
    question = normalize_exact_authority_display_text(
        exact_question.get("stem") or exact_question.get("question") or ""
    )
    scoring_subject = _sentence(question or "本题题干")
    # 通用投影器：方法脚手架只从本题自身字段（题干 / 标准答案）派生，不假设答案
    # 形态（数值题 / 概念题皆可），不硬编码任何单一题型的字面量。原实现把“混凝土
    # 保护层 / 规范数值”写死进 pitfalls 与 mnemonic，会跨题泄露到脚手架、养护等
    # 概念题上（通用闸落不进窄模式就吐罐头模板的病）。逐项真值仍在 option_analysis
    # ——那才是对题库解析的忠实投影。
    scoring_points = [
        f"圈定题干限定的对象与条件：{scoring_subject}",
        f"对照题库标准答案锁定关键依据：{correct_text}。",
        "逐项比对题库解析，排除与之不符的干扰项。",
    ]
    pitfalls = [
        "被表述相近的干扰项带走，忽略题干限定的对象与条件。",
        "只记住结论本身，没有回到题库解析里的判定依据。",
    ]
    mnemonic = f"先圈对象与条件，再对照题库答案：{correct_text}。"

    return {
        "option_analysis": _mcq_review_option_rows(
            normalized_answer=normalized_answer,
            option_values=option_values,
            option_analysis=option_analysis,
            summary=summary,
        ),
        "scoring_points": scoring_points,
        "pitfalls": pitfalls,
        "mnemonic": mnemonic,
    }


def build_exact_authority_response(
    exact_question: dict[str, Any],
    *,
    user_message: Any = "",
) -> str:
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
        if _wants_brief_exact_authority_response(user_message):
            return _build_brief_mcq_exact_authority_response(
                normalized_answer=normalized_answer,
                answer_text=answer_text,
                core_rule=core_rule,
                user_message=user_message,
            )
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
        answer = normalize_exact_authority_display_text(exact_question.get("correct_answer"))
        analysis = normalize_exact_authority_display_text(exact_question.get("analysis"))
        return "\n\n".join([item for item in [answer, analysis] if item]).strip()
    if answer_kind == "case_study":
        covered = exact_question.get("covered_subquestions")
        if not isinstance(covered, list) or not covered:
            return ""
        sections: list[str] = ["## 标准作答"]
        for item in covered:
            if not isinstance(item, dict):
                continue
            display_index = str(item.get("display_index") or "").strip()
            prompt = normalize_exact_authority_display_text(item.get("prompt"))
            answer = _clean_case_answer_for_display(item.get("authoritative_answer"))
            analysis = _clean_case_analysis_for_display(item.get("analysis"))
            heading = f"### 第{display_index}问" if display_index else "### 作答"
            block: list[str] = [heading]
            if prompt:
                block.append(f"**题目：** {prompt}")
            if answer:
                block.append(f"**结论：** {answer}")
            if analysis:
                block.append(f"**判断依据：** {analysis}")
            if answer:
                block.append(f"**采分点：** {_case_score_point_hint(answer)}")
                block.append(f"**易错点：** {_case_pitfall_hint(answer, analysis)}")
            if len(block) > 1:
                sections.append("\n\n".join(block))
        sections.append("## 记忆口诀\n\n先判对错，再写依据；计算题先列式，再代数，最后带单位。")
        return "\n\n".join(sections).strip()
    return ""


def render_case_exact_authority_response(authority: dict[str, Any]) -> str:
    covered = authority.get("covered_subquestions") or []
    lines: list[str] = []
    for item in covered:
        if not isinstance(item, dict):
            continue
        display_index = str(item.get("display_index") or "").strip() or "?"
        answer = normalize_exact_authority_display_text(item.get("authoritative_answer"))
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
    return None
