from __future__ import annotations

import logging
import re
from collections.abc import Callable
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
_OVERBROAD_GRADING_KEYWORDS = {"原则", "材料"}
logger = logging.getLogger(__name__)


class CaseGradingSkillKernel:
    """Minimal source-grounded kernel for subjective construction case grading."""

    def grade(
        self,
        *,
        question_row: dict[str, Any],
        user_answer: str,
        evidence_rows: list[dict[str, Any]] | None = None,
        grading_key: dict[str, Any] | None = None,
        artifact_shadow: bool = False,
        grading_artifact: dict[str, Any] | None = None,
        artifact_judge_fn: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> CaseGradingResult:
        """Grade a case-type submission.

        plan §Phase 3 Step 3.4 / Batch D.2 — authority priority:
          1. ``grading_key.scoring_points`` (hidden authority injected from active_object)
          2. ``row.grading_rubric`` (curated rubric in questions_bank)
          3. ``_project_specs_from_existing_fields`` (projected_rubric fallback)
          4. ``_open_skill_specs`` (open_skill — no formal rubric)

        ``grading_source`` is written into ``next_training_signal`` so trace consumers
        can prove which authority produced the result and detect any drift.
        """
        row = dict(question_row or {})
        evidence = _question_evidence_refs(row)
        evidence.extend(_external_evidence_refs(evidence_rows or []))

        # plan §Phase 3 Step 3.4 — grading_key.scoring_points has the highest authority.
        grading_source = "questions_bank"
        rubric_specs: list[dict[str, Any]]
        mode: CaseGradingMode
        gk_specs = _grading_key_rubric_specs(grading_key)
        penalty_rules = _grading_key_penalty_rules(grading_key)
        if gk_specs:
            rubric_specs = gk_specs
            mode = "curated_rubric"
            grading_source = "grading_key"
        else:
            rubric_specs, mode = _build_rubric_specs(row)
            if not rubric_specs:
                rubric_specs = _open_skill_specs(row)
                mode = "open_skill"
                grading_source = "open_skill_fallback"

        answer_text = str(user_answer or "").strip()
        answer_norm = _normalize_official_term(answer_text)
        item_results: list[CaseRubricItemResult] = []
        error_events: list[GradingErrorEvent] = []
        for spec in rubric_specs:
            keywords = list(spec["keywords"])
            required_context = _normalize_official_term(spec.get("required_context"))
            match_text = _answer_label_segment(answer_text, spec.get("answer_label"))
            match_norm = _normalize_official_term(match_text)
            context_ok = not required_context or required_context in match_norm
            matched = [
                keyword
                for keyword in keywords
                if context_ok and _official_keyword_matches(keyword, match_norm)
            ]
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

        item_results, applied_penalties = _apply_penalty_rules(
            item_results,
            answer_text=answer_text,
            penalty_rules=penalty_rules,
        )
        score_awarded = sum(item.awarded_score for item in item_results)
        max_score = sum(item.max_score for item in item_results)
        rewrite = _build_rewrite_answer(item_results)
        result = CaseGradingResult(
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
                # plan §Phase 3 Step 3.4 / Batch D.2 — single trace label
                "grading_source": grading_source,
                "case_grading_mode": mode,
                "penalty_rules_applied": applied_penalties,
            },
        )
        try:
            shadow = _build_m35_artifact_shadow(
                enabled=artifact_shadow,
                question_id=result.question_id,
                student_answer=answer_text,
                artifact=grading_artifact,
                judge_fn=artifact_judge_fn,
            )
        except Exception as exc:  # noqa: BLE001 - shadow must never break legacy grading.
            logger.debug("M35 artifact shadow skipped: %s", exc, exc_info=True)
            shadow = None
        if shadow:
            return _with_m35_artifact_shadow(result, shadow)
        return result


class _CaseGradingResultWithM35Shadow(CaseGradingResult):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["luban_m35_artifact_shadow"] = dict(self._luban_m35_artifact_shadow)
        return payload


def _with_m35_artifact_shadow(
    result: CaseGradingResult,
    shadow: dict[str, Any],
) -> CaseGradingResult:
    wrapped = _CaseGradingResultWithM35Shadow(
        question_id=result.question_id,
        grading_mode=result.grading_mode,
        score_awarded=result.score_awarded,
        max_score=result.max_score,
        rubric_items=result.rubric_items,
        evidence_refs=result.evidence_refs,
        error_events=result.error_events,
        rewrite_answer=result.rewrite_answer,
        next_training_signal=result.next_training_signal,
    )
    object.__setattr__(wrapped, "_luban_m35_artifact_shadow", shadow)
    return wrapped


def _build_m35_artifact_shadow(
    *,
    enabled: bool,
    question_id: str,
    student_answer: str,
    artifact: dict[str, Any] | None,
    judge_fn: Callable[[dict[str, Any], str], dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not enabled or not isinstance(artifact, dict) or artifact.get("artifact_missing") or judge_fn is None:
        return None

    from deeptutor.services.construction_grading import rubric_grader_v1
    from deeptutor.services.construction_grading.m35_status import m35_runtime_status_from_v0

    status_map = m35_runtime_status_from_v0(artifact)
    quality_gates = artifact.get("quality_gates") if isinstance(artifact.get("quality_gates"), dict) else {}
    if _m35_artifact_shadow_blocked(status_map=status_map, quality_gates=quality_gates):
        return None
    event = rubric_grader_v1.grade_artifact_shadow(
        qid=question_id,
        student_answer=student_answer,
        artifact=artifact,
        judge_fn=judge_fn,
    )
    if not event:
        return None
    return {
        "artifact_version": artifact.get("version_id"),
        "legacy_artifact_status": status_map["legacy_artifact_status"],
        "m35_runtime_status": status_map["m35_runtime_status"],
        "point_matches": [dict(point) for point in list(event.get("point_matches") or [])],
        "official_score_allowed": bool(status_map["official_score_allowed"]),
        "source_validity": quality_gates.get("source_refs_verified_rate"),
    }


def _m35_artifact_shadow_blocked(
    *,
    status_map: dict[str, Any],
    quality_gates: dict[str, Any],
) -> bool:
    if status_map.get("m35_runtime_status") == "blocked":
        return True
    if quality_gates.get("score_sum_ok") is False:
        return True
    try:
        if int(quality_gates.get("source_pollution_count") or 0) > 0:
            return True
    except (TypeError, ValueError):
        return True
    return bool(quality_gates.get("blocked_reasons"))


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


def _normalize_official_term(value: Any) -> str:
    return re.sub(r"[\s()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’/／~-]+", "", str(value or ""))


def _official_keyword_variants(keyword: Any) -> list[str]:
    raw = str(keyword or "")
    variants = [_normalize_official_term(raw)]
    optional_removed = re.sub(r"[（(][^()（）]{1,6}[)）]", "", raw)
    if optional_removed != raw:
        variants.append(_normalize_official_term(optional_removed))
    for source in (raw, optional_removed):
        if "或" in source:
            variants.extend(_normalize_official_term(part) for part in source.split("或"))
        if "/" in source or "／" in source:
            parts = re.split(r"[/／]", source)
            prefix = _common_variant_prefix(parts)
            variants.extend(_normalize_official_term(part) for part in parts)
            variants.extend(_normalize_official_term(prefix + part) for part in parts[1:] if prefix)
    return [variant for variant in dict.fromkeys(variants) if variant]


def _common_variant_prefix(parts: list[str]) -> str:
    first = parts[0].strip() if parts else ""
    if len(parts) < 2 or len(first) < 4:
        return ""
    match = re.match(r"^([\u4e00-\u9fffA-Za-z0-9]+?)(?:不受限制|受限制|太小|太大|过厚|过低|过高)$", first)
    return match.group(1) if match else ""


def _answer_label_segment(answer_text: str, answer_label: Any) -> str:
    label = str(answer_label or "").strip()
    if not label:
        return answer_text
    pattern = re.compile(
        rf"(?:^|[\n；;。])\s*{re.escape(label)}\s*[：:、.．]\s*(.*?)(?=(?:[\n；;。]\s*[A-Z]\s*[：:、.．])|$)",
        flags=re.S | re.I,
    )
    match = pattern.search(answer_text)
    return match.group(1) if match else ""


def _official_keyword_matches(keyword: Any, answer_norm: str) -> bool:
    raw = str(keyword or "").strip()
    if not raw or raw in _OVERBROAD_GRADING_KEYWORDS:
        return False
    return any(variant in answer_norm for variant in _official_keyword_variants(raw))


def _point_id_from_criterion(criterion: str) -> str:
    if "::" not in criterion:
        return ""
    return criterion.split("::", 1)[0].strip()


def _grading_key_penalty_rules(grading_key: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(grading_key, dict):
        return []
    rules = grading_key.get("penalty_rules")
    if not isinstance(rules, list):
        return []
    return [rule for rule in rules if isinstance(rule, dict)]


def _apply_penalty_rules(
    items: list[CaseRubricItemResult],
    *,
    answer_text: str,
    penalty_rules: list[dict[str, Any]],
) -> tuple[list[CaseRubricItemResult], list[str]]:
    if not penalty_rules:
        return items, []
    zero_point_ids: set[str] = set()
    applied: list[str] = []
    for rule in penalty_rules:
        if rule.get("type") != "multi_answer_no_score":
            continue
        trigger = rule.get("trigger") if isinstance(rule.get("trigger"), dict) else {}
        pattern = str(trigger.get("pattern") or "").strip()
        max_answered = int(trigger.get("max_answered_items") or 0)
        if not pattern or max_answered <= 0:
            continue
        if len(re.findall(re.escape(pattern), answer_text)) <= max_answered:
            continue
        scoped_ids = {str(point_id).strip() for point_id in rule.get("zero_point_ids") or [] if str(point_id).strip()}
        if scoped_ids:
            zero_point_ids.update(scoped_ids)
            applied.append(str(rule.get("rule_id") or rule.get("type") or "multi_answer_no_score"))
    if not zero_point_ids:
        return items, applied
    adjusted: list[CaseRubricItemResult] = []
    for item in items:
        point_id = _point_id_from_criterion(item.criterion)
        if point_id in zero_point_ids:
            adjusted.append(
                CaseRubricItemResult(
                    criterion=item.criterion,
                    max_score=item.max_score,
                    awarded_score=0.0,
                    status="miss",
                    keywords=item.keywords,
                    evidence_text=item.evidence_text,
                    source_fields=item.source_fields,
                )
            )
        else:
            adjusted.append(item)
    return adjusted, applied


def _grading_key_rubric_specs(grading_key: dict[str, Any] | None) -> list[dict[str, Any]]:
    """plan §Phase 3 Step 3.4 / Batch D.2 — promote ``grading_key.scoring_points``
    into rubric specs.

    Accepted shapes for ``scoring_points`` items:
      * ``str`` → criterion + keywords=[criterion], score=1.0
      * ``dict`` with at least ``criterion`` (or ``name`` / ``required_meaning``)
        and optional ``keywords`` / ``score``
    """
    if not isinstance(grading_key, dict):
        return []
    raw = grading_key.get("scoring_points")
    if not isinstance(raw, list) or not raw:
        return []
    specs: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            criterion = compact_text(item)
            if not criterion:
                continue
            specs.append(
                {
                    "criterion": criterion,
                    "keywords": [criterion],
                    "score": 1.0,
                    "source_fields": ["grading_key.scoring_points"],
                }
            )
        elif isinstance(item, dict):
            criterion = compact_text(item.get("criterion") or item.get("name") or item.get("required_meaning"))
            keywords = normalize_keyword_list(item.get("keywords") or item.get("acceptable_expressions"))
            if not keywords and criterion:
                keywords = [criterion]
            if not criterion or not keywords:
                continue
            specs.append(
                {
                    "criterion": criterion,
                    "keywords": keywords,
                    "score": float(item.get("score") or item.get("max_score") or 1),
                    "source_fields": ["grading_key.scoring_points"],
                    "answer_label": str(item.get("answer_label") or "").strip(),
                    "required_context": str(item.get("required_context") or "").strip(),
                }
            )
    return specs


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
    reference_specs = _reference_answer_specs(row.get("correct_answer"))
    if reference_specs:
        return reference_specs

    for keyword in _trusted_grading_keywords(row):
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

    return specs


def _trusted_grading_keywords(row: dict[str, Any]) -> list[str]:
    """Use generated keywords only when they agree with answer-side authority."""
    keywords = normalize_keyword_list(row.get("grading_keywords"))
    if not keywords:
        return []
    authority_text = compact_text(
        " ".join(
            str(coerce_jsonish(row.get(field)) or "")
            for field in ("correct_answer", "analysis", "testing_focus")
        )
    )
    if not authority_text:
        return keywords
    return [keyword for keyword in keywords if compact_text(keyword) in authority_text]


def _reference_answer_specs(value: Any) -> list[dict[str, Any]]:
    text = str(coerce_jsonish(value) or "")
    improper_text, correct_text = _split_reference_sections(text)
    improper_points = _split_numbered_points(improper_text)
    correct_points = _split_numbered_points(correct_text)
    specs: list[dict[str, Any]] = []
    if improper_points or correct_points:
        count = max(len(improper_points), len(correct_points))
        for index in range(count):
            improper = improper_points[index] if index < len(improper_points) else ""
            correct = correct_points[index] if index < len(correct_points) else ""
            criterion = "；".join(part for part in (improper, correct) if part)
            keywords = _keywords_from_text("；".join(part for part in (improper, correct) if part))
            if criterion and keywords:
                _append_spec(
                    specs,
                    criterion=criterion,
                    keywords=keywords,
                    source_field="correct_answer",
                )
        if specs:
            return specs

    for line in _answer_lines(value):
        keywords = _keywords_from_text(line)
        if line and keywords:
            _append_spec(specs, criterion=line, keywords=keywords, source_field="correct_answer")
    return specs


def _split_reference_sections(text: str) -> tuple[str, str]:
    compact = str(text or "")
    if "正确做法" not in compact:
        return compact, ""
    before, after = compact.split("正确做法", 1)
    before = re.sub(r"^.*?不妥之处[:：]?", "", before, flags=re.S)
    after = re.sub(r"^[:：]?", "", after.strip())
    return before, after


def _split_numbered_points(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = re.split(r"(?:^|[；;\n。]\s*)(?:[①②③④⑤⑥⑦⑧⑨]|\(?[1-9]\)|[1-9][、.．])\s*", raw)
    points = [compact_text(part) for part in parts if compact_text(part)]
    if len(points) > 1:
        return points
    return [compact_text(part) for part in re.split(r"[；;\n。]+", raw) if compact_text(part)]


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
    for pattern in (
        r"单项施工用电方案",
        r"临时用电施工组织设计",
        r"共用一个开关箱",
        r"专用的?开关箱",
        r"插座插头",
        r"插头和插座",
        r"活动连接",
    ):
        for match in re.findall(pattern, compact):
            if match and match not in keywords:
                keywords.append(match)
    if keywords:
        return keywords[:5]
    candidates = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,18}", compact)
    stopwords = {"条件", "结果", "符合", "规范", "要求", "判定", "应进行", "应按规定"}
    result: list[str] = []
    for candidate in candidates:
        if candidate in stopwords or candidate.isdigit() or len(candidate) < 3:
            continue
        if candidate not in result:
            result.append(candidate)
    return result[:5]


def _build_rewrite_answer(items: list[CaseRubricItemResult]) -> str:
    missed_or_hit = [item.criterion for item in items if item.criterion]
    if not missed_or_hit:
        return ""
    return "；".join(missed_or_hit)
