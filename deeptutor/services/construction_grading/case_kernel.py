from __future__ import annotations

import re
from typing import Any

from deeptutor.services.construction_grading.normalization import (
    coerce_jsonish,
    compact_text,
    is_meaningful,
    normalize_keyword_list,
)
from deeptutor.services.construction_grading.schema import (
    CaseGradingMode,
    CaseGradingResult,
    CaseRubricItemResult,
    EvidenceRef,
    GradingErrorEvent,
)

_VAGUE_PHRASES = ("加强管理", "加强现场管理", "严格检查", "注意安全", "落实责任", "提高意识")


class CaseGradingSkillKernel:
    """Minimal source-grounded kernel for subjective construction case grading."""

    def grade(
        self,
        *,
        question_row: dict[str, Any],
        user_answer: str,
        evidence_rows: list[dict[str, Any]] | None = None,
    ) -> CaseGradingResult:
        row = dict(question_row or {})
        evidence = _question_evidence_refs(row)
        evidence.extend(_external_evidence_refs(evidence_rows or []))
        rubric_specs, mode = _build_rubric_specs(row)
        if not rubric_specs:
            rubric_specs = _open_skill_specs(row)
            mode = "open_skill"

        answer_text = str(user_answer or "").strip()
        item_results: list[CaseRubricItemResult] = []
        error_events: list[GradingErrorEvent] = []
        for spec in rubric_specs:
            keywords = list(spec["keywords"])
            matched = [keyword for keyword in keywords if keyword and keyword in answer_text]
            status = "full" if matched else "miss"
            max_score = float(spec["score"])
            awarded = max_score if matched else 0.0
            item_results.append(
                CaseRubricItemResult(
                    criterion=str(spec["criterion"]),
                    max_score=max_score,
                    awarded_score=awarded,
                    status=status,
                    keywords=keywords,
                    evidence_text="、".join(matched),
                    source_fields=list(spec["source_fields"]),
                )
            )
            if not matched:
                error_events.append(
                    GradingErrorEvent(
                        error_code="E02",
                        severity=0.8,
                        concept_tag=str(row.get("node_code") or ""),
                        evidence=str(spec["criterion"]),
                        diagnosis=f"漏写采分点：{spec['criterion']}",
                    )
                )

        if any(phrase in answer_text for phrase in _VAGUE_PHRASES) and any(
            item.status == "miss" for item in item_results
        ):
            error_events.append(
                GradingErrorEvent(
                    error_code="E04",
                    severity=0.6,
                    concept_tag=str(row.get("node_code") or ""),
                    evidence=answer_text[:80],
                    diagnosis="答案存在口号化表达，应改成具体程序、条件或关键词。",
                )
            )

        score_awarded = sum(item.awarded_score for item in item_results)
        max_score = sum(item.max_score for item in item_results)
        rewrite = _build_rewrite_answer(item_results)
        return CaseGradingResult(
            question_id=str(row.get("id") or row.get("original_id") or row.get("question_id") or "").strip(),
            grading_mode=mode,
            score_awarded=score_awarded,
            max_score=max_score,
            rubric_items=item_results,
            evidence_refs=evidence,
            error_events=error_events,
            rewrite_answer=rewrite,
            next_training_signal={
                "concept": str(row.get("node_code") or "").strip(),
                "focus": str(row.get("testing_focus") or "").strip(),
                "mode": mode,
            },
        )


def _question_evidence_refs(row: dict[str, Any]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for field in (
        "grading_rubric",
        "correct_answer",
        "analysis",
        "grading_keywords",
        "structured_rules",
        "source_meta",
        "node_code",
        "testing_focus",
    ):
        value = coerce_jsonish(row.get(field))
        if is_meaningful(value):
            refs.append(EvidenceRef(source="questions_bank", field=field, value=value))
    return refs


def _external_evidence_refs(rows: list[dict[str, Any]]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or row.get("source_type") or "kb_chunks").strip()
        field = str(row.get("field") or row.get("content_type") or "content").strip()
        value = row.get("text") or row.get("rag_content") or row.get("content") or row.get("metadata")
        if is_meaningful(value):
            refs.append(EvidenceRef(source=source, field=field, value=value))
    return refs


def _build_rubric_specs(row: dict[str, Any]) -> tuple[list[dict[str, Any]], CaseGradingMode]:
    curated = coerce_jsonish(row.get("grading_rubric"))
    if isinstance(curated, list) and curated:
        specs: list[dict[str, Any]] = []
        for index, item in enumerate(curated, 1):
            if not isinstance(item, dict):
                continue
            criterion = compact_text(item.get("criterion") or item.get("name") or item.get("required_meaning"))
            keywords = normalize_keyword_list(item.get("keywords") or item.get("acceptable_expressions"))
            if not keywords and criterion:
                keywords = [criterion]
            if criterion and keywords:
                specs.append(
                    {
                        "criterion": criterion,
                        "keywords": keywords,
                        "score": float(item.get("score") or item.get("max_score") or 1),
                        "source_fields": ["grading_rubric"],
                    }
                )
        if specs:
            return specs, "curated_rubric"

    projected = _project_specs_from_existing_fields(row)
    return projected, "projected_rubric"


def _project_specs_from_existing_fields(row: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for keyword in normalize_keyword_list(row.get("grading_keywords")):
        _append_spec(
            specs,
            criterion=keyword,
            keywords=[keyword],
            source_field="grading_keywords",
        )

    structured = coerce_jsonish(row.get("structured_rules"))
    if isinstance(structured, list):
        for rule in structured:
            if not isinstance(rule, dict):
                continue
            requirement = compact_text(rule.get("requirement") or rule.get("result"))
            keywords = _keywords_from_text(requirement)
            if requirement and keywords:
                _append_spec(
                    specs,
                    criterion=requirement,
                    keywords=keywords,
                    source_field="structured_rules",
                )

    if not specs:
        for line in _answer_lines(row.get("correct_answer")):
            keywords = _keywords_from_text(line)
            if line and keywords:
                _append_spec(specs, criterion=line, keywords=keywords, source_field="correct_answer")
    return specs


def _open_skill_specs(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = compact_text(row.get("correct_answer") or row.get("analysis") or row.get("question_stem"))
    keywords = _keywords_from_text(text)
    if not keywords:
        return []
    return [
        {
            "criterion": keyword,
            "keywords": [keyword],
            "score": 1.0,
            "source_fields": ["open_skill_projection"],
        }
        for keyword in keywords[:3]
    ]


def _append_spec(
    specs: list[dict[str, Any]],
    *,
    criterion: str,
    keywords: list[str],
    source_field: str,
) -> None:
    clean_criterion = compact_text(criterion)
    clean_keywords = [keyword for keyword in keywords if keyword]
    if not clean_criterion or not clean_keywords:
        return
    if any(existing["criterion"] == clean_criterion for existing in specs):
        return
    specs.append(
        {
            "criterion": clean_criterion,
            "keywords": clean_keywords,
            "score": 1.0,
            "source_fields": [source_field],
        }
    )


def _answer_lines(value: Any) -> list[str]:
    text = str(coerce_jsonish(value) or "")
    return [compact_text(line) for line in re.split(r"[\n。；;]+", text) if compact_text(line)]


def _keywords_from_text(text: Any) -> list[str]:
    compact = compact_text(text)
    if not compact:
        return []
    quoted = re.findall(r"[“\"'‘]([^“\"'’]{2,24})[”\"'’]", compact)
    keywords = normalize_keyword_list(quoted)
    if keywords:
        return keywords[:5]
    candidates = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,18}", compact)
    stopwords = {"条件", "结果", "符合", "规范", "要求", "判定", "应进行", "应按规定"}
    result: list[str] = []
    for candidate in candidates:
        if candidate in stopwords or candidate.isdigit():
            continue
        if candidate not in result:
            result.append(candidate)
    return result[:5]


def _build_rewrite_answer(items: list[CaseRubricItemResult]) -> str:
    missed_or_hit = [item.criterion for item in items if item.criterion]
    if not missed_or_hit:
        return ""
    return "；".join(missed_or_hit)
