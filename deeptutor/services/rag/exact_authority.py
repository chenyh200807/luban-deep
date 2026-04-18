from __future__ import annotations

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


def build_exact_authority_response(exact_question: dict[str, Any]) -> str:
    answer_kind = str(exact_question.get("answer_kind") or "").strip().lower()
    if answer_kind == "mcq":
        answer = str(exact_question.get("correct_answer") or "").strip()
        analysis = str(exact_question.get("analysis") or "").strip()
        parts = []
        if answer:
            parts.append(f"标准答案：{answer}")
        if analysis:
            parts.append(f"解析：{analysis}")
        return "\n".join(parts).strip()
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
