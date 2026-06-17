#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from deeptutor.services.construction_grading.case_kernel import CaseGradingSkillKernel
from deeptutor.services.construction_grading.schema import CaseGradingResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = (
    PROJECT_ROOT
    / "deeptutor"
    / "services"
    / "benchmark"
    / "fixtures"
    / "luban_case_grading_golden_v1.json"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "luban_case_grading_three_arms"
DEFAULT_PILOT_CASES = ("Q1-NA", "Q4-1A434000-罚则")
OVERBROAD_TERMS = {"原则"}


def _compact(value: Any) -> str:
    return re.sub(r"[\s()（）《》〈〉、,，；;:：。.!！?？\"'“”‘’]+", "", str(value or ""))


def _avg(values: list[float]) -> float | None:
    return round(float(mean(values)), 4) if values else None


def _token_proxy(value: Any) -> int:
    return max(1, round(len(str(value or "")) / 2))


def _stable_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _is_scoring_instruction_term(term: str) -> bool:
    return bool(re.fullmatch(r"(?:命中)?\d+项\s*=\s*\d+(?:\.\d+)?(?:分)?", str(term or "").strip()))


def _official_terms_only(terms: list[str]) -> list[str]:
    return [term for term in terms if term not in OVERBROAD_TERMS and not _is_scoring_instruction_term(term)]


def _quoted_terms(text: str) -> list[str]:
    quoted: list[str] = []
    for match in re.finditer(r"[\"'“‘]([^\"'”’]{2,40})[\"'”’]", str(text or "")):
        term = match.group(1).strip()
        prefix = str(text or "")[max(0, match.start() - 4) : match.start()]
        if re.search(r"(?:而非|非|不是|不能是)$", prefix):
            continue
        if term:
            quoted.append(term)
    return _stable_unique(quoted)


def _terms_from_list_rule(point: dict[str, Any]) -> list[str]:
    text = str(point.get("list_rule") or "")
    if not text:
        return []
    scoring_match = re.search(r"应得分项为\d+项[:：]([^。;；]+)", text)
    if scoring_match:
        raw_terms = re.split(r"、(?=[\u4e00-\u9fffA-Za-z0-9])", scoring_match.group(1))
        return _stable_unique(
            [
                re.sub(r"^(?:和|及|以及)", "", term).strip()
                for term in raw_terms
                if 1 < len(term.strip()) <= 40
            ]
        )
    match = re.search(r"规范术语[（(]([^()（）]{2,120})[)）]", text)
    if not match:
        match = re.search(r"[（(]([^()（）]{2,120})[)）]", text)
    if not match:
        return []
    raw_terms = re.split(r"[、,，/／]", match.group(1))
    terms = [term.strip() for term in raw_terms if 1 < len(term.strip()) <= 24]
    return _stable_unique(terms)


def _terms_after_dash(label: str) -> list[str]:
    if "——" not in label:
        return []
    tail = label.split("——", 1)[1]
    tail = re.split(r"[（(]", tail, 1)[0]
    raw_terms = re.split(r"[、,，/／]", tail)
    return _stable_unique([term.strip() for term in raw_terms if 1 < len(term.strip()) <= 24])


def _calculation_result_terms(label: str) -> list[str]:
    if "=" not in label and "＝" not in label:
        return []
    return _stable_unique(re.findall(r"\d+(?:\.\d+)?kg", label, flags=re.I))


def extract_required_terms(point: dict[str, Any]) -> list[str]:
    """Extract textbook/official wording terms; no synonym expansion."""

    label = str(point.get("label") or "")
    core_match = re.search(r"核心得分项为(.+?)三项", label)
    terms = _quoted_terms(core_match.group(1)) if core_match else []
    terms.extend(_terms_from_list_rule(point))
    terms.extend(_terms_after_dash(label))
    terms.extend(_calculation_result_terms(label))
    terms.extend(_quoted_terms(label))
    terms.extend(_quoted_terms(str(point.get("official_basis") or "")))
    if terms:
        unique = _stable_unique(terms)
        filtered: list[str] = []
        compact_seen: set[str] = set()
        for term in unique:
            compact = _compact(term)
            if compact in compact_seen:
                continue
            compact_seen.add(compact)
            if any(compact and compact in _compact(other) and compact != _compact(other) for other in unique):
                continue
            filtered.append(term)
        return _official_terms_only(filtered)
    candidates: list[str] = []
    for pattern in (
        r"见证人员",
        r"建设单位",
        r"单独列支",
        r"操作平台",
        r"防护栏杆",
        r"连续的?安全绳",
        r"钢丝绳",
        r"黑黄相间",
        r"红白相间",
        r"施工总进度计划表\\(图\\)",
        r"开、竣工日期及工期一览表",
        r"资源需要量及供应平衡表",
        r"取样",
        r"制样",
        r"标识",
        r"封志",
        r"送检",
        r"现场检测",
    ):
        candidates.extend(match.group(0) for match in re.finditer(pattern, label))
    return _official_terms_only(_stable_unique(candidates))


def _term_hit(answer_text: str, term: str) -> bool:
    return _compact(term) in _compact(answer_text)


def _matched_terms(answer_text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _term_hit(answer_text, term)]


def compile_kernel_scoring_points(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Compile golden points into kernel atomic points without changing semantics."""

    compiled: list[dict[str, Any]] = []
    for point in case.get("gold_scoring_points") or []:
        terms = extract_required_terms(point)
        point_id = str(point.get("point_id") or "").strip()
        max_score = float(point.get("max_score") or 0)
        required_context = _required_context_for_point(point)
        answer_label = _answer_label_for_point(point)
        if len(terms) > 1:
            score = max_score / len(terms)
            for index, term in enumerate(terms, start=1):
                compiled.append(
                    _compiled_point(
                        point_id,
                        term,
                        score,
                        required_context=required_context,
                        answer_label=answer_label,
                    )
                )
        elif terms:
            compiled.append(
                _compiled_point(
                    point_id,
                    terms[0],
                    max_score,
                    required_context=required_context,
                    answer_label=answer_label,
                )
            )
    return compiled


def compile_penalty_rules(case: dict[str, Any]) -> list[dict[str, Any]]:
    raw = str(case.get("penalty_rule") or "").strip()
    if "多答不得分" not in raw:
        return []
    max_match = re.search(r"(\d+)项不妥", raw)
    zero_scope = raw.split("不牵连", 1)[0]
    zero_ids = re.findall(r"P\d+", zero_scope)
    if not max_match or not zero_ids:
        return []
    return [
        {
            "rule_id": "multi_answer_no_score",
            "type": "multi_answer_no_score",
            "trigger": {"max_answered_items": int(max_match.group(1)), "pattern": "不妥"},
            "zero_point_ids": _stable_unique(zero_ids),
            "source_field": "golden.penalty_rule",
        }
    ]


def _required_context_for_point(point: dict[str, Any]) -> str:
    label = str(point.get("label") or "")
    if "分项工程划分条件" in label:
        return "分项工程"
    if "检验批划分条件" in label:
        return "检验批"
    return ""


def _answer_label_for_point(point: dict[str, Any]) -> str:
    match = re.search(r"\b([A-Z])\s*处填", str(point.get("label") or ""))
    return match.group(1) if match else ""


def _compiled_keywords(term: str) -> list[str]:
    return [term]


def _compiled_point(
    point_id: str,
    term: str,
    score: float,
    *,
    required_context: str = "",
    answer_label: str = "",
) -> dict[str, Any]:
    item = {
        "criterion": f"{point_id}::{term}",
        "keywords": _compiled_keywords(term),
        "score": score,
        "source_point_id": point_id,
        "source_fields": ["golden.gold_scoring_points"],
    }
    if required_context:
        item["required_context"] = required_context
    if answer_label:
        item["answer_label"] = answer_label
    return item


def gold_from_ledger(case: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    """Use construction ledger as v0 programmatic ground truth."""

    answer_text = str(sample.get("answer_text") or "")
    points_by_id = {
        str(point.get("point_id") or ""): point
        for point in case.get("gold_scoring_points") or []
    }
    ledger = sample.get("ground_truth_ledger") if isinstance(sample.get("ground_truth_ledger"), dict) else {}
    hits = ledger.get("point_hits") if isinstance(ledger.get("point_hits"), list) else []
    point_scores: dict[str, float] = {}
    positive_points: set[str] = set()
    positive_terms: set[str] = set()
    rows: list[dict[str, Any]] = []
    for hit_row in hits:
        if not isinstance(hit_row, dict):
            continue
        point_id = str(hit_row.get("point_id") or "").strip()
        point = points_by_id.get(point_id) or {}
        status = str(hit_row.get("hit") or "").strip()
        terms = extract_required_terms(point)
        matched = _matched_terms(answer_text, terms)
        max_score = float(point.get("max_score") or 0)
        if status == "hit":
            score = max_score
            positive_points.add(point_id)
            positive_terms.update(terms or matched)
        elif status == "partial":
            if terms:
                score = max_score * (len(matched) / len(terms))
                positive_terms.update(matched)
            else:
                score = max_score / 2
            if score > 0:
                positive_points.add(point_id)
        else:
            score = 0.0
        point_scores[point_id] = score
        rows.append(
            {
                "point_id": point_id,
                "ledger_hit": status,
                "max_score": max_score,
                "gold_score": round(score, 4),
                "terms": terms,
                "matched_terms": matched,
                "injected_error_codes": hit_row.get("injected_error_codes") or [],
            }
        )
    return {
        "score": round(sum(point_scores.values()), 4),
        "point_scores": point_scores,
        "positive_points": positive_points,
        "positive_terms": positive_terms,
        "point_rows": rows,
        "penalty_triggered": bool(ledger.get("penalty_triggered")),
    }


def _question_row(case: dict[str, Any], *, include_curated_rubric: bool = False) -> dict[str, Any]:
    row = {
        "id": case.get("case_id"),
        "question_id": case.get("case_id"),
        "question_type": "case_study",
        "question_stem": case.get("stem"),
        "stem": case.get("stem"),
        "correct_answer": case.get("official_answer"),
        "analysis": case.get("official_analysis"),
        "node_code": case.get("question_node"),
        "testing_focus": case.get("question_node"),
    }
    if include_curated_rubric:
        row["grading_rubric"] = [
            {
                "criterion": str(point.get("label") or point.get("point_id") or ""),
                "keywords": extract_required_terms(point),
                "score": float(point.get("max_score") or 0),
            }
            for point in case.get("gold_scoring_points") or []
        ]
    return row


def _rag_evidence_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for field in ("official_answer", "official_analysis"):
        value = case.get(field)
        if value:
            rows.append({"source": "golden_fixture_rag_replay", "field": field, "content": value})
    return rows


def _result_terms(result: CaseGradingResult) -> set[str]:
    terms: set[str] = set()
    for item in result.rubric_items:
        if item.status == "full":
            terms.update(item.keywords)
    return terms


def _result_points(result: CaseGradingResult) -> set[str]:
    points: set[str] = set()
    for item in result.rubric_items:
        if item.status != "full":
            continue
        if "::" in item.criterion:
            points.add(item.criterion.split("::", 1)[0])
    return points


def _score_arm(
    *,
    arm: str,
    case: dict[str, Any],
    sample: dict[str, Any],
    grading_key: dict[str, Any] | None = None,
    evidence_rows: list[dict[str, Any]] | None = None,
) -> tuple[CaseGradingResult, float]:
    started = time.perf_counter()
    result = CaseGradingSkillKernel().grade(
        question_row=_question_row(case),
        user_answer=str(sample.get("answer_text") or ""),
        evidence_rows=evidence_rows,
        grading_key=grading_key,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    return result, latency_ms


def _case_group_tags(case: dict[str, Any]) -> list[str]:
    text = "\n".join(
        [
            str(case.get("stem") or ""),
            str(case.get("official_answer") or ""),
            str(case.get("official_analysis") or ""),
            "\n".join(str(point.get("label") or "") for point in case.get("gold_scoring_points") or []),
        ]
    )
    tags: list[str] = []
    if str(case.get("penalty_rule") or "").strip():
        tags.append("penalty_rule")
    if any(str(point.get("list_rule") or "").strip() for point in case.get("gold_scoring_points") or []):
        tags.append("list_rule")
    if re.search(r"计算|工期|费用|价款|索赔|流水|网络计划|关键线路", text):
        tags.append("calculation")
    if re.search(r"规范|标准|条文|GB|JGJ|应当|不得|必须", text, flags=re.I):
        tags.append("specification")
    return tags or ["general"]


def _precision_recall(predicted: set[str], gold: set[str]) -> tuple[float, float]:
    if not gold:
        recall = 1.0 if not predicted else 0.0
    else:
        recall = len(predicted & gold) / len(gold)
    if not predicted:
        precision = 1.0 if not gold else 0.0
    else:
        precision = len(predicted & gold) / len(predicted)
    return precision, recall


def evaluate_sample(case: dict[str, Any], sample: dict[str, Any]) -> list[dict[str, Any]]:
    gold = gold_from_ledger(case, sample)
    compiled_points = compile_kernel_scoring_points(case)
    penalty_rules = compile_penalty_rules(case)
    artifact_grading_key = {"scoring_points": compiled_points}
    if penalty_rules:
        artifact_grading_key["penalty_rules"] = penalty_rules
    arms = [
        ("baseline", None, None),
        ("rag", None, _rag_evidence_rows(case)),
        ("artifact_first", artifact_grading_key, None),
    ]
    rows: list[dict[str, Any]] = []
    baseline_score: float | None = None
    for arm, grading_key, evidence_rows in arms:
        result, latency_ms = _score_arm(
            arm=arm,
            case=case,
            sample=sample,
            grading_key=grading_key,
            evidence_rows=evidence_rows,
        )
        if arm == "baseline":
            baseline_score = result.score_awarded
        predicted_terms = {
            term
            for term in _result_terms(result)
            if any(_compact(term) == _compact(gold_term) for gold_term in gold["positive_terms"])
        }
        if arm == "artifact_first":
            predicted_points = _result_points(result)
        else:
            predicted_points = set()
            for point in case.get("gold_scoring_points") or []:
                point_id = str(point.get("point_id") or "")
                terms = set(extract_required_terms(point))
                if terms and (_result_terms(result) & terms):
                    predicted_points.add(point_id)
        point_precision, point_recall = _precision_recall(
            predicted_points,
            set(gold["positive_points"]),
        )
        term_precision, term_recall = _precision_recall(
            predicted_terms,
            set(gold["positive_terms"]),
        )
        known_terms = {term for point in case.get("gold_scoring_points") or [] for term in extract_required_terms(point)}
        hallucinated_terms = [term for term in _result_terms(result) if term not in known_terms]
        rows.append(
            {
                "case_id": case.get("case_id"),
                "sample_id": sample.get("student_id"),
                "archetype": sample.get("archetype"),
                "arm": arm,
                "gold_score": gold["score"],
                "pred_score": round(float(result.score_awarded), 4),
                "max_score": float(case.get("max_score") or result.max_score or 0),
                "score_delta": round(float(result.score_awarded) - gold["score"], 4),
                "point_precision": round(point_precision, 4),
                "point_recall": round(point_recall, 4),
                "term_precision": round(term_precision, 4),
                "term_recall": round(term_recall, 4),
                "hallucination": bool(hallucinated_terms),
                "hallucinated_terms": hallucinated_terms,
                "token_proxy": _token_proxy(grading_key or _question_row(case)) + _token_proxy(evidence_rows or []),
                "latency_ms": round(latency_ms, 4),
                "grading_mode": result.grading_mode,
                "grading_source": result.next_training_signal.get("grading_source"),
                "rubric_item_count": len(result.rubric_items),
                "evidence_ref_count": len(result.evidence_refs),
                "rag_score_changed_vs_baseline": None
                if arm != "rag" or baseline_score is None
                else abs(float(result.score_awarded) - baseline_score) > 1e-9,
                "gold_penalty_triggered": gold["penalty_triggered"],
                "case_group_tags": _case_group_tags(case),
                "predicted_points": sorted(predicted_points),
                "gold_positive_points": sorted(gold["positive_points"]),
                "predicted_terms": sorted(predicted_terms),
                "gold_positive_terms": sorted(gold["positive_terms"]),
                "gold_point_rows": gold["point_rows"],
                "result": result.to_dict(),
            }
        )
    return rows


def summarize_three_arm_results(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("arm") or "")].append(row)
    summary: dict[str, dict[str, Any]] = {}
    for arm, arm_rows in sorted(grouped.items()):
        summary[arm] = {
            "case_count": len({str(row.get("case_id")) for row in arm_rows}),
            "sample_count": len(arm_rows),
            "mean_abs_score_delta": _avg([abs(float(row["score_delta"])) for row in arm_rows]),
            "mean_point_recall": _avg([float(row["point_recall"]) for row in arm_rows]),
            "mean_point_precision": _avg([float(row["point_precision"]) for row in arm_rows]),
            "mean_term_recall": _avg([float(row["term_recall"]) for row in arm_rows]),
            "mean_term_precision": _avg([float(row["term_precision"]) for row in arm_rows]),
            "hallucination_rate": _avg([1.0 if row.get("hallucination") else 0.0 for row in arm_rows]),
            "mean_token_proxy": _avg([float(row["token_proxy"]) for row in arm_rows]),
            "mean_latency_ms": _avg([float(row["latency_ms"]) for row in arm_rows]),
        }
    return summary


def summarize_by_group(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for tag in row.get("case_group_tags") or ["general"]:
            grouped[str(tag)].append(row)
    return {tag: summarize_three_arm_results(tag_rows) for tag, tag_rows in sorted(grouped.items())}


def analyze_artifact_weaknesses(rows: list[dict[str, Any]]) -> dict[str, Any]:
    over: list[dict[str, Any]] = []
    under: list[dict[str, Any]] = []
    for row in rows:
        if row.get("arm") != "artifact_first":
            continue
        delta = float(row.get("score_delta") or 0)
        entry = {
            "case_id": row.get("case_id"),
            "sample_id": row.get("sample_id"),
            "archetype": row.get("archetype"),
            "gold_score": row.get("gold_score"),
            "pred_score": row.get("pred_score"),
            "score_delta": row.get("score_delta"),
            "gold_penalty_triggered": row.get("gold_penalty_triggered"),
            "predicted_points": row.get("predicted_points"),
            "gold_positive_points": row.get("gold_positive_points"),
            "predicted_terms": row.get("predicted_terms"),
            "gold_positive_terms": row.get("gold_positive_terms"),
        }
        if delta > 0.0001:
            if row.get("gold_penalty_triggered"):
                category = "penalty_rule_unsupported"
            elif not row.get("gold_positive_points") and row.get("pred_score", 0) > 0:
                category = "keyword_context_false_positive"
            else:
                category = "compiled_term_overmatch"
            over.append({**entry, "category": category})
        elif delta < -0.0001:
            if float(row.get("term_recall") or 0) < 1 and float(row.get("point_recall") or 0) >= 1:
                category = "term_form_normalization_gap"
            else:
                category = "compiled_term_recall_gap"
            under.append({**entry, "category": category})
    counts: dict[str, int] = defaultdict(int)
    for item in [*over, *under]:
        counts[str(item["category"])] += 1
    return {
        "over_scored": over,
        "under_scored": under,
        "category_counts": dict(sorted(counts.items())),
    }


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("suite") != "luban_case_grading_golden_v1":
        raise ValueError("unexpected fixture suite")
    return payload


def run_three_arm_eval(*, fixture_path: Path, case_ids: list[str] | None = None) -> dict[str, Any]:
    payload = _load_fixture(fixture_path)
    cases_by_id = {str(case.get("case_id")): case for case in payload.get("cases") or []}
    resolved_case_ids = case_ids or list(cases_by_id)
    selected = [cases_by_id[case_id] for case_id in resolved_case_ids if case_id in cases_by_id]
    if len(selected) != len(resolved_case_ids):
        missing = sorted(set(resolved_case_ids) - set(cases_by_id))
        raise ValueError(f"missing eval cases: {missing}")
    rows: list[dict[str, Any]] = []
    compiled_examples: dict[str, Any] = {}
    for case in selected:
        compiled_examples[str(case.get("case_id"))] = compile_kernel_scoring_points(case)
        for sample in case.get("eval_samples") or []:
            rows.extend(evaluate_sample(case, sample))
    summary = summarize_three_arm_results(rows)
    return {
        "run_scope": "pilot" if len(resolved_case_ids) <= len(DEFAULT_PILOT_CASES) else "full",
        "gold_source": "ground_truth_ledger",
        "gold_source_caveat": "v0 AI-anchored construction ledger; directional/shadow only",
        "case_ids": resolved_case_ids,
        "summary": summary,
        "group_summary": summarize_by_group(rows),
        "artifact_weaknesses": analyze_artifact_weaknesses(rows),
        "rows": rows,
        "compiled_examples": compiled_examples,
        "rag_trace": {
            "evidence_in_result": all(
                row["evidence_ref_count"] > 0 for row in rows if row["arm"] == "rag"
            ),
            "score_changed_samples": sum(
                1 for row in rows if row["arm"] == "rag" and row["rag_score_changed_vs_baseline"]
            ),
            "interpretation": "rag_evidence_reaches_trace_but_not_scoring_authority",
        },
    }


def run_pilot(*, fixture_path: Path, case_ids: list[str]) -> dict[str, Any]:
    return run_three_arm_eval(fixture_path=fixture_path, case_ids=case_ids)


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Luban Case Grading Three-Arm Pilot",
        "",
        "- status: `v0_directional_shadow`",
        f"- gold_source: `{report['gold_source']}`",
        f"- caveat: {report['gold_source_caveat']}",
        f"- cases: `{', '.join(report['case_ids'])}`",
        f"- run_scope: `{report['run_scope']}`",
        "",
        "## Summary",
        "",
        "| arm | samples | mean abs score delta | point recall | point precision | term recall | term precision | hallucination | token proxy | latency ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, data in sorted(report["summary"].items()):
        lines.append(
            "| {arm} | {sample_count} | {mean_abs_score_delta} | {mean_point_recall} | {mean_point_precision} | {mean_term_recall} | {mean_term_precision} | {hallucination_rate} | {mean_token_proxy} | {mean_latency_ms} |".format(
                arm=arm,
                **data,
            )
        )
    lines.extend(["", "## Group Summary", ""])
    for group, group_summary in report.get("group_summary", {}).items():
        lines.extend(
            [
                f"### {group}",
                "",
                "| arm | samples | mean abs score delta | point recall | point precision | term recall | term precision | hallucination | token proxy |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for arm, data in sorted(group_summary.items()):
            lines.append(
                "| {arm} | {sample_count} | {mean_abs_score_delta} | {mean_point_recall} | {mean_point_precision} | {mean_term_recall} | {mean_term_precision} | {hallucination_rate} | {mean_token_proxy} |".format(
                    arm=arm,
                    **data,
                )
            )
        lines.append("")
    lines.extend(
        [
            "",
            "## RAG Trace",
            "",
            f"- evidence_in_result: `{report['rag_trace']['evidence_in_result']}`",
            f"- score_changed_samples: `{report['rag_trace']['score_changed_samples']}`",
            f"- interpretation: `{report['rag_trace']['interpretation']}`",
            "",
            "## Artifact-First Weaknesses",
            "",
            f"- category_counts: `{json.dumps(report.get('artifact_weaknesses', {}).get('category_counts') or {}, ensure_ascii=False)}`",
            f"- over_scored: `{len((report.get('artifact_weaknesses') or {}).get('over_scored') or [])}`",
            f"- under_scored: `{len((report.get('artifact_weaknesses') or {}).get('under_scored') or [])}`",
            "",
            "## Per Sample",
            "",
            "| case | sample | arm | pred | gold | delta | source | evidence refs | point recall | point precision | penalty |",
            "|---|---|---|---:|---:|---:|---|---:|---:|---:|---|",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| {case_id} | {sample_id} | {arm} | {pred_score} | {gold_score} | {score_delta} | {grading_source} | {evidence_ref_count} | {point_recall} | {point_precision} | {gold_penalty_triggered} |".format(
                **row
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Luban case-grading three-arm pilot.")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--all", action="store_true", help="Run all cases in the fixture.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    case_ids = None if args.all else (args.case_id or list(DEFAULT_PILOT_CASES))
    report = run_three_arm_eval(fixture_path=Path(args.fixture), case_ids=case_ids)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    artifact_prefix = "full_three_arms" if report["run_scope"] == "full" else "pilot_three_arms"
    json_path = output_dir / f"{artifact_prefix}_{stamp}.json"
    md_path = output_dir / f"{artifact_prefix}_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"json_path": str(json_path), "md_path": str(md_path), "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
