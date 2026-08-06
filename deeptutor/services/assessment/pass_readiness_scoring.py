"""Pass-readiness deterministic scoring: ability readiness, score band, feasibility.

Plan authority: docs/plan/测评题库与考试模块/2026-08-04-luban-pass-readiness-acquisition-diagnostic-plan.md
(§7.1 readiness model + band-width ladder, §7.2 output fields, §9.2 authority chain).

Hard rules encoded here:

- **Two separated numbers.** ``ability_readiness`` aggregates the four ability
  dimensions ONLY and is the sole input to the score band. ``prep_feasibility``
  is a separate field that feeds risk wording / plan pacing and can never move
  the band — the isolation is structural: :func:`derive_score_band` accepts an
  :class:`AbilityEvidence` whose fields carry no time/feasibility data, and the
  function signature has no feasibility-shaped parameter.
- **Band-width ladder is a table lookup**, versioned via ``BAND_POLICY_VERSION``:
  coarse 6-task checkpoint → width ≥ 30 with ``evidence_coverage=low``;
  V1 default (12 tasks, expression not measured — the P0 reality) → ≥ 20;
  expression measured with ≥ 2 observations plus self-reported history and no
  skips → ≥ 12. Expression-unmeasured input can never reach the 12 tier.
- Band endpoints are always rounded to multiples of 5, the band never collapses
  to a single point, and insufficient evidence yields
  ``evidence insufficient for a band`` instead of a fabricated band.
- Deterministic and pure: no LLM, no network, no clock reads — ``now_iso`` is an
  explicit input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


PASS_READINESS_MODEL_VERSION = "pass-readiness-model-v1"
BAND_POLICY_VERSION = "band-v1"

# ── 表单 v2（§6.2-v2 + §7.1/§7.2 带宽阶梯 v2）───────────────────────────────
# 观察数翻倍（12 计分 → 36 计分）后带宽阶梯诚实下调一档；v1 常量与函数原样
# 保留（回滚锚），v2 走独立函数，绝不改 v1 行为。
PASS_READINESS_MODEL_VERSION_V2 = "pass-readiness-model-v2"
BAND_POLICY_VERSION_V2 = "band-v2"

PASS_LINE = 96
EXAM_TOTAL_SCORE = 160

# §7.1 V1 ability weights (prep feasibility's former 10 points are NOT here —
# it is not a band input by design).
ABILITY_WEIGHTS: dict[str, int] = {
    "core_knowledge": 30,
    "construction_logic": 20,
    "case_scoring_point_recognition": 25,
    "answer_expression": 15,
}

# A dimension with fewer than this many observations outputs an observed-signal
# sentence, never a numeric dimension score (§7.1 dimension sample-size rule).
MIN_OBSERVATIONS_FOR_DIMENSION_SCORE = 3

# §7.1 band-width ladder — versioned table lookup, not a judgment call.
BAND_WIDTH_LADDER: dict[str, int] = {
    "coarse_checkpoint": 30,  # 6-task midpoint checkpoint (§6.2), coverage=low
    "v1_default": 20,         # 12 tasks, expression not measured (P0 reality)
    "full_evidence": 12,      # expression ≥2 obs + self-reported history + no skips
}
# Skips or thin dimensions widen by one extra ladder step (§7.1: "too many
# skips or no context → wider still").
BAND_WIDEN_STEP = 5
COARSE_CHECKPOINT_TASK_COUNT = 6
MIN_COMPLETION_RATE_FOR_BAND = 0.5

# §6.2-v2 带宽阶梯 v2（两级检查点：第 10 题粗带 → 第 30 题客观带 → 36 题精带）。
# 观察数翻倍后默认档从 ≥20 下调至 ≥15；仍是查表，不是判断。
BAND_WIDTH_LADDER_V2: dict[str, int] = {
    "coarse_checkpoint": 30,  # 10-task first checkpoint, coverage=low
    "objective_band": 20,     # 30 objective tasks complete, cases pending
    "v2_default": 15,         # full form complete (36 scored tasks)
}
COARSE_CHECKPOINT_TASK_COUNT_V2 = 10
OBJECTIVE_BAND_TASK_COUNT_V2 = 30

EVIDENCE_INSUFFICIENT_COPY = "evidence insufficient for a band"

_READINESS_TIERS: tuple[tuple[int, str], ...] = (
    (85, "高"),
    (70, "中高"),
    (55, "中"),
    (40, "中低"),
    (0, "低"),
)

_REFERENCE_PASS_INTERVALS: tuple[tuple[int, str], ...] = (
    (80, "70%–85%"),
    (65, "55%–70%"),
    (50, "40%–55%"),
    (35, "25%–40%"),
    (0, "10%–25%"),
)


@dataclass(frozen=True)
class DimensionEvidence:
    """Observed evidence for one ability dimension (counts only, no context)."""

    correct: float
    observations: int


@dataclass(frozen=True)
class AbilityEvidence:
    """Band input allow-list (§7.1), enforced structurally.

    Only the four ability dimensions plus the learner's self-reported historical
    real score (labeled 自报未核验) exist here. Remaining time, weekly hours, and
    feasibility have no field to enter through.
    """

    core_knowledge: DimensionEvidence
    construction_logic: DimensionEvidence
    case_scoring_point_recognition: DimensionEvidence
    answer_expression: DimensionEvidence | None = None
    self_reported_score: int | None = None


@dataclass(frozen=True)
class PrepContext:
    """Execution/preparation feasibility context — never a band input."""

    weekly_hours_band: str = ""       # "lt_5" | "5_10" | "10_20" | "gt_20" | ""
    remaining_weeks: int | None = None
    attempt_history: str = ""         # probe tag, e.g. "first_attempt"


def _round_down_5(value: float) -> int:
    return int(math.floor(value / 5.0) * 5)


def _round_up_5(value: float) -> int:
    return int(math.ceil(value / 5.0) * 5)


def _tier_label(exact: int) -> str:
    for threshold, label in _READINESS_TIERS:
        if exact >= threshold:
            return label
    return "低"


def _coarse_range(exact: int) -> str:
    lower = max(0, min(_round_down_5(exact), 90))
    return f"{lower}–{lower + 10}"


def _reference_pass_interval(exact: int) -> str:
    for threshold, interval in _REFERENCE_PASS_INTERVALS:
        if exact >= threshold:
            return interval
    return "10%–25%"


def _dimension_report(name: str, evidence: DimensionEvidence | None) -> dict[str, Any]:
    if evidence is None or evidence.observations <= 0:
        return {
            "dimension": name,
            "measured": False,
            "observations": 0,
            "score_pct": None,
            "observed_signal": "证据不足",
        }
    observations = int(evidence.observations)
    correct = max(0.0, min(float(evidence.correct), float(observations)))
    if observations < MIN_OBSERVATIONS_FOR_DIMENSION_SCORE:
        report: dict[str, Any] = {
            "dimension": name,
            "measured": True,
            "observations": observations,
            "score_pct": None,
            "observed_signal": f"仅 {observations} 次观察，只能给出观察信号，不给维度分",
        }
        if observations == 1:
            report["annotation"] = "单次观察"
        return report
    return {
        "dimension": name,
        "measured": True,
        "observations": observations,
        "score_pct": round(correct / observations * 100),
        "observed_signal": None,
    }


def derive_ability_readiness(evidence: AbilityEvidence) -> dict[str, Any]:
    """Aggregate the four ability dimensions into readiness (0–100).

    Only dimensions with ≥ MIN_OBSERVATIONS_FOR_DIMENSION_SCORE observations
    enter the weighted aggregate; weights renormalize over qualifying
    dimensions. An unmeasured dimension is reported as 证据不足, never silently
    re-labeled as average (§7.1).
    """

    return _derive_ability_readiness(evidence, model_version=PASS_READINESS_MODEL_VERSION)


def derive_ability_readiness_v2(evidence: AbilityEvidence) -> dict[str, Any]:
    """v2 模型版（pass-readiness-model-v2）：聚合语义与 §7.1 权重不变，
    维度观察数由 v2 blueprint 维度矩阵重配（core≈20 / logic≈10 / case≈6）。"""

    return _derive_ability_readiness(evidence, model_version=PASS_READINESS_MODEL_VERSION_V2)


def _derive_ability_readiness(evidence: AbilityEvidence, *, model_version: str) -> dict[str, Any]:
    dimensions = {
        "core_knowledge": _dimension_report("core_knowledge", evidence.core_knowledge),
        "construction_logic": _dimension_report("construction_logic", evidence.construction_logic),
        "case_scoring_point_recognition": _dimension_report(
            "case_scoring_point_recognition", evidence.case_scoring_point_recognition
        ),
        "answer_expression": _dimension_report("answer_expression", evidence.answer_expression),
    }
    weight_sum = 0
    weighted = 0.0
    for name, report in dimensions.items():
        if report["score_pct"] is None:
            continue
        weight = ABILITY_WEIGHTS[name]
        weight_sum += weight
        weighted += weight * float(report["score_pct"])
    exact = round(weighted / weight_sum) if weight_sum > 0 else None
    unmeasured = [name for name, report in dimensions.items() if not report["measured"]]
    thin = [
        name
        for name, report in dimensions.items()
        if report["measured"] and report["score_pct"] is None
    ]
    return {
        "exact": exact,
        "tier": _tier_label(exact) if exact is not None else None,
        "coarse_range": _coarse_range(exact) if exact is not None else None,
        "dimensions": dimensions,
        "unmeasured_dimensions": unmeasured,
        "thin_dimensions": thin,
        "model_version": model_version,
    }


def derive_prep_feasibility(context: PrepContext) -> dict[str, Any]:
    """Deterministic feasibility wording — feeds risk wording/plan pacing only."""

    hours = str(context.weekly_hours_band or "").strip()
    weeks = context.remaining_weeks
    if not hours and weeks is None:
        return {"label": "备考时间信息未提供", "pacing": "unknown"}
    tight_hours = hours in {"lt_5", "5_10"}
    tight_weeks = weeks is not None and weeks <= 8
    if tight_hours and tight_weeks:
        return {"label": "时间预算严重偏紧", "pacing": "very_tight"}
    if tight_hours or tight_weeks:
        return {"label": "时间预算偏紧", "pacing": "tight"}
    return {"label": "时间预算可支撑计划", "pacing": "normal"}


def _band_tier(
    evidence: AbilityEvidence,
    *,
    scored_task_count: int,
    answered_count: int,
) -> str:
    if scored_task_count <= COARSE_CHECKPOINT_TASK_COUNT:
        return "coarse_checkpoint"
    expression = evidence.answer_expression
    expression_solid = expression is not None and expression.observations >= 2
    no_skips = answered_count >= scored_task_count
    if expression_solid and evidence.self_reported_score is not None and no_skips:
        return "full_evidence"
    return "v1_default"


def derive_score_band(
    evidence: AbilityEvidence,
    *,
    scored_task_count: int,
    answered_count: int,
) -> dict[str, Any]:
    """Derive the estimated score band from ability evidence only.

    Structural allow-list: this signature has no feasibility, weekly-hours, or
    remaining-time parameter, and :class:`AbilityEvidence` has no field for
    them — flow variables cannot blend into the stock claim (§7.1).
    """

    scored_task_count = max(0, int(scored_task_count))
    answered_count = max(0, min(int(answered_count), scored_task_count))
    readiness = derive_ability_readiness(evidence)
    exact = readiness["exact"]
    completion_rate = answered_count / scored_task_count if scored_task_count else 0.0
    if exact is None or completion_rate < MIN_COMPLETION_RATE_FOR_BAND:
        return {
            "status": "evidence_insufficient",
            "copy": EVIDENCE_INSUFFICIENT_COPY,
            "tier": None,
            "lower": None,
            "upper": None,
            "width": None,
            "evidence_coverage": "insufficient",
            "readiness": readiness,
            "band_policy_version": BAND_POLICY_VERSION,
        }
    tier = _band_tier(evidence, scored_task_count=scored_task_count, answered_count=answered_count)
    min_width = BAND_WIDTH_LADDER[tier]
    if answered_count < scored_task_count:
        min_width += BAND_WIDEN_STEP
    if readiness["thin_dimensions"]:
        min_width += BAND_WIDEN_STEP
    lower, upper = _banded_range(
        exact, min_width=min_width, self_reported_score=evidence.self_reported_score
    )
    coverage = {"coarse_checkpoint": "low", "v1_default": "medium", "full_evidence": "high"}[tier]
    return {
        "status": "ok",
        "copy": "",
        "tier": tier,
        "lower": lower,
        "upper": upper,
        "width": upper - lower,
        "evidence_coverage": coverage,
        "readiness": readiness,
        "band_policy_version": BAND_POLICY_VERSION,
    }


def _banded_range(
    exact: int, *, min_width: int, self_reported_score: int | None
) -> tuple[int, int]:
    """端点取整到 5 的带子几何（v1/v2 共用；阶梯表由调用方查好传入）。"""

    ability_points = exact / 100.0 * EXAM_TOTAL_SCORE
    if self_reported_score is not None:
        self_reported = max(0, min(int(self_reported_score), EXAM_TOTAL_SCORE))
        center = 0.7 * ability_points + 0.3 * self_reported
    else:
        center = ability_points
    lower = max(0, _round_down_5(center - min_width / 2.0))
    upper = min(EXAM_TOTAL_SCORE, _round_up_5(center + min_width / 2.0))
    # Preserve the ladder minimum when clamping hit an endpoint.
    while upper - lower < min_width:
        if upper < EXAM_TOTAL_SCORE:
            upper = min(EXAM_TOTAL_SCORE, upper + 5)
        elif lower > 0:
            lower = max(0, lower - 5)
        else:  # pragma: no cover - width larger than the whole scale
            break
    return lower, upper


def _band_tier_v2(scored_task_count: int) -> str:
    """v2 阶梯档位是任务量查表（§6.2-v2 两级检查点），不看 expression 证据——
    P0 事实是 written_expression 无条件 not_measured，v2 的 ≥15 精带已按
    观察数翻倍定价，档位只由走到了第几级检查点决定。"""

    if scored_task_count <= COARSE_CHECKPOINT_TASK_COUNT_V2:
        return "coarse_checkpoint"
    if scored_task_count <= OBJECTIVE_BAND_TASK_COUNT_V2:
        return "objective_band"
    return "v2_default"


def derive_score_band_v2(
    evidence: AbilityEvidence,
    *,
    scored_task_count: int,
    answered_count: int,
) -> dict[str, Any]:
    """带宽阶梯 v2（band-v2）：粗带(≤10 题)≥30 → 客观带(≤30 题)≥20 →
    全量精带 ≥15。结构同 v1：无 feasibility 形参、流量变量进不了带子。"""

    scored_task_count = max(0, int(scored_task_count))
    answered_count = max(0, min(int(answered_count), scored_task_count))
    readiness = derive_ability_readiness_v2(evidence)
    exact = readiness["exact"]
    completion_rate = answered_count / scored_task_count if scored_task_count else 0.0
    if exact is None or completion_rate < MIN_COMPLETION_RATE_FOR_BAND:
        return {
            "status": "evidence_insufficient",
            "copy": EVIDENCE_INSUFFICIENT_COPY,
            "tier": None,
            "lower": None,
            "upper": None,
            "width": None,
            "evidence_coverage": "insufficient",
            "readiness": readiness,
            "band_policy_version": BAND_POLICY_VERSION_V2,
        }
    tier = _band_tier_v2(scored_task_count)
    min_width = BAND_WIDTH_LADDER_V2[tier]
    if answered_count < scored_task_count:
        min_width += BAND_WIDEN_STEP
    if readiness["thin_dimensions"]:
        min_width += BAND_WIDEN_STEP
    lower, upper = _banded_range(
        exact, min_width=min_width, self_reported_score=evidence.self_reported_score
    )
    coverage = {"coarse_checkpoint": "low", "objective_band": "medium", "v2_default": "high"}[tier]
    return {
        "status": "ok",
        "copy": "",
        "tier": tier,
        "lower": lower,
        "upper": upper,
        "width": upper - lower,
        "evidence_coverage": coverage,
        "readiness": readiness,
        "band_policy_version": BAND_POLICY_VERSION_V2,
    }


def _risk_band(band: dict[str, Any]) -> str:
    if band["status"] != "ok":
        return "证据不足"
    if band["upper"] < PASS_LINE:
        return "过线风险高"
    if band["lower"] >= PASS_LINE:
        return "过线优势明显"
    return "临界不稳"


def build_pass_readiness_result(
    evidence: AbilityEvidence,
    prep_context: PrepContext,
    *,
    scored_task_count: int,
    answered_count: int,
    form_version: str,
    item_pool_version: str,
    now_iso: str,
) -> dict[str, Any]:
    """Assemble the §7.2 output payload (deterministic; same input → same output).

    ``prep_context`` is consumed only for the ``prep_feasibility`` field — the
    band fields are computed before it is even looked at.
    """

    band = derive_score_band(
        evidence,
        scored_task_count=scored_task_count,
        answered_count=answered_count,
    )
    return _assemble_pass_readiness_result(
        band,
        evidence,
        prep_context,
        form_version=form_version,
        item_pool_version=item_pool_version,
        now_iso=now_iso,
    )


def build_pass_readiness_result_v2(
    evidence: AbilityEvidence,
    prep_context: PrepContext,
    *,
    scored_task_count: int,
    answered_count: int,
    form_version: str,
    item_pool_version: str,
    now_iso: str,
) -> dict[str, Any]:
    """§7.2 输出的 v2 装配：band-v2 阶梯 + pass-readiness-model-v2，
    信封字段与 v1 完全同形（消费方零改动），版本随 band 块如实透出。"""

    band = derive_score_band_v2(
        evidence,
        scored_task_count=scored_task_count,
        answered_count=answered_count,
    )
    return _assemble_pass_readiness_result(
        band,
        evidence,
        prep_context,
        form_version=form_version,
        item_pool_version=item_pool_version,
        now_iso=now_iso,
    )


def _assemble_pass_readiness_result(
    band: dict[str, Any],
    evidence: AbilityEvidence,
    prep_context: PrepContext,
    *,
    form_version: str,
    item_pool_version: str,
    now_iso: str,
) -> dict[str, Any]:
    readiness = band["readiness"]
    feasibility = derive_prep_feasibility(prep_context)
    insufficient = band["status"] != "ok"
    exact = readiness["exact"]
    result: dict[str, Any] = {
        "band_status": band["status"],
        "estimated_score_band": (
            None if insufficient else f"{band['lower']}–{band['upper']} 分"
        ),
        "band_lower": band["lower"],
        "band_upper": band["upper"],
        "band_width": band["width"],
        "band_tier": band["tier"],
        "band_copy": EVIDENCE_INSUFFICIENT_COPY if insufficient else "",
        "pass_line": PASS_LINE,
        "ability_readiness": (
            "证据不足"
            if exact is None
            else f"{readiness['tier']} ({readiness['coarse_range']})"
        ),
        "ability_readiness_detail": readiness,
        "prep_feasibility": feasibility["label"],
        "prep_feasibility_detail": feasibility,
        "risk_band": _risk_band(band),
        "evidence_coverage": band["evidence_coverage"],
        "band_policy_version": str(band["band_policy_version"]),
        "model_version": str(readiness["model_version"]),
        "form_version": str(form_version or ""),
        "item_pool_version": str(item_pool_version or ""),
        "generated_at": str(now_iso or ""),
        "reference_pass_interval": (
            ""
            if insufficient or band["evidence_coverage"] == "low" or exact is None
            else _reference_pass_interval(exact)
        ),
        "unmeasured_dimensions": readiness["unmeasured_dimensions"],
        "self_reported_score_label": (
            "自报未核验" if evidence.self_reported_score is not None else ""
        ),
    }
    return result
