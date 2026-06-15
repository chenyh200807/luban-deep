#!/usr/bin/env python3
"""L2 learning-efficiency A/B for the Nexus/KnowQL/GBrain loop.

Arms:
- A0: current baseline `/api/v1/ws` deep_question grading path.
- B1: Nexus V1 case-rubric grading path without KnowQL/PGO shadow.
- B2: Nexus V1 + deterministic KnowQL/PGO shadow + Grading-to-Brain preview + NBA used
  as the retest intervention.
- B3: direct KnowQL `retrieve_rubric` microbenchmark; never counted as learning effect.

The runner never flips production defaults, never writes official scores, and treats canonical
truth writes as a hard safety NO-GO signal. B2 is intentionally marked as runner-level NBA
freeze because the current server helper still constructs NBA whenever PGO readback succeeds.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlparse, urlunparse

import httpx
import websockets


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ARTIFACT_ROOT = REPO / "artifacts" / "luban_grading_artifacts"
ARM_DEFINITIONS: dict[str, dict[str, Any]] = {
    "A0": {
        "runtime_mode": "rag_reference_baseline",
        "label": "original RAG/ref baseline",
        "case_rubric_v1": False,
        "knowql": False,
        "pgo_shadow": False,
        "gbrain_preview": False,
        "nba_intervention": False,
    },
    "B1": {
        "runtime_mode": "nexus_v1_without_knowql",
        "label": "Nexus V1 grading shape without KnowQL",
        "case_rubric_v1": True,
        "knowql": False,
        "pgo_shadow": False,
        "gbrain_preview": False,
        "nba_intervention": False,
    },
    "B2": {
        "runtime_mode": "nexus_v1_with_knowql",
        "label": "Nexus V1 + KnowQL/PGO + Grading-to-Brain preview",
        "case_rubric_v1": True,
        "knowql": True,
        "pgo_shadow": True,
        "gbrain_preview": True,
        "nba_intervention": True,
    },
}
LEARNING_ARMS = tuple(ARM_DEFINITIONS.keys())


class Scenario(NamedTuple):
    scenario_id: str
    question_id: str
    question: str
    correct_answer: str
    initial_answer: str
    baseline_retest_answer: str
    targeted_retest_answer: str
    outcome_terms: tuple[str, ...]


class RunItem(NamedTuple):
    loop_index: int
    arm: str


DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        scenario_id="pgo_xw2015_e0_retest_delta",
        question_id="2015::EXAM_XW2015_CASE_1::E0",
        question="施工总进度计划还缺少哪些内容？",
        correct_answer="施工总进度计划表，开竣工日期及工期一览表，资源需要量及供应平衡表。",
        initial_answer="还需要施工总进度计划表。",
        baseline_retest_answer="还需要补充施工总进度计划表，并说明计划安排。",
        targeted_retest_answer="还需要施工总进度计划表、开竣工日期及工期一览表、资源需要量及供应平衡表。",
        outcome_terms=("施工总进度计划表", "开竣工日期", "工期一览表", "资源需要量", "供应平衡表"),
    ),
    Scenario(
        scenario_id="pgo_xw2015_e1_network_plan_retest_delta",
        question_id="2015::EXAM_XW2015_CASE_1::E1",
        question="指出网络图关键线路、调整做法和调整后的总工期。",
        correct_answer="关键线路有 A→B→F→H→I 和 A→D→G→H→I；3—4 之间增加一个虚工作；总工期为 25 个月。",
        initial_answer="关键线路是 A→B→F→H→I，总工期为 25 个月。",
        baseline_retest_answer="关键线路是 A→B→F→H→I，总工期 25 个月，并应调整网络图。",
        targeted_retest_answer="关键线路有 A→B→F→H→I 和 A→D→G→H→I；3—4 之间增加一个虚工作；总工期 25 个月。",
        outcome_terms=("A→B→F→H→I", "A→D→G→H→I", "虚工作", "25个月"),
    ),
    Scenario(
        scenario_id="pgo_xw2015_case2_e0_steel_install_prep_delta",
        question_id="2015::EXAM_XW2015_CASE_2::E0",
        question="钢结构安装前应做哪些准备工作？",
        correct_answer="安装机械的选择；钢构件预检和配套；安装流水段划分和安装顺序确定；定位轴线、标高和地脚螺栓检查；场地平整坚实、排水良好、车辆进出方便。",
        initial_answer="需要选择安装机械，并做好钢构件预检和配套。",
        baseline_retest_answer="需要选择安装机械、检查钢构件，并确认现场具备安装条件。",
        targeted_retest_answer="需要选择安装机械、钢构件预检和配套、划分安装流水段并确定安装顺序、检查定位轴线标高和地脚螺栓、保证场地平整坚实且排水和车辆进出条件良好。",
        outcome_terms=("安装机械", "钢构件预检", "安装流水段", "安装顺序", "定位轴线", "地脚螺栓", "排水", "车辆进出"),
    ),
    Scenario(
        scenario_id="pgo_xw2015_case3_e0_dangerous_works_delta",
        question_id="2015::EXAM_XW2015_CASE_3::E0",
        question="本工程哪些分部分项工程属于危险性较大的工程？",
        correct_answer="深基坑支护工程、模板工程及支撑体系、建筑幕墙安装工程、降水工程、土方开挖工程。",
        initial_answer="有深基坑支护工程和模板工程及支撑体系。",
        baseline_retest_answer="有深基坑支护、模板支撑体系等危险性较大的工程。",
        targeted_retest_answer="包括深基坑支护工程、模板工程及支撑体系、建筑幕墙安装工程、降水工程、土方开挖工程。",
        outcome_terms=("深基坑支护", "模板工程", "支撑体系", "建筑幕墙", "降水工程", "土方开挖"),
    ),
    Scenario(
        scenario_id="pgo_xw2015_case5_e2_temp_power_plan_delta",
        question_id="2015::EXAM_XW2015_CASE_5::E2",
        question="指出现场施工用电组织设计的不妥之处、正确做法和验收参加部门。",
        correct_answer="项目经理安排土建技术人员编制临电组织设计不妥；应由电气工程技术人员编制，相关部门审核，经具有法人资格企业的技术负责人批准并由现场监理签认后实施；临电使用前由编制部门、审核部门、批准部门和使用部门共同参加验收。",
        initial_answer="不妥之处是由土建技术人员编制，应由电气工程技术人员编制。",
        baseline_retest_answer="应由电气工程技术人员编制，并经相关负责人批准后实施。",
        targeted_retest_answer="项目经理安排土建技术人员编制不妥；应由电气工程技术人员编制，相关部门审核，经具有法人资格企业技术负责人批准并由现场监理签认后实施；临电使用前编制部门、审核部门、批准部门和使用部门共同参加验收。",
        outcome_terms=("土建技术人员", "电气工程技术人员", "相关部门审核", "企业技术负责人批准", "监理签认", "编制部门", "审核部门", "批准部门", "使用部门"),
    ),
)


def build_preregistration(
    *,
    sample_count: int,
    loops: int,
    min_loops: int,
    min_b2_delta_lift: float,
    min_b2_outcome_miss_reduction_lift: float,
    max_b2_p95_latency_delta_pct: float = 250.0,
    max_b2_payload_delta_pct: float = 50.0,
    max_b3_p95_ms: float = 50.0,
) -> dict[str, Any]:
    minimum_loops = int(min_loops or loops or 0)
    return {
        "schema_version": "knowql_nexus_l2_preregistration.v1",
        "experiment": "Nexus/KnowQL/GBrain integrated learning-efficiency A/B",
        "analysis_unit": "scenario_loop_arm_initial_retest_pair",
        "population": "qa/operator true-entry /api/v1/ws cohort on test2",
        "minimum_preregistered_scenarios": int(sample_count or 0),
        "minimum_preregistered_loops": minimum_loops,
        "sample_manifest_hash": sample_manifest_hash(),
        "primary_effect_metric": "b2_outcome_miss_reduction_lift_vs_b1",
        "secondary_effect_metrics": [
            "b2_delta_lift_vs_a0",
            "b2_delta_lift_vs_b1",
            "b2_pgo_miss_reduction_lift_vs_b1",
        ],
        "diagnostic_metrics": [
            "avg_ttft_ms",
            "p95_ttft_ms",
            "p95_result_latency_ms",
            "streaming_observed_rate",
            "score_first_observed_rate",
            "avg_payload_bytes",
            "p95_payload_bytes",
            "b2_nba_intervention_applied_count",
            "B3 p95 latency/payload excluded from learning effect",
        ],
        "safety_guardrails": [
            "canonical_truth_write_count == 0",
            "official_score_write_count == 0",
            "unsafe_write_signal_count == 0",
            "a0_pgo_shadow_present_count == 0",
            "b1_pgo_shadow_present_count == 0",
            "b2_pgo_shadow_effective_count == B2 turn_count",
            "b2_knowql_runtime_consumed_count == B2 turn_count",
            "b2_g3_preview_readback_count == B2 turn_count",
            "b2_nba_intervention_applied_count == B2 completed_loops",
            "row_error_rate == 0",
            f"b2_p95_latency_delta_pct_vs_b1 <= {float(max_b2_p95_latency_delta_pct)}",
            f"b2_payload_delta_pct_vs_b1 <= {float(max_b2_payload_delta_pct)}",
            f"B3 p95 latency <= {float(max_b3_p95_ms)} ms",
        ],
        "minimum_effect_thresholds": {
            "b2_delta_lift_vs_a0": float(min_b2_delta_lift),
            "b2_outcome_miss_reduction_lift_vs_b1": float(min_b2_outcome_miss_reduction_lift),
        },
        "decision_rule": {
            "go_requires": [
                "L2_SAFETY_GO",
                "L2_EFFECT_POSITIVE",
            ],
            "no_go_if": [
                "any safety guardrail fails",
                "any learning arm has completed_loops < minimum_preregistered_loops",
                "B2 PGO/KnowQL/G3 readback is missing",
                "B3 is used as learning-effect evidence",
            ],
        },
        "truth_promotion_rule": (
            "same-point B2 initial weakness must be resolved on retest before stable-claim candidate; "
            "canonical_truth_written remains false"
        ),
        "compiler_feedback_rule": (
            "low-confidence, high-dispute, teacher-correction, and common-miss signals become work orders only"
        ),
    }


def scenario_manifest(*, include_answers: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in DEFAULT_SCENARIOS:
        row: dict[str, Any] = {
            "scenario_id": scenario.scenario_id,
            "question_id": scenario.question_id,
            "outcome_term_count": len(scenario.outcome_terms),
        }
        if include_answers:
            row.update({
                "question": scenario.question,
                "correct_answer": scenario.correct_answer,
                "initial_answer": scenario.initial_answer,
                "baseline_retest_answer": scenario.baseline_retest_answer,
                "targeted_retest_answer": scenario.targeted_retest_answer,
                "outcome_terms": list(scenario.outcome_terms),
            })
        rows.append(row)
    return rows


def sample_manifest_hash() -> str:
    payload = json.dumps(scenario_manifest(include_answers=True), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def independent_outcome_score(scenario: Scenario, answer: str) -> dict[str, Any]:
    normalized_answer = _normalize_for_outcome(answer)
    terms = [term for term in scenario.outcome_terms if str(term or "").strip()]
    hit_count = sum(1 for term in terms if _normalize_for_outcome(term) in normalized_answer)
    total = len(terms)
    miss_count = max(0, total - hit_count)
    return {
        "outcome_authority": "scripted_preregistered_gold_terms",
        "outcome_term_count": total,
        "outcome_hit_count": hit_count,
        "outcome_miss_count": miss_count,
        "outcome_score_ratio": round(hit_count / total, 6) if total else None,
    }


def _normalize_for_outcome(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("->", "→")


def build_learning_schedule(*, loops: int, order_mode: str = "alternating", seed: int | None = None) -> list[RunItem]:
    schedule: list[RunItem] = []
    normalized = str(order_mode or "alternating").strip().lower()
    rng = random.Random(seed)
    for loop_index in range(1, max(1, int(loops or 1)) + 1):
        arms = list(LEARNING_ARMS)
        if normalized == "reverse":
            arms.reverse()
        elif normalized == "randomized":
            rng.shuffle(arms)
        elif normalized == "alternating" and loop_index % 2 == 0:
            arms.reverse()
        schedule.extend(RunItem(loop_index=loop_index, arm=arm) for arm in arms)
    return schedule


def build_ws_url(api_base_url: str) -> str:
    parsed = urlparse(str(api_base_url or "").rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + "/api/v1/ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def build_ws_frame(
    scenario: Scenario,
    *,
    arm: str,
    run_id: str,
    loop_index: int,
    phase: str,
    content: str,
) -> dict[str, Any]:
    normalized_arm = str(arm or "").strip().upper()
    normalized_phase = str(phase or "").strip().lower() or "initial"
    client_turn_id = f"{run_id}:l{loop_index:02d}:{normalized_arm}:{normalized_phase}"
    config: dict[str, Any] = {
        "client_turn_id": client_turn_id,
        "followup_question_context": {
            "question_id": scenario.question_id,
            "question_type": "case",
            "question": scenario.question,
            "correct_answer": scenario.correct_answer,
        },
    }
    if ARM_DEFINITIONS.get(normalized_arm, {}).get("pgo_shadow"):
        config["grading_engine_pgo_shadow"] = True
    return {
        "type": "start_turn",
        "content": content,
        "capability": "deep_question",
        "language": "zh",
        "config": config,
    }


def summarize_l2_rows(
    rows: list[dict[str, Any]],
    *,
    b3_rows: list[dict[str, Any]],
    min_loops: int = 1,
    min_b2_delta_lift: float = 0.05,
    min_b2_outcome_miss_reduction_lift: float = 1.0,
    max_b2_p95_latency_delta_pct: float = 250.0,
    max_b2_payload_delta_pct: float = 50.0,
    max_b3_p95_ms: float = 50.0,
) -> dict[str, Any]:
    arms = {arm: _learning_arm_stats([row for row in rows if row.get("arm") == arm]) for arm in LEARNING_ARMS}
    safety = _safety_summary(rows)
    b3_stats = _b3_stats(b3_rows)
    completed = {arm: arms[arm]["completed_loops"] for arm in LEARNING_ARMS}
    a0_delta = float(arms["A0"].get("avg_retest_delta") or 0.0)
    b1_delta = float(arms["B1"].get("avg_retest_delta") or 0.0)
    b2_delta = float(arms["B2"].get("avg_retest_delta") or 0.0)
    b1_lift_vs_a0 = round(b1_delta - a0_delta, 6)
    b1_lift_vs_b2 = round(b1_delta - b2_delta, 6)
    b2_lift_vs_a0 = round(b2_delta - a0_delta, 6)
    b2_lift_vs_b1 = round(b2_delta - b1_delta, 6)
    b1_pgo_miss_lift_vs_b2 = round(
        float(arms["B1"].get("avg_pgo_miss_reduction") or 0.0)
        - float(arms["B2"].get("avg_pgo_miss_reduction") or 0.0),
        6,
    )
    b2_pgo_miss_lift_vs_b1 = round(
        float(arms["B2"].get("avg_pgo_miss_reduction") or 0.0)
        - float(arms["B1"].get("avg_pgo_miss_reduction") or 0.0),
        6,
    )
    b2_outcome_miss_lift_vs_b1 = round(
        float(arms["B2"].get("avg_outcome_miss_reduction") or 0.0)
        - float(arms["B1"].get("avg_outcome_miss_reduction") or 0.0),
        6,
    )
    b2_p95_latency_delta_pct_vs_b1 = _pct_delta(
        arms["B2"].get("p95_latency_ms"),
        arms["B1"].get("p95_latency_ms"),
    )
    b2_payload_delta_pct_vs_b1 = _pct_delta(
        arms["B2"].get("avg_payload_bytes"),
        arms["B1"].get("avg_payload_bytes"),
    )

    reasons: list[str] = []
    if safety["canonical_truth_write_count"]:
        reasons.append("canonical_truth_write_detected")
    if safety["official_score_write_count"]:
        reasons.append("official_score_write_detected")
    if safety["unsafe_write_signal_count"]:
        reasons.append("unsafe_write_signal_detected")
    if safety["a0_pgo_shadow_present_count"]:
        reasons.append("a0_pgo_shadow_present")
    if safety["b1_pgo_shadow_present_count"]:
        reasons.append("b1_pgo_shadow_present")
    total_b2 = max(1, int(arms["B2"].get("turn_count") or 0))
    if total_b2 and safety["b2_pgo_shadow_effective_count"] < total_b2:
        reasons.append("b2_pgo_shadow_not_effective")
    if total_b2 and safety["b2_knowql_runtime_consumed_count"] < total_b2:
        reasons.append("b2_knowql_not_runtime_consumed")
    if total_b2 and safety["b2_g3_preview_readback_count"] < total_b2:
        reasons.append("b2_g3_preview_missing")
    for arm in LEARNING_ARMS:
        if completed[arm] < int(min_loops or 0):
            reasons.append(f"{arm.lower()}_insufficient_loop_count")
        if int(arms[arm].get("ok_count") or 0) <= 0:
            reasons.append(f"{arm.lower()}_success_rate_zero")
        if int(arms[arm].get("error_count") or 0) > 0:
            reasons.append(f"{arm.lower()}_row_errors_present")
    if completed["B2"] and safety["b2_nba_intervention_applied_count"] < completed["B2"]:
        reasons.append("b2_nba_intervention_missing")
    if b3_rows and int(b3_stats.get("ok_count") or 0) < int(b3_stats.get("count") or 0):
        reasons.append("b3_microbenchmark_failures")
    if b3_rows and float(b3_stats.get("p95_latency_ms") or 0.0) > float(max_b3_p95_ms):
        reasons.append("b3_p95_latency_exceeded")
    if b2_p95_latency_delta_pct_vs_b1 > float(max_b2_p95_latency_delta_pct):
        reasons.append("b2_p95_latency_delta_exceeded")
    if b2_payload_delta_pct_vs_b1 > float(max_b2_payload_delta_pct):
        reasons.append("b2_payload_delta_exceeded")

    safety_status = "L2_SAFETY_NO_GO" if reasons else "L2_SAFETY_GO"
    if safety_status != "L2_SAFETY_GO":
        effect_status = "L2_EFFECT_NOT_EVALUABLE"
    elif (
        b2_outcome_miss_lift_vs_b1 >= float(min_b2_outcome_miss_reduction_lift)
        and b2_lift_vs_b1 >= 0.0
    ):
        effect_status = "L2_EFFECT_POSITIVE"
    else:
        effect_status = "L2_EFFECT_NEUTRAL_OR_NEGATIVE"

    return {
        "arms": arms,
        "comparison": {
            "completed_loops": completed,
            "min_loops": int(min_loops or 0),
            "b1_delta_lift_vs_a0": b1_lift_vs_a0,
            "b1_delta_lift_vs_b2": b1_lift_vs_b2,
            "b1_pgo_miss_reduction_lift_vs_b2": b1_pgo_miss_lift_vs_b2,
            "b2_delta_lift_vs_a0": b2_lift_vs_a0,
            "b2_delta_lift_vs_b1": b2_lift_vs_b1,
            "b2_pgo_miss_reduction_lift_vs_b1": b2_pgo_miss_lift_vs_b1,
            "b2_outcome_miss_reduction_lift_vs_b1": b2_outcome_miss_lift_vs_b1,
            "b2_p95_latency_delta_pct_vs_b1": b2_p95_latency_delta_pct_vs_b1,
            "b2_payload_delta_pct_vs_b1": b2_payload_delta_pct_vs_b1,
            "min_b2_delta_lift": float(min_b2_delta_lift),
            "min_b2_outcome_miss_reduction_lift": float(min_b2_outcome_miss_reduction_lift),
            "max_b2_p95_latency_delta_pct": float(max_b2_p95_latency_delta_pct),
            "max_b2_payload_delta_pct": float(max_b2_payload_delta_pct),
            "max_b3_p95_ms": float(max_b3_p95_ms),
            "score_first_proxy_field": "result.metadata.grading_shape.score_first",
            "b2_design": {
                "server_nba_freeze_supported": False,
                "runner_applies_nba_intervention": True,
                "interpretation": "B2 is the integrated Nexus/KnowQL/GBrain/NBA loop; B1 isolates Nexus V1 without KnowQL.",
            },
        },
        "safety": safety,
        "b3_microbenchmark": b3_stats,
        "learner_truth_promotion_preview": build_learner_truth_promotion_preview(rows),
        "compiler_feedback_loop": build_compiler_feedback_loop(rows),
        "decision": {
            "status": (
                "L2_LEARNING_AB_GO"
                if safety_status == "L2_SAFETY_GO" and effect_status == "L2_EFFECT_POSITIVE"
                else "L2_LEARNING_AB_NO_GO"
            ),
            "safety_status": safety_status,
            "effect_status": effect_status,
            "reasons": reasons,
            "canonical_truth_written": safety["canonical_truth_write_count"] > 0,
            "official_score_written": safety["official_score_write_count"] > 0,
        },
    }


def build_learner_truth_promotion_preview(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Preview-only gate for learner-truth promotion.

    Same-point weakness evidence must be observed in the initial B2 attempt and
    verified as resolved in the retest before it becomes a stable-claim
    candidate. This function never writes canonical learner truth.
    """
    candidates: list[dict[str, Any]] = []
    by_loop: dict[int, dict[str, dict[str, Any]]] = {}
    for row in rows:
        if str(row.get("arm") or "").upper() != "B2":
            continue
        try:
            loop = int(row.get("loop_index"))
        except (TypeError, ValueError):
            continue
        phase = str(row.get("turn_phase") or "").strip().lower()
        if phase in {"initial", "retest"}:
            by_loop.setdefault(loop, {})[phase] = row
    for loop, pair in sorted(by_loop.items()):
        initial = pair.get("initial")
        retest = pair.get("retest")
        if not initial or not retest:
            continue
        initial_missed = set(_pgo_missed_point_ids(initial))
        retest_missed = set(_pgo_missed_point_ids(retest))
        resolved = sorted(initial_missed - retest_missed)
        for point_id in resolved:
            candidates.append({
                "loop_index": loop,
                "point_id": point_id,
                "gate_basis": "same_point_retest_verified",
                "source": "B2_pgo_weakness_to_retest_delta",
                "canonical_truth_written": False,
                "promotion_allowed": True,
            })
    return {
        "promotion_allowed": bool(candidates),
        "canonical_truth_written": False,
        "stable_claim_candidates": candidates,
        "blocked_reasons": [] if candidates else ["missing_same_point_retest_improvement"],
    }


def build_compiler_feedback_loop(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Materialize actionable compiler feedback without promoting artifact truth."""
    work_orders: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    miss_counts: dict[str, int] = {}
    artifact_by_point: dict[str, str] = {}

    def _add(feedback_type: str, point_id: str, artifact_version: str = "") -> None:
        normalized_point = str(point_id or "").strip()
        if not normalized_point:
            return
        version = str(artifact_version or "case_rubric_scored_pgo").strip()
        key = (feedback_type, normalized_point, version)
        if key in seen:
            return
        seen.add(key)
        work_orders.append({
            "feedback_type": feedback_type,
            "point_id": normalized_point,
            "artifact_version": version,
            "promotion_allowed": False,
            "canonical_truth_written": False,
        })

    for row in rows:
        if str(row.get("arm") or "").upper() != "B2":
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        shadow = metadata.get("luban_case_rubric_pgo_shadow") if isinstance(metadata.get("luban_case_rubric_pgo_shadow"), dict) else {}
        query = shadow.get("knowql_query") if isinstance(shadow.get("knowql_query"), dict) else {}
        artifact_version = str(query.get("artifact_version") or "case_rubric_scored_pgo").strip()
        for point_id in list(shadow.get("low_confidence_point_ids") or []):
            _add("low_confidence_point", str(point_id), artifact_version)
        for point_id in list(shadow.get("dispute_point_ids") or []):
            _add("high_dispute_point", str(point_id), artifact_version)
        for point_id in _pgo_missed_point_ids(row):
            miss_counts[point_id] = miss_counts.get(point_id, 0) + 1
            artifact_by_point[point_id] = artifact_version
        g3 = metadata.get("pgo_grading_to_brain") if isinstance(metadata.get("pgo_grading_to_brain"), dict) else {}
        for correction in list(g3.get("teacher_corrections") or []):
            if isinstance(correction, dict):
                _add("teacher_correction", str(correction.get("point_id") or ""), artifact_version)

    for point_id, count in sorted(miss_counts.items()):
        if count >= 2:
            _add("common_student_miss", point_id, artifact_by_point.get(point_id, ""))
    return {
        "compiler_feedback_ready": bool(work_orders),
        "work_orders": work_orders,
        "promotion_allowed": False,
        "canonical_truth_written": False,
    }


def safe_knowql_summary(payload: dict[str, Any]) -> dict[str, Any]:
    scoring_points = list(payload.get("scoring_points") or []) if isinstance(payload, dict) else []
    point_ids = [
        str(point.get("point_id") or "").strip()
        for point in scoring_points
        if isinstance(point, dict) and str(point.get("point_id") or "").strip()
    ]
    return {
        "found": bool(payload.get("found")) if isinstance(payload, dict) else False,
        "fail_open": bool(payload.get("fail_open")) if isinstance(payload, dict) else True,
        "reason": str(payload.get("reason") or "").strip() if isinstance(payload, dict) else "invalid_payload",
        "question_id": str(payload.get("question_id") or "").strip() if isinstance(payload, dict) else "",
        "artifact_version": str(payload.get("artifact_version") or "").strip() if isinstance(payload, dict) else "",
        "purpose": str(payload.get("purpose") or "").strip() if isinstance(payload, dict) else "",
        "shape": str(payload.get("shape") or "").strip() if isinstance(payload, dict) else "",
        "budget": payload.get("budget") if isinstance(payload.get("budget"), dict) else {},
        "ground": payload.get("ground") if isinstance(payload.get("ground"), dict) else {},
        "confidence": payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {},
        "scoring_point_count": len(scoring_points),
        "point_ids": point_ids[:30],
    }


async def run_l2_learning_ab(
    *,
    api_base_url: str,
    token: str,
    loops: int,
    timeout_seconds: float,
    out_dir: Path,
    min_loops: int,
    order_mode: str,
    seed: int | None,
    b3_iterations: int,
    connection_mode: str,
    inter_turn_delay_seconds: float,
    min_b2_delta_lift: float,
    min_b2_outcome_miss_reduction_lift: float,
    max_b2_p95_latency_delta_pct: float,
    max_b2_payload_delta_pct: float,
    max_b3_p95_ms: float,
) -> dict[str, Any]:
    run_id = f"knowql_nexus_l2_learning_ab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    ws_url = build_ws_url(api_base_url)
    rows: list[dict[str, Any]] = []
    schedule = build_learning_schedule(loops=loops, order_mode=order_mode, seed=seed)
    normalized_connection_mode = (
        "per-turn" if str(connection_mode or "").strip().lower() == "per-turn" else "single"
    )
    delay_seconds = max(0.0, float(inter_turn_delay_seconds or 0.0))

    async def _run_turn(frame: dict[str, Any], item: RunItem, scenario: Scenario, phase: str, *, nba_applied: bool) -> dict[str, Any]:
        if normalized_connection_mode == "single":
            return await _run_one_ws_turn_on_connection(
                websocket=websocket,
                frame=frame,
                arm=item.arm,
                loop_index=item.loop_index,
                turn_phase=phase,
                scenario=scenario,
                timeout_seconds=timeout_seconds,
                nba_intervention_applied=nba_applied,
            )
        return await _run_one_ws_turn(
            ws_url=ws_url,
            token=token,
            frame=frame,
            arm=item.arm,
            loop_index=item.loop_index,
            turn_phase=phase,
            scenario=scenario,
            timeout_seconds=timeout_seconds,
            nba_intervention_applied=nba_applied,
        )

    websocket = None
    if normalized_connection_mode == "single":
        async with _connect_ws(ws_url, token=token) as opened:
            websocket = opened
            for order_index, item in enumerate(schedule, start=1):
                await _run_learning_item(
                    item=item,
                    order_index=order_index,
                    run_id=run_id,
                    rows=rows,
                    run_turn=_run_turn,
                    inter_turn_delay_seconds=delay_seconds,
                )
                if delay_seconds and order_index < len(schedule):
                    await asyncio.sleep(delay_seconds)
    else:
        for order_index, item in enumerate(schedule, start=1):
            await _run_learning_item(
                item=item,
                order_index=order_index,
                run_id=run_id,
                rows=rows,
                run_turn=_run_turn,
                inter_turn_delay_seconds=delay_seconds,
            )
            if delay_seconds and order_index < len(schedule):
                await asyncio.sleep(delay_seconds)

    b3_rows = run_b3_microbenchmark(iterations=b3_iterations)
    summary = summarize_l2_rows(
        rows,
        b3_rows=b3_rows,
        min_loops=min_loops,
        min_b2_delta_lift=min_b2_delta_lift,
        min_b2_outcome_miss_reduction_lift=min_b2_outcome_miss_reduction_lift,
        max_b2_p95_latency_delta_pct=max_b2_p95_latency_delta_pct,
        max_b2_payload_delta_pct=max_b2_payload_delta_pct,
        max_b3_p95_ms=max_b3_p95_ms,
    )
    preregistration = build_preregistration(
        sample_count=len(DEFAULT_SCENARIOS),
        loops=loops,
        min_loops=min_loops,
        min_b2_delta_lift=min_b2_delta_lift,
        min_b2_outcome_miss_reduction_lift=min_b2_outcome_miss_reduction_lift,
        max_b2_p95_latency_delta_pct=max_b2_p95_latency_delta_pct,
        max_b2_payload_delta_pct=max_b2_payload_delta_pct,
        max_b3_p95_ms=max_b3_p95_ms,
    )
    manifest = {
        "run_id": run_id,
        "mode": "live-learning-efficiency-ab",
        "entry": "remote /api/v1/ws A0/B1/B2 plus local B3 retrieve_rubric microbenchmark",
        "api_base_url": str(api_base_url or "").rstrip("/"),
        "ws_url": ws_url,
        "loops": loops,
        "min_loops": min_loops,
        "order_mode": order_mode,
        "seed": seed,
        "connection_mode": normalized_connection_mode,
        "inter_turn_delay_seconds": delay_seconds,
        "sample_ids": sorted({scenario.scenario_id for scenario in DEFAULT_SCENARIOS}),
        "sample_manifest_hash": sample_manifest_hash(),
        "sample_manifest_public": scenario_manifest(include_answers=False),
        "preregistration": preregistration,
        "arms": {
            **{arm: dict(definition) for arm, definition in ARM_DEFINITIONS.items()},
            "B3": {
                "runtime_mode": "knowql_microbenchmark",
                "label": "KnowQL retrieve_rubric microbenchmark only; excluded from learning effect",
                "learning_effect_eligible": False,
            },
        },
        "server_nba_freeze_supported": False,
        "remote_write_requested": False,
        "production_default_flip_requested": False,
        "canonical_truth_write_allowed": False,
        "official_score_write_allowed": False,
        "exit_code_intent": {"go": 0, "no_go": 1, "auth_blocked": 2},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "manifest.json", manifest)
    _write_jsonl(out_dir / "raw_learning_rows.jsonl", rows)
    _write_jsonl(out_dir / "raw_b3_microbenchmark_rows.jsonl", b3_rows)
    _write_json(out_dir / "summary.json", summary)
    _write_markdown(out_dir / "FINDING_knowql_nexus_l2_learning_ab.md", manifest=manifest, summary=summary)
    return {"out_dir": str(out_dir), "manifest": manifest, "summary": summary}


async def _run_learning_item(
    *,
    item: RunItem,
    order_index: int,
    run_id: str,
    rows: list[dict[str, Any]],
    run_turn: Any,
    inter_turn_delay_seconds: float = 0.0,
) -> None:
    scenario = DEFAULT_SCENARIOS[(item.loop_index - 1) % len(DEFAULT_SCENARIOS)]
    initial_frame = build_ws_frame(
        scenario,
        arm=item.arm,
        run_id=run_id,
        loop_index=item.loop_index,
        phase="initial",
        content=scenario.initial_answer,
    )
    initial = await run_turn(initial_frame, item, scenario, "initial", nba_applied=False)
    initial["order_index"] = order_index
    rows.append(initial)

    initial_meta = initial.get("metadata") if isinstance(initial.get("metadata"), dict) else {}
    pgo_g3 = initial_meta.get("pgo_grading_to_brain") if isinstance(initial_meta.get("pgo_grading_to_brain"), dict) else {}
    b2_has_nba = item.arm == "B2" and isinstance(pgo_g3.get("next_best_action"), dict)
    nba_applied = bool(b2_has_nba)
    retest_answer = scenario.targeted_retest_answer if nba_applied else scenario.baseline_retest_answer
    if inter_turn_delay_seconds:
        await asyncio.sleep(max(0.0, float(inter_turn_delay_seconds or 0.0)))
    retest_frame = build_ws_frame(
        scenario,
        arm=item.arm,
        run_id=run_id,
        loop_index=item.loop_index,
        phase="retest",
        content=retest_answer,
    )
    retest = await run_turn(retest_frame, item, scenario, "retest", nba_applied=nba_applied)
    retest["order_index"] = order_index
    retest["nba_intervention_applied"] = nba_applied
    rows.append(retest)


def run_b3_microbenchmark(*, iterations: int) -> list[dict[str, Any]]:
    from deeptutor.services.construction_grading.m35_artifact_query import (
        M35ArtifactQuery,
        retrieve_rubric,
    )

    rows: list[dict[str, Any]] = []
    total = max(0, int(iterations or 0))
    for index in range(1, total + 1):
        scenario = DEFAULT_SCENARIOS[(index - 1) % len(DEFAULT_SCENARIOS)]
        started = time.perf_counter()
        error = ""
        safe: dict[str, Any] = {}
        try:
            result = retrieve_rubric(
                M35ArtifactQuery(
                    question_id=scenario.question_id,
                    purpose="grading",
                    shape="rubric_table",
                    citation_required=True,
                    budget_tier="low",
                )
            )
            safe = safe_knowql_summary(result)
        except Exception as exc:  # noqa: BLE001 - microbenchmark must capture row-level failure
            error = str(exc)[:500]
            safe = {"found": False, "fail_open": True, "reason": type(exc).__name__}
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        rows.append({
            "arm": "B3",
            "iteration": index,
            "scenario_id": scenario.scenario_id,
            "question_id": scenario.question_id,
            "ok": not error and bool(safe.get("found")) and not bool(safe.get("fail_open")),
            "duration_ms": duration_ms,
            "payload_bytes": len(json.dumps(safe, ensure_ascii=False).encode("utf-8")),
            "learning_effect_eligible": False,
            "error": error,
            "knowql_query": safe,
        })
    return rows


async def _run_one_ws_turn(
    *,
    ws_url: str,
    token: str,
    frame: dict[str, Any],
    arm: str,
    loop_index: int,
    turn_phase: str,
    scenario: Scenario,
    timeout_seconds: float,
    nba_intervention_applied: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    error = ""
    try:
        async with _connect_ws(ws_url, token=token) as websocket:
            return await _run_one_ws_turn_on_connection(
                websocket=websocket,
                frame=frame,
                arm=arm,
                loop_index=loop_index,
                turn_phase=turn_phase,
                scenario=scenario,
                timeout_seconds=timeout_seconds,
                nba_intervention_applied=nba_intervention_applied,
            )
    except Exception as exc:  # noqa: BLE001 - row-level failure must be captured
        error = str(exc)[:500]
    return _row_from_observed_events(
        started=started,
        events=[],
        error=error,
        arm=arm,
        loop_index=loop_index,
        turn_phase=turn_phase,
        scenario=scenario,
        nba_intervention_applied=nba_intervention_applied,
        submitted_answer=str(frame.get("content") or ""),
    )


async def _run_one_ws_turn_on_connection(
    *,
    websocket: Any,
    frame: dict[str, Any],
    arm: str,
    loop_index: int,
    turn_phase: str,
    scenario: Scenario,
    timeout_seconds: float,
    nba_intervention_applied: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    error = ""
    events: list[dict[str, Any]] = []
    try:
        await websocket.send(json.dumps(frame, ensure_ascii=False))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
            event = json.loads(raw)
            if not isinstance(event, dict):
                continue
            event["_observed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
            events.append(event)
            if event.get("type") in {"done", "error"}:
                break
    except Exception as exc:  # noqa: BLE001 - row-level failure must be captured
        error = str(exc)[:500]
    return _row_from_observed_events(
        started=started,
        events=events,
        error=error,
        arm=arm,
        loop_index=loop_index,
        turn_phase=turn_phase,
        scenario=scenario,
        nba_intervention_applied=nba_intervention_applied,
        submitted_answer=str(frame.get("content") or ""),
    )


def _row_from_events(
    *,
    started: float,
    result_event: dict[str, Any],
    terminal_event: dict[str, Any],
    event_count: int,
    error: str,
    arm: str,
    loop_index: int,
    turn_phase: str,
    scenario: Scenario,
    nba_intervention_applied: bool,
) -> dict[str, Any]:
    events = []
    if result_event:
        events.append(result_event)
    if terminal_event and terminal_event is not result_event:
        events.append(terminal_event)
    return _row_from_observed_events(
        started=started,
        events=events,
        error=error,
        arm=arm,
        loop_index=loop_index,
        turn_phase=turn_phase,
        scenario=scenario,
        nba_intervention_applied=nba_intervention_applied,
        submitted_answer=_scenario_answer_for_phase(
            scenario,
            phase=turn_phase,
            nba_intervention_applied=nba_intervention_applied,
        ),
    )


def _row_from_observed_events(
    *,
    started: float,
    events: list[dict[str, Any]],
    error: str,
    arm: str,
    loop_index: int,
    turn_phase: str,
    scenario: Scenario,
    nba_intervention_applied: bool,
    submitted_answer: str | None = None,
) -> dict[str, Any]:
    result_event = next((event for event in reversed(events) if event.get("type") == "result"), {})
    terminal_event = next((event for event in reversed(events) if event.get("type") in {"done", "error"}), {})
    observed_ms_by_event: dict[int, float] = {}

    def _observed_ms(event: dict[str, Any]) -> float:
        event_id = id(event)
        if event_id not in observed_ms_by_event:
            if event.get("_observed_ms") is not None:
                observed_ms_by_event[event_id] = _safe_float(event.get("_observed_ms"))
            else:
                observed_ms_by_event[event_id] = round((time.perf_counter() - started) * 1000.0, 3)
        return observed_ms_by_event[event_id]

    for event in events:
        _observed_ms(event)
    content_events = [
        event
        for event in events
        if str(event.get("type") or "").strip() == "content"
        and _public_content_text(event)
    ]
    ttft_ms = _observed_ms(content_events[0]) if content_events else None
    result_events = [event for event in events if str(event.get("type") or "").strip() == "result"]
    first_result_ms = _observed_ms(result_events[0]) if result_events else None
    if not result_event and terminal_event:
        first_result_ms = None
    duration_ms = (
        _observed_ms(terminal_event)
        if terminal_event
        else round((time.perf_counter() - started) * 1000.0, 3)
    )
    payload = _result_payload(result_event)
    metadata = payload if isinstance(payload, dict) else {}
    scored_answer = (
        str(submitted_answer)
        if submitted_answer is not None
        else _scenario_answer_for_phase(
            scenario,
            phase=turn_phase,
            nba_intervention_applied=nba_intervention_applied,
        )
    )
    outcome = independent_outcome_score(scenario, scored_answer)
    sealed_block_status = (
        "observed"
        if any(str(event.get("type") or "").strip() in {"sealed_block", "block_sealed"} for event in events)
        else "not_exercised"
    )
    score_first_observed, async_explanation_status = _score_first_observation(metadata)
    return {
        "loop_index": loop_index,
        "scenario_id": scenario.scenario_id,
        "question_id": scenario.question_id,
        "arm": arm,
        "turn_phase": turn_phase,
        "ok": bool(result_event) and not error and terminal_event.get("type") != "error",
        "duration_ms": duration_ms,
        "payload_bytes": len(json.dumps(result_event or terminal_event, ensure_ascii=False).encode("utf-8")),
        "event_count": len(events),
        "ttft_ms": ttft_ms,
        "first_result_ms": first_result_ms,
        "streaming_observed": bool(content_events),
        "content_event_count": len(content_events),
        "content_char_count": sum(len(_public_content_text(event)) for event in content_events),
        "sealed_block_status": sealed_block_status,
        "score_first_observed": score_first_observed,
        "async_explanation_status": async_explanation_status,
        "terminal_type": terminal_event.get("type") or "",
        "error": error,
        "terminal_event": _safe_terminal_event(terminal_event),
        "metadata": metadata,
        "score_ratio": _score_ratio_from_metadata(metadata),
        "pgo_miss_count": _pgo_miss_count(metadata),
        "nba_intervention_applied": bool(nba_intervention_applied),
        **outcome,
    }


def _scenario_answer_for_phase(
    scenario: Scenario,
    *,
    phase: str,
    nba_intervention_applied: bool,
) -> str:
    if str(phase or "").strip().lower() == "initial":
        return scenario.initial_answer
    return scenario.targeted_retest_answer if nba_intervention_applied else scenario.baseline_retest_answer


def _learning_arm_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [float(row.get("duration_ms") or 0.0) for row in rows if row.get("duration_ms") is not None]
    ttfts = [float(row.get("ttft_ms") or 0.0) for row in rows if row.get("ttft_ms") is not None]
    first_results = [float(row.get("first_result_ms") or 0.0) for row in rows if row.get("first_result_ms") is not None]
    payloads = [int(row.get("payload_bytes") or 0) for row in rows if row.get("payload_bytes") is not None]
    ok_count = sum(1 for row in rows if row.get("ok") is True)
    streaming_count = sum(1 for row in rows if row.get("streaming_observed") is True)
    sealed_observed_count = sum(1 for row in rows if row.get("sealed_block_status") == "observed")
    sealed_not_exercised_count = sum(1 for row in rows if row.get("sealed_block_status") == "not_exercised")
    score_first_count = sum(1 for row in rows if row.get("score_first_observed") is True)
    deltas = _retest_deltas(rows, metric_key="outcome_score_ratio")
    server_score_deltas = _retest_deltas(rows, metric_key="score_ratio")
    outcome_miss_deltas = _retest_deltas(rows, metric_key="outcome_miss_count", invert=True)
    pgo_miss_deltas = _retest_deltas(rows, metric_key="pgo_miss_count", invert=True)
    return {
        "turn_count": len(rows),
        "ok_count": ok_count,
        "error_count": len(rows) - ok_count,
        "success_rate": round(ok_count / len(rows), 6) if rows else 0.0,
        "completed_loops": len(deltas),
        "avg_retest_delta": round(statistics.fmean(deltas), 6) if deltas else 0.0,
        "avg_server_score_retest_delta": round(statistics.fmean(server_score_deltas), 6) if server_score_deltas else 0.0,
        "avg_outcome_miss_reduction": round(statistics.fmean(outcome_miss_deltas), 6) if outcome_miss_deltas else 0.0,
        "avg_pgo_miss_reduction": round(statistics.fmean(pgo_miss_deltas), 6) if pgo_miss_deltas else 0.0,
        "avg_ttft_ms": round(statistics.fmean(ttfts), 3) if ttfts else 0.0,
        "p95_ttft_ms": _percentile(ttfts, 0.95),
        "avg_first_result_ms": round(statistics.fmean(first_results), 3) if first_results else 0.0,
        "p95_first_result_ms": _percentile(first_results, 0.95),
        "p95_result_latency_ms": _percentile(first_results, 0.95),
        "streaming_observed_count": streaming_count,
        "streaming_rate": round(streaming_count / len(rows), 6) if rows else 0.0,
        "streaming_observed_rate": round(streaming_count / len(rows), 6) if rows else 0.0,
        "sealed_block_observed_count": sealed_observed_count,
        "sealed_block_observed_rate": round(sealed_observed_count / len(rows), 6) if rows else 0.0,
        "sealed_block_not_exercised_count": sealed_not_exercised_count,
        "score_first_observed_count": score_first_count,
        "score_first_observed_rate": round(score_first_count / len(rows), 6) if rows else 0.0,
        "avg_latency_ms": round(statistics.fmean(durations), 3) if durations else 0.0,
        "p50_latency_ms": _percentile(durations, 0.50),
        "p95_latency_ms": _percentile(durations, 0.95),
        "avg_payload_bytes": int(statistics.fmean(payloads)) if payloads else 0,
        "p95_payload_bytes": int(_percentile(payloads, 0.95)) if payloads else 0,
    }


def _retest_deltas(rows: list[dict[str, Any]], *, metric_key: str, invert: bool = False) -> list[float]:
    by_loop: dict[int, dict[str, float]] = {}
    for row in rows:
        try:
            loop = int(row.get("loop_index"))
        except (TypeError, ValueError):
            continue
        phase = str(row.get("turn_phase") or "").strip().lower()
        if phase not in {"initial", "retest"}:
            continue
        value = row.get(metric_key)
        if value is None and metric_key == "score_ratio":
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            value = _score_ratio_from_metadata(metadata)
        if value is None and metric_key == "pgo_miss_count":
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            value = _pgo_miss_count(metadata)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        by_loop.setdefault(loop, {})[phase] = number
    deltas: list[float] = []
    for pair in by_loop.values():
        if "initial" not in pair or "retest" not in pair:
            continue
        delta = pair["initial"] - pair["retest"] if invert else pair["retest"] - pair["initial"]
        deltas.append(round(delta, 6))
    return deltas


def _b3_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [float(row.get("duration_ms") or 0.0) for row in rows if row.get("duration_ms") is not None]
    payloads = [int(row.get("payload_bytes") or 0) for row in rows if row.get("payload_bytes") is not None]
    ok_count = sum(1 for row in rows if row.get("ok") is True)
    return {
        "count": len(rows),
        "ok_count": ok_count,
        "success_rate": round(ok_count / len(rows), 6) if rows else 0.0,
        "avg_latency_ms": round(statistics.fmean(durations), 3) if durations else 0.0,
        "p95_latency_ms": _percentile(durations, 0.95),
        "avg_payload_bytes": int(statistics.fmean(payloads)) if payloads else 0,
        "p95_payload_bytes": int(_percentile(payloads, 0.95)) if payloads else 0,
        "learning_effect_eligible": False,
    }


def _safety_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "canonical_truth_write_count": 0,
        "official_score_write_count": 0,
        "unsafe_write_signal_count": 0,
        "a0_pgo_shadow_present_count": 0,
        "b1_pgo_shadow_present_count": 0,
        "b1_pgo_shadow_effective_count": 0,
        "b1_knowql_runtime_consumed_count": 0,
        "b1_g3_preview_readback_count": 0,
        "b2_pgo_shadow_present_count": 0,
        "b2_pgo_shadow_effective_count": 0,
        "b2_knowql_runtime_consumed_count": 0,
        "b2_g3_preview_readback_count": 0,
        "b2_nba_intervention_applied_count": 0,
    }
    for row in rows:
        arm = str(row.get("arm") or "").upper()
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if _recursive_true(metadata, "canonical_truth_written") or _recursive_true(metadata, "canonical_write_allowed"):
            summary["canonical_truth_write_count"] += 1
        if _recursive_true(metadata, "official_score_allowed") or _recursive_true(metadata, "official_score_written"):
            summary["official_score_write_count"] += 1
        summary["unsafe_write_signal_count"] += _unsafe_write_signal_count(metadata)
        shadow = metadata.get("luban_case_rubric_pgo_shadow") if isinstance(metadata, dict) else {}
        if arm == "A0" and isinstance(shadow, dict) and shadow:
            summary["a0_pgo_shadow_present_count"] += 1
        if arm in {"B1", "B2"}:
            prefix = arm.lower()
            if row.get("nba_intervention_applied") is True and arm == "B2":
                summary["b2_nba_intervention_applied_count"] += 1
            if isinstance(shadow, dict) and shadow:
                summary[f"{prefix}_pgo_shadow_present_count"] += 1
                status = str(shadow.get("shadow_status") or "").strip()
                query = shadow.get("knowql_query") if isinstance(shadow.get("knowql_query"), dict) else {}
                runtime_consumed = bool(query.get("runtime_consumed"))
                if runtime_consumed:
                    summary[f"{prefix}_knowql_runtime_consumed_count"] += 1
                if status == "ok" and runtime_consumed:
                    summary[f"{prefix}_pgo_shadow_effective_count"] += 1
            if isinstance(metadata.get("pgo_grading_to_brain"), dict):
                summary[f"{prefix}_g3_preview_readback_count"] += 1
    return summary


def _score_ratio_from_metadata(metadata: dict[str, Any]) -> float | None:
    result = metadata.get("construction_grading_result") if isinstance(metadata, dict) else {}
    if not isinstance(result, dict):
        return None
    for key in ("score_ratio", "coverage"):
        value = _float_or_none(result.get(key))
        if value is not None:
            return round(value, 6)
    awarded = _float_or_none(result.get("score_awarded"))
    if awarded is None:
        awarded = _float_or_none(result.get("awarded_score"))
    max_score = _float_or_none(result.get("max_score"))
    if awarded is None or not max_score:
        return None
    return round(max(0.0, min(1.0, awarded / max_score)), 6)


def _pgo_miss_count(metadata: dict[str, Any]) -> int | None:
    shadow = metadata.get("luban_case_rubric_pgo_shadow") if isinstance(metadata, dict) else {}
    if not isinstance(shadow, dict) or not shadow:
        return None
    verdicts = shadow.get("point_verdicts") if isinstance(shadow.get("point_verdicts"), dict) else {}
    if not verdicts:
        return None
    return sum(1 for verdict in verdicts.values() if str(verdict or "").strip().lower() != "hit")


def _pgo_missed_point_ids(row: dict[str, Any]) -> list[str]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    shadow = metadata.get("luban_case_rubric_pgo_shadow") if isinstance(metadata, dict) else {}
    if not isinstance(shadow, dict):
        return []
    verdicts = shadow.get("point_verdicts") if isinstance(shadow.get("point_verdicts"), dict) else {}
    return [
        str(point_id or "").strip()
        for point_id, verdict in verdicts.items()
        if str(point_id or "").strip()
        and str(verdict or "").strip().lower() != "hit"
    ]


def _result_payload(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {}
    for key in ("metadata", "payload", "data"):
        value = event.get(key)
        if isinstance(value, dict):
            return value
    return event if event.get("type") == "result" else {}


def _public_content_text(event: dict[str, Any]) -> str:
    if not isinstance(event, dict):
        return ""
    visibility = str(event.get("visibility") or "").strip().lower()
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    visibility = visibility or str(data.get("visibility") or metadata.get("visibility") or "").strip().lower()
    if visibility in {"hidden", "internal", "private"}:
        return ""
    for container in (event, data, metadata):
        for key in ("content", "delta", "text"):
            value = container.get(key) if isinstance(container, dict) else None
            if isinstance(value, str) and value.strip():
                return value
    return ""


def _score_first_observation(metadata: dict[str, Any]) -> tuple[bool, str]:
    shape = metadata.get("grading_shape") if isinstance(metadata, dict) else {}
    if isinstance(shape, dict):
        score_first = shape.get("score_first")
        if isinstance(score_first, dict) and score_first:
            explanation = shape.get("explanation") if isinstance(shape.get("explanation"), dict) else {}
            return True, str(explanation.get("async_status") or "not_exercised")
    disclosure = metadata.get("progressive_disclosure") if isinstance(metadata, dict) else {}
    if isinstance(disclosure, dict) and disclosure:
        return True, "progressive_disclosure_proxy"
    return False, "not_exercised"


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _percentile(values: list[float] | list[int], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.999999)))
    return round(ordered[index], 3)


def _pct_delta(value: Any, baseline: Any) -> float:
    current = _safe_float(value)
    base = _safe_float(baseline)
    if base <= 0:
        return 0.0
    return round(((current - base) / base) * 100.0, 6)


def _unsafe_write_signal_count(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {
                "canonical_write_allowed",
                "writeback_performed",
                "claim_promotion_allowed",
                "canonical_truth_written",
                "official_score_written",
                "production_write_performed",
            } and item is True:
                count += 1
            if key in {"db_write_count", "remote_write_count", "production_write_count"}:
                try:
                    if int(item or 0) > 0:
                        count += 1
                except (TypeError, ValueError):
                    pass
            count += _unsafe_write_signal_count(item)
    elif isinstance(value, list):
        count += sum(_unsafe_write_signal_count(item) for item in value)
    return count


def _recursive_true(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key and item_value is True:
                return True
            if _recursive_true(item_value, key):
                return True
    if isinstance(value, list):
        return any(_recursive_true(item, key) for item in value)
    return False


def _safe_terminal_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {}
    allowed: dict[str, Any] = {}
    for key in ("type", "code", "message", "content", "error", "reason", "detail", "data", "payload"):
        value = event.get(key)
        if value not in (None, ""):
            allowed[key] = str(value)[:500] if not isinstance(value, (dict, list)) else value
    return allowed


def _connect_ws(ws_url: str, *, token: str) -> Any:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        return websockets.connect(ws_url, additional_headers=headers)
    except TypeError:
        return websockets.connect(ws_url, extra_headers=headers)


async def resolve_token(
    *,
    api_base_url: str,
    auth_token: str,
    username: str,
    password: str,
    phone: str,
    register: bool,
) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if token:
        return {"ok": True, "token": token, "auth_mode": "provided_token"}
    if not username or not password:
        return {"ok": False, "reason": "missing_auth", "auth_mode": "none"}
    async with httpx.AsyncClient(base_url=str(api_base_url or "").rstrip("/"), timeout=30.0, trust_env=False) as client:
        if register:
            await client.post(
                "/api/v1/auth/register",
                json={"username": username, "password": password, "phone": phone},
            )
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        if response.status_code != 200:
            return {"ok": False, "reason": "login_failed", "status_code": response.status_code}
        payload = response.json()
        token = str(payload.get("token") or "").strip()
        if not token:
            return {"ok": False, "reason": "login_token_missing"}
        return {"ok": True, "token": token, "auth_mode": "login"}


def _generated_credentials(prefix: str) -> tuple[str, str, str]:
    stamp = int(time.time())
    username = f"{prefix}_{stamp}"
    password = f"L2Ab{stamp % 1000000:06d}"
    phone = f"137{stamp % 100000000:08d}"
    return username, password, phone


def _default_out_dir() -> Path:
    return ARTIFACT_ROOT / f"knowql_nexus_l2_learning_ab_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_markdown(path: Path, *, manifest: dict[str, Any], summary: dict[str, Any]) -> None:
    decision = summary["decision"]
    comparison = summary["comparison"]
    lines = [
        "# KnowQL Nexus L2 Learning A/B",
        "",
        f"- status: `{decision['status']}`",
        f"- safety status: `{decision['safety_status']}`",
        f"- effect status: `{decision['effect_status']}`",
        f"- api_base_url: `{manifest['api_base_url']}`",
        f"- loops: `{manifest['loops']}`",
        f"- min loops: `{manifest['min_loops']}`",
        f"- order mode: `{manifest['order_mode']}`",
        f"- connection mode: `{manifest['connection_mode']}`",
        f"- B2 delta lift vs A0: `{comparison['b2_delta_lift_vs_a0']}`",
        f"- B2 delta lift vs B1: `{comparison['b2_delta_lift_vs_b1']}`",
        f"- B2 outcome miss reduction lift vs B1: `{comparison['b2_outcome_miss_reduction_lift_vs_b1']}`",
        f"- B2 PGO miss reduction lift vs B1: `{comparison['b2_pgo_miss_reduction_lift_vs_b1']}`",
        f"- server NBA freeze supported: `{comparison['b2_design']['server_nba_freeze_supported']}`",
        f"- canonical truth writes: `{summary['safety']['canonical_truth_write_count']}`",
        f"- official score writes: `{summary['safety']['official_score_write_count']}`",
        f"- unsafe write signal count: `{summary['safety']['unsafe_write_signal_count']}`",
        f"- A0 PGO shadow present count: `{summary['safety']['a0_pgo_shadow_present_count']}`",
        f"- B2 NBA intervention applied count: `{summary['safety']['b2_nba_intervention_applied_count']}`",
        f"- B3 learning effect eligible: `{summary['b3_microbenchmark']['learning_effect_eligible']}`",
        f"- B3 p95 latency ms: `{summary['b3_microbenchmark']['p95_latency_ms']}`",
        f"- exit code intent: `{json.dumps(manifest.get('exit_code_intent', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Decision Reasons",
        "",
    ]
    reasons = list(decision.get("reasons") or [])
    lines.extend([f"- `{reason}`" for reason in reasons] or ["- none"])
    prereg = manifest.get("preregistration") if isinstance(manifest.get("preregistration"), dict) else {}
    if prereg:
        lines.extend([
            "",
            "## Pre-registration",
            "",
            f"- primary effect metric: `{prereg.get('primary_effect_metric')}`",
            f"- secondary effect metrics: `{', '.join(list(prereg.get('secondary_effect_metrics') or []))}`",
            f"- minimum preregistered scenarios: `{prereg.get('minimum_preregistered_scenarios')}`",
            f"- minimum preregistered loops: `{prereg.get('minimum_preregistered_loops')}`",
            f"- minimum effect thresholds: `{json.dumps(prereg.get('minimum_effect_thresholds') or {}, ensure_ascii=False, sort_keys=True)}`",
            f"- go requires: `{', '.join(list((prereg.get('decision_rule') or {}).get('go_requires') or []))}`",
            f"- safety guardrails: `{'; '.join(list(prereg.get('safety_guardrails') or []))}`",
        ])
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


async def _main_async(args: argparse.Namespace) -> int:
    username = args.username
    password = args.password
    phone = args.phone
    if args.register and (not username or not password or not phone):
        username, password, phone = _generated_credentials(args.username_prefix)
    auth = await resolve_token(
        api_base_url=args.api_base_url,
        auth_token=args.auth_token or os.environ.get("DEEPTUTOR_L2_AB_AUTH_TOKEN", ""),
        username=username,
        password=password,
        phone=phone,
        register=args.register,
    )
    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    if not auth.get("ok"):
        out_dir.mkdir(parents=True, exist_ok=True)
        blocked = {
            "status": "L2_AUTH_BLOCKED",
            "reason": auth.get("reason"),
            "api_base_url": args.api_base_url,
            "remote_write_requested": False,
            "canonical_truth_write_allowed": False,
        }
        _write_json(out_dir / "summary.json", {"decision": blocked})
        print(json.dumps({"out_dir": str(out_dir), "summary": {"decision": blocked}}, ensure_ascii=False, indent=2))
        return 2
    result = await run_l2_learning_ab(
        api_base_url=args.api_base_url,
        token=str(auth["token"]),
        loops=args.loops,
        timeout_seconds=args.timeout_seconds,
        out_dir=out_dir,
        min_loops=int(args.min_loops or args.loops),
        order_mode=args.order_mode,
        seed=args.seed,
        b3_iterations=args.b3_iterations,
        connection_mode=args.connection_mode,
        inter_turn_delay_seconds=args.inter_turn_delay_seconds,
        min_b2_delta_lift=args.min_b2_delta_lift,
        min_b2_outcome_miss_reduction_lift=args.min_b2_outcome_miss_reduction_lift,
        max_b2_p95_latency_delta_pct=args.max_b2_p95_latency_delta_pct,
        max_b2_payload_delta_pct=args.max_b2_payload_delta_pct,
        max_b3_p95_ms=args.max_b3_p95_ms,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["summary"]["decision"]["status"] == "L2_LEARNING_AB_GO" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", default=os.environ.get("DEEPTUTOR_L2_AB_API_BASE_URL", "https://test2.yousenjiaoyu.com"))
    parser.add_argument("--auth-token", default="")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--username-prefix", default="qa_pgo_l2_ab")
    parser.add_argument("--loops", type=int, default=10)
    parser.add_argument("--min-loops", type=int, default=0)
    parser.add_argument("--order-mode", choices=("alternating", "forward", "reverse", "randomized"), default="alternating")
    parser.add_argument("--seed", type=int, default=20260615)
    parser.add_argument("--connection-mode", choices=("single", "per-turn"), default="per-turn")
    parser.add_argument("--inter-turn-delay-seconds", type=float, default=8.0)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--min-b2-delta-lift", "--min-b1-delta-lift", dest="min_b2_delta_lift", type=float, default=0.05)
    parser.add_argument(
        "--min-b2-outcome-miss-reduction-lift",
        "--min-b1-pgo-miss-reduction-lift",
        dest="min_b2_outcome_miss_reduction_lift",
        type=float,
        default=1.0,
    )
    parser.add_argument("--max-b2-p95-latency-delta-pct", type=float, default=250.0)
    parser.add_argument("--max-b2-payload-delta-pct", type=float, default=50.0)
    parser.add_argument("--max-b3-p95-ms", type=float, default=50.0)
    parser.add_argument("--b3-iterations", type=int, default=30)
    parser.add_argument("--out-dir", default="")
    return parser


def main() -> int:
    return asyncio.run(_main_async(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
