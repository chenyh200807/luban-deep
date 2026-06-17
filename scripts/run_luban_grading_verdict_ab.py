#!/usr/bin/env python3
"""Nexus-vs-RAG grading verdict: gold panel + three candidate arms + 9-dim scorecard.

The judgment run for "does the typed scoring-point contract arm win on
consistency / granularity / auditability — even when the headline total is a
tie?". It does NOT look at headline totals; it compares three candidate graders
against a trustworthy per-scoring-point gold along nine product-value axes.

Pipeline (all over the SAME golden_v1 eval_samples, so every arm and the gold
share the same {case -> P1..Pn} scoring-point taxonomy):

  A. GOLD   reuse the pure-API arbitration panel (deepseek-v4-flash + qwen-max +
            glm-4-plus blind, deepseek-reasoner arbiter) to produce a per-point
            consensus verdict + full-slice Fleiss' kappa. When kappa < 0.6 the
            gold is ai_council_directional and quality_claim_allowed=false: the
            scorecard is then a DIRECTIONAL read, never a trustworthy quality
            claim.
  B. ARMS   grade the same answers with three candidate arms that differ ONLY in
            the rubric context supplied:
              - typed_case_grading_artifact_grader : golden points wrapped as a
                typed point-contract; output gated by the Phase-1 locked
                per-point schema validator (run_luban_student_answer_grading_eval
                .validate_grading_output) with one contract-feedback regrade.
              - runtime_slim_grader                : golden points as a slim
                grounding blob; no locked contract.
              - kbv5_grader                        : golden points + kbv5
                retrieval chunks; no locked contract.
            Each arm emits one verdict per golden point_id, so it lines up with
            the gold point-for-point.
  C. SCORE  per arm vs the gold, the nine axes:
              1 hit/miss concordance with gold
              2 validator contract pass rate
              3 deduction-reason completeness
              4 error/misconception tag completeness+stability
              5 student-evidence-quote completeness
              6 miss rate  (gold=hit but arm=miss)
              7 over-credit rate (gold=miss but arm=hit)
              8 per-point ordinal score MAE
              9 field-schema compliance rate

Scope: candidate_only / review_only. production_write_count == 0. No production
DB / canonical-truth / published-registry / remote write. Offline measurement.

Tiers:
  - shape : injected fake gold panel + fake graders, no network (default; CI).
  - live  : real HTTP providers; requires --live AND
            LUBAN_GRADING_VERDICT_LIVE=1 (double opt-in). Gold panel uses
            DEEPSEEK/DASHSCOPE/BIGMODEL keys; grading arms use the configured
            grading provider (default deepseek-chat via DEEPSEEK_API_KEY).

Usage:
  python scripts/run_luban_grading_verdict_ab.py --cases Q2-1A436000-罚则,Q3-1A433000
  LUBAN_GRADING_VERDICT_LIVE=1 python scripts/run_luban_grading_verdict_ab.py \
      --cases Q2-1A436000-罚则 --tier live --live
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import luban_grading_metrics as metrics  # noqa: E402
from scripts import run_luban_arbitration_gold_panel as panel  # noqa: E402
from scripts import run_luban_student_answer_grading_eval as grading_eval  # noqa: E402

SCHEMA_VERSION = "luban_grading_verdict_ab.v1"
GOLDEN_FIXTURE = REPO / "deeptutor/services/benchmark/fixtures/luban_case_grading_golden_v1.json"
LIVE_ENV_FLAG = "LUBAN_GRADING_VERDICT_LIVE"
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/luban_grading_verdict_ab_20260613"

ARM_TYPED = "typed_case_grading_artifact_grader"
ARM_RUNTIME_SLIM = "runtime_slim_grader"
ARM_KBV5 = "kbv5_grader"
VERDICT_ARMS = (ARM_TYPED, ARM_RUNTIME_SLIM, ARM_KBV5)

HIT_ORD = {"miss": 0, "partial": 1, "hit": 2, "contradiction": 0}
GradeFn = Callable[[str, dict[str, Any], list[dict[str, Any]], dict[str, Any]], dict[str, Any]]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ord(verdict: Any) -> int:
    return HIT_ORD.get(str(verdict or "").lower(), 0)


# --------------------------------------------------------------- gold reference


def _gold_consensus(panel_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], str]:
    """Map (case_id, student_id, point_id) -> panel consensus verdict.

    Unadjudicated points are dropped: they have no trustworthy gold, so they are
    excluded from every arm comparison rather than counted as a fake label.
    """
    gold: dict[tuple[str, str, str], str] = {}
    for row in panel_rows:
        verdict = str(row.get("consensus_verdict") or "")
        if verdict in (panel.UNADJUDICATED, ""):
            continue
        key = (str(row.get("case_id")), str(row.get("student_id")), str(row.get("point_id")))
        gold[key] = verdict
    return gold


# --------------------------------------------------------------- typed artifact


def _typed_artifact_for_case(case: dict[str, Any]) -> dict[str, Any]:
    """Wrap golden_v1 gold points as a typed point-contract for the typed arm.

    Mirrors the production-shaped contract from
    ``run_luban_student_answer_grading_eval.build_typed_case_grading_artifact``:
    one subquestion per case, one scoring_point per golden point_id, the locked
    output_contract, and weights = each point's max_score so the validator's
    Σawarded/Σmax recompute is exercised. No new scoring truth is invented; this
    only restructures the curated golden points.
    """
    scoring_points: list[dict[str, Any]] = []
    for gp in case.get("gold_scoring_points") or []:
        point_id = str(gp.get("point_id") or "")
        label = str(gp.get("label") or "")
        scoring_points.append(
            {
                "point_id": point_id,
                "sub_no": "1",
                "weight": float(gp.get("max_score") or 0.0),
                "canonical_answer": label[:140],
                "acceptable_variants": [label[:140]],
                "required_terms": [],
                "miss_tags": ["漏列采分点"],
                "source_refs": [],
                "official_basis": str(gp.get("official_basis") or ""),
                "provenance": {"gold_ref": f"golden_v1:{case.get('case_id')}:{point_id}", "sourced": True},
            }
        )
    return {
        "artifact_schema": "case_grading_artifact.v1",
        "case_id": case.get("case_id"),
        "source": "golden_v1_scoring_points_restructured_as_point_contract",
        "source_chunks": [],
        "subquestions": [
            {
                "sub_no": "1",
                "intent": "flaw_correction",
                "max_score": float(case.get("max_score") or 0.0),
                "question": str(case.get("stem") or "")[:220],
                "scoring_points": scoring_points,
                "partial_credit_rules": ["hit=覆盖该point_id核心语义; partial=只覆盖部分关键条件; miss=未覆盖/关键判断错"],
                "common_traps": ["概括性整改表述不能替代明确采分点"],
                "next_action_templates": ["围绕漏判point_id回看规范条文"],
            }
        ],
        "score_aggregation": "sum(point.awarded_points)/sum(point.weight)*100",
        "output_contract": {
            "must_emit_one_result_per_point_id": True,
            "score_must_equal_point_sum": True,
            "deduction_required_if_any_miss": True,
            "weakness_required_if_any_miss": True,
            "basis_ref_must_use_point_id": True,
        },
    }


# --------------------------------------------------------------- grading prompt


def _grading_messages(arm: str, case: dict[str, Any], sample: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    gold_points = [
        {"point_id": gp.get("point_id"), "max_score": gp.get("max_score"),
         "label": gp.get("label"), "official_basis": gp.get("official_basis")}
        for gp in case.get("gold_scoring_points") or []
    ]
    typed = context.get("typed_case_grading_artifact") if isinstance(context.get("typed_case_grading_artifact"), dict) else None
    payload = {
        "case_id": case.get("case_id"),
        "student_id": sample.get("student_id"),
        "question": str(case.get("stem") or "")[:2600],
        "student_answer": str(sample.get("answer_text") or "")[:2200],
        "reference_gold_points": [] if typed else gold_points,
        "context": context,
        "required_json": {
            "score_pct": "0-100 estimated score for THIS student answer",
            "point_results": [
                {
                    "point_id": "one per golden point_id",
                    "sub_no": "question number",
                    "status": "hit | partial | miss | contradiction",
                    "awarded_points": "numeric points awarded",
                    "max_points": "numeric max points",
                    "required_points": "list",
                    "accepted_variants": "list",
                    "deduction_reason": "specific Chinese reason (empty only when hit)",
                    "misconception_tag": "stable short Chinese tag",
                    "student_evidence_quote": "short verbatim quote from student answer",
                    "next_review_action": "string or object",
                    "learning_evidence_event": "object",
                    "basis_ref": "point_id",
                }
            ],
            "deduction_reasons": "list of Chinese reasons",
            "misconception_tags": "list of stable tags",
        },
    }
    system = (
        "You are a strict Chinese construction-exam grader (一级建造师建筑实务案例题). Grade the STUDENT "
        "answer against the golden scoring points. Emit exactly one point_results item per golden point_id. "
        "For every point include point_id, status, awarded_points, max_points, required_points, "
        "accepted_variants, deduction_reason, misconception_tag, student_evidence_quote, next_review_action, "
        "learning_evidence_event, and basis_ref=point_id. If any point is miss/partial/contradiction do not "
        "give it full marks and give a non-empty deduction_reason. score_pct must equal the awarded-point sum "
        "over the max sum. Return JSON only."
    )
    if typed:
        system += (
            " The context.typed_case_grading_artifact is the rubric authority: its scoring_points.point_id set "
            "is the exact set you must emit, and you must not collapse points."
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def _arm_context(arm: str, case: dict[str, Any], retrieval: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {"mode": arm}
    if arm == ARM_TYPED:
        context["typed_case_grading_artifact"] = _typed_artifact_for_case(case)
    elif arm == ARM_RUNTIME_SLIM:
        lines = [f"{gp.get('point_id')}（{gp.get('max_score')}分）：{gp.get('label')}"
                 for gp in case.get("gold_scoring_points") or []]
        context["rich_leaf_grounding"] = "\n".join(lines)
    elif arm == ARM_KBV5:
        context["retrieved_chunks"] = [
            {"chunk_id": c.get("chunk_id"), "doc_type": c.get("doc_type"),
             "content": str(c.get("content") or "")[:450]}
            for c in (retrieval.get("chunks") or [])
        ]
    return context


# --------------------------------------------------------------- live grading


def _build_live_grade_fn(provider_call: Callable[..., dict[str, Any]], retriever, max_tokens: int) -> GradeFn:
    """One grader callable shared by all arms; arms differ only by context.

    The typed arm additionally runs the Phase-1 locked-schema validator and a
    single contract-feedback regrade — exactly the production contract path.
    """
    def grade(arm: str, case: dict[str, Any], _gold_points: list[dict[str, Any]], sample: dict[str, Any]) -> dict[str, Any]:
        retrieval = {"status": "skipped", "chunks": []}
        if arm == ARM_KBV5 and retriever is not None:
            query = f"{case.get('stem')}\n学生作答：{sample.get('answer_text')}"
            retrieval = retriever(query)
        context = _arm_context(arm, case, retrieval)
        messages = _grading_messages(arm, case, sample, context)
        response = provider_call(messages, max_tokens=max_tokens)
        content = str(response.get("content") or "")
        parsed = grading_eval.case_eval._parse_json_object(content)
        normalized = grading_eval.normalize_grading_payload(parsed)
        validation = grading_eval.validate_grading_output(context, normalized)
        regrade_attempted = False
        if validation.get("should_regrade"):
            regrade_attempted = True
            retry_messages = messages + [
                {"role": "assistant", "content": content[:2400]},
                {"role": "user", "content": (
                    "你上一次的判分输出违反了评分合约，必须修正后重新输出 JSON。违规清单："
                    + json.dumps(validation.get("errors") or [], ensure_ascii=False)
                    + "。要求：每个 point_id 一条结果且锁死字段齐全；任何 miss/partial 必须给非空 deduction_reason；"
                      "Σawarded≤Σmax；score_pct 与点和自洽。只返回 JSON。")},
            ]
            retry = provider_call(retry_messages, max_tokens=max_tokens)
            retry_content = str(retry.get("content") or "")
            retry_parsed = grading_eval.case_eval._parse_json_object(retry_content)
            retry_normalized = grading_eval.normalize_grading_payload(retry_parsed)
            retry_validation = grading_eval.validate_grading_output(context, retry_normalized)
            if retry_validation.get("status") != "contract_invalid":
                normalized, validation = retry_normalized, retry_validation
        return {
            "point_results": normalized.get("point_results") or [],
            "score_pct": normalized.get("score_pct"),
            "validation_status": validation.get("status"),
            "regrade_attempted": regrade_attempted,
        }

    return grade


def _shape_grade_fn() -> GradeFn:
    """Deterministic fake grader: emits a full, contract-shaped point_result per
    golden point so the scorecard math is exercised offline (no network)."""
    def grade(arm: str, case: dict[str, Any], gold_points: list[dict[str, Any]], sample: dict[str, Any]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for index, gp in enumerate(gold_points):
            h = (abs(hash((arm, gp.get("point_id"), sample.get("student_id")))) ) % 10
            status = "hit" if h < 6 else ("partial" if h < 8 else "miss")
            max_pts = float(gp.get("max_score") or 0.0)
            awarded = max_pts if status == "hit" else (round(max_pts / 2, 2) if status == "partial" else 0.0)
            results.append({
                "point_id": gp.get("point_id"),
                "sub_no": "1",
                "max_points": max_pts,
                "required_points": [],
                "accepted_variants": [],
                "student_evidence_quote": str(sample.get("answer_text") or "")[:12],
                "status": status,
                "awarded_points": awarded,
                "deduction_reason": "" if status == "hit" else "漏列关键采分点",
                "misconception_tag": "" if status == "hit" else "漏列采分点",
                "next_review_action": "回看规范条文",
                "learning_evidence_event": {"knowledge_points": [], "weaknesses": []},
                "basis_ref": gp.get("point_id"),
            })
        total_max = sum(float(gp.get("max_score") or 0.0) for gp in gold_points) or 1.0
        awarded_sum = sum(r["awarded_points"] for r in results)
        # The typed arm passes the locked schema (full fields); the slim/kbv5 arms
        # drop two fields to model the looser contract -> contract_invalid.
        if arm != ARM_TYPED:
            for r in results:
                r.pop("required_points", None)
                r.pop("accepted_variants", None)
        return {
            "point_results": results,
            "score_pct": round(awarded_sum / total_max * 100, 2),
            "validation_status": "passed" if arm == ARM_TYPED else "contract_invalid",
            "regrade_attempted": arm != ARM_TYPED,
        }

    return grade


# --------------------------------------------------------------- scorecard


_FIELD_REQUIRED = (
    "point_id", "status", "awarded_points", "max_points",
    "deduction_reason", "misconception_tag", "student_evidence_quote",
)


def _field_compliant(result: dict[str, Any]) -> bool:
    return all(key in result for key in _FIELD_REQUIRED)


def _index_results(point_results: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in point_results:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("point_id") or item.get("basis_ref") or "")
        if pid:
            out[pid] = item
    return out


def _arm_scorecard(
    arm: str,
    arm_rows: list[dict[str, Any]],
    gold: dict[tuple[str, str, str], str],
) -> dict[str, Any]:
    pred_ord: list[int] = []
    gold_ord: list[int] = []
    pred_hits: list[str] = []
    gold_hits: list[str] = []
    miss_when_gold_hit = 0
    overcredit_when_gold_miss = 0
    gold_hit_total = 0
    gold_miss_total = 0
    abs_score_err: list[float] = []
    field_total = 0
    field_compliant = 0
    deduction_needed = deduction_present = 0
    tag_needed = tag_present = 0
    evidence_needed = evidence_present = 0
    tag_values: list[str] = []
    validator_rows = 0
    validator_passed = 0
    contract_enforced_rows = 0

    for row in arm_rows:
        case_id = str(row.get("case_id"))
        student_id = str(row.get("student_id"))
        if row.get("validation_status"):
            validator_rows += 1
            if row["validation_status"] == "passed":
                validator_passed += 1
            # A pass is only meaningful when a real (typed) contract was applied.
            # Arms without a typed artifact pass the validator trivially; count
            # how many rows were under genuine locked-schema enforcement so the
            # verdict can refuse to treat a vacuous 1.0 as a quality win.
            if row.get("regrade_attempted") or row.get("contract_invalid_before_regrade"):
                contract_enforced_rows += 1
        results = _index_results(row.get("point_results") or [])
        for pid, gold_verdict in {k[2]: v for k, v in gold.items() if k[0] == case_id and k[1] == student_id}.items():
            item = results.get(pid)
            field_total += 1
            arm_status = str((item or {}).get("status") or "").lower()
            if item is not None and _field_compliant(item):
                field_compliant += 1
            # Axis 1/6/7/8: hit-concordance, miss/over-credit, ordinal MAE.
            gv = _ord(gold_verdict)
            av = _ord(arm_status) if item is not None else 0
            pred_ord.append(av)
            gold_ord.append(gv)
            pred_hits.append(arm_status if item is not None else "miss")
            gold_hits.append(gold_verdict)
            abs_score_err.append(abs(av - gv))
            if gold_verdict == "hit":
                gold_hit_total += 1
                if arm_status == "miss" or item is None:
                    miss_when_gold_hit += 1
            if gold_verdict == "miss":
                gold_miss_total += 1
                if arm_status == "hit":
                    overcredit_when_gold_miss += 1
            # Axis 3/4/5: completeness of deduction / tag / evidence on non-hit points.
            if arm_status in {"partial", "miss", "contradiction"}:
                deduction_needed += 1
                if str((item or {}).get("deduction_reason") or "").strip():
                    deduction_present += 1
                tag_needed += 1
                tag = str((item or {}).get("misconception_tag") or "").strip()
                if tag:
                    tag_present += 1
                    tag_values.append(tag)
            if arm_status in {"hit", "partial"}:
                evidence_needed += 1
                if str((item or {}).get("student_evidence_quote") or "").strip():
                    evidence_present += 1

    n = len(gold_ord)

    def rate(num: int, den: int) -> float | None:
        return round(num / den, 4) if den else None

    distinct_tags = len(set(tag_values))
    tag_stability = round(distinct_tags / len(tag_values), 4) if tag_values else None
    return {
        "arm": arm,
        "compared_point_count": n,
        # 1 hit/miss concordance with gold
        "axis1_hit_concordance": metrics.agreement_block(pred_hits, gold_hits) if n else None,
        # 2 validator contract pass rate. ``contract_enforced`` distinguishes a
        # REAL locked-schema pass (typed arm: every row checked, regrades fired)
        # from a vacuous pass (slim/kbv5: no typed artifact -> validator returns
        # passed trivially). A 1.0 with contract_enforced=False is not a quality
        # win and is excluded from the typed-vs-other comparison.
        "axis2_validator_pass_rate": rate(validator_passed, validator_rows),
        "axis2_validator_rows": validator_rows,
        "axis2_contract_enforced": arm == ARM_TYPED,
        "axis2_contract_enforced_rows": contract_enforced_rows,
        # 3 deduction-reason completeness on non-hit points
        "axis3_deduction_completeness": rate(deduction_present, deduction_needed),
        "axis3_deduction_needed": deduction_needed,
        # 4 misconception/error tag completeness + stability
        "axis4_tag_completeness": rate(tag_present, tag_needed),
        "axis4_tag_distinct_per_emitted": tag_stability,
        # 5 student-evidence-quote completeness on credited points
        "axis5_evidence_completeness": rate(evidence_present, evidence_needed),
        "axis5_evidence_needed": evidence_needed,
        # 6 miss rate (gold=hit, arm=miss/absent)
        "axis6_miss_rate": rate(miss_when_gold_hit, gold_hit_total),
        "axis6_gold_hit_total": gold_hit_total,
        # 7 over-credit rate (gold=miss, arm=hit)
        "axis7_overcredit_rate": rate(overcredit_when_gold_miss, gold_miss_total),
        "axis7_gold_miss_total": gold_miss_total,
        # 8 per-point ordinal score MAE
        "axis8_ordinal_mae": round(sum(abs_score_err) / n, 4) if n else None,
        # 9 field schema compliance rate
        "axis9_field_compliance_rate": rate(field_compliant, field_total),
    }


# --------------------------------------------------------------- run


def run_verdict(
    cases: list[dict[str, Any]],
    *,
    gold_panel: dict[str, Any],
    grade_fn: GradeFn,
    arms: tuple[str, ...] = VERDICT_ARMS,
) -> dict[str, Any]:
    gold = _gold_consensus(gold_panel["rows"])
    arm_rows: dict[str, list[dict[str, Any]]] = {arm: [] for arm in arms}
    sample_count = 0
    for case in cases:
        gold_points = case.get("gold_scoring_points") or []
        for sample in case.get("eval_samples") or []:
            sample_count += 1
            for arm in arms:
                graded = grade_fn(arm, case, gold_points, sample)
                arm_rows[arm].append({
                    "case_id": case.get("case_id"),
                    "student_id": sample.get("student_id"),
                    **graded,
                })
    scorecards = [_arm_scorecard(arm, arm_rows[arm], gold) for arm in arms]
    return {
        "gold_point_count": len(gold),
        "sample_count": sample_count,
        "scorecards": scorecards,
        "arm_rows": arm_rows,
    }


def _concordance(sc: dict[str, Any]) -> float | None:
    block = sc.get("axis1_hit_concordance")
    return block.get("qwk") if isinstance(block, dict) else None


def _verdict_summary(scorecards: list[dict[str, Any]], quality_claim_allowed: bool) -> dict[str, Any]:
    """Where does the typed contract arm win / lose vs the other two arms?

    Judged on the accuracy axis (1, via QWK concordance), the audit-quality axes
    (2,3,4,5,9) and the error axes (6,7,8) — NOT the headline total. Returned
    facts are honest even when quality_claim_allowed is false (DIRECTIONAL then).

    axis2 (validator pass rate) is EXCLUDED from the comparison unless the other
    arms also enforced a real contract: an arm with no typed artifact passes the
    validator trivially, so its 1.0 is vacuous and must not count as beating the
    typed arm. This keeps the verdict from mislabeling enforcement asymmetry as a
    typed-arm loss.
    """
    by_arm = {sc["arm"]: sc for sc in scorecards}
    typed = by_arm.get(ARM_TYPED)
    others = [sc for sc in scorecards if sc["arm"] != ARM_TYPED]
    if typed is None or not others:
        return {"verdict": "insufficient_arms"}

    others_enforced_contract = any(sc.get("axis2_contract_enforced") for sc in others)

    def value(sc: dict[str, Any], key: str) -> float | None:
        if key == "axis1_concordance_qwk":
            return _concordance(sc)
        v = sc.get(key)
        return v if isinstance(v, (int, float)) else None

    def best_other(key: str, higher_is_better: bool) -> float | None:
        vals = [value(sc, key) for sc in others]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        return max(vals) if higher_is_better else min(vals)

    higher = {
        "axis1_concordance_qwk", "axis3_deduction_completeness", "axis4_tag_completeness",
        "axis5_evidence_completeness", "axis9_field_compliance_rate",
    }
    if others_enforced_contract:
        higher.add("axis2_validator_pass_rate")
    # axis4 stability and the error axes: lower is better.
    lower = {"axis4_tag_distinct_per_emitted", "axis6_miss_rate", "axis7_overcredit_rate", "axis8_ordinal_mae"}
    wins: list[str] = []
    losses: list[str] = []
    for key in higher | lower:
        tv = value(typed, key)
        ov = best_other(key, key in higher)
        if tv is None or ov is None:
            continue
        if key in higher:
            if tv > ov:
                wins.append(key)
            elif tv < ov:
                losses.append(key)
        else:
            if tv < ov:
                wins.append(key)
            elif tv > ov:
                losses.append(key)
    return {
        "typed_arm_wins_on": sorted(wins),
        "typed_arm_loses_on": sorted(losses),
        "axis2_excluded_reason": (
            None if others_enforced_contract
            else "other_arms_pass_validator_trivially_no_typed_contract"
        ),
        "typed_arm_validator_pass_rate_under_real_contract": typed.get("axis2_validator_pass_rate"),
        "quality_claim_allowed": quality_claim_allowed,
        "interpretation": (
            "typed_contract_arm_wins_on_auditability"
            if len(wins) > len(losses) else
            "typed_contract_arm_not_clearly_ahead"
        ),
        "directional_only": not quality_claim_allowed,
    }


def _slice_cases(golden: dict[str, Any], wanted: list[str], max_students: int) -> list[dict[str, Any]]:
    by_id = {c["case_id"]: c for c in golden["cases"]}
    missing = [cid for cid in wanted if cid not in by_id]
    if missing:
        raise KeyError(f"unknown case_ids: {missing}")
    cases = [by_id[cid] for cid in wanted]
    if max_students > 0:
        cases = [{**c, "eval_samples": (c.get("eval_samples") or [])[:max_students]} for c in cases]
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="Q2-1A436000-罚则,Q3-1A433000",
                        help="comma-separated case_ids from luban_case_grading_golden_v1.json")
    parser.add_argument("--tier", choices=["shape", "live"], default="shape")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-students", type=int, default=0, help="cap eval_samples per case (0=all)")
    parser.add_argument("--provider", default="deepseek", help="grading provider (run_luban_rich_leaf_case_question_eval.PROVIDER_DEFAULTS)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--grading-max-tokens", type=int, default=1400)
    parser.add_argument("--timeout-s", type=float, default=90.0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    golden = _read_json(GOLDEN_FIXTURE)
    wanted = [c.strip() for c in args.cases.split(",") if c.strip()]
    try:
        cases = _slice_cases(golden, wanted, args.max_students)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    live_ok = args.tier == "live" and args.live and os.environ.get(LIVE_ENV_FLAG) == "1"
    if args.tier == "live" and not live_ok:
        print(f"ERROR: live tier requires --live AND {LIVE_ENV_FLAG}=1", file=sys.stderr)
        return 2

    # A. GOLD PANEL (reuse the arbitration panel end to end).
    if live_ok:
        judge_fns, _stats, roster = panel.build_live_judges()
    else:
        judge_fns, _stats, roster = panel._shape_judges()
    panel_ids = roster["blind_panel_live"]
    if len(panel_ids) < 3:
        print(f"ERROR: gold panel needs >=3 live independent models; got {panel_ids} "
              f"(degraded: {roster['blind_panel_degraded']})", file=sys.stderr)
        return 3
    gold_panel = panel.run_panel(cases, judge_fns, panel_ids, roster.get("arbiter"))
    kappa_block = gold_panel["panel_fleiss_kappa"]
    quality_claim_allowed = bool(kappa_block["quality_claim_allowed"])

    # B. CANDIDATE ARMS.
    if live_ok:
        provider_call = grading_eval.case_eval._openai_compat_provider(
            provider=args.provider,
            model=args.model or grading_eval.case_eval.PROVIDER_DEFAULTS[args.provider]["model"],
            timeout_s=args.timeout_s,
        )
        if provider_call is None:
            print(f"ERROR: grading provider {args.provider} has no API key", file=sys.stderr)
            return 3
        retriever = grading_eval.case_eval._kbv5_retriever(
            3, doc_types=grading_eval.case_eval.DEFAULT_KBV5_DOC_TYPES
        )
        grade_fn = _build_live_grade_fn(provider_call, retriever, args.grading_max_tokens)
        grading_model = args.model or grading_eval.case_eval.PROVIDER_DEFAULTS[args.provider]["model"]
    else:
        grade_fn = _shape_grade_fn()
        grading_model = "shape_fake_grader"

    # C. SCORECARD.
    result = run_verdict(cases, gold_panel=gold_panel, grade_fn=grade_fn)
    summary = _verdict_summary(result["scorecards"], quality_claim_allowed)

    out_dir = Path(args.output_dir) if Path(args.output_dir).is_absolute() else REPO / args.output_dir
    safety = {
        "production_db_write": False, "canonical_truth_write": False,
        "published_registry_write": False, "remote_write": False,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "classification": "candidate_only",
        "review_status": "review_only",
        "production_write_count": 0,
        "safety": safety,
        "tier": args.tier,
        "live": live_ok,
        "golden_fixture": str(GOLDEN_FIXTURE.relative_to(REPO)),
        "cases": wanted,
        "slice": {"case_count": len(cases), "sample_count": result["sample_count"],
                  "gold_point_count": result["gold_point_count"]},
        "gold_panel_roster": roster,
        "gold_fleiss_kappa": kappa_block,
        "quality_claim_allowed": quality_claim_allowed,
        "gold_label_authority": kappa_block["label_authority"],
        "grading_model": grading_model,
        "arms": list(VERDICT_ARMS),
        "scorecards": result["scorecards"],
        "verdict_summary": summary,
    }
    _write_json(out_dir / "verdict_scorecard.json", report)
    _write_json(out_dir / "gold_panel.json", {
        "schema_version": panel.SCHEMA_VERSION,
        "safety": safety,
        "panel_roster": roster,
        "aggregate": {k: v for k, v in gold_panel.items() if k != "rows"},
        "rows": gold_panel["rows"],
    })
    _write_json(out_dir / "arm_rows.json", {"arm_rows": result["arm_rows"]})

    print(json.dumps({
        "tier": args.tier, "live": live_ok,
        "slice": report["slice"],
        "fleiss_kappa": kappa_block["fleiss_kappa"],
        "quality_claim_allowed": quality_claim_allowed,
        "verdict": summary.get("interpretation"),
        "typed_arm_wins_on": summary.get("typed_arm_wins_on"),
        "typed_arm_loses_on": summary.get("typed_arm_loses_on"),
        "output_dir": str(out_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
