from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import logging
import math
import re
import time
from typing import Any

from deeptutor.services.observability import get_langfuse_observability

logger = logging.getLogger(__name__)

# Observe-only Langfuse generation name for the assessment deep-explanation LLM
# call. Threaded through factory.complete so this out-of-turn-pipeline call is
# identifiable in Langfuse instead of collapsing into the generic "llm.complete".
_ASSESSMENT_EXPLANATION_OBSERVATION_NAME = "assessment.deep_explanation"


def _record_assessment_explanation_duration(elapsed_ms: float) -> None:
    """Observe-only, fail-open: forward one LLM call duration sample (ms) to the
    runtime metrics histogram. Never raises; observability must not break the
    paid explanation path."""
    try:
        from deeptutor.api.runtime_metrics import get_turn_runtime_metrics

        get_turn_runtime_metrics().record_assessment_explanation(elapsed_ms=elapsed_ms)
    except Exception:  # pragma: no cover - defensive, never affects explanation
        logger.debug("assessment explanation duration metric skipped", exc_info=True)

PROMPT_VERSION = "assessment-deep-explanation-llm-v2"
_MINIMUM_EXPLANATION_POINTS = 20
_COST_POINT_SCALE = 1000


def minimum_explanation_points() -> int:
    return _MINIMUM_EXPLANATION_POINTS


def build_explanation_cache_key(
    quiz_id: str,
    question_id: str,
    learner_answer_hash: str,
    grading_result_hash: str,
    prompt_version: str,
) -> str:
    raw = "|".join(
        [
            str(quiz_id or ""),
            str(question_id or ""),
            str(learner_answer_hash or ""),
            str(grading_result_hash or ""),
            str(prompt_version or ""),
        ]
    )
    return "assessment_explain_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class DailyExplanationBudget:
    def __init__(self, *, max_misses_per_user_per_day: int = 20) -> None:
        self.max_misses_per_user_per_day = max(0, int(max_misses_per_user_per_day))
        self._misses: dict[str, int] = {}

    def record_cache_miss(self, user_id: str) -> int:
        normalized = str(user_id or "").strip() or "anonymous"
        next_count = int(self._misses.get(normalized) or 0) + 1
        if next_count > self.max_misses_per_user_per_day:
            raise RuntimeError("assessment_deep_explanation_budget_exceeded")
        self._misses[normalized] = next_count
        return next_count


def attach_deep_explanation(
    report: dict[str, Any],
    *,
    question_id: str,
    explanation: dict[str, Any],
) -> dict[str, Any]:
    next_report = deepcopy(report)
    normalized_question_id = str(question_id or "")
    for group_key in ("wrong_items", "items", "questions"):
        for item in next_report.get(group_key) or []:
            if str(item.get("question_id") or item.get("id") or "") == normalized_question_id:
                item["deep_explanation"] = dict(explanation or {})
    return next_report


def build_static_deep_explanation(
    *,
    question: dict[str, Any],
    learner_answer: str,
    correct_answer: str,
) -> dict[str, Any]:
    simple = str(
        question.get("simple_explanation")
        or question.get("explanation")
        or question.get("analysis")
        or "本题需要回到题干条件、规范要求和选项差异逐项判断。"
    ).strip()
    knowledge_points = list(question.get("knowledge_points") or question.get("knowledge_nodes") or [])
    return {
        "summary": simple,
        "learner_answer": str(learner_answer or ""),
        "correct_answer": str(correct_answer or ""),
        "knowledge_points": knowledge_points,
        "score_mutation_allowed": False,
        "source": "assessment_deep_explanation_projection",
    }


def billable_points_from_usage_summary(usage_summary: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
    if not isinstance(usage_summary, dict):
        return _MINIMUM_EXPLANATION_POINTS, {
            "billing_amount_source": "fallback_minimum",
            "billing_cost_source": "missing_usage_summary",
            "billing_cost_point_scale": _COST_POINT_SCALE,
            "billing_minimum_points": _MINIMUM_EXPLANATION_POINTS,
        }
    measured_cost = _safe_float(usage_summary.get("total_cost_usd"))
    estimated_cost = _safe_float(usage_summary.get("estimated_total_cost_usd"))
    billable_cost = measured_cost + estimated_cost
    cost_points = int(math.ceil(billable_cost * _COST_POINT_SCALE)) if billable_cost > 0 else 0
    amount_points = max(_MINIMUM_EXPLANATION_POINTS, cost_points)
    if measured_cost > 0 and estimated_cost > 0:
        cost_source = "mixed_cost"
    elif measured_cost > 0:
        cost_source = "measured_cost"
    elif estimated_cost > 0:
        cost_source = "estimated_cost"
    else:
        cost_source = "missing_cost"
    return amount_points, {
        "billing_amount_source": cost_source if cost_points >= _MINIMUM_EXPLANATION_POINTS else "fallback_minimum",
        "billing_cost_source": cost_source,
        "billing_cost_point_scale": _COST_POINT_SCALE,
        "billing_minimum_points": _MINIMUM_EXPLANATION_POINTS,
        "billing_measured_cost": round(measured_cost, 8),
        "billing_estimated_cost": round(estimated_cost, 8),
        "billing_billable_cost": round(billable_cost, 8),
        "billing_cost_points": int(cost_points),
        "usage_accuracy": str(usage_summary.get("usage_accuracy") or "").strip(),
        "usage_total_input_tokens": int(usage_summary.get("total_input_tokens") or 0),
        "usage_total_output_tokens": int(usage_summary.get("total_output_tokens") or 0),
        "usage_total_tokens": int(usage_summary.get("total_tokens") or 0),
        "usage_estimated_input_tokens": int(usage_summary.get("estimated_input_tokens") or 0),
        "usage_estimated_output_tokens": int(usage_summary.get("estimated_output_tokens") or 0),
        "usage_estimated_total_tokens": int(usage_summary.get("estimated_total_tokens") or 0),
    }


async def generate_llm_deep_explanation(
    *,
    question: dict[str, Any],
    learner_answer: str,
    correct_answer: str,
    quiz_id: str,
    question_id: str,
) -> dict[str, Any]:
    from deeptutor.services.llm import complete

    system_prompt = (
        "你是一建建筑实务老师。只基于题干、选项、标准答案和已给依据讲解，"
        "不要改分，不要编造规范条文编号。输出严格 JSON。"
    )
    prompt = _build_prompt(
        question=question,
        learner_answer=learner_answer,
        correct_answer=correct_answer,
    )
    observability = get_langfuse_observability()
    with observability.usage_scope(
        scope_id=f"assessment_explanation:{quiz_id}:{question_id}",
        session_id=str(quiz_id or ""),
        turn_id=str(question_id or ""),
        capability="assessment_deep_explanation",
    ):
        started_at = time.monotonic()
        try:
            parsed: dict[str, Any] = {}
            # 内容级重试一次:输出截断/非 JSON 时再要一遍。解析仍失败则显式抛错
            # ——绝不吐罐头模板冒充付费解析(fail-closed-to-template 反模式;
            # 2026-08-07 实测:v2 prompt 输出更长,1200 tokens 截断产出罐头还被
            # 计费+缓存)。调用方不 capture、不缓存,前端提示稍后重试。
            for _attempt in range(2):
                raw = await complete(
                    prompt,
                    system_prompt=system_prompt,
                    temperature=0.2,
                    max_tokens=2400,
                    max_retries=2,
                    observation_name=_ASSESSMENT_EXPLANATION_OBSERVATION_NAME,
                )
                parsed = _parse_llm_json(raw)
                if parsed:
                    break
        finally:
            _record_assessment_explanation_duration((time.monotonic() - started_at) * 1000.0)
        usage_summary = observability.get_current_usage_summary()
    if not parsed:
        raise RuntimeError("assessment_deep_explanation_generation_failed")
    return {
        "summary": _text(parsed.get("summary"))
        or _text(question.get("simple_explanation")),
        "learner_answer": str(learner_answer or ""),
        "correct_answer": str(correct_answer or ""),
        "key_terms": _string_list(parsed.get("key_terms"))[:6],
        "why_wrong": _text(parsed.get("why_wrong")),
        "cause_analysis": _text(parsed.get("cause_analysis") or parsed.get("cause")),
        "scoring_points": _text(parsed.get("scoring_points")),
        "option_reviews": _option_reviews(parsed.get("option_reviews")),
        "pitfall": _text(parsed.get("pitfall") or parsed.get("pitfalls")),
        "mnemonic": _text(parsed.get("mnemonic")),
        "source_basis": _text(parsed.get("source_basis") or parsed.get("source")),
        "next_action": _text(parsed.get("next_action")),
        "knowledge_points": _string_list(question.get("knowledge_points") or question.get("knowledge_nodes")),
        "score_mutation_allowed": False,
        "source": "assessment_deep_explanation_llm",
        "prompt_version": PROMPT_VERSION,
        "usage_summary": usage_summary,
    }


def _build_prompt(*, question: dict[str, Any], learner_answer: str, correct_answer: str) -> str:
    payload = {
        "question_id": question.get("question_id") or question.get("source_question_id") or "",
        "question_stem": question.get("question_stem") or question.get("stem") or "",
        "question_type": question.get("question_type") or "",
        "options": question.get("options") or [],
        "learner_answer": learner_answer,
        "correct_answer": correct_answer,
        "simple_explanation": question.get("simple_explanation") or question.get("explanation") or question.get("analysis") or "",
        "knowledge_points": question.get("knowledge_points") or question.get("knowledge_nodes") or [],
        "error_codes": question.get("error_codes") or [],
        "grading_key": question.get("grading_key") or {},
        # v2: 签发教研诊断(逐选项 pitfall/why_missed/fix + model_answer + 采分点)
        # 是内容事实权威——喂给模型作基准,防运行时现编与权威矛盾的解析。
        "issued_diagnosis": question.get("answer_diagnosis") or {},
    }
    return (
        "请为学员生成一次付费 AI 详细解析。要求：\n"
        "1. 先说明本题考什么，以及学员为什么错。\n"
        "2. 逐项解释选项为什么对/错，特别指出漏选、错选、多选。\n"
        "3. 给出采分点、易错点、记忆口诀和下一步练习建议。\n"
        "4. 不要说空话；每句话都要落到题干、选项或答案差异。\n"
        "5. issued_diagnosis 是教研签发的诊断事实（采分点/逐选项易错点/纠错口径），"
        "解析必须与其一致并在其基础上讲透讲细；它为空时才按题干与选项严谨推导，"
        "不得编造教材条文或数值。\n"
        "6. 严格输出 JSON，字段为 summary, key_terms, why_wrong, cause_analysis, "
        "scoring_points, option_reviews, pitfall, mnemonic, source_basis, next_action。\n"
        "option_reviews 每项字段为 key, status, status_label, review。\n\n"
        "题目信息：\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def _parse_llm_json(raw: Any) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _option_reviews(value: Any) -> list[dict[str, str]]:
    rows = value if isinstance(value, list) else []
    result: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _text(row.get("key")).upper()
        review = _text(row.get("review"))
        if not key or not review:
            continue
        result.append(
            {
                "key": key[:4],
                "status": _text(row.get("status")) or "neutral",
                "status_label": _text(row.get("status_label")),
                "review": review,
            }
        )
    return result[:8]


def _safe_float(value: Any) -> float:
    try:
        return max(float(value or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]
